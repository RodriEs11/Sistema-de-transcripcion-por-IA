"""Página principal, sus estilos y su script, el editor de Word y las plantillas HTML de web/plantillas/.
Todo se lee en cada pedido: cambiar una página no requiere reiniciar el servidor."""


def principal(h, pedido):
    """GET /, /index.html."""
    sis = h.sis
    h._html((sis.web / "index.html").read_bytes())


def unir_partes(carpeta, extension):
    """Las partes de una carpeta (010-base.js, 020-lista.js…) unidas en orden de nombre, como un solo texto.

    El script de la página se escribe en partes por área (web/js/principal/) pero se envía como un único script,
    igual que cuando estaba dentro de index.html: así una función de una parte se puede usar desde el código de
    arranque de otra anterior, y el orden de ejecución no depende de cuándo llega cada archivo."""
    return "".join(p.read_text(encoding="utf-8") for p in sorted(carpeta.glob(f"*{extension}")))


def estilos(h, pedido):
    """GET /css/principal.css: web/css/principal/*.css en orden."""
    h._contenido(unir_partes(h.sis.web / "css" / "principal", ".css"), "text/css; charset=utf-8")


def script(h, pedido):
    """GET /js/principal.js: web/js/principal/*.js en orden."""
    h._contenido(unir_partes(h.sis.web / "js" / "principal", ".js"), "text/javascript; charset=utf-8")


def editor_word(h, pedido):
    """GET /editor_word.js."""
    sis = h.sis
    h._enviar_archivo(sis.web / "editor_word.js")


def plantilla(sis, nombre):
    """Página con marcadores {{…}} de web/plantillas/. Se lee como texto (los fines de línea de Windows no cambian
    lo que se envía) y sin el salto de línea final del archivo."""
    return (sis.web / "plantillas" / nombre).read_text(encoding="utf-8").removesuffix("\n")
