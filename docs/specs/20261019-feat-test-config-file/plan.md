---
status: aprobada
---

# Plan: Fichero de configuración de la tarea

## Objetivo técnico
Una función pura en `domain` que convierte el contenido ya parseado de un fichero de tarea en un
`TaskFile` o en una lista de errores con ruta; un adapter que lee el TOML sin lanzar excepciones
de E/S; un caso de uso en `app` que los une; y el comando `ia-testing validate <file>` con
cyclopts, que escribe `OK` o los errores y devuelve el código de salida.

## Arquitectura propuesta

```
cli.validate(file)
  ├─ monta TomlTaskFileSource(file)          (adapters/task_file.py)
  ├─ app.validate_task_file(source, RUNNER_NAMES)
  │     ├─ source.read() → Mapping           (o InvalidTaskFile con el error del fichero)
  │     └─ domain.parse_task_file(data, runner_names) → TaskFile | InvalidTaskFile
  └─ report.print_validation(errors) → exit code   (adapters/report/validation.py)
```

- `domain` valida datos ya parseados, sin E/S (P1). Los nombres de runner válidos le llegan
  como parámetro, así que no conoce el registro (P5, RF-12).
- La lectura del fichero y `tomllib` viven en `adapters` (P3, RNF-06): no es configuración de
  cyclopts, solo un argumento `Path`.
- Elementos nuevos en el mapa del código: `domain/task_file.py`, `adapters/task_file.py`,
  `adapters/runners/registry.py` y `adapters/report/validation.py`. Los tres últimos encajan en
  carpetas que ya prevé ARCHITECTURE §3; `adapters/task_file.py` no, así que se añade su fila al
  mapa de §3 (ver Componentes). No hay capas nuevas.
- No se crea `domain.Task` todavía: la validación no la necesita. La spec de ejecución
  construirá cada `Task` a partir de `TaskFile.type` y del prompt efectivo de cada `RunnerConfig`.

## Componentes y responsabilidades

| Fichero | Responsabilidad | PR |
|---|---|---|
| `src/ia_testing/domain/task_file.py` | `TaskType`, `RunnerConfig`, `TaskFile`, `FieldError`, `InvalidTaskFile`, `TaskFileSource` (Protocol) y `parse_task_file()` | 1 |
| `src/ia_testing/adapters/runners/registry.py` | `RUNNER_NAMES = ("claude", "codex", "opencode")`: el registro explícito (ARCHITECTURE §6). Más adelante pasará a asociar cada nombre con su implementación | 1 |
| `src/ia_testing/adapters/task_file.py` | `TomlTaskFileSource(path)`: lee los bytes, los decodifica en UTF-8 y aplica `tomllib.loads`; convierte `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, cualquier otro `OSError` (último recurso), `UnicodeDecodeError` y `TOMLDecodeError` en `InvalidTaskFile`. Nunca interpola `strerror` ni el texto de la excepción | 2 |
| `src/ia_testing/app/task_file.py` | `validate_task_file(source, runner_names) -> tuple[FieldError, ...]` (vacía si el fichero es válido) | 2 |
| `src/ia_testing/adapters/report/validation.py` | `print_validation(errors, out, err) -> int`: escribe `OK\n` o una línea `<path>: <reason>` por error; devuelve 0 o 1 | 2 |
| `src/ia_testing/cli.py` | App cyclopts creada con `App(result_action="return_value")` (variable `cli_app`, para no confundirla con el paquete `app`), con el comando `validate(file: Path) -> int`, que pasa `sys.stdout`/`sys.stderr` a `print_validation` en el momento de la llamada; y `main()`, que hace `sys.exit(cli_app())` | 2 |
| `docs/config_file.md` + `README.md` | Esquema, tabla de campos, formato de errores y un ejemplo en un bloque `toml` | 2 |
| `docs/ARCHITECTURE.md` | §3: `domain/task_file.py` y el Protocol `TaskFileSource` en la fila de `domain`; el registro (`adapters/runners/registry.py`) en la fila de `runners/`. Va en la misma PR que los introduce (§12) | 1 |
| `docs/ARCHITECTURE.md` | §3: fila nueva para `adapters/task_file.py` (lectura del fichero de tarea) y `validation.py` en la fila de `report/`; §8 (glosario: fichero de tarea, configuración de runner, matiz de Tarea); §10 (el fichero de tarea no es configuración de cyclopts) | 2 |
| `pyproject.toml` / `uv.lock` | `uv add "cyclopts>=4,<5"` | 2 |

## Modelo de datos mínimo

```python
class TaskType(StrEnum):
    CODE_GENERATION = "code-generation"
    CODE_REVIEW = "code-review"


