# Fichero de tarea

Un fichero de tarea es un fichero [TOML](https://toml.io) que describe una tarea (qué tipo de
trabajo es) y los runners con los que se lanza, cada uno con su modelo. Se valida con:

```
ia-testing validate <fichero>
```

Validar no ejecuta ningún runner ni herramienta externa, ni crea worktrees.

## Esquema

El esquema es cerrado: cualquier clave que no figure en las tablas siguientes es un error, a
cualquier nivel. Los campos de texto no pueden estar vacíos ni contener solo espacios.

### Nivel de tarea

| Campo | Tipo | Obligatorio | Por defecto | Valores permitidos |
|---|---|---|---|---|
| `type` | texto | sí | - | `code-generation`, `code-review` |
| `prompt` | texto | no | - | Cualquier texto no vacío. Es el prompt común: lo usan las configuraciones de runner que no definen el suyo |
| `runners` | lista de tablas (`[[runners]]`) | sí | - | Al menos un elemento |

### Configuración de runner (`[[runners]]`)

| Campo | Tipo | Obligatorio | Por defecto | Valores permitidos |
|---|---|---|---|---|
| `id` | texto | sí | - | Único en el fichero. Solo letras minúsculas `a-z`, dígitos `0-9` y `-` |
| `runner` | texto | sí | - | `claude`, `codex`, `opencode` (los del registro de runners) |
| `model` | texto | sí | - | Texto libre: cada herramienta usa sus propios nombres de modelo |
| `local` | booleano | no | `false` | `true` indica que el modelo es local. No se comprueba que esté disponible |
| `prompt` | texto | no | - | Cualquier texto no vacío. Sustituye al prompt común |

Cada configuración de runner debe acabar con un prompt efectivo: el propio o, si no tiene, el
común. Si no hay ninguno de los dos, es un error. Se puede repetir el mismo `runner` varias veces
con distinto `id` y `model` para comparar modelos con la misma herramienta.

El fichero debe estar en UTF-8. Se acepta que empiece con una marca de orden de bytes (BOM).

No pongas credenciales en el fichero: cualquier clave desconocida (como `api_key` o `token`) se
rechaza.

## Ejemplo completo y válido

```toml
type = "code-generation"
prompt = "Implement a function that parses ISO 8601 dates and add tests for it."

[[runners]]
id = "claude-sonnet"
runner = "claude"
model = "sonnet"

[[runners]]
id = "claude-opus"
runner = "claude"
model = "opus"
prompt = "Implement a date parser (ISO 8601) with tests, and explain the edge cases you cover."

[[runners]]
id = "opencode-local"
runner = "opencode"
model = "qwen2.5-coder"
local = true
```

## Salida de `validate`

Si el fichero es válido, escribe `OK` en la salida estándar y termina con código 0:

```text
OK
```

Si no lo es, escribe **todos** los errores en la salida de error, uno por línea, con el formato
`<ruta>: <motivo>`, en el orden en que aparecen en el fichero, deja vacía la salida estándar y
termina con código 1. La salida estándar vacía y el código de salida permiten usar el comando en
un `if` de shell.

La ruta del campo usa índices desde 0 para la lista de runners. Los mensajes indican la ruta y el
motivo, **nunca el valor** recibido, para no mostrar un secreto pegado por error. Si el fichero no
se puede leer o no es TOML válido, la ruta es la del fichero tal como se pasó al comando.

Ejemplos:

```text
type: unknown type: expected one of code-generation, code-review
runners[0].modle: unknown key
runners[1].model: missing required field
runners[1].runner: unknown runner: expected one of claude, codex, opencode
runners[2].local: expected a boolean
runners[2].id: duplicate id
runners[3].prompt: missing prompt: set it here or at the top level
foo: unknown key
```

Errores al leer el fichero:

```text
task.toml: file not found
task.toml: is a directory
task.toml: permission denied
task.toml: cannot read file
task.toml: not valid UTF-8
task.toml: invalid TOML at line 3, column 10
```

Si el TOML está mal formado, se informa de la línea y la columna y no se valida el esquema.
