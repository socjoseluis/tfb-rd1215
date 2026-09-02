import os
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import DocumentoForm, ExencionForm
from .models import (
    Criterio, Documento, Equipo, Evaluacion, EvidenciaEsperada,
    ExencionDocumental, GrupoCriterio, Respuesta, TipoEquipo,
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

    def test_no_se_puede_subir_un_documento_de_un_tipo_eximido(self):
        """El equipo no puede decir dos cosas contrarias a la vez."""
        ExencionDocumental.objects.create(
            equipo=self.equipo, tipo='RM', motivo='Taller externo sin registro.',
        )
        form = DocumentoForm(
            {'tipo': 'RM', 'titulo': 'Parte de mantenimiento', 'publico': False},
            {'fichero': SimpleUploadedFile('p.pdf', b'%PDF-1.4 falso')},
            equipo=Equipo.objects.get(pk=self.equipo.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('tipo', form.errors)

    def test_no_se_puede_eximir_un_tipo_que_ya_esta_subido(self):
        Documento.objects.create(
            equipo=self.equipo, tipo='RM',
            fichero=SimpleUploadedFile('p.pdf', b'%PDF-1.4 falso'),
        )
        form = ExencionForm(equipo=Equipo.objects.get(pk=self.equipo.pk))
        ofrecidos = [codigo for codigo, _ in form.fields['tipo'].choices if codigo]
        self.assertNotIn('RM', ofrecidos)

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

    def test_la_incidencia_queda_firmada_por_quien_la_registra(self):
        """Lo que tumba un dictamen lleva firma.

        Sin autor, cualquiera con cuenta podría marcar para revisión la
        evaluación de cualquier equipo sin que se pudiera saber quién fue.
        """
        self.registrar()
        self.assertEqual(
            self.equipo.incidencias.get().autor.get_username(), 'tecnico',
        )

    def test_no_se_puede_firmar_en_nombre_de_otro(self):
        otro = User.objects.create_user('intruso', password='x')
        self.client.post(self.url, {
            'descripcion': 'Intento de firmar como otro.',
            'fecha': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'autor': otro.pk,
        })
        # El autor lo pone la sesión, no el formulario.
        self.assertEqual(
            self.equipo.incidencias.get().autor.get_username(), 'tecnico',
        )

    def test_la_incidencia_sobrevive_a_la_baja_de_su_autor(self):
        self.registrar()
        User.objects.get(username='tecnico').delete()
        incidencia = self.equipo.incidencias.get()
        self.assertIsNone(incidencia.autor)
        self.vigente.refresh_from_db()
        self.assertTrue(self.vigente.en_revision)

    def test_la_firma_sobrevive_al_borrado_de_la_cuenta(self):
        """Lo normal es desactivar al técnico, no borrarlo.

        Pero si alguien lo borra de verdad, la incidencia tiene que seguir
        diciendo quién la registró: si no, queda una evaluación tumbada sin
        saber por quién.
        """
        self.registrar()
        User.objects.get(username='tecnico').delete()
        incidencia = self.equipo.incidencias.get()
        self.assertIsNone(incidencia.autor)
        self.assertEqual(incidencia.firma, 'tecnico')

    def test_desactivar_al_tecnico_conserva_todo(self):
        self.registrar()
        usuario = User.objects.get(username='tecnico')
        usuario.is_active = False
        usuario.save(update_fields=['is_active'])

        incidencia = self.equipo.incidencias.get()
        self.assertEqual(incidencia.firma, 'tecnico')
        self.assertIsNotNone(incidencia.autor)
        # Y esa cuenta ya no entra.
        self.client.logout()
        self.assertFalse(self.client.login(username='tecnico', password='x'))

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


class SeguimientoDeMedidas(TestCase):
    """Medidas correctivas derivadas de no conformidades (RF-06).

    El seguimiento es lo que separa una lista de arreglos propuestos de un
    registro de lo que se ha hecho, así que lo que se comprueba no es que la
    medida se guarde, sino de qué cuelga y qué pasa al cerrarla.
    """

    def setUp(self):
        self.equipo = Equipo.objects.create(codigo='EQ-300', nombre='Sierra')
        grupo = GrupoCriterio.objects.create(nombre='GC-01')
        self.criterio = Criterio.objects.create(
            grupo=grupo, enunciado='¿Los órganos de accionamiento son visibles?',
        )
        self.evaluacion = Evaluacion.objects.create(equipo=self.equipo)
        self.no_conformidad = Respuesta.objects.create(
            evaluacion=self.evaluacion, criterio=self.criterio, resultado='NC',
        )
        User.objects.create_user('tecnico', password='x')
        self.client.login(username='tecnico', password='x')

    def test_una_medida_nace_pendiente_y_cuelga_de_su_no_conformidad(self):
        # Se da de alta por la vista y no con el ORM: creada a mano solo se
        # comprobaría que Django guarda una fila. Por la vista se recorre la
        # dirección, el formulario, el guardado y la redirección.
        respuesta = self.client.post(
            reverse('evaluaciones:medida_nueva', args=[self.evaluacion.pk]),
            {
                'descripcion': 'Reponer el pulsador de parada de emergencia',
                'no_conformidades': [self.no_conformidad.pk],
                'estado': 'P',
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        medida = self.evaluacion.medidas.get()
        self.assertEqual(medida.estado, 'P')
        self.assertIsNone(medida.fecha_cierre)
        # Lo que sostiene el «derivadas de las no conformidades» del RF-06:
        # sin esto la prueba solo diría que se guarda texto.
        self.assertEqual(
            list(medida.no_conformidades.all()), [self.no_conformidad]
        )

    def crear_medida(self):
        """Medida ya dada de alta, para las pruebas que van del cierre.

        Aquí sí se crea con el ORM: lo que se prueba es el cambio de estado, y
        pasar por el formulario solo añadiría ruido a la prueba.
        """
        medida = self.evaluacion.medidas.create(
            descripcion='Reponer el pulsador de parada de emergencia',
        )
        medida.no_conformidades.set([self.no_conformidad])
        return medida

    def test_cerrar_una_medida_le_pone_fecha_y_reabrirla_se_la_quita(self):
        medida = self.crear_medida()
        url = reverse('evaluaciones:medida_estado', args=[medida.pk])

        self.client.post(url, {'estado': 'R'})
        medida.refresh_from_db()
        self.assertEqual(medida.estado, 'R')
        # La fecha la pone la vista, no el formulario: tecleada a mano acabaría
        # habiendo medidas realizadas sin fecha.
        self.assertEqual(medida.fecha_cierre, timezone.localdate())

        self.client.post(url, {'estado': 'P'})
        medida.refresh_from_db()
        self.assertEqual(medida.estado, 'P')
        self.assertIsNone(medida.fecha_cierre)

    def test_cerrar_una_medida_no_cambia_el_dictamen(self):
        # Donde el RF-06 se cruza con el RF-03: el histórico no se reescribe,
        # así que la conformidad se recupera evaluando de nuevo y la medida
        # cerrada queda como rastro de por qué cambió.
        medida = self.crear_medida()
        self.assertEqual(self.evaluacion.dictamen, 'No conforme')

        self.client.post(
            reverse('evaluaciones:medida_estado', args=[medida.pk]),
            {'estado': 'R'},
        )

        self.assertEqual(self.evaluacion.dictamen, 'No conforme')


class CriteriosDelFixtureTest(TestCase):
    """Comprobaciones sobre el cuestionario del RD 1215/1997.

    Es el único sitio donde se carga `criterios_rd1215.json`: el resto de
    pruebas construye sus criterios a mano porque solo les importa la lógica.
    Aquí importa el dato. Estos recuentos son parte del contrato del fichero:
    si se separan de él, el cuestionario deja de ser el del RD 1215/1997.
    """

    fixtures = ['criterios_rd1215.json']

    def criterios_de(self, equipo):
        return Criterio.objects.filter(grupo__in=equipo.grupos_aplicables())

    def test_un_equipo_sin_tipos_aplica_solo_los_generales(self):
        equipo = Equipo.objects.create(
            codigo='PR-001', nombre='Prensa', tipos_confirmados=True,
        )
        self.assertEqual(self.criterios_de(equipo).count(), 23)

    def test_una_carretilla_aplica_ademas_los_del_anexo_I_2(self):
        equipo = Equipo.objects.create(
            codigo='CA-001', nombre='Carretilla', tipos_confirmados=True,
        )
        equipo.tipos.set(TipoEquipo.objects.all())
        self.assertEqual(self.criterios_de(equipo).count(), 34)

    def test_la_informacion_de_utilizacion_la_reclama_un_criterio(self):
        # El tipo «IU» existía desde el RF-09 y no lo pedía ningún criterio:
        # se podía subir una evidencia que nada reclamaba, y el artículo 5.2
        # no se preguntaba en ninguna parte del cuestionario.
        criterios = Criterio.objects.filter(evidencias_esperadas__tipo='IU')
        self.assertEqual(criterios.count(), 1)
        self.assertEqual(criterios.get().grupo.nombre, 'GC-00 Documentación y marcado')
