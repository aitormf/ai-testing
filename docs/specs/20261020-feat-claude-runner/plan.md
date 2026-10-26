---
status: aprobada
---

# Plan: Runner de Claude Code y ejecución de tareas (`run`)

## Objetivo técnico
Un caso de uso `app.run_task()` que hace las comprobaciones previas, crea el directorio de la
ejecución y todos los worktrees, lanza los runners en secuencia y guarda `results.json` tras cada
uno. Para ello hacen falta:
- Protocols nuevos en `domain` (`Runner`, `Workspace`, `ResultStore`);
- adapters para git, JSON, procesos y Claude Code;
- un registro que asocia el nombre de cada runner con su implementación (o `None` si no está
  implementada);
- el comando `ia-testing run`.

## Arquitectura propuesta

```
cli.run(file, repo, ref, timeout, output_dir)
  ├─ monta TomlTaskFileSource, GitWorkspace(repo), JsonResultStore, build_runners()
  ├─ app.run_task(source, runners, workspace, store, options, warn) → RunOutcome
  │    1. parse_task_file(source.read(), runners.keys())        → errores → código 2
  │    2. workspace.open() → raíz; workspace.resolve(ref) → commit → error → código 2
  │    3. runner.check(configs) por runner usado (instalado; avisos)  → error → código 2
  │    4. aviso si workspace.is_dirty()
  │    5. store.create_run(base_id, output_dir) → RunLocation  → error → código 2
  │    6. workspace.create(path, branch, commit) para cada config implementada → error → código 2
  │    7. para cada config: runner.run(RunRequest) → Execution → RunResult; store.save(record)
  │       KeyboardInterrupt → marca la actual y las pendientes como "interrupted"; store.save
  └─ report.print_run(outcome, stdout, stderr) → código de salida
```

- `domain` solo tiene datos, Protocols y funciones puras: rutas derivadas (`pathlib`, sin E/S),
  el `run-id` y la composición de `RunResult` (P1).
- `app` orquesta y no conoce nombres de runners: recibe `Mapping[str, Runner | None]` (P5).
- Todo `subprocess` vive en `adapters/workspace/git.py` y en `adapters/runners/_process.py` (P3).
- Elementos nuevos en el mapa del código:
  - `domain/run.py`
  - `app/run.py`
  - `adapters/workspace/git.py`
  - `adapters/storage/json_store.py`
  - `adapters/runners/_process.py`
  - `adapters/runners/claude.py`
  - `adapters/report/run.py`

  Todos encajan en las carpetas que ya prevé ARCHITECTURE.md §3. No hay capas nuevas.
- Los avisos (cambios sin commitear, `bypassPermissions`, `local = true`) llegan a `report`
  mediante un `warn: Callable[[str], None]` que pasa `cli`. Es un parámetro, no un Protocol
  nuevo, y se emite en cuanto ocurre, no al final.
- SIGTERM y SIGHUP se tratan como Ctrl-C: `cli.main()` instala, antes de llamar a la App, un
  manejador que lanza `KeyboardInterrupt`. Es configuración del proceso, no lógica de negocio
  (P4).

Estructura del directorio de una ejecución (RF-07):

```
<output-dir>/<run-id>/
├── results.json
├── logs/
│   ├── <id>.jsonl
│   └── <id>.stderr.log
└── worktrees/
    └── <id>/          # rama ia-testing/<run-id>/<id>
```

## Componentes y responsabilidades

