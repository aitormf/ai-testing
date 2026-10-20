---
status: aprobada
---

# Fichero de configuración de la tarea

## Objetivo
Describir una tarea (qué tipo de trabajo es y con qué runners y configuración se lanza) en un
fichero TOML que la CLI lee y valida, con un esquema documentado.

## Problema que resuelve
Hoy no hay forma de declarar una tarea: el tipo de trabajo, los runners que participan, el modelo
de cada uno y el prompt tendrían que pasarse a mano por argumentos, cosa que no escala con varios
runners ni se puede guardar, versionar o repetir.

## Usuarios
- **Quien compara runners**: desarrollador/a que lanza la CLI en local, cómodo con TOML y con las
  CLIs de los agentes. Escribe y reutiliza ficheros de tarea, a mano o desde scripts de shell.

## User stories
- Como persona que compara runners, quiero describir una tarea en un fichero para poder
  repetirla y versionarla.
- Como persona que compara runners, quiero incluir el mismo runner varias veces con distinto
  modelo para comparar modelos con la misma herramienta.
- Como persona que compara runners, quiero validar el fichero antes de lanzar nada para detectar
  erratas sin gastar tiempo ni tokens.
- Como persona que automatiza, quiero que la validación se pueda usar en un `if` de shell para
  encadenarla con otros pasos.
- Como persona que escribe un fichero nuevo, quiero un esquema documentado con ejemplo para no
  tener que leer el código.

## Requisitos funcionales
- RF-01: La CLI ofrece el comando `ia-testing validate <file>`, que valida un fichero de tarea en TOML.
- RF-02: El fichero declara un único tipo de tarea (`type`) para todos los runners. Valores
  aceptados: `code-generation`, `code-review`. Cualquier otro valor es un error.
- RF-03: El fichero declara una lista de configuraciones de runner (`[[runners]]`) con al menos
  un elemento.
- RF-04: Cada configuración de runner tiene:
  - `id` (obligatorio, único en el fichero; solo letras minúsculas `a-z`, dígitos `0-9` y `-`);
  - `runner` (obligatorio; uno de los runners del registro de runners: en esta entrega
    `claude`, `codex` y `opencode`);
  - `model` (texto, obligatorio);
  - `local` (booleano, opcional, por defecto `false`; `true` indica que el modelo es local);
  - `prompt` (texto, opcional).
- RF-05: El fichero puede declarar un `prompt` común a nivel de tarea. El `prompt` de una
  configuración de runner, si existe, sustituye al común. Cada configuración de runner debe
  acabar con un prompt efectivo.
- RF-06: Cualquier clave no definida en el esquema, a cualquier nivel, es un error.
- RF-07: Un campo de texto vacío o con solo espacios (`id`, `model`, `prompt`, el `prompt`
  común) es un error; no se trata como ausente ni cede al prompt común.
- RF-08: Si el fichero no es válido o no se puede leer, el comando:
  - escribe **todos** los errores en la salida de error (stderr), uno por línea, con el formato
    `<path>: <reason>`, en el orden en que aparecen en el fichero;
  - deja vacía la salida estándar;
  - termina con código de salida 1.
- RF-09: La ruta del campo usa índices desde 0 para la lista de runners. Ejemplos:
  - campo ausente: `runners[1].model: missing required field`;
  - clave desconocida: `runners[0].modle: unknown key`, `foo: unknown key`;
  - tipo incorrecto: `runners[2].local: expected a boolean`.

  Los mensajes muestran la ruta y el motivo, **nunca el valor** recibido.
- RF-10: Si el fichero es válido, el comando escribe `OK` seguido de salto de línea en la salida
  estándar, deja vacía stderr y termina con código de salida 0.
- RF-11: El esquema se documenta en `docs/config_file.md`, enlazado desde el `README.md`: cada
  campo con su tipo, obligatoriedad, valor por defecto y valores permitidos, el formato de los
  errores y un fichero de ejemplo completo y válido en un bloque de código `toml`.
