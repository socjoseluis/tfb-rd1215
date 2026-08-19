import os
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ExencionForm
from .models import (
    Criterio, Documento, Equipo, Evaluacion, EvidenciaEsperada,
    ExencionDocumental, GrupoCriterio, Respuesta,
)

TMP = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP)
class HumoDocumentos(TestCase):
    def setUp(self):
        self.equipo = Equipo.objects.create(codigo='PR-014', nombre='Prensa')
        self.publico = Documento.objects.create(
            equipo=self.equipo, tipo='MF', titulo='Manual',
            fichero=SimpleUploadedFile('manual.pdf', b'%PDF-1.4 falso'),
            publico=True,
        )
        self.privado = Documento.objects.create(
            equipo=self.equipo, tipo='RC', titulo='Registro',
            fichero=SimpleUploadedFile('registro.pdf', b'%PDF-1.4 falso'),
            publico=False,
        )

    def url(self, doc):
        return reverse('evaluaciones:documento_descargar', args=[doc.pk])

    def test_anonimo_abre_el_publico(self):
        self.assertEqual(self.client.get(self.url(self.publico)).status_code, 200)

    def test_anonimo_no_abre_el_privado(self):
        self.assertEqual(self.client.get(self.url(self.privado)).status_code, 404)

    def test_con_sesion_abre_los_dos(self):
        User.objects.create_user('tecnico', password='x')
        self.client.login(username='tecnico', password='x')
        self.assertEqual(self.client.get(self.url(self.publico)).status_code, 200)
        self.assertEqual(self.client.get(self.url(self.privado)).status_code, 200)

    def test_la_ficha_sigue_exigiendo_sesion(self):
        respuesta = self.client.get(
            reverse('evaluaciones:equipo_detalle', args=[self.equipo.pk])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/cuentas/entrar/', respuesta['Location'])

    def test_titulo_vacio_toma_el_nombre_del_tipo(self):
        documento = Documento.objects.create(
            equipo=self.equipo, tipo='CE', titulo='',
            fichero=SimpleUploadedFile('ce.pdf', b'%PDF-1.4 falso'),
        )
        self.assertEqual(documento.titulo, 'Declaración CE de conformidad')

    def test_titulo_vacio_en_otro_toma_el_tipo_escrito(self):
        documento = Documento.objects.create(
            equipo=self.equipo, tipo='OT', tipo_otro='Permiso de trabajo',
            titulo='', fichero=SimpleUploadedFile('pt.pdf', b'%PDF-1.4 falso'),
        )
        self.assertEqual(documento.titulo, 'Permiso de trabajo')

    def test_los_publicos_van_primero(self):
        titulos = list(
            self.equipo.documentos.values_list('publico', flat=True)
        )
        self.assertEqual(titulos, sorted(titulos, reverse=True))

    def test_la_carpeta_va_por_identificador(self):
        self.assertTrue(
            self.publico.fichero.name.startswith(f'documentos/{self.equipo.pk}/')
        )

    def test_borrar_el_documento_borra_su_fichero(self):
        ruta = self.publico.fichero.path
        self.assertTrue(os.path.exists(ruta))
        self.publico.delete()
        self.assertFalse(os.path.exists(ruta))

    def test_borrar_el_equipo_se_lleva_los_ficheros(self):
        rutas = [self.publico.fichero.path, self.privado.fichero.path]
        self.equipo.delete()
        self.assertEqual([r for r in rutas if os.path.exists(r)], [])

    def test_retirar_un_documento_exige_confirmar(self):
        User.objects.create_user('tecnico', password='x')
        self.client.login(username='tecnico', password='x')
        url = reverse('evaluaciones:documento_borrar', args=[self.publico.pk])

        # Un GET solo enseña la confirmación: no borra nada.
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Documento.objects.filter(pk=self.publico.pk).exists())

        self.client.post(url)
        self.assertFalse(Documento.objects.filter(pk=self.publico.pk).exists())


