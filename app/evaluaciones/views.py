from itertools import groupby

import segno
from django import forms
from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.db.models import Prefetch
from django.forms import modelformset_factory
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    DocumentoForm, EquipoForm, EquipoTiposForm, ExencionForm, IncidenciaForm,
    MedidaForm,
)
from .importador import importar_equipos
from .models import (
    Criterio, Documento, Equipo, Evaluacion, ExencionDocumental, Incidencia,
    Linea, Medida, Respuesta,
)


def _marcar_desfasadas(equipo, tipos_antes):
    """Marca para revisión las evaluaciones que han quedado incompletas.

    Añadir un tipo hace aplicables criterios del Anexo I.2 que las
    evaluaciones anteriores nunca comprobaron, así que dejan de ser fiables.
    Quitar un tipo no las invalida: solo deja respuestas que ya no aplican.

    Se llama desde las dos vistas que pueden cambiar los tipos de un equipo.
    El admin de Django los cambia sin pasar por aquí; es una limitación
    conocida de la trastienda de administración.
    """
    tipos_despues = set(equipo.tipos.values_list('pk', flat=True))
    if tipos_despues - tipos_antes:
        equipo.evaluaciones.update(en_revision=True, motivo_revision='T')


def inicio(request):
    """Portada: los equipos organizados por línea de producción (RF-05).

    Es también el punto de entrada de la aplicación: hasta ahora solo se
    podía navegar escribiendo la dirección de cada ficha.
    """
    # Las medidas se traen por dos caminos porque la columna de estado
    # pregunta dos cosas distintas: qué no conformidades siguen sin medida
    # (por respuesta) y hasta cuándo llegan las fechas previstas (por
    # evaluación). Sin los dos, cada fila de la tabla consultaría por su
    # cuenta.
    # «documentos» y el criterio de cada respuesta los pide además el aviso
    # de evidencia documental de la última evaluación.
    equipos = Equipo.objects.prefetch_related(
        'tipos',
        'documentos',
        'exenciones',
        'incidencias',
        'evaluaciones__respuestas__medidas',
        'evaluaciones__respuestas__criterio__evidencias_esperadas',
        'evaluaciones__medidas',
    )
    lineas = Linea.objects.prefetch_related(
        Prefetch('equipos', queryset=equipos),
    )
    return render(request, 'evaluaciones/inicio.html', {
        'lineas': lineas,
        'sin_linea': equipos.filter(linea__isnull=True),
        'total': equipos.count(),
    })


def equipo_alta(request):
    """Alta individual de un equipo con validación de datos (RF-01).

    Quien da de alta un equipo a mano responde también por sus tipos, así
    que el formulario los marca como confirmados aunque no señale ninguno.
    """
    if request.method == 'POST':
        form = EquipoForm(request.POST)
        if form.is_valid():
            equipo = form.save()
            # Quien da de alta un equipo a mano responde también por su tipo,
            # aunque no marque ninguno. La edición no: allí se corrigen datos
            # del equipo, y confirmar el tipo es una decisión aparte que no
            # debe darse por hecha sin que nadie la tome.
            equipo.tipos_confirmados = True
            equipo.save(update_fields=['tipos_confirmados'])
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = EquipoForm()
    return render(request, 'evaluaciones/equipo_alta.html', {'form': form})


def equipo_detalle(request, pk):
    """Ficha de gestión de un equipo.

    Exige sesión, como el resto de la aplicación. La consulta en modo solo
    lectura del RF-10 no es esta pantalla, sino la que cuelga del código QR.
    """
    # Los documentos se traen con el equipo porque cada evaluación los
    # consulta para saber si le falta alguna evidencia: sin esto sería una
    # consulta por evaluación.
    equipo = get_object_or_404(
        Equipo.objects.prefetch_related('documentos', 'exenciones'), pk=pk
    )
    # El dictamen recorre las respuestas de cada evaluación, y el aviso de
    # evidencias necesita además su criterio: sin prefetch sería una consulta
    # por evaluación listada.
    evaluaciones = equipo.evaluaciones.prefetch_related(
        'respuestas__criterio__evidencias_esperadas'
    )
    return render(request, 'evaluaciones/equipo_detalle.html', {
        'equipo': equipo,
        'evaluaciones': evaluaciones,
        'documentos': equipo.documentos.all(),
        'exenciones': equipo.exenciones.all(),
        'incidencias': equipo.incidencias.all(),
        'evidencias_pendientes': equipo.evidencias_pendientes,
    })