| Fichero | Responsabilidad | PR |
|---|---|---|
| `domain/run.py` | `RunStatus`, `Execution`, `RunRequest`, `RunResult`, `RunRecord`, `RunLocation`, `RunnerCheck`, `WorkspaceError`, `StoreError`; Protocols `Runner`, `Workspace`, `ResultStore`; funciones puras `base_run_id(now)`, `default_output_dir(repo_root)`, `branch_name(run_id, id)`, `worktree_path(location, id)`, `log_paths(location, id)` | 1 |
| `adapters/workspace/git.py` | `GitWorkspace(path)`: `open()` (`git rev-parse --show-toplevel`), `resolve(ref)` (rechaza antes de llamar a git las refs vacías o que empiezan por `-`; después `git rev-parse --verify --end-of-options <ref>^{commit}`), `is_dirty()` (`git status --porcelain`, incluye ficheros sin seguimiento), `create(path, branch, commit)` (`git -c core.hooksPath=/dev/null worktree add -b <branch> -- <path> <commit>` con `GIT_LFS_SKIP_SMUDGE=1`: sin hooks ni LFS). Todas las llamadas con lista de argumentos, sin shell y con timeout de 60 s; cualquier fallo, incluido `git` ausente, se convierte en `WorkspaceError` con un motivo fijo | 1 |
| `adapters/storage/json_store.py` | `JsonResultStore`: `create_run(base_id, base_dir)` (crea `base_dir` con `parents=True`, crea el directorio de la ejecución en exclusiva con `mkdir(exist_ok=False)` y prueba `-2`, `-3`… si ya existe; crea `logs/` y `worktrees/`), `save(location, record)` (escribe un temporal y lo renombra de forma atómica; `OSError` → `StoreError`) | 1 |
| `app/run.py` | `RunOptions`, `RunOutcome`, `run_task()` (flujo de los pasos 1 a 7; interrupción; fallo de `save`) | 2 |
| `adapters/runners/_process.py` | `run_logged(argv, cwd, env, stdin_text, timeout_s, stdout_path, stderr_path, secrets) -> ProcessResult`. Ver "Gestión de procesos" | 3 |
| `adapters/runners/claude.py` | `ClaudeRunner`: `check(configs)` (`shutil.which("claude")` → error si falta; aviso de `bypassPermissions`; aviso por cada `local = true`); `run(request)`. Funciones puras: `build_argv(exe, model)`, `build_env(source_env) -> (env, secrets)`, `parse_result(jsonl_path) -> OutputSummary` (tipo común a todos los runners, en `adapters/runners/_summary.py`; `run()` compone el `Execution` con el código de salida y la duración) | 4 |
| `adapters/runners/registry.py` | `RUNNERS: Mapping[str, Callable[[], Runner] | None] = {"claude": ClaudeRunner, "codex": None, "opencode": None}`; `RUNNER_NAMES = tuple(RUNNERS)` (lo sigue usando `validate`); `build_runners() -> dict[str, Runner | None]` (instancia los implementados, para que `cli` no tenga lógica) | 4 |
| `tests/fakes.py` | Fixture que genera en `tmp_path` el ejecutable `claude` falso (shebang con `sys.executable`, bit de ejecución) y una función para escribir su escenario. Ver Pruebas | 4 |
| `adapters/report/run.py` | `print_run(outcome, out, err) -> int`: errores previos → stderr y 2; resumen → stdout; devuelve 0 o 1 | 5 |
| `cli.py` | Comando `run(file, *, repo: Path | None = None, ref="HEAD", timeout: int>0 = 30, output_dir: Path | None = None) -> int` (`repo=None` = directorio actual, se resuelve en `GitWorkspace`): monta los adapters con `build_runners()`, pasa `datetime.now().astimezone()` y delega. `main()` instala el manejador de SIGTERM/SIGHUP | 5 |
| `docs/run.md` (nuevo) + `README.md` | Uso de `run`, estructura del directorio de ejecución, esquema de `results.json`, permisos (`bypassPermissions`) y riesgos | 5 |

### Documentación por PR
Cada PR actualiza la documentación de lo que introduce (ARCHITECTURE.md §12):

| PR | Documentos |
|---|---|
| 1 | ARCHITECTURE.md §3 (filas de `domain/run.py`, `workspace/`, `storage/`), §9 (los worktrees se crean todos antes de lanzar runners; sin hooks ni LFS) |
| 2 | ARCHITECTURE.md §3 (`app/run.py`), §7 (flujo real, sin `Comparison` todavía) |
| 3 | ARCHITECTURE.md §3 (`_process.py`) |
| 4 | ARCHITECTURE.md §1 y §9 (Claude es el primer runner), §3 (`karajan.py` → `claude.py`, registro), §6 (la CLI elige las variables que pasa al agente, incluidas las credenciales, y las enmascara en los logs), §10 (dobles de test). SECURITY.md (`bypassPermissions`, logs del agente y su riesgo). AGENTS.md: regla de credenciales ("la CLI solo pasa las credenciales de la lista de RF-14 al agente y las enmascara en los logs; nunca las guarda") y regla de dobles de test. CONTRIBUTING.md §5 (dobles de test) |
| 5 | `docs/run.md`, README.md, `docs/config_file.md` (el fichero también se usa con `run`), ARCHITECTURE.md §10 (el fichero de tarea también es entrada de `run`) |

