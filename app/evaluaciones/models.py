import uuid

from django.conf import settings
from django.db import models
from django.dispatch import receiver
from django.utils import timezone

# Tipos de documento que puede tener un equipo. Salen del RD 1215/1997 el
# manual y la información de utilización (art. 5.2) y el registro de
# comprobación (art. 4.4). El registro de mantenimiento NO lo exige la norma
# —el art. 3.5 obliga a hacer el mantenimiento, no a documentarlo— y se
# incluye porque es lo único que acreditaría ese cumplimiento.
#
# Vive suelto y no dentro de Documento porque Criterio también lo usa para
# decir qué documento lo acredita, y Criterio se declara antes en el fichero.
TIPOS_DOCUMENTO = [
    ('MF', 'Manual o instrucciones del fabricante'),
    ('IU', 'Información de utilización segura'),
    ('CE', 'Declaración CE de conformidad'),
    # El marcado y la declaración no son lo mismo: el marcado es la placa
    # atornillada a la máquina, que se comprueba mirando en planta, y la
    # declaración es el papel que emite el fabricante. Van separados para no
    # confundirlos. Este tipo no lo reclama ningún criterio: exigir una
    # fotografía a cada equipo no sale de ninguna norma, es evidencia de
    # apoyo que el técnico adjunta si le conviene.
    ('MC', 'Fotografía del marcado CE o placa de características'),
    ('RC', 'Registro de comprobación'),
    ('RM', 'Registro de mantenimiento'),
    ('OT', 'Otro'),
]

# Tipos que se pueden declarar «no procede» para un equipo concreto. La lista
# no es una preferencia de diseño, sale de la norma:
#
# - `RM` no lo exige el RD 1215/1997: el art. 3.5 obliga a hacer el
#   mantenimiento según las instrucciones del fabricante, no a documentarlo.
# - `RC` solo alcanza a los equipos del art. 4 —aquellos cuya seguridad
#   dependa de las condiciones de instalación, o sometidos a deterioro—, no a
#   todos: una llave dinamométrica no necesita comprobaciones periódicas.
# - `IU` se sostiene en que el art. 5.2 pide la información «preferentemente
#   por escrito»: preferentemente, no obligatoriamente. Eximirla significa que
#   la información se da por otra vía, típicamente la formación.
#
# Quedan FUERA `MF` y `CE`, y es deliberado. La documentación del fabricante
# está a disposición de los trabajadores por el art. 5.2: si no está, eso es
# una no conformidad y hay que responderla como tal. Y una máquina anterior al
# marcado CE no se resuelve eximiendo el documento, sino respondiendo «No
# aplica» al criterio, que es lo que significa. Permitir eximirlos convertiría
# esto en un botón para hacer desaparecer incumplimientos.
TIPOS_EXIMIBLES = ['IU', 'RC', 'RM', 'OT']


