from django import forms
from django.db.models import Prefetch
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import EquipoForm, EquipoTiposForm
from .importador import importar_equipos
from .models import Criterio, Equipo, Evaluacion, Linea, Respuesta


def inicio(request):
    """Portada: los equipos organizados por línea de producción (RF-05).

    Es también el punto de entrada de la aplicación: hasta ahora solo se
    podía navegar escribiendo la dirección de cada ficha.
    """
    equipos = Equipo.objects.prefetch_related('tipos', 'evaluaciones__respuestas')
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
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = EquipoForm()
    return render(request, 'evaluaciones/equipo_alta.html', {'form': form})


def equipo_detalle(request, pk):
    """Ficha de un equipo.

    Es la base de la consulta en modo solo lectura (RF-10), pendiente
    todavía del control de acceso por autenticación: hoy la ficha es
    pública.
    """
    equipo = get_object_or_404(Equipo, pk=pk)
    # El dictamen recorre las respuestas de cada evaluación: sin prefetch
    # sería una consulta por evaluación listada.
    evaluaciones = equipo.evaluaciones.prefetch_related('respuestas')
    return render(request, 'evaluaciones/equipo_detalle.html', {
        'equipo': equipo,
        'evaluaciones': evaluaciones,
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
            # Añadir un tipo hace aplicables criterios del Anexo I.2 que las
            # evaluaciones anteriores nunca llegaron a comprobar: quedan
            # incompletas y se marcan para revisión, el mismo mecanismo que
            # RF-07 usa al registrar una incidencia. Quitar un tipo no las
            # invalida, solo deja respuestas que ya no aplican.
            tipos_despues = set(equipo.tipos.values_list('pk', flat=True))
            if tipos_despues - tipos_antes:
                equipo.evaluaciones.update(en_revision=True)
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

    return render(request, 'evaluaciones/evaluacion_nueva.html', {
        'equipo': equipo,
        'formset': formset,
        'filas': zip(formset, criterios),
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
    return render(request, 'evaluaciones/evaluacion_detalle.html', {
        'evaluacion': evaluacion,
        'respuestas': respuestas,
    })
