from django.db import models
from django.utils import timezone


class Linea(models.Model):
    nombre = models.CharField(max_length=200)
    ubicacion = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.nombre


class Equipo(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    linea = models.ForeignKey(
        Linea,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='equipos',
    )
    nombre = models.CharField(max_length=200)
    marca_modelo = models.CharField(max_length=200, blank=True)
    num_serie = models.CharField(max_length=100, blank=True)
    anio = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.nombre


class GrupoCriterio(models.Model):
    nombre = models.CharField(max_length=200)
    fuente_normativa = models.CharField(max_length=200, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden']

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
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name='evaluaciones',
    )
    fecha = models.DateTimeField(default=timezone.now)
    en_revision = models.BooleanField(default=False)

    class Meta:
        ordering = ['-fecha']

    @property
    def dictamen(self):
        if any(r.resultado == 'NC' for r in self.respuestas.all()):
            return 'No conforme'
        return 'Conforme'

    def __str__(self):
        return f"{self.equipo} — {self.fecha:%Y-%m-%d}"


class Respuesta(models.Model):
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