### Gestión de procesos (`_process.py`)
- **Arranque:** `Popen(argv, cwd, env, stdin=PIPE, stdout=PIPE, stderr=PIPE,
  start_new_session=True)`, en binario. Un `OSError` al arrancar → `ProcessResult` con error de
  arranque.
- **Stdin:** un hilo escribe el prompt y cierra stdin, ignorando `BrokenPipeError` y `OSError`. Así
  un prompt grande no bloquea la CLI y la escritura cuenta dentro del timeout.
- **Salida:** dos hilos leen stdout y stderr línea a línea en binario, sustituyen
  cada valor de `secrets` (codificado en UTF-8) por `***` y escriben los bytes en su fichero, sin
  decodificar: el log conserva los bytes exactos salvo el enmascarado (RF-23, RF-24).
- **Espera:** con sondeo (`proc.wait(timeout=0.2)` en bucle hasta el timeout total), para que un
  `KeyboardInterrupt` del hilo principal se atienda en cualquier momento.
- **Final, siempre** (salida normal, timeout o interrupción): `killpg(SIGTERM)` al grupo, 5 s de
  gracia, `killpg(SIGKILL)`; después se espera a los tres hilos con un límite de 5 s cada uno. Un
  hijo que sobreviva al agente (por ejemplo, un servidor MCP) no puede dejar colgada la CLI.
- **Resultado:** `ProcessResult(returncode, timed_out, start_error)`. Ante una interrupción, tras
  la limpieza vuelve a lanzar `KeyboardInterrupt`.

## Modelo de datos mínimo

```python
class RunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Execution:  # lo que devuelve un Runner
    status: RunStatus
    reason: str | None
    duration_s: float
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class RunRequest:
    config: RunnerConfig
    workdir: Path
    timeout_s: float
    stdout_log: Path
    stderr_log: Path


@dataclass(frozen=True)
class RunResult:  # RF-21
    id: str
    runner: str
    model: str
    local: bool
    status: RunStatus
    reason: str | None
    duration_s: float
    worktree: Path | None
    branch: str | None
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    stdout_log: Path | None
    stderr_log: Path | None


@dataclass(frozen=True)
class RunRecord:  # RF-22 → results.json
    run_id: str
    started_at: datetime  # con zona horaria
    task_type: TaskType
    repo: Path
    ref: str
    commit: str
    results: tuple[RunResult, ...]


@dataclass(frozen=True)
class RunLocation:
    run_id: str
    dir: Path  # worktrees en dir/worktrees/<id>, logs en dir/logs/


@dataclass(frozen=True)
class RunnerCheck:
    error: str | None
    warnings: tuple[str, ...]
```

Esquema de `results.json` (`schema_version: 1`): los campos de `RunRecord`, con `started_at` en ISO
8601 con zona horaria, rutas absolutas como texto y `results` como lista de objetos `RunResult`;
los valores ausentes se escriben como `null`. No incluye el fichero de tarea.

Tokens (RF-21), a partir de `usage` del último evento `result` de Claude:
- `input_tokens` = `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`
  (todo lo procesado como entrada, sea o no de caché);
- `output_tokens` = `output_tokens`.

Coste: `total_cost_usd`, tal cual.

Duración: la real para las configuraciones ejecutadas, incluida la interrumpida (la mide `app`
cuando el runner vuelve a lanzar la interrupción); `0` para las pendientes y las no implementadas.

Motivos fijos: `runner not implemented yet`, `timeout`, `interrupted`,
`claude exited with code N`, `claude reported an error`, `cannot start claude`. Si el código de
salida no es 0, el motivo es `claude exited with code N` aunque también haya `is_error`. Ningún
motivo incluye la salida del agente.

