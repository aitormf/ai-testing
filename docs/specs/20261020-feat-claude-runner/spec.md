---
status: aprobada
issue:
---

# Runner de Claude Code y ejecución de tareas (`run`)

## Objetivo
Poder lanzar de verdad un fichero de tarea contra Claude Code: cada configuración de runner se
ejecuta en su propio `git worktree`, y su resultado (estado, coste, tokens y log completo) se
guarda para inspeccionarlo. Sienta la base común (ejecución, espacio de trabajo, resultados) que
reutilizarán los siguientes runners.

## Problema que resuelve
Hoy solo se puede validar un fichero de tarea (`validate`); no hay forma de ejecutarlo. Para
comparar modelos o herramientas hay que lanzar cada agente a mano, en directorios preparados a
mano, y apuntar coste y resultado por separado, sin garantía de que todos partan del mismo código.

## Usuarios
- **Persona que evalúa agentes** (desarrollador/a, nivel técnico alto): escribe un fichero de
  tarea, lo lanza en local sobre un repositorio propio y revisa después qué hizo cada agente.
- **Quien añada el siguiente runner** (persona o agente de IA): necesita una base común clara
  para añadir Codex u OpenCode sin tocar `domain` ni `app`.

## User stories
- Como persona que evalúa agentes, quiero lanzar un fichero de tarea con varias configuraciones
  de `claude` (distintos modelos o prompts) con un solo comando, para compararlas sin preparar
  nada a mano.
- Como persona que evalúa agentes, quiero que cada ejecución parta del mismo commit en un
  worktree y una rama propios que se conserven, para inspeccionar con git lo que cambió cada
  agente.
- Como persona que evalúa agentes, quiero ver al terminar un resumen con estado, duración y coste
  de cada ejecución, y tener en disco el log completo, para analizar cómo trabajó cada una.
- Como persona que evalúa agentes, quiero que el agente no reciba mis variables de entorno y que
  sus credenciales no queden escritas en los logs, sabiendo que el agente actúa sin restricciones
  de permisos y que lo lanzo bajo mi responsabilidad.
- Como quien añade un runner, quiero que la ejecución, los worktrees y el almacenamiento sean
  comunes, para que un runner nuevo sea un fichero más una línea en el registro.

## Requisitos funcionales

### Comando y opciones
- RF-01: Existe un comando `run <fichero>` que valida el fichero de tarea con las mismas reglas
  que `validate` y, si es válido, ejecuta sus configuraciones de runner una a una, en el orden
  del fichero.
- RF-02: Por defecto el repositorio es el del directorio actual y el punto de partida su `HEAD`.
  Las opciones `--repo <ruta>` y `--ref <ref>` permiten elegir otro repositorio y otra ref. Si
  `--repo` apunta a un subdirectorio, se usa la raíz del repositorio que lo contiene.
- RF-03: `--timeout <minutos>` fija el timeout de cada configuración: entero mayor que 0, 30 por
  defecto. Un valor no válido es un error de argumentos.
- RF-04: `--output-dir <ruta>` fija el directorio base de salida. Por defecto es
  `<padre-de-la-raíz-del-repo>/<nombre-del-repo>.ia-testing/`.

### Comprobaciones previas
- RF-05: Antes de crear nada ni lanzar ningún runner, `run` comprueba que:
  - el fichero de tarea es válido; si no, escribe los errores con el mismo formato que `validate`
    en la salida de error;
  - el repositorio es un repositorio git y la ref existe;
  - la herramienta de cada runner implementado que use el fichero está instalada (para `claude`,
    que el ejecutable de Claude Code está disponible);
  - el directorio de salida se puede crear.

  Si alguna falla, muestra un error claro, no crea nada y termina con código 2.
- RF-06: Si el repositorio tiene cambios sin commitear (incluidos ficheros sin seguimiento),
  `run` avisa de que no se copian a los worktrees y continúa.