def equipo_importar(request):
    """Importación por lotes desde .xlsx o .csv con validación (RF-02).

    Las filas que no superan la validación se rechazan una a una, con su
    motivo, sin abortar la importación de las demás.
    """
    resultado = None
    if request.method == 'POST':
        fichero = request.FILES.get('fichero')
        if fichero is not None:
            resultado = importar_equipos(fichero, fichero.name)
    return render(request, 'evaluaciones/equipo_importar.html', {'resultado': resultado})


def equipo_editar(request, pk):
    """Corregir o completar los datos de un equipo (necesario para RF-05).

    La importación por lotes admite equipos con campos vacíos y sin línea, y
    un equipo puede trasladarse de una línea a otra. Sin poder editarlos,
    esos equipos no podrían organizarse nunca por línea de producción, de
    modo que RF-05 quedaría fuera del alcance de la aplicación.
    """
    equipo = get_object_or_404(Equipo, pk=pk)

    if request.method == 'POST':
        tipos_antes = set(equipo.tipos.values_list('pk', flat=True))
        form = EquipoForm(request.POST, instance=equipo)
        if form.is_valid():
            form.save()
            _marcar_desfasadas(equipo, tipos_antes)
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = EquipoForm(instance=equipo)

    return render(request, 'evaluaciones/equipo_editar.html', {
        'equipo': equipo,
        'form': form,
    })


def equipo_tipos(request, pk):
    """Indicar a qué tipos del Anexo I.2 pertenece un equipo (apoyo a RF-04).

    La importación por lotes (RF-02) no trae el tipo, y de él dependen los
    criterios aplicables. Guardar marca el equipo como confirmado aunque no
    se señale ningún tipo: un equipo fijo no es de ninguno, y eso es una
    respuesta, no un dato que falte.
    """
    equipo = get_object_or_404(Equipo, pk=pk)
    # Si se llega aquí desde el intento de evaluar, hay que volver allí.
    evaluar = '1' in (request.GET.get('evaluar'), request.POST.get('evaluar'))

    if request.method == 'POST':
        tipos_antes = set(equipo.tipos.values_list('pk', flat=True))
        form = EquipoTiposForm(request.POST, instance=equipo)
        if form.is_valid():
            form.save()
            _marcar_desfasadas(equipo, tipos_antes)
            if evaluar:
                return redirect('evaluaciones:evaluacion_nueva', pk=equipo.pk)
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = EquipoTiposForm(instance=equipo)

    return render(request, 'evaluaciones/equipo_tipos.html', {
        'equipo': equipo,
        'form': form,
        'evaluar': evaluar,
    })


