# 0002. Subir versiones por entrega, no por PR, y marcar cada entrega con etiquetas de git

- Estado: Aceptado
- Fecha: 2026-11-05

## Contexto

Hasta la App 1.28 y el Servidor 2026.11.15, cada PR con cambios funcionales subía su propia versión. Las reglas
pedían «agregar los cambios de una misma entrega en una versión», pero no definían qué era una entrega, así que en
la práctica cada PR fue una:

- El 03/11 salieron 11 versiones del servidor (2026.11.2 a 2026.11.12), casi todas etapas del refactor sin cambios
  visibles. Se subían porque era la única forma de que el panel mostrara qué código corría.
- El 05/11 salieron la App 1.27 y la 1.28, y los Servidores 2026.11.14 y 2026.11.15.
- Dos ramas abiertas a la vez se disputan el mismo número.
- No había etiquetas de git: ningún número estaba atado a un commit, y volver atrás dependía de buscar en el historial.
- El CHANGELOG decía «versionado semántico» para la app, pero la regla obligaba a subir siempre el segundo número
  (1.15 → 1.16), sin lugar para correcciones (1.28.1).
- Las versiones también se copiaban a mano en otros lugares que quedaban desactualizados. `docs/README.md`, por
  ejemplo, decía «Servidor 2026.11.12 · App 1.25».

## Decisión

1. Los PR de trabajo no cambian números: dejan sus notas en «Sin publicar» del CHANGELOG, bajo `### App` y/o
   `### Servidor`.
2. Una entrega es un PR propio (`release/…`) que sube las versiones con `herramientas/subir_version.py`, pasa las
   notas a entradas fechadas y actualiza LEEME. Incluye todo lo fusionado hasta ese momento.
3. Tras fusionarla, el commit se marca con etiquetas anotadas `app-vX` / `servidor-vY`. La instalación en uso se
   actualiza a esa etiqueta (`git merge --ff-only`), no a la punta de `main`. El panel muestra la etiqueta al lado
   del commit.
4. La app usa versionado semántico completo: PARCHE para correcciones, MENOR para funciones, MAYOR para cambios
   incompatibles. El servidor sigue con `AAAA.M.N`.
5. Un refactor con los contratos en verde no tiene versión propia: va como «Interno» en la próxima entrega.
6. `herramientas/verificar_versiones.py` comprueba:
   - siempre: el esquema y el mes del servidor contra la fecha de su entrada, y que ninguna versión sea anterior a la
     última etiqueta;
   - con `--entrega`, en el CI de las ramas `release/`: que haya algo nuevo y que no queden notas sin entregar.

Detalle y comandos: [versiones.md](../versiones.md).

## Alternativas consideradas

- **Seguir subiendo por PR y solo agregar etiquetas.** Mantiene la inflación de números y los choques entre ramas, y
  las PC instalan varias veces por día.
- **Instalación siguiendo `main` y versiones por entrega.** Habría código corriendo con un número que no le
  corresponde entre una fusión y la entrega. Seguir etiquetas evita ese estado intermedio.
- **Versión calculada desde git (`git describe`) en lugar de escrita en el código.** El ejecutable necesita su
  número compilado (`AssemblyFileVersion`), la instalación puede no tener git y el manifiesto compara versiones
  escritas. Se descartó por ahora; las etiquetas cubren la trazabilidad.
- **Herramientas externas (semantic-release, release-please).** Dependen de Node o de la nube de GitHub,
  y de commits con un formato que hoy no siempre describe el resultado para los usuarios. Para una sola persona
  y dos componentes alcanza con un script propio.

## Consecuencias

- Menos versiones y cada una con sentido: lo que ven las PC y el panel corresponde a una entrega y a un commit.
- Las notas se escriben en el momento del cambio (en el PR), cuando se sabe qué se hizo.
- Hay un paso más, el PR de entrega, que la herramienta reduce a un comando y una revisión.
- La activación cambia: `git merge --ff-only <etiqueta>` en lugar de `git pull`. Si se hace `git pull` por
  costumbre, el panel lo muestra (commit sin etiqueta).
- Queda pendiente decidir si los cambios solo de la página principal deben seguir subiendo la versión de la app
  (ver [versiones.md](../versiones.md#decisión-pendiente-página-principal-y-versión-de-la-app)).
