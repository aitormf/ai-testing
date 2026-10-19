---
id: ADR-0001
titulo: Arquitectura hexagonal ligera con regla de dependencias comprobada por import-linter
estado: aceptado
fecha: 2026-10-14
responsables: ["@aitormf"]
etiquetas: [arquitectura, capas, runners]
sustituye: null
sustituido_por: null
---

# ADR-0001: Arquitectura hexagonal ligera con regla de dependencias comprobada por import-linter

## Contexto

ia-testing compara cómo resuelven tareas de programación distintos agentes de IA. Crece en dos ejes: runners (hoy Karajan; después las CLIs de Claude Code, Codex, Gemini CLI…) y tareas. El requisito principal es poder ampliar sin perder simplicidad y sin acoplarse a Karajan.

Las llamadas a herramientas externas (`subprocess`) son el punto más frágil: se rompen con los cambios de versión de esas herramientas. La lógica de comparación tiene que poder testearse sin ninguna de ellas instalada.

## Decisión

Organizamos el código en cuatro capas dentro de `src/ia_testing/`:

- `domain/`: `Task`, `RunResult`, `Comparison` y los Protocols (`Runner`, `ResultStore`…). Python puro, sin E/S ni `subprocess`.
- `app/`: casos de uso (`run_comparison()`, `list_runners()`).
- `adapters/`: `runners/`, `storage/`, `report/`… Todas las llamadas a `subprocess` viven aquí.
- `cli.py`: monta los adapters y llama a `app`.

La regla de dependencias es `cli → adapters → app → domain`, y `domain` no importa nada del proyecto. La comprueba import-linter en CI.

Un runner nuevo es un fichero en `adapters/runners/` más una línea en el registro; `domain` y `app` no cambian.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| A: módulos planos con `Protocol` (`cli.py`, `models.py`, `runners/`, `compare.py`, `report.py`) | Es la más simple, pero las reglas de dependencia son implícitas y nada impide romperlas. Lo previsible es que `compare.py` acabe mezclando la comparación con detalles de cada herramienta (`subprocess`, parsing) justo al añadir el segundo runner. No protege el eje de crecimiento principal. **Reconsiderar** si el proyecto se queda en un único runner o pasa a ser un script de uso puntual. |
| C: hexagonal con plugins por *entry points* (`importlib.metadata.entry_points(group="ia_testing.runners")`) | Permite runners de terceros como paquetes (`ia-testing-codex`), pero añade descubrimiento, errores de carga y versionado de `Runner` como API pública, y exige publicar el paquete, que está aplazado. Resuelve un caso que hoy no existe (YAGNI). **Reconsiderar** cuando haya demanda de runners mantenidos fuera del repo; se puede añadir sobre esta arquitectura sin reestructurar. |

## Consecuencias

**Positivas**
- La lógica de comparación se testea con un runner falso, sin Karajan ni otras herramientas.
- La fragilidad de las herramientas externas queda confinada en `adapters/`.
- Añadir runners no toca el núcleo.

**Negativas / costes asumidos**
- Un par de carpetas más que la opción plana.
- Algo de ceremonia: Protocols en `domain` y montaje explícito en `cli.py`.

**Riesgos y cómo se mitigan**
- Que la regla de capas se quede en el papel → contratos de import-linter en CI.

## Cumplimiento

- Verificación automática: contratos de import-linter en `pyproject.toml` (capas y `subprocess` prohibido en `domain` y `app`).
- Principios P1, P2, P3 y P5 de `docs/ARCHITECTURE.md`.
- Instrucción para agentes: convención de dónde va un runner nuevo en `AGENTS.md`.

## Referencias

- `docs/informe-decisiones-iniciales.md` §3
