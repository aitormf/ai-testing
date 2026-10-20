# Tareas: Runner de Claude Code y ejecución de tareas (`run`)

<!-- Tareas pequeñas, en orden de dependencias. [P] = se puede hacer en paralelo con la anterior.
Cada tarea dice qué ficheros toca y cómo se verifica. El agente implement marca [x] al terminarlas.
TDD (AGENTS.md): en cada tarea el test se escribe primero y se ve en ROJO antes de implementar. -->

## Decisiones tomadas al partir en tareas

@aitormf las aprobó el 2026-10-20:

- **Tests de `_process.py` en la PR 3.** Van en `tests/test_process.py`, con scripts Python
  mínimos generados en `tmp_path` y lanzados con `sys.executable`. La regla de dobles de test
  (AGENTS.md, CONTRIBUTING.md §5, ARCHITECTURE.md §10) se adelanta a la PR 3. `test_claude.py`
  solo prueba lo específico de Claude. Esto cambia el reparto del plan, que ponía estos tests en
  `test_claude.py` y la regla en la PR 4.
- **Ramas.** La spec y el plan van en su propia PR de documentación (`feat/claude-runner`). Cada
  PR de código va en su propia rama desde `main`.
- **Runner falso.** El de los tests de `app` vive en `tests/fake_runner.py`.

## Fase 1: domain, workspace git y almacén JSON (PR 1, rama `feat/run-domain`)

- [ ] T1. Tipos y Protocols de `domain/run.py`:
  - tipos: `RunStatus`, `Execution`, `RunRequest`, `RunResult`, `RunRecord`, `RunLocation`,
    `RunnerCheck`;
  - excepciones: `WorkspaceError`, `StoreError`;
  - Protocols: `Runner`, `Workspace`, `ResultStore`.

  Ficheros: `src/ia_testing/domain/run.py`, `tests/test_domain_run.py`. Verificación:
  `test_dataclasses_are_frozen` + `uv run lint-imports` + `uv run mypy`
- [ ] T2. Funciones puras: `base_run_id(now)`, `default_output_dir(repo_root)`,
  `branch_name(run_id, id)`, `worktree_path(location, id)`, `log_paths(location, id)`.
  Ficheros: ídem. Verificación: `test_base_run_id_format` (RF-07), `test_default_output_dir`
  (RF-04), `test_worktree_and_log_paths` (un `id` llamado `logs` no choca)
- [ ] T3. [P] `GitWorkspace.open()`, `resolve()` e `is_dirty()`: lista de argumentos, timeout de
  60 s, refs que empiezan por `-` rechazadas antes de llamar a git, `--end-of-options`, y
  cualquier fallo convertido en `WorkspaceError` con motivo fijo. Ficheros:
  `src/ia_testing/adapters/workspace/__init__.py`, `src/ia_testing/adapters/workspace/git.py`,
  `tests/test_git_workspace.py` (repo real en `tmp_path`). Verificación:
  `test_open_from_subdirectory_returns_root`, `test_open_defaults_to_cwd`,
  `test_resolve_head_and_branch`, `test_resolve_rejects_option_like_ref`,
  `test_unknown_ref_raises`, `test_is_dirty_counts_untracked`,
  `test_git_missing_raises_workspace_error`
- [ ] T4. `GitWorkspace.create(path, branch, commit)`: `-c core.hooksPath=/dev/null`,
  `GIT_LFS_SKIP_SMUDGE=1`, `worktree add -b <branch> -- <path> <commit>`. Ficheros: ídem.
  Verificación: `test_create_worktree_on_new_branch_from_commit`,
  `test_create_does_not_run_post_checkout_hook` (RF-08), `test_existing_branch_raises`
