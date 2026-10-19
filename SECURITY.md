# Política de seguridad

ia-testing es una CLI local en un repositorio privado. Solo se mantiene la rama `main`.

## Cómo informar de una vulnerabilidad

**No abras un issue ni una PR.** Escribe por privado a @aitormf con:

- Descripción del problema e impacto.
- Pasos para reproducirlo.
- Commit afectado.

## Prácticas de seguridad del proyecto

Para quien contribuye (personas y agentes de IA):

- **Ejecución de agentes:** la CLI lanza agentes de IA que ejecutan código y modifican ficheros. Cada ejecución trabaja en su propio `git worktree` ([ADR-0005](docs/adr/0005-git-worktree-por-ejecucion.md)), pero **un worktree no es un sandbox**: el agente se ejecuta con los permisos de quien lanza la CLI. Lanza solo tareas y herramientas en las que confíes.
- **Credenciales:** la CLI no lee, guarda ni registra credenciales de las herramientas externas; cada herramienta las toma del entorno, como si se lanzara a mano.
- **Resultados:** los resultados guardados en disco no contienen variables de entorno. Aun así, la salida de un agente puede incluir datos del repositorio sobre el que trabaja: revisa los resultados antes de compartirlos.
- **Secretos:** nunca en el repositorio. **gitleaks** se ejecuta en pre-commit y en CI; no se salta (`--no-verify`). Si se filtra un secreto, rótalo **inmediatamente**: borrarlo del historial no basta.
- **Dependencias:** cada dependencia nueva necesita aprobación humana y un ADR (principio P8 de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)). Dependabot avisa de vulnerabilidades.

### Agentes de IA que trabajan en este repositorio

- No se pegan secretos ni credenciales en herramientas de IA.
- Los agentes trabajan con permisos acotados (`.claude/settings.json`); los permisos personales más amplios van en `.claude/settings.local.json` (fuera de git).
- Se evita combinar en un mismo agente acceso a datos privados, contenido no fiable y capacidad de comunicarse con el exterior (*lethal trifecta*). Revísalo al añadir servidores MCP (`.mcp.json`, siempre sin credenciales).
- El código generado por IA pasa exactamente las mismas comprobaciones y revisiones que el escrito a mano.