class Linea(models.Model):
    """Línea de producción que agrupa equipos (RF-05)."""

    nombre = models.CharField(max_length=200)
    ubicacion = models.CharField('Ubicación', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Línea'
        verbose_name_plural = 'Líneas'

    def __str__(self):
        return self.nombre


class TipoEquipo(models.Model):
    """Tipo de equipo a efectos del Anexo I.2 del RD 1215/1997.

    Un equipo puede ser de varios tipos a la vez: una carretilla elevadora es
    equipo móvil (Anexo I.2.1) y equipo de elevación de cargas (Anexo I.2.2).
    """

    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Tipo de equipo'
        verbose_name_plural = 'Tipos de equipo'

    def __str__(self):
        return self.nombre


class Equipo(models.Model):
    codigo = models.CharField('Código', max_length=50, unique=True)
    # Lo que lleva escrito dentro el código QR pegado a la máquina (RF-08).
    # No se usa el código del equipo por dos razones: la página a la que
    # lleva es anónima, y con un código correlativo cualquiera podría
    # recorrer el inventario desde fuera sin haber visto ninguna máquina;
    # además el código se puede corregir al editar el equipo, y entonces
    # todas las etiquetas impresas dejarían de valer. Un identificador
    # aleatorio no estorba a quien está delante del equipo, que escanea, y
    # sobrevive a los cambios de datos.
    token = models.UUIDField(
        'Identificador del QR',
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    linea = models.ForeignKey(
        Linea,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='equipos',
        verbose_name='Línea',
    )
    nombre = models.CharField(max_length=200)
    marca_modelo = models.CharField('Marca / modelo', max_length=200, blank=True)
    num_serie = models.CharField('Nº de serie', max_length=100, blank=True)
    anio = models.PositiveIntegerField('Año', null=True, blank=True)
    tipos = models.ManyToManyField(
        TipoEquipo,
        blank=True,
        related_name='equipos',
        verbose_name='Tipos de equipo',
        help_text=(
            'Marque todos los que apliquen; un mismo equipo puede ser de '
            'varios tipos. Si no es de ninguno, déjelo sin marcar.'
        ),
    )
    tipos_confirmados = models.BooleanField(
        'Tipos confirmados',
        default=False,
        help_text=(
            'Alguien ha revisado a qué tipos del Anexo I.2 pertenece el '
            'equipo. Distingue un equipo que no es de ninguno de otro cuyo '
            'tipo todavía no se ha comprobado.'
        ),
    )

    def __str__(self):
        return self.nombre

    @property
    def ultima_evaluacion(self):
        """La evaluación más reciente, o None si nunca se ha evaluado.

        Se recorre la lista completa en lugar de pedir first() para
        aprovechar el prefetch de los listados: first() añadiría un LIMIT y
        volvería a consultar la base de datos por cada equipo.
        """
        evaluaciones = list(self.evaluaciones.all())
        return evaluaciones[0] if evaluaciones else None

    @property
    def tipos_eximidos(self):
        """Tipos de documento declarados «no procede» para este equipo."""
        return {exencion.tipo for exencion in self.exenciones.all()}

    @property
    def evidencias_pendientes(self):
        """Documentos que le faltan al equipo según su evaluación vigente.

        Solo mira la última evaluación, no el histórico: las anteriores son
        el registro de lo que se comprobó entonces y no describen el estado
        de hoy. Marcar una evaluación vieja cuando ya hay otra más reciente
        sería avisar de un problema que puede estar resuelto.
        """
        evaluacion = self.ultima_evaluacion
        return evaluacion.evidencias_pendientes if evaluacion else []

    def grupos_aplicables(self):
        """Grupos de criterios que corresponden a este equipo (RF-04).

        Devuelve los grupos sin ningún tipo asignado, que son los generales
        del Anexo I.1 y aplican a todo equipo, más los propios de los tipos
        de este equipo (Anexo I.2). Una carretilla elevadora, que es móvil y
        de elevación de cargas, recoge los de ambos.

        El distinct() es necesario: al cruzar una relación de muchos a
        muchos con un OR, un mismo grupo puede aparecer repetido, una vez
        por cada tipo que empareje.
        """
        return GrupoCriterio.objects.filter(
            models.Q(tipos_aplicables__isnull=True)
            | models.Q(tipos_aplicables__in=self.tipos.all())
        ).distinct()


class GrupoCriterio(models.Model):
    """Bloque temático de criterios, con su origen en la norma.

    Los criterios se guardan como datos y no codificados en la aplicación:
    así, ampliar los tipos de equipo o revisar la norma se resuelve
    editando registros y no tocando el programa. Un grupo sin ningún tipo
    asignado aplica a todos los equipos.
    """

    nombre = models.CharField(max_length=200)
    fuente_normativa = models.CharField(max_length=200, blank=True)
    orden = models.PositiveIntegerField(default=0)
    tipos_aplicables = models.ManyToManyField(
        TipoEquipo,
        blank=True,
        related_name='grupos',
        help_text=(
            'Tipos de equipo a los que aplica este grupo. '
            'Sin ninguno, aplica a todos los equipos.'
        ),
    )

    class Meta:
        ordering = ['orden']
        verbose_name = 'Grupo de criterios'
        verbose_name_plural = 'Grupos de criterios'

    def __str__(self):
        return self.nombre


class Criterio(models.Model):
    grupo = models.ForeignKey(
        GrupoCriterio,
        on_delete=models.PROTECT,
        related_name='criterios',
    )
    enunciado = models.CharField(max_length=500)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['grupo', 'orden']

    @property
    def tipos_esperados(self):
        """Tipos de documento que acreditan este criterio, si alguno.

        Son varios y no uno porque un mismo criterio puede pedir más de una
        cosa: el del marcado CE se acredita con la declaración del fabricante
        y con la fotografía de la placa atornillada a la máquina, que son
        documentos distintos de hechos distintos.
        """
        return [
            evidencia.tipo for evidencia in self.evidencias_esperadas.all()
        ]

    def __str__(self):
        return self.enunciado[:75]


class EvidenciaEsperada(models.Model):
    """Documento que acredita un criterio.

    Es una tabla y no un campo del criterio porque la relación es de varios a
    varios: un criterio puede pedir más de un documento —el del marcado CE
    pide la declaración del fabricante y la fotografía de la placa— y un
    mismo tipo de documento puede acreditar varios criterios.

    Responder «Conforme» sin tener el documento no invalida la evaluación: el
    técnico ha podido comprobarlo en planta. Solo se avisa, para que nadie
    lea «Conforme» y cierre la pantalla sin advertir que la evidencia no está
    en el sistema.
    """

    criterio = models.ForeignKey(
        Criterio,
        on_delete=models.CASCADE,
        related_name='evidencias_esperadas',
    )
    tipo = models.CharField(
        'Tipo de documento',
        max_length=2,
        choices=TIPOS_DOCUMENTO,
    )

    class Meta:
        verbose_name = 'Evidencia esperada'
        verbose_name_plural = 'Evidencias esperadas'
        ordering = ['criterio', 'tipo']
        constraints = [
            models.UniqueConstraint(
                fields=['criterio', 'tipo'],
                name='unique_evidencia_por_tipo_en_criterio',
            ),
        ]

    def __str__(self):
        return f"{self.criterio} ← {self.get_tipo_display()}"


class Evaluacion(models.Model):
    """Evaluación de un equipo en una fecha concreta (RF-03).

    Cada evaluación es un registro independiente: evaluar de nuevo un
    equipo añade una fila, nunca modifica las anteriores, de modo que el
    histórico se conserva íntegro.
    """

    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name='evaluaciones',
    )
    MOTIVO_REVISION_CHOICES = [
        ('T', 'Desfasada'),
        ('I', 'Con incidencia'),
    ]

    fecha = models.DateTimeField(default=timezone.now)
    en_revision = models.BooleanField('En revisión', default=False)
    # Dos causas distintas llevan a revisar una evaluación y no significan lo
    # mismo: que se añadan tipos al equipo la deja incompleta, porque hay
    # criterios que nunca se comprobaron; que se registre una incidencia la
    # deja en duda, porque la máquina ha cambiado de estado. Sin este campo
    # ambas se mostrarían como «Desfasada», que en el segundo caso sería
    # falso: no hay nada desfasado, se ha roto el equipo.
    motivo_revision = models.CharField(
        'Motivo de la revisión',
        max_length=1,
        choices=MOTIVO_REVISION_CHOICES,
        blank=True,
    )

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Evaluación'
        verbose_name_plural = 'Evaluaciones'

    @property
    def dictamen(self):
        """Resultado global de la evaluación (RF-04).

        El dictamen es binario porque el RD 1215/1997 fija disposiciones
        mínimas: se cumplen o no se cumplen. Basta una no conformidad para
        que el conjunto lo sea. Los matices que el binario no captura se
        recogen en las indicaciones de cada respuesta.
        """
        if any(r.resultado == 'NC' for r in self.respuestas.all()):
            return 'No conforme'
        return 'Conforme'

    @property
    def no_conformidades_sin_medida(self):
        """No conformidades que todavía no ataca ninguna medida (RF-06).

        Una medida descartada no cubre nada: se propuso y se desestimó, de
        modo que la no conformidad vuelve a quedar desatendida. Las
        realizadas sí cuentan, porque el arreglo se hizo.

        Se recorren las listas ya traídas en lugar de filtrar, para no
        lanzar consultas por evaluación en los listados; es el mismo motivo
        que en Equipo.ultima_evaluacion.
        """
        return [
            respuesta for respuesta in self.respuestas.all()
            if respuesta.resultado == 'NC'
            and not any(m.estado != 'D' for m in respuesta.medidas.all())
        ]

    @property
    def evidencias_pendientes(self):
        """Criterios dados por conformes cuyo documento no está subido.

        No es una no conformidad y no toca el dictamen: el técnico ha podido
        comprobar el marcado CE con la placa delante y responder «Conforme»
        con toda la razón. Lo que evita es la falsa sensación de conformidad
        de quien lee el dictamen y cierra la pantalla sin advertir que la
        evidencia documental no está en el sistema.

        Solo mira las respuestas «Conforme»: un «No aplica» significa que la
        disposición no rige para este equipo —una máquina anterior al marcado
        CE no puede tener declaración— y un «No conforme» ya está señalado.

        Devuelve pares (criterio, nombre del documento que falta).
        """
        # Un tipo eximido cuenta como resuelto: el técnico ha declarado por
        # escrito, y con motivo, que ese documento no procede en este equipo.
        # La declaración no desaparece, queda a la vista en la ficha.
        cubiertos = {
            documento.tipo for documento in self.equipo.documentos.all()
        } | self.equipo.tipos_eximidos
        nombres = dict(TIPOS_DOCUMENTO)
        return [
            (respuesta.criterio, nombres[tipo])
            for respuesta in self.respuestas.all()
            if respuesta.resultado == 'C'
            for tipo in respuesta.criterio.tipos_esperados
            if tipo not in cubiertos
        ]

    @property
    def fecha_prevista_limite(self):
        """La más lejana de las fechas previstas de sus medidas abiertas.

        Es la fecha en la que, si todo se cumple, el equipo dejaría de tener
        no conformidades sin atender. Devuelve None si ninguna medida
        abierta tiene fecha, porque la fecha prevista es opcional.
        """
        fechas = [
            medida.fecha_prevista for medida in self.medidas.all()
            if medida.fecha_prevista and medida.estado in ('P', 'EC')
        ]
        return max(fechas) if fechas else None

    def __str__(self):
        return f"{self.equipo} — {self.fecha:%Y-%m-%d}"


class Respuesta(models.Model):
    """Resultado de un criterio dentro de una evaluación.

    El «no aplica» no es un hueco de datos ni una comodidad: la propia
    norma prevé que sus disposiciones solo rigen si el equipo da lugar al
    riesgo para el que se especifica la medida (Anexo I, observación
    preliminar).
    """

    RESULTADO_CHOICES = [
        ('C', 'Conforme'),
        ('NC', 'No conforme'),
        ('NA', 'No aplica'),
    ]

    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name='respuestas',
    )
    criterio = models.ForeignKey(
        Criterio,
        on_delete=models.PROTECT,
        related_name='respuestas',
    )
    resultado = models.CharField(max_length=2, choices=RESULTADO_CHOICES)
    indicaciones = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['evaluacion', 'criterio'],
                name='unique_respuesta_por_criterio_en_evaluacion',
            ),
        ]

    def __str__(self):
        return f"{self.criterio} → {self.get_resultado_display()}"


