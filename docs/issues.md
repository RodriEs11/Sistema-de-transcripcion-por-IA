# Issues: cómo se cargan y se ordenan

Al tocar **New issue** en GitHub aparecen cuatro formularios (`.github/ISSUE_TEMPLATE/`):

| Plantilla | Para | Etiqueta | Rama |
|---|---|---|---|
| 🐞 Bug | algo que falla | `bug` | `fix/<n>-<tema>` |
| ✨ Característica | algo nuevo | `feat` | `feat/<n>-<tema>` |
| 🎨 Interfaz / UX | cambiar cómo se ve o se usa | `ux` | `feat/` o `refactor/` |
| 📋 Paraguas | agrupar varios issues | `paraguas` | — |

## Reglas
- **Un issue = una cosa.** Si son varias, un issue por cada una y un paraguas que las agrupe.
- Título que se entienda solo: `[Bug] El editor pierde el formato al pegar desde Word`.
- Criterios de aceptación como lista de casillas: definen cuándo cerrar.
- Prioridad: P1 bloquea el trabajo · P2 importante · P3 cuando se pueda.
- **Nunca** datos de pacientes, nombres de médicos ni secretos (tampoco en capturas).

## Para cargar varios a la vez
1. Crear cada issue con su plantilla.
2. Crear un **Paraguas** y enlazarlos con `- [ ] #número`. GitHub muestra el avance.
3. Trabajar uno por rama; en el PR escribir `Closes #número` para que se cierre al fusionar.
