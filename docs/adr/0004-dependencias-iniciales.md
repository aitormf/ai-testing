---
id: ADR-0004
titulo: Dependencias iniciales del proyecto
estado: aceptado
fecha: 2026-10-19
responsables: ["@aitormf"]
etiquetas: [dependencias, toolchain]
sustituye: null
sustituido_por: null
---

# ADR-0004: Dependencias iniciales del proyecto

## Contexto

El principio P8 de `docs/ARCHITECTURE.md` exige aprobación humana y un ADR para cada dependencia nueva. Este ADR recoge las dependencias con las que arranca el proyecto, para que la regla se cumpla desde el primer commit. cyclopts tiene su propio ADR ([ADR-0002](0002-cyclopts-framework-cli.md)).

## Decisión

**Ejecución:**

| Dependencia | Para qué |
|---|---|
| cyclopts | Framework de CLI ([ADR-0002](0002-cyclopts-framework-cli.md)) |
| Rich | Salida por terminal del informe de comparación (`adapters/report/`) |

**Desarrollo:**

| Dependencia | Para qué |
|---|---|
| uv | Gestión del entorno, de Python 3.13 y del lockfile |
| ruff | Formato y lint |
| mypy | Tipado (decisión de la entrevista de arranque) |
| pytest y pytest-cov | Tests y cobertura mínima del 80 % |
| import-linter | Comprobar la regla de capas ([ADR-0001](0001-arquitectura-hexagonal-ligera.md)) |

**Hooks y CI** (no son dependencias del paquete: se ejecutan con prek, `uvx` o como GitHub Actions):

| Herramienta | Para qué |
|---|---|
| prek | Ejecutar los hooks de pre-commit (compatible con pre-commit) |
| pre-commit-hooks | Comprobaciones básicas: espacios, fin de fichero, YAML, TOML, conflictos y ficheros grandes |
| gitleaks | Detectar secretos en pre-commit y en CI |
| zizmor | Seguridad de los workflows de GitHub Actions |
| pip-audit | Vulnerabilidades conocidas en las dependencias del lockfile (CI) |
| Semgrep | Análisis estático de seguridad (CI) |
| Dependabot | Actualizar dependencias y actions, con cooldown de 7 días |
| `actions/checkout`, `astral-sh/setup-uv` | Pasos base de los workflows, fijados a un SHA |
| `amannn/action-semantic-pull-request` | Validar el título de la PR en Conventional Commits ([ADR-0003](0003-squash-merge-conventional-commits.md)), fijada a un SHA |

Las herramientas que se añadan después a los hooks o a CI se anotan en esta tabla en la misma PR que las introduzca.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Salida con `print` y formato a mano | Más código propio para tablas y colores; Rich ya era la opción prevista en la entrevista de arranque. |
| pip + venv, o Poetry | uv es más rápido, gestiona la versión de Python y el lockfile en una sola herramienta. |
| black + flake8 + isort | ruff los sustituye con una sola herramienta. |
| commitizen como hook de commit-msg | Con squash merge solo importa el título de la PR, que se valida en CI; los commits de la rama son libres ([ADR-0003](0003-squash-merge-conventional-commits.md)). |
| Script propio para validar el título de la PR | Se prefirió una action mantenida y más completa, fijada a un SHA. |

## Consecuencias

**Positivas**
- La regla P8 se cumple desde el principio.

**Negativas / costes asumidos**
- Rich añade tiempo de arranque a la CLI.

## Cumplimiento

- Cualquier dependencia que no esté aquí ni en otro ADR necesita uno nuevo en la PR que la añada.

## Referencias

- Entrevista de arranque del proyecto (2026-10-14)