- [ ] T5. [P] `JsonResultStore.create_run()`: creación exclusiva, sufijos `-2`, `-3`…, crea
  `logs/` y `worktrees/`; `OSError` → `StoreError`. Ficheros:
  `src/ia_testing/adapters/storage/__init__.py`, `src/ia_testing/adapters/storage/json_store.py`,
  `tests/test_json_store.py`. Verificación: `test_create_run_adds_suffix_when_exists`,
  `test_create_run_creates_logs_and_worktrees`, `test_create_run_unwritable_raises` (`skipif`
  como root)
- [ ] T6. `JsonResultStore.save()`: `schema_version: 1`, ISO 8601 con zona horaria, `null` para
  lo ausente, escritura atómica, `OSError` → `StoreError`. Ficheros: ídem. Verificación:
  `test_save_writes_schema_v1`, `test_save_is_atomic_rewrite`,
  `test_results_do_not_contain_env_values` (Seguridad)
- [ ] T7. Documentación: ARCHITECTURE.md §3 (filas de `domain/run.py`, `workspace/` y
  `storage/`) y §9 (los worktrees se crean todos antes de lanzar runners, sin hooks ni LFS).
  Ficheros: `docs/ARCHITECTURE.md`. Verificación: revisión del diff
- [ ] ✅ Punto de control PR 1: `./scripts/check.sh` en verde. PR
  `feat: add run domain model, git workspace and JSON result store`.

## Fase 2: caso de uso `run_task` (PR 2, rama `feat/run-task`)

- [ ] T8. Runner falso que implementa `Runner` (registra los `RunRequest` recibidos y devuelve
  `Execution` programados, o lanza `KeyboardInterrupt`), más el flujo feliz de `run_task`:
  pasos 1 a 7, `RunOptions` (timeout de 30 min por defecto), `RunOutcome` y `save` tras cada
  configuración. Ficheros: `src/ia_testing/app/run.py`, `tests/fake_runner.py`,
  `tests/test_app_run.py` (git real y store real en `tmp_path`). Verificación:
  `test_runs_all_configs_from_same_commit`, `test_uses_given_ref`, `test_output_dir_option`,
  `test_task_type_is_recorded_and_prompt_unchanged` (RF-16), `test_results_saved_after_each_config`
  (RF-22), `test_default_timeout_reaches_runner`, `test_runner_names_are_injected` (P5)
- [ ] T9. Fallos antes de empezar (código 2, no se lanza ningún runner): fichero inválido, no es
  repo, ref inexistente, `check()` con error, `create_run` falla, falla la creación de un
  worktree (lista los ya creados). Ficheros: ídem. Verificación:
  `test_invalid_file_returns_errors`, `test_not_a_repo_returns_error`, `test_check_error_aborts`,
  `test_worktree_failure_aborts_before_running`
- [ ] T10. Avisos, runners no implementados y fallos que no detienen el resto. Ficheros: ídem.
  Verificación: `test_dirty_repo_warns`, `test_warnings_are_emitted`,
  `test_unimplemented_runner_fails_without_worktree` (RF-10), `test_failed_run_continues`
- [ ] T11. Interrupción y fallo de `save`:
  - la configuración actual y las pendientes quedan como `interrupted`, con duración real y 0;
  - `interrupted before start` lista los worktrees ya creados;
  - `cannot write results` da código 1.

  Ficheros: ídem. Verificación: `test_interrupt_marks_current_and_pending` (RF-20),
  `test_interrupt_before_start_lists_worktrees`, `test_save_failure_stops_with_exit_1`
- [ ] T12. Documentación: ARCHITECTURE.md §3 (`app/run.py`) y §7 (flujo real, sin `Comparison`
  todavía). Ficheros: `docs/ARCHITECTURE.md`. Verificación: revisión del diff
- [ ] ✅ Punto de control PR 2: `./scripts/check.sh` en verde. PR `feat: add run_task use case`.

## Fase 3: gestión de procesos (PR 3, rama `feat/run-process`)

