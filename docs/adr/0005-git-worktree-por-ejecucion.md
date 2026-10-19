---
id: ADR-0005
titulo: Un git worktree por ejecución de runner
estado: aceptado
fecha: 2026-10-19
responsables: ["@aitormf"]
etiquetas: [runners, aislamiento, seguridad]
sustituye: null
sustituido_por: null
---

# ADR-0005: Un git worktree por ejecución de runner

## Contexto

Los runners lanzan agentes de IA que leen, modifican y crean ficheros. Para comparar resultados, cada ejecución tiene que partir del mismo estado del código, sin interferir con las demás ni con el working tree de quien lanza la CLI. Además, interesa poder inspeccionar después lo que hizo cada agente.

## Decisión

Cada ejecución de un runner trabaja en un **`git worktree` propio**, creado para esa ejecución a partir del mismo commit. Al terminar, el worktree **se conserva**, y su ruta queda en el `RunResult`. Solo se borra con un comando de limpieza explícito.

La creación y limpieza vive en `adapters/workspace/`, que implementa un Protocol `Workspace` de `domain` y llama a `git` por `subprocess` (P3).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Directorio temporal con una copia de los ficheros | Copiar es más lento y pierde la información de git, así que no se puede obtener el diff de lo que cambió el agente con las herramientas habituales. |
| Clon completo por ejecución | Más lento y ocupa más disco que un worktree, que comparte el almacén de objetos. |
| Contenedor por ejecución | Aísla mejor, pero exige un motor de contenedores y que las CLIs de los agentes y sus credenciales funcionen dentro. Es mucha complejidad para una herramienta local. |
| Trabajar en el working tree actual | Las ejecuciones se pisarían entre sí y con el trabajo de la persona. |

## Consecuencias

**Positivas**
- Todas las ejecuciones parten del mismo commit.
- El resultado de cada agente se inspecciona con git (`git diff`, `git log`) en su worktree.
- Rápido y barato en disco.

**Negativas / costes asumidos**
- La CLI solo funciona dentro de un repositorio git.
- Los worktrees conservados ocupan disco hasta que se limpian, y aparecen en `git worktree list`.
- Un worktree no es un sandbox: el agente sigue pudiendo escribir fuera de él con los permisos de quien lo lanza.

**Riesgos y cómo se mitigan**
- Acumulación de worktrees → comando de limpieza explícito.
- Lanzar fuera de un repositorio git → error claro antes de ejecutar ningún runner.

## Cumplimiento

- Invariante en `docs/ARCHITECTURE.md` §6.
- Tests de `adapters/workspace/` contra un repositorio git real creado en `tmp_path`.

## Referencias

- Conversación de definición del contexto del proyecto (2026-10-19).