class Incidencia(models.Model):
    """Suceso que pone en duda el estado de un equipo (RF-07).

    Cuelga del equipo y no de una evaluación porque le ocurre a la máquina:
    un atrapamiento, un resguardo que deja de enclavar, una fuga. Registrarla
    marca para revisión la evaluación vigente, que es lo que el requisito
    pide, porque el dictamen se emitió sobre un equipo que ya no está en ese
    estado.

    Solo marca la vigente, no el histórico: una evaluación de marzo describía
    correctamente el equipo en marzo. Es la diferencia con el cambio de tipos,
    que sí invalida todas las anteriores, porque ninguna llegó a comprobar los
    criterios nuevos.

    No guarda estado —abierta, cerrada— a propósito. El seguimiento de lo que
    haya que arreglar ya existe: se reevalúa el equipo y las no conformidades
    que salgan generan medidas correctivas con su propio ciclo (RF-06). Darle
    aquí un ciclo de vida propio duplicaría ese seguimiento.

    Sí guarda quién la registra, a diferencia del resto del prototipo, y la
    línea que lo justifica es esta: una incidencia **invalida un registro de
    conformidad**, y lo que tumba un dictamen lleva firma. Subir un documento
    o proponer una medida no invalidan nada. Sin autor, cualquiera con cuenta
    podría marcar para revisión la evaluación de cualquier equipo sin que
    nadie pudiera saber quién fue.

    No choca con la exclusión de la gestión de personas: el autor es un
    usuario de la aplicación, dado de alta con su cuenta, no un operario. Es
    dato de auditoría, no de dominio.
    """

    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name='incidencias',
    )
    # SET_NULL y no CASCADE: si se da de baja a un técnico, sus incidencias
    # tienen que sobrevivir. Borrarlas dejaría evaluaciones marcadas para
    # revisión sin nada que explique por qué. Que la autoría se pierda al
    # borrar la cuenta es además coherente con la minimización de datos.
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incidencias',
        verbose_name='Registrada por',
        editable=False,
    )
    descripcion = models.TextField('Descripción')
    fecha = models.DateTimeField('Fecha', default=timezone.now)

    class Meta:
        ordering = ['-fecha']
        verbose_name_plural = 'Incidencias'

    def __str__(self):
        return f"{self.equipo} — {self.fecha:%Y-%m-%d}"