def evaluacion_nueva(request, pk):
    """Evaluar la conformidad de un equipo frente al RD 1215/1997 (RF-04).

    Los criterios que se presentan no son fijos: dependen de los tipos del
    equipo según el Anexo I.2, de modo que un equipo fijo responde solo a
    las disposiciones generales del Anexo I.1.

    Cada evaluación se guarda como un registro nuevo y nunca sobrescribe
    las anteriores (RF-03). La evaluación solo se crea si todas las
    respuestas son válidas, para que no queden evaluaciones a medias en el
    histórico.
    """
    equipo = get_object_or_404(Equipo, pk=pk)

    # Los equipos importados por lotes llegan sin tipo: hay que preguntarlo
    # antes de evaluar, porque de él dependen los criterios aplicables.
    if not equipo.tipos_confirmados:
        url = reverse('evaluaciones:equipo_tipos', kwargs={'pk': equipo.pk})
        return redirect(f'{url}?evaluar=1')

    criterios = list(
        Criterio.objects.filter(grupo__in=equipo.grupos_aplicables())
    )

    RespuestaFormSet = modelformset_factory(
        Respuesta,
        fields=['criterio', 'resultado', 'indicaciones'],
        extra=len(criterios),
        widgets={
            'resultado': forms.Select(
                attrs={'class': 'form-select form-select-sm'},
            ),
            # Una línea basta dentro de la tabla; el área de texto que Django
            # elige por defecto para un TextField ocuparía toda la fila.
            'indicaciones': forms.TextInput(
                attrs={'class': 'form-control form-control-sm'},
            ),
        },
    )

    if request.method == 'POST':
        formset = RespuestaFormSet(
            request.POST,
            queryset=Respuesta.objects.none(),
        )
        if formset.is_valid():
            evaluacion = Evaluacion.objects.create(equipo=equipo)
            for respuesta in formset.save(commit=False):
                respuesta.evaluacion = evaluacion
                respuesta.save()
            return redirect('evaluaciones:evaluacion_detalle', pk=evaluacion.pk)
    else:
        formset = RespuestaFormSet(
            queryset=Respuesta.objects.none(),
            initial=[{'criterio': c} for c in criterios],
        )

    # Cada fila del formulario va emparejada con su criterio, y las filas se
    # agrupan por grupo de criterios para que la tabla reproduzca la
    # estructura del anexo en vez de repetir el nombre del grupo en cada
    # fila. groupby exige que la entrada venga ordenada, y lo está por el
    # Meta.ordering de Criterio.
    filas = list(zip(formset, criterios))
    grupos = [
        (grupo, list(pares))
        for grupo, pares in groupby(filas, key=lambda par: par[1].grupo)
    ]

    return render(request, 'evaluaciones/evaluacion_nueva.html', {
        'equipo': equipo,
        'formset': formset,
        'grupos': grupos,
    })


def evaluacion_detalle(request, pk):
    """Resultado de una evaluación concreta del histórico (RF-03, RF-04).

    Las respuestas se agrupan por grupo de criterios y se ordenan en la
    consulta, porque la plantilla solo sabe agrupar elementos que ya vengan
    consecutivos.
    """
    evaluacion = get_object_or_404(Evaluacion, pk=pk)
    respuestas = (
        evaluacion.respuestas
        .select_related('criterio__grupo')
        .order_by('criterio__grupo__orden', 'criterio__orden')
    )
    # Cada medida lista las no conformidades que ataca y el enunciado de su
    # criterio: sin prefetch serían dos consultas más por cada medida.
    medidas = evaluacion.medidas.prefetch_related('no_conformidades__criterio')
    return render(request, 'evaluaciones/evaluacion_detalle.html', {
        'evaluacion': evaluacion,
        'respuestas': respuestas,
        'medidas': medidas,
        'hay_no_conformidades': any(r.resultado == 'NC' for r in respuestas),
        'evidencias_pendientes': evaluacion.evidencias_pendientes,
    })


def medidas(request):
    """Seguimiento de las medidas correctivas de todos los equipos (RF-06).

    Es lo que da sentido a la palabra «seguimiento» del requisito: el alta y
    la consulta por evaluación no bastan si no hay dónde ver, de una vez, qué
    queda abierto en toda la instalación.

    El filtro viaja en la dirección y no en un envío de formulario para que
    cada vista filtrada sea enlazable. Por defecto se muestran solo las
    abiertas, que es lo que se quiere ver al entrar.
    """
    estado = request.GET.get('estado', 'abiertas')
    # Un valor manipulado no debe alterar la consulta: solo se aceptan los
    # estados del modelo, más los dos agregados de la propia pantalla.
    if estado not in dict(Medida.ESTADO_CHOICES) and estado != 'todas':
        estado = 'abiertas'

    medidas = (
        Medida.objects
        # El equipo se alcanza subiendo dos claves ajenas: cabe en el JOIN.
        .select_related('evaluacion__equipo')
        # Las no conformidades son varias por medida: consulta aparte.
        .prefetch_related('no_conformidades__criterio')
    )
    if estado == 'abiertas':
        medidas = medidas.filter(estado__in=['P', 'EC'])
    elif estado != 'todas':
        medidas = medidas.filter(estado=estado)

    return render(request, 'evaluaciones/medidas.html', {
        'medidas': medidas,
        'estado': estado,
        'estados': Medida.ESTADO_CHOICES,
    })