### Directorio de ejecución y worktrees
- RF-07: Cada ejecución tiene un `run-id` con formato `YYYYMMDD-HHMMSS` en hora local. Su
  directorio `<output-dir>/<run-id>/` se crea de forma exclusiva; si ya existe, se añade un sufijo
  (`-2`, `-3`…). Dentro van un worktree por cada `id` de configuración, `results.json` y `logs/`.
- RF-08: La ref se resuelve a un commit al empezar. Todos los worktrees de la ejecución se crean
  desde ese commit, **antes de lanzar ningún runner**, cada uno en una rama nueva
  `ia-testing/<run-id>/<id>`. Se conservan al terminar. No se inicializan submódulos ni Git LFS.
- RF-09: Si falla la creación de algún worktree, no se lanza ningún runner, se muestra un error
  claro con la configuración afectada y `run` termina con código 2. Los worktrees y ramas ya
  creados se conservan y se indican en el error (solo el comando de limpieza borra worktrees).
- RF-10: Las configuraciones con un runner del registro que todavía no está implementado
  (`codex`, `opencode`) no tienen worktree y producen un resultado fallido con el motivo
  "runner not implemented yet", sin detener el resto.

### Ejecución de Claude Code
- RF-11: Las configuraciones con `runner = "claude"` lanzan Claude Code en modo no interactivo
  dentro de su worktree, con su `model` y su prompt efectivo, pasados como argumentos (nunca a
  través de un shell).
- RF-12: Claude Code se lanza sin restricciones de permisos (`bypassPermissions`): puede leer,
  escribir y ejecutar cualquier cosa con los permisos del usuario del sistema. `run` lo avisa en
  la salida de error al empezar, y la documentación lo explica.
- RF-13: Claude Code carga los ajustes del usuario y los del proyecto (`.claude/` del repo
  evaluado, presente en el worktree), como al usarlo a mano dentro del repo.
- RF-14: El proceso del agente recibe solo estas variables de entorno, si existen en el entorno
  de quien lanza `run`:
  - de funcionamiento: `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM`, `TMPDIR`;
  - de credenciales: `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`.

  La lista exacta puede ajustarse en el plan si la autenticación lo requiere, manteniendo la
  separación entre las dos categorías.
- RF-15: Una configuración `claude` con `local = true` muestra un aviso de que este runner no
  distingue modelos locales y se ejecuta igual que con `local = false`; `local` se guarda tal
  cual en el resultado.
- RF-16: El `type` de la tarea (`code-generation` o `code-review`) no cambia la ejecución: el
  prompt se pasa tal cual y el `type` solo se guarda en el resultado.

### Fallos, timeout e interrupción
- RF-17: Si Claude Code no está autenticado o termina con error, el resultado de esa
  configuración es fallido con un motivo legible y la ejecución continúa con la siguiente.
- RF-18: Una configuración es `succeeded` cuando la herramienta termina con código 0 **y** no
  informa de error en su salida estructurada (para Claude, `is_error`). `succeeded` significa que
  el agente terminó, no que haya resuelto bien la tarea.
- RF-19: Al vencer el timeout se termina el grupo de procesos completo del agente (incluidos los
  procesos hijos: comandos, servidores MCP) y el resultado es fallido con el motivo "timeout".
- RF-20: Si se interrumpe `run` (Ctrl-C), se termina el grupo de procesos completo del agente en
  curso, no se lanzan las configuraciones pendientes y `results.json` queda con lo hecho: la
  configuración interrumpida y las pendientes figuran como fallidas con el motivo "interrupted".
  El código de salida es 1.

### Resultados y logs
- RF-21: Cada resultado incluye: `id`, `runner`, `model`, `local`, estado (`succeeded` |
  `failed`), motivo del fallo si lo hay, duración en segundos, ruta del worktree, rama, coste en
  USD y tokens de entrada y salida (si la herramienta los informa; si no, vacíos) y rutas de los
  logs.
