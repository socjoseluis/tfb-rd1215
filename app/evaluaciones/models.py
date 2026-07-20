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
