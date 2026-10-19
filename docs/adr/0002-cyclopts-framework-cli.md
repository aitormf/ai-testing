---
id: ADR-0002
titulo: cyclopts como framework de CLI
estado: aceptado
fecha: 2026-10-14
responsables: ["@aitormf"]
etiquetas: [cli, dependencias]
sustituye: null
sustituido_por: null
---

# ADR-0002: cyclopts como framework de CLI

## Contexto

ia-testing es una CLI. Las tareas y la configuración de los runners se describen con tipos ricos, y el proyecto usa mypy, así que interesa que la firma de las funciones sea el contrato de la CLI.

## Decisión

Usamos **cyclopts** como framework de CLI, con la versión mayor fijada en `pyproject.toml`. `cli.py` se mantiene fino: solo parsea y delega en `app`.

Motivos:
- La firma de la función define la CLI y mypy comprueba los tipos de verdad.
- Soporta tipos ricos (`Union`, `Literal`, dataclasses, Pydantic como grupos de parámetros), útiles para describir tareas y configuraciones de runners.
- Saca la ayuda de cada parámetro del docstring, sin repetirla en `Annotated`.
- Incluye configuración por variables de entorno y TOML.
- No depende de Click.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Typer | Madura, sobre Click, con autocompletado y `CliRunner`. Pero el soporte de tipos complejos (uniones, dataclasses como parámetro) es limitado, hereda *quirks* de Click (booleanos `--x/--no-x`) y arranca más lento. **Reconsiderar** si la madurez o la comunidad de cyclopts dan problemas (cambios de API frecuentes, bugs sin resolver). |
| argparse (stdlib) | Cero dependencias y máxima estabilidad, pero los argumentos van separados de la función, `Namespace` no tiene tipos (mypy no ve nada) y subcomandos, autocompletado y tests van a mano. Cero dependencias no es un requisito. **Reconsiderar** si aparece un requisito duro de cero dependencias. |
| Click | No se evaluó en profundidad. Es más explícito, con decoradores, y no usa los *type hints* como contrato; Typer cubre su caso con menos código. |

## Consecuencias

**Positivas**
- La CLI está tipada de punta a punta y con poco *boilerplate*.

**Negativas / costes asumidos**
- Comunidad más pequeña que la de Typer o Click: menos ejemplos y respuestas.
- Su API ha cambiado más entre versiones mayores.

**Riesgos y cómo se mitigan**
- Cambio de API o abandono → versión mayor fijada y `cli.py` fino, de modo que cambiar de framework afecta a un único fichero.

## Cumplimiento

- Principio P4 de `docs/ARCHITECTURE.md` (`cli.py` fino), comprobado en revisión.
- Versión mayor fijada en `pyproject.toml`.

## Referencias

- `docs/informe-decisiones-iniciales.md` §4
