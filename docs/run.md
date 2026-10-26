# Comando `run`

`ia-testing run` lanza un [fichero de tarea](config_file.md) contra los runners que describe.
Cada configuración de runner se ejecuta, una tras otra y en el orden del fichero, en su propio
`git worktree` y en una rama propia, todos creados desde el mismo commit. Al terminar escribe un
resumen en la terminal y deja en disco los resultados (`results.json`) y los logs completos de cada
agente.

Por ahora solo está implementado el runner `claude` ([Claude Code](https://claude.com/claude-code)
instalado y autenticado en tu máquina; la CLI no lo gestiona). `codex` y `opencode` siguen en el
registro sin implementar: sus configuraciones aparecen como fallidas con el motivo
`runner not implemented yet`.

## Antes de usarlo: permisos y riesgos

**El agente se ejecuta sin restricciones de permisos.** Claude Code se lanza con
`--permission-mode bypassPermissions`: con los permisos de tu usuario puede leer y escribir
cualquier fichero (incluidos `.env`, `~/.ssh` o `~/.claude/.credentials.json`), acceder a la red y
ejecutar cualquier comando. `run` lo avisa en la salida de error al empezar. Lánzalo solo con
tareas y repositorios en los que confíes.

- **Un worktree no es un sandbox.** El agente puede salir de su directorio.
- **`.git` compartido.** El worktree comparte `config`, `hooks` y `refs` con tu repositorio: el
  agente puede dejar hooks que se ejecutarán en tu próximo commit, crear o borrar ramas o hacer
  `git push`.
- **Ajustes cargados.** Claude Code carga tus ajustes de usuario y los del repo evaluado
  (`.claude/`: hooks, servidores MCP, skills), que se ejecutan con tus permisos. El repo evaluado
  es una entrada no fiable. Además, los resultados no son del todo reproducibles entre máquinas.
- **Contaminación entre configuraciones.** Una configuración puede leer los worktrees y los logs
  de las anteriores, porque están en el mismo directorio de ejecución.
- **Entorno mínimo.** El agente solo recibe `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM` y
  `TMPDIR`, y las credenciales `ANTHROPIC_API_KEY` y `CLAUDE_CODE_OAUTH_TOKEN`, si existen en tu
  entorno. El resto de tu entorno (por ejemplo, otras claves de API) no llega al agente.
- **Logs.** Los valores de esas dos credenciales se sustituyen por `***` en los logs, y nada más
  se filtra: un secreto que el agente lea de un fichero y escriba en su salida **queda en el
  log**, y un secreto partido en dos líneas no se enmascara. Revisa los logs antes de compartirlos.
  Los resultados (`results.json`) no contienen variables de entorno.
- **Procesos.** Si interrumpes la CLI (Ctrl-C, SIGTERM, SIGHUP) se termina el grupo de procesos
  completo del agente, y lo mismo al vencer el timeout. Un SIGKILL a la CLI no se puede capturar y
  el agente seguiría vivo; un proceso que escape del grupo (`setsid`) tampoco se termina. Un
  segundo Ctrl-C durante la limpieza puede dejar procesos vivos.

Más detalles en [SECURITY.md](../SECURITY.md).

## Uso

```
ia-testing run <fichero> [--repo <ruta>] [--ref <ref>] [--timeout <minutos>] [--output-dir <ruta>]
```

| Opción | Por defecto | Significado |
|---|---|---|
| `<fichero>` | - | Fichero de tarea (TOML). Se valida con las mismas reglas que `validate` |
| `--repo <ruta>` | directorio actual | Repositorio a evaluar. Si es un subdirectorio, se usa la raíz del repositorio que lo contiene |
| `--ref <ref>` | `HEAD` | Commit, rama o etiqueta de partida. Se resuelve a un commit al empezar y todos los worktrees salen de él |
| `--timeout <minutos>` | `30` | Timeout de cada configuración: entero mayor que 0. Un valor no válido es un error de argumentos |
| `--output-dir <ruta>` | `<padre-del-repo>/<nombre-del-repo>.ia-testing/` | Directorio base de la salida |

Ejemplo:

```
ia-testing run task.toml --repo ~/git/mi-proyecto --ref main --timeout 45
```

Los cambios sin commitear (incluidos los ficheros sin seguimiento) **no** se copian a los
worktrees: `run` avisa de ello y continúa desde el commit. Tampoco se inicializan submódulos ni
Git LFS, y los worktrees se crean sin ejecutar hooks de git.

### Qué hace, paso a paso

1. Valida el fichero de tarea, comprueba que el repositorio es git y que la ref existe, y que la
   herramienta de cada runner implementado está instalada.
2. Crea el directorio de la ejecución y **todos** los worktrees, antes de lanzar ningún runner.
3. Lanza cada configuración en su worktree, con su `model` y su prompt, y reescribe `results.json`
   al terminar cada una.
4. Escribe el resumen.

Si algo falla en los pasos 1 y 2, no se lanza ningún runner y el código de salida es 2. Si falla
la creación de un worktree, el error indica la configuración afectada y los worktrees ya creados,
que se conservan.

Claude Code recibe el prompt por la entrada estándar y el modelo como `--model=<model>`: nunca
pasan por un shell, así que los metacaracteres se pasan literales. El `type` de la tarea
(`code-generation` o `code-review`) no cambia la ejecución: solo se guarda en `results.json`. Una
configuración `claude` con `local = true` muestra un aviso y se ejecuta igual que con
`local = false`.

## Salida

El resumen va a la salida estándar, con una línea por configuración y la ruta de `results.json`:

```text
claude-haiku  succeeded  41.2s  $0.0231  /home/yo/git/mi-proyecto.ia-testing/20261020-120000/worktrees/claude-haiku
claude-opus  failed (timeout)  1800.0s  -  /home/yo/git/mi-proyecto.ia-testing/20261020-120000/worktrees/claude-opus
opencode-local  failed (runner not implemented yet)  0.0s  -  -
results: /home/yo/git/mi-proyecto.ia-testing/20261020-120000/results.json
```

Cada línea es `<id>  <estado>  <duración>  <coste>  <worktree>`: el estado lleva el motivo entre
paréntesis si falló, el coste es `-` si la herramienta no lo informa y el worktree es `-` si no se
creó. Los avisos (`warning: ...`) y los errores van a la salida de error.

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | Todas las configuraciones terminaron en `succeeded` |
| `1` | Alguna falló (incluidos timeout, interrupción y runner no implementado), o no se pudo escribir `results.json` |
| `2` | No se pudo empezar: fichero inválido, no es un repositorio git, ref inexistente, herramienta no instalada, directorio de salida o worktree que no se pueden crear, o interrupción antes de lanzar ningún runner |

Que un fichero inválido dé `1` en `validate` y `2` en `run` es intencionado: en `run`, `1`
significa "alguna ejecución falló". Un valor no válido de `--timeout` es un error de argumentos:
la CLI lo rechaza con código 1 antes de ejecutar nada, y no crea nada.

`succeeded` significa que la herramienta terminó con código 0 y no informó de error en su salida
estructurada (para Claude, `is_error`): **no** que el agente haya resuelto bien la tarea.

## Estructura del directorio de una ejecución

```
<output-dir>/<run-id>/
├── results.json
├── logs/
│   ├── <id>.jsonl
│   └── <id>.stderr.log
└── worktrees/
    └── <id>/          # rama ia-testing/<run-id>/<id>
```

- `<run-id>` tiene el formato `YYYYMMDD-HHMMSS` en hora local. Si el directorio ya existe (dos
  `run` en el mismo segundo), se añade un sufijo: `-2`, `-3`… y el existente no se toca.
- Cada worktree está en una rama nueva `ia-testing/<run-id>/<id>`, creada desde el commit
  resuelto. Los commits que haga el agente quedan en esa rama, y los ficheros sin commitear, en el
  worktree.
- **Todo se conserva.** Los worktrees, las ramas `ia-testing/*` y los directorios de ejecución se
  acumulan hasta que exista el comando de limpieza, y solo ese comando los borrará. Para
  inspeccionar lo que hizo un agente: `git -C <worktree> log`, `git -C <worktree> status`.
- Las configuraciones con un runner no implementado no tienen worktree ni logs.
- `logs/<id>.jsonl` es la salida estructurada del agente (una línea JSON por evento) y
  `logs/<id>.stderr.log` su salida de error, ambas con las credenciales enmascaradas (`***`).

## Esquema de `results.json` (`schema_version: 1`)

Se reescribe de forma atómica al terminar cada configuración, así que queda constancia aunque la
CLI muera. No incluye el fichero de tarea ni variables de entorno. Los valores ausentes son
`null`; las rutas son absolutas.

```json
{
  "schema_version": 1,
  "run_id": "20261020-120000",
  "started_at": "2026-10-20T12:00:00+02:00",
  "task_type": "code-generation",
  "repo": "/home/yo/git/mi-proyecto",
  "ref": "HEAD",
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "results": [
    {
      "id": "claude-haiku",
      "runner": "claude",
      "model": "haiku",
      "local": false,
      "status": "succeeded",
      "reason": null,
      "duration_s": 41.2,
      "worktree": "/home/yo/git/mi-proyecto.ia-testing/20261020-120000/worktrees/claude-haiku",
      "branch": "ia-testing/20261020-120000/claude-haiku",
      "cost_usd": 0.0231,
      "input_tokens": 15230,
      "output_tokens": 912,
      "stdout_log": "/home/yo/git/mi-proyecto.ia-testing/20261020-120000/logs/claude-haiku.jsonl",
      "stderr_log": "/home/yo/git/mi-proyecto.ia-testing/20261020-120000/logs/claude-haiku.stderr.log"
    }
  ]
}
```

| Campo | Tipo | Significado |
|---|---|---|
| `schema_version` | entero | Versión del esquema (`1`) |
| `run_id` | texto | Identificador de la ejecución, con el sufijo si lo hubo |
| `started_at` | texto | Fecha de inicio, ISO 8601 con zona horaria |
| `task_type` | texto | `type` del fichero de tarea |
| `repo` | texto | Raíz del repositorio evaluado |
| `ref` | texto | Ref pedida (`--ref`) |
| `commit` | texto | Commit al que se resolvió la ref |
| `results` | lista | Un objeto por configuración, en el orden del fichero |

Cada elemento de `results`:

| Campo | Tipo | Significado |
|---|---|---|
| `id`, `runner`, `model`, `local` | texto, texto, texto, booleano | Los de la configuración, tal cual (para `claude`, `local` se guarda aunque no cambie la ejecución) |
| `status` | texto | `succeeded` o `failed` |
| `reason` | texto o `null` | Motivo del fallo; `null` si tuvo éxito |
| `duration_s` | número | Duración real en segundos; `0` para las pendientes y las no implementadas |
| `worktree`, `branch` | texto o `null` | Worktree y rama; `null` si el runner no está implementado |
| `cost_usd` | número o `null` | Coste en USD (`total_cost_usd` de Claude), si la herramienta lo informa |
| `input_tokens` | entero o `null` | Entrada sin caché + lectura de caché + creación de caché |
| `output_tokens` | entero o `null` | Tokens de salida |
| `stdout_log`, `stderr_log` | texto o `null` | Rutas de los logs; `null` si no se lanzó |

Motivos de fallo: `runner not implemented yet`, `timeout`, `interrupted`,
`claude exited with code N`, `claude reported an error` y `cannot start claude`. Ninguno incluye la
salida del agente. Si el código de salida no es 0, el motivo es `claude exited with code N` aunque
también haya `is_error`.

## Interrupción y timeout

- Al vencer el timeout se termina el grupo de procesos completo del agente (comandos, servidores
  MCP…); la configuración queda como `failed` con el motivo `timeout` y se ejecuta la siguiente.
- Con Ctrl-C (o SIGTERM / SIGHUP) se termina el grupo del agente en curso y no se lanzan las
  pendientes. `results.json` conserva lo hecho; la configuración interrumpida y las pendientes
  figuran como `failed` con el motivo `interrupted`, y el código de salida es 1. Si ocurre antes de
  lanzar ningún runner, el código es 2, no se escribe `results.json` y el error lista los
  worktrees ya creados.
- Si no se puede escribir `results.json`, se deja de ejecutar y el código es 1.