class Medida(models.Model):
    """Medida correctiva derivada de no conformidades (RF-06).

    Nace de una evaluación concreta y ataca una o varias no conformidades de
    esa misma evaluación. Cerrarla no cambia el dictamen: el RF-03 exige que
    el histórico no se sobrescriba, así que la conformidad se recupera
    evaluando de nuevo y la medida cerrada queda como rastro de por qué
    cambió.
    """

    ESTADO_CHOICES = [
        ('P', 'Pendiente'),
        ('EC', 'En curso'),
        ('R', 'Realizada'),
        ('D', 'Descartada'),
    ]

    # La clave ajena marca la frontera del problema y la relación múltiple
    # permite que un mismo arreglo cierre varias no conformidades. Sin la
    # primera, una medida podría enganchar no conformidades de equipos
    # distintos y quedar a la vez realizada para uno y pendiente para otro;
    # además, una relación múltiple admite quedarse vacía, mientras que la
    # clave ajena garantiza que ninguna medida cuelgue de nada.
    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name='medidas',
    )
    # Que sean no conformidades de esta misma evaluación no lo impone el
    # modelo: Django no puede restringir una relación múltiple en función de
    # otro campo de la fila. Lo impone el formulario, limitando las opciones.
    no_conformidades = models.ManyToManyField(
        Respuesta,
        related_name='medidas',
        verbose_name='No conformidades',
    )
    descripcion = models.TextField('Descripción')
    fecha_alta = models.DateTimeField('Fecha de alta', default=timezone.now)
    fecha_prevista = models.DateField('Fecha prevista', null=True, blank=True)
    estado = models.CharField(max_length=2, choices=ESTADO_CHOICES, default='P')
    # «Descartada» existe para la medida que se propone y luego se desestima,
    # por ejemplo porque se sustituye el equipo: borrarla perdería el rastro
    # de lo que se decidió.
    fecha_cierre = models.DateField('Fecha de cierre', null=True, blank=True)

    class Meta:
        ordering = ['-fecha_alta']

    def __str__(self):
        return f"{self.get_estado_display()} — {self.descripcion[:60]}"


