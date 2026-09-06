# TFB — Aplicación web de evaluación de seguridad de equipos (RD 1215/1997)

Trabajo Final de Bàtxelor en Informática — Universitat Carlemany (ed. 2510).

Prototipo funcional en Django para evaluar la conformidad de los equipos de
trabajo frente al Real Decreto 1215/1997, organizarlos por líneas de producción
y dar acceso a su documentación desde el taller mediante un código QR.

## Estructura
- `app/` — Proyecto Django (prototipo funcional)
- `memoria/` — Memoria en LaTeX (KOMA-Script, biblatex/APA 7)
- `docs/` — Notas de trabajo en Markdown (insumo)
- `assets/` — Diagramas y capturas

## Requisitos
Python 3.12 y SQLite. No hace falta ningún servidor de base de datos: la
persistencia es un único fichero que se crea al migrar.

## Puesta en marcha
Todos los comandos se ejecutan desde la raíz del repositorio.

1. Crear el entorno virtual e instalar las dependencias:

       python3 -m venv .venv
       source .venv/bin/activate
       pip install -r requirements.txt

2. Crear la configuración a partir de la plantilla y **poner una `SECRET_KEY`
   propia**. Si se deja el valor de relleno, Django avisa de clave débil:

       cp app/.env.example app/.env

3. Crear la base de datos:

       python app/manage.py migrate

4. Cargar los criterios del RD 1215/1997 y, si se quiere un caso de ejemplo,
   el inventario sintético:

       python app/manage.py loaddata criterios_rd1215
       python app/manage.py loaddata caso_ejemplo

5. Copiar los documentos de ejemplo que acompañan al caso sintético. La carpeta
   `app/media/` no se versiona, porque guarda lo que suben los usuarios, así que
   hay que crearla antes:

       mkdir -p app/media/documentos
       cp -r app/evaluaciones/fixtures/documentos_ejemplo/* app/media/documentos/

6. Crear un usuario con el que entrar:

       python app/manage.py createsuperuser

7. Arrancar el servidor:

       python app/manage.py runserver

   La aplicación queda en `http://localhost:8000/`. Sin sesión iniciada solo es
   accesible la consulta en campo que abre el código QR; el resto exige entrar.

## Pruebas

       python app/manage.py test app

## Licencia y datos
El caso de estudio es enteramente sintético: no contiene datos de ninguna
empresa real.
