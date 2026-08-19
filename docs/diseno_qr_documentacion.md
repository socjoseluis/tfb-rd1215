# Documentación de los equipos y consulta por QR

Notas técnicas del bloque que cubre los requisitos RF-08, RF-09 y RF-10:

- **RF-08**: consultar la información de un equipo en campo mediante QR.
- **RF-09**: información básica y documentación obligatoria, sin autenticar.
- **RF-10**: ficha completa en solo lectura para el usuario autenticado.

Los tres son una sola pantalla con dos capas, más la etiqueta que se pega a la
máquina.

## Por qué la consulta anónima no es una concesión

El artículo 5.2 del RD 1215/1997 dice que la documentación informativa del
fabricante «estará a disposición de los trabajadores». Exigir contraseña para
leer el manual de la máquina que uno maneja incumpliría esa obligación: el
trabajador no es un usuario del sistema, y la gestión de personas queda fuera
del alcance del proyecto por el RGPD, de modo que no hay ninguna cuenta que
pudiera pedírsele. Por eso existe la capa anónima, y por eso no se registra
quién consulta.

La aplicación exige sesión en todas sus vistas mediante
`LoginRequiredMiddleware`. Las dos excepciones —la página pública del QR y la
entrega de un documento público— van marcadas con `@login_not_required`, para
que se lea en el código que son deliberadas.

## Modelo `Documento`

| Campo | Tipo | Notas |
| --- | --- | --- |
| `equipo` | FK a `Equipo` | El documento pertenece a un equipo |
| `tipo` | choices | `MF`, `IU`, `CE`, `MC`, `RC`, `RM`, `OT` |
| `tipo_otro` | texto corto | Obligatorio solo si el tipo es «Otro» |
| `titulo` | texto corto | Opcional: vacío toma el nombre del tipo |
| `fichero` | `FileField` | Sube a `media/documentos/<id del equipo>/` |
| `publico` | booleano | Si se ve sin autenticar. Nace en falso |
| `fecha_subida` | fecha y hora | Automática |

### Los tipos y su origen

- `MF` **Manual o instrucciones del fabricante** — art. 5.2, último párrafo, y
  art. 3.5, que ordena mantener el equipo según esas instrucciones.
- `IU` **Información de utilización segura** — art. 5.2 a, b y c: la que
  redacta la empresa, con las condiciones de uso correcto, las situaciones
  anormales y peligrosas previsibles y las conclusiones de la experiencia. La
  norma prevé que se presente en forma de folletos informativos cuando el
  equipo lo requiera por volumen, complejidad o uso poco frecuente.
- `CE` **Declaración CE de conformidad** — respaldo documental del art. 3.1.a.
- `MC` **Fotografía del marcado CE o placa de características** — el marcado
  no es la declaración: es la placa atornillada a la máquina, que se comprueba
  mirando. Van separados para no confundirlos.
- `RC` **Registro de comprobación** — art. 4.4, que obliga a documentar los
  resultados y conservarlos durante toda la vida útil del equipo.
- `RM` **Registro de mantenimiento** — la norma **no** lo exige: el art. 3.5
  obliga a hacer el mantenimiento, no a documentarlo. Se incluye porque es lo
  único que acreditaría ese cumplimiento.
- `OT` **Otro**, con `tipo_otro` obligatorio. La lista no es una jaula: deja
  subir cualquier documento propio del servicio de prevención con el nombre que
  le dé el técnico, y un equipo puede tener tantos como haga falta. Sin
  `tipo_otro`, la consulta en campo mostraría «Otro», que es no informar.

### Por qué `publico` es de cada documento y no del tipo

El manual del fabricante y la declaración CE son la documentación del art. 5.2
y van abiertos; el registro de comprobación del art. 4.4 está a disposición de
**la autoridad laboral**, no de los trabajadores. Mismo equipo, dos
obligaciones documentales, dos destinatarios distintos. Deducir la visibilidad
del tipo obligaría además a cerrar hoy y para siempre la lista de lo que es
público, y bastaría un tipo nuevo mal clasificado para publicar algo que no
debía salir. La marca tiene valor por defecto seguro: **nace cerrada y se abre
a propósito**.

### Lo que el modelo no lleva

- **Quién sube el documento y quién lo consulta.** Son datos personales y no
  los pide ningún requisito.
- **Versionado y caducidad del documento.** Sustituir un manual es borrar y
  subir.

### Validación del fichero