@dataclass(frozen=True)
class RunnerConfig:
    id: str
    runner: str
    model: str
    local: bool
    prompt: str  # prompt efectivo


@dataclass(frozen=True)
class TaskFile:
    type: TaskType
    runners: tuple[RunnerConfig, ...]


@dataclass(frozen=True)
class FieldError:
    path: str
    reason: str  # __str__ → "<path>: <reason>"


class InvalidTaskFile(Exception):
    errors: tuple[FieldError, ...]
```

- `runner` es un `str` validado contra `runner_names`, no un enum, para que `domain` no cambie
  al añadir un runner (P5).
- `RunnerConfig.prompt` guarda directamente el prompt efectivo. Para la validación no hace
  falta distinguir entre prompt propio y común.

## Contratos

```python
def parse_task_file(data: Mapping[str, object], runner_names: Collection[str]) -> TaskFile
    # lanza InvalidTaskFile con TODOS los errores

class TaskFileSource(Protocol):
    def read(self) -> Mapping[str, object]   # lanza InvalidTaskFile si no se puede leer o parsear

def validate_task_file(source: TaskFileSource, runner_names: Collection[str]) -> tuple[FieldError, ...]
```

CLI: `ia-testing validate <file>` → stdout `OK\n` y exit 0, o stderr `<path>: <reason>` (una
línea por error) y exit 1.

**Reglas de validación** (en `parse_task_file`):

- **Orden de los errores:** dentro de cada tabla, primero las claves presentes en el orden del
  documento (`tomllib` conserva el orden de inserción) y después los campos obligatorios que
  faltan, en el orden del esquema.
- **Ruta:** índices desde 0. Para los errores del fichero, la ruta tal como se pasó en la CLI.
- **`id`:** `re.fullmatch(r"[a-z0-9-]+", id)`. Se usa `fullmatch` para que no se cuele un `\n`
  final. El duplicado se marca en la segunda aparición y en las siguientes.
- **Texto:** `isinstance(v, str)` y `v.strip() != ""`. Si no se cumple, `must not be empty` (RF-07).
- **Prompt efectivo:** si un runner no tiene prompt propio y no hay prompt común, el error va
  en `runners[i].prompt` (`missing prompt`). Si el prompt común está vacío o tiene solo
  espacios, da un único error `prompt: must not be empty`, como cualquier otro campo vacío, y
  no se añade un `missing prompt` por cada runner sin prompt propio.
- **Mensajes:** nunca interpolan un valor recibido. Solo usan rutas, tipos esperados y los
  valores permitidos del esquema.

| Situación | `reason` |
|---|---|
| Falta un campo obligatorio | `missing required field` |
| Clave fuera del esquema | `unknown key` |
| Tipo incorrecto | `expected a string` / `expected a boolean` / `expected an array of tables` |
| Texto vacío o con solo espacios | `must not be empty` |
| `runners = []` | `must contain at least one runner` |
| `id` con formato no válido | `invalid id: use only lowercase letters, digits and '-'` |
| `id` repetido | `duplicate id` |
| `runner` fuera del registro | `unknown runner: expected one of claude, codex, opencode` |
| `type` no válido | `unknown type: expected one of code-generation, code-review` |
| Sin prompt efectivo | `missing prompt: set it here or at the top level` |
| No existe / es un directorio / sin permiso | `file not found` / `is a directory` / `permission denied` |
| Otro `OSError` (p. ej. `NotADirectoryError`, `ENAMETOOLONG`) | `cannot read file` |
| No es UTF-8 | `not valid UTF-8` |
| TOML mal formado | `invalid TOML at line N, column M` (o `invalid TOML` si no se pueden extraer) |

## Comprobación de principios

| Principio | ¿Se cumple? | Nota |
|---|---|---|
| P1 `domain` puro | Sí | `task_file.py` solo usa `dataclasses`, `enum`, `re` y `typing`; la E/S está en el adapter |
| P2 dirección de dependencias | Sí | cli → adapters (source, registry, report) → app → domain. Lo comprueba import-linter |
| P3 `subprocess` solo en adapters | No aplica | No hay `subprocess`; `tomllib` y la lectura del fichero también están en `adapters` |
| P4 `cli.py` fino | Sí | `validate` monta el source, llama a `app` y pasa el resultado a `report`, sin `if` ni `try` |
| P5 runner nuevo sin tocar domain/app | Sí | `runner_names` se inyecta desde `adapters/runners/registry.py`; un test lo comprueba con un nombre inventado |
| P6 tests sin herramientas externas | Sí | No hay runners reales; ficheros reales en `tmp_path` y sin parchear nada |
| P7 test primero | Sí | Cada tarea empieza por su test en rojo |
| P8 sin dependencias nuevas sin ADR | Sí | cyclopts ya está aceptado en ADR-0002 y ADR-0004, y su instalación está aprobada por @aitormf (2026-10-19); `tomllib` es stdlib |

AGENTS.md: se añade un Protocol nuevo a `domain` (`TaskFileSource`), aprobado por @aitormf
(2026-10-19). Los Protocols que ya existen no cambian. El test del saludo de `tests/test_cli.py`
se sustituye por los tests del comando `validate`, también con aprobación (era un marcador de posición).

## Pruebas

| Criterio | Test | Nivel |
|---|---|---|
| CA-01 | `test_cli.py::test_validate_valid_file_prints_ok` (stdout `OK\n`, stderr vacío, exit 0) | CLI |
| CA-02 | `test_task_file.py::test_unknown_type_lists_allowed_without_value` | domain |
| CA-03 | `test_task_file.py::test_same_runner_twice_with_distinct_ids_is_valid` | domain |
| CA-04 | `test_task_file.py::test_duplicate_id_reported_on_later_entry_without_value` | domain |
| CA-05 | `test_task_file.py::test_invalid_id_format` (parametrizado: mayúsculas, `_`, espacio, `/`, `..`, `\n` final) | domain |
| CA-06 | `test_task_file.py::test_missing_effective_prompt` | domain |
| CA-07 | `test_task_file.py::test_missing_model` | domain |
| CA-08 | `test_cli.py::test_validate_invalid_file_reports_all_errors_in_order` (stdout vacío, exit 1, sin `x` ni `gemini`) | CLI |
| CA-09 | `test_task_file.py::test_unknown_root_key` | domain |
| CA-10 | `test_task_file.py::test_local_defaults_to_false` | domain |
| CA-11 | `test_task_file.py::test_blank_text_fields_are_errors` (parametrizado: `model`, `prompt` propio y común, `id`; con el común en blanco, el único error es `prompt: must not be empty`) | domain |
| CA-12 | `test_task_file.py::test_empty_document_reports_type_and_runners` + `test_toml_source.py::test_empty_file` | domain + adapter |
| CA-13 | `test_toml_source.py::test_binary_file`: fichero binario de 20 KB con bytes fijos (`bytes(range(256)) * 80`, 20 480 bytes, no es UTF-8 válido) → `not valid UTF-8` | adapter (`tmp_path`) |
| CA-14 | `test_task_file.py::test_runners_empty_or_table` (parametrizado) | domain |
| CA-15 | `test_toml_source.py::test_malformed_toml_reports_line` (comprueba la línea concreta, p. ej. `line 3, column 5`) | adapter |
| CA-16 | `test_toml_source.py::test_missing_file`, `test_directory`, `test_unreadable_file` (`skipif` como root), `test_not_a_directory` (`cannot read file`) | adapter |
| CA-13, CA-15, CA-16 de extremo a extremo | `test_cli.py::test_validate_unreadable_or_malformed_file_fails` (parametrizado: inexistente, directorio, binario, TOML mal formado): exit 1, stdout vacío, stderr empieza por la ruta del fichero y no contiene `Traceback` | CLI |
| `app` | `test_app_task_file.py::test_validate_task_file_returns_errors_or_empty` con el `TomlTaskFileSource` real en `tmp_path` (sin dobles: AGENTS.md solo permite el runner falso) | app + adapter |
| CA-17 | `test_task_file.py::test_karajan_is_not_a_known_runner` (con `RUNNER_NAMES` real) | domain + registro |
| CA-18 | `test_docs.py::test_config_file_example_is_valid`: extrae el primer bloque `toml` de `docs/config_file.md` y pasa `validate_task_file` con el source real | adapter + app |
| RF-05 (prompt propio sustituye al común) | `test_task_file.py::test_own_prompt_overrides_common` | domain |
| RF-12 / P5 | `test_task_file.py::test_runner_names_are_injected` (acepta un nombre inventado) + `test_registry.py::test_registered_runners` | domain |
| RNF-05 sin traza | Los tests de CLI (CA-01, CA-08 y el parametrizado de errores de fichero) comprueban que stderr no contiene `Traceback` | CLI |
| Seguridad: `api_key` | `test_task_file.py::test_credential_key_rejected_without_value` (y en el CLI, el valor no aparece en stderr) | domain + CLI |
| Seguridad: TOML mal formado con un secreto | `test_toml_source.py::test_malformed_toml_does_not_echo_content` | adapter |
| Seguridad: tipos incorrectos | `test_task_file.py::test_wrong_types` (parametrizado: `local = "yes"`, `model = 1`, `type = []`) | domain |

Los tests de CLI llaman a `cli_app(["validate", str(path)])` en el mismo proceso, comprueban el
`int` devuelto y capturan stdout y stderr con `capsys`, sin procesos hijos.

## Riesgos
- **`TOMLDecodeError`:** en Python 3.13 no expone `lineno`/`colno` como atributos (llegan en
  3.14), y algunos de sus mensajes repiten trozos del documento (nombres de clave, el carácter
  no permitido). Por eso no se reenvía el texto del parser: se extrae solo
  `line N, column M` con una expresión regular sobre `str(exc)` y se escribe
  `invalid TOML at line N, column M`, o `invalid TOML` si no casa. Si en 3.14 se pasa a los
  atributos, el formato del mensaje no cambia.
- **Códigos de salida de cyclopts:** en v4, el `result_action` por defecto
  (`print_non_int_sys_exit`) llama a `sys.exit` con el `int` devuelto, también con 0. Se usa
  `result_action="return_value"`: el comando devuelve el código, los tests lo comprueban sin
  `SystemExit`, y `main()` hace el `sys.exit` explícito. Hay que confirmarlo con la versión
  que resuelva `uv add`. Los errores de uso (falta `<file>`) los gestiona cyclopts con su
  propio código y quedan fuera de RF-08.
- **Registro sin implementaciones:** `RUNNER_NAMES` es solo una tupla de nombres. Cuando exista
  el Protocol `Runner`, el registro pasará a asociar nombre e implementación; `domain` seguirá
  recibiendo solo nombres.
- **Coverage al 80 %:** `cli.py` y `report` deben quedar cubiertos por los tests de CLI.
- **Tamaño de las PRs:** se mantienen 2 PRs aunque alguna supere el límite de 400 líneas de
  AGENTS.md. Es una excepción aceptada por @aitormf (2026-10-20) porque este trabajo sienta las
  bases del proyecto. Se indicará en la descripción de la PR. La documentación no se separa en
  otra PR: RNF-04, RNF-06 y ARCHITECTURE §12 exigen que vaya junto al código, así que cada PR
  actualiza la parte de `ARCHITECTURE.md` que le corresponde.

## Decisiones abiertas
Interpretaciones técnicas de la spec, a confirmar al aprobar el plan:
1. Orden de los errores: claves presentes en el orden del documento y después los campos que
   faltan, en el orden del esquema.
2. Si falta el prompt efectivo, el error va en `runners[i].prompt`, no en la raíz.
3. No se crea `domain.Task` en esta entrega.
4. Los tests de CLI llaman a la App en el mismo proceso, no al ejecutable instalado.

Sin decidir (hallazgos 7, 9, 11 y 12 de `review-plan.md`), a resolver al implementar:
- Elementos de `runners` que no son tablas (`runners = [1]`): necesitan un motivo propio para
  no acabar en una traza (RNF-05).
- Orden fijo de los runners permitidos en el mensaje de `unknown runner`.
- Ficheros UTF-8 con BOM: aceptarlos o rechazarlos.
- Qué bloque o bloques `toml` de `docs/config_file.md` valida el test de CA-18.
