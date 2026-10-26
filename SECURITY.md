# Política de seguridad

ia-testing es una CLI local de código abierto. Solo se mantiene la rama `main`.

## Cómo informar de una vulnerabilidad

**No abras un issue, PR ni discusión pública.** Usa [GitHub Private Vulnerability Reporting](https://github.com/aitormf/ai-testing/security/advisories/new) (pestaña *Security* → *Report a vulnerability*) e incluye:

- Descripción del problema e impacto.
- Pasos para reproducirlo.
- Commit afectado.

## Prácticas de seguridad del proyecto

Para quien contribuye (personas y agentes de IA):

- **Ejecución de agentes:** la CLI lanza agentes de IA que ejecutan código y modifican ficheros. Cada ejecución trabaja en su propio `git worktree` ([ADR-0005](docs/adr/0005-git-worktree-por-ejecucion.md)), pero **un worktree no es un sandbox**: el agente se ejecuta con los permisos de quien lanza la CLI. Lanza solo tareas y herramientas en las que confíes.
  - **Claude Code se lanza con `bypassPermissions`**, sin restricciones de herramientas: puede leer y escribir fuera de su worktree (incluidos `.env`, `~/.ssh` o `~/.claude/.credentials.json`), acceder a la red y ejecutar cualquier comando con tus permisos. `run` lo avisa en la salida de error al empezar. Claude Code carga también tus ajustes y los del repo evaluado (`.claude/`: hooks, servidores MCP, skills), que se ejecutan con tus permisos; trata el repo evaluado como entrada no fiable.
  - El worktree comparte `.git` con tu repositorio (`config`, `hooks`, `refs`): el agente puede dejar hooks que se ejecutarán en tu próximo commit, crear o borrar ramas o hacer `git push`. Una configuración puede leer los worktrees y los logs de las anteriores.
  - Si se interrumpe la CLI (Ctrl-C, SIGTERM, SIGHUP) se termina el grupo de procesos del agente; un SIGKILL a la CLI no se puede capturar y el agente seguiría vivo, igual que un proceso que escape del grupo (`setsid`).
- **Credenciales:** la CLI no lee ficheros de credenciales de las herramientas externas ni guarda credenciales. Al agente solo le pasa un entorno mínimo: variables de funcionamiento (`PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM`, `TMPDIR`) y, si existen, las credenciales `ANTHROPIC_API_KEY` y `CLAUDE_CODE_OAUTH_TOKEN`; el resto de tu entorno no llega al agente. Los valores de esas credenciales se enmascaran (`***`) en los logs.
- **Resultados y logs:** los resultados guardados en disco no contienen variables de entorno. Los logs del agente (`logs/<id>.jsonl` y `logs/<id>.stderr.log`) se guardan sin más filtrado que el enmascarado de esas credenciales: pueden contener cualquier cosa que el agente haya leído o ejecutado, por ejemplo un secreto que lea de un fichero y escriba en su salida (no se enmascara). Un secreto partido entre dos líneas tampoco. Revisa los logs y los resultados antes de compartirlos.
- **Secretos:** nunca en el repositorio. **gitleaks** se ejecuta en pre-commit y en CI; no se salta (`--no-verify`). Si se filtra un secreto, rótalo **inmediatamente**: borrarlo del historial no basta.
- **Dependencias:** cada dependencia nueva necesita aprobación humana y un ADR (principio P8 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)). Dependabot avisa de vulnerabilidades.

### Agentes de IA que trabajan en este repositorio

- No se pegan secretos ni credenciales en herramientas de IA.
- Los agentes trabajan con permisos acotados (`.claude/settings.json`); los permisos personales más amplios van en `.claude/settings.local.json` (fuera de git).
- Se evita combinar en un mismo agente acceso a datos privados, contenido no fiable y capacidad de comunicarse con el exterior (*lethal trifecta*). Revísalo al añadir servidores MCP (`.mcp.json`, siempre sin credenciales).
- El código generado por IA pasa exactamente las mismas comprobaciones y revisiones que el escrito a mano.