def ruta_documento(instance, filename):
    """Carpeta de destino del fichero subido: una por equipo.

    La carpeta lleva el identificador del equipo y no su código porque el
    código se puede corregir desde el formulario de edición: renombrar un
    equipo dejaría los ficheros en una carpeta con el nombre antiguo.
    """
    return f'documentos/{instance.equipo_id}/{filename}'


class Documento(models.Model):
    """Documentación asociada a un equipo (RF-09).

    El artículo 5.2 del RD 1215/1997 obliga a poner cierta documentación a
    disposición de los trabajadores, y el artículo 4.4 obliga a documentar
    los resultados de las comprobaciones y conservarlos durante toda la vida
    útil del equipo. Estos son los ficheros que la consulta por QR ofrece
    sin pedir autenticación, porque exigir contraseña para leer el manual de
    la máquina que uno maneja incumpliría esa obligación.
    """

    TIPO_CHOICES = TIPOS_DOCUMENTO

    # Los documentos no significan nada sin su equipo, igual que las
    # evaluaciones: por eso CASCADE y no PROTECT, que es lo que usa Linea.
    # Nota: al borrar la fila, Django NO borra el fichero del disco (dejó de
    # hacerlo en la versión 1.3 para no destruir ficheros por accidente), de
    # modo que quedan huérfanos en media/.
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name='documentos',
    )
    tipo = models.CharField(max_length=2, choices=TIPO_CHOICES)
    # Los cuatro primeros tipos son los que nombra la norma; este campo evita
    # que la lista sea una jaula. Un documento propio del servicio de
    # prevención se presenta con el nombre que le dé el técnico y no como un
    # «Otro» que en la consulta en campo no informaría de nada. Que sea
    # obligatorio al elegir «Otro» lo impone el formulario: el modelo no
    # puede condicionar un campo al valor de otro.
    tipo_otro = models.CharField(
        'Especifique el tipo',
        max_length=100,
        blank=True,
    )
    # Opcional: en los cuatro tipos de la norma el título casi siempre
    # repetiría el nombre del tipo. Si se deja vacío, save() lo rellena.
    titulo = models.CharField('Título', max_length=200, blank=True)
    fichero = models.FileField('Fichero', upload_to=ruta_documento)
    # Nace cerrado y se abre a propósito. La visibilidad es de cada documento
    # y no del tipo: el artículo 5.2 pone la documentación del fabricante a
    # disposición de los trabajadores, mientras que el artículo 4.4 pone los
    # registros de comprobación a disposición de la autoridad laboral. Mismo
    # equipo, dos obligaciones documentales, dos destinatarios distintos.
    publico = models.BooleanField(
        'Visible sin autenticar',
        default=False,
        help_text=(
            'Marque los documentos que deben estar a disposición de los '
            'trabajadores: cualquiera que escanee el código QR del equipo '
            'podrá abrirlos sin identificarse.'
        ),
    )
    fecha_subida = models.DateTimeField('Fecha de subida', default=timezone.now)

    class Meta:
        # Primero los que puede ver el trabajador. Ordenar solo por tipo
        # dejaba el orden al azar del código interno de cada opción, que es
        # alfabético y no significa nada.
        ordering = ['-publico', 'tipo', '-fecha_subida']

    def save(self, *args, **kwargs):
        """Un documento sin título se queda con el nombre de su tipo.

        Va aquí y no en el formulario para que valga también cuando el
        documento se crea desde el código o desde el admin.
        """
        if not self.titulo.strip():
            self.titulo = self.tipo_mostrado()
        return super().save(*args, **kwargs)

    def tipo_mostrado(self):
        """Cómo se nombra el tipo en pantalla.

        Para los tipos de la norma es su nombre; para «Otro», el que haya
        escrito el técnico.
        """
        if self.tipo == 'OT' and self.tipo_otro:
            return self.tipo_otro
        return self.get_tipo_display()

    def __str__(self):
        return f"{self.tipo_mostrado()} — {self.titulo}"


