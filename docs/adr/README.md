# Architecture Decision Records

Decisiones de arquitectura del proyecto, con su contexto y las alternativas descartadas. Este directorio explica **por qué** el sistema es como es; [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) describe **cómo es**.

**Antes de cambiar** las capas, los runners, el aislamiento de las ejecuciones, el framework de CLI o una dependencia, busca aquí las decisiones relacionadas. Si tu cambio contradice un ADR aceptado, no lo cambies en silencio: propón un ADR nuevo que lo sustituya.

**Para crear uno:** copia `0000-plantilla.md` como `NNNN-titulo.md` con el siguiente número libre, ábrelo en estado `propuesto` en una PR y pasa a `aceptado` al aprobarse.

| ADR | Título | Estado | Fecha |
|---|---|---|---|
| [0001](0001-arquitectura-hexagonal-ligera.md) | Arquitectura hexagonal ligera con regla de dependencias comprobada por import-linter | aceptado | 2026-10-14 |
| [0002](0002-cyclopts-framework-cli.md) | cyclopts como framework de CLI | aceptado | 2026-10-14 |
| [0003](0003-squash-merge-conventional-commits.md) | Squash merge con Conventional Commits en el título de la PR | aceptado | 2026-10-14 |
| [0004](0004-dependencias-iniciales.md) | Dependencias iniciales del proyecto | aceptado | 2026-10-19 |
| [0005](0005-git-worktree-por-ejecucion.md) | Un git worktree por ejecución de runner | aceptado | 2026-10-19 |
