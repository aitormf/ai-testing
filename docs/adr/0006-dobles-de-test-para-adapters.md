---
id: ADR-0006
titulo: Dobles de test permitidos para los adapters que lanzan procesos
estado: propuesto
fecha: 2026-10-21
responsables: ["@aitormf"]
etiquetas: [tests, runners, subprocess]
sustituye: null
sustituido_por: null
---

# ADR-0006: Dobles de test permitidos para los adapters que lanzan procesos

## Contexto

El principio P6 dice que los tests por defecto no necesitan herramientas externas y que el único doble es un runner falso que implementa `Runner`. Con ese doble se prueba `app`, pero no los adapters que lanzan procesos (`_process.py`, `claude.py`): su trabajo es justamente arrancar un proceso, aplicar un timeout, matar su grupo de procesos, enmascarar credenciales y registrar logs. Un runner falso no ejercita nada de eso.

Parchear `subprocess` tampoco sirve: el test acabaría comprobando el parche y no el comportamiento real, y P6 lo prohíbe. Probar esos adapters solo con las herramientas reales los haría lentos, dependientes de la red y de una sesión autenticada, y no reproducibles en CI.

Además, el caso de uso `run_task` tiene un camino que ningún runner falso puede provocar: una interrupción (Ctrl-C) entre la creación de dos worktrees, para comprobar que el error lista los que ya existen.

## Decisión

Los dobles de test permitidos son:

1. Un **runner falso** que implementa el Protocol `Runner` (`tests/fake_runner.py`).
2. **Ejecutables o scripts falsos** generados por los propios tests en `tmp_path` (por ejemplo, scripts Python lanzados con `sys.executable`; `tests/fakes.py` genera el `claude` falso), para los adapters que lanzan procesos.
3. Una **subclase de un adapter real que solo inyecta un fallo** (por ejemplo, un `KeyboardInterrupt` en una llamada concreta) y delega todo lo demás en el adapter real.

Sigue prohibido parchear `subprocess`. Los tests con herramientas reales siguen llevando `@pytest.mark.integration` y no se ejecutan por defecto.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Parchear `subprocess` | El test verifica el parche, no el comportamiento del proceso (timeout, grupo de procesos, E/S). Es lo que P6 quiere evitar. |
| Probar los adapters solo con herramientas reales | Lento, necesita sesión y red, y no es reproducible en CI. |
| Mantener solo el runner falso | `_process.py` y `claude.py` quedarían sin pruebas por defecto, justo la parte más frágil (P3). |
| Dejar fuera la subclase que inyecta fallos | Se perdería la prueba de que la interrupción durante la preparación lista los worktrees ya creados. |

## Consecuencias

**Positivas**
- Los adapters que lanzan procesos se prueban con procesos reales, sin herramientas externas ni red.
- Los tests siguen siendo rápidos y reproducibles en cualquier máquina y en CI.

**Negativas / costes asumidos**
- El ejecutable falso puede divergir del real. Se mitiga con una captura real de la salida de Claude Code en `tests/data/` y con un test de integración.
- La subclase que inyecta un fallo depende del orden de las llamadas de `app` al adapter, así que un cambio de ese orden puede romperla.

**Riesgos y cómo se mitigan**
- Que "subclase que inyecta un fallo" se use para sustituir comportamiento y no solo para fallar → la revisión de PR comprueba que delega todo lo demás en el adapter real.

## Cumplimiento

- Verificación automática: ninguna; la prohibición de parchear `subprocess` se comprueba en la revisión de PR.
- Principio P6 actualizado en `docs/ARCHITECTURE.md` (sección 5); §3 y §10 describen los dobles.
- Instrucción para agentes: regla de dobles de test en `AGENTS.md` y en `CONTRIBUTING.md` §5.

## Contexto de IA

- Agente / modelo: Claude Code / claude-sonnet-5-5
- Resumen de la tarea: implementar la spec del runner de Claude Code; al hacerlo aparecieron los ejecutables falsos (aprobados en el plan) y la subclase que inyecta un fallo en `test_app_run.py`.
- Revisión humana: @aitormf aprobó la ampliación de la regla (2026-10-20 y 2026-10-21).

## Referencias

- `docs/specs/20261020-feat-claude-runner/plan.md` (decisión abierta 1).
- `tests/fakes.py`, `tests/fake_runner.py` y `InterruptingWorkspace` en `tests/test_app_run.py`.