- [ ] T13. `run_logged()`, arranque y E/S:
  - `Popen` en binario con `start_new_session=True`;
  - hilo de stdin que ignora `BrokenPipeError`;
  - hilos lectores con `errors="replace"`, enmascarado con `***` y ficheros separados;
  - `OSError` al arrancar → `start_error`.

  Ficheros: `src/ia_testing/adapters/runners/_process.py`, `tests/test_process.py` (scripts en
  `tmp_path` lanzados con `sys.executable`). Verificación:
  `test_stdout_and_stderr_go_to_separate_files`, `test_secrets_masked_in_stdout_and_stderr`,
  `test_non_utf8_output_is_logged`, `test_large_stdin_not_read_does_not_hang`,
  `test_start_error`, `test_no_shell_interpretation`
- [ ] T14. Timeout y limpieza en todos los casos: espera con sondeo, `killpg(SIGTERM)`, 5 s de
  gracia, `killpg(SIGKILL)` siempre al terminar, y espera de 5 s como máximo a los hilos.
  Ficheros: ídem. Verificación: `test_timeout_kills_process_group`,
  `test_orphan_child_killed_after_normal_exit` (bloqueante de `review-plan.md`)
- [ ] T15. Interrupción: ante `KeyboardInterrupt`, mata el grupo y la vuelve a lanzar. Ficheros:
  ídem. Verificación: `test_interrupt_kills_group_and_reraises` (`signal.pthread_kill` desde un
  temporizador)
- [ ] T16. Documentación:
  - ARCHITECTURE.md §3 (`_process.py`) y §10 (dobles de test);
  - regla de dobles de test en AGENTS.md y CONTRIBUTING.md §5: ejecutables o scripts falsos
    generados por los tests; sigue prohibido parchear `subprocess`.

  Ficheros: `docs/ARCHITECTURE.md`, `AGENTS.md`, `CONTRIBUTING.md`. Verificación: revisión del
  diff
- [ ] ✅ Punto de control PR 3: `./scripts/check.sh` en verde. PR `feat: add process runner with
  timeout, process-group cleanup and secret masking`.

## Fase 4: runner de Claude Code y registro (PR 4, rama `feat/claude-runner-adapter`)

- [ ] T17. Fixture del `claude` falso: script con `sys.executable` en el shebang y bit de
  ejecución, puesto al principio del `PATH`. Lee el escenario de `fake-claude.json` en el `cwd`
  y registra argv, stdin y entorno. Escenarios: stream-json fijo, código de salida, stderr,
  imprimir una credencial, hijo dormido. Ficheros: `tests/fakes.py`. Verificación: la usan los
  tests de T19 y T20
- [ ] T18. [P] Funciones puras `build_argv(exe, model)`, `build_env(source_env)` y
  `parse_result(jsonl_path)`. Captura real de la versión 2.1.303. Tokens: entrada sin caché +
  lectura de caché + creación de caché. Ficheros: `src/ia_testing/adapters/runners/claude.py`,
  `tests/test_claude.py`, `tests/data/claude-stream-2.1.303.jsonl`. Verificación:
  `test_argv_does_not_restrict_settings` (RF-13), `test_build_env_keeps_only_allowed_vars`,
  `test_parse_result_real_capture`, `test_parse_result_sums_cache_tokens`,
  `test_parse_result_tolerates_missing_fields`
- [ ] T19. `ClaudeRunner.check()`. Ficheros: ídem. Verificación:
  `test_check_missing_claude_errors`, `test_check_warns_bypass` (RF-12),
  `test_check_warns_on_local` (RF-15)
- [ ] T20. `ClaudeRunner.run()` con el `claude` falso:
  - estado, motivos y precedencia del código de salida;
  - timeout y Ctrl-C;
  - entorno, enmascarado, logs y argumentos literales.

  Ficheros: ídem. Verificación: `test_nonzero_exit_fails`, `test_exit_0_with_is_error_fails`,
  `test_nonzero_exit_takes_precedence_over_is_error`, `test_timeout_kills_process_group`,
  `test_interrupt_kills_group_and_reraises`, `test_secret_env_not_passed`,
  `test_credential_masked_in_logs`, `test_stdout_and_stderr_logs`,
  `test_argv_and_stdin_are_literal`