@require_POST
def medida_estado(request, pk):
    """Cambiar el estado de una medida correctiva (RF-06).

    Es lo que convierte el listado en seguimiento y no en un inventario: sin
    esto una medida nace con su estado y no puede cerrarse nunca.

    Solo acepta POST porque modifica datos: no debe poder alcanzarse
    escribiendo la dirección ni desde un enlace.
    """
    medida = get_object_or_404(Medida, pk=pk)
    estado = request.POST.get('estado')

    if estado in dict(Medida.ESTADO_CHOICES):
        medida.estado = estado
        # La fecha de cierre la lleva la vista y no el formulario: tecleada a
        # mano acabaría habiendo medidas realizadas sin fecha y medidas
        # pendientes con ella. Se pone al cerrar y se retira al reabrir.
        if estado == 'R':
            medida.fecha_cierre = medida.fecha_cierre or timezone.localdate()
        else:
            medida.fecha_cierre = None
        medida.save(update_fields=['estado', 'fecha_cierre'])

    # Volver al listado tal como estaba, con su filtro. Un destino que llegue
    # de fuera no se sigue: aceptarlo a ciegas convertiría la aplicación en
    # trampolín hacia otro sitio.
    destino = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse('evaluaciones:medidas')
    return redirect(destino)


def medida_nueva(request, pk):
    """Alta de una medida correctiva derivada de no conformidades (RF-06).

    La dirección cuelga de la evaluación porque la medida nace de ella: por
    eso el formulario no ofrece elegirla, y las no conformidades que presenta
    son las de esa evaluación y ninguna otra.
    """
    evaluacion = get_object_or_404(Evaluacion, pk=pk)

    # Una evaluación conforme no tiene no conformidades que atacar, así que el
    # formulario no tendría ninguna casilla que ofrecer y, siendo el campo
    # obligatorio, no habría forma de enviarlo. La dirección se puede escribir
    # a mano, de modo que el corte va aquí y no solo en la plantilla.
    if not evaluacion.respuestas.filter(resultado='NC').exists():
        return redirect('evaluaciones:evaluacion_detalle', pk=evaluacion.pk)

    if request.method == 'POST':
        form = MedidaForm(request.POST, evaluacion=evaluacion)
        if form.is_valid():
            medida = form.save(commit=False)
            medida.evaluacion = evaluacion
            medida.save()
            # Una relación múltiple solo puede colgarse de una fila que ya
            # existe, así que las no conformidades se guardan después.
            form.save_m2m()
            return redirect('evaluaciones:evaluacion_detalle', pk=evaluacion.pk)
    else:
        form = MedidaForm(evaluacion=evaluacion)

    return render(request, 'evaluaciones/medida_nueva.html', {
        'evaluacion': evaluacion,
        'form': form,
    })


def documento_subir(request, pk):
    """Subida de un documento a la ficha de un equipo (RF-09).

    La dirección cuelga del equipo, igual que el alta de una medida cuelga
    de su evaluación: por eso el formulario no ofrece elegir el equipo.
    """
    equipo = get_object_or_404(Equipo, pk=pk)

    if request.method == 'POST':
        # Los ficheros no viajan en request.POST, sino en request.FILES. Sin
        # ese segundo argumento el formulario daría «este campo es
        # obligatorio» en el fichero por mucho que se hubiera elegido uno.
        form = DocumentoForm(request.POST, request.FILES, equipo=equipo)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.equipo = equipo
            # El equipo tiene que estar puesto antes de guardar: la carpeta
            # de destino se calcula con su identificador.
            documento.save()
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = DocumentoForm(equipo=equipo)

    return render(request, 'evaluaciones/documento_subir.html', {
        'equipo': equipo,
        'form': form,
    })


