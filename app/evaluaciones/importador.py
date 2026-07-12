import csv
import io

import openpyxl

from .models import Equipo, Linea

COLUMNAS = ['codigo', 'nombre', 'marca_modelo', 'num_serie', 'anio', 'linea']


def _leer_filas_xlsx(archivo):
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    hoja = wb.active
    filas = hoja.iter_rows(values_only=True)
    try:
        cabecera = next(filas)
    except StopIteration:
        return
    indices = {}
    for i, nombre_col in enumerate(cabecera):
        if nombre_col is None:
            continue
        clave = str(nombre_col).strip().lower()
        if clave in COLUMNAS:
            indices[clave] = i
    for num_fila, valores in enumerate(filas, start=2):
        fila = {}
        for clave, idx in indices.items():
            valor = valores[idx] if idx < len(valores) else None
            if isinstance(valor, float) and valor.is_integer():
                valor = int(valor)
            fila[clave] = '' if valor is None else str(valor).strip()
        if any(fila.values()):
            yield num_fila, fila


def _leer_filas_csv(archivo):
    contenido = archivo.read()
    if isinstance(contenido, bytes):
        contenido = contenido.decode('utf-8-sig')
    lector = csv.reader(io.StringIO(contenido))
    try:
        cabecera = next(lector)
    except StopIteration:
        return
    indices = {}
    for i, nombre_col in enumerate(cabecera):
        clave = (nombre_col or '').strip().lower()
        if clave in COLUMNAS:
            indices[clave] = i
    for num_fila, valores in enumerate(lector, start=2):
        fila = {}
        for clave, idx in indices.items():
            valor = valores[idx] if idx < len(valores) else ''
            fila[clave] = (valor or '').strip()
        if any(fila.values()):
            yield num_fila, fila


def importar_equipos(archivo, nombre_archivo):
    """Importa equipos desde un fichero .xlsx o .csv, fila a fila, con
    política de importación parcial: las filas inválidas se rechazan y se
    reportan, sin abortar la importación de las restantes."""
    nombre_archivo = (nombre_archivo or '').lower()
    if nombre_archivo.endswith('.xlsx'):
        filas = _leer_filas_xlsx(archivo)
    elif nombre_archivo.endswith('.csv'):
        filas = _leer_filas_csv(archivo)
    else:
        return {
            'importados': 0,
            'lineas_nuevas': [],
            'rechazadas': [],
            'error_fichero': 'Formato de fichero no soportado. Usa .xlsx o .csv.',
        }

    importados = 0
    lineas_nuevas = []
    rechazadas = []
    codigos_vistos = set()

    for num_fila, fila in filas:
        codigo = fila.get('codigo', '')
        nombre = fila.get('nombre', '')
        marca_modelo = fila.get('marca_modelo', '')
        num_serie = fila.get('num_serie', '')
        anio_raw = fila.get('anio', '')
        linea_raw = fila.get('linea', '')

        if not codigo:
            rechazadas.append((num_fila, 'Falta el código.'))
            continue
        if codigo in codigos_vistos:
            rechazadas.append((num_fila, f'Código «{codigo}» duplicado en el fichero.'))
            continue
        codigos_vistos.add(codigo)

        if not nombre:
            rechazadas.append((num_fila, 'Falta el nombre.'))
            continue

        anio = None
        if anio_raw:
            try:
                anio = int(anio_raw)
            except ValueError:
                anio = None
            if anio is None or anio <= 0:
                rechazadas.append(
                    (num_fila, f'Año no válido: «{anio_raw}» no es un entero positivo.')
                )
                continue

        if Equipo.objects.filter(codigo=codigo).exists():
            rechazadas.append((num_fila, f'El código «{codigo}» ya existe en la base de datos.'))
            continue

        linea = None
        if linea_raw:
            linea = Linea.objects.filter(nombre__iexact=linea_raw).first()
            if linea is None:
                linea = Linea.objects.create(nombre=linea_raw)
                lineas_nuevas.append(linea.nombre)

        Equipo.objects.create(
            codigo=codigo,
            nombre=nombre,
            marca_modelo=marca_modelo,
            num_serie=num_serie,
            anio=anio,
            linea=linea,
        )
        importados += 1

    return {
        'importados': importados,
        'lineas_nuevas': lineas_nuevas,
        'rechazadas': rechazadas,
        'error_fichero': None,
    }
