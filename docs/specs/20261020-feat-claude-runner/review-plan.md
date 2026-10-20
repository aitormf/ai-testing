# Revisión: plan de Runner de Claude Code y ejecución de tareas (`run`)

<!-- Escrita por review-spec. Es una recomendación: la aprobación la hace una persona cambiando status. -->

## Recomendación
**Devolver.** Hay un bloqueante: el plan solo termina el grupo de procesos del agente cuando vence
el timeout o se pulsa Ctrl-C. Si Claude termina normalmente y deja un descendiente vivo, ese
proceso sigue funcionando y la CLI puede quedarse colgada sin que actúe el timeout. Si la CLI
recibe SIGTERM o SIGHUP, el agente sobrevive sin control y sin restricciones de permisos.
`start_new_session=True` lo desvincula del terminal.

Lo demás está bien encaminado:
- todos los criterios de aceptación y casi todos los tests negativos de Seguridad tienen un test;
- los Protocols bastan para añadir `codex` sin tocar `domain` ni `app`;
- no hay sobreingeniería relevante.

Los hallazgos importantes tratan de:
- la colisión del `id` `logs` con el directorio de logs;
- Git LFS y los hooks en `git worktree add`;
- la escritura por stdin y la decodificación en `_process`;
- un reparto de PRs que hace imposible el TDD de `app` en la PR 1 con los dobles permitidos;
- la documentación de seguridad, que llega una PR más tarde que el código.

## Hallazgos

### Bloqueantes

1. **Componentes (`adapters/runners/_process.py`) y Riesgos ("Ctrl-C"): el grupo de procesos solo se termina con timeout o Ctrl-C (RF-19, RF-20 y CA "no queda ningún proceso hijo vivo").**
   - **Qué falla.**
     - **(a) Salida normal con descendientes vivos.** Al salir `claude` con cualquier código, el plan no llama a `killpg`. Un proceso que el agente deja en segundo plano (`npm run dev &`, un servidor MCP que no se cierra, algo con `nohup`) sigue ejecutándose sin restricciones de permisos después de "terminar" la configuración. Además, si ese descendiente hereda el stdout o el stderr del agente, el hilo lector no recibe nunca EOF. Por ejemplo, el SDK de MCP lanza los servidores stdio con `stderr: "inherit"` por defecto, y el `claude` falso del plan "se queda dormido con un proceso hijo" que hereda los pipes. Si después se hace `join()` de los hilos sin límite, `run` se cuelga indefinidamente, y el timeout ya no actúa porque `wait()` ha vuelto.
     - **(b) SIGTERM o SIGHUP a la CLI.** Puede ocurrir al cerrar el terminal, con `kill` o con `timeout(1)`. Python muere sin limpiar, y como el agente está en su propia sesión no recibe el SIGHUP del terminal. Resultado: un agente con `bypassPermissions` sigue vivo sin que nadie lo vigile. Es una exposición que crea el propio diseño (`start_new_session`) y que la spec no asume en Riesgos ni en Seguridad.
   - **Arreglo sugerido.**
     - En `run_logged`, hacer siempre `killpg(SIGTERM)` → gracia → `killpg(SIGKILL)` al terminar el proceso principal, no solo con timeout o interrupción. Tolerar `ProcessLookupError` si el grupo ya no existe.
     - Hacer `join()` de los hilos lectores con un límite y, si no terminan, cerrar los pipes.
     - Instalar en la CLI (o en `_process`, mientras dure el proceso) manejadores de SIGTERM y SIGHUP que sigan el mismo camino que la interrupción. Si se decide no hacerlo, declararlo como riesgo explícito en la spec y en SECURITY.md.
     - Añadir dos tests con el `claude` falso:
       - sale con código 0 dejando un hijo que hereda stdout: `run` vuelve en un tiempo acotado y el hijo ha muerto;
       - la CLI recibe SIGTERM: el grupo termina.

### Importantes

2. **Modelo de datos (`RunLocation`: "worktrees en `dir/<id>`, logs en `dir/logs/`"): un `id` llamado `logs` choca con el directorio de logs.**
   - **Qué falla.** El patrón de `id` (`[a-z0-9-]+`) admite `logs`. `create_run` crea `dir/logs/` vacío, y `git worktree add` acepta un directorio vacío existente. El worktree de esa configuración acabaría siendo el directorio de logs: los logs de todas las configuraciones se escribirían dentro de ese worktree como ficheros sin seguimiento, y el agente leería su propio log y los de las demás. Además, el plan no dice qué función construye las rutas `logs/<id>.jsonl`, `logs/<id>.stderr.log` y `dir/<id>`. `domain` solo lista `base_run_id`, `default_output_dir` y `branch_name`.
   - **Arreglo sugerido.** Poner los worktrees en `dir/worktrees/<id>/`, que sigue dentro de `<run-id>/` como pide la CA, o reservar el `id` `logs`. Añadir a `domain/run.py` las funciones puras de rutas (worktree y logs) con sus tests.

