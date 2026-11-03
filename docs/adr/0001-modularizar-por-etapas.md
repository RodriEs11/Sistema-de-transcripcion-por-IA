# 0001. Modularizar el código por etapas, con contratos como red de seguridad

- Estado: Aceptado
- Fecha: 2026-11-03

## Contexto

El sistema está en uso diario. `servidor.py` (~3.400 líneas) concentra el arranque, unas 40 variables
globales de estado, la cola, el trabajador, la gestión de casos y ~100 rutas HTTP. `web/index.html` (~3.570
líneas) contiene todo el CSS y el JavaScript. `nucleo.py` (~1.400) mezcla la preparación del prompt, el cliente de
Ollama y los controles. Importar `servidor.py` lee la configuración y crea carpetas junto a los datos reales.

El costo se ve en el trabajo diario: cada cambio exige leer archivos enormes, las pruebas reemplazan decenas de
globales con `patch.object` y se rompen cuando el código se mueve, y un efecto colateral puede llegar a producción.

Restricciones: una sola persona desarrolla (con agentes de IA); el código corre en la misma carpeta que el
repositorio; no puede haber cambios visibles para la transcriptora; no se pueden usar datos de pacientes en pruebas.

## Decisión

1. Reorganizar el código en un paquete `transcripcion/` con módulos de una sola responsabilidad, **por etapas**
   (plan y estructura destino en [docs/refactor.md](../refactor.md)), un PR por etapa o módulo.
2. **Antes de mover nada**, fijar el comportamiento con dos contratos que no dependen de cómo está organizado el
   código por dentro: uno HTTP de caja negra (servidor real en subproceso, modo simulado) y uno del núcleo
   (salidas de marcas, prompt, normalización, orden y Word sobre casos ficticios). Un refactor no puede cambiarlos.
3. Configuración y estado explícitos: un objeto `Ajustes` creado en el arranque y objetos con su propio estado
   (cola, procesador, casos) en lugar de globales; ningún módulo hace nada al importarse.
4. Conservar los puntos de entrada actuales (`servidor.py`, los `.bat`) como lanzadores finos.
5. Calidad gradual: ruff con errores reales desde ya; reglas de estilo y formato por módulo terminado.

## Alternativas consideradas

- **Reescribir desde cero** (o en otro framework). Descartado: meses sin entregar mejoras, y se perderían
  decenas de detalles aprendidos con el uso real (borradores, cola, sesiones, Whisper) que hoy solo están en el código.
- **Pasar ahora a FastAPI/Flask.** Descartado por ahora: cambia dependencias, el modelo de hilos y el
  comportamiento HTTP al mismo tiempo que se reorganiza. Se puede reconsiderar después de la etapa 6, cuando las
  rutas ya estén en una tabla y cambiar el servidor HTTP sea un cambio acotado (sería otro ADR).
- **Un único PR grande que mueva todo.** Descartado: imposible de revisar y de revertir con seguridad en
  una instalación en uso.
- **Dejarlo como está.** Descartado: el costo de cada cambio sigue creciendo con el código.

## Consecuencias

- Durante varias semanas conviven código nuevo y viejo; `docs/refactor.md` dice en qué etapa está cada parte.
- Cada etapa que toca el servidor obliga a reiniciarlo en una ventana sin trabajo, con etiqueta git previa para volver atrás.
- Las pruebas existentes que parchean globales se reescriben a medida que se mueve lo que prueban.
- Los contratos pasan a ser parte permanente del CI: también protegen cambios funcionales futuros.
- Si un contrato no cubre algo que se rompe, se agrega el caso al contrato antes de arreglarlo.
