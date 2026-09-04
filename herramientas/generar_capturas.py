#!/usr/bin/env python
"""Genera las capturas de pantalla del prototipo con un formato homogéneo.

Las capturas del prototipo son material del capítulo «Prototipo funcional».
Tomadas a mano salen cada una con un ancho distinto, según el tamaño que
tuviera la ventana, y al escalarlas todas a `0.9\\textwidth` unas quedan más
nítidas que otras. Este script las toma siempre con el mismo viewport, de
modo que el ancho es idéntico en todas y solo varía el alto.

Requisitos (ninguno es dependencia del prototipo, por eso no están en
requirements.txt):

    pip install playwright

El navegador no se descarga: se reutiliza el Chromium que instaló puppeteer
para mermaid-cli. Si no estuviera, se indica otro con CHROME=/ruta/al/chrome.

Antes de ejecutar hay que tener el servidor levantado y un usuario con el que
entrar (que no se versiona: créalo con `manage.py createsuperuser` o desde el
shell). La contraseña se pasa por el entorno, nunca escrita aquí:

    CAPTURAS_CLAVE=... python herramientas/generar_capturas.py

Las páginas cortas se capturan enteras, ajustando el alto al contenido. Las
largas —una evaluación son 34 criterios— se capturan recortando una pantalla,
porque la página completa, reducida al ancho de la caja de texto, no se leería.
"""

import os
import pathlib
import struct
import sys
import time
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402  (después de fijar DJANGO_SETTINGS_MODULE)

django.setup()

from evaluaciones.models import Equipo  # noqa: E402

BASE = os.environ.get('BASE', 'http://127.0.0.1:8006')
SALIDA = RAIZ / 'assets' / 'capturas'
USUARIO = os.environ.get('CAPTURAS_USUARIO', 'tecnico')
# Sin valor por defecto a propósito: una contraseña escrita en un fichero
# versionado es una contraseña publicada, aunque sea la de un usuario local.
CLAVE = os.environ.get('CAPTURAS_CLAVE')


def buscar_chrome():
    """Ruta del navegador, sin fijar ninguna ruta de una máquina concreta.

    Se reutiliza el Chromium que instala puppeteer para mermaid-cli, que es
    lo que ya hay en el entorno de desarrollo. Con CHROME=/ruta se indica
    cualquier otro.
    """
    if os.environ.get('CHROME'):
        return os.environ['CHROME']
    candidatos = sorted(
        pathlib.Path.home().glob('.cache/puppeteer/chrome/*/chrome-linux64/chrome')
    )
    if candidatos:
        return str(candidatos[-1])
    raise SystemExit(
        'No se encuentra ningún Chromium. Indícalo con CHROME=/ruta/al/chrome.'
    )

ANCHO, ESCALA, RECORTE = 1280, 2, 900
MOVIL = {'width': 390, 'height': 844}

# El primer botón de cualquier página es el «Salir» de la barra de navegación:
# si el selector no se acota a <main>, enviar un formulario cierra la sesión y
# las capturas siguientes salen de la pantalla de entrada.
ENVIAR = 'main button[type=submit], main input[type=submit]'


def esperar_servidor(intentos=40):
    for _ in range(intentos):
        try:
            urllib.request.urlopen(BASE, timeout=1)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f'El servidor no responde en {BASE}. Arráncalo antes.')


def _guardar(pag, nombre):
    fichero = SALIDA / f'{nombre}.png'
    pag.screenshot(path=str(fichero))
    ancho, alto = struct.unpack('>II', fichero.read_bytes()[16:24])
    print(f'  {nombre:32} {ancho}x{alto:<5} {fichero.stat().st_size // 1024:4} KB')


def completa(pag, nombre, ruta=None, ancho=ANCHO):
    """Captura la página entera, con el alto ajustado a su contenido."""
    if ruta is not None:
        # Encoger primero: si no, la página hereda el alto de la captura
        # anterior y scrollHeight devuelve ese en vez del del contenido.
        pag.set_viewport_size({'width': ancho, 'height': 200})
        pag.goto(BASE + ruta, wait_until='networkidle')
    alto = pag.evaluate('Math.ceil(document.documentElement.scrollHeight)')
    pag.set_viewport_size({'width': ancho, 'height': alto})
    _guardar(pag, nombre)