3. **Componentes (`adapters/workspace/git.py`): `git worktree add` inicializa Git LFS y ejecuta hooks (RF-08 y Riesgos de la spec, "`.git` compartido").**
   - **Qué falla.**
     - Si `git-lfs` está instalado de forma global, `git worktree add` aplica el filtro `smudge` y descarga los objetos LFS. Eso contradice RF-08 ("No se inicializan […] Git LFS") y puede superar el timeout de 60 s en repos grandes, lo que convertiría un repo válido en un error de código 2.
     - `git worktree add` también ejecuta el hook `post-checkout` del `.git` compartido. La spec reconoce que un agente puede dejar hooks en él. Con este diseño, el hook que deje el agente de una ejecución se ejecuta en el `run` siguiente, al crear los worktrees, antes de cualquier aviso.
   - **Arreglo sugerido.**
     - Lanzar esa llamada con `GIT_LFS_SKIP_SMUDGE=1` en el entorno.
     - Decidir si se desactivan los hooks en las llamadas de la CLI (`-c core.hooksPath=/dev/null`) o si se asume el riesgo y se documenta.
     - Revisar si 60 s bastan para el checkout de un repo grande, o usar un timeout distinto para `worktree add`.
     - Añadir a `test_git_workspace.py` un test que compruebe que no se ejecuta un `post-checkout`, si se decide desactivar los hooks.

4. **Componentes (`_process.py`): la escritura por stdin y la decodificación de la salida pueden colgar la CLI o acabar en traza (RNF-03 y contrato "nunca lanza otras excepciones").**
   - **Qué falla.**
     - El plan no dice cómo se escribe `stdin_text`. Si el hilo principal escribe un prompt mayor que el buffer del pipe (unos 64 KB) y el proceso no lee, el hilo se bloquea antes de empezar a contar el timeout. Si el proceso sale antes de leer, se produce un `BrokenPipeError` sin capturar.
     - Los hilos copian "línea a línea" sin decir si leen bytes o texto. En modo texto, una salida de error que no sea UTF-8 lanza `UnicodeDecodeError` en el hilo, que deja de vaciar el pipe. Usar `errors="replace"` alteraría el log, cosa que RF-23 no permite ("sin más filtrado que el de RF-24").
   - **Arreglo sugerido.**
     - Escribir stdin en un hilo propio (o antes de empezar a esperar, pero con el timeout ya en marcha), cerrar stdin y tratar `BrokenPipeError` como fin normal.
     - Leer y enmascarar en bytes (secretos codificados en UTF-8).
     - Añadir tests con el `claude` falso: prompt grande que no se lee, salida no UTF-8 y salida antes de leer stdin.

5. **Componentes (columna PR) frente a Pruebas y AGENTS.md: la PR 1 no se puede hacer con TDD usando solo los dobles permitidos.**
   - **Qué falla.** `app/run.py` va en la PR 1, pero sus tests usan "runner falso + git real + store real" (`test_runs_all_configs_from_same_commit`, `test_worktree_failure_aborts_before_running`), y `GitWorkspace` y `JsonResultStore` llegan en la PR 2. AGENTS.md solo permite como doble el runner falso. En la PR 1 habría que elegir entre crear un `Workspace` y un `ResultStore` falsos, lo que incumple la regla, o integrar `app` sin sus tests, lo que incumple P7.
   - **Arreglo sugerido.** Reordenar: la PR 1 con `domain/run.py` y los adapters `workspace` y `storage` (con sus tests reales), y la PR 2 con `app/run.py` y sus tests. También se pueden juntar `domain` y `app` con los dos adapters si cabe en 400 líneas. Añadir a la tabla de Pruebas en qué PR va cada test y una estimación de líneas por PR: la PR 3 (proceso, Claude, registro, ejecutable falso y unos diez tests) tiene pinta de superar 400.

