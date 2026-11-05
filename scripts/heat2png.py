#!/usr/bin/env python3
"""Convierte el mapa de riesgo del Vigia (PGM 0-255) a PNG con rampa de color.
Uso: python3 scripts/heat2png.py mapa.pgm [otro.pgm ...]   -> mapa.png
Azul = riesgo bajo, amarillo = medio, rojo = alto, beige = nunca afectada."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pgm2png import leer_pgm, escribir_png

def color(v):
    if v == 0:
        return bytes((235, 235, 220))
    t = v / 255.0
    r = int(255 * min(1.0, 2 * t))
    g = int(255 * (min(1.0, 2 * t) if t < 0.5 else 2 * (1 - t)))
    b = int(255 * max(0.0, 1 - 2 * t))
    return bytes((r, g, b))

TABLA = [color(v) for v in range(256)]
for ruta in sys.argv[1:]:
    w, h, px = leer_pgm(ruta)
    filas = [b"".join(TABLA[px[i * w + j]] for j in range(w)) for i in range(h)]
    out = ruta.rsplit(".", 1)[0] + ".png"
    escribir_png(out, w, h, filas)
    print("PNG:", out)