- RF-22: `results.json` incluye además una versión de esquema y los datos comunes de la
  ejecución: `run-id`, fecha, `type` de la tarea, repositorio, ref pedida y commit resuelto. Se
  reescribe al terminar cada configuración, para que quede constancia aunque la CLI muera.
- RF-23: La salida estructurada del agente se guarda en `logs/<id>.jsonl` y su salida de error en
  `logs/<id>.stderr.log`, sin más filtrado que el de RF-24.
- RF-24: Antes de escribir los logs, la CLI sustituye por `***` cualquier aparición de los
  valores de las variables de credenciales de RF-14 que haya pasado al agente.
- RF-25: Al terminar, `run` muestra en la salida estándar un resumen con una línea por
  configuración (`id`, estado, duración, coste y ruta del worktree) y la ruta de `results.json`.
  Los avisos y errores van a la salida de error.

### Códigos de salida
- RF-26: `0` si todas las configuraciones acaban en `succeeded`; `1` si alguna falla (incluidos
  timeout, interrupción y runner no implementado); `2` si no se pudo empezar (RF-05, RF-09). Que
  un fichero inválido dé `1` en `validate` y `2` en `run` es intencionado: en `run`, `1` significa
  "alguna ejecución falló".

## Requisitos no funcionales
- RNF-01: Añadir el siguiente runner (Codex, OpenCode) es un fichero en `adapters/runners/` más
  una línea en el registro, sin tocar `domain` ni `app` (P5).
- RNF-02: Los tests por defecto no necesitan Claude Code instalado: usan un runner falso. La
  construcción del entorno y de los argumentos de Claude se puede probar sin lanzarlo. Los tests
  que lanzan Claude de verdad llevan `@pytest.mark.integration` (P6).
- RNF-03: Ningún fallo de una herramienta externa ni de `git` interrumpe la ejecución con un
  traceback: se convierte en un resultado fallido o, antes de lanzar runners, en un error con
  código 2.
- RNF-04: La CLI no escribe en disco ni en el terminal variables de entorno ni credenciales. En
  los logs del agente, los valores de las credenciales que pasa la CLI se enmascaran (RF-24);
  lo que el agente lea por su cuenta de ficheros u otras fuentes queda fuera de esta garantía.
- RNF-05: La ejecución es secuencial; el tiempo total es aproximadamente la suma de las
  ejecuciones.
- RNF-06: Sin dependencias nuevas.

## Casos límite
- Fichero con solo runners no implementados: no se lanza ningún agente ni se crea ningún
  worktree; todos los resultados son fallidos y el código es 1.
- Dos `run` en el mismo segundo: el segundo `run-id` lleva sufijo (`-2`) y no pisa al primero.
- Directorio de salida sin permiso de escritura: código 2 antes de crear nada.
- La herramienta termina sin informar coste o tokens: esos campos quedan vacíos.
- El agente hace commits o deja ficheros sin commitear en su worktree: se conserva tal cual; sus
  commits quedan en la rama `ia-testing/<run-id>/<id>`.
- `local = true` con `runner = "claude"`: aviso y se ejecuta (RF-15).
- Interrupción con Ctrl-C a mitad: RF-20.
- Repositorio con submódulos o Git LFS: los worktrees no los inicializan.

## Criterios de aceptación

### Ejecución normal
- Dado un fichero válido con dos configuraciones `claude` y un repositorio limpio, cuando ejecuto
  `run`, entonces se crean dos worktrees desde el mismo commit en
  `<padre>/<repo>.ia-testing/<run-id>/`, cada uno en su rama `ia-testing/<run-id>/<id>`, con sus
  logs y su entrada en `results.json`, y el código de salida es 0 si ambas terminan bien.
- Dado que ejecuto `run` sin `--repo` ni `--ref`, cuando empieza, entonces usa el repositorio del
  directorio actual y su `HEAD`; dado `--repo <subdirectorio>` y `--ref <otra-rama>`, entonces usa
  la raíz de ese repositorio y el commit de esa rama.
