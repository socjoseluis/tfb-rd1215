# Diseño del RF-06: medidas correctivas

Decisiones tomadas el 17/08/2026, antes de escribir nada de código. Notas
técnicas en crudo: la redacción de la memoria se hace aparte.

## De qué cuelga una medida

Una medida correctiva **pertenece a una evaluación** y ataca **una o varias no
conformidades de esa misma evaluación**.

- `evaluacion`: clave ajena a `Evaluacion`. Es la frontera del problema.
- `no_conformidades`: relación de muchos a muchos con `Respuesta`, limitada a
  las respuestas con `resultado='NC'` de esa evaluación.

**Por qué las dos cosas y no solo la relación múltiple:** un muchos a muchos
suelto dejaría enganchar no conformidades de equipos o de fechas distintas, y
una medida no puede estar «realizada» para un equipo y «pendiente» para otro.
Además, una relación múltiple admite quedarse vacía, y la clave ajena garantiza
que ninguna medida quede colgando de nada.

**Fuera de alcance, a trabajo futuro:** una misma medida que cubra varios
equipos a la vez (por ejemplo, la misma seta de emergencia en tres prensas).

## Campos

| Campo | Tipo | Notas |
| --- | --- | --- |
| `evaluacion` | FK a `Evaluacion` | La evaluación de la que nace |
| `no_conformidades` | M2M a `Respuesta` | Solo las `NC` de esa evaluación |
| `descripcion` | texto | Qué se va a hacer |
| `fecha_prevista` | fecha, opcional | Cuándo debería estar hecha |
| `estado` | P / EC / R / D | Pendiente, En curso, Realizada, Descartada |
| `fecha_cierre` | fecha, opcional | Se rellena al pasar a Realizada |

«Descartada» existe para la medida que se propone y luego se desestima (por
ejemplo, porque se sustituye el equipo): borrarla perdería el rastro de lo que
se decidió.

## Lo que NO lleva

- **Responsable de la medida.** Sería un dato personal, y el Capítulo 3 declara
  la gestión de personas fuera de alcance por el RGPD.
- **Efecto sobre el dictamen.** Cerrar una medida no cambia el dictamen de la
  evaluación: el RF-03 exige que el histórico no se sobrescriba. La conformidad
  se recupera evaluando de nuevo, y la medida cerrada queda como el rastro de
  por qué cambió.

## Pantallas

1. **Alta de la medida desde la evaluación**: formulario con las no
   conformidades de esa evaluación en casillas.
2. **Las medidas visibles dentro de la evaluación** que las originó.
3. **Listado propio de seguimiento**, transversal a todos los equipos, con
   filtro por estado. Es lo que da sentido a la palabra «seguimiento» del RF-06
   y lo que se llevará una captura a la memoria.

Todo ello para usuario autenticado: el alta y el cierre de medidas no son
acciones anónimas.