@receiver(models.signals.post_delete, sender=Documento)
def borrar_fichero_del_documento(sender, instance, **kwargs):
    """Al borrar un documento, borra también su fichero del disco.

    Django dejó de hacerlo en la versión 1.3 para no destruir ficheros por
    accidente, y con razón cuando varias filas pueden apuntar al mismo. Aquí
    no ocurre: cada subida guarda su propio fichero, y el almacenamiento
    añade un sufijo si el nombre ya existe. Sin esto, cada borrado —y cada
    equipo borrado, que arrastra sus documentos— dejaría basura invisible en
    media/.

    save=False evita que el borrado del fichero intente guardar una fila que
    ya no existe.
    """
    if instance.fichero:
        instance.fichero.delete(save=False)


class ExencionDocumental(models.Model):
    """Declaración de que un tipo de documento no procede en un equipo.

    Es la tercera salida al aviso de evidencia documental, junto a subir el
    fichero y a responder «No aplica» al criterio, y cada una significa una
    cosa distinta:

    - Subir el documento: la evidencia existe y entra en el sistema.
    - «No aplica» en el criterio: la disposición no rige para este equipo.
    - Esta exención: la disposición rige y se cumple, pero la norma no exige
      documentarlo, o no de esta forma.

    Por eso solo alcanza a TIPOS_EXIMIBLES y exige un motivo escrito: sin él
    sería un botón para silenciar avisos, y con él es una declaración del
    técnico que queda a la vista en la ficha y se puede auditar.
    """

    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name='exenciones',
    )
    tipo = models.CharField(
        'Tipo de documento',
        max_length=2,
        choices=[(c, n) for c, n in TIPOS_DOCUMENTO if c in TIPOS_EXIMIBLES],
    )
    motivo = models.TextField(
        'Motivo',
        help_text=(
            'Por qué no procede en este equipo. Queda a la vista en la ficha, '
            'así que escríbalo como lo defendería ante una inspección.'
        ),
    )
    fecha = models.DateTimeField('Fecha', default=timezone.now)

    class Meta:
        verbose_name = 'Exención documental'
        verbose_name_plural = 'Exenciones documentales'
        ordering = ['tipo']
        constraints = [
            # Un mismo tipo no se exime dos veces en el mismo equipo: la
            # segunda declaración solo podría contradecir a la primera.
            models.UniqueConstraint(
                fields=['equipo', 'tipo'],
                name='unique_exencion_por_tipo_en_equipo',
            ),
        ]

    def __str__(self):
        return f"{self.equipo} — {self.get_tipo_display()}: no procede"
