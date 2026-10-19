<!--
PLANTILLA de ADR → docs/adr/0000-plantilla.md
Basada en el formato de Michael Nygard / MADR, con extras útiles para agentes de IA.

Cómo usarla:
- Copia como docs/adr/NNNN-titulo-en-kebab-case.md (numeración correlativa, nunca se reutiliza).
- Un ADR = una decisión. Corto: 1-2 páginas como máximo.
- Escribe la decisión en voz activa ("Usamos X"), no "se podría considerar".
- Un ADR aceptado NO se edita (salvo erratas o enlaces): si la decisión cambia, crea uno nuevo
  que lo sustituya y marca este como "Sustituido por ADR-NNNN".
- La sección de alternativas descartadas es la más valiosa: evita que personas y agentes vuelvan a proponerlas.
- Añade una línea al índice docs/adr/README.md.
-->

---
id: ADR-NNNN
titulo: <Decisión en pocas palabras>
estado: propuesto            # propuesto | aceptado | rechazado | obsoleto | sustituido
fecha: AAAA-MM-DD
responsables: ["@persona", "@equipo"]
etiquetas: [persistencia, api]   # facilita que un agente encuentre los ADR relevantes
sustituye: null              # ADR-XXXX si reemplaza a otro
sustituido_por: null         # ADR-YYYY cuando quede obsoleto
---

# ADR-NNNN: <Decisión en pocas palabras>

## Contexto

<!-- Qué problema o necesidad obliga a decidir. Fuerzas en juego: requisitos, restricciones técnicas,
de negocio, de equipo, plazos. Hechos, no opiniones. -->

## Decisión

<!-- La decisión en voz activa y concreta. Qué se hace y, si aplica, dónde se aplica. -->

Usamos <X> para <Y>.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| <Opción A> | <motivo concreto> |
| <Opción B> | <motivo concreto> |
| No hacer nada | <motivo> |

## Consecuencias

**Positivas**
- <beneficio>

**Negativas / costes asumidos**
- <coste, deuda o limitación que aceptamos conscientemente>

**Riesgos y cómo se mitigan**
- <riesgo> → <mitigación>

## Cumplimiento

<!-- Cómo se hace cumplir. Si se puede automatizar, mejor: lint, contrato de import-linter, test, hook, CI. -->

- Verificación automática: <p. ej. contrato "Dominio puro" en import-linter / regla de ruff / test de arquitectura>
- Si afecta a un principio innegociable: actualizado en `docs/ARCHITECTURE.md` (sección 5).
- Instrucción para agentes, si hace falta: <línea añadida a AGENTS.md o "no necesaria">

## Contexto de IA (opcional)

<!-- Rellenar si un agente propuso o influyó de forma relevante en la decisión. -->

- Agente / modelo: <p. ej. Claude Code / claude-opus-5-5>
- Resumen del prompt o la tarea: <…>
- Revisión humana: <quién y qué validó>

## Referencias

- <issues, specs, PRs, documentación, benchmarks>