- [ ] T21. Registro: `RUNNERS`, `RUNNER_NAMES = tuple(RUNNERS)` y `build_runners()`. Ficheros:
  `src/ia_testing/adapters/runners/registry.py`, `tests/test_registry.py`. Verificación:
  `test_registered_runners` (sigue pasando sin cambios),
  `test_build_runners_instantiates_implemented`
- [ ] T22. [P] Test de integración con Claude real (modelo `haiku`, repo mínimo en `tmp_path`).
  Ficheros: `tests/test_claude_integration.py` (`@pytest.mark.integration`). Verificación:
  `uv run pytest -m integration tests/test_claude_integration.py`
- [ ] T23. Documentación:
  - ARCHITECTURE.md §1 y §9 (Claude es el primer runner), §3 (`karajan.py` → `claude.py`,
    registro), §6 (credenciales: la CLI elige las variables y las enmascara en los logs);
  - SECURITY.md (`bypassPermissions`, logs del agente y su riesgo);
  - AGENTS.md (regla de credenciales).

  Ficheros: `docs/ARCHITECTURE.md`, `SECURITY.md`, `AGENTS.md`. Verificación: revisión del diff
- [ ] ✅ Punto de control PR 4: `./scripts/check.sh` en verde y `uv run pytest -m integration` en
  verde en local. PR `feat: add claude code runner`.

## Fase 5: comando `run`, informe y documentación de uso (PR 5, rama `feat/run-command`)

- [ ] T24. `print_run(outcome, out, err)`: errores previos → stderr y código 2; `cannot write
  results` → código 1; resumen → stdout; 0 o 1. Ficheros: `src/ia_testing/adapters/report/run.py`,
  `tests/test_report_run.py`. Verificación: `test_summary_lines`, `test_errors_exit_2`,
  `test_any_failure_exit_1`
- [ ] T25. Comando `run`:
  - opciones `--repo` (`None` por defecto), `--ref`, `--timeout` (entero mayor que 0, 30 por
    defecto) y `--output-dir`;
  - `datetime.now().astimezone()` y `build_runners()`;
  - `warn` escribe en stderr;
  - `main()` instala el manejador de SIGTERM y SIGHUP.

  Ficheros: `src/ia_testing/cli.py`, `tests/test_cli_run.py` (con el `claude` falso).
  Verificación: `test_invalid_file_exit_2_creates_nothing`, `test_not_a_repo_exit_2`,
  `test_unknown_ref_exit_2`, `test_option_like_ref_exit_2`, `test_claude_missing_exit_2`,
  `test_invalid_timeout` (`0`, `-5`, `abc`), `test_default_timeout_parameter`,
  `test_claude_and_codex`, `test_secret_not_in_output`,
  `test_sigterm_handler_raises_keyboard_interrupt`; ninguno tiene `Traceback` en stderr
- [ ] T26. Documentación de uso:
  - `docs/run.md`: uso, estructura del directorio, esquema de `results.json`, permisos y riesgos;
  - README.md;
  - `docs/config_file.md` (también se usa con `run`);
  - ARCHITECTURE.md §10 (el fichero de tarea es entrada de `run`).

  Ficheros: los citados. Verificación: revisión del diff + `test_docs.py` en verde
- [ ] ✅ Punto de control PR 5: `./scripts/check.sh` en verde. PR `feat: add run command`.

## Cierre

- [ ] Todos los criterios de aceptación de la spec tienen un test que pasa (correspondencia en
  la tabla "Pruebas" de `plan.md`).
- [ ] Los tests negativos de Seguridad de la spec pasan: `SECRET_X`, credencial enmascarada,
  metacaracteres, `--ref=--foo` y `--timeout` no válido.
- [ ] `./scripts/check.sh` en verde.
- [ ] `uv run pytest -m integration` en verde en local con Claude Code instalado.
