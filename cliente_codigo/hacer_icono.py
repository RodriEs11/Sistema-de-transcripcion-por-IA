"""Genera app.ico (diseño 7, "Marcas de revisión") y PNG de control.
Los tamaños chicos están ajustados a mano a la grilla de píxeles."""
import struct, io
from PIL import Image, ImageDraw

FONDO = (0x0F, 0x17, 0x2A)
GRIS = (0xCB, 0xD5, 0xE1)
ROJO = (0xEF, 0x44, 0x44)
AMAR = (0xFA, 0xCC, 0x15)
TURQ = (0x2D, 0xD4, 0xBF)

# Diseño original (grilla de 64): (x, y, ancho, alto, color, radio)
BASE64 = {
    "tile": (2, 2, 60, 60, 14),
    "rects": [
        (12, 14, 40, 6, GRIS, 3),
        (12, 24, 12, 6, GRIS, 3), (27, 23, 25, 8, ROJO, 2.5),
        (12, 33, 22, 8, AMAR, 2.5), (37, 34, 15, 6, GRIS, 3),
        (12, 44, 14, 6, GRIS, 3), (29, 43, 18, 8, TURQ, 2.5),
    ],
}

def caja(x0, y0, x1, y1, c, r):
    return (x0, y0, x1 - x0, y1 - y0, c, r)

# Versiones ajustadas a píxel: coordenadas x0,y0,x1,y1 en píxeles del tamaño final.
AJUSTADOS = {
    16: {"tile": (0, 0, 16, 16, 3.5), "rects": [
        caja(3, 3, 13, 5, GRIS, 0),
        caja(3, 6, 5, 8, GRIS, 0), caja(6, 6, 13, 8, ROJO, 0),
        caja(3, 9, 9, 11, AMAR, 0), caja(10, 9, 13, 11, GRIS, 0),
        caja(3, 12, 6, 14, GRIS, 0), caja(7, 12, 12, 14, TURQ, 0)]},
    20: {"tile": (0, 0, 20, 20, 4.5), "rects": [
        caja(4, 3, 16, 5, GRIS, 0),
        caja(4, 7, 7, 9, GRIS, 0), caja(8, 7, 16, 9, ROJO, 0),
        caja(4, 11, 11, 13, AMAR, 0), caja(12, 11, 16, 13, GRIS, 0),
        caja(4, 15, 8, 17, GRIS, 0), caja(9, 15, 15, 17, TURQ, 0)]},
    24: {"tile": (0, 0, 24, 24, 5.5), "rects": [
        caja(4, 3, 20, 6, GRIS, 1),
        caja(4, 8, 8, 11, GRIS, 1), caja(9, 8, 20, 11, ROJO, .7),
        caja(4, 13, 13, 16, AMAR, .7), caja(14, 13, 20, 16, GRIS, 1),
        caja(4, 18, 9, 21, GRIS, 1), caja(10, 18, 18, 21, TURQ, .7)]},
    32: {"tile": (0, 0, 32, 32, 7), "rects": [
        caja(6, 6, 26, 9, GRIS, 1.5),
        caja(6, 12, 12, 15, GRIS, 1.5), caja(14, 11, 26, 16, ROJO, 1.2),
        caja(6, 17, 17, 22, AMAR, 1.2), caja(19, 18, 26, 21, GRIS, 1.5),
        caja(6, 24, 13, 27, GRIS, 1.5), caja(15, 23, 24, 28, TURQ, 1.2)]},
    48: {"tile": (1, 1, 46, 46, 10.5), "rects": [
        caja(9, 10, 39, 14, GRIS, 2),
        caja(9, 18, 18, 22, GRIS, 2), caja(20, 17, 39, 23, ROJO, 1.8),
        caja(9, 25, 25, 31, AMAR, 1.8), caja(28, 26, 39, 30, GRIS, 2),
        caja(9, 34, 19, 38, GRIS, 2), caja(22, 33, 35, 39, TURQ, 1.8)]},
}

SS = 16  # sobremuestreo

def dibujar(n):
    if n in AJUSTADOS:
        d, k = AJUSTADOS[n], 1.0
    else:
        d, k = BASE64, n / 64.0
    big = Image.new("RGBA", (n * SS, n * SS), (0, 0, 0, 0))
    g = ImageDraw.Draw(big)
    x, y, w, h, r = d["tile"]
    s = k * SS
    g.rounded_rectangle([x * s, y * s, (x + w) * s - 1, (y + h) * s - 1], radius=r * s, fill=FONDO + (255,))
    for (x, y, w, h, c, r) in d["rects"]:
        g.rounded_rectangle([x * s, y * s, (x + w) * s - 1, (y + h) * s - 1], radius=r * s, fill=c + (255,))
    return big.resize((n, n), Image.BOX)

def dib(img):
    """Entrada BMP de 32 bits (BITMAPINFOHEADER + BGRA de abajo arriba + máscara AND)."""
    w, h = img.size
    hdr = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    px = img.load()
    filas = []
    for yy in range(h - 1, -1, -1):
        filas.append(b"".join(struct.pack("BBBB", px[xx, yy][2], px[xx, yy][1], px[xx, yy][0], px[xx, yy][3]) for xx in range(w)))
    ancho_mask = ((w + 31) // 32) * 4
    mask = b""
    for yy in range(h - 1, -1, -1):
        bits = 0
        fila = bytearray(ancho_mask)
        for xx in range(w):
            if px[xx, yy][3] == 0:
                fila[xx // 8] |= 0x80 >> (xx % 8)
        mask += bytes(fila)
    return hdr + b"".join(filas) + mask

def png(img):
    b = io.BytesIO(); img.save(b, "PNG"); return b.getvalue()

TAMANOS = [16, 20, 24, 32, 40, 48, 64, 128, 256]

def main(salida):
    imgs = {n: dibujar(n) for n in TAMANOS}
    datos = [(n, png(imgs[n]) if n == 256 else dib(imgs[n])) for n in TAMANOS]
    cab = struct.pack("<HHH", 0, 1, len(datos))
    off = 6 + 16 * len(datos)
    dirs, cuerpo = b"", b""
    for n, b in datos:
        dirs += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(b), off + len(cuerpo))
        cuerpo += b
    open(salida, "wb").write(cab + dirs + cuerpo)
    for n in TAMANOS:
        imgs[n].save(f"/home/claude/icono/p_{n}.png")
    # hoja de control: tamaño real sobre fondo oscuro y claro, y ampliado x8
    hoja = Image.new("RGBA", (1300, 420), (255, 255, 255, 255))
    xx = 10
    for n in [16, 20, 24, 32, 48]:
        z = imgs[n].resize((n * 8 if n <= 24 else n * 4,) * 2, Image.NEAREST)
        hoja.alpha_composite(z, (xx, 10))
        xx += z.size[0] + 20
    oscuro = Image.new("RGBA", (640, 80), (32, 32, 32, 255))
    claro = Image.new("RGBA", (640, 80), (238, 238, 238, 255))
    xx = 20
    for n in [16, 20, 24, 32, 48, 64]:
        oscuro.alpha_composite(imgs[n], (xx, 40 - n // 2)); claro.alpha_composite(imgs[n], (xx, 40 - n // 2)); xx += n + 30
    hoja.alpha_composite(oscuro, (10, 230)); hoja.alpha_composite(claro, (10, 320))
    hoja.alpha_composite(imgs[128], (700, 230))
    hoja.save("/home/claude/icono/control.png")

if __name__ == "__main__":
    main("/home/claude/icono/app.ico")
