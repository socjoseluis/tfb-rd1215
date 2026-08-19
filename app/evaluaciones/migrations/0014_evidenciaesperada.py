"""Un criterio pasa a esperar varios documentos, no uno.

El criterio del marcado CE se acredita con dos cosas distintas: la declaración
de conformidad que emite el fabricante y la fotografía de la placa atornillada
a la máquina. Con un solo campo había que elegir una de las dos.

Escrita a mano para conservar el mapeo que ya estaba cargado: primero la tabla
nueva, después se copia a ella lo que había en el campo viejo, y solo entonces
se retira el campo.
"""
from django.db import migrations, models
import django.db.models.deletion


def copiar_mapeo(apps, schema_editor):
    Criterio = apps.get_model('evaluaciones', 'Criterio')
    EvidenciaEsperada = apps.get_model('evaluaciones', 'EvidenciaEsperada')
    for criterio in Criterio.objects.exclude(tipo_documento=''):
        EvidenciaEsperada.objects.create(
            criterio=criterio, tipo=criterio.tipo_documento,
        )


def devolver_mapeo(apps, schema_editor):
    """Marcha atrás: solo puede devolver el primero de cada criterio.

    Es la pérdida inevitable de volver de varios a uno, y por eso existe la
    tabla.
    """
    Criterio = apps.get_model('evaluaciones', 'Criterio')
    EvidenciaEsperada = apps.get_model('evaluaciones', 'EvidenciaEsperada')
    for evidencia in EvidenciaEsperada.objects.order_by('criterio', 'tipo'):
        Criterio.objects.filter(
            pk=evidencia.criterio_id, tipo_documento='',
        ).update(tipo_documento=evidencia.tipo)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluaciones', '0013_alter_criterio_tipo_documento_alter_documento_tipo'),
    ]

    operations = [
        migrations.CreateModel(
            name='EvidenciaEsperada',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('tipo', models.CharField(
                    choices=[
                        ('MF', 'Manual o instrucciones del fabricante'),
                        ('IU', 'Información de utilización segura'),
                        ('CE', 'Declaración CE de conformidad'),
                        ('MC', 'Fotografía del marcado CE o placa de características'),
                        ('RC', 'Registro de comprobación'),
                        ('RM', 'Registro de mantenimiento'),
                        ('OT', 'Otro'),
                    ],
                    max_length=2, verbose_name='Tipo de documento',
                )),
                ('criterio', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='evidencias_esperadas',
                    to='evaluaciones.criterio',
                )),
            ],
            options={
                'verbose_name': 'Evidencia esperada',
                'verbose_name_plural': 'Evidencias esperadas',
                'ordering': ['criterio', 'tipo'],
            },
        ),
        migrations.AddConstraint(
            model_name='evidenciaesperada',
            constraint=models.UniqueConstraint(
                fields=('criterio', 'tipo'),
                name='unique_evidencia_por_tipo_en_criterio',
            ),
        ),
        migrations.RunPython(copiar_mapeo, devolver_mapeo),
        migrations.RemoveField(
            model_name='criterio',
            name='tipo_documento',
        ),
    ]
