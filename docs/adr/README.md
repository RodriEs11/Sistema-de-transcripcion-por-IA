# Registro de decisiones de arquitectura (ADR)

Cada decisión importante y difícil de revertir se anota en un archivo corto y numerado: qué se decidió, por qué,
qué alternativas se descartaron y qué consecuencias tiene. No se borran ni se reescriben: si una decisión cambia,
se escribe un ADR nuevo que la reemplaza y el viejo pasa a «Reemplazado por NNNN».

| # | Decisión | Estado |
|---|---|---|
| [0001](0001-modularizar-por-etapas.md) | Modularizar el código por etapas, con contratos como red de seguridad | Aceptado |
| [0002](0002-versiones-por-entrega.md) | Subir versiones por entrega, no por PR, y marcar cada entrega con etiquetas de git | Aceptado |

Decisiones anteriores a este registro (están en el CHANGELOG y en `docs/`): Gemma 4 12B en lugar de Qwen
(fase 2), Git dentro de la carpeta en uso, lotes de IA de 2 audios / 180 s (`historial/validacion-gpu.md`), cola SQLite
(`cola-servidor.md`), rama `experimental` (`experimentos.md`). Se pueden pasar a ADR cuando se las revise.

## Plantilla

```markdown
# NNNN. Título en forma de decisión

- Estado: Propuesto | Aceptado | Reemplazado por NNNN
- Fecha: AAAA-MM-DD

## Contexto
Qué problema hay y qué restricciones importan.

## Decisión
Qué se va a hacer.

## Alternativas consideradas
Cada una con por qué no.

## Consecuencias
Qué mejora, qué cuesta y qué queda pendiente.
```