Extensiones aceptadas (PDF e imagen) y tamaño máximo, comprobados en el
formulario. Sin tope, un solo fichero puede llenar el disco del servidor; sin
lista de formatos, la aplicación se convierte en alojamiento de ficheros
arbitrarios servidos desde su propio dominio. Se comprueba la extensión y no el
contenido: un fichero puede llamarse `.pdf` y ser otra cosa. Comprobarlo de
verdad exigiría una biblioteca aparte, y lo que se sube nunca se ejecuta ni se
interpreta, solo se entrega tal cual.

Las imágenes se aceptan a propósito: la evidencia del marcado CE es una
fotografía de la placa hecha con el móvil en planta.

### Por qué los ficheros no se sirven como carpeta estática

`MEDIA_ROOT` vive en `app/media/`, que no se versiona. Servir esa carpeta como
ficheros sueltos tendría dos efectos contrarios y ambos malos: cualquiera que
diera con la ruta abriría también los documentos no públicos, y a la vez
`LoginRequiredMiddleware` exigiría sesión para todos, impidiendo al trabajador
leer el manual. Por eso los entrega una vista propia que aplica la regla antes
de servir el fichero, y el control de acceso vive en un solo sitio.

Responde 404 y no 403 a quien no puede ver un documento: un 403 confirmaría su
existencia.

## La dirección del QR

Campo `token` (UUID) en `Equipo`, único, del que cuelga la vista pública en
`/q/<uuid>/`.

No se usa el código del equipo por dos razones. La página es anónima, y con
códigos correlativos cualquiera podría recorrer el inventario desde fuera sin
haber visto ninguna máquina; además el código se puede corregir al editar el
equipo, y entonces todas las etiquetas impresas dejarían de valer. El
identificador aleatorio no estorba a quien está delante de la máquina, que
escanea, y sobrevive a los cambios de datos. Es minimización de la exposición,
no seguridad por oscuridad: la información sensible sigue detrás de la
autenticación.

Coste asumido: si la etiqueta se ensucia no se puede teclear la dirección de
memoria. La ficha sigue alcanzable buscando el equipo con sesión.

La migración rellena el identificador equipo a equipo, en tres pasos, porque un
campo único con valor por defecto lo calcularía una sola vez y todas las filas
existentes recibirían el mismo.

## Generación del QR

`segno`: Python puro, licencia BSD, sin dependencias. Genera SVG vectorial, que
se incrusta en la plantilla sin fichero intermedio que guardar, servir ni
limpiar, y que se imprime nítido a cualquier tamaño. Un PNG tiene resolución
fija y, en una etiqueta grande, se pixela; un QR pixelado se lee peor con el
móvil, que es el escenario del RF-08. Se usa corrección de errores media, que
recupera hasta el 15 % del código: una etiqueta pegada a una máquina acaba con
polvo, grasa o un roce.

La dirección se construye con `build_absolute_uri`. Escaneada desde un móvil,
una relativa no lleva a ninguna parte y `localhost` apuntaría al propio
teléfono. **Limitación**: la etiqueta queda atada al dominio con el que se
generó; en producción esto se fija con un dominio base configurado.

## Aviso de evidencia documental

Cada criterio puede declarar qué documentos lo acreditan, en la tabla
`EvidenciaEsperada`. Es una tabla y no un campo porque la relación es de varios
a varios: el criterio del marcado CE pide la declaración del fabricante **y**
la fotografía de la placa, que son documentos de hechos distintos.

Al mostrar una evaluación se avisa de los criterios respondidos «Conforme»
cuyo documento no está en el sistema. **No es una no conformidad y no cambia el
dictamen**: el técnico puede haber comprobado el marcado con la placa delante y
responder «Conforme» con razón, y el RF-03 exige que el histórico no se
sobrescriba. Lo que evita es la falsa sensación de conformidad de quien lee el
dictamen y cierra la pantalla sin advertir que la evidencia no está.

Reglas:

- Solo mira las respuestas **«Conforme»**. Un «No aplica» significa que la
  disposición no rige para ese equipo —una máquina anterior al marcado CE no
  puede tener declaración— y un «No conforme» ya está señalado.
- Solo mira la **evaluación vigente**. Las anteriores son el registro de lo que
  se comprobó entonces y no describen el estado de hoy.
- Los documentos cuelgan del equipo, no de la evaluación: **una evaluación
  nueva no vuelve a pedir lo ya subido**.