@login_not_required
def documento_descargar(request, pk):
    """Entrega el fichero de un documento, si quien lo pide puede verlo.

    Es la única puerta a los ficheros subidos: la carpeta media/ no se sirve
    como ficheros sueltos. Hacerlo tendría dos efectos contrarios y ambos
    malos: cualquiera que diera con la ruta abriría también los documentos
    no públicos, y a la vez LoginRequiredMiddleware exigiría sesión para
    todos, impidiendo al trabajador leer el manual, que es justo lo que el
    artículo 5.2 del RD 1215/1997 obliga a permitir. Con una vista propia,
    la regla vive en un solo sitio.

    Se responde 404 y no 403 a propósito: un 403 confirmaría que el
    documento existe a quien no puede verlo.
    """
    documento = get_object_or_404(Documento, pk=pk)

    if not documento.publico and not request.user.is_authenticated:
        raise Http404

    try:
        fichero = documento.fichero.open('rb')
    except FileNotFoundError:
        # La fila puede sobrevivir al fichero: borrar un equipo se lleva sus
        # documentos de la base de datos pero no del disco, y una copia de
        # seguridad restaurada a medias deja el caso contrario.
        raise Http404

    # as_attachment=False para que el móvil abra el PDF en el navegador en
    # vez de descargarlo: en planta interesa verlo, no guardarlo.
    return FileResponse(fichero, as_attachment=False)


def incidencia_nueva(request, pk):
    """Registro de una incidencia sobre un equipo (RF-07).

    Registrarla marca para revisión la evaluación vigente: el dictamen se
    emitió sobre un equipo que ya no está en ese estado.

    Solo la vigente, y no todo el histórico. Una evaluación de marzo describía
    correctamente el equipo en marzo, y el RF-03 exige conservar ese registro
    tal cual. Es la diferencia con el cambio de tipos, donde
    _marcar_desfasadas() sí marca todas: allí ninguna evaluación llegó a
    comprobar los criterios nuevos, de modo que todas quedaron incompletas.

    Registrar la incidencia y marcar la evaluación son una sola cosa: si lo
    segundo fallara, quedaría una incidencia registrada sobre una evaluación
    que sigue diciendo que el equipo está conforme. Por eso van en la misma
    transacción.
    """
    equipo = get_object_or_404(Equipo, pk=pk)

    if request.method == 'POST':
        form = IncidenciaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                incidencia = form.save(commit=False)
                incidencia.equipo = equipo
                # Quién la registra no lo elige el formulario: lo pone la
                # sesión. Un campo editable permitiría firmar en nombre de
                # otro, que es justo lo que la firma tiene que impedir.
                incidencia.autor = request.user
                incidencia.save()

                evaluacion = equipo.ultima_evaluacion
                if evaluacion is not None:
                    evaluacion.en_revision = True
                    evaluacion.motivo_revision = 'I'
                    evaluacion.save(
                        update_fields=['en_revision', 'motivo_revision']
                    )
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = IncidenciaForm()

    return render(request, 'evaluaciones/incidencia_nueva.html', {
        'equipo': equipo,
        'form': form,
        # Un equipo sin evaluar admite incidencias: lo que no hay es
        # evaluación que marcar, y conviene decirlo antes de registrarla.
        'sin_evaluacion': equipo.ultima_evaluacion is None,
    })


def documento_borrar(request, pk):
    """Retira un documento de un equipo.

    La confirmación es una página y no un aviso del navegador: el borrado es
    irreversible y un confirm() de JavaScript deja de existir si el
    JavaScript no se ejecuta. Además, así se puede decir qué se va a borrar.

    El fichero del disco se lo lleva la señal post_delete del modelo.
    """
    documento = get_object_or_404(Documento.objects.select_related('equipo'), pk=pk)
    equipo = documento.equipo

    if request.method == 'POST':
        documento.delete()
        return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)

    return render(request, 'evaluaciones/documento_borrar.html', {
        'documento': documento,
        'equipo': equipo,
    })