6. **Componentes (documentación y `AGENTS.md`) y Comprobación de principios (P6): las reglas de seguridad y de tests se actualizan después del código que las cambia, y faltan ficheros.**
   - **Qué falla.**
     - `build_env` lee los valores de `ANTHROPIC_API_KEY` y `CLAUDE_CODE_OAUTH_TOKEN` en la PR 3. Sin embargo, §6 de ARCHITECTURE.md ("La CLI no lee […] credenciales"), SECURITY.md ("Credenciales") y AGENTS.md ("Nunca leas ni guardes credenciales de las herramientas externas") se cambian en la PR 4, y el plan no menciona reformular esa regla de AGENTS.md. Hasta la PR 4, el código contradice las tres. ARCHITECTURE §12 y CONTRIBUTING §7 piden actualizarlos en la misma PR.
     - La regla de dobles se amplía en AGENTS.md, pero CONTRIBUTING.md §5 sigue diciendo "Qué se falsea en los tests: solo el `Runner`", y ARCHITECTURE §3 (fila `tests/`) y §10 ("Tests") tampoco cambian. P6 no queda incumplido: el ejecutable falso no es una herramienta externa ni un parche de `subprocess`. Pero la redacción del principio y de esos documentos tiene que seguir siendo coherente.
   - **Arreglo sugerido.**
     - Pasar a la PR 3 los cambios de §6, de SECURITY.md ("Credenciales" y "Resultados") y de la regla de credenciales de AGENTS.md.
     - Añadir CONTRIBUTING.md §5 y ARCHITECTURE §3 y §10 a la tabla de documentos, junto a la regla de dobles.
     - Si se quiere reescribir el texto de P6, hacerlo con un ADR (ARCHITECTURE §12).

### Menores

7. **Contratos (`Runner.run → Execution`) frente a la spec ("Entidades": el `Runner` "devuelve un `RunResult`").** Separar `Execution` de `RunResult` es razonable, porque el runner no conoce la rama ni el worktree. Pero se aparta de la spec aprobada sin decirlo. Arreglo: declararlo en "Comprobación de principios" o en "Decisiones abiertas".

8. **Componentes (`cli.py`) y P4: lógica en la CLI.**
   - "Instancia los runners del registro" sobre `Mapping[str, Callable[[], Runner] | None]` exige una comprensión con condicional en `cli.py`. Arreglo: una función `build_runners()` en `registry.py`.
   - `repo=Path.cwd()` como valor por defecto se evalúa al importar el módulo. Los tests que hacen `chdir` reciben otro directorio, y la ayuda muestra una ruta absoluta. Arreglo: `Path(".")` o `None`, y resolverlo en el adapter.

9. **Modelo de datos (`RunRecord.started_at`) y `cli.py` ("pasa `datetime.now()`"): `datetime.now()` no lleva zona horaria**, pero el esquema promete ISO 8601 con zona. Arreglo: `datetime.now().astimezone()`, con un test del formato en `test_json_store.py`.

10. **Componentes (`GitWorkspace.resolve`) y Pruebas (Seguridad, "`--ref` con forma de opción"): la defensa y el test están incompletos.**
    - `git rev-parse --end-of-options` depende de la versión de git, y el plan no declara una versión mínima. Arreglo: declararla, o rechazar antes de llamar a git las refs que empiecen por `-`, como defensa adicional.
    - El test negativo de la spec pide "código 2 sin crear nada", y el plan solo lo prueba en el adapter. Arreglo: añadir `test_cli_run.py::test_option_like_ref_exit_2` con `--ref=--foo` (con `--ref --foo`, cyclopts puede tomar `--foo` como opción desconocida) y comprobar que no se crea el directorio de salida.

11. **Pruebas: cobertura parcial de algunos requisitos.**
    - CA `SECRET_X`: falta comprobar que no aparece "en la salida de la CLI". Arreglo: añadirlo a un test de CLI con el `claude` falso.
    - RF-04 (`<padre>/<repo>.ia-testing/`) y RF-07 (formato `YYYYMMDD-HHMMSS`): faltan tests de `default_output_dir` y `base_run_id`.
    - RNF-03 con `git` ausente: falta un test con un `PATH` sin `git`.
    - RF-13: ningún test comprueba que el `argv` no restringe las fuentes de ajustes.
    - `test_default_timeout` inspecciona cyclopts en lugar del valor que llega al runner. Es aceptable, pero mejor comprobar el `RunOptions` o el `RunRequest` resultante.

12. **Pruebas (`test_process.py::test_interrupt_kills_group_and_reraises`): `_thread.interrupt_main` no interrumpe una llamada bloqueante.** Desde Python 3.10 no envía una señal real, así que solo funciona si `run_logged` espera con sondeo (`wait(timeout=…)`). Arreglo: fijar en el plan que la espera es con sondeo, o usar `signal.pthread_kill(threading.main_thread().ident, SIGINT)` en el test.

