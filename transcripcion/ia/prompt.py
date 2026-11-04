"""Armado de los mensajes que se mandan a la IA: instrucciones, plantillas relevantes, reglas, correcciones
aprendidas, notas del médico, referencias y ejemplos.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""

from transcripcion.acceso import usuarios as U
from transcripcion.conocimiento import archivos as CON
from transcripcion.conocimiento import medicos as MED
from transcripcion.conocimiento import plantillas as PL
from transcripcion.ia import ejemplos as EJEM

# ------------------------------------------------------------------ prompt
SISTEMA = """Sos un asistente de transcripción médica de un servicio de diagnóstico por imágenes de Argentina.
Recibís el DICTADO de un médico (texto generado por un reconocedor de voz, con errores) y escribís el INFORME FINAL
exactamente con el formato de las plantillas del servicio.

REGLAS:
1. Usá las plantillas y frases habituales de abajo, palabra por palabra, siempre que correspondan.
2. Todo hallazgo, medida, número, lado (derecho/izquierdo), hora (H12) o nivel (L5-S1) sale SOLO del dictado.
   Nunca inventes datos. Si un dato que la plantilla necesita no fue dictado, escribí [[COMPLETAR: qué falta]].
3. El reconocedor de voz deforma palabras. Corregilas usando el vocabulario de las plantillas.
   Si no estás seguro de qué quiso decir el médico, escribí tu mejor propuesta así: [[?texto propuesto]].
4. No incluyas el nombre del paciente ni comentarios del médico dirigidos al transcriptor.
5. Respondé SOLO con el informe, sin explicaciones, sin markdown, sin ```.
6. Nunca escribas "protocolo normal" como texto: reemplazalo por las viñetas del PROTOCOLO NORMAL de la plantilla.

FORMATO:
- Título de cada estudio en su propia línea, luego una línea en blanco, luego las viñetas que empiezan con "-" (sin espacio).
- Línea en blanco entre estudios. Último renglón: "Lo saluda atte."

===== PLANTILLAS =====
{plantillas}

===== CÓMO DICTAN =====
{reglas}
"""


def reglas_de(usuario=None):
    """reglas_dictado.md general + las reglas propias del transcriptor.

    Se suman; si se contradicen, valen las suyas."""
    reglas = CON.leer("reglas_dictado.md")
    propias = U.leer_archivo(usuario, "reglas_dictado.md").strip() if usuario else ""
    if propias:
        reglas = (
            reglas.rstrip() + "\n\n===== REGLAS PROPIAS DE ESTE TRANSCRIPTOR "
            "(si contradicen a las de arriba, valen estas) =====\n" + propias + "\n"
        )
    return reglas


def armar_mensajes(dictado, ejemplos, medico=None, sin_estilos=False, usuario=None):
    """usuario: transcriptor con cuyo estilo se arma el informe (plantillas, notas, reglas y correcciones propias)."""
    sis = SISTEMA.format(
        plantillas=PL.plantillas_relevantes(dictado, medico, sin_estilos, usuario), reglas=reglas_de(usuario)
    )
    # referencias: solo si los ejemplos con dictado no cubren bien este tipo de estudio
    d = PL.categorias(dictado)
    cubre = (
        max((len(d & PL.categorias(e["dictado"])) / len(d | PL.categorias(e["dictado"])) for e in ejemplos), default=0)
        if d
        else 1
    )
    if cubre < 1:
        refs = EJEM.elegir_referencias(dictado, medico=medico)
        if refs:
            sis += (
                "\n===== INFORMES DE REFERENCIA DE ESTE TIPO DE ESTUDIO (sin dictado) =====\n"
                "Usalos para copiar el formato, el texto fijo y el estilo de las frases. "
                "NO copies sus hallazgos ni sus medidas: todo hallazgo sale del dictado.\n\n"
                + "\n\n----------\n\n".join(refs)
                + "\n"
            )
    notas = MED.notas_medico(medico, usuario) if medico else ""
    if notas.strip():
        sis += f"\n===== CÓMO DICTA ESTE MÉDICO ({medico}) =====\n{notas.strip()}\n"
    corr = CON.CONOC / "correcciones_aprendidas.md"
    if corr.exists() and corr.read_text(encoding="utf-8").count("\n- ") > 0:
        sis += "\n===== CORRECCIONES FRECUENTES DEL TRANSCRIPTOR =====\n" + corr.read_text(encoding="utf-8")
    propias = U.leer_archivo(usuario, "correcciones_aprendidas.md") if usuario else ""
    if propias.count("\n- ") > 0:
        sis += "\n===== CORRECCIONES FRECUENTES DE ESTE TRANSCRIPTOR =====\n" + propias
    if any(e.get("ajeno") for e in ejemplos):
        sis += (
            "\nAlgunos ejemplos son de OTRO transcriptor (lo dice antes del dictado): usalos para entender cómo "
            "dicta el médico, pero NO copies su formato ni sus frases si las plantillas dicen otra cosa.\n"
        )
    msgs = [{"role": "system", "content": sis}]
    for e in ejemplos:
        msgs.append(
            {
                "role": "user",
                "content": (
                    "DICTADO (ejemplo de otro transcriptor: solo para entender el dictado):\n"
                    if e.get("ajeno")
                    else "DICTADO:\n"
                )
                + e["dictado"],
            }
        )
        msgs.append({"role": "assistant", "content": e["informe"].strip()})
    msgs.append({"role": "user", "content": "DICTADO:\n" + dictado})
    return msgs
