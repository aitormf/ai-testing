---
id: ADR-0003
titulo: Squash merge con Conventional Commits en el título de la PR
estado: aceptado
fecha: 2026-10-14
responsables: ["@aitormf"]
etiquetas: [proceso, git, ci]
sustituye: null
sustituido_por: null
---

# ADR-0003: Squash merge con Conventional Commits en el título de la PR

## Contexto

Hay que decidir cómo se integran las PRs en `main` y cómo se nombran los cambios. Se quiere un historial legible y la puerta abierta a versionado y changelog automáticos, sin exigir disciplina de commits dentro de cada rama.

## Decisión

Integramos las PRs con **squash merge**. El título de la PR sigue [Conventional Commits](https://www.conventionalcommits.org/es/) (`feat:`, `fix:`, `feat!:`…) y se valida en CI, porque es el mensaje del commit resultante. Se activa en GitHub el borrado automático de ramas tras el merge.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Merge commit | Conserva cada commit de la rama, pero el historial deja de ser lineal y obliga a cuidar los commits intermedios para que sean útiles. |
| Rebase merge | Historial lineal, pero también exige commits limpios dentro de la rama. No se evaluó en profundidad. |

## Consecuencias

**Positivas**
- Historial lineal: una PR, un commit.
- Reverts triviales y cherry-picks limpios.
- Compatible con versionado y changelog automáticos.
- No hace falta disciplina de commits dentro de la rama.

**Negativas / costes asumidos**
- `git bisect` y `git blame` de grano grueso.
- Fricción con *stacked PRs*.
- `git branch --merged` no detecta las ramas squasheadas.

**Riesgos y cómo se mitigan**
- Ramas huérfanas acumuladas → borrado automático de ramas en GitHub.
- Títulos que no cumplen el formato → validación en CI.

## Cumplimiento

- Verificación automática: job de CI que valida el título de la PR.
- Configuración del repositorio: solo squash merge habilitado y borrado automático de ramas.
- Proceso documentado en `CONTRIBUTING.md`.

## Referencias

- Entrevista de arranque del proyecto (2026-10-14)