- Dado `--output-dir <ruta>`, cuando ejecuto `run`, entonces todo se crea en
  `<ruta>/<run-id>/`.
- Dado un `run-id` cuyo directorio ya existe, cuando ejecuto `run`, entonces se crea
  `<run-id>-2/` y el existente no se toca.
- Dada una tarea con `type = code-review`, cuando ejecuto `run`, entonces Claude recibe el mismo
  prompt que con `code-generation` y el `type` aparece en `results.json`.
- Dada una ejecución terminada, cuando miro la salida estándar, entonces hay una línea por
  configuración con `id`, estado, duración, coste y ruta del worktree, y la ruta de
  `results.json`.
- Dada una ejecución terminada, cuando abro `results.json`, entonces contiene la versión de
  esquema, los datos comunes (RF-22) y por cada configuración los campos de RF-21.

### Runners no implementados y modelos locales
- Dado un fichero con una configuración `claude` y otra `codex`, cuando ejecuto `run`, entonces la
  de `claude` se ejecuta, la de `codex` aparece como fallida con el motivo "runner not implemented
  yet" sin worktree, y el código es 1.
- Dada una configuración `claude` con `local = true`, cuando ejecuto `run`, entonces se muestra un
  aviso, se ejecuta normalmente y su resultado guarda `local = true`.

### No se puede empezar
- Dado un fichero inválido, cuando ejecuto `run`, entonces se muestran los mismos errores que con
  `validate`, no se crea ningún directorio ni worktree y el código es 2.
- Dado un directorio que no es un repositorio git, o una `--ref` inexistente, cuando ejecuto
  `run`, entonces se muestra un error claro, no se crea nada y el código es 2.
- Dado que Claude Code no está instalado y el fichero tiene alguna configuración `claude`, cuando
  ejecuto `run`, entonces se muestra un error claro, no se crea nada y el código es 2.
- Dado `--timeout 0`, `--timeout -5` o `--timeout abc`, cuando ejecuto `run`, entonces se muestra
  un error de argumentos y no se crea nada.
- Dado que falla la creación del segundo worktree, cuando ejecuto `run`, entonces no se lanza
  ningún runner, el error indica la configuración afectada y los worktrees ya creados, y el código
  es 2.

### Fallos durante la ejecución
- Dado un repositorio con cambios sin commitear o ficheros sin seguimiento, cuando ejecuto `run`,
  entonces se avisa de que no se copian y la ejecución continúa desde el commit.
- Dado que Claude Code no está autenticado o termina con código distinto de 0, cuando ejecuto
  `run`, entonces esa configuración es fallida con un motivo legible, se ejecuta la siguiente y el
  código es 1.
- Dado que Claude Code termina con código 0 pero informa `is_error`, cuando termina, entonces la
  configuración es fallida.
- Dado un runner que supera el timeout, cuando vence, entonces su grupo de procesos completo
  termina (no queda ningún proceso hijo vivo), su resultado es fallido con el motivo "timeout" y
  se ejecuta la siguiente configuración.
- Dado que no paso `--timeout`, cuando ejecuto `run`, entonces cada configuración tiene un timeout
  de 30 minutos.
- Dada una ejecución con tres configuraciones, cuando pulso Ctrl-C durante la segunda, entonces su
  grupo de procesos termina, la tercera no se lanza, `results.json` contiene la primera con su
  resultado y la segunda y la tercera como fallidas con el motivo "interrupted", y el código es 1.

### Seguridad y logs
- Al empezar `run`, se muestra en la salida de error un aviso de que el agente se ejecuta sin
  restricciones de permisos.
- Dada una variable de entorno `SECRET_X` en mi shell, cuando el agente se ejecuta, entonces
  `SECRET_X` no está en el entorno del proceso del agente, ni en `results.json`, ni en la salida
  de la CLI.
- Dado un valor de `ANTHROPIC_API_KEY` que el agente imprime en su salida o en su salida de
  error, cuando termina, entonces ese valor no aparece en `logs/<id>.jsonl` ni en
  `logs/<id>.stderr.log`, y en su lugar aparece `***`.
