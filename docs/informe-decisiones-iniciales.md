# Informe de decisiones iniciales: ia-testing

- **Fecha:** 2026-10-14
- **Origen:** entrevista de arranque del proyecto
- **Estado:** decisiones aceptadas. Las opciones descartadas quedan registradas como base para futuros ADRs.

---

## 1. Qué es el proyecto y qué queda fuera

> **ia-testing** es una CLI local para comparar cómo resuelven tareas de programación distintos agentes de IA. Lanza la misma tarea contra varios *runners* y recoge los resultados para poder compararlos. La primera versión usa [Karajan Code](https://karajancode.com), y el diseño permite añadir más tareas y llamar directamente a las CLIs de los agentes (Claude Code, Codex, Gemini CLI…).
>
> **Queda fuera:** no es un servicio ni tiene interfaz web; todo se ejecuta en la máquina de quien la usa. No instala ni gestiona las herramientas externas ni sus credenciales, sino que da por hecho que ya están en el sistema.

Este texto va a `README.md` y a `docs/ARCHITECTURE.md`.

### Ejes de crecimiento previstos

1. **Runners:** con qué se ejecuta la tarea. Hoy es Karajan; más adelante, las CLIs de los agentes directamente.
2. **Tareas:** qué trabajos se comparan.

El requisito principal es **poder ampliar sin perder simplicidad**.

---

## 2. Resumen de decisiones

| Ámbito | Decisión |
|---|---|
| Tipo | CLI local |
| Publicación | De momento no se publica. Se aplaza hasta decidir el nombre; el layout `src/` permite publicar en PyPI más adelante sin cambios estructurales. |
| Python mínimo | 3.13 |
| Framework CLI | **cyclopts** |
| Arquitectura | **Hexagonal ligera** (`domain / app / adapters / cli`) |
| Type checker | mypy |
| Integración de PRs | Squash, con el título de la PR en Conventional Commits validado en CI |
| Aprobaciones | 1 |
| Tamaño de PR | ≤ 400 líneas |
| Herramientas de IA | Sin estipular |

---

## 3. Arquitectura

### 3.1 Decisión: hexagonal ligera

```
src/ia_testing/
  domain/      Task, RunResult, Comparison + Protocols (Runner, ResultStore)
               Python puro: sin subprocess, sin I/O
  app/         casos de uso: run_comparison(), list_runners()
  adapters/
    runners/   karajan.py (más adelante claude.py, codex.py…)
    storage/   resultados en JSON en disco
    report/    salida Rich y Markdown
  cli.py       cyclopts: monta los adapters y llama a app
```

**Regla de dependencias:** `cli → adapters → app → domain`. `domain` no importa nada del proyecto.
Se comprueba en CI con **import-linter**, así que la regla no se queda en un documento.

**Cómo se amplía:** un runner nuevo es un fichero en `adapters/runners/` más una línea en el registro. Ni `domain` ni `app` cambian.

**Por qué:**
- La lógica de comparación se testea sin tener Karajan ni ninguna otra herramienta instalada, usando un runner falso.
- Todas las llamadas a aplicaciones del sistema (`subprocess`) quedan en `adapters/`. Es el punto más frágil, porque se rompe con los cambios de versión de las herramientas externas.
- Evita acoplarse a Karajan, que es explícitamente un requisito.
- Cuesta poco más que la opción plana: un par de carpetas extra.

### 3.2 Opciones descartadas

#### A: módulos planos con `Protocol`

```
src/ia_testing/
  cli.py
  models.py
  runners/  base.py (Protocol), karajan.py
  tasks/
  compare.py
  report.py
```

- **A favor:** es la más simple y se entiende en minutos.
- **En contra:** las reglas de dependencia son implícitas y nada impide romperlas. Lo previsible es que `compare.py` acabe mezclando la lógica de comparación con detalles de cada herramienta (`subprocess`, parsing de salida), justo cuando se añada el segundo runner.
- **Motivo del descarte:** no protege el eje de crecimiento principal, que es añadir runners.
- **Cuándo reconsiderarla:** si el proyecto se queda en un único runner, o se convierte en un script de uso puntual.

#### C: hexagonal con plugins por *entry points*

Igual que la opción elegida, pero los runners se descubren con `importlib.metadata.entry_points(group="ia_testing.runners")`. Así se pueden publicar runners de terceros como paquetes independientes, por ejemplo `ia-testing-codex`.

- **A favor:** terceros pueden ampliar la herramienta sin tocar el repo.
- **En contra:**
  - Más complejidad: descubrimiento, errores de carga y versionado de la interfaz `Runner` como API pública.
  - Requiere publicar el paquete, y eso está aplazado.
- **Motivo del descarte:** resuelve un caso que hoy no existe (YAGNI).
- **Cuándo reconsiderarla:** cuando haya demanda de runners mantenidos fuera del repo. Se puede añadir sobre la arquitectura elegida sin reestructurar.

---

## 4. Framework de CLI

### 4.1 Decisión: cyclopts

**Por qué:**
- La firma de la función define la CLI y mypy comprueba los tipos de verdad.
- Soporta tipos ricos (`Union`, `Literal`, dataclasses, Pydantic como grupos de parámetros). Esto es útil para describir tareas y configuraciones de runners.
- Saca la ayuda de cada parámetro del *docstring*, sin repetirla en `Annotated`.
- Incluye configuración por variables de entorno y TOML.
- No depende de Click.

**Riesgos aceptados:**
- Comunidad más pequeña que la de Typer o Click, con menos ejemplos y respuestas.
- Su API ha cambiado más entre versiones mayores.
- Mitigación: fijar la versión mayor en `pyproject.toml` y mantener `cli.py` fino, solo parseo y delegación a `app`. Así un cambio de framework afectaría a un único fichero.

### 4.2 Opciones descartadas

#### Typer

- **A favor:**
  - Es la opción madura y conocida, de los autores de FastAPI.
  - Funciona sobre Click, con un ecosistema enorme.
  - Trae autocompletado y `CliRunner` para tests.
  - También es *type-hint first*.
- **En contra:**
  - Soporte limitado de tipos complejos (uniones, dataclasses como parámetro).
  - Hereda *quirks* de Click, como los booleanos `--x/--no-x`.
  - Arranque más lento por cargar Click y Rich.
- **Motivo del descarte:** cyclopts cubre mejor los tipos ricos previstos y saca la ayuda del docstring.
- **Cuándo reconsiderarlo:** si la madurez o la comunidad de cyclopts dan problemas, por ejemplo cambios de API frecuentes o bugs sin resolver.

#### argparse (stdlib)

- **A favor:** no tiene dependencias, arranca lo más rápido posible y tiene estabilidad garantizada.
- **En contra:**
  - La declaración de los argumentos va separada de la función.
  - `Namespace` no tiene tipos, así que mypy no ve nada.
  - Subcomandos, *dispatch*, autocompletado y tests van a mano.
  - Mucho *boilerplate*.
- **Motivo del descarte:** cero dependencias no es un requisito, y perder el tipado contradice la elección de mypy.
- **Cuándo reconsiderarlo:** si apareciera un requisito duro de cero dependencias.

#### Click

- **Motivo del descarte:** se mencionó como alternativa, pero no se evaluó en profundidad. Es más explícito, con decoradores, y no usa los *type hints* como contrato. Typer cubre su caso de uso con menos código.

---

## 5. Proceso del equipo

- **Integración:** squash merge. El título de la PR sigue Conventional Commits (`feat:`, `fix:`, `feat!:`…) y se valida en CI. Se eligió frente a merge commit por:
  - historial lineal de una PR por commit;
  - reverts triviales;
  - cherry-picks limpios;
  - compatibilidad con versionado y changelog automáticos;
  - no exigir disciplina de commits dentro de la rama.
- **Coste asumido:**
  - bisect y blame de grano grueso;
  - fricción con *stacked PRs*;
  - `git branch --merged` no detecta las ramas squasheadas, así que conviene activar el borrado automático de ramas en GitHub.
- **Aprobaciones:** 1 revisión humana.
- **Tamaño de PR:** ≤ 400 líneas; si es mayor, se parte.
- **Herramientas de IA:** no se estipulan.

---

## 6. Decisiones aplazadas

| Tema | Estado | Disparador para decidir |
|---|---|---|
| Nombre del paquete y del comando | Pendiente | Antes de la primera publicación |
| Publicación en PyPI | Aplazada | Cuando la idea esté madura y haya nombre |
| Plugins por *entry points* | Descartado por ahora | Demanda de runners externos al repo |

---

## 7. ADRs sugeridos

| ADR | Título | Fuente |
|---|---|---|
| 0001 | Arquitectura hexagonal ligera con regla de dependencias comprobada por import-linter | §3 |
| 0002 | cyclopts como framework de CLI | §4 |
| 0003 | Squash merge con Conventional Commits en el título de la PR | §5 |
