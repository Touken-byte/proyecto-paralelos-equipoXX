#!/usr/bin/env python3
"""Generador de mapas sintéticos del Chaco con semilla reproducible.

Formato binario (little-endian):
  4 bytes  "FIRE"
  4 bytes  N (uint32)
  N*N bytes  estado   (0 vacía, 1 vegetación, 2 quemando, 3 quemada, 4 cortafuego, 5 agua)
  N*N bytes  combustible (0-255)
  N*N bytes  humedad     (0-255)
"""
import argparse, math, os, random, struct

VACIA, VEGETACION, QUEMANDO, QUEMADA, CORTAFUEGO, AGUA = range(6)

def crear_grilla(n, rnd, celda):
    g = n // celda + 2
    return [[rnd.random() for _ in range(g)] for _ in range(g)]

def fila_ruido(grid, i, n, celda):
    fy = i / celda
    y0 = int(fy)
    ty = fy - y0
    ty = ty * ty * (3 - 2 * ty)
    r0, r1 = grid[y0], grid[y0 + 1]
    out = []
    for j in range(n):
        fx = j / celda
        x0 = int(fx)
        tx = fx - x0
        tx = tx * tx * (3 - 2 * tx)
        a = r0[x0] + (r0[x0 + 1] - r0[x0]) * tx
        b = r1[x0] + (r1[x0 + 1] - r1[x0]) * tx
        out.append(a + (b - a) * ty)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=512)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--focos", type=int, default=3)
    ap.add_argument("--out", default="data/maps/map_512.bin")
    a = ap.parse_args()

    n = a.n
    rnd = random.Random(a.seed)
    celda = max(8, n // 16)
    g_veg = crear_grilla(n, rnd, celda)
    g_hum = crear_grilla(n, rnd, celda)

    estado = bytearray(n * n)
    fuel = bytearray(n * n)
    hum = bytearray(n * n)

    ancho_rio = max(2, n // 170)
    for i in range(n):
        v = fila_ruido(g_veg, i, n, celda)
        h = fila_ruido(g_hum, i, n, celda)
        centro = n * 0.30 + n * 0.08 * math.sin(i * 2 * math.pi / (n * 0.6))
        base = i * n
        for j in range(n):
            hum[base + j] = min(255, int(40 + 140 * h[j]))
            if abs(j - centro) <= ancho_rio:
                estado[base + j] = AGUA
            elif v[j] < 0.25:
                estado[base + j] = VACIA
            else:
                estado[base + j] = VEGETACION
                fuel[base + j] = min(255, int(60 + 195 * v[j]))

    # Focos iniciales en la zona central
    for _ in range(a.focos):
        ci = rnd.randint(int(n * 0.4), int(n * 0.7))
        cj = rnd.randint(int(n * 0.4), int(n * 0.7))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                k = (ci + di) * n + (cj + dj)
                if estado[k] == VEGETACION:
                    estado[k] = QUEMANDO

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "wb") as f:
        f.write(b"FIRE")
        f.write(struct.pack("<I", n))
        f.write(estado)
        f.write(fuel)
        f.write(hum)

    total = n * n
    print(f"Mapa {n}x{n} semilla={a.seed} -> {a.out} ({os.path.getsize(a.out)/1e6:.2f} MB)")
    for nombre, cod in [("vacía", VACIA), ("vegetación", VEGETACION), ("quemando", QUEMANDO), ("agua", AGUA)]:
        c = estado.count(cod)
        print(f"  {nombre:11s}: {c:9d} ({100*c/total:5.1f}%)")

if __name__ == "__main__":
    main()
