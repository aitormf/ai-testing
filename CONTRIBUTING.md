# Cómo contribuir a ia-testing

Este documento explica cómo preparar el entorno, cómo proponer cambios y qué se espera de una PR. Vale igual si programas a mano, con asistentes de IA o con agentes autónomos.

**Lecturas previas:**
- [`README.md`](README.md): qué es el proyecto.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): estructura, capas y **principios innegociables**.
- [`docs/adr/`](docs/adr/README.md): decisiones tomadas y por qué.
- [`AGENTS.md`](AGENTS.md): instrucciones para agentes de IA (útil también para personas: resume comandos y límites).

## 1. Preparar el entorno

Requisitos: [uv](https://docs.astral.sh/uv/) y git. uv instala Python 3.13 según `.python-version`. Las herramientas que se comparan (Karajan Code, Claude Code, Codex…) solo hacen falta para los tests de integración y para usar la CLI de verdad.

```bash
git clone git@github.com:aitormf/ai-testing.git
cd ai-testing
uv sync                     # crea .venv e instala dependencias desde uv.lock
uv tool install prek        # o pre-commit
prek install                # activa los hooks de pre-commit
./scripts/check.sh          # debe terminar en verde
```

Si `./scripts/check.sh` no pasa en un clon limpio, es un bug: abre un issue.

## 2. Comandos habituales

| Acción | Comando |
|---|---|
| Verificación completa (lo mismo que CI) | `./scripts/check.sh` |
| Tests (sin herramientas externas) | `uv run pytest` |
| Un test concreto | `uv run pytest tests/test_x.py::test_y` |
| Tests de integración con herramientas reales | `uv run pytest -m integration` |
| Formatear | `uv run ruff format .` |
| Lint con autocorrección | `uv run ruff check --fix .` |
| Tipos | `uv run mypy` |
| Regla de capas | `uv run lint-imports` |

No uses `pip install` ni edites `uv.lock` a mano. Para añadir dependencias, lee antes la §5.

## 3. Antes de empezar

- **Cambios pequeños** (bug evidente, typo, refactor local): adelante, directamente con una PR.
- **Cambios medianos o grandes** (runner nuevo, tipo de tarea nuevo, varios módulos): escribe antes una spec en `docs/specs/`.
- **Cambios de arquitectura** (capas, aislamiento de las ejecuciones, romper un principio) y **dependencias nuevas**: necesitan un **ADR** en `docs/adr/` en la misma PR. Usa `docs/adr/0000-plantilla.md`.

Antes de implementar, revisa tu plan contra los principios innegociables de `docs/ARCHITECTURE.md`.

## 4. Flujo de trabajo con git

- Rama desde `main`, con el formato `<tipo>/<descripcion-corta>`: `feat/runner-codex`, `fix/parsing-karajan`, `docs/adr-worktree`.
- Nadie hace push directo a `main`; todo entra por PR.
- Las PRs se integran con **squash merge** ([ADR-0003](docs/adr/0003-squash-merge-conventional-commits.md)): el **título de la PR** es el mensaje del commit y debe seguir [Conventional Commits](https://www.conventionalcommits.org/es/) (`feat:`, `fix:`, `feat!:`, `docs:`, `refactor:`, `test:`, `chore:`). Lo valida CI.
- Los commits dentro de la rama son libres; se aplastan al integrar.
- Mensajes de commit, títulos y descripciones de las PRs, **en inglés**.
- Mantén la rama al día con `main` con rebase o merge, como prefieras: el resultado se squashea igual.
- La rama se borra automáticamente tras el merge.
- No te saltes los hooks (`--no-verify`). Si un hook falla sin motivo, arréglalo o abre un issue.

## 5. Calidad del código

Lo comprueban las herramientas (`./scripts/check.sh` y CI); aquí solo se resume:

- **Formato y lint:** ruff, con la configuración de `pyproject.toml`.
- **Tipos:** mypy. Las funciones públicas van tipadas.
- **Arquitectura:** import-linter comprueba la regla de capas y que `subprocess` no aparezca en `domain` ni en `app`.
- **Test primero (TDD):** un test cada vez: escríbelo, compruébalo en rojo, escribe solo el código que lo pasa a verde y sigue con el siguiente. En un bug, primero un test que lo reproduzca.
- **Qué se falsea en los tests:** el `Runner`, con un runner falso que implementa el Protocol, y las herramientas externas, con ejecutables o scripts falsos que generan los propios tests en `tmp_path` (por ejemplo, scripts Python lanzados con `sys.executable`). También se permite una subclase de un adapter real que solo inyecta un fallo (por ejemplo, un `KeyboardInterrupt` en una llamada concreta) y delega todo lo demás. No se parchea `subprocess`. El storage se prueba con `tmp_path` real, y `adapters/workspace/` contra un repositorio git real creado en `tmp_path`.
- **Tests con herramientas reales:** llevan el marcador `integration` y no se ejecutan por defecto.
- **Cobertura:** CI exige como mínimo un **80 %** global. No la bajes sin justificarlo.
- **Dependencias:** ninguna dependencia nueva sin la aprobación de la persona responsable y sin un ADR en la misma PR (principio P8). Comprueba que el paquete existe, está mantenido y es el que crees (cuidado con nombres parecidos).
- **Secretos:** gitleaks bloquea el commit si detecta uno. Quita el secreto; no lo silencies.

Criterios que las herramientas no comprueban y que se miran en revisión:
- **Todo el código en inglés:** identificadores, comentarios, docstrings, nombres de tests y textos de la CLI (ayuda, mensajes de error, informes). La documentación de `docs/` y estos ficheros de proceso siguen en español.
- `cli.py` sigue siendo fino (P4) y un runner nuevo no toca `domain` ni `app` (P5).
- Nombres coherentes con el glosario de `docs/ARCHITECTURE.md`.
- Sin código muerto, sin abstracciones "por si acaso" y sin dependencias innecesarias.
- Mensajes de error útiles; nada de excepciones genéricas tragadas.

## 6. Uso de IA

No se estipulan herramientas concretas: puedes usar el asistente o agente que quieras. Las reglas son las mismas que para el código escrito a mano, más estas:

1. **Respondes de todo lo que envías.** Quien abre la PR debe entender y poder explicar cada línea, la haya escrito quien la haya escrito.
2. **Revisa los diffs antes de pedir revisión**, sobre todo en `tests/`: los agentes a veces debilitan o borran tests para que pasen. Ninguna PR puede eliminar ni relajar un test sin explicar por qué.
3. **PRs pequeñas:** ≤ 400 líneas cambiadas (sin contar ficheros generados ni `uv.lock`). Si es más, divídela.
4. **Verifica, no confíes.** CI en verde es necesario pero no suficiente: prueba la CLI a mano cuando cambie comportamiento visible.
5. **Dependencias propuestas por la IA:** aplica la §5; las alucinadas o con nombres parecidos a los reales son un riesgo real.
6. **Datos y secretos:** no pegues secretos ni credenciales en herramientas de IA.
7. **Si un agente comete un error recurrente**, mejora el sistema en la misma PR o en una aparte: mejor un lint, test o hook; si no se puede, una línea en `AGENTS.md`.
8. **Ficheros de configuración de agentes:**
   - Se versionan y se revisan como código: `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.claude/skills/`, `.claude/agents/`, `.mcp.json`.
   - Son personales y **no** se versionan: `CLAUDE.local.md`, `.claude/settings.local.json`.
9. **Transparencia:** indica en la PR si una parte relevante la generó un agente (la plantilla tiene una casilla). Los co-autores automáticos (`Co-Authored-By`) **no están permitidos**: quítalos de los commits y de la descripción de la PR.

## 7. Pull requests

**Antes de abrirla:**
- [ ] `./scripts/check.sh` en verde en local.
- [ ] Tests nuevos o actualizados para el cambio.
- [ ] Documentación actualizada en la misma PR si aplica: `README.md`, `docs/ARCHITECTURE.md`, ADR, `AGENTS.md`.
- [ ] Sin cambios no relacionados (formateos masivos, renombrados de paso).
- [ ] Título en Conventional Commits y en inglés; sin `Co-Authored-By`.

**Descripción** (lo pide `.github/pull_request_template.md`): qué cambia y por qué, cómo se ha verificado, riesgos y uso de IA relevante.

**Revisión:**
- Mínimo **1 aprobación** humana de alguien que no sea el autor.
- Una revisión automática con IA es bienvenida como apoyo, pero **no sustituye** a la humana.
- El autor resuelve o responde todos los comentarios.
- Squash merge cuando CI está en verde y hay aprobación.

## 8. Documentación

| Qué cambia | Qué actualizar |
|---|---|
| Estructura, capas, integraciones, principios | `docs/ARCHITECTURE.md` (los principios requieren ADR) |
| Una decisión técnica relevante o una dependencia nueva | ADR nuevo en `docs/adr/` (los ADR no se editan: se sustituyen por otro) |
| Comandos, herramientas o trampas conocidas | `AGENTS.md` |
| Instalación o uso | `README.md` |

Lo que se decida en reuniones, chats o issues y afecte al código se lleva al repositorio. Lo que no está en el repo no existe para los agentes, ni para quien llegue dentro de seis meses.

## 9. Bugs y propuestas

- **Bugs:** issue con pasos para reproducir, comportamiento esperado frente al real, commit, versión de la herramienta externa implicada (Karajan, Claude Code…) y logs relevantes (sin secretos).
- **Propuestas:** issue describiendo el problema antes que la solución.
- **Vulnerabilidades:** no abras un issue; ver [`SECURITY.md`](SECURITY.md).