Cómo se pinta: no se recolorea el dictamen con el naranja, que ya significa
«evaluación desfasada» y «tipos sin confirmar». En el listado, un dictamen
conforme con evidencia pendiente se muestra en gris con una marca propia al
lado, siguiendo el mismo criterio que las evaluaciones desfasadas: un
«conforme» en verde da por bueno el equipo de un vistazo, y esa seguridad
todavía no se ha ganado. No se usa el rojo, que significa incumplimiento.

Tampoco se depende del ratón: el atributo `title` no se muestra al tocar en una
pantalla táctil, y el escenario es el móvil en planta, así que la marca es
visible y enlazable por sí sola.

### Exenciones

`ExencionDocumental` declara que un tipo de documento no procede en un equipo,
con motivo obligatorio. Es la tercera salida al aviso, y cada una significa una
cosa distinta:

- Subir el documento: la evidencia existe y entra en el sistema.
- «No aplica» en el criterio: la disposición no rige para el equipo.
- La exención: la disposición rige y se cumple, pero la norma no exige
  documentarlo, o no de esta forma.

Solo alcanza a `IU`, `RC`, `RM` y `OT`, y la lista sale de la norma:

- `RM` no lo exige el RD 1215/1997.
- `RC` solo alcanza a los equipos del art. 4 —aquellos cuya seguridad dependa
  de las condiciones de instalación, o sometidos a deterioro—, no a todos: una
  llave dinamométrica no necesita comprobaciones periódicas.
- `IU` se sostiene en que el art. 5.2 pide la información «preferentemente por
  escrito»: preferentemente, no obligatoriamente. Eximirla significa que la
  información llega por otra vía.

Quedan fuera `MF` y `CE`, y es deliberado. La documentación del fabricante está
a disposición de los trabajadores por el art. 5.2: si no está, eso es una no
conformidad y hay que responderla como tal. Y una máquina anterior al marcado
CE no se resuelve eximiendo el documento, sino respondiendo «No aplica» al
criterio. Permitir eximirlos convertiría la exención en un botón para hacer
desaparecer incumplimientos.

El motivo es obligatorio por lo mismo: sin él, la exención sería un modo de
ocultar el aviso en vez de justificarlo. Las exenciones se ven en la ficha, no
desaparecen, para que puedan auditarse.

## Limitaciones conocidas

- **El aviso no mira fechas.** Comprueba que exista un documento del tipo
  esperado, no que siga vigente. Vale para los permanentes —manual, declaración
  CE— pero no para los periódicos: un registro de comprobación antiguo silencia
  el aviso indefinidamente. Resolverlo pide una fecha propia del documento,
  distinta de la de subida, y un periodo de validez por tipo.
- **Ningún criterio pregunta por el artículo 4**, las comprobaciones, ni por la
  información del art. 5.2 que redacta la empresa. De las cuatro obligaciones
  documentales del RD 1215/1997, el cuestionario cargado pregunta por dos. Los
  tipos documentales del modelo van por delante de la cobertura del
  cuestionario. Añadir criterios no es inocuo: el cuestionario crecería y las
  evaluaciones ya guardadas quedarían sin esas respuestas sin que nada las
  marque, porque `_marcar_desfasadas()` solo se dispara al cambiar los tipos de
  un equipo.
- **Al borrar un documento, Django borra la fila pero no el fichero del
  disco.** Dejó de hacerlo en la versión 1.3 para no destruir ficheros por
  accidente, de modo que quedan huérfanos en `media/`.
- **Documentación obligatoria fuera de alcance.** El Anexo II.4.3 exige nota de
  cálculo y plan de montaje, utilización y desmontaje para andamios. Quedan
  fuera: los andamios no están entre los tipos de equipo del prototipo y los
  criterios cargados son todos del Anexo I.

## Trabajo futuro

- **Evidencia enlazada a cada respuesta.** Hoy el aviso relaciona criterios con
  *tipos* de documento. Enlazar cada respuesta con el documento concreto que la
  acredita tocaría el formset de la evaluación, con subida por fila.
- **Vigencia de los documentos periódicos**, según la limitación de fechas.
- **Servir los ficheros con `X-Sendfile`** o equivalente en producción, en vez
  de entregarlos desde la vista.
- **Borrado del fichero en disco** al borrar su fila, mediante una señal.

## Nota sobre los datos de ejemplo

`app/media/` no se versiona, y `dumpdata` vuelca las filas pero no los
ficheros. Un clon que cargue el fixture vería documentos listados sin fichero
detrás. Los documentos de ejemplo, **sintéticos**, se versionan aparte en
`app/evaluaciones/fixtures/documentos_ejemplo/` y la guía de instalación indica
copiarlos a `app/media/documentos/`.
