#!/usr/bin/env python3
"""Genera docs/figuras/fig_cluster.png (diagrama del clúster) con pygame, sin ventana.
Uso (desde la raíz del repo): python3 scripts/diagrama_cluster.py"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

W, H = 1200, 700
s = pygame.Surface((W, H))
s.fill((255, 255, 255))
NEGRO, GRIS, AZUL, VERDE = (30, 30, 30), (110, 110, 110), (40, 110, 220), (34, 139, 34)
f_t, f_n, f_p = pygame.font.Font(None, 34), pygame.font.Font(None, 26), pygame.font.Font(None, 22)

def texto(t, f, col, x, y, centro=True):
    r = f.render(t, True, col)
    s.blit(r, r.get_rect(center=(x, y)) if centro else (x, y))

# host
pygame.draw.rect(s, GRIS, (20, 20, W - 40, H - 40), 3, border_radius=12)
texto("Host con Docker Engine - CPU y RAM del host: [PENDIENTE]", f_t, NEGRO, W // 2, 50)

# red bridge
pygame.draw.rect(s, (225, 238, 255), (50, 100, W - 100, 46), border_radius=8)
pygame.draw.rect(s, AZUL, (50, 100, W - 100, 46), 2, border_radius=8)
texto("Red bridge interna: clusternet (resolución de nombres y SSH sin contraseña)", f_n, AZUL, W // 2, 123)

# contenedores
nodos = [
    ("master", "Compila y lanza mpirun"),
    ("worker1", "Ejecuta procesos MPI (por SSH)"),
    ("worker2", "Ejecuta procesos MPI (por SSH)"),
]
for k, (nom, rol) in enumerate(nodos):
    x = 50 + k * 385
    r = pygame.Rect(x, 210, 340, 250)
    pygame.draw.line(s, AZUL, (r.centerx, 146), (r.centerx, 210), 3)
    pygame.draw.rect(s, (240, 248, 240), r, border_radius=10)
    pygame.draw.rect(s, VERDE, r, 3, border_radius=10)
    texto(nom, f_t, NEGRO, r.centerx, r.y + 30)
    for i, l in enumerate(["4 CPUs (cpus=CPUS_NODO) y 8 GB (mem_limit)",
                           "4 slots MPI en el hostfile",
                           "Ubuntu 22.04, gcc/g++, OpenMP, OpenMPI",
                           "Usuario mpiuser", rol]):
        texto(l, f_p, NEGRO, r.centerx, r.y + 80 + i * 32)

# volúmenes
pygame.draw.rect(s, (250, 245, 225), (50, 500, W - 100, 56), border_radius=8)
pygame.draw.rect(s, GRIS, (50, 500, W - 100, 56), 2, border_radius=8)
texto("Volumen: el repositorio se monta en los tres nodos (/home/mpiuser/proyecto)", f_n, NEGRO, W // 2, 528)
pygame.draw.rect(s, (250, 245, 225), (50, 570, W - 100, 56), border_radius=8)
pygame.draw.rect(s, GRIS, (50, 570, W - 100, 56), 2, border_radius=8)
texto("Volumen shared_keys: claves SSH generadas al arrancar (no se suben al repositorio)", f_n, NEGRO, W // 2, 598)
texto("Los tres nodos comparten la CPU física del host.", f_p, GRIS, W // 2, 650)

os.makedirs("docs/figuras", exist_ok=True)
pygame.image.save(s, "docs/figuras/fig_cluster.png")
print("OK: docs/figuras/fig_cluster.png")
