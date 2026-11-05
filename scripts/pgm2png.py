#!/usr/bin/env python3
"""Convierte mapas PGM del motor a PNG coloreado (sin librerias externas).
Uso:
  python3 scripts/pgm2png.py a.pgm b.pgm            -> a.png, b.png
  python3 scripts/pgm2png.py --montaje out.png a.pgm b.pgm c.pgm   -> una sola imagen
"""
import argparse, struct, zlib

# estado -> color: vacia, vegetacion, quemando, quemada, cortafuego, agua
PAL = {0: (222, 205, 160), 1: (34, 139, 34), 2: (230, 40, 20),
       3: (70, 70, 70), 4: (130, 90, 40), 5: (40, 110, 220)}

def leer_pgm(ruta):
    datos = open(ruta, "rb").read()
    toks, pos = [], 0
    while len(toks) < 4:
        while datos[pos:pos + 1].isspace():
            pos += 1
        ini = pos
        while not datos[pos:pos + 1].isspace():
            pos += 1
        toks.append(datos[ini:pos])
    pos += 1
    assert toks[0] == b"P5", "No es un PGM binario"
    w, h = int(toks[1]), int(toks[2])
    return w, h, datos[pos:pos + w * h]

def filas_rgb(w, h, px):
    tabla = {k * 40: bytes(v) for k, v in PAL.items()}
    magenta = bytes((255, 0, 255))
    return [b"".join(tabla.get(px[i * w + j], magenta) for j in range(w)) for i in range(h)]

def escribir_png(ruta, w, h, filas):
    raw = b"".join(b"\x00" + r for r in filas)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    open(ruta, "wb").write(png)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--montaje", help="PNG de salida con todas las imagenes lado a lado")
    ap.add_argument("archivos", nargs="+")
    a = ap.parse_args()
    if a.montaje:
        sep = b"\xff\xff\xff" * 6
        imgs = [leer_pgm(f) for f in a.archivos]
        h = imgs[0][1]
        filas_todas = [filas_rgb(w, hh, px) for (w, hh, px) in imgs]
        filas = [sep.join(f[i] for f in filas_todas) for i in range(h)]
        ancho = sum(i[0] for i in imgs) + 6 * (len(imgs) - 1)
        escribir_png(a.montaje, ancho, h, filas)
        print("Montaje:", a.montaje)
    else:
        for f in a.archivos:
            w, h, px = leer_pgm(f)
            out = f.rsplit(".", 1)[0] + ".png"
            escribir_png(out, w, h, filas_rgb(w, h, px))
            print("PNG:", out)

if __name__ == "__main__":
    main()