def recorte(pag, nombre, ruta=None, al_final=False):
    """Captura una pantalla, para páginas demasiado largas para verse enteras."""
    pag.set_viewport_size({'width': ANCHO, 'height': RECORTE})
    if ruta is not None:
        pag.goto(BASE + ruta, wait_until='networkidle')
    if al_final:
        # Se baja hasta el botón de enviar y no hasta scrollHeight: la página
        # sigue reajustándose tras networkidle y un solo scrollTo se quedaba
        # corto, dejando fuera el último grupo de criterios y el botón.
        pag.locator(ENVIAR).scroll_into_view_if_needed()
        pag.wait_for_timeout(500)
        pag.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
        pag.wait_for_timeout(500)
    _guardar(pag, nombre)


def entrar(pag):
    pag.goto(f'{BASE}/cuentas/entrar/')
    pag.fill('input[name=username]', USUARIO)
    pag.fill('input[name=password]', CLAVE)
    pag.click(ENVIAR)
    pag.wait_for_load_state('networkidle')
    if 'Salir' not in pag.content():
        raise SystemExit(f'No se ha podido entrar como «{USUARIO}».')


def main():
    if not CLAVE:
        raise SystemExit(
            'Falta la contraseña: CAPTURAS_CLAVE=... python herramientas/generar_capturas.py'
        )
    esperar_servidor()

    # Todo lo que venga del ORM se consulta ANTES de abrir el navegador: la
    # API síncrona de Playwright levanta un bucle de eventos y Django rechaza
    # las consultas hechas desde dentro.
    ids = {e.codigo: e.pk for e in Equipo.objects.all()}
    token = Equipo.objects.get(codigo='EQ-008').token
    ev_conforme = Equipo.objects.get(codigo='EQ-008').ultima_evaluacion.pk
    ev_noconforme = Equipo.objects.get(codigo='EQ-006').ultima_evaluacion.pk
    ev_en_duda = Equipo.objects.get(codigo='EQ-002').ultima_evaluacion.pk
    codigos_antes = set(Equipo.objects.values_list('codigo', flat=True))

    SALIDA.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=buscar_chrome(), args=['--no-sandbox'])

        # --- Sin sesión: lo que ve quien no se ha identificado --------------
        anon = nav.new_context(
            viewport={'width': ANCHO, 'height': 900}, device_scale_factor=ESCALA,
        )
        pag = anon.new_page()
        completa(pag, 'rnf-autenticacion-entrar', '/cuentas/entrar/')
        completa(pag, 'rf09-consulta-publica', f'/q/{token}/')
        anon.close()

        # --- Con sesión ----------------------------------------------------
        ctx = nav.new_context(
            viewport={'width': ANCHO, 'height': 900}, device_scale_factor=ESCALA,
        )
        pag = ctx.new_page()
        entrar(pag)

        completa(pag, 'rf05-portada', '/')
        completa(pag, 'rf01-alta-formulario', '/equipos/alta/')
        completa(pag, 'rf01-editar-1', f'/equipos/{ids["EQ-004"]}/editar/')
        completa(pag, 'rf01-editar-2', f'/equipos/{ids["EQ-001"]}/editar/')
        # La ficha, no la pantalla de tipos: lo que se quiere enseñar es el
        # indicador «Sin confirmar» y el enlace «Cambiar» que llevan a ella.
        completa(pag, 'rf04-tipos', f'/equipos/{ids["EQ-005"]}/')
        completa(pag, 'rf03-desfasada', f'/equipos/{ids["EQ-003"]}/')
        completa(pag, 'rf03-historico', f'/equipos/{ids["EQ-007"]}/')
        # La segunda capa del QR (RF-10) es la consulta en campo CON sesión,
        # no la ficha de gestión: es la misma dirección que la consulta
        # pública, vista ahora con la sesión abierta.
        completa(pag, 'rf10-ficha-completa', f'/q/{token}/')
        completa(pag, 'rf06-medidas', '/medidas/')
        completa(pag, 'rf06-medidas-todas', '/medidas/?estado=todas')
        completa(pag, 'rf06-medida-nueva', f'/evaluaciones/{ev_noconforme}/medidas/nueva/')
        completa(pag, 'rf07-incidencia-nueva', f'/equipos/{ids["EQ-004"]}/incidencias/nueva/')
        completa(pag, 'rf08-qr-etiqueta', f'/equipos/{ids["EQ-008"]}/qr/')
        completa(pag, 'rf09-documento-subir', f'/equipos/{ids["EQ-006"]}/documentos/subir/')
        completa(pag, 'rf09-exencion-nueva', f'/equipos/{ids["EQ-006"]}/documentos/no-procede/')
        completa(pag, 'rf02-importacion-formulario', '/equipos/importar/')
        completa(pag, 'rf09-exencion-documental', f'/equipos/{ids["EQ-010"]}/')

        # Alta rechazada por validación: código repetido y año imposible.
        pag.set_viewport_size({'width': ANCHO, 'height': 200})
        pag.goto(f'{BASE}/equipos/alta/', wait_until='networkidle')
        pag.fill('input[name=codigo]', 'EQ-001')
        pag.fill('input[name=anio]', '3025')
        pag.click(ENVIAR)
        pag.wait_for_load_state('networkidle')
        completa(pag, 'rf01-alta-validacion')

        # Pantallas largas: una evaluación son 23 o 34 criterios.
        recorte(pag, 'rf04-evaluacion-carretilla-1', f'/equipos/{ids["EQ-008"]}/evaluar/')
        recorte(pag, 'rf04-evaluacion-carretilla-2', al_final=True)
        recorte(pag, 'rf04-evaluacion-fijo-2', f'/equipos/{ids["EQ-006"]}/evaluar/', al_final=True)
        recorte(pag, 'rf04-evaluacion-transpaleta', f'/equipos/{ids["EQ-010"]}/evaluar/', al_final=True)
        recorte(pag, 'rf04-resultado-conforme', f'/evaluaciones/{ev_conforme}/')
        recorte(pag, 'rf04-resultado-noconforme', f'/evaluaciones/{ev_noconforme}/')
        recorte(pag, 'rf07-evaluacion-en-duda', f'/evaluaciones/{ev_en_duda}/')

        # --- Móvil: ancho distinto A PROPÓSITO, es otro dispositivo --------
        # Demuestra el RNF-01: por debajo de 768 px se oculta la columna de
        # tipos y la barra de navegación se parte en varias líneas.
        # Va ANTES de la importación de rechazos: esa importación mete en la
        # base de datos las filas válidas del fichero de ejemplo y, hasta que
        # se limpian al final, la portada enseñaría un equipo que no es del
        # caso de estudio.
        mov = nav.new_context(
            viewport=MOVIL, device_scale_factor=3, is_mobile=True, has_touch=True,
        )
        pag_movil = mov.new_page()
        entrar(pag_movil)
        pag_movil.goto(f'{BASE}/', wait_until='networkidle')
        _guardar(pag_movil, 'rnf01-movil-portada')
        mov.close()

        # La de rechazos va la última: importa de verdad, y las filas válidas
        # del fichero de ejemplo entran en la base de datos. Se limpian abajo.
        pag.set_viewport_size({'width': ANCHO, 'height': 200})
        pag.goto(f'{BASE}/equipos/importar/', wait_until='networkidle')
        pag.set_input_files(
            'input[name=fichero]',
            str(RAIZ / 'docs' / 'ejemplos_importacion' / 'equipos_errores.xlsx'),
        )
        pag.click(ENVIAR)
        pag.wait_for_load_state('networkidle')
        completa(pag, 'rf02-importacion-rechazos')
        ctx.close()
        nav.close()

    sobran = Equipo.objects.exclude(codigo__in=codigos_antes)
    if sobran.exists():
        print(f'\nlimpiando lo que importó la captura de rechazos: '
              f'{sorted(sobran.values_list("codigo", flat=True))}')
        sobran.delete()

    total = sum(f.stat().st_size for f in SALIDA.glob('*.png'))
    anchos = {
        struct.unpack('>II', f.read_bytes()[16:24])[0] for f in SALIDA.glob('*.png')
    }
    print(f'\n{len(list(SALIDA.glob("*.png")))} capturas · '
          f'anchos: {sorted(anchos)} · {total / 1024 / 1024:.1f} MB')


if __name__ == '__main__':
    main()