13. **Componentes (`tests/fakes/claude`): detalles del ejecutable falso sin fijar.**
    - Con el entorno mínimo, un shebang `#!/usr/bin/env python3` resuelve el `python3` del sistema, no el del entorno de uv.
    - El fichero necesita el bit de ejecución en git.
    - En `test_cli_run.py`, el `fake-claude.json` tiene que estar commiteado en el repo de prueba para aparecer en el worktree.

    Arreglo: decirlo en el plan, o generar el ejecutable en `tmp_path` con `sys.executable` en el shebang.

14. **Modelo de datos y Motivos fijos: casos sin decidir.**
    - Precedencia entre `claude exited with code N` y `claude reported an error` cuando ocurren las dos cosas.
    - Duración que se guarda para la configuración interrumpida (el runner vuelve a lanzar la excepción y no devuelve `Execution`) y para las pendientes.
    - `RunRecord` no incluye el fichero de tarea, que la spec lista en "Entidades" (no en RF-22). Decidir si se guarda.

15. **Contratos (`ResultStore.save`) y Decisión abierta 3: errores en mitad de la ejecución.**
    - No se define qué pasa si `save` falla en el paso 7 (disco lleno, permisos): hoy acabaría en traza.
    - Si la interrupción llega durante el paso 6, ya puede haber worktrees creados. La decisión 3 no dice si se listan, como pide RF-09 para el fallo de creación.

    Arreglo: convertir el fallo de `save` en un error con motivo fijo, y listar los worktrees creados en el error "interrupted before start".

## Principios y ADRs
- **P1:** se cumple. `domain/run.py` usa solo la stdlib, y `pathlib` solo para operaciones de ruta.
- **P2 / ADR-0001:** se cumple. `app` recibe `Mapping[str, Runner | None]` y no importa `adapters`.
- **P3:** se cumple. El `subprocess` está en `workspace/git.py` y `runners/_process.py`, con lista de argumentos, sin shell y con timeout. El prompt va por stdin y el modelo como `--model=<model>`, así que ninguno de los dos puede tomarse por una opción. Ver los hallazgos 1 y 4 sobre el ciclo de vida del proceso.
- **P4 / ADR-0002:** se cumple en lo esencial. Ver el hallazgo 8.
- **P5 / RNF-01:** el contrato basta. Para `codex` bastaría un `codex.py` que use `_process.run_logged`, su `check` (`which`, avisos) y su `Execution` (coste a `None` si no lo informa), además de cambiar `None` por la clase en `RUNNERS`. `RunRequest` lleva todo lo que necesita un runner de CLI (configuración, worktree, timeout y logs). El test con un nombre inventado lo protege.
- **P6:** no hay choque. El ejecutable falso no es una herramienta externa ni parchea `subprocess`. La regla de AGENTS.md la aprobó @aitormf. Falta coherencia documental (hallazgo 6).
- **P7:** en riesgo con el reparto actual de PRs (hallazgo 5).
- **P8:** se cumple. Solo stdlib y cyclopts.
- **ADR-0005:** se cumple (worktree y rama por configuración, desde el mismo commit, que se conservan). Ver el hallazgo 3 sobre LFS y hooks.
- **Invariantes de §6, SECURITY.md y AGENTS.md:** su cambio está aprobado en la spec, pero llega una PR tarde (hallazgo 6).

## Preguntas
- ¿Se desactivan los hooks en las llamadas a `git` de la CLI, o se asume y documenta que `post-checkout` se ejecuta al crear los worktrees (hallazgo 3)?
- ¿Se manejan SIGTERM y SIGHUP como una interrupción, o se acepta y documenta que el agente puede sobrevivir a la CLI (hallazgo 1)?
- Decisiones abiertas 1 a 5: son coherentes con la spec y no contradicen ningún requisito. Las tiene que confirmar la persona que apruebe. Ver el hallazgo 15 sobre la decisión 3.

## Riesgos
- Claude Code rechaza el modo sin permisos cuando se ejecuta como root. En ese caso, todas las configuraciones fallarían con `claude exited with code 1`, sin una pista clara. Conviene mencionarlo en `docs/run.md`.
- Un `--output-dir` dentro del propio repositorio crea worktrees anidados que aparecen como ficheros sin seguimiento, y hace saltar el aviso de RF-06 en el `run` siguiente. La spec no lo prohíbe; conviene documentarlo.