- Dada una ejecución terminada, cuando abro `logs/<id>.jsonl`, entonces cada línea es JSON válido
  con la salida estructurada del agente, y su salida de error está en `logs/<id>.stderr.log`.
- Dado un prompt o un `model` con metacaracteres de shell (`; rm -rf`, `$(…)`), cuando ejecuto
  `run`, entonces se pasan literales a Claude, sin ejecutarse.

## Alcance
- Comando `run` con `--repo`, `--ref`, `--timeout` y `--output-dir`.
- Base común: comprobaciones previas, ejecución secuencial, worktree y rama por configuración,
  resultados en JSON, logs con credenciales enmascaradas, resumen en terminal.
- Runner `claude` funcional. `codex` y `opencode` siguen en el registro, sin implementar.
- Documentación del comando, de `results.json` y del modelo de permisos y sus riesgos.
- Actualización en la misma PR de:
  - `docs/ARCHITECTURE.md`: §1 y §9 (Claude es el primer runner), §3 (`karajan.py`), §6
    (invariantes de credenciales y variables de entorno: la CLI elige qué variables pasa y
    enmascara las credenciales en los logs), §7 (el flujo aún no construye una `Comparison`),
    §9 (los worktrees se crean todos antes de lanzar runners) y §10 (el fichero de tarea también
    es entrada de `run`);
  - `docs/config_file.md` (el fichero también se usa con `run`);
  - `SECURITY.md` y `AGENTS.md` (permisos sin restricciones, logs del agente y su riesgo).

## Fuera de alcance
- Runners `codex`, `opencode` y Karajan.
- Ejecución en paralelo.
- Comando de limpieza de worktrees, ramas y directorios de ejecución.
- Informe o comparación entre resultados (Markdown u otro formato), más allá del resumen.
- Restringir los permisos del agente (listas de herramientas permitidas o reglas de denegación),
  sandbox a nivel de sistema operativo y contenedores.
- Elegir, por fichero de tarea o por configuración, qué skills, MCP, hooks o ajustes usa el agente
  (trabajo futuro).
- Límites de coste por ejecución.
- Copiar cambios sin commitear a los worktrees; inicializar submódulos o Git LFS.
- Comportamiento distinto según el `type` de la tarea.

## Entidades / Modelo de datos
- **Ejecución** (`run`): `run-id`, fecha, fichero de tarea, `type`, repositorio, ref pedida,
  commit resuelto, lista de resultados.
- **Resultado** (`RunResult`): `id`, `runner`, `model`, `local`, estado, motivo, duración, ruta
  del worktree, rama, coste, tokens, rutas de los logs.
- **Espacio de trabajo**: worktree y rama de una configuración dentro de una ejecución.

Responsabilidades mínimas de los Protocols que se introducen en `domain`:
- **`Runner`**: recibe la configuración de runner, la ruta de su worktree, el timeout y las rutas
  de sus logs; devuelve un `RunResult`. Él mismo aplica el timeout, termina su grupo de procesos
  y convierte cualquier fallo de la herramienta en un `RunResult` fallido (P3). Ante una
  interrupción, termina su grupo de procesos antes de propagarla.
- **`Workspace`**: crea el worktree y la rama de una configuración a partir de un commit.
- **`ResultStore`**: escribe `results.json` de una ejecución, reescribiéndolo tras cada
  configuración.
- El estado "runner no implementado" se resuelve en el registro de runners, dentro de
  `adapters`; `domain` y `app` no conocen nombres de runners.

## Dependencias
- Claude Code instalado y autenticado en la máquina (no lo gestiona la CLI).
- Fichero de tarea y validación ya existentes (`20261019-feat-test-config-file`).
- Introduce en `domain` los Protocols `Runner`, `Workspace` y `ResultStore` y el `RunResult`,
  previstos en ADR-0001 y ARCHITECTURE.md. Según AGENTS.md, cambiar Protocols de `domain` requiere
  confirmación humana: se da al aprobar esta spec.