- RF-12: Los valores permitidos de `runner` salen del registro de runners. Añadir un runner al
  registro lo hace válido en el fichero sin modificar `domain` ni `app` (P5).

## Requisitos no funcionales
- RNF-01: Sin dependencias nuevas para leer el fichero: se usa `tomllib` de la stdlib.
- RNF-02: Leer y validar el fichero no ejecuta ningún runner ni herramienta externa, ni crea worktrees.
- RNF-03: Textos de la CLI y mensajes de error en inglés.
- RNF-04: Un test valida el ejemplo de `docs/config_file.md`, para que la documentación no se
  quede desfasada respecto al código.
- RNF-05: Ningún error muestra una traza de Python.
- RNF-06: El fichero de tarea es un dato de entrada del comando `validate`, no configuración de
  la CLI: no lo resuelve cyclopts. `docs/ARCHITECTURE.md` (§3, §8 y §10) se actualiza en la
  misma PR para reflejarlo y para añadir al glosario "fichero de tarea" y "configuración de runner".

## Casos límite
- El fichero no existe, es un directorio o no tiene permiso de lectura → error con la ruta del
  fichero y código 1.
- TOML mal formado → error con la línea y la columna que da el parser; no se intenta validar el esquema.
- El fichero no está en UTF-8 o es binario → error.
- Fichero vacío → error (faltan `type` y `runners`).
- `runners` ausente, vacío (`runners = []`) o definido como tabla en vez de lista → error.
- `id` duplicado → un error por cada configuración repetida, con su ruta (p. ej. `runners[2].id`).
- `id` con mayúsculas, espacios, `_`, `/` o `.` → error.
- Campo de texto vacío o con solo espacios → error (RF-07).
- Tipo incorrecto (`local = "yes"`) → error con la ruta.
- Ningún prompt efectivo (sin prompt común ni propio) → error en esa configuración de runner.
- `runner = "karajan"` u otro valor fuera del registro → error.
- `local = true` → válido. Esta entrega no comprueba que el modelo esté disponible.

## Criterios de aceptación
Salvo que se diga otra cosa, "falla" significa: código de salida 1, salida estándar vacía y los
errores indicados en stderr con el formato `<path>: <reason>`, sin el valor recibido y sin traza.

- CA-01: Dado un fichero válido con `type = "code-generation"` y dos configuraciones de runner,
  cuando ejecuto `ia-testing validate <file>`, entonces la salida estándar es `OK\n`, stderr
  está vacío y el código de salida es 0.
- CA-02: Dado un fichero con `type = "benchmark"`, cuando lo valido, entonces falla con un error
  en `type` que lista los valores permitidos y no contiene `benchmark`.
- CA-03: Dado un fichero con dos configuraciones `runner = "claude"` con distinto `id` y
  distinto `model`, cuando lo valido, entonces es válido.
- CA-04: Dado un fichero en el que `runners[0]` y `runners[2]` tienen el mismo `id`, cuando lo
  valido, entonces falla con un error en `runners[2].id` que no contiene el valor del `id`.
- CA-05: Dado un `id` con mayúsculas o con `_`, cuando lo valido, entonces falla en `runners[i].id`.
- CA-06: Dada una configuración de runner sin prompt propio y un fichero sin prompt común,
  cuando lo valido, entonces falla en esa configuración.
- CA-07: Dada una configuración de runner sin `model`, cuando lo valido, entonces falla con
  `runners[i].model: missing required field`.
- CA-08: Dado un fichero con `modle = "x"` en `runners[0]` y `runner = "gemini"` en `runners[1]`,
  cuando lo valido, entonces falla con los dos errores, en ese orden, y ninguno contiene `x` ni `gemini`.
- CA-09: Dado un fichero con una clave desconocida en la raíz, cuando lo valido, entonces falla
  con `<clave>: unknown key`.
- CA-10: Dada una configuración de runner sin `local`, cuando se carga el fichero, entonces
  `local` vale `false`.
- CA-11: Dado un `model` o un `prompt` con solo espacios, cuando lo valido, entonces falla en
  ese campo.
