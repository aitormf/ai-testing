# Revisión: spec de Fichero de configuración de la prueba

<!-- Escrita por review-spec. Es una recomendación: la aprobación la hace una persona cambiando status. -->

## Recomendación
**Devolver.** Un criterio de aceptación (CA-04) contradice la regla de Seguridad de no mostrar
valores en los errores, y el test no puede cumplir las dos cosas. Además hay varios huecos
importantes (glosario, origen de los valores de `agent`, formato de la ruta del campo) que
conviene cerrar antes de escribir el plan.

## Hallazgos

### Bloqueantes

1. **Criterios de aceptación (CA-04) y Casos límite, frente a Seguridad: ¿se muestra el valor del `id` duplicado?**
   - Qué falla: CA-04 pide que el error indique "el `id` duplicado", es decir, su valor.
     Seguridad dice que los mensajes indican la ruta de la clave, "**nunca su valor**". Los
     casos límite hablan en cambio de "los índices afectados". El test de CA-04 tiene que
     elegir una de las dos lecturas. Pasa lo mismo, de forma implícita, con CA-08
     (`agent = "gemini"`): no queda claro si el error puede repetir `gemini`.
   - Arreglo sugerido: elegir una regla y aplicarla en todas las secciones. Opción A:
     CA-04 dice "falla indicando las rutas de los agentes con el mismo `id` (p. ej.
     `agents[0].id` y `agents[2].id`)", sin el valor. Opción B: declarar en Seguridad una
     excepción explícita para valores que no pueden ser secretos (`id`, `agent`, `type`) y
     justificarla. Con cualquiera de las dos, CA-02 y CA-08 deben decir si el valor recibido
     aparece en el mensaje.
   - **Decisión:** Modificado. Solo rutas en todos los errores, nunca valores (RF-09, CA-02, CA-04, CA-08, Seguridad).

### Importantes

2. **Términos fuera del glosario y solapados con él (Objetivo, RF-02 a RF-05, Entidades).**
   - Qué falla: la spec usa "prueba", "tipo de prueba", "agente", "agente configurado" y
     "prompt efectivo", y ninguno está en el glosario de `docs/ARCHITECTURE.md` §8. Además se
     solapan con términos que sí están: "Tarea" (`domain.Task`, el trabajo que se lanza igual
     contra varios runners), "Runner" y "Comparación". `agent = "karajan"` es un runner según
     el glosario, no un agente. No queda claro si una "prueba" es la definición de una
     Comparación, si `type` + `prompt` forman una `Task`, ni si `agent` identifica un runner.
   - Arreglo sugerido: en Entidades, relacionar cada término con el glosario (p. ej.
     "`agent` = identificador de runner"; "`type` + prompt efectivo = `Task`") y decir qué
     términos nuevos se añaden al glosario en la misma PR. Fijar también el nombre en inglés
     para el código. Ojo: si se usa `Test…` (como el slug `test-config-file`), pytest
     intentará recoger como tests las clases `Test*`.
   - **Decisión:** Modificado. prueba=tarea y agente=runner; claves TOML `[[runners]]` y `runner`; "fichero de tarea" y "configuración de runner" se añaden al glosario (Entidades, RNF-06).

3. **RF-04: de dónde salen los valores permitidos de `agent` (P5).**
   - Qué falla: la spec fija la lista `claude`, `codex`, `opencode`, `karajan` como parte del
     esquema cerrado, pero no dice de dónde sale. Si el plan la pone en la validación con
     dataclasses de `domain`, añadir un runner (p. ej. Gemini CLI, que está en
     ARCHITECTURE §1 y CA-08 da por inválido) obligará a tocar `domain`, y eso choca con P5 y
     con ADR-0001. Además, hoy solo está previsto el runner de Karajan. Aceptar `codex` u
     `opencode` sin runner detrás es un supuesto que la spec no declara.
   - Arreglo sugerido: declarar que los valores permitidos de `agent` son los identificadores
     del registro de runners (`adapters/runners/`) o una lista que vive en `adapters`, y que
     añadir un valor no modifica `domain` ni `app`. Añadir a Supuestos que un valor puede ser
     válido aunque su runner todavía no exista, o bien limitar la lista a los runners
     registrados.
   - **Decisión:** Aplicado. Los valores salen del registro de runners (RF-12); se registran `claude`, `codex` y `opencode`; `karajan` queda fuera de alcance (CA-17).

