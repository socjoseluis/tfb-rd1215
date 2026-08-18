from django.db import models
from django.utils import timezone


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

    def __str__(self):
        return self.enunciado[:75]


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
    fecha = models.DateTimeField(default=timezone.now)
    en_revision = models.BooleanField('En revisión', default=False)

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
