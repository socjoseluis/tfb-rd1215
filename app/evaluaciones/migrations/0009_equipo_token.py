"""Identificador aleatorio de cada equipo para el código QR (RF-08).

Escrita a mano en tres pasos y no generada de una vez a propósito. Un campo
único con valor por defecto se añade calculando ese valor UNA sola vez, así
que los nueve equipos que ya existen recibirían todos el mismo identificador
y la restricción de unicidad reventaría al aplicarla. Por eso: primero la
columna admitiendo vacío, después un identificador distinto para cada fila, y
solo entonces la restricción.
"""
import uuid

from django.db import migrations, models


def rellenar_tokens(apps, schema_editor):
    Equipo = apps.get_model('evaluaciones', 'Equipo')
    for equipo in Equipo.objects.all():
        equipo.token = uuid.uuid4()
        equipo.save(update_fields=['token'])


def vaciar_tokens(apps, schema_editor):
    """Marcha atrás de la anterior.

    Los identificadores no se pueden recuperar, pero el paso inverso tiene
    que existir para que la migración se pueda deshacer.
    """
    Equipo = apps.get_model('evaluaciones', 'Equipo')
    Equipo.objects.update(token=None)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluaciones', '0008_alter_documento_options_alter_documento_titulo'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipo',
            name='token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                null=True,
                verbose_name='Identificador del QR',
            ),
        ),
        migrations.RunPython(rellenar_tokens, vaciar_tokens),
        migrations.AlterField(
            model_name='equipo',
            name='token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='Identificador del QR',
            ),
        ),
    ]