## Contratos

```python
class Runner(Protocol):
    def check(self, configs: Sequence[RunnerConfig]) -> RunnerCheck: ...
    def run(self, request: RunRequest) -> Execution: ...
        # aplica el timeout y termina su grupo de procesos; ante KeyboardInterrupt termina
        # el grupo y la vuelve a lanzar; nunca lanza otras excepciones

class Workspace(Protocol):
    def open(self) -> Path: ...                                   # raíz; WorkspaceError
    def resolve(self, ref: str) -> str: ...                       # commit; WorkspaceError
    def is_dirty(self) -> bool: ...
    def create(self, path: Path, branch: str, commit: str) -> None: ...   # WorkspaceError

class ResultStore(Protocol):
    def create_run(self, base_id: str, base_dir: Path) -> RunLocation: ...  # StoreError
    def save(self, location: RunLocation, record: RunRecord) -> Path: ...    # StoreError

def run_task(source: TaskFileSource, runners: Mapping[str, Runner | None],
             workspace: Workspace, store: ResultStore, options: RunOptions,
             warn: Callable[[str], None]) -> RunOutcome
```

`RunOutcome` contiene:
- `errors: tuple[str, ...]`: fallos previos (código 2), o el fallo de `save` (código 1);
- `record: RunRecord | None`;
- `results_path: Path | None`.

Errores fuera del flujo normal:
- Si `save` falla en el paso 7, se deja de ejecutar, el error lleva un motivo fijo
  (`cannot write results`) y el código es 1.
- Una interrupción en los pasos 1 a 6 termina con código 2 y el error
  `interrupted before start`, que lista los worktrees ya creados; no se escribe `results.json`.

Claude Code se lanza así: `[<ruta absoluta de claude>, "-p", "--model=<model>",
"--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions"]`, con
`cwd` en el worktree y el prompt por **stdin**. Así un prompt o un `model` que empiecen por `-`
nunca se interpretan como opciones, y no hay shell. No se pasa `--setting-sources` ni `--bare`
(RF-13). Comprobado con Claude Code 2.1.303: acepta el prompt por stdin (también si empieza por
`--`), funciona con el entorno mínimo usando la sesión de suscripción y acepta
`bypassPermissions` sin flags extra.

Entorno: solo las variables de RF-14 que existan en `os.environ`. `secrets` son los valores no
vacíos de `ANTHROPIC_API_KEY` y `CLAUDE_CODE_OAUTH_TOKEN`.

Estado (RF-18): `succeeded` si el código de salida es 0 y el último evento `result` no tiene
`is_error: true`. Si no hay evento `result` o no se puede parsear, el coste y los tokens quedan
en `null` y el estado depende solo del código de salida.

## Comprobación de principios

| Principio | ¿Se cumple? | Nota |
|---|---|---|
| P1 `domain` puro | Sí | `domain/run.py` usa `dataclasses`, `enum`, `datetime`, `pathlib` (solo operaciones de ruta) y `typing` |
| P2 dirección de dependencias | Sí | Lo comprueba import-linter; `app` solo importa `domain` |
| P3 `subprocess` solo en adapters | Sí | En `workspace/git.py` y `runners/_process.py`; siempre con timeout, nunca con `shell=True` |
| P4 `cli.py` fino | Sí | `run` monta los adapters con `build_runners()`, llama a `run_task` y pasa el resultado a `print_run`; sin `if` ni `try`. `main()` solo instala el manejador de señales |
| P5 runner nuevo sin tocar domain/app | Sí | Añadir `codex` = `adapters/runners/codex.py` + cambiar `None` por la clase en `RUNNERS`. Un test de `app` con un nombre de runner inventado lo demuestra |
| P6 tests sin herramientas externas | Sí | Runner falso en los tests de `app`; ejecutable `claude` falso en los del adapter (sin parchear `subprocess`); git real en `tmp_path`; los tests con Claude real llevan `integration` |
| P7 test primero | Sí | Cada tarea empieza por su test en rojo; el orden de las PRs permite que cada una se pruebe con lo que ya existe |
| P8 sin dependencias nuevas | Sí | Solo stdlib y cyclopts |

