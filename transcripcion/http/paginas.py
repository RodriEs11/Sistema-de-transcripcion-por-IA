"""Página principal, editor de Word y plantillas HTML de web/plantillas/ (se leen en cada pedido)."""


def principal(h, pedido):
    """GET /, /index.html."""
    sis = h.sis
    h._html((sis.web / "index.html").read_bytes())


def editor_word(h, pedido):
    """GET /editor_word.js."""
    sis = h.sis
    h._enviar_archivo(sis.web / "editor_word.js")


def plantilla(sis, nombre):
    """Página con marcadores {{…}} de web/plantillas/. Se lee como texto (los fines de línea de Windows no cambian
    lo que se envía) y sin el salto de línea final del archivo."""
    return (sis.web / "plantillas" / nombre).read_text(encoding="utf-8").removesuffix("\n")
