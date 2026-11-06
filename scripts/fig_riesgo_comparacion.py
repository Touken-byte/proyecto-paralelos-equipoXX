#!/usr/bin/env python3
"""Dibuja docs/figuras/fig_riesgo_comparacion.png a partir de los PGM del Vigía.
Uso: python3 scripts/fig_riesgo_comparacion.py   (tras ./scripts/vigia_comparacion.sh)"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

def leer(ruta):
    d = open(ruta, "rb").read()
    n = int(d.split()[1])
    return n, d[-n * n:]

def color(v):
    t = v / 255.0
    if t < 0.5:
        u = t / 0.5
        return (int(60 + 195 * u), int(90 + 165 * u), int(220 - 220 * u))
    u = (t - 0.5) / 0.5
    return (255, int(255 - 255 * u), 0)

K = 4
f_t, f_p = pygame.font.Font(None, 30), pygame.font.Font(None, 24)
n, a = leer("output/vigia/sin_cortafuegos.pgm")
_, b = leer("output/vigia/con_cortafuegos.pgm")
L = n * K
W, H = 2 * L + 90, L + 150
s = pygame.Surface((W, H)); s.fill((255, 255, 255))
for k, (datos, titulo) in enumerate([(a, "(a) Sin cortafuegos"), (b, "(b) Con cortafuegos")]):
    x0 = 30 + k * (L + 30)
    alto = sum(1 for v in datos if v > 128)  # >50%: mas de 4 de 8 sims
    print(titulo, "-> celdas con riesgo > 50%:", alto, "(%.1f%%)" % (100.0 * alto / (n * n)))
    for i in range(n):
        for j in range(n):
            pygame.draw.rect(s, color(datos[i * n + j]), (x0 + j * K, 20 + i * K, K, K))
    t = f_t.render(titulo, True, (30, 30, 30)); s.blit(t, (x0, 28 + L))
    t = f_p.render("Riesgo alto: %d celdas (%.1f%%)" % (alto, 100.0 * alto / (n * n)), True, (30, 30, 30))
    s.blit(t, (x0, 56 + L))
for bx in range(240):
    pygame.draw.line(s, color(bx * 255 // 239), (30 + bx, L + 95), (30 + bx, L + 109))
s.blit(f_p.render("0%", True, (30, 30, 30)), (30, L + 114))
s.blit(f_p.render("100% de riesgo de quema", True, (30, 30, 30)), (150, L + 114))
os.makedirs("docs/figuras", exist_ok=True)
pygame.image.save(s, "docs/figuras/fig_riesgo_comparacion.png")
print("OK: docs/figuras/fig_riesgo_comparacion.png")