## Riesgos
- **Agente sin restricciones**: con `bypassPermissions`, el agente puede leer y escribir fuera de
  su worktree, leer secretos de ficheros (`.env`, `~/.ssh`, `~/.claude/.credentials.json`),
  acceder a la red y ejecutar cualquier comando con los permisos del usuario. Un worktree no es
  un sandbox. Mitigación: entorno mínimo, enmascarado de credenciales en los logs, aviso visible y
  documentación en SECURITY.md; restricción de permisos y sandbox en una spec posterior.
- **`.git` compartido**: el worktree comparte `config`, `hooks` y `refs` con el repo de la
  persona; el agente puede dejar cambios persistentes en él (por ejemplo, hooks que se ejecutarán
  en su próximo commit), crear o borrar ramas, o hacer `git push`.
- **Ajustes del proyecto evaluado**: el `.claude/` del repo evaluado es una entrada no fiable y
  puede añadir hooks y servidores MCP que se ejecutan con los permisos del usuario.
- **Ajustes de usuario cargados**: los hooks, MCP y skills del usuario influyen en el resultado;
  la comparación no es del todo reproducible entre máquinas.
- **Contaminación de la comparación**: una configuración puede leer los worktrees y los logs de
  las anteriores, que están en el mismo directorio de ejecución.
- **Secretos en los logs**: solo se enmascaran las credenciales que pasa la CLI; un secreto que el
  agente lea de un fichero y escriba en su salida queda en el log.
- **Formato de salida de Claude Code**: cambia entre versiones y puede romper la lectura del coste,
  los tokens o `is_error`; el coste y los tokens deben quedar vacíos sin hacer fallar la ejecución.
- **Disco y ramas**: los worktrees y las ramas `ia-testing/*` se acumulan hasta que exista el
  comando de limpieza.

## Supuestos
- La persona usuaria tiene permiso de escritura en el directorio de salida.
- La autenticación de Claude Code funciona con el entorno mínimo (sesión de suscripción en
  `~/.claude` o una variable de credenciales de RF-14).
- El modo no interactivo de Claude Code informa del coste, los tokens y `is_error` en su salida
  estructurada.

## Preguntas abiertas
- Trabajo futuro: elegir por fichero de tarea qué skills, MCP y demás conexiones usa cada
  configuración, y aislar los ajustes de usuario y de proyecto.
- Trabajo futuro: restringir permisos del agente y sandbox de sistema operativo.

## Seguridad
- **Datos que maneja y su sensibilidad**: el código del repositorio (sensibilidad del proyecto);
  los logs del agente, que pueden contener cualquier cosa que el agente haya leído o ejecutado
  (alta); las credenciales de Claude Code, que la CLI pasa al agente si están en el entorno y
  enmascara en los logs, pero no guarda en ningún otro sitio.
- **Quién puede hacer qué**: el agente actúa con todos los permisos del usuario del sistema, sin
  restricciones de herramientas. Un worktree no es un sandbox. Se asume y se avisa (RF-12).
- **Entradas no fiables**: el fichero de tarea (validado con el esquema cerrado existente); el
  repo evaluado, incluido su `.claude/`; el prompt y la salida del agente, que se tratan como
  datos: no se interpretan como órdenes para la CLI ni se pasan por un shell; `--repo` y `--ref`
  se validan con git antes de usarlos.
- **Tests negativos requeridos**:
  - una variable de entorno del shell no llega al proceso del agente ni aparece en
    `results.json` ni en la salida;
  - una credencial que el agente imprime no aparece en los logs;
  - un prompt o un `model` con metacaracteres de shell se pasa literal, sin ejecutarse;
  - una `--ref` con forma de opción (`--foo`) o inexistente da código 2 sin crear nada;
  - un `--timeout` no válido da error de argumentos sin crear nada.