- CA-12: Dado un fichero vacío, cuando lo valido, entonces falla con errores en `type` y en `runners`.
- CA-13: Dado un fichero binario o que no está en UTF-8, cuando lo valido, entonces falla.
- CA-14: Dado `runners = []` o `runners` definido como tabla, cuando lo valido, entonces falla en `runners`.
- CA-15: Dado un TOML mal formado, cuando lo valido, entonces falla con la línea del error.
- CA-16: Dada una ruta que no existe o que es un directorio, cuando la valido, entonces falla
  con un mensaje que incluye la ruta del fichero.
- CA-17: Dada una configuración con `runner = "karajan"`, cuando lo valido, entonces falla en
  `runners[i].runner`.
- CA-18: El ejemplo de `docs/config_file.md` pasa la validación.

## Alcance
- Formato del fichero de tarea, carga, validación y comando `validate`.
- Registro de los runners `claude`, `codex` y `opencode`, aunque todavía no ejecuten nada.
- Documentación del esquema en `docs/config_file.md`, enlazada desde el `README.md`.
- Actualización de `docs/ARCHITECTURE.md` (RNF-06).

## Fuera de alcance
- Ejecutar runners con esta configuración (otra spec).
- El runner `karajan` y las secciones de configuración propias de cada runner (pensadas sobre
  todo para Karajan, que orquesta varios agentes): irán en otra spec.
- Opciones propias de cada herramienta (flags, parámetros extra).
- Datos de conexión de modelos locales (endpoint, proveedor): `local` es solo un booleano.
- Comprobar que la herramienta o el modelo existen en el sistema.
- Otros tipos de tarea aparte de `code-generation` y `code-review`.
- `prompt_file` o prompts en ficheros externos.
- Generar un JSON Schema.
- Mostrar un resumen de la configuración cuando es válida.

## Entidades / Modelo de datos
Relación con el glosario de `docs/ARCHITECTURE.md`:

- **Fichero de tarea** (término nuevo): fichero TOML que describe una tarea y los runners con
  los que se lanza. Contiene `type`, un `prompt` común opcional y la lista `runners`.
- **Tarea** (`domain.Task`): `type` y el prompt efectivo. El prompt puede ajustarse en cada
  configuración de runner.
- **Runner**: el valor de `runner` identifica un runner del registro.
- **Configuración de runner** (término nuevo): cada elemento de `[[runners]]`: `id`, `runner`,
  `model`, `local` y `prompt` opcional. Su *prompt efectivo* es el propio o, si no tiene, el común.

## Supuestos
- Un fichero describe una sola tarea.
- Los valores de `model` son texto libre: cada herramienta usa sus propios nombres.
- `claude`, `codex` y `opencode` tienen una configuración lo bastante homogénea para compartir
  los mismos campos.
- Un runner puede estar en el registro, y ser válido en el fichero, antes de saber ejecutar tareas.

## Riesgos
- El glosario define la tarea como el trabajo que se lanza "igual" contra varios runners. El
  prompt por configuración de runner lo matiza, y la definición debe actualizarse (RNF-06).
- Con el esquema cerrado (RF-06), la spec de ejecución y la de Karajan tendrán que ampliar el
  esquema y su documentación.

## Seguridad
- Datos que maneja y su sensibilidad: el fichero lo escribe la propia persona y contiene prompts
  y nombres de modelo. No debe contener credenciales.
- Quién puede hacer qué: no aplica (herramienta local de un solo usuario).
- Entradas no fiables y cómo se validan: el fichero TOML. Se valida contra un esquema cerrado (las
  claves desconocidas son error, así que `api_key` o `token` se rechazan) y no se interpreta
  como código. El `id` tiene un formato restringido, por si más adelante se usa en rutas.
- Los mensajes de error indican la ruta del campo, pero **nunca su valor**, para no mostrar un
  secreto que alguien haya pegado por error.
- Tests negativos requeridos: clave `api_key` en una configuración de runner → error sin mostrar
  su valor; TOML mal formado; fichero binario; tipos incorrectos; `runner` fuera del registro;
  `id` con `/` o `..`.