def exencion_nueva(request, pk):
    """Declarar que un tipo de documento no procede en un equipo.

    Cuelga del equipo y no de la evaluación a propósito: el motivo describe
    cómo se gestiona ese equipo —el mantenimiento lo lleva un taller externo
    sin registro, la información se imparte en la formación— y no una
    inspección concreta. Declararlo en cada evaluación obligaría a repetir lo
    mismo en cada visita.
    """
    equipo = get_object_or_404(Equipo, pk=pk)

    if request.method == 'POST':
        form = ExencionForm(request.POST, equipo=equipo)
        if form.is_valid():
            exencion = form.save(commit=False)
            exencion.equipo = equipo
            exencion.save()
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = ExencionForm(equipo=equipo)

    return render(request, 'evaluaciones/exencion_nueva.html', {
        'equipo': equipo,
        'form': form,
    })


@require_POST
def exencion_retirar(request, pk):
    """Retirar una exención: el documento vuelve a pedirse.

    Solo acepta POST porque modifica datos. Se borra en vez de marcarse como
    retirada: la exención no es un hecho evaluado que haya que conservar,
    como sí lo son las respuestas, sino una declaración vigente sobre cómo se
    gestiona el equipo hoy.
    """
    exencion = get_object_or_404(ExencionDocumental, pk=pk)
    equipo_pk = exencion.equipo_id
    exencion.delete()
    return redirect('evaluaciones:equipo_detalle', pk=equipo_pk)


@login_not_required
def equipo_publico(request, token):
    """Consulta en campo de un equipo por su código QR (RF-08, 09 y 10).

    Una sola pantalla con dos capas, que es como la describe la tarea T15 de
    la planificación:

    - Sin sesión (RF-09): datos básicos del equipo y los documentos marcados
      como públicos. El artículo 5.2 del RD 1215/1997 obliga a poner esa
      documentación a disposición de los trabajadores, y un trabajador no es
      un usuario del sistema: la gestión de operarios está fuera de alcance
      por el RGPD, así que no hay ninguna cuenta que pudiera pedirle.
    - Con sesión (RF-10): además, la ficha completa en modo solo lectura.

    Quien escanea no sabe en qué capa está ni le cambia el gesto, y no se
    registra quién consulta.
    """
    equipo = get_object_or_404(Equipo, token=token)

    documentos = equipo.documentos.all()
    if not request.user.is_authenticated:
        documentos = documentos.filter(publico=True)

    contexto = {'equipo': equipo, 'documentos': documentos}

    # El histórico solo se arma para quien puede verlo: construirlo y luego
    # esconderlo en la plantilla dejaría los datos en el contexto de una
    # página pública.
    if request.user.is_authenticated:
        contexto['evaluaciones'] = (
            equipo.evaluaciones
            .prefetch_related('respuestas', 'medidas')
        )

    return render(request, 'evaluaciones/equipo_publico.html', contexto)


def equipo_qr(request, pk):
    """Etiqueta imprimible con el código QR de un equipo (RF-08).

    El QR se dibuja como SVG dentro de la propia página: es vectorial, así
    que se imprime nítido al tamaño que haga falta, y no deja ficheros de
    imagen que guardar, servir ni limpiar.

    La dirección se construye con build_absolute_uri y no se escribe a mano
    porque tiene que funcionar escaneada desde un móvil: una dirección
    relativa no lleva a ninguna parte fuera del navegador, y localhost
    apuntaría al propio teléfono.
    """
    equipo = get_object_or_404(Equipo, pk=pk)
    destino = request.build_absolute_uri(
        reverse('evaluaciones:equipo_publico', args=[equipo.token])
    )
    # Corrección de errores media: recupera hasta el 15 % del código. En una
    # etiqueta pegada a una máquina, que acaba con polvo, grasa o un roce, el
    # mínimo se queda corto.
    qr = segno.make(destino, error='m')
    return render(request, 'evaluaciones/equipo_qr.html', {
        'equipo': equipo,
        'destino': destino,
        'qr_svg': qr.svg_inline(scale=6, border=2),
    })
