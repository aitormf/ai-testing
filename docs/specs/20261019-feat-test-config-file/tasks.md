# Tareas: Fichero de configuración de la tarea

<!-- Tareas pequeñas, en orden de dependencias. [P] = se puede hacer en paralelo con la anterior.
Cada tarea dice qué ficheros toca y cómo se verifica. El agente implement marca [x] al terminarlas.
TDD (AGENTS.md): en cada tarea el test se escribe primero y se ve en ROJO antes de implementar. -->

## Decisiones tomadas al partir en tareas

Los hallazgos 7, 9, 11 y 12 de `review-plan.md` quedaron aplazados en el plan. @aitormf los
resolvió el 2026-10-20 así:

- **H7. Elementos de `runners` que no son tablas** (`runners = [1]`, `runners = ["a"]`): error
  `runners[i]: expected a table`, y ese elemento no se sigue validando (T4).
- **H9. Orden de los runners en el mensaje:** `unknown runner: expected one of <...>` se construye
  a partir de `runner_names` en orden alfabético (`sorted`), así que es determinista aunque llegue
  un `set` (T4 y T6).
- **H11. BOM de UTF-8:** se acepta. El fichero se decodifica con `utf-8-sig` y queda documentado
  en `docs/config_file.md` (T9 y T12).
- **H12. Ejemplos de la documentación:** todos los bloques `toml` de `docs/config_file.md` deben
  ser válidos. Los ejemplos de salida de error van en bloques `text`, no `toml` (T12).

## Fase 1: modelo y validación en domain (PR 1)

- [ ] T1. Tipos de `domain`: `TaskType`, `RunnerConfig`, `TaskFile`, `FieldError` (`__str__` →
  `"<path>: <reason>"`), `InvalidTaskFile(errors)` y el Protocol `TaskFileSource` — ficheros:
  `src/ia_testing/domain/task_file.py`, `tests/test_task_file.py` — verificación:
  `uv run pytest tests/test_task_file.py -q` (test de `FieldError.__str__`) + `uv run lint-imports`
- [ ] T2. `parse_task_file()`, caso válido: prompt común y prompt propio, `local` por defecto,
  `runner_names` inyectado — ficheros: `src/ia_testing/domain/task_file.py`,
  `tests/test_task_file.py` — verificación: `test_same_runner_twice_with_distinct_ids_is_valid`
  (CA-03), `test_local_defaults_to_false` (CA-10), `test_own_prompt_overrides_common` (RF-05),
  `test_runner_names_are_injected` (RF-12/P5)
- [ ] T3. Errores de la raíz: clave desconocida, `type` ausente o no válido, `runners` ausente,
  vacío o como tabla, tipos incorrectos en la raíz, documento vacío — ficheros: ídem —
  verificación: `test_unknown_root_key` (CA-09), `test_unknown_type_lists_allowed_without_value`
  (CA-02), `test_empty_document_reports_type_and_runners` (CA-12), `test_runners_empty_or_table`
  (CA-14), `test_wrong_types` (caso `type = []`)
- [ ] T4. Errores de cada configuración de runner — ficheros: ídem. Incluye:
  - campo obligatorio ausente, clave desconocida y tipo incorrecto;
  - texto vacío o con solo espacios; si es el prompt común, un único error `prompt: must not be empty`;
  - elemento que no es tabla: `runners[i]: expected a table` (H7);
  - `runner` fuera de `runner_names`, con los valores permitidos en orden alfabético (H9);
  - orden de los errores: claves presentes en el orden del documento y después los campos que faltan;
  - mensajes sin valores.

  Verificación: `test_missing_model` (CA-07), `test_blank_text_fields_are_errors` (CA-11),
  `test_wrong_types` (`local = "yes"`, `model = 1`, `runners = [1]`, `runners = ["a"]`),
  `test_unknown_runner_lists_allowed_sorted` (H9, con un `set` como `runner_names`),
  `test_credential_key_rejected_without_value` (Seguridad)
- [ ] T5. Reglas entre campos: formato de `id` (`fullmatch`), `id` duplicado marcado en la
  segunda aparición, prompt efectivo ausente — ficheros: ídem — verificación:
  `test_invalid_id_format` (CA-05, incluidos `/`, `..` y `\n` final),
  `test_duplicate_id_reported_on_later_entry_without_value` (CA-04),
  `test_missing_effective_prompt` (CA-06)
- [ ] T6. [P] Registro de runners `RUNNER_NAMES = ("claude", "codex", "opencode")` — ficheros:
  `src/ia_testing/adapters/runners/__init__.py`, `src/ia_testing/adapters/runners/registry.py`,
  `tests/test_registry.py`, `tests/test_task_file.py` — verificación: `test_registered_runners`,
  `test_karajan_is_not_a_known_runner` (CA-17, con `RUNNER_NAMES` real; el mensaje lista
  `claude, codex, opencode`)
