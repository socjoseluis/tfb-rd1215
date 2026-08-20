# Casos límite pendientes de cubrir con pruebas

Notas técnicas en crudo. Cada punto es un caso que hoy no está cubierto y que
debe traducirse en un test al ampliar la suite de pruebas.

Origen: una revisión crítica del código. Los tres primeros no son alcanzables desde la interfaz con uso normal; el cuarto sí.

## 1. Criterio de año distinto entre alta y importación

- Alta individual: acepta `anio = 0`.
- Importador (`app/evaluaciones/importador.py:108`): rechaza `anio <= 0`
  con el motivo «no es un entero positivo».

Las dos vías de entrada aplican reglas distintas al mismo campo. Decidir el
criterio único (probablemente `anio > 0`) y probar ambas vías contra él.

## 2. POST de evaluación con criterios duplicados

La restricción de unicidad existe en el modelo, pero el formset no la valida
antes de guardar: un POST manipulado con el mismo criterio repetido produce
`IntegrityError` y una respuesta 500 en lugar de un error de validación.

No alcanzable desde la interfaz (el formulario genera un campo por criterio),
pero es el tipo de caso que un test de vista debe cubrir.

## 3. POST de importación sin fichero

Sin mensaje del servidor: la única defensa es el atributo `required` del
navegador. Si se envía el formulario sin fichero salteando el cliente, no hay
retroalimentación.

## 4. Ficheros de importación defectuosos (sí alcanzable)

Ver también el arreglo pendiente en el importador:

- `.xlsx` corrupto o que no es un zip válido → `zipfile.BadZipFile`.
- `.csv` guardado en Latin-1 (Excel en Windows, con «año» o «Línea» en la
  cabecera) → `UnicodeDecodeError` en la decodificación `utf-8-sig`.

Ambos llegan hoy al usuario como error 500. El mecanismo para informar bien ya
existe (`error_fichero` en el diccionario de retorno, ya pintado por la
plantilla); falta capturar las excepciones.

Detalle a tener en cuenta al arreglarlo: `_leer_filas_xlsx` y `_leer_filas_csv`
son generadores, así que la apertura del fichero y la decodificación no ocurren
en la llamada, sino en la primera iteración dentro de `importar_equipos`. Un
`try/except` alrededor de la llamada no capturaría nada.

*(Resuelto el 25/07/2026: los lectores devuelven listas y las excepciones se
capturan por formato. Se mantiene aquí el caso para que la suite lo cubra.)*

## 5. Confirmación de tipos en el alta manual (decisión a revisar)

No es un fallo: es una decisión de diseño razonada en el docstring de
`equipo_alta`, pero tiene un flanco que conviene revisar.

Comportamiento actual (`app/evaluaciones/views.py:57-60`): el alta manual pone
`tipos_confirmados = True` **siempre**, incluso si no se marca ningún tipo. El
importador no lo toca, así que los equipos importados llegan sin confirmar.

La tensión: `tipos_confirmados` existe precisamente para distinguir «no es de
ningún tipo» de «nadie ha comprobado el tipo» — lo dice su propio `help_text` en
`models.py`. El alta resuelve esa ambigüedad por decreto.

Consecuencia concreta: la guarda de `views.py:173`, que impide evaluar un equipo
con tipos sin confirmar, **nunca se dispara para un equipo dado de alta a mano**.
Si el técnico se salta la sección de tipos al dar de alta una carretilla, el
sistema la evalúa con los 23 criterios generales en vez de 34 y emite un dictamen
de apariencia válida al que le faltan los criterios del Anexo I.2.1 y I.2.2.

Lo que hoy sostiene la decisión: el campo `tipos` lleva el `help_text` «Marque
todos los que apliquen; […] Si no es de ninguno, déjelo sin marcar», visible en
el formulario de alta. El valor por defecto está
instruido, no es una suposición silenciosa. Lo que queda sin cubrir es el usuario
que no lee el texto de ayuda.

Las dos salidas si se retoma:

1. **Elección explícita en el alta**: exigir o al menos un tipo marcado, o una
   casilla «no es de ninguno». Solo entonces se confirma. Es lo correcto, pero
   toca formulario, plantilla y validación.
2. **Que el alta no confirme**: el equipo queda sin confirmar igual que los
   importados y la confirmación se hace siempre en la pantalla de tipos. Una sola
   puerta, a cambio de un paso más para el usuario.

Test a escribir en cualquiera de los dos casos: alta sin marcar ningún tipo y
comprobar el estado esperado de `tipos_confirmados`.