AGENTS.md:
- Los Protocols nuevos de `domain` están confirmados al aprobar la spec.
- `RUNNER_NAMES` se mantiene, ahora derivado de `RUNNERS`.
- La regla "el único doble es un runner falso" se amplía para permitir ejecutables falsos de las
  herramientas externas, generados por los tests (aprobado por @aitormf, 2026-10-20). Sigue
  prohibido parchear `subprocess`.

Desviación de la spec: en "Entidades", la spec dice que el `Runner` devuelve un `RunResult`. En
el plan devuelve un `Execution` (estado, motivo, duración, coste, tokens) y `app` compone el
`RunResult` con la configuración, el worktree, la rama y los logs, que el runner no necesita
conocer. Así un runner nuevo implementa menos.

Desviación del plan: `parse_result` devuelve un `OutputSummary` (`is_error`, coste y tokens), no un
`Execution`, porque el estado y la duración dependen del proceso y no del fichero. El tipo es común a
todos los runners y vive en `adapters/runners/_summary.py`; no toca `domain` ni `app`. La función que
compone el `Execution` (precedencia timeout, código de salida, `is_error`) se extraerá cuando haya un
segundo runner que confirme qué varía.

## Pruebas

**`claude` falso.** La fixture de `tests/fakes.py` genera en `tmp_path` un ejecutable `claude`
(script Python con `sys.executable` en el shebang y bit de ejecución) y lo pone al principio del
`PATH` con `monkeypatch.setenv`. El escenario se lee de `fake-claude.json` en el `cwd`, porque
`build_env` no deja pasar variables de control. En los tests de CLI, el escenario se commitea en
el repo de prueba para que aparezca en el worktree. El script registra en un fichero lo que
recibió (argv, stdin y entorno) para que el test lo compruebe.