@override_settings(MEDIA_ROOT=TMP)
class EvidenciaDocumental(TestCase):
    """El aviso de documentos que acreditan la evaluación.

    No es una no conformidad: avisa, no invalida. Evita que se lea
    «Conforme» y se cierre la pantalla sin ver que la evidencia no está.
    """

    def setUp(self):
        self.equipo = Equipo.objects.create(codigo='EQ-200', nombre='Prensa')
        grupo = GrupoCriterio.objects.create(nombre='GC-00')
        self.criterio = Criterio.objects.create(
            grupo=grupo, enunciado='¿Tiene marcado CE?',
        )
        EvidenciaEsperada.objects.create(criterio=self.criterio, tipo='CE')
        self.sin_documento = Criterio.objects.create(
            grupo=grupo, enunciado='¿Los mandos son visibles?',
        )
        self.evaluacion = Evaluacion.objects.create(equipo=self.equipo)

    def responder(self, criterio, resultado):
        return Respuesta.objects.create(
            evaluacion=self.evaluacion, criterio=criterio, resultado=resultado,
        )

    def test_conforme_sin_el_documento_avisa(self):
        self.responder(self.criterio, 'C')
        pendientes = self.evaluacion.evidencias_pendientes
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0][1], 'Declaración CE de conformidad')

    def test_con_el_documento_subido_no_avisa(self):
        self.responder(self.criterio, 'C')
        Documento.objects.create(
            equipo=self.equipo, tipo='CE',
            fichero=SimpleUploadedFile('ce.pdf', b'%PDF-1.4 falso'),
        )
        self.assertEqual(self.evaluacion.evidencias_pendientes, [])

    def test_no_aplica_no_avisa(self):
        # Una máquina anterior al marcado CE no puede tener declaración: la
        # disposición no rige, y eso ya lo dice el «No aplica» del criterio.
        self.responder(self.criterio, 'NA')
        self.assertEqual(self.evaluacion.evidencias_pendientes, [])

    def test_no_conforme_no_avisa(self):
        # Un incumplimiento ya está señalado como tal; avisar además de que
        # falta el papel sería contarlo dos veces.
        self.responder(self.criterio, 'NC')
        self.assertEqual(self.evaluacion.evidencias_pendientes, [])

    def test_un_criterio_sin_documento_esperado_nunca_avisa(self):
        self.responder(self.sin_documento, 'C')
        self.assertEqual(self.evaluacion.evidencias_pendientes, [])

    def test_una_evaluacion_nueva_no_vuelve_a_pedir_lo_ya_subido(self):
        """El documento cuelga del equipo, no de la evaluación.

        Subir el manual una vez vale para todas las evaluaciones futuras:
        volver a pedirlo en cada una duplicaría ficheros idénticos.
        """
        Documento.objects.create(
            equipo=self.equipo, tipo='CE',
            fichero=SimpleUploadedFile('ce.pdf', b'%PDF-1.4 falso'),
        )
        segunda = Evaluacion.objects.create(equipo=self.equipo)
        Respuesta.objects.create(
            evaluacion=segunda, criterio=self.criterio, resultado='C',
        )
        self.assertEqual(segunda.evidencias_pendientes, [])

    def test_una_exencion_apaga_el_aviso(self):
        criterio_rm = Criterio.objects.create(
            grupo=self.criterio.grupo, enunciado='¿Mantenimiento?',
        )
        EvidenciaEsperada.objects.create(criterio=criterio_rm, tipo='RM')
        self.responder(criterio_rm, 'C')
        self.assertTrue(self.evaluacion.evidencias_pendientes)

        ExencionDocumental.objects.create(
            equipo=self.equipo, tipo='RM',
            motivo='El mantenimiento lo realiza un taller externo sin registro.',
        )
        # La propiedad del equipo se calcula sobre datos ya traídos, así que
        # hay que releerlo para que no responda con la caché de antes.
        self.evaluacion = Evaluacion.objects.get(pk=self.evaluacion.pk)
        self.assertEqual(self.evaluacion.evidencias_pendientes, [])

    def test_no_se_puede_eximir_el_manual_ni_la_declaracion_ce(self):
        """La lista de eximibles sale de la norma, no del gusto de nadie.

        Permitir eximirlos convertiría la exención en un modo de hacer
        desaparecer un incumplimiento del artículo 5.2.
        """
        form = ExencionForm(equipo=self.equipo)
        ofrecidos = [codigo for codigo, _ in form.fields['tipo'].choices if codigo]
        self.assertNotIn('MF', ofrecidos)
        self.assertNotIn('CE', ofrecidos)
        self.assertIn('RM', ofrecidos)

    def test_una_exencion_sin_motivo_se_rechaza(self):
        form = ExencionForm(
            {'tipo': 'RM', 'motivo': '   '}, equipo=self.equipo,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('motivo', form.errors)

    def test_el_tipo_ya_eximido_no_se_vuelve_a_ofrecer(self):
        ExencionDocumental.objects.create(
            equipo=self.equipo, tipo='RM', motivo='Taller externo.',
        )
        form = ExencionForm(equipo=Equipo.objects.get(pk=self.equipo.pk))
        ofrecidos = [codigo for codigo, _ in form.fields['tipo'].choices if codigo]
        self.assertNotIn('RM', ofrecidos)

    def test_el_aviso_no_cambia_el_dictamen(self):
        self.responder(self.criterio, 'C')
        self.assertEqual(self.evaluacion.dictamen, 'Conforme')
        self.assertTrue(self.evaluacion.evidencias_pendientes)


class RegistroDeIncidencias(TestCase):
    """RF-07: registrar una incidencia marca su evaluación para revisión."""

    def setUp(self):
        self.equipo = Equipo.objects.create(codigo='EQ-300', nombre='Prensa')
        self.antigua = Evaluacion.objects.create(
            equipo=self.equipo, fecha=timezone.now() - timedelta(days=90),
        )
        self.vigente = Evaluacion.objects.create(equipo=self.equipo)
        User.objects.create_user('tecnico', password='x')
        self.client.login(username='tecnico', password='x')
        self.url = reverse('evaluaciones:incidencia_nueva', args=[self.equipo.pk])

    def registrar(self, descripcion='El resguardo ha dejado de enclavar.'):
        return self.client.post(self.url, {
            'descripcion': descripcion,
            'fecha': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        })

    def test_registrar_marca_la_evaluacion_vigente(self):
        self.registrar()
        self.vigente.refresh_from_db()
        self.assertTrue(self.vigente.en_revision)
        self.assertEqual(self.vigente.motivo_revision, 'I')

    def test_no_toca_las_evaluaciones_anteriores(self):
        """Una evaluación de hace tres meses describía el equipo de entonces.

        Es la diferencia con el cambio de tipos, que sí las invalida todas.
        """
        self.registrar()
        self.antigua.refresh_from_db()
        self.assertFalse(self.antigua.en_revision)

    def test_la_incidencia_queda_registrada(self):
        self.registrar('Fuga de aceite en el circuito hidráulico.')
        incidencia = self.equipo.incidencias.get()
        self.assertEqual(
            incidencia.descripcion, 'Fuga de aceite en el circuito hidráulico.',
        )

    def test_una_incidencia_sin_descripcion_se_rechaza(self):
        respuesta = self.client.post(self.url, {
            'descripcion': '   ',
            'fecha': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(self.equipo.incidencias.exists())
        self.vigente.refresh_from_db()
        self.assertFalse(self.vigente.en_revision)

    def test_un_equipo_sin_evaluar_admite_incidencias(self):
        otro = Equipo.objects.create(codigo='EQ-301', nombre='Cizalla')
        respuesta = self.client.post(
            reverse('evaluaciones:incidencia_nueva', args=[otro.pk]),
            {'descripcion': 'Ruido anómalo.',
             'fecha': timezone.localtime().strftime('%Y-%m-%dT%H:%M')},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(otro.incidencias.count(), 1)

    def test_registrar_incidencias_exige_sesion(self):
        self.client.logout()
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/cuentas/entrar/', respuesta['Location'])


@override_settings(MEDIA_ROOT=TMP)
class ConsultaPorQR(TestCase):
    """Las dos capas de la pantalla del QR (RF-08, RF-09 y RF-10)."""

    def setUp(self):
        self.equipo = Equipo.objects.create(codigo='EQ-100', nombre='Prensa')
        self.publico = Documento.objects.create(
            equipo=self.equipo, tipo='MF', titulo='Manual del fabricante',
            fichero=SimpleUploadedFile('m.pdf', b'%PDF-1.4 falso'), publico=True,
        )
        self.privado = Documento.objects.create(
            equipo=self.equipo, tipo='RC', titulo='Acta de comprobacion',
            fichero=SimpleUploadedFile('a.pdf', b'%PDF-1.4 falso'), publico=False,
        )
        self.evaluacion = Evaluacion.objects.create(equipo=self.equipo)
        self.url = reverse('evaluaciones:equipo_publico', args=[self.equipo.token])

    def test_anonimo_ve_datos_basicos_y_solo_lo_publico(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('EQ-100', html)
        self.assertIn('Manual del fabricante', html)
        self.assertNotIn('Acta de comprobacion', html)

    def test_anonimo_no_ve_el_historico(self):
        respuesta = self.client.get(self.url)
        self.assertNotIn('evaluaciones', respuesta.context)
        self.assertNotIn('Histórico', respuesta.content.decode())

    def test_con_sesion_ve_el_historico_y_lo_privado(self):
        User.objects.create_user('tecnico', password='x')
        self.client.login(username='tecnico', password='x')
        html = self.client.get(self.url).content.decode()
        self.assertIn('Acta de comprobacion', html)
        self.assertIn('Histórico', html)

    def test_un_identificador_inventado_da_404(self):
        otro = reverse(
            'evaluaciones:equipo_publico',
            args=['00000000-0000-4000-8000-000000000000'],
        )
        self.assertEqual(self.client.get(otro).status_code, 404)

    def test_cada_equipo_tiene_un_identificador_propio(self):
        otro = Equipo.objects.create(codigo='EQ-101', nombre='Cizalla')
        self.assertNotEqual(self.equipo.token, otro.token)

    def test_la_etiqueta_exige_sesion(self):
        url = reverse('evaluaciones:equipo_qr', args=[self.equipo.pk])
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_la_etiqueta_lleva_la_direccion_completa_del_qr(self):
        User.objects.create_user('tecnico', password='x')
        self.client.login(username='tecnico', password='x')
        respuesta = self.client.get(
            reverse('evaluaciones:equipo_qr', args=[self.equipo.pk])
        )
        # Escaneada desde un móvil, una dirección relativa no lleva a ningún
        # sitio: tiene que ir el servidor delante.
        self.assertIn(f'http://testserver{self.url}', respuesta.context['destino'])
        self.assertIn('<svg', respuesta.context['qr_svg'])