4. **RF-07 y CA-07: formato de la ruta del campo sin definir.**
   - Qué falla: `agents[1].model` no aclara si el índice empieza en 0 o en 1. CA-07 usa
     `agents[i]` sin fijarlo. Tampoco se define la ruta de una clave desconocida
     (`agents[0].modle`, o `foo` en la raíz) ni el formato de cada línea de error. Así no se
     pueden escribir tests exactos para CA-07 ni CA-08.
   - Arreglo sugerido: fijar la base del índice (0, como en TOML y Python, o 1, más cercano
     a quien edita el fichero) y el formato de línea, p. ej. `<path>: <reason>`, con un
     ejemplo para un campo ausente, una clave desconocida y un tipo incorrecto.
   - **Decisión:** Modificado. Índices desde 0 y formato `<path>: <reason>`, con ejemplos (RF-08, RF-09).

5. **RF-09, RNF-04 y CA-11: no se dice dónde está la documentación ni cómo se extrae el ejemplo.**
   - Qué falla: "en `docs/`" no dice qué fichero es. RNF-04 exige que un test valide el
     ejemplo, pero no dice cómo se saca de un Markdown. Sin eso, CA-11 no se puede verificar
     de forma estable.
   - Arreglo sugerido: fijar la ruta (p. ej. `docs/test-config.md`) y una de dos: guardar el
     ejemplo en un `.toml` aparte (p. ej. `docs/examples/…toml`) enlazado desde el Markdown y
     validado por el test, o fijar una convención para el bloque de código que el test busca.
   - **Decisión:** Modificado. `docs/config_file.md` enlazado desde el README; el ejemplo va en un bloque `toml` del propio Markdown y el test lo extrae (RF-11, RNF-04, CA-18).

6. **RF-04 y Seguridad: el `id` es texto libre sin restricción de formato.**
   - Qué falla: el `id` es el identificador único del agente configurado. Es previsible que la
     spec de ejecución lo use para nombrar resultados o worktrees (ARCHITECTURE §6). Como
     texto libre admite `/`, `..`, saltos de línea o espacios. Endurecer el formato más
     adelante rompería ficheros que hoy se dan por válidos. Flexibilizarlo después no rompe
     nada.
   - Arreglo sugerido: fijar ya un formato (p. ej. `^[a-z0-9][a-z0-9_-]*$`) con su caso límite
     y su test negativo, o declarar como supuesto explícito que el `id` no se usará en rutas.
   - **Decisión:** Modificado. `id` solo con `a-z`, `0-9` y `-` (RF-04, CA-05).

7. **Objetivo y RNF-01, frente a ARCHITECTURE §10 y ADR-0002: hay dos "configuraciones TOML".**
   - Qué falla: según ARCHITECTURE §10, "la configuración la resuelve cyclopts (argumentos,
     variables de entorno y TOML) en `cli.py`", y ADR-0002 cita ese soporte como motivo. Esta
     spec añade un TOML distinto, leído con `tomllib` fuera de cyclopts. Sin aclararlo, se
     puede entender que contradice el documento o que hay que meterlo en la configuración de
     cyclopts.
   - Arreglo sugerido: decir en la spec que el fichero de prueba es un dato de entrada del
     comando y no configuración de la CLI. Indicar que ARCHITECTURE (§3 "¿Dónde va algo
     nuevo?", §8 y §10) se actualiza en la misma PR, como pide §12.
   - **Decisión:** Aplicado. El fichero es un dato de entrada, no configuración de cyclopts; ARCHITECTURE §3, §8 y §10 se actualizan en la misma PR (RNF-06).

8. **Requisitos y casos límite sin criterio de aceptación.**
   - Qué falla: no tienen CA estos puntos:
     - RF-06 para una clave desconocida en la raíz (CA-08 solo cubre el nivel de agente);
     - el valor por defecto de `local`;
     - "solo espacios se trata como ausente";
     - fichero vacío;
     - fichero no UTF-8 o binario;
     - `agents` como tabla;
     - `agents = []`;
     - salida estándar vacía en *todos* los fallos (solo CA-08 lo exige).

     Además, CA-05 dice "cuando se carga la configuración", pero `validate` solo imprime `OK`,
     así que no se ve desde la CLI qué prompt usa cada agente.
   - Arreglo sugerido: añadir un CA por cada punto. Generalizar en RF-07 que, ante cualquier
     fallo, la salida estándar queda vacía. Reformular CA-05 sobre lo que devuelve la carga
     (la API de carga, no la CLI).
   - **Decisión:** Modificado. CA nuevos: CA-09 a CA-14; stdout vacío en todo fallo (RF-08); campos con solo espacios = error (RF-07); se elimina el CA-05 anterior.

### Menores

9. **RF-07, RF-08 y CA-01: códigos de salida y salto de línea.** "Distinto de 0" vale para un
   `if`, pero no dice si todos los fallos usan el mismo código, ni qué pasa con los errores de
   uso de la CLI (falta `<file>`), que cyclopts gestiona con su propio código. "Exactamente
   `OK`" no aclara si lleva `\n` al final. Arreglo: fijar el código (p. ej. 1 para cualquier
   fichero inválido o ilegible) y que la salida es `OK\n`.
    - **Decisión:** Aplicado. `OK\n` y código 0; código 1 en cualquier fallo (RF-08, RF-10, CA-01).