| Criterio / requisito | Test | Nivel |
|---|---|---|
| CA dos configs `claude`, mismo commit, ramas, logs, `results.json`, código 0 | `test_app_run.py::test_runs_all_configs_from_same_commit` (runner falso + git real + store real) | app |
| CA `--repo` / `--ref` por defecto y subdirectorio | `test_git_workspace.py::test_open_from_subdirectory_returns_root`, `test_open_defaults_to_cwd`, `test_resolve_head_and_branch` + `test_app_run.py::test_uses_given_ref` | adapter + app |
| CA `--output-dir` | `test_app_run.py::test_output_dir_option` | app |
| RF-04 ruta por defecto | `test_domain_run.py::test_default_output_dir` | domain |
| RF-07 formato del `run-id` y rutas | `test_domain_run.py::test_base_run_id_format`, `test_worktree_and_log_paths` (un `id` llamado `logs` no choca) | domain |
| CA sufijo `-2` | `test_json_store.py::test_create_run_adds_suffix_when_exists` | adapter |
| CA `type = code-review` | `test_app_run.py::test_task_type_is_recorded_and_prompt_unchanged` | app |
| CA resumen en stdout | `test_report_run.py::test_summary_lines` | adapter |
| CA esquema de `results.json` | `test_json_store.py::test_save_writes_schema_v1` (incluye `started_at` con zona horaria) | adapter |
| CA `claude` + `codex` → `codex` no implementado, sin worktree, código 1 | `test_app_run.py::test_unimplemented_runner_fails_without_worktree` + `test_cli_run.py::test_claude_and_codex` (CLI real con el `claude` falso) | app + CLI |
| CA `local = true` → aviso | `test_claude.py::test_check_warns_on_local` + `test_app_run.py::test_warnings_are_emitted` | adapter + app |
| CA fichero inválido → 2, nada creado | `test_cli_run.py::test_invalid_file_exit_2_creates_nothing` | CLI |
| CA no es repo git / ref inexistente → 2 | `test_cli_run.py::test_not_a_repo_exit_2`, `test_unknown_ref_exit_2` | CLI |
| CA Claude no instalado → 2 | `test_cli_run.py::test_claude_missing_exit_2` (`PATH` sin `claude`) | CLI |
| CA `--timeout` no válido | `test_cli_run.py::test_invalid_timeout` (parametrizado: `0`, `-5`, `abc`) | CLI |
| CA timeout de 30 min por defecto | `test_app_run.py::test_default_timeout_reaches_runner` (`RunRequest.timeout_s == 1800` con el `RunOptions` por defecto) + `test_cli_run.py::test_default_timeout_parameter` | app + CLI |
| CA falla la creación de un worktree → 2, sin lanzar runners | `test_app_run.py::test_worktree_failure_aborts_before_running` (rama ya existente en un repo real) | app |
| RF-08 sin hooks ni LFS | `test_git_workspace.py::test_create_does_not_run_post_checkout_hook` | adapter |
| CA cambios sin commitear / sin seguimiento → aviso | `test_git_workspace.py::test_is_dirty_counts_untracked` + `test_app_run.py::test_dirty_repo_warns` | adapter + app |
| RNF-03 `git` ausente | `test_git_workspace.py::test_git_missing_raises_workspace_error` (`PATH` sin `git`) | adapter |
| CA no autenticado / código ≠ 0 → fallido, sigue | `test_claude.py::test_nonzero_exit_fails` (`claude` falso) + `test_app_run.py::test_failed_run_continues` | adapter + app |
| CA código 0 con `is_error` → fallido | `test_claude.py::test_exit_0_with_is_error_fails` (`claude` falso) + `test_claude.py::test_parse_result_real_capture` (salida real de v2.1.303) | adapter |
| Precedencia de motivos | `test_claude.py::test_nonzero_exit_takes_precedence_over_is_error` | adapter |
| Tokens y coste | `test_claude.py::test_parse_result_sums_cache_tokens` | adapter |
| RF-13 sin restringir ajustes | `test_claude.py::test_argv_does_not_restrict_settings` (sin `--setting-sources` ni `--bare`) | adapter |
| CA timeout mata el grupo | `test_claude.py::test_timeout_kills_process_group` (el `claude` falso lanza un hijo que escribe su PID y duerme; se comprueba que los dos han muerto) | adapter |
| Bloqueante: hijo vivo tras salida normal | `test_claude.py::test_orphan_child_killed_after_normal_exit` (el `claude` falso deja un hijo con su stderr abierto y sale con 0; `run` termina y el hijo está muerto) | adapter |
| Stdin: prompt grande / proceso que no lee | `test_claude.py::test_large_prompt_not_read_does_not_hang` (1 MB de prompt, el falso sale sin leer) | adapter |
| Salida no UTF-8 | `test_claude.py::test_non_utf8_output_is_logged` | adapter |
| CA Ctrl-C | `test_app_run.py::test_interrupt_marks_current_and_pending` (el runner falso lanza `KeyboardInterrupt`) + `test_claude.py::test_interrupt_kills_group_and_reraises` (`signal.pthread_kill(main_thread, SIGINT)` desde un temporizador) | app + adapter |
| SIGTERM / SIGHUP | `test_cli_run.py::test_sigterm_handler_raises_keyboard_interrupt` (instala el manejador de `main` y envía SIGTERM al propio proceso) | CLI |
| Interrupción antes de empezar | `test_app_run.py::test_interrupt_before_start_lists_worktrees` | app |
| Fallo de `save` | `test_app_run.py::test_save_failure_stops_with_exit_1` (directorio de la ejecución sin permiso de escritura, `skipif` como root) | app |
| CA aviso de `bypassPermissions` | `test_claude.py::test_check_warns_bypass` | adapter |
| CA / Seguridad: `SECRET_X` no llega al agente ni a los resultados ni a la salida | `test_claude.py::test_secret_env_not_passed` (el `claude` falso registra su entorno) + `test_json_store.py::test_results_do_not_contain_env_values` + `test_cli_run.py::test_secret_not_in_output` | adapter + CLI |
| CA / Seguridad: credencial enmascarada en los logs | `test_claude.py::test_credential_masked_in_logs` (el `claude` falso imprime `ANTHROPIC_API_KEY` en stdout y stderr) | adapter |
| CA logs JSONL válidos + stderr aparte | `test_claude.py::test_stdout_and_stderr_logs` | adapter |
| CA / Seguridad: metacaracteres de shell | `test_claude.py::test_argv_and_stdin_are_literal` (`model="-x; rm -rf $(…)"` y un prompt así llegan literales al `claude` falso; no se crea ningún fichero) | adapter |
| Seguridad: `--ref` con forma de opción | `test_git_workspace.py::test_resolve_rejects_option_like_ref` + `test_cli_run.py::test_option_like_ref_exit_2` (`--ref=--foo`: código 2 y no se crea el directorio de salida) | adapter + CLI |
| RF-22 reescritura tras cada config | `test_app_run.py::test_results_saved_after_each_config` | app |
| RNF-03 sin traza | Los tests de CLI comprueban que stderr no contiene `Traceback` | CLI |
| P5 | `test_app_run.py::test_runner_names_are_injected` (nombre inventado) | app |
| Extremo a extremo con Claude real | `test_claude_integration.py` (`@pytest.mark.integration`, modelo `haiku`, repo mínimo en `tmp_path`) | integración |