- [ ] T7. `docs/ARCHITECTURE.md` §3: `domain/task_file.py` y el Protocol `TaskFileSource` en la
  fila de `domain`; el registro en la fila de `runners/` — ficheros: `docs/ARCHITECTURE.md` —
  verificación: revisión del diff
- [ ] ✅ Punto de control PR 1: `./scripts/check.sh` en verde. Rama `feat/task-file-model`. PR
  `feat: add task file model and validation`, avisando en la descripción de que supera las
  400 líneas por excepción aceptada en el plan.

## Fase 2: lectura, CLI y documentación (PR 2)

- [ ] T8. `uv add "cyclopts>=4,<5"` y comprobar que `result_action="return_value"` existe en la
  versión resuelta — ficheros: `pyproject.toml`, `uv.lock` — verificación: `uv sync` +
  `./scripts/check.sh`
- [ ] T9. [P] `TomlTaskFileSource(path)` — ficheros: `src/ia_testing/adapters/task_file.py`,
  `tests/test_toml_source.py`. Hace lo siguiente:
  - lee los bytes, los decodifica con `utf-8-sig` (H11) y aplica `tomllib.loads`;
  - convierte `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, otros `OSError`,
    `UnicodeDecodeError` y `TOMLDecodeError` en `InvalidTaskFile`, sin repetir contenido del fichero.

  Verificación:
  - CA-16: `test_missing_file`, `test_directory`, `test_unreadable_file` (`skipif` como root),
    `test_not_a_directory`;
  - CA-13: `test_binary_file` (20 KB, `bytes(range(256)) * 80`);
  - CA-15: `test_malformed_toml_reports_line` (`line 3, column 5`);
  - Seguridad: `test_malformed_toml_does_not_echo_content`;
  - CA-12: `test_empty_file`;
  - H11: `test_utf8_bom_is_accepted`.
- [ ] T10. Caso de uso `validate_task_file(source, runner_names)` — ficheros:
  `src/ia_testing/app/task_file.py`, `tests/test_app_task_file.py` — verificación:
  `test_validate_task_file_returns_errors_or_empty` con el `TomlTaskFileSource` real en `tmp_path`
- [ ] T11. Salida del comando y CLI cyclopts — ficheros:
  `src/ia_testing/adapters/report/__init__.py`, `src/ia_testing/adapters/report/validation.py`,
  `src/ia_testing/cli.py`, `tests/test_cli.py`. Incluye:
  - `print_validation(errors, out, err) -> int`;
  - `App(result_action="return_value")` con el comando `validate(file)`;
  - `main()` con `sys.exit(cli_app())`;
  - sustituir el test del saludo (aprobado).

  Verificación:
  - CA-01: `test_validate_valid_file_prints_ok`;
  - CA-08: `test_validate_invalid_file_reports_all_errors_in_order`;
  - CA-13, CA-15 y CA-16 de extremo a extremo, y RNF-05: `test_validate_unreadable_or_malformed_file_fails`;
  - Seguridad: el valor de `api_key` no aparece en stderr.
- [ ] T12. `docs/config_file.md` y enlace en `README.md` — ficheros: `docs/config_file.md`,
  `README.md`, `tests/test_docs.py`. El documento recoge:
  - campos, tipos, obligatoriedad, valores por defecto y permitidos;
  - formato de errores, con los ejemplos en bloques `text`;
  - que se acepta el BOM de UTF-8;
  - un ejemplo completo en un bloque `toml`.

  Verificación: `test_config_file_examples_are_valid` (CA-18): extrae **todos** los bloques
  `toml` (H12), falla si no hay ninguno y está en rojo mientras no exista el documento.
- [ ] T13. [P] `docs/ARCHITECTURE.md` — ficheros: `docs/ARCHITECTURE.md`. Cambios:
  - §3: fila nueva para `adapters/task_file.py` y `validation.py` en la fila de `report/`;
  - §8: fichero de tarea, configuración de runner y el matiz de Tarea;
  - §10: el fichero de tarea no es configuración de cyclopts.

  Verificación: revisión del diff.
- [ ] ✅ Punto de control PR 2: `./scripts/check.sh` en verde. PR
  `feat: add validate command for task files`, con el mismo aviso de tamaño. Se apila sobre
  la rama de la PR 1 (base = rama de la PR 1, no `main`), decisión de @aitormf (2026-10-20).

## Cierre

- [ ] Todos los criterios de aceptación de la spec (CA-01 a CA-18) y los tests negativos de
  Seguridad tienen un test que pasa (ver la tabla de Pruebas de `plan.md`).
- [ ] `./scripts/check.sh` sale en verde.