10. **RF-07: orden de los errores.** Si no se fija el orden, los tests y la salida pueden no
    ser deterministas. Arreglo: errores en el orden del fichero, o por ruta.
    - **Decisión:** Aplicado. Orden en que aparecen en el fichero (RF-08).

11. **Entidades: `local` no tiene significado definido.** Solo se dice que es un booleano.
    Arreglo: una frase sobre qué significa (p. ej. "el modelo se sirve en local") aunque hoy no
    tenga efecto.
    - **Decisión:** Aplicado. `local = true` significa que el modelo es local (RF-04).

12. **RF-04 y Casos límite: la unicidad del `id` está poco definida.** No se dice si
    distingue mayúsculas ni si se compara tras quitar espacios. Arreglo: fijarlo (se resuelve
    solo si se adopta el formato del hallazgo 6).
    - **Decisión:** Resuelto por el hallazgo 6 (solo minúsculas). El error se marca en la segunda aparición (CA-04).

13. **RF-05 y Casos límite: el prompt efectivo con espacios.** No se dice si un `prompt` de
    agente con solo espacios cede al común (se deduce de "se trata como ausente", pero no se
    afirma), ni si el prompt efectivo se guarda recortado. Arreglo: decirlo de forma explícita.
    - **Decisión:** Modificado. Un prompt con solo espacios es un error y no cede al común (RF-07).

14. **Casos límite: "sin traza" solo aparece para algunos errores.** Falta el caso de una
    ruta que es un directorio o de un fichero sin permisos de lectura. Arreglo: un caso límite
    general: "ningún error muestra una traza de Python", y añadir el caso del directorio.
    - **Decisión:** Aplicado. RNF-05; casos de directorio y de fichero sin permiso de lectura (Casos límite, CA-16).

15. **Frontmatter: `issue:` está vacío.** Arreglo: enlazar el issue o quitar el campo.
    - **Decisión:** Aplicado. Se quita el campo `issue:`.

## Principios y ADRs
- **P5 / ADR-0001:** riesgo de choque según dónde viva la lista de valores de `agent`
  (hallazgo 3). La spec no lo incumple directamente, pero debe fijar el origen para que el plan
  no lo meta en `domain`.
- **P1 / P3:** leer el fichero es E/S y tiene que ir en `adapters`. En `domain` solo cabe
  validar los datos ya parseados. La spec es compatible; el plan debe respetarlo.
- **P4 / ADR-0002:** `cli.py` fino. Dar formato a los errores y escribir `OK` o los mensajes
  en stderr no debería ser lógica de `cli.py`. Es cosa del plan.
- **ARCHITECTURE §10 / ADR-0002:** posible contradicción sobre quién resuelve la
  configuración TOML (hallazgo 7).
- **P8 / ADR-0004:** `tomllib` y `dataclasses` son stdlib, así que no hay dependencias
  nuevas. Correcto.
- **ADR-0005:** no le afecta. RNF-02 excluye crear worktrees.

## Preguntas
<!-- Decisiones (apply-review): 1 → solo rutas; índices → desde 0; codex y opencode → se aceptan y se registran; karajan con un único `model` → **aplazado**: Karajan y las secciones de configuración propias de cada runner irán en otra spec. -->
- ¿Se pueden mostrar en los errores valores como `id`, `agent` o `type`, o la regla "nunca
  su valor" es absoluta? (hallazgo 1)
- ¿Los índices de la ruta empiezan en 0 o en 1? (hallazgo 4)
- ¿Encaja `model` obligatorio y único con `agent = "karajan"`? Karajan orquesta varios roles
  y agentes, así que un solo `model` puede no tener sentido para él.
- ¿Se deben aceptar `codex` y `opencode` antes de que existan sus runners? (hallazgo 3)

## Riesgos
- `pyproject.toml` tiene `dependencies = []`, pero el subcomando `validate` necesita cyclopts
  (aceptado en ADR-0002 y ADR-0004, aún sin instalar). Es cosa del plan: añadirlo con
  `uv add`, sin ADR nuevo.
- `tomllib` lanza `UnicodeDecodeError` (no `TOMLDecodeError`) con ficheros que no son
  UTF-8. Si el plan solo captura el segundo, el caso del binario saldría con traza.
- Con el esquema cerrado (RF-06), la spec de ejecución tendrá que ampliar el esquema y
  su documentación. Es lo esperado, pero conviene que esa spec lo diga.