## Riesgos
- **Formato de stream-json:** cambia entre versiones. `parse_result` es tolerante: los campos
  ausentes quedan en `null`. Hay un test con una salida real capturada (v2.1.303).
- **`subtype` no es fiable:** vale `"success"` incluso con `is_error: true` (comprobado). Se usa
  solo `is_error`.
- **El `claude` falso puede divergir del real:** se mitiga con el test sobre una captura real y
  con el test `integration`.
- **Señales:** SIGINT, SIGTERM y SIGHUP terminan el grupo del agente. SIGKILL a la CLI no se puede
  capturar: el agente seguiría vivo (se documenta). Un segundo Ctrl-C durante la limpieza puede
  dejar procesos vivos (se documenta).
- **Hijos que escapan del grupo:** un proceso que el agente lance con `setsid` sale del grupo y
  no se termina. Sin sandbox no se puede evitar (se documenta).
- **Ramas en conflicto:** si se reutiliza `--output-dir` con otro repo, `ia-testing/<run-id>/<id>`
  podría existir ya; entonces falla la creación del worktree y el código es 2.
- **Enmascarado por línea:** un secreto partido por un salto de línea no se enmascara (los tokens
  no contienen saltos de línea).
- **Versión de git:** `--end-of-options` necesita git 2.24 o posterior; las refs que empiezan por
  `-` se rechazan antes de llamar a git, así que con versiones anteriores solo falla la
  resolución con un error claro.
- **Tamaño de las PRs:** 5 PRs de 400 líneas como máximo (columna PR):
  1. `domain` + workspace git + almacén JSON;
  2. `app/run.py`;
  3. `_process.py`;
  4. `claude.py` + registro + `claude` falso;
  5. CLI + report + documentación de uso.

## Decisiones abiertas
Decisiones tomadas por @aitormf (2026-10-20), a confirmar al aprobar el plan:
1. Ejecutable `claude` falso en los tests, con la regla de AGENTS.md ampliada.
2. Tokens de entrada = entrada sin caché + lectura de caché + creación de caché.
3. Una interrupción antes de lanzar runners (pasos 1 a 6) termina con código 2, sin traza y
   listando los worktrees ya creados; no se escribe `results.json`.
4. Si no hay evento `result`, el estado depende solo del código de salida (aplicación literal de
   RF-18).
5. Para RF-18 se usa el último evento `result` del stream.
6. Respuestas a `review-plan.md`: 1A, 2A (worktrees en `worktrees/<id>/`, cambio en RF-07 de la
   spec), 3A, 4A, 5A, 6A y 7A.
7. El `Runner` devuelve `Execution`, no `RunResult` (ver "Desviación de la spec").
8. `test_default_timeout`: comprueba que, sin `--timeout`, el `RunRequest` que recibe el runner
   tiene `timeout_s = 1800`. Como `cli` usa el registro real, se hace a nivel de `app` con el
   valor por defecto de `RunOptions`, más un test de CLI que inspecciona el valor por defecto del
   parámetro.
