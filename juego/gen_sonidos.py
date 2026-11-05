#!/usr/bin/env python3
"""Genera los efectos de sonido del visor (sintetizados por codigo, sin assets externos).
Uso (desde la raiz del repo): python3 juego/gen_sonidos.py
Crea juego/sonidos/agua.wav y juego/sonidos/cortafuegos.wav"""
import math, os, random, struct, wave

TASA = 22050

def guardar(ruta, muestras):
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(TASA)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, m)) * 32767)) for m in muestras))

def agua():
    # Ruido filtrado con barrido descendente: salpicadura breve
    random.seed(1)
    n = int(TASA * 0.45); out = []; prev = 0.0
    for i in range(n):
        t = i / n
        alfa = 0.55 - 0.45 * t
        prev = prev + alfa * (random.uniform(-1, 1) - prev)
        out.append(prev * 0.9 * (1 - t) ** 1.5)
    return out

def cortafuegos():
    # Golpe grave tipo pala sobre tierra: seno descendente con ruido corto
    random.seed(2)
    n = int(TASA * 0.25); out = []
    for i in range(n):
        t = i / n
        f = 160 - 90 * t
        s = math.sin(2 * math.pi * f * (i / TASA))
        r = random.uniform(-1, 1) * (1 - t) ** 4
        out.append((0.7 * s + 0.3 * r) * (1 - t) ** 1.2)
    return out

if __name__ == "__main__":
    os.makedirs("juego/sonidos", exist_ok=True)
    guardar("juego/sonidos/agua.wav", agua())
    guardar("juego/sonidos/cortafuegos.wav", cortafuegos())
    print("OK: sonidos generados en juego/sonidos/")
