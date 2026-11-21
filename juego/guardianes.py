#!/usr/bin/env python3
"""Guardianes del Chaco - visor minimo (niveles de la campana regional).
El fuego lo calcula el motor C++ (fire_seq) dentro del contenedor 'master'.
Este programa solo dibuja y envia las acciones del bombero.
Uso (desde la raiz del repo): python3 juego/guardianes.py
Controles: clic izq = cortafuegos | clic der = mochila de agua | Enter = avanzar ronda
           Retroceso = deshacer ultima accion | R = reiniciar | Esc = salir"""
import os, random, re, shutil, struct, subprocess, threading
from time import perf_counter
import pygame

CELDA = 6; PASOS_RONDA = 5; MAX_ACCIONES = 12; SEMILLA = 42
ALCANCE = 6                                  # celdas desde el bombero
LIMITES = {"APAGAR": 6, "CORTAFUEGO": 8}     # usos por ronda (se renuevan con Enter)
DIR_SONIDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonidos")
MAPA_JUEGO = "output/juego_mapa.bin"
PANEL_W = 220                                # panel lateral derecho
VIGIA_PROCS, VIGIA_SIMS, VIGIA_PASOS, VIGIA_HILOS = 3, 32, 100, 2
SALIDA_VIGIA = "output/vigia/juego.pgm"
ACCIONES = "output/juego_acciones.txt"
COLORES = {0: (222, 200, 150), 2: (255, 87, 34), 3: (55, 55, 55), 4: (121, 85, 72), 5: (33, 150, 243)}

def leer_mapa(ruta):
    with open(ruta, "rb") as f:
        if f.read(4) != b"FIRE":
            raise ValueError("mapa invalido: " + ruta)
        n = struct.unpack("<I", f.read(4))[0]
        return n, f.read(n * n), f.read(n * n)   # n, estado, combustible

def color(s, fuel):
    if s == 1:
        return (34, 80 + fuel * 115 // 255, 50)   # mas combustible, verde mas vivo
    return COLORES[s]

_TILES = {}

_FONT_ORIG = pygame.font.Font
FUENTE_PIXEL = "VT323.ttf"        # alternativa: "PixelifySans.ttf" con _ESC_FUENTE = 0.72
_ESC_FUENTE = 0.92
_RUTA_FUENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fuentes", FUENTE_PIXEL)


class _FuentePixel(_FONT_ORIG):
    """V15: la fuente por defecto pasa a ser pixel art, sin suavizado."""
    def __init__(self, nombre=None, tam=20, *a, **k):
        if nombre is None and os.path.exists(_RUTA_FUENTE):
            nombre, tam = _RUTA_FUENTE, max(10, int(round(tam * _ESC_FUENTE)))
        super().__init__(nombre, tam, *a, **k)

    def render(self, texto, antialias=True, color=(255, 255, 255), fondo=None):
        if fondo is not None:
            return super().render(texto, False, color, fondo)
        return super().render(texto, False, color)


pygame.font.Font = _FuentePixel

_DR_ORIG = pygame.draw.rect


def _rect_pixel(surf, color, rect, width=0, border_radius=0, *args, **kw):
    """V12: con border_radius dibuja esquinas escalonadas (pixel art) en vez de redondeadas."""
    if not border_radius or border_radius < 0:
        return _DR_ORIG(surf, color, rect, width)
    r = pygame.Rect(rect)
    x, y, w, h = r.x, r.y, r.w, r.h
    c = 2 if border_radius < 6 else 3
    if w < 2 * c + 2 or h < 2 * c + 2:
        return _DR_ORIG(surf, color, r, width)
    if width <= 0:
        _DR_ORIG(surf, color, (x + c, y, w - 2 * c, h))
        _DR_ORIG(surf, color, (x, y + c, w, h - 2 * c))
        if c == 3:
            _DR_ORIG(surf, color, (x + 1, y + 1, w - 2, h - 2))
        return r
    t = width
    _DR_ORIG(surf, color, (x + c, y, w - 2 * c, t))
    _DR_ORIG(surf, color, (x + c, y + h - t, w - 2 * c, t))
    _DR_ORIG(surf, color, (x, y + c, t, h - 2 * c))
    _DR_ORIG(surf, color, (x + w - t, y + c, t, h - 2 * c))
    for k in range(1, c):
        _DR_ORIG(surf, color, (x + c - k, y + k, t, t))
        _DR_ORIG(surf, color, (x + w - (c - k) - t, y + k, t, t))
        _DR_ORIG(surf, color, (x + c - k, y + h - k - t, t, t))
        _DR_ORIG(surf, color, (x + w - (c - k) - t, y + h - k - t, t, t))
    return r


pygame.draw.rect = _rect_pixel


def obtener_tiles():
    """Tiles pixel art dibujados por codigo (se construyen una sola vez)."""
    if _TILES.get('C') == CELDA:
        return _TILES
    _TILES.clear(); _TILES['C'] = CELDA
    C = CELDA

    def base(col):
        s = pygame.Surface((C, C))
        s.fill(col)
        return s

    def puntos(s, col, lista):
        for x, y in lista:
            s.set_at((x % C, y % C), col)

    veg = []
    for b in [(36, 92, 46), (48, 128, 54), (64, 164, 66)]:
        claro = tuple(min(255, c + 34) for c in b)
        brillo = tuple(min(255, c + 70) for c in b)
        oscuro = tuple(max(0, c - 18) for c in b)
        sombra = tuple(max(0, c - 34) for c in b)
        fila = []
        for v in range(4):
            s = base(b)
            if C < 12:
                s.fill(sombra, (0, C - 1, C, 1))
                s.fill(claro, (1 + v % 2, 1, max(2, C // 2), max(2, C // 3)))
                s.set_at((1 + v % 2, 1), brillo)
            else:
                puntos(s, sombra, [((v * 5 + 3) % C, (v * 3 + 1) % C), ((v * 7 + 9) % C, (v * 5 + 11) % C),
                                   ((v * 3 + 12) % C, (v * 7 + 5) % C)])
            puntos(s, oscuro, [(v + 1, C // 2 + 1), (C - 2 - v, C // 2), (v, C - 2)])
            if C >= 12:   # matas de pasto mas grandes a celda grande
                for k in range(C // 3):
                    gx, gy = (v * 5 + k * 7 + 3) % C, (k * 5 + v * 3 + 2) % (C - 2)
                    s.fill(claro, (gx, gy, 1, 2))
                    s.set_at((gx, gy), brillo)
            fila.append(s)
        veg.append(fila)
    _TILES["veg"] = veg

    agua, vacia, cortafuego, quemada, suelo_fuego = [], [], [], [], []
    for v in range(4):
        s = base((33, 150, 243)); y = 1 + (v % 3) * 2
        puntos(s, (120, 200, 255), [(v, y), (v + 1, y), (v + 2, y)])
        puntos(s, (22, 118, 205), [(v + 3, y + 1), (v + 4, y + 1)])
        puntos(s, (225, 245, 255), [(C - 1 - v, y + 3), (v + 2, y + 5)])
        if C >= 12:
            s.fill((120, 200, 255), (v + 4, y + 7, 5, 1))
            s.fill((22, 118, 205), (C - 8 - v, y + 10, 4, 1))
        agua.append(s)
        s = base((205, 160, 105))
        puntos(s, (172, 130, 84), [(v, 1), (C - 1 - v, C - 2)])
        puntos(s, (150, 175, 95), [(v + 2, 3), (v + 2, 4), (C - 1 - v, 1)])
        puntos(s, (224, 184, 130), [(C - 2 - v, 2)])
        if C >= 12:
            puntos(s, (172, 130, 84), [(v + 5, C // 2), (C - 4 - v, C // 2 + 2), (v + 2, C - 4)])
            puntos(s, (150, 175, 95), [(C // 2 + v, 3), (C // 2 + v + 1, 3), (C // 2 + v, 4)])
        vacia.append(s)
        s = base((121, 85, 72))
        for yy in range(1, C, 2):
            s.fill((88, 60, 50), (0, yy, C, 1))
        puntos(s, (150, 112, 94), [(v, 0), (C - 1 - v, C - 1)])
        if C >= 12:   # tierra removida: terrones
            for k in range(3):
                tx, ty = (v * 5 + k * 6 + 2) % (C - 3), (k * 5 + v * 3 + 3) % (C - 2)
                s.fill((160, 120, 100), (tx, ty, 3, 1))
                s.set_at((tx + 1, ty + 1), (70, 48, 40))
        cortafuego.append(s)
        s = base((45, 45, 45))
        puntos(s, (140, 50, 20), [(v, 2), (C - 1 - v, 4)])
        puntos(s, (255, 120, 30), [(v, 2)])
        puntos(s, (90, 88, 86), [(C - 2 - v, 1), (v + 1, C - 1)])
        puntos(s, (28, 28, 28), [(v + 2, 3), (C - 1 - v, 5)])
        if C >= 12:   # ceniza, carbon y una brasa
            for k in range(4):
                gx, gy = (v * 3 + k * 5 + 1) % (C - 4), (k * 4 + v * 5 + 2) % (C - 3)
                s.fill((70, 68, 66), (gx, gy, 3, 2))
                s.set_at((gx + 1, gy), (105, 102, 98))
            s.fill((100, 34, 14), (2 + v, C - 5, 4, 1))
            s.set_at((3 + v, C - 5), (230, 90, 25))
        quemada.append(s)
        suelo_fuego.append(base((90, 20, 10)))
    _TILES[5], _TILES[0], _TILES[4], _TILES[3], _TILES[2] = agua, vacia, cortafuego, quemada, suelo_fuego

    formas = [
        ([(3, 0), (5, 3), (5, 6), (1, 6), (1, 3)], [(3, 2), (4, 4), (4, 6), (2, 6), (2, 4)]),
        ([(2, 0), (5, 3), (5, 6), (0, 6), (1, 3)], [(3, 2), (4, 4), (4, 6), (1, 6), (2, 3)]),
        ([(3, 1), (5, 2), (6, 6), (1, 6), (0, 3)], [(3, 3), (4, 4), (4, 6), (2, 6), (2, 4)]),
    ]
    fuego = []
    for ext, inte in formas:
        s = pygame.Surface((C, C), pygame.SRCALPHA)
        _k = (C - 1) / 5.0
        pygame.draw.polygon(s, (255, 110, 20), [(round(x * _k), round(y * _k)) for x, y in ext])
        pygame.draw.polygon(s, (255, 220, 80), [(round(x * _k), round(y * _k)) for x, y in inte])
        s.set_at((min(C - 1, round(3 * _k)), min(C - 1, round(4 * _k))), (255, 250, 200))
        fuego.append(s)
    _TILES["fuego"] = fuego
    return _TILES


SPRITE_BOMBERO = [
    "....KKKKKK....",
    "...KRRRRRRK...",
    "..KRHHRRRRRK..",
    "..KRRRYYRRRK..",
    "..KrrrrrrrrK..",
    "..KSSSSSSSSK..",
    "..KSKYSSKYSK..",
    "..KSKKSSKKSK..",
    "..KSSSSSSSSK..",
    "...KSSMMSSK...",
    "....KKKKKK....",
    "...KuUUUUuK...",
    "..KBUYYYYUBK..",
    "..KBUUUUUUBK..",
    "...KuUYYUuK...",
    "...KBBBBBBK...",
    "...KBBKKBBK...",
    "..KKKK..KKKK..",
]
PALETA_BOMBERO = {"R": (200, 30, 30), "r": (140, 21, 21), "u": (161, 140, 28),
                  "S": (240, 190, 150), "K": (30, 30, 30), "H": (255, 130, 110), "M": (200, 100, 90),
                  "U": (230, 200, 40), "Y": (255, 255, 255), "B": (40, 110, 200)}
_SPRITES = {}

def sprite_bombero():
    """Bombero pixel art (matriz de texto escalada x2), se construye una sola vez."""
    if "bombero" not in _SPRITES:
        h, w = len(SPRITE_BOMBERO), len(SPRITE_BOMBERO[0])
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y, fila in enumerate(SPRITE_BOMBERO):
            for x, ch in enumerate(fila):
                if ch in PALETA_BOMBERO:
                    s.set_at((x, y), PALETA_BOMBERO[ch])
        _SPRITES["bombero"] = pygame.transform.scale(s, (w * 2, h * 2))
    return _SPRITES["bombero"]

def posicion_inicial(n, estado):
    """Celda libre (ni agua ni fuego) mas cercana al centro del mapa."""
    c = n // 2
    for r in range(n):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = c + dx, c + dy
                if 0 <= x < n and 0 <= y < n and estado[y * n + x] not in (2, 5):
                    return x, y
    return c, c


SPRITE_VET = [
    "....KKKKKK....",
    "...KGGGGGGK...",
    "..KGGGGGGGGK..",
    "..KGGGGGGGGK..",
    "..KGSSSSSSGK..",
    "..KGSSSSSSGK..",
    "..KGKESSKEGK..",
    "..KGKKSSKKGK..",
    "..KGSSSSSSGK..",
    "...KGSMMSGK...",
    "....KKKKKK....",
    "...KwWWWWwK...",
    "..KSWTWWTWSK..",
    "..KSWWTTWWSK..",
    "...KwWWTWwK...",
    "...KPPPPPPK...",
    "...KPPKKPPK...",
    "..KKKK..KKKK..",
]
PALETA_VET = {"G": (30, 140, 80), "g": (21, 98, 56), "w": (168, 168, 168),
              "S": (240, 190, 150), "K": (30, 30, 30), "M": (200, 100, 90),
              "E": (255, 255, 255), "T": (90, 95, 110),
              "W": (240, 240, 240), "P": (60, 60, 120)}
SPRITE_ANIMAL = [
    ".DDDD..",
    "DTTTTD.",
    "TTTTTTK",
    "TT.TT..",
]
PALETA_ANIMAL = {"D": (110, 70, 40), "T": (170, 120, 70), "K": (20, 20, 20)}

def con_sombras(pal):
    """Deriva los tonos de sombra (r, u, g, w) de los colores base de la skin."""
    for k, padre in (("r", "R"), ("u", "U"), ("g", "G"), ("w", "W")):
        if padre in pal and k in pal:
            pal[k] = tuple(int(c * 0.7) for c in pal[padre])
    return pal


ANIMALES_SPR = {
    "jaguar": ([
        "......B.B...",
        "..BHHBBBBBB.",
        ".BHDBBDBBKBB",
        "BBBBDBBBBBNN",
        "BLLLLLLLLLB.",
        ".BDBBDBBDBB.",
        ".B.B....B.B.",
        ".D.D....D.D.",
    ], {"B": (225, 170, 40), "D": (40, 25, 10), "L": (245, 225, 170), "K": (20, 20, 20),
        "H": (250, 205, 90), "N": (230, 120, 120)}),
    "tapir": ([
        "....BBBB....",
        "..BHHBBBBBB.",
        ".BBBWWWBBBKB",
        "BBBBWWWBBBBB",
        "BBBBBBBBBBDD",
        ".BBHBBBBBBBD",
        ".B.B....B.B.",
        ".D.D....D.D.",
    ], {"B": (110, 90, 80), "W": (235, 235, 235), "D": (60, 45, 40), "K": (20, 20, 20),
        "H": (150, 128, 115)}),
    "taitetu": ([
        "...DDDDDD...",
        "..DHDHDHDH..",
        ".BBBBWWBBBBB",
        "BBBBBWWBBBBK",
        "BBBBBBBBBBBB",
        ".BBBBBBBBBB.",
        "..B.B..B.B..",
        "..D.D..D.D..",
    ], {"B": (80, 70, 60), "W": (220, 210, 180), "D": (45, 38, 32), "K": (20, 20, 20),
        "H": (125, 112, 98)}),
    "loro": ([
        "....RRRR....",
        "...RHRRRR...",
        "...RRKRROO..",
        ".GGGRRRRO...",
        "GGGGGGGYY...",
        "GGHGGHGGY...",
        ".GGGGGGG....",
        "..YY..KK....",
    ], {"G": (60, 170, 70), "R": (220, 40, 40), "Y": (250, 210, 40),
        "O": (240, 150, 30), "K": (20, 20, 20), "H": (130, 225, 120)}),
}

_CUADRUPEDO = [
    "..........OO.OO.",
    ".........OBBOBBO",
    ".OO....OBBBBBBBO",
    "OBBO...OBBBBBBBO",
    "OBBO.OOOBBBBBBBO",
    ".OBOBBBBBBBBBBBO",
    "..OBBBBBBBBBNNO.",
    "..OBLLLLLLLBBOO.",
    "..OOOOOOOOOOOO..",
    "..OBBO....OBBO..",
    "..OBBO....OBBO..",
    "..OOOO....OOOO..",
]
_LORO = [
    "......OOOO......",
    ".....ORRRRO.....",
    "....ORRRRRRO....",
    "....ORRRRRROOO..",
    "....ORRRRRROPPO.",
    "....OGGGGGGOOO..",
    "...OGGGGGGGGO...",
    "..OGGGHGGGGGGO..",
    ".OYGGGGGGGGGO...",
    "OYYYGGGGGGGO....",
    ".OOO....OYO.OYO.",
    "........OOO.OOO.",
]
_OV_ANIMAL = {
    "jaguar": [(9, 2, "H"), (10, 2, "H"), (5, 5, "H"), (9, 3, "D"), (1, 3, "D"), (4, 5, "D"), (7, 5, "D"),
               (10, 5, "D"), (5, 6, "D"), (9, 6, "D")],
    "tapir": [(10, 1, "W"), (11, 1, "W"), (13, 1, "W"), (14, 1, "W"), (12, 6, "D"), (13, 6, "D"),
              (13, 5, "H"), (14, 5, "H"), (14, 4, "H"), (14, 3, "H"), (5, 5, "H"), (6, 5, "H"), (7, 5, "H")],
    "taitetu": [(8, 2, "W"), (8, 3, "W"), (8, 4, "W"), (8, 5, "W"), (5, 3, "D"), (6, 3, "D"),
                (5, 5, "H"), (6, 5, "H"), (7, 5, "H")],
    "loro": [],
}
_PAL_ANIMAL = {
    "jaguar": {"O": (50, 30, 10), "B": (225, 170, 40), "D": (40, 25, 10), "L": (245, 225, 170),
               "N": (230, 120, 120), "H": (250, 205, 90), "K": (20, 20, 20), "E": (255, 255, 255)},
    "tapir": {"O": (45, 34, 30), "B": (110, 90, 80), "D": (60, 45, 40), "L": (90, 72, 64),
              "N": (60, 45, 40), "H": (150, 128, 115), "W": (235, 235, 235), "K": (20, 20, 20), "E": (255, 255, 255)},
    "taitetu": {"O": (40, 34, 30), "B": (80, 70, 60), "D": (45, 38, 32), "L": (110, 98, 86),
                "N": (150, 105, 100), "H": (125, 112, 98), "W": (220, 210, 180), "K": (20, 20, 20), "E": (255, 255, 255)},
    "loro": {"O": (25, 30, 25), "R": (220, 40, 40), "G": (60, 170, 70), "H": (130, 225, 120),
             "Y": (250, 210, 40), "P": (240, 150, 30), "K": (20, 20, 20), "E": (255, 255, 255)},
}
_OJOS = {
    "normal": {(1, 1): "E", (2, 1): "K", (1, 2): "K", (2, 2): "K"},
    "asustado": {(0, 0): "E", (1, 0): "E", (2, 0): "E", (0, 1): "E", (1, 1): "K", (2, 1): "E",
                 (0, 2): "E", (1, 2): "E", (2, 2): "E"},
    "herido": {(0, 0): "K", (2, 0): "K", (1, 1): "K", (0, 2): "K", (2, 2): "K"},
    "feliz": {(1, 1): "K", (0, 2): "K", (2, 2): "K"},
    "parpadeo": {(0, 1): "K", (1, 1): "K", (2, 1): "K"},
}
_ESTADO_CARA = {"asustado": "asustado", "aislado": "asustado", "herido": "herido", "salvo": "feliz", "a salvo": "feliz", "parpadeo": "parpadeo"}

def matriz_animal(esp, cara):
    filas = [list(r) for r in (_LORO if esp == "loro" else _CUADRUPEDO)]
    ex = 7 if esp == "loro" else 11
    for x, y, c in _OV_ANIMAL.get(esp, []):
        filas[y][x] = c
    for (dx, dy), c in _OJOS[cara].items():
        filas[2 + dy][ex + dx] = c
    return ["".join(f) for f in filas]

def sprite_animal(esp, estado="normal"):
    if esp not in _PAL_ANIMAL:
        esp = "jaguar"
    cara = _ESTADO_CARA.get(estado, "normal")
    return sprite_generico("animal:%s:%s" % (esp, cara), matriz_animal(esp, cara), _PAL_ANIMAL[esp])


def sprite_generico(nombre, matriz, paleta, escala=2):
    """Sprite pixel art a partir de una matriz de texto (se construye una sola vez)."""
    if nombre not in _SPRITES:
        h, w = len(matriz), len(matriz[0])
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y, fila in enumerate(matriz):
            for x, ch in enumerate(fila):
                if ch in paleta:
                    s.set_at((x, y), paleta[ch])
        _SPRITES[nombre] = pygame.transform.scale(s, (w * escala, h * escala))
    return _SPRITES[nombre]

ESPECIES = ["tapir", "jaguar", "taitetu", "loro"]
ESP_INFO = {"tapir": ("T", (200, 170, 120)), "jaguar": ("J", (255, 200, 60)),
            "taitetu": ("P", (230, 140, 140)), "loro": ("L", (120, 230, 120))}

def crear_animales(n, estado, refugio, k=5):
    """k animales en celdas de vegetacion lejos del refugio. Formato: [x, y, estado]."""
    rng = random.Random(7)
    rx, ry, rw, rh = refugio
    cx, cy = rx + rw // 2, ry + rh // 2
    cand = [(i % n, i // n) for i in range(n * n)
            if estado[i] == 1 and abs(i % n - cx) + abs(i // n - cy) > 20]
    pos = rng.sample(cand, min(k, len(cand)))
    return [[x, y, "libre", ESPECIES[i % len(ESPECIES)]] for i, (x, y) in enumerate(pos)]


# Tabla de niveles: una sola fuente de verdad por nivel.
# focos=None usa el valor por defecto de gen_map.py (se ajusta mas adelante).
NIVELES = [
    dict(id="yacuiba", zona=1, nombre="Bosques de Yacuiba", n=96, semilla_mapa=42, focos=None,
         semilla=42, viento_ang=0.0, viento_fuerza=0.6, animales=5,
         dialogos="facil", dificultad=1),
    dict(id="yacuiba2", zona=1, nombre="Yacuiba II: el monte seco", n=96, semilla_mapa=11, focos=None,
         semilla=11, viento_ang=90.0, viento_fuerza=0.6, animales=5,
         dialogos="facil", dificultad=1),
    dict(id="yacuiba3", zona=1, nombre="Yacuiba III: la ribera", n=96, semilla_mapa=33, focos=4,
         semilla=33, viento_ang=315.0, viento_fuerza=0.7, animales=6,
         dialogos="facil", dificultad=2),
    dict(id="aguarague", zona=2, nombre="Serranía del Aguaragüe", n=112, semilla_mapa=7, focos=None,
         semilla=7, viento_ang=45.0, viento_fuerza=0.8, animales=6,
         dialogos="medio", dificultad=2),
    dict(id="aguarague2", zona=2, nombre="Aguaragüe II: las laderas", n=112, semilla_mapa=14, focos=None,
         semilla=14, viento_ang=180.0, viento_fuerza=0.8, animales=6,
         dialogos="medio", dificultad=2),
    dict(id="aguarague3", zona=2, nombre="Aguaragüe III: la quebrada", n=112, semilla_mapa=58, focos=None,
         semilla=58, viento_ang=225.0, viento_fuerza=0.9, animales=7,
         dialogos="medio", dificultad=3),
    dict(id="tarija", zona=3, nombre="Región de Tarija", n=128, semilla_mapa=21, focos=None,
         semilla=21, viento_ang=90.0, viento_fuerza=0.9, animales=7,
         dialogos="dificil", dificultad=3),
    dict(id="tarija2", zona=3, nombre="Tarija II: el valle", n=128, semilla_mapa=35, focos=4,
         semilla=35, viento_ang=0.0, viento_fuerza=0.9, animales=7,
         dialogos="dificil", dificultad=3),
    dict(id="tarija3", zona=3, nombre="Tarija III: la cuesta", n=128, semilla_mapa=77, focos=5,
         semilla=77, viento_ang=270.0, viento_fuerza=1.0, animales=8,
         dialogos="dificil", dificultad=3),
    dict(id="gran_incendio", zona=4, nombre="El gran incendio", n=128, semilla_mapa=99, focos=None,
         semilla=99, viento_ang=135.0, viento_fuerza=1.1, animales=8,
         dialogos="silencio", dificultad=4),
]
NIVEL_SEL = {"i": 0}   # indice del nivel activo (el menu de niveles lo cambiara)

NIVEL_CORAZON = dict(id="corazon", zona=0, nombre="El corazón del incendio", n=128, semilla_mapa=63, focos=9,
                     semilla=63, viento_ang=200.0, viento_fuerza=1.2, animales=8,
                     dialogos="silencio", dificultad=4)

def nivel_actual():
    if MODO_ESP["id"] == "corazon":
        return NIVEL_CORAZON
    return NIVELES[NIVEL_SEL["i"]]

def ruta_mapa(niv):
    """Un archivo de mapa por nivel: el nombre lleva tamaño y semilla (antes solo el tamaño)."""
    suf = f"_f{niv['focos']}" if niv["focos"] is not None else ""
    return f"data/maps/map_{niv['n']}_s{niv['semilla_mapa']}{suf}.bin"

def args_viento(niv):
    return f"--viento-ang {niv['viento_ang']} --viento-fuerza {niv['viento_fuerza']}"

def asegurar_motor(niv=None):
    """Compila fire_seq y genera el mapa del nivel dentro del contenedor si faltan."""
    niv = niv or nivel_actual()
    focos = f" --focos {niv['focos']}" if niv["focos"] is not None else ""
    mapa = ruta_mapa(niv)
    orden = ("cd /home/mpiuser/proyecto && mkdir -p bin data/maps output && "
             "{ [ -x bin/fire_seq ] || g++ -std=c++17 -O2 -I src/common src/sequential/fire_seq.cpp -o bin/fire_seq; } && "
             f"{{ [ -f {mapa} ] || python3 data/gen_map.py --n {niv['n']} --seed {niv['semilla_mapa']}{focos} --out {mapa}; }}")
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c", orden],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("No se pudo preparar el motor (clúster arriba? docker compose up -d):\n" + (r.stderr or r.stdout))


def correr_ronda(paso, pendientes):
    with open(ACCIONES, "w") as f:
        for tipo, x, y in pendientes:
            f.write(f"{paso} {tipo} {x} {y}\n")
    orden = (f"cd /home/mpiuser/proyecto && ./bin/fire_seq --mapa {MAPA_JUEGO} --pasos {PASOS_RONDA} "
             f"--semilla {nivel_actual()['semilla']} {args_viento(nivel_actual())} "
             f"--paso-inicial {paso} --acciones {ACCIONES} --guardar-mapa {MAPA_JUEGO}")
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c", orden],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:120])

MODO = {"ia": "veterinaria"}   # quien controla la IA: "veterinaria", "bombero" o None (dos jugadores)

MODO_ESP = {"id": None}         # modo especial activo: None (campaña), "record", ...
MARGEN_VISTA_X = 80    # px que se restan al ancho para el dock de Ubuntu y el borde
MARGEN_VISTA_Y = 110   # px que se restan al alto para la barra superior y la de titulo
ALTO_PANT = {"h": 768, "w": 1366}          # alto del escritorio, para calcular CELDA por nivel
_MINIATURAS = {}
_MAPAS_LISTOS = {"ok": False}
DIALOGO_TXT = {"facil": "inicio, final, ocasionales y datos educativos",
               "medio": "inicio, final y avisos importantes",
               "dificil": "solo avisos críticos y un cierre corto",
               "silencio": "casi en silencio: inicio y avisos críticos"}

def texto_viento(niv):
    dirs = ["este", "sureste", "sur", "suroeste", "oeste", "noroeste", "norte", "noreste"]
    d = dirs[int(((niv["viento_ang"] % 360) + 22.5) // 45) % 8]
    f = niv["viento_fuerza"]
    fuerza = "suave" if f < 0.7 else "moderado" if f < 1.0 else "fuerte"
    return f"viento {fuerza} hacia el {d}"

def miniatura_nivel(niv, lado):
    clave = (niv["id"], lado)
    if clave not in _MINIATURAS:
        n, estado, _ = leer_mapa(ruta_mapa(niv))
        s = pygame.Surface((n, n))
        paleta = {1: (46, 125, 50), 2: (230, 60, 30), 5: (33, 110, 190)}
        for y in range(n):
            for x in range(n):
                s.set_at((x, y), paleta.get(estado[y * n + x], (150, 125, 90)))
        m = pygame.transform.smoothscale(s, (lado, lado))
        k = lado / n
        pygame.draw.rect(m, (120, 255, 120), pygame.Rect(int(4 * k), int((n - 14) * k), int(10 * k), int(10 * k)), 2)
        _MINIATURAS[clave] = m
    return _MINIATURAS[clave]

def dibujar_estrellas(pantalla, cx, cy, llenas, total=4, r=7):
    import math
    for i in range(total):
        c = cx + i * (2 * r + 4)
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            rr = r if k % 2 == 0 else r * 0.45
            pts.append((c + rr * math.cos(a), cy + rr * math.sin(a)))
        if i < llenas:
            pygame.draw.polygon(pantalla, (255, 200, 60), pts)
        else:
            pygame.draw.polygon(pantalla, (110, 110, 110), pts, 1)

ZONAS = {1: ("Yacuiba", "Bosques de Yacuiba"), 2: ("Aguaragüe", "Serranía del Aguaragüe"),
         3: ("Tarija", "Región de Tarija"), 4: ("Gran incendio", "El gran incendio")}

CAMPANA_RUTA = "output/campana.json"

def cargar_campana():
    import json
    try:
        with open(CAMPANA_RUTA, encoding="utf-8") as f:
            return set(json.load(f).get("completados", []))
    except Exception:
        return set()

def marcar_nivel_completo(id_nivel):
    import json
    c = cargar_campana()
    c.add(id_nivel)
    try:
        os.makedirs(os.path.dirname(CAMPANA_RUTA) or ".", exist_ok=True)
        with open(CAMPANA_RUTA, "w", encoding="utf-8") as f:
            json.dump({"completados": sorted(c)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def nivel_completado(i):
    return NIVELES[i]["id"] in cargar_campana()

def nivel_bloqueado(i):
    """Una zona se abre al completar todos los niveles de la anterior (CAMPANA_ABIERTA=1 abre todo)."""
    if os.environ.get("CAMPANA_ABIERTA"):
        return False
    z = NIVELES[i]["zona"]
    if z <= 1:
        return False
    hechos = cargar_campana()
    return any(nv["id"] not in hechos for nv in NIVELES if nv["zona"] == z - 1)

def _degradado_tramado(w, h, f, banda=8):
    """Degradado vertical en bandas con transicion en damero (dithering). f(t) -> color."""
    s = pygame.Surface((w, h))
    n = (h + banda - 1) // banda
    cols = [f(min(1.0, (k * banda) / max(1, h))) for k in range(n + 1)]
    for k in range(n):
        y0 = k * banda
        s.fill(cols[k], (0, y0, w, min(banda, h - y0)))
    for k in range(n - 1):
        y0 = k * banda
        for dy, paso in ((banda - 2, 4), (banda - 1, 2)):
            y = y0 + dy
            if y < h:
                for x in range(0, w, paso):
                    s.set_at((x, y), cols[k + 1])
    return s


def fondo_marca(w, h):
    """Degradado verde del menu, cacheado, para las pantallas internas."""
    cache = _SPRITES.setdefault("fondo_marca", {})
    s = cache.get((w, h))
    if s is None:
        s = _degradado_tramado(w, h, lambda t: (int(15 + 90 * t), int(40 - 10 * t), int(25 - 10 * t)))
        cache[(w, h)] = s
    return s


def seleccionar_nivel(pantalla, fuente):
    """Devuelve el indice del nivel elegido, None si vuelve, 'salir' si cierra."""
    w, h = pantalla.get_size()
    f_tit = pygame.font.Font(None, 48)
    f_nom = pygame.font.Font(None, 26)
    f_p = pygame.font.Font(None, 21)
    if not _MAPAS_LISTOS["ok"]:
        pantalla.fill((22, 34, 26))
        t = fuente.render("Preparando mapas de los niveles...", True, (230, 230, 230))
        pantalla.blit(t, t.get_rect(center=(w // 2, h // 2)))
        pygame.display.flip()
        for niv in NIVELES:
            asegurar_motor(niv)
        _MAPAS_LISTOS["ok"] = True
    mg = 16
    zonas = sorted(set(nv["zona"] for nv in NIVELES))
    tw = (w - 2 * mg - 8 * (len(zonas) - 1)) // len(zonas)
    tab_rects = {z: pygame.Rect(mg + j * (tw + 8), 78, tw, 34) for j, z in enumerate(zonas)}
    sel = NIVEL_SEL["i"]
    aviso = ""
    reloj = pygame.time.Clock()
    while True:
        zona = NIVELES[sel]["zona"]
        idxs = [i for i, nv in enumerate(NIVELES) if nv["zona"] == zona]
        k = len(idxs)
        cw = min(300, (w - mg * (k + 1)) // k)
        x0 = (w - (k * cw + (k - 1) * mg)) // 2
        lado = min(cw - 20, 170)
        ch = lado + 86
        y0 = 126
        rects = {i: pygame.Rect(x0 + j * (cw + mg), y0, cw, ch) for j, i in enumerate(idxs)}
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                aviso = ""
                if e.key == pygame.K_ESCAPE:
                    sonar("ui_volver")
                    return None
                elif e.key == pygame.K_LEFT:
                    sel = idxs[(idxs.index(sel) - 1) % k]; sonar("ui_mover")
                elif e.key == pygame.K_RIGHT:
                    sel = idxs[(idxs.index(sel) + 1) % k]; sonar("ui_mover")
                elif e.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_TAB):
                    sonar("ui_mover")
                    paso = -1 if e.key == pygame.K_UP else 1
                    z = zonas[(zonas.index(zona) + paso) % len(zonas)]
                    sel = next(i for i, nv in enumerate(NIVELES) if nv["zona"] == z)
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if nivel_bloqueado(sel):
                        aviso = "Nivel bloqueado: completa antes la zona anterior."
                        sonar("ui_volver")
                    else:
                        sonar("ui_jugar")
                        return sel
            elif e.type == pygame.MOUSEMOTION:
                for i, r in rects.items():
                    if r.collidepoint(e.pos):
                        if sel != i:
                            sonar("ui_mover")
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for z, r in tab_rects.items():
                    if r.collidepoint(e.pos):
                        sonar("ui_aceptar"); sel = next(i for i, nv in enumerate(NIVELES) if nv["zona"] == z)
                for i, r in rects.items():
                    if r.collidepoint(e.pos):
                        if nivel_bloqueado(i):
                            aviso = "Nivel bloqueado: completa antes la zona anterior."; sonar("ui_volver")
                        else:
                            sonar("ui_aceptar")
                            return i
        zona = NIVELES[sel]["zona"]
        pantalla.blit(fondo_marca(w, h), (0, 0))
        t = f_tit.render("Elige el nivel", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 40)))
        for z, r in tab_rects.items():
            act = (z == zona)
            pygame.draw.rect(pantalla, (255, 120, 60) if act else (50, 62, 54), r, border_radius=6)
            s = f_nom.render(f"{z}. {ZONAS[z][0]}", True, (255, 255, 255) if act else (190, 190, 190))
            pantalla.blit(s, s.get_rect(center=r.center))
        for i, r in rects.items():
            niv = NIVELES[i]; r = r.move(0, -2) if i == sel else r
            pygame.draw.rect(pantalla, (40, 52, 44), r, border_radius=8)
            pygame.draw.rect(pantalla, (255, 200, 120) if i == sel else (90, 90, 90), r, 3, border_radius=8)
            pantalla.blit(miniatura_nivel(niv, lado), (r.centerx - lado // 2, r.y + 10))
            nom = f_nom.render(niv["nombre"], True, (255, 255, 255))
            if nom.get_width() > cw - 8:
                nom = f_p.render(niv["nombre"], True, (255, 255, 255))
            pantalla.blit(nom, nom.get_rect(center=(r.centerx, r.y + lado + 30)))
            dibujar_estrellas(pantalla, r.centerx - 33, r.y + lado + 56, niv["dificultad"])
            if nivel_completado(i):
                cx, cy = r.right - 22, r.y + 22
                pygame.draw.circle(pantalla, (40, 150, 70), (cx, cy), 14)
                pygame.draw.lines(pantalla, (255, 255, 255), False,
                                  [(cx - 7, cy), (cx - 2, cy + 6), (cx + 8, cy - 6)], 3)
            if nivel_bloqueado(i):
                vel = pygame.Surface(r.size, pygame.SRCALPHA)
                vel.fill((10, 14, 12, 190))
                pantalla.blit(vel, r.topleft)
                c = f_nom.render("BLOQUEADO", True, (255, 200, 90))
                pantalla.blit(c, c.get_rect(center=(r.centerx, r.y + lado // 2 + 10)))
        niv = NIVELES[sel]
        py = y0 + ch + 14
        ficha = pygame.Rect(mg, py, w - 2 * mg, h - py - 44)
        pygame.draw.rect(pantalla, (32, 44, 36), ficha, border_radius=8)
        pygame.draw.rect(pantalla, (255, 170, 60), ficha, 2, border_radius=8)
        lineas = [
            (niv["nombre"], f_nom, (255, 170, 60)),
            (f"Mapa de {niv['n']}x{niv['n']} celdas, {texto_viento(niv)}.", fuente, (230, 230, 230)),
            (f"Objetivo: apagar el incendio, llevar los {niv['animales']} animales al refugio y conservar el bosque.", fuente, (230, 230, 230)),
            ("Comentarios de los personajes: " + DIALOGO_TXT[niv["dialogos"]] + ".", fuente, (230, 230, 230)),
            ((aviso or "Mapa ilustrativo, no a escala real."), f_p, (255, 150, 90) if aviso else (170, 170, 170)),
        ]
        yy = ficha.y + 14
        for txt, fnt, col in lineas:
            pantalla.blit(fnt.render(txt, True, col), (ficha.x + 16, yy))
            yy += 30
        v = fuente.render("Izq/Der: nivel   Arriba/Abajo: zona   Enter: jugar   Esc: volver", True, (170, 170, 170))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 22)))
        pygame.display.flip()
        reloj.tick(30)

RECORDS_RUTA = "output/records.json"
MODOS_ESP = [("record", "Modo récord", True,
              "Mismo mapa y misma semilla siempre: consigue la mejor puntuación en un nivel."),
             ("supervivencia", "Supervivencia", True,
              "Más animales y el bosque no cuenta: salva a todos los que puedas."),
             ("desafio", "Desafío", True,
              "Tanque de agua reducido y un máximo de rondas: hazlo con menos recursos."),
             ("corazon", "El corazón del incendio", True,
              "Un escenario especial con 9 focos y viento fuerte. Va directo, sin elegir nivel.")]

def cargar_records():
    import json
    try:
        with open(RECORDS_RUTA, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def registrar_record(est, ev):
    """Modo récord: guarda la mejor puntuación por nivel (solo si la misión se cumple)."""
    import json
    est["record_msg"] = ""
    if MODO_ESP["id"] not in ("record", "supervivencia", "desafio", "corazon") or not str(ev.get("titulo", "")).startswith("MISION CUMPLIDA"):
        return
    r = cargar_records()
    idn = nivel_actual()["id"]
    if MODO_ESP["id"] in ("supervivencia", "desafio"):
        idn = MODO_ESP["id"] + ":" + idn
    ant = r.get(idn)
    p = ev.get("puntos", 0)
    if ant is None or p > ant.get("puntos", 0):
        r[idn] = dict(puntos=p, estrellas=ev.get("estrellas", 0), ronda=ev.get("ronda", 0))
        est["record_msg"] = "¡Nuevo récord!" if ant is None else f"¡Nuevo récord! Superaste tus {ant.get('puntos', 0)} puntos."
    elif p == ant.get("puntos", 0):
        est["record_msg"] = "Igualaste tu récord."
    else:
        est["record_msg"] = f"Tu récord es {ant.get('puntos', 0)}: te faltaron {ant.get('puntos', 0) - p} puntos."
    try:
        os.makedirs(os.path.dirname(RECORDS_RUTA) or ".", exist_ok=True)
        with open(RECORDS_RUTA, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def seleccionar_modo_especial(pantalla, fuente):
    """Devuelve el id del modo especial, None si vuelve, 'salir' si cierra."""
    f_tit = pygame.font.Font(None, 56)
    f_op = pygame.font.Font(None, 36)
    w, h = pantalla.get_size()
    rects = [pygame.Rect(w // 2 - 260, 200 + i * 80, 520, 56) for i in range(len(MODOS_ESP))]
    reloj = pygame.time.Clock()
    sel = 0
    while True:
        elegido = None
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    sonar("ui_volver")
                    return None
                elif e.key == pygame.K_UP:
                    sel = (sel - 1) % len(MODOS_ESP); sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(MODOS_ESP); sonar("ui_mover")
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    sonar("ui_aceptar" if MODOS_ESP[sel][2] else "ui_volver")
                    elegido = sel
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        if sel != i:
                            sonar("ui_mover")
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sel = i
                        elegido = i; sonar("ui_aceptar" if MODOS_ESP[i][2] else "ui_volver")
        if elegido is not None and MODOS_ESP[elegido][2]:
            return MODOS_ESP[elegido][0]
        pantalla.blit(fondo_marca(w, h), (0, 0))
        t = f_tit.render("Modos especiales", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 120)))
        for i, r in enumerate(rects):
            ok = MODOS_ESP[i][2]
            col = color_boton(True) if i == sel and ok else (90, 90, 90) if i == sel else (38, 56, 44)
            rr = rect_boton(r, i == sel)
            pygame.draw.rect(pantalla, (0, 0, 0), rr.move(0, 3), border_radius=8)
            pygame.draw.rect(pantalla, col, rr, border_radius=8)
            pygame.draw.rect(pantalla, (255, 200, 120) if i == sel and ok else (90, 120, 95), rr, 2, border_radius=8)
            s = f_op.render(MODOS_ESP[i][1] + ("" if ok else " (próximamente)"), True,
                            (255, 255, 255) if ok else (150, 150, 150))
            pantalla.blit(s, s.get_rect(center=r.center))
        d = fuente.render(MODOS_ESP[sel][3], True, (230, 230, 230))
        pantalla.blit(d, d.get_rect(center=(w // 2, 200 + len(MODOS_ESP) * 80 + 20)))
        v = fuente.render("Arriba/Abajo: elegir   Enter: continuar   Esc: volver", True, (170, 170, 170))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 40)))
        pygame.display.flip()
        reloj.tick(30)

def seleccionar_modo(pantalla, fuente):
    """Devuelve 'dos', 'veterinaria' o 'bombero' (rol que controla la IA), None si vuelve, 'salir' si cierra."""
    f_tit = pygame.font.Font(None, 56)
    f_op = pygame.font.Font(None, 36)
    opciones = [("Dos jugadores", "dos",
                 "Veterinaria: W A S D y E.   Bombero: flechas y ratón."),
                ("Solitario: soy el Bombero", "veterinaria",
                 "Flechas y ratón. La IA controla a la veterinaria."),
                ("Solitario: soy la Veterinaria", "bombero",
                 "W A S D y E. La IA controla al bombero.")]
    w, h = pantalla.get_size()
    rects = [pygame.Rect(w // 2 - 260, 280 + i * 80, 520, 56) for i in range(len(opciones))]
    reloj = pygame.time.Clock()
    sel = 0
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    sonar("ui_volver")
                    return None
                elif e.key == pygame.K_UP:
                    sel = (sel - 1) % len(opciones); sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(opciones); sonar("ui_mover")
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    sonar("ui_aceptar")
                    r_ = elegir_dificultad_modo(pantalla, fuente, opciones[sel][1])
                    if r_ == "salir":
                        return "salir"
                    if r_ is not None:
                        return r_
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        if sel != i:
                            sonar("ui_mover")
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sonar("ui_aceptar"); r_ = elegir_dificultad_modo(pantalla, fuente, opciones[i][1])
                        if r_ == "salir":
                            return "salir"
                        if r_ is not None:
                            return r_
        pantalla.blit(fondo_marca(w, h), (0, 0))
        t = f_tit.render("Elige el modo de juego", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 170)))
        for i, r in enumerate(rects):
            rr = rect_boton(r, i == sel)
            pygame.draw.rect(pantalla, (0, 0, 0), rr.move(0, 3), border_radius=8)
            pygame.draw.rect(pantalla, color_boton(i == sel), rr, border_radius=8)
            pygame.draw.rect(pantalla, (255, 200, 120) if i == sel else (90, 120, 95), rr, 2, border_radius=8)
            s = f_op.render(opciones[i][0], True, (255, 255, 255))
            pantalla.blit(s, s.get_rect(center=r.center))
        d = fuente.render(opciones[sel][2], True, (230, 230, 230))
        pantalla.blit(d, d.get_rect(center=(w // 2, 280 + 3 * 80 + 20)))
        v = fuente.render("Esc: volver", True, (170, 170, 170))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 40)))
        pygame.display.flip()
        reloj.tick(30)

MAQUETAS = {
    "Centro de Análisis": ("Centro de Análisis y Predicción", [
        "Laboratorio del Vigía: simulaciones Monte Carlo con tus propios parámetros.",
        "",
        "Podrás cambiar el número de simulaciones y el ángulo y la fuerza del viento.",
        "La humedad aparece como próximamente: el motor aún no la recibe.",
        "Compararás el mapa de riesgo sin cortafuegos y con cortafuegos.",
        "",
        "Los resultados son experimentales y educativos, no predicciones oficiales.",
        "Estado: maqueta. El Vigía ya funciona dentro de la partida (tecla V)."]),
    "Cuaderno de Guardianes": ("Cuaderno de Guardianes", [
        "Aquí se guardará lo que descubras durante las misiones.",
        "",
        "Enciclopedia de fauna: tapir, jaguar, taitetú y loro.",
        "Guía de prevención: causas de incendios y medidas preventivas.",
        "Manual de emergencias: herramientas y recomendaciones de actuación.",
        "Atlas de incendios: propagación, mapas de riesgo y simulaciones.",
        "",
        "Estado: maqueta. Si lo abres en partida, el juego se pausará."]),
    "Salón de Guardianes": ("Salón de Guardianes", [
        "Aquí se guardarán tus mejores resultados:",
        "",
        "Mejor puntuación.",
        "Mayor cantidad de animales rescatados.",
        "Mayor porcentaje de bosque conservado.",
        "Menor cantidad de rondas utilizadas.",
        "",
        "Estado: maqueta. Se actualizará al cerrar la evaluación de cada misión."]),
    "Próximamente": ("Próximamente", [
        "Lo que viene después de esta versión:",
        "",
        "Cámara inteligente y pantalla dividida.",
        "Más niveles, especies y contenido educativo."]),
}

SALON_RUTA = "output/salon.json"

def cargar_salon():
    import json
    base = dict(puntos=0, nivel_puntos="", salvos=0, bosque=0, rondas=None, partidas=0)
    try:
        with open(SALON_RUTA, encoding="utf-8") as f:
            base.update(json.load(f))
    except Exception:
        pass
    return base

ECO_RUTA = "output/ecomonedas.json"
ECO_POR_ANIMAL, ECO_MISION, ECO_POR_ESTRELLA = 10, 20, 5

def cargar_eco():
    import json
    base = dict(saldo=0, comprados=[], equipado={})
    try:
        with open(ECO_RUTA, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                base.update(d)
    except Exception:
        pass
    return base

def guardar_eco(d):
    import json
    try:
        os.makedirs(os.path.dirname(ECO_RUTA) or ".", exist_ok=True)
        with open(ECO_RUTA, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def monedas_partida(ev):
    cumplida = str(ev.get("titulo", "")).startswith("MISION CUMPLIDA")
    if MODO_ESP["id"] and not cumplida:
        return 0
    g = ev.get("salvos", 0) * ECO_POR_ANIMAL
    if cumplida:
        g += ECO_MISION + ev.get("estrellas", 0) * ECO_POR_ESTRELLA
    return g

# Skins: solo recoloreo de paleta (casco/gorro y uniforme/bata), sin ventajas (spec 10.4)
SKINS = {
    "bombero": [("Clásico", 0, {}),
                ("Guardaparque", 60, {"R": (90, 100, 40), "U": (190, 170, 120)}),
                ("Aguaragüe", 100, {"R": (240, 130, 30), "U": (30, 50, 110)}),
                ("Ceibo", 150, {"R": (230, 60, 140), "U": (200, 30, 30)})],
    "vet": [("Clásica", 0, {}),
            ("Cuaderno", 60, {"G": (40, 90, 190), "W": (245, 235, 200)}),
            ("Quebracho", 100, {"G": (110, 70, 40), "W": (190, 230, 180)}),
            ("Aurora", 150, {"G": (130, 70, 190), "W": (240, 240, 240)})],
}
SKIN_ACTUAL = {"bombero": 0, "vet": 0}

def skin_comprada(pers, i, d=None):
    if d is None:
        d = cargar_eco()
    return i == 0 or f"{pers}:{i}" in d.get("comprados", [])

def skin_equipada(pers, d=None):
    if d is None:
        d = cargar_eco()
    eq = d.get("equipado", {})
    i = eq.get(pers, 0) if isinstance(eq, dict) else 0
    if not isinstance(i, int) or not 0 <= i < len(SKINS[pers]) or not skin_comprada(pers, i, d):
        return 0
    return i

def refrescar_skins():
    d = cargar_eco()
    for p in SKINS:
        SKIN_ACTUAL[p] = skin_equipada(p, d)

def comprar_skin(pers, i):
    d = cargar_eco()
    nombre, precio, _ = SKINS[pers][i]
    if skin_comprada(pers, i, d):
        return False, "Ya la tienes"
    if d.get("saldo", 0) < precio:
        return False, f"Te faltan {precio - d.get('saldo', 0)} EcoMonedas"
    d["saldo"] = d.get("saldo", 0) - precio
    d.setdefault("comprados", []).append(f"{pers}:{i}")
    if not isinstance(d.get("equipado"), dict):
        d["equipado"] = {}
    d["equipado"][pers] = i
    guardar_eco(d)
    refrescar_skins()
    return True, f"Comprada: {nombre}"

def equipar_skin(pers, i):
    d = cargar_eco()
    if not skin_comprada(pers, i, d):
        return False, "Aún no la tienes"
    if not isinstance(d.get("equipado"), dict):
        d["equipado"] = {}
    d["equipado"][pers] = i
    guardar_eco(d)
    refrescar_skins()
    return True, f"Equipada: {SKINS[pers][i][0]}"

def sprite_chibi(pers, i):
    # personajes chibi (juego/sprites_chibi.py): 33x51 y 39x51 px, escala 1; las skins recolorean por grupos
    import sprites_chibi
    nombre = pers if i == 0 else f"{pers}:{i}"
    if nombre not in _SPRITES:
        _SPRITES[nombre] = sprites_chibi.construir(pers, {} if i == 0 else SKINS[pers][i][2])
    return nombre, _SPRITES[nombre]


def sprite_personaje(pers, i=None):
    # devuelve (nombre_de_cache, sprite); el nombre incluye la skin para sprite_paso
    if i is None:
        i = SKIN_ACTUAL[pers]
    return sprite_chibi(pers, i)

refrescar_skins()

def pagar_monedas(est, ev):
    d = cargar_eco()
    g = monedas_partida(ev)
    d["saldo"] = d.get("saldo", 0) + g
    guardar_eco(d)
    sonar("ui_moneda") if g else None; est["monedas_txt"] = f"   EcoMonedas: +{g} (saldo {d['saldo']})"

def registrar_salon(est):
    """Actualiza los records con la evaluacion de la partida (una vez por partida)."""
    import json
    if est.get("salon_ok"):
        return
    est["salon_ok"] = True
    ev = est.get("evaluacion") or {}
    if not ev:
        return
    desbloquear(est, "guia:causas"); desbloquear(est, "atlas:motor")
    if est.get("ia_rol"):
        desbloquear(est, "manual:ia")
    pagar_monedas(est, ev)
    if MODO_ESP["id"]:
        registrar_record(est, ev)   # los modos especiales no tocan el Salón ni la campaña
        return
    s = cargar_salon()
    s["partidas"] += 1
    if ev.get("puntos", 0) > s["puntos"]:
        s["puntos"] = ev["puntos"]; s["nivel_puntos"] = nivel_actual()["nombre"]
    s["salvos"] = max(s["salvos"], ev.get("salvos", 0))
    s["bosque"] = max(s["bosque"], ev.get("bosque", 0))
    if str(ev.get("titulo", "")).startswith("MISION CUMPLIDA"):
        marcar_nivel_completo(nivel_actual()["id"])
        r = ev.get("ronda", 0)
        if s["rondas"] is None or r < s["rondas"]:
            s["rondas"] = r
    try:
        with open(SALON_RUTA, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def lineas_salon():
    s = cargar_salon()
    if s["partidas"] == 0:
        return ["Aún no hay partidas registradas.", "",
                "Termina una misión y tus mejores resultados aparecerán aquí."]
    return [f"Partidas jugadas: {s['partidas']}", "",
            f"Mejor puntuación: {s['puntos']}  ({s['nivel_puntos']})",
            f"Más animales rescatados: {s['salvos']}",
            f"Mayor porcentaje de bosque conservado: {s['bosque']}%",
            "Menos rondas en una misión cumplida: " + (str(s["rondas"]) if s["rondas"] is not None else "aún ninguna")]

# Fichas del Cuaderno. Las de fauna son PROVISIONALES: verificar con fuentes antes de la entrega.
CUADERNO = [
    ("Enciclopedia de fauna", [
        ("Tapir", ["Hábitat: bosques y zonas cercanas al agua.",
                   "Protección: dispersa semillas y ayuda a mantener el monte. Evita el fuego y los atropellos.",
                   "[ficha provisional: verificar datos]"]),
        ("Jaguar", ["Hábitat: bosques extensos y poco perturbados.",
                    "Protección: es un depredador clave; necesita territorio amplio y sin incendios.",
                    "[ficha provisional: verificar datos]"]),
        ("Taitetú", ["Hábitat: monte y bosque seco, en grupos.",
                     "Protección: se desplaza en manada; cuando el fuego avanza hay que abrirle camino.",
                     "[ficha provisional: verificar datos]"]),
        ("Loro", ["Hábitat: arboledas y bosque.",
                  "Protección: se esconde entre el follaje; la veterinaria debe localizarlo antes de que llegue el fuego.",
                  "[ficha provisional: verificar datos]"])]),
    ("Guía de prevención", [
        ("Causas frecuentes", ["Las quemas agrícolas sin control y los descuidos con fuego son causas frecuentes de incendios forestales.",
                               "[contenido provisional: verificar con fuentes]"]),
        ("Ante un foco", ["No encender fuego con viento y avisar de inmediato a las autoridades ante un foco.",
                          "[contenido provisional: verificar con fuentes]"]),
        ("Cortafuegos", ["Un cortafuegos es una franja sin vegetación combustible que frena el avance del fuego.",
                         "En el juego se construye con clic izquierdo y necesita 4 s de recuperación.",
                         "[contenido provisional: verificar con fuentes]"])]),
    ("Manual de emergencias", [
        ("Mochila de agua", ["Clic derecho apaga una celda en llamas.",
                             "El tanque tiene 6 cargas y se recarga junto al río."]),
        ("Cortafuegos", ["Clic izquierdo crea una barrera que frena el avance del fuego.",
                         "Recuperación: 4 s."]),
        ("Manguera de presión (G)", ["Apunta a varios focos cercanos a la vez y gasta una carga de agua por foco.",
                                     "Recuperación: 8 s."]),
        ("Torre de vigilancia (T)", ["Marca los focos que hay alrededor del bombero.",
                                     "Recuperación: 15 s."]),
        ("Protección térmica (H)", ["Durante 6 s el bombero cruza celdas en llamas sin recibir daño.",
                                    "Recuperación: 20 s."]),
        ("Rescate (E)", ["Recoge o suelta un animal cercano.",
                         "Llévalo al refugio (zona verde) para ponerlo a salvo."]),
        ("Botiquín (Z)", ["Atiende a un animal herido, aislado o asustado que esté cerca.",
                          "Recuperación: 8 s."]),
        ("Rastreo animal (X)", ["Marca los animales que hay cerca de la veterinaria.",
                                "Recuperación: 10 s."]),
        ("Señal de auxilio (Q)", ["Marca los animales aislados.",
                                  "Recuperación: 12 s."]),
        ("Apoyo al bombero (F)", ["Si la veterinaria está a 2 celdas o menos, le da +2 de agua y +15 de vida.",
                                  "Recuperación: 15 s."]),
        ("Compañero IA", ["En solitario, la IA controla al otro personaje. Elegirás su dificultad antes de jugar.",
                          "Asistente: prioriza apoyarte. Equilibrado: usa manguera (bombero) y botiquín (veterinaria).",
                          "Experto: además usa la señal de auxilio y prioriza lo que amenaza el refugio."])]),
    ("Atlas de incendios", [
        ("Propagación del fuego", ["El fuego avanza más rápido en la dirección del viento.",
                                   "El motor es un autómata celular estocástico: cada celda cambia de estado según sus vecinas."]),
        ("El Vigía", ["Pulsa V para calcular el riesgo de quema con simulaciones Monte Carlo.",
                      "Muchas simulaciones del mismo incendio dan la probabilidad de que cada celda se queme."]),
        ("Niveles de emergencia", ["Inicial: menos de 15% del bosque perdido. Avanzada: menos de 35%. Crítica: 35% o más.",
                                   "En emergencia crítica empieza una cuenta regresiva."]),
        ("Modalidades del motor", ["El motor existe en versión secuencial, OpenMP, MPI e híbrida (MPI + OpenMP).",
                                   "En cada ronda el juego usa la versión secuencial; el Vigía usa la híbrida."])]),
]

# Claves estables de cada ficha (mismo orden que CUADERNO). Lo desbloqueado va a output/cuaderno.json.
CUAD_CLAVES = [
    ["fauna:tapir", "fauna:jaguar", "fauna:taitetu", "fauna:loro"],
    ["guia:causas", "guia:foco", "guia:cortafuegos"],
    ["manual:mochila", "manual:cortafuego", "manual:manguera", "manual:torre", "manual:termica",
     "manual:rescate", "manual:botiquin", "manual:rastreo", "manual:senal", "manual:apoyo", "manual:ia"],
    ["atlas:propagacion", "atlas:vigia", "atlas:emergencia", "atlas:motor"],
]
assert [len(c) for c in CUAD_CLAVES] == [len(s[1]) for s in CUADERNO]
CUAD_PISTA = {"fauna": "Identifica a esta especie con Conocimiento silvestre (K) o rescátala.",
              "manual": "Usa esta herramienta en una partida para desbloquearla.",
              "guia": "Sigue jugando: se desbloquea con tu progreso.",
              "atlas": "Sigue jugando: se desbloquea con tu progreso."}
HAB_T = {pygame.K_g: "t_mang", pygame.K_t: "t_torre", pygame.K_h: "t_prot",
         pygame.K_z: "t_boti", pygame.K_x: "t_rastreo", pygame.K_q: "t_senal"}
HAB_FICHA = {pygame.K_g: "manguera", pygame.K_t: "torre", pygame.K_h: "termica",
             pygame.K_z: "botiquin", pygame.K_x: "rastreo", pygame.K_q: "senal"}
CUADERNO_RUTA = "output/cuaderno.json"
NOTIF_MS = 6000

def cargar_cuaderno():
    import json
    validas = {c for cs in CUAD_CLAVES for c in cs}
    try:
        with open(CUADERNO_RUTA, encoding="utf-8") as f:
            return set(json.load(f).get("abiertas", [])) & validas
    except Exception:
        return set()

def guardar_cuaderno():
    import json
    try:
        os.makedirs(os.path.dirname(CUADERNO_RUTA) or ".", exist_ok=True)
        with open(CUADERNO_RUTA, "w", encoding="utf-8") as f:
            json.dump({"abiertas": sorted(CUAD["abiertas"])}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

CUAD = {"abiertas": cargar_cuaderno(), "nuevas": set()}

def desbloquear(est, clave):
    """Desbloquea una ficha una sola vez: la guarda, la marca como nueva y encola la notificacion."""
    if clave in CUAD["abiertas"]:
        return
    pos = next(((s, i) for s, cs in enumerate(CUAD_CLAVES) for i, c in enumerate(cs) if c == clave), None)
    if pos is None:
        return
    CUAD["abiertas"].add(clave)
    CUAD["nuevas"].add(clave)
    guardar_cuaderno()
    sonar("ui_notif"); est.setdefault("notif", []).append(CUADERNO[pos[0]][1][pos[1]][0])

def dibujar_icono_cuaderno(pantalla, x, y, fnt):
    pygame.draw.rect(pantalla, (90, 60, 140), (x, y, 26, 30), border_radius=3); pygame.draw.line(pantalla, (150, 120, 200), (x + 10, y + 24), (x + 22, y + 24), 1); pygame.draw.line(pantalla, (150, 120, 200), (x + 10, y + 27), (x + 22, y + 27), 1)
    pygame.draw.rect(pantalla, (230, 170, 60), (x, y, 26, 30), 2, border_radius=3)
    pygame.draw.line(pantalla, (200, 180, 240), (x + 6, y + 3), (x + 6, y + 27), 2)
    t = fnt.render("N", True, (255, 255, 255))
    pantalla.blit(t, (x + 15 - t.get_width() // 2, y + 9))
    if CUAD["nuevas"]:
        pygame.draw.circle(pantalla, (255, 60, 60), (x + 26, y + 2), 8)
        c = fnt.render(str(len(CUAD["nuevas"])), True, (255, 255, 255))
        pantalla.blit(c, (x + 26 - c.get_width() // 2, y + 2 - c.get_height() // 2))

def dibujar_notif(pantalla, est, fnt, lado):
    """Franja discreta abajo a la derecha del mapa. No pausa la partida."""
    ahora = pygame.time.get_ticks()
    act = est.get("notif_act")
    if (act is None or ahora >= act[1]) and est.get("notif"):
        act = (est["notif"].pop(0), ahora + NOTIF_MS)
        est["notif_act"] = act
    if act is None or ahora >= act[1]:
        return
    txt = fnt.render("Cuaderno: nueva ficha - " + act[0], True, (255, 255, 255))
    w = txt.get_width() + 20
    x, y = lado[0] - w - 10, lado[1] - 40
    cuadro = pygame.Surface((w, 26), pygame.SRCALPHA)
    cuadro.fill((45, 25, 70, 225))
    pantalla.blit(cuadro, (x, y))
    pygame.draw.rect(pantalla, (255, 170, 60), (x, y, w, 26), 2)
    pantalla.blit(txt, (x + 10, y + 6))

def cuaderno(pantalla, fuente):
    """Cuaderno de Guardianes. Modal: izq/der cambia seccion, arriba/abajo la ficha.
    Esc, N o Retroceso cierran. En partida el llamador pone la pausa."""
    w, h = pantalla.get_size()
    fondo = pantalla.copy()
    f_tit = pygame.font.Font(None, 40)
    f_s = pygame.font.Font(None, 24)
    f_t = pygame.font.Font(None, 26)
    f_p = pygame.font.Font(None, 20)
    sec, ent = 0, 0
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_n, pygame.K_BACKSPACE):
                    sonar("ui_volver")
                    return None
                elif e.key == pygame.K_RIGHT:
                    sec = (sec + 1) % len(CUADERNO); ent = 0; sonar("ui_mover")
                elif e.key == pygame.K_LEFT:
                    sec = (sec - 1) % len(CUADERNO); ent = 0; sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    ent = (ent + 1) % len(CUADERNO[sec][1]); sonar("ui_mover")
                elif e.key == pygame.K_UP:
                    ent = (ent - 1) % len(CUADERNO[sec][1]); sonar("ui_mover")
        pantalla.blit(fondo, (0, 0))
        marco = pygame.Rect(30, 30, w - 60, h - 60)
        pygame.draw.rect(pantalla, (0, 0, 0), marco.move(4, 5), border_radius=8)
        pygame.draw.rect(pantalla, (22, 36, 28), marco, border_radius=8)
        pygame.draw.rect(pantalla, (255, 170, 60), marco, 3, border_radius=8)
        t = f_tit.render("CUADERNO DE GUARDIANES", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 68)))
        x = marco.x + 20
        for i, (nom, _) in enumerate(CUADERNO):
            s = f_s.render(nom, True, (255, 255, 255) if i == sec else (150, 170, 150))
            pantalla.blit(s, (x, 100))
            if i == sec:
                pygame.draw.line(pantalla, (255, 170, 60), (x, 122), (x + s.get_width(), 122), 2)
            x += s.get_width() + 24
        fichas = CUADERNO[sec][1]
        lista = pygame.Rect(marco.x + 20, 140, 190, marco.h - 140 - 60)
        for i, (nom, _) in enumerate(fichas):
            r = pygame.Rect(lista.x, lista.y + i * 36, lista.w, 30)
            pygame.draw.rect(pantalla, (255, 87, 34) if i == ent else (45, 66, 52), r, border_radius=6)
            _cl = CUAD_CLAVES[sec][i]
            _ab = _cl in CUAD["abiertas"]
            pantalla.blit(f_s.render(nom if _ab else "??? bloqueada", True, (255, 255, 255) if _ab else (150, 165, 150)), (r.x + 10, r.y + 6))
            if _cl in CUAD["nuevas"]:
                pygame.draw.circle(pantalla, (255, 60, 60), (r.right - 12, r.centery), 5)
        det = pygame.Rect(lista.right + 20, 140, marco.right - lista.right - 40, lista.h)
        pygame.draw.rect(pantalla, (14, 24, 18), det, border_radius=6)
        pygame.draw.rect(pantalla, (90, 120, 95), det, 1, border_radius=6)
        yy = det.y + 14
        _cl = CUAD_CLAVES[sec][ent]
        _ab = _cl in CUAD["abiertas"]
        if _ab:
            CUAD["nuevas"].discard(_cl)
        pantalla.blit(f_tit.render(fichas[ent][0] if _ab else "Ficha bloqueada", True, (240, 240, 240)), (det.x + 14, yy)); yy += 44
        for linea in (fichas[ent][1] if _ab else [CUAD_PISTA.get(_cl.split(":")[0], "")]):
            for parte in _ajustar(linea, f_t, det.w - 28):
                pantalla.blit(f_t.render(parte, True, (230, 230, 230)), (det.x + 14, yy)); yy += 28
            yy += 8
        pie = f_p.render("Izq/Der: sección   Arriba/Abajo: ficha   Esc o N: cerrar", True, (200, 190, 150))
        pantalla.blit(pie, pie.get_rect(center=(w // 2, marco.bottom - 24)))
        pygame.display.flip()
        reloj.tick(30)

def pantalla_maqueta(pantalla, titulo, lineas, etiqueta_txt="MAQUETA - EN CONSTRUCCIÓN"):
    """Pantalla de texto generica para menus en construccion.
    Devuelve None al volver, o 'salir' si se cierra la ventana."""
    w, h = pantalla.get_size()
    f_tit = pygame.font.Font(None, 46)
    f_t = pygame.font.Font(None, 28)
    f_p = pygame.font.Font(None, 22)
    fondo = fondo_marca(w, h)
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return None
        pantalla.blit(fondo, (0, 0))
        t = f_tit.render(titulo, True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 70)))
        etiqueta = f_p.render(etiqueta_txt, True, (255, 220, 100))
        pantalla.blit(etiqueta, etiqueta.get_rect(center=(w // 2, 108)))
        caja = pygame.Rect(40, 135, w - 80, h - 135 - 70)
        pygame.draw.rect(pantalla, (32, 44, 36), caja, border_radius=8)
        pygame.draw.rect(pantalla, (255, 170, 60), caja, 2, border_radius=8)
        yy = caja.y + 18
        for linea in lineas:
            if linea == "":
                yy += 14
                continue
            for parte in _ajustar(linea, f_t, caja.w - 40):
                pantalla.blit(f_t.render(parte, True, (235, 235, 235)), (caja.x + 20, yy))
                yy += 30
        v = f_p.render("Pulsa cualquier tecla para volver", True, (190, 190, 190))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 30)))
        pygame.display.flip()
        reloj.tick(30)

SALON_PAGINAS = [("Campaña", "campana"), ("Modo récord", "record"), ("Supervivencia", "supervivencia"),
                 ("Desafío", "desafio"), ("El corazón del incendio", "corazon")]

def lineas_records(modo):
    r = cargar_records()
    if modo == "corazon":
        claves = [("corazon", NIVEL_CORAZON["nombre"])]
    else:
        pref = "" if modo == "record" else modo + ":"
        claves = [(pref + n["id"], n["nombre"]) for n in NIVELES]
    out = []
    for k, nom in claves:
        v = r.get(k)
        if isinstance(v, dict):
            e = v.get("estrellas", 0)
            out.append(f"{nom}: {v.get('puntos', 0)} puntos, {e} estrella{'s' if e != 1 else ''}, ronda {v.get('ronda', 0)}")
    return out or ["Sin récords todavía.", "", "Cumple una misión en este modo y aparecerá aquí."]

def salon(pantalla, fuente):
    # Salón de Guardianes con una página por modo. None al volver, 'salir' si se cierra la ventana.
    w, h = pantalla.get_size()
    f_tit = pygame.font.Font(None, 46)
    f_t = pygame.font.Font(None, 28)
    f_p = pygame.font.Font(None, 22)
    fondo = fondo_marca(w, h)
    pag = 0
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                    return None
                elif e.key == pygame.K_LEFT:
                    pag = (pag - 1) % len(SALON_PAGINAS)
                elif e.key == pygame.K_RIGHT:
                    pag = (pag + 1) % len(SALON_PAGINAS)
        nombre, modo = SALON_PAGINAS[pag]
        lineas = lineas_salon() if modo == "campana" else lineas_records(modo)
        pantalla.blit(fondo, (0, 0))
        t = f_tit.render("Salón de Guardianes", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 60)))
        sub = f_t.render(f"<  {nombre}  ({pag + 1}/{len(SALON_PAGINAS)})  >", True, (255, 220, 100))
        pantalla.blit(sub, sub.get_rect(center=(w // 2, 105)))
        caja = pygame.Rect(40, 135, w - 80, h - 135 - 70)
        pygame.draw.rect(pantalla, (32, 44, 36), caja, border_radius=8)
        pygame.draw.rect(pantalla, (255, 170, 60), caja, 2, border_radius=8)
        yy = caja.y + 18
        for linea in lineas:
            if linea == "":
                yy += 14
                continue
            for parte in _ajustar(linea, f_t, caja.w - 40):
                pantalla.blit(f_t.render(parte, True, (235, 235, 235)), (caja.x + 20, yy))
                yy += 30
        v = f_p.render("Izquierda/Derecha: cambiar de modo  |  Esc: volver", True, (190, 190, 190))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 30)))
        pygame.display.flip()
        reloj.tick(30)

def tienda(pantalla, fuente):
    # Tienda de skins: devuelve None al volver, o 'salir' si se cierra la ventana.
    w, h = pantalla.get_size()
    f_tit = pygame.font.Font(None, 46)
    f_s = pygame.font.Font(None, 34)
    f_n = pygame.font.Font(None, 28)
    f_p = pygame.font.Font(None, 22)
    fondo = fondo_marca(w, h)
    pers = ("bombero", "vet")
    nombres = {"bombero": "Bombero", "vet": "Veterinaria"}
    col, sel, msg, msg_ok = 0, [0, 0], "", True
    d = cargar_eco()
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    sonar("ui_volver")
                    return None
                elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    col = 1 - col; sonar("ui_mover")
                elif e.key == pygame.K_UP:
                    sel[col] = (sel[col] - 1) % len(SKINS[pers[col]]); sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    sel[col] = (sel[col] + 1) % len(SKINS[pers[col]]); sonar("ui_mover")
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    p, i = pers[col], sel[col]
                    if skin_comprada(p, i, d):
                        msg_ok, msg = equipar_skin(p, i)
                    else:
                        msg_ok, msg = comprar_skin(p, i)
                    sonar("ui_tienda" if msg_ok else "ui_volver")
                    d = cargar_eco()
        pantalla.blit(fondo, (0, 0))
        t = f_tit.render("Tienda de personalización", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 50)))
        s = f_s.render(f"EcoMonedas: {d.get('saldo', 0)}", True, (255, 220, 100))
        pantalla.blit(s, s.get_rect(center=(w // 2, 92)))
        ancho = (w - 90) // 2
        for c, p in enumerate(pers):
            caja = pygame.Rect(30 + c * (ancho + 30), 125, ancho, 310)
            pygame.draw.rect(pantalla, (32, 44, 36), caja, border_radius=8)
            pygame.draw.rect(pantalla, (255, 170, 60) if c == col else (90, 90, 90), caja, 2, border_radius=8)
            pantalla.blit(f_n.render(nombres[p], True, (255, 255, 255)), (caja.x + 12, caja.y + 10))
            eq = skin_equipada(p, d)
            for i, (nom, precio, _) in enumerate(SKINS[p]):
                r = pygame.Rect(caja.x + 10, caja.y + 44 + i * 62, ancho - 130, 56)
                if i == sel[c]:
                    fcol = (255, 87, 34) if c == col else (110, 80, 60)
                else:
                    fcol = (50, 60, 52)
                pygame.draw.rect(pantalla, fcol, r, border_radius=6)
                pantalla.blit(f_n.render(nom, True, (255, 255, 255)), (r.x + 8, r.y + 6))
                if i == eq:
                    est_txt, est_col = "Equipada", (120, 230, 120)
                elif skin_comprada(p, i, d):
                    est_txt, est_col = "Comprada", (200, 200, 200)
                else:
                    est_txt = f"{precio} EcoMonedas"
                    est_col = (255, 90, 90) if d.get("saldo", 0) < precio else (255, 255, 255)
                pantalla.blit(f_p.render(est_txt, True, est_col), (r.x + 8, r.y + 33))
            _, spr = sprite_personaje(p, sel[c])
            big = pygame.transform.scale(spr, (spr.get_width() * 5, spr.get_height() * 5))
            pantalla.blit(big, big.get_rect(center=(caja.right - 60, caja.y + 150)))
            pantalla.blit(f_p.render("Vista previa", True, (190, 190, 190)),
                          f_p.render("Vista previa", True, (0, 0, 0)).get_rect(center=(caja.right - 60, caja.y + 60)))
        if msg:
            m = f_n.render(msg, True, (120, 230, 120) if msg_ok else (255, 90, 90))
            pantalla.blit(m, m.get_rect(center=(w // 2, 462)))
        ayuda = f_p.render("Flechas: elegir  |  Enter: comprar o equipar  |  Esc: volver", True, (190, 190, 190))
        pantalla.blit(ayuda, ayuda.get_rect(center=(w // 2, h - 30)))
        pygame.display.flip()
        reloj.tick(30)

CENTRO_PARAMS = [
    ("Ángulo del viento", [0, 45, 90, 135, 180, 225, 270, 315], 0, lambda v: f"{v} grados"),
    ("Fuerza del viento", [0.0, 0.3, 0.6, 0.9, 1.2], 2, lambda v: f"{v:.1f}"),
    ("Humedad ambiental", [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], 0,
     lambda v: f"{v:.1f}" + (" (neutra)" if v == 0 else "")),
    ("Simulaciones", [8, 16, 32, 64], 1, lambda v: str(v)),
    ("Tamaño del mapa", [96, 112, 128], 0, lambda v: f"{v} x {v}"),
    ("Fila de la barrera", [25, 50, 75], 1, lambda v: f"{v} % del alto"),
]
CENTRO_PASOS, CENTRO_SEMILLA = 50, 42

def centro_asegurar_vigia():
    """Recompila bin/vigia_hibrido en el contenedor si falta o es mas viejo que el motor."""
    b = "bin/vigia_hibrido"
    fuentes = ["src/common/fire_common.h", "src/common/fire_core.h", "src/parallel/vigia_hibrido.cpp"]
    if os.path.exists(b) and os.path.getmtime(b) >= max(os.path.getmtime(s) for s in fuentes):
        return
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c",
        "cd /home/mpiuser/proyecto && mpicxx -std=c++17 -O2 -fopenmp -I src/common "
        "-o bin/vigia_hibrido src/parallel/vigia_hibrido.cpp < /dev/null"],
        capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("no compila vigia_hibrido")

def centro_vigia(par, salida, acciones):
    """Una corrida del Vigia (MPI+OpenMP). Devuelve porcentajes y los pixeles del mapa de riesgo."""
    n = par["n"]
    cmd = (f"cd /home/mpiuser/proyecto && mpirun -np {VIGIA_PROCS} --hostfile infrastructure/hostfile "
           f"--map-by node ./bin/vigia_hibrido --mapa data/maps/map_{n}.bin --sims {par['sims']} "
           f"--viento-ang {par['ang']} --viento-fuerza {par['fuerza']} --humedad {par['hum']} "
           f"--pasos {CENTRO_PASOS} --semilla {CENTRO_SEMILLA} --hilos {VIGIA_HILOS} --salida {salida}")
    if acciones:
        cmd += f" --acciones {acciones}"
    cmd += " < /dev/null"
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c", cmd],
                       capture_output=True, text=True, timeout=150)
    if r.returncode != 0:
        raise RuntimeError("vigia fallo: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    m_alto = re.search(r"riesgo > 50%\s*:\s*(\d+) \(([\d.]+)%\)", r.stdout)
    m_afec = re.search(r"afectadas\s*:\s*(\d+) \(([\d.]+)%\)", r.stdout)
    m_med = re.search(r"quema\s*:\s*([\d.]+)", r.stdout)
    m_t = re.search(r" t=([0-9.]+)", r.stdout)
    if not (m_alto and m_afec and m_med and m_t):
        raise RuntimeError("no pude leer la salida del Vigia")
    datos = open(salida, "rb").read()
    if not datos.startswith(b"P5") or len(datos) < n * n:
        raise RuntimeError("PGM del Vigia inesperado")
    return {"alto": float(m_alto.group(2)), "afect": float(m_afec.group(2)),
            "media": float(m_med.group(1)), "t": float(m_t.group(1)), "pix": datos[-(n * n):]}

def centro_calcular(par):
    """Vigia sin y con cortafuegos (misma semilla). Devuelve (sin, con, fila_barrera)."""
    centro_asegurar_vigia()
    n = par["n"]
    os.makedirs("output/vigia", exist_ok=True)
    fila = n * par["fila"] // 100
    with open("output/vigia/centro_barrera.txt", "w") as f:
        for k in range(n):
            f.write(f"0 CORTAFUEGO {k} {fila}\n")
    sin = centro_vigia(par, "output/vigia/centro_sin.pgm", None)
    con = centro_vigia(par, "output/vigia/centro_con.pgm", "output/vigia/centro_barrera.txt")
    return sin, con, fila

def centro_superficie(pix, n, esc):
    sup = pygame.Surface((n, n))
    sup.fill((25, 40, 30))
    for i in range(n * n):
        v = pix[i]
        if v:
            sup.set_at((i % n, i // n), color_riesgo(v))
    return pygame.transform.scale(sup, (n * esc, n * esc))

def centro_analisis(pantalla, fuente):
    # Centro de Analisis y Prediccion: devuelve None al volver, o 'salir' si se cierra la ventana.
    w, h = pantalla.get_size()
    f_tit = pygame.font.Font(None, 46)
    f_n = pygame.font.Font(None, 30)
    f_p = pygame.font.Font(None, 22)
    fondo = fondo_marca(w, h)
    idx = [p[2] for p in CENTRO_PARAMS]
    sel, msg, res = 0, "", None
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type != pygame.KEYDOWN:
                continue
            if res is not None:
                if e.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    res = None
                    sonar("ui_volver")
                continue
            if e.key == pygame.K_ESCAPE:
                sonar("ui_volver")
                return None
            elif e.key == pygame.K_UP:
                sel = (sel - 1) % len(CENTRO_PARAMS); sonar("ui_mover")
            elif e.key == pygame.K_DOWN:
                sel = (sel + 1) % len(CENTRO_PARAMS); sonar("ui_mover")
            elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                d = 1 if e.key == pygame.K_RIGHT else -1
                idx[sel] = (idx[sel] + d) % len(CENTRO_PARAMS[sel][1])
                msg = ""
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                sonar("ui_aceptar")
                v = [CENTRO_PARAMS[k][1][idx[k]] for k in range(len(CENTRO_PARAMS))]
                par = {"ang": v[0], "fuerza": v[1], "hum": v[2], "sims": v[3], "n": v[4], "fila": v[5]}
                pantalla.blit(fondo, (0, 0))
                c = f_tit.render("El Vigía está calculando...", True, (255, 220, 100))
                pantalla.blit(c, c.get_rect(center=(w // 2, h // 2)))
                pygame.display.flip()
                try:
                    sin, con, fila = centro_calcular(par)
                    n = par["n"]
                    esc = max(1, min((w - 90) // 2 // n, (h - 290) // n))
                    res = {"sin": sin, "con": con, "fila": fila, "n": n, "esc": esc, "par": par,
                           "s_sin": centro_superficie(sin["pix"], n, esc),
                           "s_con": centro_superficie(con["pix"], n, esc)}
                    msg = ""
                except Exception as ex:
                    msg = "Error: " + str(ex)
        pantalla.blit(fondo, (0, 0))
        if res is None:
            t = f_tit.render("Centro de Análisis y Predicción", True, (255, 170, 60))
            pantalla.blit(t, t.get_rect(center=(w // 2, 46)))
            sub = f_p.render("Laboratorio del Vigía: Monte Carlo sin y con cortafuegos", True, (200, 200, 200))
            pantalla.blit(sub, sub.get_rect(center=(w // 2, 78)))
            ancho = min(560, w - 60)
            x0 = (w - ancho) // 2
            for k, (nom, vals, _, fmt) in enumerate(CENTRO_PARAMS):
                r = pygame.Rect(x0, 104 + k * 44, ancho, 38)
                pygame.draw.rect(pantalla, (255, 87, 34) if k == sel else (50, 60, 52), r, border_radius=6)
                pantalla.blit(f_n.render(nom, True, (255, 255, 255)), (r.x + 12, r.y + 8))
                tv = f_n.render("<  " + fmt(vals[idx[k]]) + "  >", True, (255, 255, 255))
                pantalla.blit(tv, (r.right - tv.get_width() - 12, r.y + 8))
            nota = f_p.render("La cantidad de vegetación depende del mapa elegido.", True, (190, 190, 190))
            pantalla.blit(nota, nota.get_rect(center=(w // 2, 104 + len(CENTRO_PARAMS) * 44 + 14)))
            if msg:
                m = f_n.render(msg, True, (255, 90, 90))
                pantalla.blit(m, m.get_rect(center=(w // 2, 104 + len(CENTRO_PARAMS) * 44 + 42)))
            av = f_p.render("Resultados experimentales y educativos, no son predicciones oficiales.", True, (255, 220, 100))
            pantalla.blit(av, av.get_rect(center=(w // 2, h - 54)))
            ay = f_p.render("Flechas: elegir y cambiar  |  Enter: calcular  |  Esc: volver", True, (190, 190, 190))
            pantalla.blit(ay, ay.get_rect(center=(w // 2, h - 30)))
        else:
            n, esc = res["n"], res["esc"]
            lado = n * esc
            xs = (w - (2 * lado + 30)) // 2
            t = f_tit.render("Resultados del Vigía", True, (255, 170, 60))
            pantalla.blit(t, t.get_rect(center=(w // 2, 36)))
            for k, (clave, nom) in enumerate((("sin", "Sin cortafuegos"), ("con", "Con cortafuegos"))):
                x = xs + k * (lado + 30)
                lb = f_n.render(nom, True, (255, 255, 255))
                pantalla.blit(lb, lb.get_rect(center=(x + lado // 2, 78)))
                pantalla.blit(res["s_" + clave], (x, 96))
                if clave == "con":
                    yb = 96 + res["fila"] * esc
                    pygame.draw.line(pantalla, (255, 255, 255), (x, yb), (x + lado, yb), 2)
                d = res[clave]
                tx = f_p.render(f"Riesgo alto (>50 %): {d['alto']:.1f} %   media: {d['media']:.3f}",
                                True, (255, 255, 255))
                pantalla.blit(tx, tx.get_rect(center=(x + lado // 2, 96 + lado + 14)))
            dif = res["con"]["alto"] - res["sin"]["alto"]
            tx = f_n.render(f"Con la barrera, el riesgo alto cambia {dif:+.1f} puntos porcentuales",
                            True, (120, 230, 120) if dif < 0 else (255, 200, 100))
            pantalla.blit(tx, tx.get_rect(center=(w // 2, 96 + lado + 42)))
            p = res["par"]
            info = (f"Viento {p['ang']} grados, fuerza {p['fuerza']:.1f}  |  humedad {p['hum']:.1f}  |  "
                    f"{p['sims']} sims, {CENTRO_PASOS} pasos  |  motor {res['sin']['t'] + res['con']['t']:.1f} s")
            pantalla.blit(f_p.render(info, True, (190, 190, 190)),
                          f_p.render(info, True, (0, 0, 0)).get_rect(center=(w // 2, 96 + lado + 66)))
            lg = f_p.render("Azul = riesgo bajo, rojo = riesgo alto. Experimental y educativo, no es una predicción oficial.",
                            True, (255, 220, 100))
            pantalla.blit(lg, lg.get_rect(center=(w // 2, h - 54)))
            ay = f_p.render("Enter o Esc: volver a los parámetros", True, (190, 190, 190))
            pantalla.blit(ay, ay.get_rect(center=(w // 2, h - 30)))
        pygame.display.flip()
        reloj.tick(30)

def dibujar_fondo_panel(pantalla, x, ancho, alto):
    """Fondo del panel lateral: degradado verde oscuro y borde de acento naranja (cacheado)."""
    cache = _SPRITES.setdefault("fondo_panel", {})
    s = cache.get((ancho, alto))
    if s is None:
        s = _degradado_tramado(ancho, alto, lambda t: (int(28 - 8 * t), int(40 - 12 * t), int(36 - 10 * t)))
        pygame.draw.rect(s, (255, 140, 40), (0, 0, 3, alto))
        pygame.draw.rect(s, (255, 205, 130), (0, 0, 1, alto))
        pygame.draw.rect(s, (150, 70, 20), (2, 0, 1, alto)); _salpicar(s, ancho, alto)
        cache[(ancho, alto)] = s
    pantalla.blit(s, (x, 0))


def _salpicar(s, ancho, alto):
    # motas oscuras y claras fijas para dar textura al panel
    rng = random.Random(7)
    for _ in range(ancho * alto // 70):
        px_, py_ = rng.randrange(4, ancho), rng.randrange(alto)
        c = s.get_at((px_, py_))
        d = -7 if rng.random() < 0.7 else 5
        s.set_at((px_, py_), (max(0, min(255, c[0] + d)), max(0, min(255, c[1] + d)), max(0, min(255, c[2] + d))))


def banner_emergencia(pantalla, est, fnt, x0, py):
    # caja con triangulo de alerta, nivel, cuenta regresiva e Ignis reducido
    niv = est["nivel"]
    col = {"inicial": (120, 255, 160), "avanzada": (255, 200, 80), "critica": (255, 80, 80)}[niv]
    fondo = {"inicial": (22, 66, 38), "avanzada": (84, 56, 10), "critica": (96, 18, 18)}[niv]
    r = pygame.Rect(x0 + 6, py - 4, PANEL_W - 18, 46)
    pygame.draw.rect(pantalla, fondo, r, border_radius=8)
    pygame.draw.rect(pantalla, col, r, 2, border_radius=8)
    tx, cy = r.x + 8, r.centery
    pygame.draw.polygon(pantalla, col, [(tx + 11, cy - 10), (tx, cy + 8), (tx + 22, cy + 8)])
    pygame.draw.line(pantalla, fondo, (tx + 11, cy - 4), (tx + 11, cy + 1), 2)
    pygame.draw.rect(pantalla, fondo, (tx + 10, cy + 3, 2, 2))
    pantalla.blit(fnt.render("EMERGENCIA", True, (255, 255, 255)), (r.x + 34, r.y + 7))
    t2 = niv.upper()
    if est["cuenta"] is not None:
        t2 += "  " + str(max(0, est["cuenta"]) * TICK_MS["critica"] // 1000) + " s"
    pantalla.blit(fnt.render(t2, True, col), (r.x + 34, r.y + 25))
    s = pygame.Surface((80, 90), pygame.SRCALPHA)
    dibujar_ignis(s, 40, 82, niv, pygame.time.get_ticks())
    pantalla.blit(pygame.transform.scale(s, (40, 45)), (r.right - 44, r.bottom - 48))


def marco_dorado(pantalla, rect, alpha=200):
    # caja oscura translucida con borde dorado y filete interior
    if alpha > 0:
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (14, 20, 16, alpha), s.get_rect(), border_radius=6)
        pantalla.blit(s, rect.topleft)
    pygame.draw.rect(pantalla, (230, 170, 60), rect, 2, border_radius=6)
    pygame.draw.rect(pantalla, (120, 80, 20), rect.inflate(-4, -4), 1, border_radius=4)


def marcador_alerta(pantalla, fnt, cx, base_y, t):
    # burbuja oscura con signo de exclamacion amarillo que sube y baja
    sube = 2 if (t // 250) % 2 else 0
    r = pygame.Rect(0, 0, 14, 18)
    r.midbottom = (cx, base_y - sube)
    pygame.draw.rect(pantalla, (40, 28, 10), r, border_radius=4)
    pygame.draw.rect(pantalla, (230, 170, 60), r, 1, border_radius=4)
    s = fnt.render("!", True, (255, 230, 60))
    pantalla.blit(s, s.get_rect(center=r.center))


def decorar_mapa(sup, est, cubiertas):
    # vallas y cartel alrededor del refugio, sobre celdas libres
    n, estado = est["n"], est["estado"]
    rx, ry, rw, rh = est["refugio"]

    def libre(cx, cy):
        return 0 <= cx < n and 0 <= cy < n and estado[cy * n + cx] in (0, 1, 3) and (cy * n + cx) not in cubiertas

    def poste(cx, cy):
        x0, y0 = cx * CELDA, cy * CELDA
        g = max(2, CELDA // 5)
        xp = x0 + CELDA // 2 - g // 2
        sup.fill((96, 66, 38), (xp, y0, g, CELDA))
        sup.fill((170, 125, 75), (xp, y0, 1, 1 if CELDA < 12 else CELDA))
        sup.fill((150, 108, 62), (x0, y0 + max(2, CELDA // 4), CELDA, max(1, CELDA // 8)))

    def tramo(cx, cy):
        x0, y0 = cx * CELDA, cy * CELDA
        alt = max(2, CELDA // 8)
        ys = (CELDA // 2 - 1,) if CELDA < 12 else (CELDA // 3 - 1, CELDA * 2 // 3 - 1)
        for yy in ys:
            sup.fill((150, 108, 62), (x0, y0 + yy, CELDA, alt))
            sup.fill((96, 66, 38), (x0, y0 + yy + alt, CELDA, 1))
        sup.fill((96, 66, 38), (x0, y0 + 1, 1, CELDA - 2))

    ent = ry + rh // 2
    for k in range(ry, ry + rh):
        if k not in (ent - 1, ent) and libre(rx - 1, k):
            poste(rx - 1, k)
        if k % 5 != 0 and libre(rx + rw, k):
            poste(rx + rw, k)
    for k in range(rx, rx + rw):
        if k % 4 != 3 and libre(k, ry + rh):
            tramo(k, ry + rh)
    if libre(rx - 2, ent - 1):
        x0, y0 = (rx - 2) * CELDA, (ent - 1) * CELDA
        ph = max(4, CELDA * 2 // 5)
        gp = max(1, CELDA // 8)
        sup.fill((96, 66, 38), (x0 + CELDA // 2 - gp // 2, y0 + ph, gp, CELDA - ph))
        sup.fill((40, 28, 16), (x0, y0 + 1, CELDA, ph))
        sup.fill((190, 150, 90), (x0 + 1, y0 + 2, CELDA - 2, ph - 2))


_ARBOLES = {}
_BORDES = {}


def franja_irregular(sup, x0, y0, lado, cols, sem, d0=0):
    # franja de pixeles con borde irregular sobre un lado de la celda (lado: 0 arriba, 1 abajo, 2 izquierda, 3 derecha)
    C = CELDA
    prob = (4, 2, 1)   # fila 0 siempre; fila 1 la mitad de los pixeles; fila 2 un cuarto
    for idx, col in enumerate(cols):
        d = d0 + idx
        for k in range(C):
            if idx > 0:
                hh = (k * 374761393 + d * 668265263 + sem * 1103515245 + 12345) & 0xFFFFFFFF
                hh = ((hh ^ (hh >> 13)) * 1274126177) & 0xFFFFFFFF
                if ((hh ^ (hh >> 16)) & 3) >= prob[idx]:
                    continue
            if lado == 0:
                p = (x0 + k, y0 + d)
            elif lado == 1:
                p = (x0 + k, y0 + C - 1 - d)
            elif lado == 2:
                p = (x0 + d, y0 + k)
            else:
                p = (x0 + C - 1 - d, y0 + k)
            sup.set_at(p, col)


def borde_sup(tipo, cols, lado, var, d0=0):
    # franja ya dibujada (cacheada por celda, tipo, lado y variante)
    clave = (CELDA, tipo, lado, var)
    s = _BORDES.get(clave)
    if s is None:
        s = pygame.Surface((CELDA, CELDA), pygame.SRCALPHA)
        franja_irregular(s, 0, 0, lado, cols, var * 5 + lado, d0)
        _BORDES[clave] = s
    return s


def suavizar_bordes(sup, estado, n):
    # a celda grande: bordes irregulares entre pasto, tierra, quemada y orilla del rio
    if CELDA < 12:
        return
    C = CELDA
    pasto = ((46, 118, 52), (60, 146, 62), (84, 170, 76))
    ceniza = ((40, 34, 30), (62, 52, 42), (84, 66, 48))
    espuma = ((214, 242, 255), (150, 214, 252))
    mojado_p = ((26, 72, 44), (34, 90, 50))
    mojado_t = ((150, 118, 80), (176, 142, 98))
    for i in range(n):
        for j in range(n):
            s = estado[i * n + j]
            if s == 2:
                continue
            x0, y0 = j * C, i * C
            for lado, (di, dj) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
                ii, jj = i + di, j + dj
                if not (0 <= ii < n and 0 <= jj < n):
                    continue
                t = estado[ii * n + jj]
                if t == s:
                    continue
                var = (((i * 73856093) ^ (j * 19349663) ^ (lado * 83492791)) >> 6) & 3
                if s in (0, 4) and t == 1:
                    sup.blit(borde_sup("pasto", pasto, lado, var), (x0, y0))
                elif s == 1 and t == 3:
                    sup.blit(borde_sup("ceniza", ceniza, lado, var), (x0, y0))
                elif s == 5:
                    sup.blit(borde_sup("espuma", espuma, lado, var, 1), (x0, y0))
                elif s == 1 and t == 5:
                    sup.blit(borde_sup("mojado_p", mojado_p, lado, var, 1), (x0, y0))
                elif s in (0, 3, 4) and t == 5:
                    sup.blit(borde_sup("mojado_t", mojado_t, lado, var, 1), (x0, y0))


def _dibujar_copa(spr, v, w):
    # copa redonda de 6 lobulos; el tronco se pinta antes y queda debajo de la copa
    C3 = CELDA * 3
    e = lambda a: int(round(a * C3 / 48.0))
    cx, cy = C3 // 2, e(21)
    pygame.draw.ellipse(spr, (14, 40, 22), (e(4), e(40), e(40), e(7)))
    spr.fill((84, 56, 32), (cx - e(3), e(33), e(6), e(12)))
    spr.fill((58, 38, 22), (cx + e(1), e(33), e(2), e(12)))
    spr.fill((120, 84, 50), (cx - e(3), e(33), max(1, e(1)), e(12)))
    mid = (30 + 4 * v, 92 + 8 * v, 44 + 3 * v)
    luz = (44 + 5 * v, 118 + 8 * v, 54 + 3 * v)
    sombra = (20, 68 + 4 * v, 34)
    sg = -1 if w else 1
    for dx, dy, r in ((0, -9, 10), (-10, -3, 10), (10, -3, 10), (-10, 6, 9), (10, 6, 9), (0, 4, 12)):
        px, py, rr = cx + sg * e(dx), cy + e(dy), e(r)
        pygame.draw.circle(spr, (16, 48, 28), (px, py), rr + 1)
        pygame.draw.circle(spr, mid, (px, py), rr)
        pygame.draw.circle(spr, sombra, (px, py), rr, 2, draw_bottom_right=True)
        pygame.draw.circle(spr, luz, (px - e(2), py - e(3)), max(2, rr - e(4)))
        pygame.draw.circle(spr, (92, 172, 80), (px - e(3), py - e(4)), max(1, rr // 3))


def _dibujar_pino(spr, v, w):
    # pino conico de 3 pisos
    C3 = CELDA * 3
    e = lambda a: int(round(a * C3 / 48.0))
    cx = C3 // 2
    pygame.draw.ellipse(spr, (14, 40, 22), (e(6), e(41), e(36), e(6)))
    spr.fill((84, 56, 32), (cx - e(2), e(38), e(4), e(8)))
    spr.fill((58, 38, 22), (cx + e(1), e(38), max(1, e(1)), e(8)))
    oscuro = (10, 42, 32)
    mid = (22 + 3 * v, 84 + 5 * v, 60 + 3 * v)
    luz = (34 + 4 * v, 112 + 6 * v, 78 + 3 * v)
    umbra = (16, 62 + 3 * v, 46)
    for ap, base, hw in ((19, 42, 19), (10, 31, 15), (2, 20, 10)):   # de abajo hacia arriba
        a, b, m = e(ap), e(base), e(hw)
        pygame.draw.polygon(spr, oscuro, [(cx, a - 1), (cx + m + 1, b + 1), (cx - m - 1, b + 1)])
        pygame.draw.polygon(spr, mid, [(cx, a), (cx + m, b), (cx - m, b)])
        pygame.draw.polygon(spr, umbra if w else luz, [(cx, a), (cx, b), (cx - m, b)])
        pygame.draw.polygon(spr, luz if w else umbra, [(cx, a), (cx + m, b), (cx, b)])
        pygame.draw.line(spr, (80, 158, 108), (cx - 1, a + 2), (cx - m + e(3), b - 2))


def arbol3(sup, x0, y0, v):
    # celda < 12: dibujo anterior; si no, copa redonda o pino (sprites cacheados, elegidos por posicion)
    if CELDA < 12:
        return arbol3_viejo(sup, x0, y0, v)
    gi, gj = y0 // CELDA // 3, x0 // CELDA // 3
    h = (gi * 5 + gj * 7 + gi * gj) % 10
    tipo = "pino" if h < 4 else "copa"
    clave = (CELDA, tipo, v, h % 2)
    spr = _ARBOLES.get(clave)
    if spr is None:
        spr = pygame.Surface((CELDA * 3, CELDA * 3), pygame.SRCALPHA)
        (_dibujar_pino if tipo == "pino" else _dibujar_copa)(spr, v, h % 2)
        _ARBOLES[clave] = spr
    sup.blit(spr, (x0, y0))


def arbol3_viejo(sup, x0, y0, v):
    # (celda < 12) arbol de 3x3 celdas: sombra, tronco y copa en 3 tonos con brillo
    C3 = CELDA * 3
    cx = x0 + C3 // 2
    r = C3 // 2 - 2
    cy = y0 + C3 // 2 - 2
    pygame.draw.ellipse(sup, (14, 40, 22), (x0 + 1, y0 + C3 - 5, C3 - 2, 5))
    sup.fill((90, 60, 35), (cx - 1, y0 + C3 - 6, 3, 5))
    sup.fill((60, 40, 24), (cx + 1, y0 + C3 - 6, 1, 5))
    pygame.draw.circle(sup, (18, 54, 30), (cx, cy), r + 1)
    pygame.draw.circle(sup, (26 + 4 * v, 84 + 8 * v, 40 + 4 * v), (cx, cy), r)
    pygame.draw.circle(sup, (36 + 5 * v, 112 + 10 * v, 52), (cx - 1, cy - 1), max(2, r * 2 // 3))
    pygame.draw.circle(sup, (70 + 6 * v, 156 + 8 * v, 72), (cx - 2, cy - 3), max(1, r // 3))
    sup.set_at((cx - 3, cy - 4), (150, 215, 120))
    sup.set_at((cx + 2, cy + 2), (16, 48, 26))
    sup.set_at((cx - 2, cy + 3), (16, 48, 26))
    if CELDA >= 12:   # racimos de hojas y tronco visible a celda grande
        for k in range(9):
            ox = ((k * 37 + v * 11) % (2 * r - 8)) - r + 4
            oy = ((k * 53 + v * 7) % (2 * r - 10)) - r + 2
            if ox * ox + oy * oy < (r - 4) ** 2:
                col_k = (70 + 6 * v, 156 + 8 * v, 72) if k % 2 else (16, 48, 26)
                pygame.draw.circle(sup, col_k, (cx + ox, cy + oy), max(2, r // 6))
        sup.fill((90, 60, 35), (cx - 2, y0 + C3 - 9, 4, 9))
        sup.fill((60, 40, 24), (cx + 1, y0 + C3 - 9, 1, 9))
        sup.fill((120, 84, 50), (cx - 2, y0 + C3 - 9, 1, 9))


def color_boton(activo):
    # relleno del boton: naranja claro si esta seleccionado
    return (255, 120, 60) if activo else (38, 56, 44)


def rect_boton(r, activo):
    # boton seleccionado: mas ancho y 2 px mas arriba
    if not activo:
        return r
    return r.inflate(14, 0).move(0, -2)


def sonar(nombre):
    """Reproduce un sonido de interfaz por el canal de efectos (no falla si no hay audio)."""
    try:
        s = AJ["snd"].get(nombre)
        if s:
            s.play()
    except Exception:
        pass


LLAMA_LOGO = ["......R.....",
               ".....RR.....",
               ".....ROR....",
               "....RROOR...",
               "...RROOOR.R.",
               "..RROOYOORR.",
               "..ROOYYYOOR.",
               ".RROOYYYOOR.",
               ".ROOYYYYYOOR",
               ".ROOYYYYYOOR",
               "..ROOYYYOOR.",
               "...RROOORR.."]

def llamas_logo(pantalla, f_tit, w, y):
    """Dos llamas pixel a los lados del titulo, con vaiven suave."""
    import math
    pal = {"R": (200, 40, 20), "O": (255, 130, 30), "Y": (255, 230, 90)}
    s = sprite_generico("llama_logo", LLAMA_LOGO, pal, 3)
    mitad = f_tit.size("GUARDIANES DEL CHACO")[0] // 2
    dy = int(2 * math.sin(pygame.time.get_ticks() / 250))
    for lado in (-1, 1):
        cx = w // 2 + lado * (mitad + 34)
        pantalla.blit(s, (cx - s.get_width() // 2, y - s.get_height() // 2 + dy))

def cortina(pantalla, dur=300):
    """Cortina pixelada: bloques de 16x16 que se oscurecen en orden aleatorio (dur ms)."""
    w, h = pantalla.get_size()
    cols, filas = (w + 15) // 16, (h + 15) // 16
    celdas = [(i % cols, i // cols) for i in range(cols * filas)]
    random.Random(5).shuffle(celdas)
    t0 = pygame.time.get_ticks()
    reloj = pygame.time.Clock()
    hecho = 0
    while True:
        f = min(1.0, (pygame.time.get_ticks() - t0) / dur)
        hasta = int(len(celdas) * f)
        for cx, cy in celdas[hecho:hasta]:
            pantalla.fill((10, 14, 12), (cx * 16, cy * 16, 16, 16))
        hecho = hasta
        pygame.display.flip()
        pygame.event.pump()
        if f >= 1.0:
            break
        reloj.tick(60)

def menu_principal(pantalla, fuente):
    # Pantalla de titulo. Devuelve True para jugar, False para salir.
    f_tit = pygame.font.Font(None, 72)
    f_sub = pygame.font.Font(None, 30)
    f_op = pygame.font.Font(None, 32)
    opciones = ["Jugar", "Campaña", "Modos especiales", "Centro de Análisis", "Cuaderno de Guardianes",
                "Salón de Guardianes", "Tienda", "Próximamente", "Cómo jugar", "Salir"]
    ayuda_txt = [
        "Eres el bombero forestal de los Bosques de Yacuiba.",
        "Clic izquierdo: cortafuegos (frena el avance del fuego).",
        "Clic derecho: mochila de agua (apaga una celda en llamas).",
        "El fuego avanza solo. P: pausa  |  Enter: adelantar el fuego (depuración).",
        "Retroceso: deshacer la última acción  |  R: reiniciar.",
        "Bombero: flechas.  Veterinaria: W A S D.  El modo se elige al pulsar Jugar.",
        "Veterinaria: E recoge o suelta un animal. Llévalos al refugio (zona verde).",
        "Meta: apagar el incendio y conservar el mayor bosque posible.",
        "M: silenciar la música.  |  O: ajustes de audio  |  N: Cuaderno (pausa).",
        "Bombero: G manguera, T torre.  Veterinaria: Z botiquín, X rastreo, Q señal de auxilio.",
        "Menú: Modos especiales, Tienda (skins con EcoMonedas) y dificultad de la IA en solitario.",
        "Pulsa cualquier tecla para volver.",
    ]
    w, h = pantalla.get_size()
    fondo = pygame.Surface((w, h))
    for y in range(h):
        t = y / h
        pygame.draw.line(fondo, (int(15 + 90 * t), int(40 - 10 * t), int(25 - 10 * t)), (0, y), (w, y))
    paso = min(52, (h - 200) // len(opciones))
    rects = [pygame.Rect(w // 2 - 150, 140 + i * paso, 300, paso - 8) for i in range(len(opciones))]
    reloj = pygame.time.Clock()
    sel = 0
    ayuda = False
    _pres = [None, 0]
    luci = [[random.uniform(0, w), random.uniform(0, h), random.uniform(0, 6.28), random.uniform(0.2, 0.8)]
            for _ in range(40)]

    def centrado(texto, fnt, col, y):
        s = fnt.render(texto, True, col)
        pantalla.blit(s, s.get_rect(center=(w // 2, y)))

    while True:
        accion = None
        if _pres[0] is not None and pygame.time.get_ticks() - _pres[1] >= 100:
            accion = _pres[0]; _pres[0] = None
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if ayuda:
                if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    ayuda = False
                continue
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    return False
                elif e.key == pygame.K_LEFT:
                    cambiar_volumen(-0.1)
                elif e.key == pygame.K_RIGHT:
                    cambiar_volumen(0.1)
                elif e.key == pygame.K_UP:
                    sel = (sel - 1) % len(opciones); sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(opciones); sonar("ui_mover")
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    accion = sel
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        if sel != i:
                            sonar("ui_mover")
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sel = i
                        _pres[0] = i; _pres[1] = pygame.time.get_ticks()
        if accion is not None:
            sonar({"Jugar": "ui_jugar", "Campaña": "ui_jugar", "Tienda": "ui_tienda",
                   "Salir": "ui_salir"}.get(opciones[accion], "ui_aceptar"))
        if accion is not None and opciones[accion] in ("Jugar", "Campaña"):
            m = seleccionar_modo(pantalla, fuente)
            if m == "salir":
                return False
            if m is not None:
                k = seleccionar_nivel(pantalla, fuente)
                if k == "salir":
                    return False
                if k is not None:
                    NIVEL_SEL["i"] = k
                    MODO["ia"] = None if m == "dos" else m
                    MODO_ESP["id"] = None
                    return True
        if accion is not None:
            op = opciones[accion]
            if op == "Cómo jugar":
                ayuda = True
            elif op == "Salir":
                return False
            elif op == "Modos especiales":
                me = seleccionar_modo_especial(pantalla, fuente)
                if me == "salir":
                    return False
                if me is not None:
                    m = seleccionar_modo(pantalla, fuente)
                    if m == "salir":
                        return False
                    if m is not None and me == "corazon":
                        NIVEL_SEL["i"] = 0
                        MODO["ia"] = None if m == "dos" else m
                        MODO_ESP["id"] = me
                        return True
                    if m is not None:
                        k = seleccionar_nivel(pantalla, fuente)
                        if k == "salir":
                            return False
                        if k is not None:
                            NIVEL_SEL["i"] = k
                            MODO["ia"] = None if m == "dos" else m
                            MODO_ESP["id"] = me
                            return True
            elif op == "Salón de Guardianes":
                if salon(pantalla, fuente) == "salir":
                    return False
            elif op == "Cuaderno de Guardianes":
                if cuaderno(pantalla, fuente) == "salir":
                    return False
            elif op == "Tienda":
                if tienda(pantalla, fuente) == "salir":
                    return False
            elif op == "Centro de Análisis":
                if centro_analisis(pantalla, fuente) == "salir":
                    return False
            elif op in MAQUETAS:
                titulo_m, lineas_m = MAQUETAS[op]
                if pantalla_maqueta(pantalla, titulo_m, lineas_m) == "salir":
                    return False

        pantalla.blit(fondo, (0, 0))
        import math
        _tm = pygame.time.get_ticks() / 1000.0
        for _l in luci:
            _l[1] -= _l[3]
            if _l[1] < -5:
                _l[1] = h + 5
                _l[0] = random.uniform(0, w)
            _a = 0.5 + 0.5 * math.sin(_tm * 2 + _l[2])
            pygame.draw.circle(pantalla, (255, int(150 + 80 * _a), int(40 + 40 * _a)),
                               (int(_l[0] + math.sin(_tm * 0.8 + _l[2]) * 14), int(_l[1])), 2)
        centrado("GUARDIANES DEL CHACO", f_tit, (90, 30, 10), 63)
        centrado("GUARDIANES DEL CHACO", f_tit, (255, 170, 60), 60); llamas_logo(pantalla, f_tit, w, 60)
        centrado("Gran Chaco boliviano - Tarija", f_sub, (230, 230, 230), 105)
        if ayuda:
            for k, linea in enumerate(ayuda_txt):
                centrado(linea, fuente, (240, 240, 240), 160 + k * 34)
        else:
            for i, r in enumerate(rects):
                rr = rect_boton(r, i == sel).move(0, 4 if i == _pres[0] else 0)
                pygame.draw.rect(pantalla, (0, 0, 0), rr.move(0, 3), border_radius=8)
                pygame.draw.rect(pantalla, color_boton(i == sel), rr, border_radius=8)
                pygame.draw.rect(pantalla, (255, 200, 120) if i == sel else (90, 120, 95), rr, 2, border_radius=8)
                centrado(opciones[i], f_op, (140, 140, 140) if "bloqueada" in opciones[i] else (255, 255, 255), r.centery + (2 if i == _pres[0] else 0))
            centrado("Flechas + Enter, o usa el ratón", fuente, (200, 200, 200), h - 40)
        dibujar_barra_volumen(pantalla, 20, h - 46)
        pygame.display.flip()
        reloj.tick(30)


def color_riesgo(v):
    """0..255 -> azul (bajo) a amarillo a rojo (alto)."""
    t = v / 255.0
    if t < 0.5:
        u = t / 0.5
        return (int(60 + 195 * u), int(90 + 165 * u), int(220 - 220 * u))
    u = (t - 0.5) / 0.5
    return (255, int(255 - 255 * u), 0)

def calcular_vigia(n):
    """Lanza el Vigia (MPI+OpenMP) sobre output/juego_mapa.bin y devuelve
    (superficie con alpha del mapa de riesgo, lineas de informacion)."""
    if not os.path.exists("bin/vigia_hibrido"):
        r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c",
            "cd /home/mpiuser/proyecto && mpicxx -std=c++17 -O2 -fopenmp -I src/common "
            "-o bin/vigia_hibrido src/parallel/vigia_hibrido.cpp < /dev/null"],
            capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError("no compila vigia_hibrido")
    cmd = (f"cd /home/mpiuser/proyecto && mpirun -np {VIGIA_PROCS} --hostfile infrastructure/hostfile "
           f"--map-by node ./bin/vigia_hibrido --mapa {MAPA_JUEGO} --sims {VIGIA_SIMS} {args_viento(nivel_actual())} "
           f"--pasos {VIGIA_PASOS} --hilos {VIGIA_HILOS} --salida {SALIDA_VIGIA} < /dev/null")
    t0 = perf_counter()
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c", cmd],
                       capture_output=True, text=True, timeout=90)
    total = perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError("vigia fallo: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    t_motor = None
    for linea in r.stdout.splitlines():
        if linea.startswith("RESULT"):
            m = re.search(r" t=([0-9.]+)", linea)
            if m:
                t_motor = float(m.group(1))
    if t_motor is None:
        raise RuntimeError("el Vigia no imprimio RESULT")
    datos = open(SALIDA_VIGIA, "rb").read()
    cab = datos[:40].split()
    w, h = int(cab[1]), int(cab[2])
    if cab[0] != b"P5" or w != n or h != n or len(datos) < n * n:
        raise RuntimeError("PGM del Vigia inesperado")
    pix = datos[-(n * n):]
    chica = pygame.Surface((n, n), pygame.SRCALPHA)
    for i in range(n * n):
        v = pix[i]
        if v:
            chica.set_at((i % n, i // n), (*color_riesgo(v), 150))
    sup = pygame.transform.scale(chica, (n * CELDA, n * CELDA))
    info = [f"{VIGIA_SIMS} sims, {VIGIA_PASOS} pasos",
            f"{VIGIA_PROCS} procs x {VIGIA_HILOS} hilos",
            f"Motor: {t_motor:.2f} s",
            f"Total: {total:.2f} s"]
    return sup, info


VIDA_MAX = 100
DANO_LLAMAS = 5          # por golpe, cada 600 ms sobre una celda en llamas
CURA_REFUGIO = 2         # por golpe, dentro del refugio
META_SALVOS, META_BOSQUE = 3, 40
CUENTA_RONDAS = 15                           # ticks de la cuenta regresiva (~30 s en critico)
TICK_MS = {"inicial": 3000, "avanzada": 2500, "critica": 2000}   # ritmo del fuego en tiempo real

TANQUE_BASE = 6              # cargas de agua del bombero
TANQUE_DESAFIO = 3           # Desafío: tanque reducido
LIMITE_DESAFIO = 40          # Desafío: rondas máximas para cumplir la misión

def tanque_max():
    return TANQUE_DESAFIO if MODO_ESP["id"] == "desafio" else TANQUE_BASE
CD_CORTAFUEGO_MS = 4000     # recuperacion entre cortafuegos
RECARGA_MS = 1000           # 1 carga por segundo junto al rio
RIO_DIST = 2                # celdas de distancia al agua para recargar

CD_APOYO_MS = 15000        # recuperacion del apoyo de la veterinaria

def estado_apoyo(est):
    resto = CD_APOYO_MS - (pygame.time.get_ticks() - est["t_apoyo"])
    return "listo" if resto <= 0 else f"{resto / 1000:.0f}s"

def apoyo(est, ahora, avisar=True):
    """La veterinaria, a 2 celdas o menos del bombero, le da +2 de agua y +15 de vida."""
    if ahora - est["t_apoyo"] < CD_APOYO_MS:
        if avisar:
            est["msg"] = "Apoyo en recuperación"
        return False
    if (est["vx"] - est["bx"]) ** 2 + (est["vy"] - est["by"]) ** 2 > 4:
        if avisar:
            est["msg"] = "Acércate al bombero para apoyarlo"
        return False
    est["agua"] = min(tanque_max(), est["agua"] + 2)
    est["vida"]["b"] = min(VIDA_MAX, est["vida"]["b"] + 15)
    est["t_apoyo"] = ahora
    desbloquear(est, "manual:apoyo")
    est["msg"] = "Apoyo: +2 agua y +15 vida al bombero"; decir(est, "v", "Toma agua. De nada, por cierto.", "importante")
    return True

def estado_cortafuego(est):
    resto = CD_CORTAFUEGO_MS - (pygame.time.get_ticks() - est["t_cf"])
    return "listo" if resto <= 0 else f"{resto / 1000:.1f}s"

DLG_DURACION_MS = 3500      # tiempo que dura un globo en pantalla
DLG_ESPERA_MS = 8000        # espera minima entre globos
DLG_REPITE_CRIT_MS = 20000  # un aviso critico no se repite antes de esto
DLG_COLA_MAX = 3
# Tipos de comentario que permite cada modo de dialogos del nivel
DLG_POLITICA = {"facil": {"critico", "importante", "educativo", "ocasional"},
                "medio": {"critico", "importante"},
                "dificil": {"critico"},
                "silencio": {"critico"}}

for _k, _v in {"facil": {"inicio", "final"}, "medio": {"inicio", "final"},
               "dificil": {"final"}, "silencio": {"inicio"}}.items():
    DLG_POLITICA[_k] |= _v

# Texto de inicio por nivel: (bombero, veterinaria o None). Se editan aqui.
INICIO_TXT = {
    "yacuiba": ("¡Buenos días, Yacuiba! Hoy el fuego se va a arrepentir de haber madrugado.",
                "Concéntrate. Hay animales que dependen de que no te pongas a bromear."),
    "aguarague": ("Serranía y viento en contra. Me gustan los retos.",
                  "Ojo con las laderas: el fuego sube más rápido de lo que crees."),
    "tarija": ("Mucho mapa y muchos focos. Esto ya no es entrenamiento.",
               "Prioricemos el refugio y repartámonos el terreno."),
    "gran_incendio": ("Todos a lo suyo. Hoy no hay bromas.", None),
    "yacuiba2": ("Otro día en Yacuiba y el monte sigue seco. Menos charla, más mochila.",
                 "Revisa el viento antes de cortar nada. Yo me ocupo de los animales."),
    "yacuiba3": ("Un río cerca y aun así el fuego avanza. Qué descortés.",
                 "Más focos que la última vez. Ve por los más cercanos al refugio."),
    "aguarague2": ("Laderas otra vez. El fuego sube y yo también.",
                   "El viento cambió de lado. No te confíes con los cortafuegos."),
    "aguarague3": ("Una quebrada, viento fuerte y poco margen. Me encanta.",
                   "Tenemos más animales que tiempo. Prioriza."),
    "tarija2": ("Valle abierto y focos por todos lados. Hoy se trabaja en serio.",
                "Repartámonos el mapa. Yo voy por los animales del fondo."),
    "tarija3": ("Cinco focos y viento fuerte. Sin bromas, de verdad.",
                "Refugio primero. Después lo demás."),
    "corazon": ("Nueve focos a la vez. Este es el corazón del incendio.",
                "Refugio primero. Después, los focos más grandes."),
}

def dialogos_inicio(est):
    b, v = INICIO_TXT[nivel_actual()["id"]]
    return   # el inicio lo presenta cuadro_grande (intro_nivel)
    decir(est, "b", b, "inicio")
    if v:
        decir(est, "v", v, "inicio")

def nuevo_dialogo():
    return dict(cola=[], actual=None, t_ini=0, t_ultimo=-99999, crit={})

def decir(est, quien, texto, tipo="ocasional", clave=None):
    """Encola un comentario. quien: 'b' (bombero) o 'v' (veterinaria).
    tipo: 'critico', 'importante', 'educativo' u 'ocasional'. Devuelve True si se encolo."""
    d = est["dlg"]
    if tipo not in DLG_POLITICA[nivel_actual()["dialogos"]]:
        return False
    ahora = pygame.time.get_ticks()
    clave = clave or texto
    if tipo == "critico":
        if ahora - d["crit"].get(clave, -99999) < DLG_REPITE_CRIT_MS:
            return False
        d["crit"][clave] = ahora
    else:
        if tipo in ("ocasional", "educativo") and (d["actual"] or d["cola"]):
            return False
        if len(d["cola"]) >= DLG_COLA_MAX:
            return False
    if any(c["texto"] == texto for c in d["cola"]):
        return False
    item = dict(quien=quien, texto=texto, tipo=tipo)
    if tipo == "critico":
        d["cola"].insert(0, item)
    else:
        d["cola"].append(item)
    return True

def _ajustar(texto, fnt, ancho):
    lineas, act = [], ""
    for p in texto.split():
        prueba = (act + " " + p).strip()
        if fnt.size(prueba)[0] <= ancho or not act:
            act = prueba
        else:
            lineas.append(act)
            act = p
    if act:
        lineas.append(act)
    return lineas

def dibujar_globo(pantalla, est, fnt, cam=(0, 0), vista=None):
    """Avanza la cola y dibuja el globo actual cerca del personaje que habla."""
    d = est["dlg"]
    ahora = pygame.time.get_ticks()
    if d["actual"] and ahora - d["t_ini"] >= DLG_DURACION_MS:
        d["actual"] = None
        d["t_ultimo"] = ahora
    if d["actual"] is None and d["cola"]:
        cab = d["cola"][0]
        if cab["tipo"] == "critico" or ahora - d["t_ultimo"] >= DLG_ESPERA_MS:
            d["actual"] = d["cola"].pop(0)
            d["t_ini"] = ahora
    a = d["actual"]
    if not a:
        return
    es_b = a["quien"] == "b"
    nombre = "Bombero" if es_b else "Veterinaria"
    col_n = (255, 170, 60) if es_b else (120, 220, 255)
    lineas = _ajustar(a["texto"], fnt, 230)
    sn = fnt.render(nombre, True, col_n)
    lh = fnt.get_linesize()
    ancho = max([sn.get_width()] + [fnt.size(l)[0] for l in lineas]) + 20
    alto = 12 + lh * (len(lineas) + 1)
    cx, cy = (est["bx"], est["by"]) if es_b else (est["vx"], est["vy"])
    px_, py_ = camara_a_pantalla(cx * CELDA + CELDA // 2, cy * CELDA, cam)
    limx, limy = vista if vista else (est["n"] * CELDA, est["n"] * CELDA)
    x = max(4, min(limx - ancho - 4, px_ - ancho // 2))
    y = py_ - alto - 14
    abajo = y < 4
    if abajo:
        y = py_ + CELDA + 14
    y = max(4, min(y, limy - alto - 4))
    rect = pygame.Rect(x, y, ancho, alto)
    pygame.draw.rect(pantalla, (45, 25, 70), rect, border_radius=6)
    pygame.draw.rect(pantalla, (200, 180, 240), rect, 2, border_radius=6)
    pygame.draw.rect(pantalla, (120, 95, 170), rect.inflate(-8, -8), 1, border_radius=4)
    tx = max(x + 10, min(x + ancho - 10, px_))
    if abajo:
        pts = [(tx - 6, y), (tx + 6, y), (tx, y - 10)]
    else:
        pts = [(tx - 6, y + alto), (tx + 6, y + alto), (tx, y + alto + 10)]
    pygame.draw.polygon(pantalla, (45, 25, 70), pts)
    pygame.draw.lines(pantalla, (200, 180, 240), False, pts, 2)
    pantalla.blit(sn, (x + 10, y + 6))
    for k, l in enumerate(lineas):
        pantalla.blit(fnt.render(l, True, (240, 240, 240)), (x + 10, y + 6 + lh * (k + 1)))

RET_BASE = {
    "b": ["................",
          "....RRRRRRRR....",
          "...RRRRRRRRRR...",
          "..RRRRRUURRRRR..",
          "..UUUUUUUUUUUU..",
          "...SSSSSSSSSS...",
          "...SSSSSSSSSS...",
          "...SSSSSSSSSS...",
          "...SSSSSSSSSS...",
          "...SSSSSSSSSS...",
          "...SSSSSSSSSS...",
          "...SSSSSSSSSS...",
          "....SSSSSSSS....",
          "..RRRRSSSSRRRR..",
          ".RRRRRRRRRRRRRR.",
          ".RRUURRRRRRUURR."],
    "v": ["................",
          "....HHHHHHHH....",
          "...HHHHHHHHHH...",
          "..HHHHHHHHHHHH..",
          "..HHGGGGGGGGHH..",
          "..HSSSSSSSSSSH..",
          "..HSSSSSSSSSSH..",
          "..HSSSSSSSSSSH..",
          "..HSSSSSSSSSSH..",
          "..HSSSSSSSSSSH..",
          "..HSSSSSSSSSSH..",
          "...HSSSSSSSSH...",
          "....SSSSSSSS....",
          "...GGWWSSWWGG...",
          ".GGGWWWWWWWWGGG.",
          ".GGGWWWWWWWWGGG."],
}
# Rasgos de cada expresion: (fila, columna) que se pintan de oscuro sobre la cara base
RET_EXPR = {
    "normal": [(6, 4), (6, 5), (6, 10), (6, 11), (8, 5), (9, 5), (8, 10), (9, 10),
               (11, 6), (11, 7), (11, 8), (11, 9)],
    "alegre": [(8, 4), (8, 5), (8, 6), (8, 9), (8, 10), (8, 11), (9, 4), (9, 6), (9, 9), (9, 11),
               (11, 5), (11, 10), (12, 6), (12, 7), (12, 8), (12, 9)],
    "preocupada": [(7, 4), (6, 5), (6, 6), (7, 11), (6, 10), (6, 9), (8, 5), (9, 5), (8, 10), (9, 10),
                   (11, 6), (11, 7), (11, 8), (11, 9), (12, 5), (12, 10)],
}

def retrato(quien, expr="normal"):
    """Retrato pixel 16x16 (x6 = 96 px) con la paleta y la skin equipada del personaje."""
    pers = "bombero" if quien == "b" else "vet"
    i = SKIN_ACTUAL.get(pers, 0)
    if expr not in RET_EXPR:
        expr = "normal"
    pal = dict(PALETA_BOMBERO if quien == "b" else PALETA_VET)
    pal["H"] = (90, 55, 35)
    try:
        pal.update(SKINS[pers][i][2])
    except Exception:
        pass
    filas = [list(f) for f in RET_BASE["b" if quien == "b" else "v"]]
    for fila, col in RET_EXPR[expr]:
        filas[fila][col] = "K"
    return sprite_generico(f"ret:{pers}:{i}:{expr}", ["".join(f) for f in filas], pal, 6)

def expr_final(est):
    """Expresion de los retratos en el dialogo final segun el resultado."""
    if est.get("derrota"):
        return "preocupada"
    return "alegre" if (est.get("evaluacion") or {}).get("estrellas", 0) >= 2 else "normal"

def cuadro_grande(pantalla, paginas, fuente, expr="normal"):
    """Cuadro de dialogo grande. paginas: lista de (quien, texto); quien: 'b', 'v' o None.
    Enter, espacio o clic avanzan. Bloquea mientras esta abierto (la partida queda en pausa)."""
    w, h = pantalla.get_size()
    fondo = pantalla.copy()
    f_n = pygame.font.Font(None, 30)
    f_t = pygame.font.Font(None, 28)
    f_p = pygame.font.Font(None, 22)
    reloj = pygame.time.Clock()
    i = 0
    while i < len(paginas):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                sonar("ui_mover"); i += 1
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                sonar("ui_mover"); i += 1
        if i >= len(paginas):
            break
        quien, texto = paginas[i]
        pantalla.blit(fondo, (0, 0))
        caja = pygame.Rect(30, h - 220, w - 60, 175)
        pygame.draw.rect(pantalla, (0, 0, 0), caja.move(4, 5), border_radius=8)
        pygame.draw.rect(pantalla, (22, 36, 28), caja, border_radius=8)
        pygame.draw.rect(pantalla, (255, 170, 60), caja, 3, border_radius=8)
        pygame.draw.rect(pantalla, (90, 120, 95), caja.inflate(-14, -14), 1, border_radius=6)
        pygame.draw.line(pantalla, (255, 215, 150), (caja.x + 5, caja.y + 3), (caja.right - 6, caja.y + 3))
        pygame.draw.line(pantalla, (255, 215, 150), (caja.x + 3, caja.y + 5), (caja.x + 3, caja.bottom - 6))
        pygame.draw.line(pantalla, (120, 70, 20), (caja.x + 5, caja.bottom - 4), (caja.right - 6, caja.bottom - 4))
        pygame.draw.line(pantalla, (120, 70, 20), (caja.right - 4, caja.y + 5), (caja.right - 4, caja.bottom - 6))
        tx = caja.x + 24
        if quien:
            es_b = quien == "b"
            ret = pygame.Rect(caja.x + 24, caja.y + 26, 96, 96)
            pygame.draw.rect(pantalla, (30, 16, 50), ret, border_radius=6)
            pygame.draw.rect(pantalla, (255, 170, 60) if es_b else (120, 220, 255), ret, 3, border_radius=6)
            ini = pygame.font.Font(None, 80).render("B" if es_b else "V", True,
                                                    (255, 170, 60) if es_b else (120, 220, 255))
            pantalla.blit(retrato(quien, expr.get(quien, "normal") if isinstance(expr, dict) else expr), ret); pygame.draw.rect(pantalla, (255, 170, 60) if es_b else (120, 220, 255), ret, 3, border_radius=6)
            nom = f_n.render("Bombero" if es_b else "Veterinaria", True,
                             (255, 170, 60) if es_b else (120, 220, 255))
            pantalla.blit(nom, (ret.right + 20, caja.y + 18))
            tx = ret.right + 20
            ty = caja.y + 50
        else:
            ty = caja.y + 26
        for k, l in enumerate(_ajustar(texto, f_t, caja.right - tx - 24)):
            pantalla.blit(f_t.render(l, True, (240, 240, 240)), (tx, ty + 28 * k))
        pie = f_p.render(f"Enter: continuar  ({i + 1}/{len(paginas)})", True, (200, 190, 150))
        pantalla.blit(pie, (caja.right - pie.get_width() - 22, caja.bottom - 30))
        pygame.display.flip()
        reloj.tick(30)

def animales_nivel(niv):
    return min(12, niv["animales"] * 2) if MODO_ESP["id"] == "supervivencia" else niv["animales"]

def intro_nivel(pantalla, fuente, est):
    niv = nivel_actual()
    b, v = INICIO_TXT[niv["id"]]
    pag = [(None, f"{niv['nombre']}. Apaga el incendio, lleva los {animales_nivel(niv)} animales al refugio" + ("." if MODO_ESP["id"] == "supervivencia" else " y conserva el bosque.")),
           ("b", b)]
    if v:
        pag.append(("v", v))
    cuadro_grande(pantalla, pag, fuente, expr={"b": "alegre", "v": "normal"})
    est["tick"]["t_fin"] = pygame.time.get_ticks()

def paginas_final(est):
    ev = est.get("evaluacion") or {}
    if est.get("derrota"):
        p = [("v", "Tenemos que replegarnos. Lo intentaremos otra vez."),
             ("b", "Aprendimos algo. A la próxima apagamos más rápido.")]
    else:
        e, s, t = ev.get("estrellas", 0), ev.get("salvos", 0), ev.get("total", 0)
        b = ev.get("bosque", 0)
        if e >= 2:
            p = [("b", "¡Lo logramos! Ese fuego se fue con la cola entre las patas."),
                 ("v", f"{s} de {t} animales a salvo y {b}% del bosque. Nada mal.")]
        else:
            p = [("b", "Pudo ser mejor, pero seguimos en pie."),
                 ("v", f"{s} de {t} animales a salvo y {b}% del bosque. Hay que mejorar.")]
    if nivel_actual()["dialogos"] in ("dificil", "silencio"):
        p = p[:1]
    return p

def eventos_periodicos(est, pantalla, fuente):
    """Cuadro de final de mision y avisos de cooperacion. Se llama una vez por cuadro."""
    if est.pop("final_pend", False):
        registrar_salon(est)
        pausa_prev = est["tick"]["pausa"]
        est["tick"]["pausa"] = True
        cuadro_grande(pantalla, paginas_final(est), fuente, expr=expr_final(est))
        est["tick"]["pausa"] = pausa_prev
        return
    ahora = pygame.time.get_ticks()
    if ahora - est.get("t_ev", 0) < 1500:
        return
    est["t_ev"] = ahora
    if ahora - est.get("t_aislado", -99999) > 30000 and "aislado" in estados_fauna(est):
        if decir(est, "v", "Hay un animal aislado. Hay que llegar antes de que cierre el fuego.", "importante", "aislado"):
            est["t_aislado"] = ahora

def _aviso_vida(est, k):
    if est["vida"][k] >= 35 or est.get("derrota"):
        return
    if k == "b":
        decir(est, "v", "Estás hecho una brasa. Sal de ahí.", "critico", "vida_b")
    else:
        decir(est, "b", "Veterinaria, sal de ahí. Hay fuego cerca.", "critico", "vida_v")

MANGUERA_R = 4; MANGUERA_MAX = 4     # radio y focos maximos por uso (1 carga de agua por foco)
TORRE_R = 20                          # radio de vigilancia de la torre
RASTREO_R = 14                        # radio del rastreo animal
BOTIQUIN_R = 3                        # distancia para atender a un animal
ZONA_ALERTA = 10                      # celdas de fuego al refugio que disparan la alerta
CD_MANGUERA_MS = 8000; CD_TORRE_MS = 15000; CD_BOTIQUIN_MS = 8000
CD_RASTREO_MS = 10000; CD_SENAL_MS = 12000
CD_PROT_MS = 20000; DUR_PROT_MS = 6000   # proteccion termica: recuperacion y duracion
CD_CONOC_MS = 8000; CONOC_R = 4; DUR_FICHA_MS = 7000   # conocimiento silvestre: recuperacion, radio y tiempo de la ficha

AGUA_GOTAS = [(-1, -1), (1, -1), (0, -1.4), (-0.6, -0.4), (0.6, -0.4)]

def fx_nuevo(est, tipo, x, y, dur, col, extra=None):
    """Efecto visual temporal. x, y en celdas. Formato: [tipo, x, y, t0, dur, col, extra]."""
    est.setdefault("fx", []).append([tipo, x, y, pygame.time.get_ticks(), dur, col, extra])


def dibujar_fx(pantalla, est):
    import math
    ahora = pygame.time.get_ticks()
    est["fx"] = [f for f in est.get("fx", []) if ahora - f[3] < f[4]]
    for tipo, x, y, t0, dur, col, extra in est["fx"]:
        f = (ahora - t0) / dur
        cx, cy = int(x * CELDA + CELDA // 2), int(y * CELDA + CELDA // 2)
        if tipo == "onda":
            r = int(extra * CELDA * f)
            if r > 1:
                pygame.draw.circle(pantalla, col, (cx, cy), r, 2)
                if r > 8:
                    pygame.draw.circle(pantalla, col, (cx, cy), r - 5, 1)
        elif tipo == "agua":
            pygame.draw.circle(pantalla, col, (cx, cy), int(CELDA * (0.5 + f * 1.5)), 1)
            for dx, dy in extra:
                px = cx + int(dx * f * 10)
                py = cy + int(dy * f * 10 + 14 * f * f)
                pygame.draw.rect(pantalla, col, (px - 1, py - 1, 3, 3))
                pantalla.set_at((px - 1, py - 1), tuple(min(255, c + 80) for c in col))
        elif tipo == "chorro":
            if f < 0.8:
                bx, by = extra
                pygame.draw.line(pantalla, col, (int(bx * CELDA + CELDA // 2), int(by * CELDA + CELDA // 2)),
                                 (cx, cy), 2)
                pygame.draw.circle(pantalla, col, (cx, cy), 3 + int(3 * f))
        elif tipo == "destello":
            pygame.draw.circle(pantalla, col, (cx, cy), int(6 + 14 * f), 2)
            pygame.draw.circle(pantalla, col, (cx, cy), int(3 + 8 * f), 1)
            _d = int(4 + 12 * f)
            for _dx, _dy in ((_d, 0), (-_d, 0), (0, _d), (0, -_d)):
                pygame.draw.rect(pantalla, (255, 255, 230), (cx + _dx - 1, cy + _dy - 1, 3, 3))
        elif tipo == "estrellas":
            for k in range(6):
                ang = k * math.pi / 3 + f * 3
                d = 4 + 18 * f
                px = cx + int(math.cos(ang) * d)
                py = cy - int(math.sin(ang) * d) - int(10 * f)
                pygame.draw.rect(pantalla, col, (px - 2, py, 5, 1))
                pygame.draw.rect(pantalla, col, (px, py - 2, 1, 5))
                pantalla.set_at((px, py), (255, 255, 235))
        elif tipo == "tierra":
            for dx, dy in extra:
                px = cx + int(dx * f * 9)
                py = cy + int(dy * f * 9 + 10 * f * f)
                pygame.draw.rect(pantalla, col, (px, py, 2, 2))
        elif tipo == "corazones":
            for k in range(3):
                g = max(0.0, min(1.0, f * 1.3 - k * 0.15))
                if 0 < g < 1:
                    dibujar_corazon(pantalla, cx + (k - 1) * 9, cy - 6 - int(28 * g) - k * 3, col)
        elif tipo == "lupa":
            _qy = cy - 14 - int(16 * f)
            _q = ("#####", "#...#", "....#", "..##.", "..#..", ".....", "..#..")
            for _fi, _fila in enumerate(_q):
                for _ci, _ch in enumerate(_fila):
                    if _ch == "#":
                        pygame.draw.rect(pantalla, (40, 30, 10), (cx - 7 + _ci * 3 - 1, _qy + _fi * 3 - 1, 5, 5))
            for _fi, _fila in enumerate(_q):
                for _ci, _ch in enumerate(_fila):
                    if _ch == "#":
                        pygame.draw.rect(pantalla, col, (cx - 7 + _ci * 3, _qy + _fi * 3, 3, 3))
        elif tipo == "cura":
            py = cy - 8 - int(18 * f)
            pygame.draw.rect(pantalla, (20, 40, 25), (cx - 2, py - 5, 5, 11))
            pygame.draw.rect(pantalla, (20, 40, 25), (cx - 5, py - 2, 11, 5))
            pygame.draw.rect(pantalla, col, (cx - 1, py - 4, 3, 9))
            pygame.draw.rect(pantalla, col, (cx - 4, py - 1, 9, 3))
            pygame.draw.rect(pantalla, (230, 255, 235), (cx - 1, py - 4, 1, 3))
            pygame.draw.circle(pantalla, col, (cx, py), 8 + int(4 * f), 1)
    if ahora < est.get("t_prot_fin", 0):
        p = est.get("vis", {}).get("b")
        if p:
            cx, cy = int(p[0] * CELDA + CELDA // 2), int(p[1] * CELDA + CELDA // 2)
            r = 14 + int(3 * abs(math.sin(ahora / 150)))
            pygame.draw.circle(pantalla, (255, 220, 80), (cx, cy), r + 3, 1)
            pygame.draw.circle(pantalla, (255, 130, 20), (cx, cy), r, 2)


def dibujar_corazon(pantalla, x, y, col, esc=1):
    """Corazon pixel art de 5x5 (esc = tamano del pixel). x, y = centro."""
    filas = (".#.#.", "#####", "#####", ".###.", "..#..")
    x0, y0 = x - 5 * esc // 2, y - 5 * esc // 2
    luz = tuple(min(255, c + 90) for c in col)
    for fi, fila in enumerate(filas):
        for ci, ch in enumerate(fila):
            if ch == "#":
                c = luz if (fi == 1 and ci == 1) else col
                pantalla.fill(c, (x0 + ci * esc, y0 + fi * esc, esc, esc))


def estado_hab(est, clave, cd):
    resto = cd - (pygame.time.get_ticks() - est.get(clave, -99999))
    return "listo" if resto <= 0 else f"{resto / 1000:.1f}s"

def _marcar(est, celdas, color, dur):
    fin = pygame.time.get_ticks() + dur
    est.setdefault("marcas", []).extend((x, y, color, fin) for x, y in celdas)

def habilidad(est, tecla, desde_ia=False):
    """G manguera, T torre (bombero); Z botiquin, X rastreo, Q senal de auxilio (veterinaria)."""
    if est.get("ver_eval") or est.get("derrota"):
        return
    ahora = pygame.time.get_ticks()
    n, estado = est["n"], est["estado"]
    ia = est.get("ia_rol")
    es_b = tecla in (pygame.K_g, pygame.K_t, pygame.K_h)
    if not desde_ia and ((es_b and ia == "bombero") or (not es_b and ia == "veterinaria")):
        est["msg"] = "Esa habilidad la controla la IA"
        return
    bx, by, vx, vy = est["bx"], est["by"], est["vx"], est["vy"]
    if tecla == pygame.K_g:
        if estado_hab(est, "t_mang", CD_MANGUERA_MS) != "listo":
            est["msg"] = "Manguera en recuperación"; return
        if est["agua"] <= 0:
            est["msg"] = "Tanque vacío: recárgalo junto al río"; return
        ya = {(x, y) for t, x, y in est["pend"] if t == "APAGAR"}
        cand = [(x, y) for y in range(max(0, by - MANGUERA_R), min(n, by + MANGUERA_R + 1))
                for x in range(max(0, bx - MANGUERA_R), min(n, bx + MANGUERA_R + 1))
                if estado[y * n + x] == 2 and (x - bx) ** 2 + (y - by) ** 2 <= MANGUERA_R ** 2
                and (x, y) not in ya]
        cand.sort(key=lambda c: (c[0] - bx) ** 2 + (c[1] - by) ** 2)
        cand = cand[:min(MANGUERA_MAX, est["agua"])]
        if not cand:
            est["msg"] = "Manguera: no hay focos al alcance"; return
        for x, y in cand:
            est["pend"].append(("APAGAR", x, y)); est["agua"] -= 1
        est["t_mang"] = ahora
        sonar("hab_manguera")
        est["msg"] = f"Manguera: {len(cand)} focos apuntados"
        for x, y in cand:
            fx_nuevo(est, "agua", x, y, 600, (120, 200, 255), AGUA_GOTAS)
            fx_nuevo(est, "chorro", x, y, 300, (150, 220, 255), (bx, by))
    elif tecla == pygame.K_t:
        if estado_hab(est, "t_torre", CD_TORRE_MS) != "listo":
            est["msg"] = "Torre en recuperación"; return
        fuegos = [(i % n, i // n) for i, v in enumerate(estado) if v == 2
                  and (i % n - bx) ** 2 + (i // n - by) ** 2 <= TORRE_R ** 2]
        est["t_torre"] = ahora
        _marcar(est, fuegos, (255, 140, 0), 5000)
        fx_nuevo(est, "onda", bx, by, 900, (255, 140, 0), TORRE_R)
        sonar("hab_torre")
        est["msg"] = f"Torre de vigilancia: {len(fuegos)} focos en un radio de {TORRE_R} celdas"
    elif tecla == pygame.K_z:
        if estado_hab(est, "t_boti", CD_BOTIQUIN_MS) != "listo":
            est["msg"] = "Botiquín en recuperación"; return
        sts = estados_fauna(est)
        cerca = [i for i, (a, st) in enumerate(zip(est["animales"], sts))
                 if a[2] == "libre" and st in ("herido", "aislado", "asustado")
                 and (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= BOTIQUIN_R ** 2]
        if not cerca:
            est["msg"] = "Botiquín: no hay animales en peligro cerca"; return
        est.setdefault("tratados", set()).add(cerca[0])
        est["t_boti"] = ahora
        sonar("hab_botiquin")
        est["msg"] = "Botiquín: animal atendido"
        _a = est["animales"][cerca[0]]
        fx_nuevo(est, "cura", _a[0], _a[1], 900, (80, 230, 120))
    elif tecla == pygame.K_x:
        if estado_hab(est, "t_rastreo", CD_RASTREO_MS) != "listo":
            est["msg"] = "Rastreo en recuperación"; return
        pos = [(a[0], a[1]) for a in est["animales"] if a[2] != "salvo"
               and (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= RASTREO_R ** 2]
        est["t_rastreo"] = ahora
        _marcar(est, pos, (80, 220, 255), 6000)
        fx_nuevo(est, "onda", vx, vy, 900, (80, 220, 255), RASTREO_R)
        sonar("hab_rastreo")
        est["msg"] = f"Rastreo: {len(pos)} animales cerca"
    elif tecla == pygame.K_q:
        if estado_hab(est, "t_senal", CD_SENAL_MS) != "listo":
            est["msg"] = "Señal de auxilio en recuperación"; return
        sts = estados_fauna(est)
        pos = [(a[0], a[1]) for a, st in zip(est["animales"], sts) if st == "aislado"]
        est["t_senal"] = ahora
        _marcar(est, pos, (255, 230, 60), 6000)
        fx_nuevo(est, "onda", vx, vy, 1200, (255, 230, 60), 14)
        sonar("hab_senal")
        est["msg"] = (f"Señal de auxilio: {len(pos)} animales aislados marcados" if len(pos) != 1 else "Señal de auxilio: 1 animal aislado marcado") if pos else "Señal de auxilio: sin animales aislados"
    elif tecla == pygame.K_h:
        if estado_hab(est, "t_prot", CD_PROT_MS) != "listo":
            est["msg"] = "Protección térmica en recuperación"; return
        est["t_prot"] = ahora
        est["t_prot_fin"] = ahora + DUR_PROT_MS
        est["msg"] = "Protección térmica activa: cruza las llamas sin daño"
        decir(est, "b", "Traje térmico listo. Ahora sí puedo meterme al fuego.", "importante", "prot")
        _s = AJ["snd"].get("proteccion")
        if _s:
            _s.play()
    elif tecla == pygame.K_k:
        if estado_hab(est, "t_conoc", CD_CONOC_MS) != "listo":
            est["msg"] = "Conocimiento silvestre en recuperación"; return
        cerca = [a for a in est["animales"] if (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= CONOC_R ** 2]
        if not cerca:
            est["msg"] = "Conocimiento silvestre: no hay animales cerca"; return
        a = min(cerca, key=lambda a: (a[0] - vx) ** 2 + (a[1] - vy) ** 2)
        import unicodedata
        def clave(s):
            return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
        ficha = next(((nom, lin) for nom, lin in CUADERNO[0][1] if clave(nom) == a[3]), None)
        if ficha is None:
            est["msg"] = "Conocimiento silvestre: sin ficha para esa especie"; return
        est["t_conoc"] = ahora
        est.setdefault("conocidas", set()).add(a[3])
        desbloquear(est, "fauna:" + a[3])
        fx_nuevo(est, "lupa", a[0], a[1], 1200, (255, 235, 120)); est["ficha_act"] = (ficha[0], ficha[1], ahora + DUR_FICHA_MS)
        est["msg"] = "Conocimiento silvestre: " + ficha[0] + " identificado"
        _s = AJ["snd"].get("conocimiento")
        if _s:
            _s.play()

_ICONOS_HAB = {
    "mochila": ((80, 170, 255), [
        ".....AA.....", "....AAAA....", "....AAAA....", "...AAAAAA...",
        "..AAAAAAAA..", "..AAWAAAAA..", "..AAWAAAAA..", "..AAAAAAAA..",
        "..AAAAAAAA..", "...AAAAAA...", "....aaaa....", "............"]),
    "cortafuego": ((170, 110, 60), [
        "............", "AAAAA.AAAAAA", "AAAAA.AAAAAA", "............",
        "AA.AAAAA.AAA", "AA.AAAAA.AAA", "............", "AAAAA.AAAAAA",
        "AAAAA.AAAAAA", "............", "AA.AAAAA.AAA", "AA.AAAAA.AAA"]),
    "manguera": ((190, 190, 200), [
        "............", "............", "A...........", "AAAA....W..W",
        "AAAAAAA.W.W.", "AAAAAAA..W..", "AAAAAAA.W.W.", "AAAA....W..W",
        "A...........", "A...........", "AA..........", "AAA........."]),
    "proteccion": ((255, 170, 60), [
        "............", ".AAAAAAAAAA.", ".AAWWAAAAAA.", ".AAWAAAAAAA.",
        ".AAAAAAAAAA.", ".AAAAAAAAAA.", "..AAAAAAAA..", "..AAAAAAAA..",
        "...AAAAAA...", "....AAAA....", ".....AA.....", "............"]),
    "torre": ((210, 170, 100), [
        "....AAAA....", "....AWWA....", "....AAAA....", ".....AA.....",
        "....AAAA....", "....A..A....", "...AA..AA...", "...A....A...",
        "..AAAAAAAA..", "..A......A..", ".AAAAAAAAAA.", "............"]),
    "botiquin": ((220, 50, 50), [
        "....AAAA....", "....A..A....", "AAAAAAAAAAAA", "AAAAAWWAAAAA",
        "AAAAAWWAAAAA", "AAAWWWWWWAAA", "AAAWWWWWWAAA", "AAAAAWWAAAAA",
        "AAAAAWWAAAAA", "AAAAAAAAAAAA", "aaaaaaaaaaaa", "............"]),
    "rastreo": ((160, 220, 120), [
        "............", "..AA....AA..", ".AAAA..AAAA.", ".AAAA..AAAA.",
        "..AA....AA..", "............", "....AAAA....", "...AAAAAA...",
        "..AAAAAAAA..", "..AAAAAAAA..", "...AA..AA...", "............"]),
    "senal": ((255, 220, 60), [
        "....AAAA....", "....AAAA....", "....AAAA....", "....AAAA....",
        "....AAAA....", "....AAAA....", ".....AA.....", "............",
        ".....AA.....", "....AAAA....", ".....AA.....", "............"]),
    "conocimiento": ((120, 200, 255), [
        "............", "............", "....AAAA....", "..AAAAAAAA..",
        ".AWWWKKWWWA.", "AWWWKKKKWWWA", "AWWWKKKKWWWA", ".AWWWKKWWWA.",
        "..AAAAAAAA..", "....AAAA....", "............", "............"]),
    "apoyo": ((240, 100, 140), [
        "............", "..AAA..AAA..", ".AAAAAAAAAA.", ".AAWAAAAAAA.",
        ".AAAAAAAAAA.", ".AAAAAAAAAA.", "..AAAAAAAA..", "...AAAAAA...",
        "....AAAA....", ".....AA.....", "............", "............"]),
    "rescate": ((120, 230, 120), [
        "............", ".....AA.....", "....AAAA....", "...AAAAAA...",
        "..AAAAAAAA..", ".AAAAAAAAAA.", "...AAAAAA...", "...AAKKAA...",
        "...AAKKAA...", "...AAKKAA...", "............", "............"]),
}
# (prefijo del nombre en el panel, icono, clave de recarga en est, duracion de la recarga)
_HAB_ICONO = (("Mochila", "mochila", None, 0), ("Cortafuegos", "cortafuego", "t_cf", CD_CORTAFUEGO_MS),
              ("Manguera", "manguera", "t_mang", CD_MANGUERA_MS), ("Proteccion", "proteccion", "t_prot", CD_PROT_MS),
              ("Torre", "torre", "t_torre", CD_TORRE_MS), ("Rescate", "rescate", None, 0),
              ("Apoyo", "apoyo", "t_apoyo", CD_APOYO_MS), ("Botiquin", "botiquin", "t_boti", CD_BOTIQUIN_MS),
              ("Rastreo", "rastreo", "t_rastreo", CD_RASTREO_MS), ("Senal", "senal", "t_senal", CD_SENAL_MS),
              ("Conocimiento", "conocimiento", "t_conoc", CD_CONOC_MS))

def dibujar_icono_hab(pantalla, nombre, est, x, y):
    """Icono pixel 12x12 de la habilidad; el velo de recarga se recoge de arriba hacia abajo."""
    for pref, clave, tk, cd in _HAB_ICONO:
        if nombre.startswith(pref):
            break
    else:
        return
    col, mat = _ICONOS_HAB[clave]
    pal = {"A": col, "a": tuple(int(c * 0.6) for c in col), "W": (245, 245, 245), "K": (30, 30, 30)}
    pantalla.blit(sprite_generico("hab:" + clave, mat, pal, 1), (x, y + 1))
    if tk and cd:
        frac = 1.0 - (pygame.time.get_ticks() - est.get(tk, -99999)) / cd
        if frac > 0:
            alto = max(1, int(12 * min(1.0, frac)))
            velo = pygame.Surface((12, alto), pygame.SRCALPHA)
            velo.fill((10, 10, 20, 170))
            pantalla.blit(velo, (x, y + 13 - alto))

def dibujar_habilidades(pantalla, est, fnt, parte="todo", vista=None):
    """Anillos de las habilidades y alerta de zona prioritaria (refugio)."""
    import math
    ahora = pygame.time.get_ticks()
    if parte in ("todo", "mundo"):
        dibujar_fx(pantalla, est)
        est["marcas"] = [m for m in est.get("marcas", []) if m[3] > ahora]
        r = CELDA + 2 + int(2 * abs(math.sin(ahora / 200)))
        for x, y, col, _ in est["marcas"]:
            pygame.draw.circle(pantalla, col, (x * CELDA + CELDA // 2, y * CELDA + CELDA // 2), r, 2)
    if parte == "mundo":
        return
    if ahora - est.get("t_dref", -99999) > 500:
        est["t_dref"] = ahora
        n = est["n"]
        rx, ry, rw, rh = est["refugio"]
        mejor = 999
        for i, v in enumerate(est["estado"]):
            if v == 2:
                fx, fy = i % n, i // n
                d = max(max(rx - fx, 0, fx - (rx + rw - 1)), max(ry - fy, 0, fy - (ry + rh - 1)))
                if d < mejor:
                    mejor = d
        est["d_ref"] = mejor
        alerta = mejor <= ZONA_ALERTA
        if alerta and not est.get("alerta_ref"):
            decir(est, "v", "El fuego se acerca al refugio.", "importante", "refugio")
        est["alerta_ref"] = alerta
    if est.get("alerta_ref") and not est.get("ver_eval") and (ahora // 400) % 2 == 0:
        s = fnt.render(f"ALERTA: fuego a {est['d_ref']} celdas del refugio", True, (255, 255, 255))
        caja = s.get_rect(center=((vista[0] if vista else est["n"] * CELDA) // 2, 18)).inflate(16, 8)
        pygame.draw.rect(pantalla, (170, 30, 30), caja, border_radius=6)
        pygame.draw.rect(pantalla, (255, 200, 200), caja, 2, border_radius=6)
        pantalla.blit(s, s.get_rect(center=caja.center))

def _hilo_tick(paso, pend, res):
    """Corre un tick del motor en segundo plano (no congela la ventana)."""
    try:
        correr_ronda(paso, pend)
        res["mapa"] = leer_mapa(MAPA_JUEGO)
    except Exception as ex:
        res["err"] = str(ex)
    res["listo"] = True

# Estrellas: 0 si falla, 1 si cumple, 2 con frac >= ESTR2, 3 con frac >= ESTR3 y ronda <= ESTR_RONDAS
ESTR2, ESTR3, ESTR_RONDAS = 0.55, 0.75, 30
BONO_RONDAS_TOPE, BONO_RONDA_PTS = 40, 3

def evaluar(est):
    salvos = sum(1 for a in est["animales"] if a[2] == "salvo")
    total = len(est["animales"])
    bosque = est["estado"].count(1) * 100 // est["veg0"]
    sup = MODO_ESP["id"] == "supervivencia"
    cumplida = (salvos >= META_SALVOS and (bosque >= META_BOSQUE or sup)
                and (MODO_ESP["id"] != "desafio" or est["ronda"] <= LIMITE_DESAFIO))
    frac = salvos / max(1, total) if sup else 0.5 * salvos / max(1, total) + 0.5 * bosque / 100
    if not cumplida:
        estrellas = 0
    elif frac >= ESTR3 and (sup or est["ronda"] <= ESTR_RONDAS):
        estrellas = 3
    elif frac >= ESTR2:
        estrellas = 2
    else:
        estrellas = 1
    puntos = (salvos * 100 + bosque * 5 + estrellas * 50
              + max(0, BONO_RONDAS_TOPE - est["ronda"]) * BONO_RONDA_PTS)
    if MODO_ESP["id"] == "supervivencia":
        puntos = salvos * 100 + max(0, 40 - est["ronda"]) * 5
    return dict(salvos=salvos, total=total, bosque=bosque, estrellas=estrellas,
                puntos=puntos, ronda=est["ronda"], focos=est["estado"].count(2),
                titulo=("MISION CUMPLIDA" if cumplida
                        else "MISION FALLIDA: meta no alcanzada"))

COMPARTIR_DIR = "output/compartir"
NOMBRES_MODO = {"record": "Modo récord", "supervivencia": "Supervivencia", "desafio": "Desafío",
                "corazon": "El corazón del incendio"}

def imagen_resultados(est, ev):
    # Genera un PNG fijo de 640x400 con los resultados de la misión. Devuelve la ruta.
    import time
    W, H = 640, 400
    s = _degradado_tramado(W, H, lambda t: (int(15 + 60 * t), int(40 - 10 * t), int(25 + 20 * t)))
    pygame.draw.rect(s, (255, 170, 60), (8, 8, W - 16, H - 16), 3, border_radius=10)
    f_tit, f_g, f_m, f_p = (pygame.font.Font(None, n) for n in (44, 34, 28, 22))

    def centrado(txt, fnt, col, y):
        r = fnt.render(txt, True, col)
        s.blit(r, r.get_rect(center=(W // 2, y)))

    niv = nivel_actual()
    modo = NOMBRES_MODO.get(MODO_ESP["id"])
    centrado("GUARDIANES DEL CHACO", f_tit, (255, 170, 60), 42)
    centrado(niv["nombre"] + (f"  -  {modo}" if modo else ""), f_m, (235, 235, 235), 82)
    centrado(str(ev.get("titulo", "")), f_m, (255, 220, 100), 114)
    r = 22
    dibujar_estrellas(s, W // 2 - (2 * r + 4), 160, ev.get("estrellas", 0), total=3, r=r)
    centrado(f"Puntuación: {ev.get('puntos', 0)}", f_g, (255, 255, 255), 215)
    centrado(f"Animales rescatados: {ev.get('salvos', 0)}/{ev.get('total', 0)}", f_m, (235, 235, 235), 255)
    centrado(f"Bosque conservado: {ev.get('bosque', 0)}%", f_m, (235, 235, 235), 285)
    centrado(f"Rondas usadas: {ev.get('ronda', 0)}", f_m, (235, 235, 235), 315)
    for x, pers in ((70, "bombero"), (W - 70, "vet")):
        _, spr = sprite_personaje(pers)
        big = pygame.transform.scale(spr, (spr.get_width() * 4, spr.get_height() * 4))
        s.blit(big, big.get_rect(center=(x, 255)))
    centrado("Simulación de incendios forestales - Chaco boliviano y Tarija", f_p, (190, 190, 190), 372)
    os.makedirs(COMPARTIR_DIR, exist_ok=True)
    nombre = niv["id"] + ("_" + MODO_ESP["id"] if MODO_ESP["id"] else "") + "_" + time.strftime("%Y%m%d-%H%M%S") + ".png"
    ruta = os.path.join(COMPARTIR_DIR, nombre)
    pygame.image.save(s, ruta)
    return ruta

# IA del compañero: tres niveles (spec 9.3). Valores ajustables.
IA_PESO_REFUGIO = 1.0      # Experto: peso de la cercania al refugio al elegir foco
IA_NIVELES = {
    "asistente": dict(nombre="Asistente", apoyo_agua=4, apoyo_vida=80, mang_min=None, hab_vet=(),
                      desc="Te apoya a ti: ataca los focos cercanos a ti y te cuida más seguido."),
    "equilibrado": dict(nombre="Equilibrado", apoyo_agua=2, apoyo_vida=60, mang_min=3, hab_vet=(pygame.K_z,),
                        desc="Combina ayuda y decisiones propias. Usa manguera y botiquín."),
    "experto": dict(nombre="Experto", apoyo_agua=2, apoyo_vida=60, mang_min=2, hab_vet=(pygame.K_z, pygame.K_q),
                    desc="Prioriza lo que amenaza el refugio y a los animales en peligro."),
}
MODO.setdefault("dif", "equilibrado")

def ia_param(k):
    return IA_NIVELES.get(MODO.get("dif"), IA_NIVELES["equilibrado"])[k]

def ia_ordenar_focos(est, fuegos):
    bx, by = est["bx"], est["by"]
    dif = MODO.get("dif")
    if dif == "asistente":
        px, py = est["vx"], est["vy"]
        fuegos.sort(key=lambda f: (f[0] - px) ** 2 + (f[1] - py) ** 2)
    elif dif == "experto":
        rx, ry, rw, rh = est["refugio"]
        cx, cy = rx + rw / 2, ry + rh / 2
        fuegos.sort(key=lambda f: (f[0] - bx) ** 2 + (f[1] - by) ** 2
                    + IA_PESO_REFUGIO * ((f[0] - cx) ** 2 + (f[1] - cy) ** 2))
    else:
        fuegos.sort(key=lambda f: (f[0] - bx) ** 2 + (f[1] - by) ** 2)

def ia_hab_bombero(est, fuegos):
    """Manguera de la IA: solo si esta lista y hay suficientes focos a su alcance."""
    minimo = ia_param("mang_min")
    if minimo is None or estado_hab(est, "t_mang", CD_MANGUERA_MS) != "listo" or est["agua"] < minimo:
        return False
    bx, by = est["bx"], est["by"]
    cerca = [f for f in fuegos if (f[0] - bx) ** 2 + (f[1] - by) ** 2 <= MANGUERA_R ** 2]
    if len(cerca) < minimo:
        return False
    t0 = est.get("t_mang")
    habilidad(est, pygame.K_g, desde_ia=True)
    return est.get("t_mang") != t0

def ia_hab_vet(est):
    """Botiquin y senal de auxilio de la IA, segun el nivel."""
    usa = ia_param("hab_vet")
    if not usa:
        return
    vx, vy = est["vx"], est["vy"]
    if pygame.K_z in usa and estado_hab(est, "t_boti", CD_BOTIQUIN_MS) == "listo":
        sts = estados_fauna(est)
        if any(a[2] == "libre" and st in ("herido", "aislado", "asustado")
               and (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= BOTIQUIN_R ** 2
               for a, st in zip(est["animales"], sts)):
            habilidad(est, pygame.K_z, desde_ia=True)
    if pygame.K_q in usa and estado_hab(est, "t_senal", CD_SENAL_MS) == "listo":
        if "aislado" in estados_fauna(est):
            habilidad(est, pygame.K_q, desde_ia=True)

def ia_prioridad_animales(est, libres):
    """Experto: atiende primero a los animales en peligro (si hay); el resto, todos los libres."""
    if MODO.get("dif") != "experto":
        return libres
    sts = estados_fauna(est)
    riesgo = [a for a, st in zip(est["animales"], sts)
              if a[2] == "libre" and st in ("herido", "aislado", "asustado")]
    return riesgo or libres

def seleccionar_dificultad(pantalla, fuente):
    """Devuelve la clave de dificultad, None si vuelve, 'salir' si cierra."""
    f_tit = pygame.font.Font(None, 56)
    f_op = pygame.font.Font(None, 36)
    w, h = pantalla.get_size()
    claves = list(IA_NIVELES)
    rects = [pygame.Rect(w // 2 - 260, 220 + i * 80, 520, 56) for i in range(len(claves))]
    sel = claves.index(MODO.get("dif")) if MODO.get("dif") in claves else 1
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    sonar("ui_volver")
                    return None
                elif e.key == pygame.K_UP:
                    sel = (sel - 1) % len(claves); sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(claves); sonar("ui_mover")
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    sonar("ui_aceptar")
                    return claves[sel]
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        if sel != i:
                            sonar("ui_mover")
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sonar("ui_aceptar"); return claves[i]
        pantalla.blit(fondo_marca(w, h), (0, 0))
        t = f_tit.render("Dificultad del compañero", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 150)))
        for i, r in enumerate(rects):
            rr = rect_boton(r, i == sel)
            pygame.draw.rect(pantalla, (0, 0, 0), rr.move(0, 3), border_radius=8)
            pygame.draw.rect(pantalla, color_boton(i == sel), rr, border_radius=8)
            pygame.draw.rect(pantalla, (255, 200, 120) if i == sel else (90, 120, 95), rr, 2, border_radius=8)
            s = f_op.render(IA_NIVELES[claves[i]]["nombre"], True, (255, 255, 255))
            pantalla.blit(s, s.get_rect(center=r.center))
        d = fuente.render(IA_NIVELES[claves[sel]]["desc"], True, (230, 230, 230))
        pantalla.blit(d, d.get_rect(center=(w // 2, 220 + len(claves) * 80 + 20)))
        v = fuente.render("Arriba/Abajo: elegir   Enter: continuar   Esc: volver", True, (170, 170, 170))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 40)))
        pygame.display.flip()
        reloj.tick(30)

def elegir_dificultad_modo(pantalla, fuente, m):
    """Tras elegir el modo: en solitario pide la dificultad. Devuelve m, None (volver) o 'salir'."""
    if m == "dos":
        return "dos"
    d = seleccionar_dificultad(pantalla, fuente)
    if d == "salir":
        return "salir"
    if d is None:
        return None
    MODO["dif"] = d
    return m

def ia_veterinaria(est, ahora):
    """IA basica de la veterinaria: camino mas corto (BFS) al animal libre mas cercano,
    lo recoge y lo lleva al refugio. Esquiva agua y celdas en llamas."""
    from collections import deque
    if est["ver_eval"] or est["tick"]["pausa"] or ahora - est.get("t_movv", 0) < 160:
        return
    est["t_movv"] = ahora
    if est["agua"] <= ia_param("apoyo_agua") or est["vida"]["b"] < ia_param("apoyo_vida"):
        apoyo(est, ahora, avisar=False)
    ia_hab_vet(est)
    n, estado = est["n"], est["estado"]
    vx, vy = est["vx"], est["vy"]
    if est["carga"] is None:
        libres = [a for a in est["animales"] if a[2] == "libre"]
        for a in libres:
            if (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= 4:
                a[2] = "cargado"; est["carga"] = a
                est["msg"] = "La IA recogio un animal"
                return
        libres = ia_prioridad_animales(est, libres)
        metas = {(a[0] + dx, a[1] + dy) for a in libres for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    else:
        rx, ry, rw, rh = est["refugio"]
        metas = {(x, y) for x in range(rx, rx + rw) for y in range(ry, ry + rh)}
    if (MODO.get("dif") == "asistente" and est["carga"] is None
            and ahora - est["t_apoyo"] >= CD_APOYO_MS
            and (est["agua"] <= ia_param("apoyo_agua") or est["vida"]["b"] < ia_param("apoyo_vida"))):
        metas = {(est["bx"] + dx, est["by"] + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    if not metas:
        return
    prev = {(vx, vy): None}
    cola = deque([(vx, vy)])
    meta = None
    while cola:
        c = cola.popleft()
        if c in metas:
            meta = c
            break
        x, y = c
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < n and 0 <= ny < n and (nx, ny) not in prev and estado[ny * n + nx] != 2:
                prev[(nx, ny)] = c
                cola.append((nx, ny))
    if meta is None or meta == (vx, vy):
        return
    while prev[meta] != (vx, vy):
        meta = prev[meta]
    est["vx"], est["vy"] = meta
    if estado[meta[1] * n + meta[0]] == 5:
        est["t_movv"] = ahora + 110    # vadear el rio es mas lento

def ia_bombero(est, ahora):
    """IA basica del bombero: va al foco mas cercano, se pone al alcance y lo apaga."""
    from collections import deque
    if est["ver_eval"] or est["tick"]["pausa"] or ahora - est.get("t_mov", 0) < 220:
        return
    est["t_mov"] = ahora
    n, estado = est["n"], est["estado"]
    bx, by = est["bx"], est["by"]
    pend_apagar = {(x, y) for t, x, y in est["pend"] if t == "APAGAR"}
    fuegos = [(i % n, i // n) for i, v in enumerate(estado) if v == 2 and (i % n, i // n) not in pend_apagar]
    if not fuegos:
        return
    ia_ordenar_focos(est, fuegos)
    if ia_hab_bombero(est, fuegos):
        return
    if est["agua"] <= 0:
        est["ia_rec"] = True
    elif est["agua"] >= tanque_max():
        est["ia_rec"] = False
    en_rio = est.get("ia_rec", False)
    if not en_rio:
        gastado = False
        for fx, fy in fuegos:
            if est["agua"] <= 0:
                break
            if (fx - bx) ** 2 + (fy - by) ** 2 <= (ALCANCE - 1) ** 2:
                est["pend"].append(("APAGAR", fx, fy)); est["agua"] -= 1; gastado = True
        if gastado:
            return
    tx, ty = fuegos[0]

    def llego(c):
        if en_rio:
            return any(0 <= c[0] + dx < n and 0 <= c[1] + dy < n and estado[(c[1] + dy) * n + c[0] + dx] == 5
                       for dy in range(-RIO_DIST, RIO_DIST + 1) for dx in range(-RIO_DIST, RIO_DIST + 1))
        return (c[0] - tx) ** 2 + (c[1] - ty) ** 2 <= (ALCANCE - 2) ** 2
    prev = {(bx, by): None}
    cola = deque([(bx, by)])
    meta = None
    while cola:
        c = cola.popleft()
        if llego(c):
            meta = c
            break
        x, y = c
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < n and 0 <= ny < n and (nx, ny) not in prev and estado[ny * n + nx] != 2:
                prev[(nx, ny)] = c
                cola.append((nx, ny))
    if meta is None or meta == (bx, by):
        return
    while prev[meta] != (bx, by):
        meta = prev[meta]
    est["bx"], est["by"] = meta
    if estado[meta[1] * n + meta[0]] == 5:
        est["t_mov"] = ahora + 110

def estados_fauna(est):
    """Estado de cada animal segun su situacion y la distancia al fuego (no toca a[2])."""
    n = est["n"]
    fuegos = [(i % n, i // n) for i, v in enumerate(est["estado"]) if v == 2]
    res = []
    for ax, ay, ea, esp in est["animales"]:
        if ea == "salvo":
            res.append("a salvo")
        elif ea == "cargado":
            res.append("en evacuacion")
        else:
            d = min((abs(fx - ax) + abs(fy - ay) for fx, fy in fuegos), default=999)
            if d == 0:
                res.append("herido")
            elif d <= 3:
                res.append("aislado")
            elif d <= 8:
                res.append("asustado")
            elif esp == "loro":
                res.append("escondido")
            else:
                res.append("tranquilo")
    return res

# Reaccion por especie: radio de alarma, pasos de huida por tick y distancia
# a la que se paraliza de miedo (0 = nunca). Nadie muere: si no puede huir, queda pendiente.
FAUNA_REACCION = {
    "tapir":   dict(radio=6,  pasos=1, para=2),
    "jaguar":  dict(radio=8,  pasos=3, para=0),
    "taitetu": dict(radio=7,  pasos=2, para=1),
    "loro":    dict(radio=10, pasos=4, para=0),
}

def mover_fauna(est):
    n, estado = est["n"], est["estado"]
    pend = est.setdefault("pendientes", set())
    fuegos = [(i % n, i // n) for i, v in enumerate(estado) if v == 2]
    if not fuegos:
        pend.clear()
        return
    def dist(x, y):
        return min(abs(fx - x) + abs(fy - y) for fx, fy in fuegos)
    for i, a in enumerate(est["animales"]):
        if a[2] != "libre":
            pend.discard(i)
            continue
        r = FAUNA_REACCION[a[3]]
        d = dist(a[0], a[1])
        if d > r["radio"]:
            pend.discard(i)
            continue
        movido = 0
        if not (0 < d <= r["para"]):
            for _ in range(r["pasos"]):
                mejor = None
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = a[0] + dx, a[1] + dy
                    if 0 <= nx < n and 0 <= ny < n and estado[ny * n + nx] not in (2, 5):
                        dn = dist(nx, ny)
                        if dn > d and (mejor is None or dn > mejor[0]):
                            mejor = (dn, nx, ny)
                if mejor is None:
                    break
                d, a[0], a[1] = mejor
                movido += 1
                if d > r["radio"]:
                    break
        if d <= 3 and movido == 0:
            if i not in pend:
                pend.add(i)
                est["msg"] = "¡" + a[3].capitalize() + " pendiente de rescate!"
                decir(est, "v", "El " + a[3] + " no puede salir solo. Hay que sacarlo antes de que llegue el fuego.", "importante", "pend" + str(i))
        else:
            pend.discard(i)

_TINTE = {"lado": 0, "clave": None, "sup": None}

def tinte_emergencia(pantalla, est):
    """Velo de color sobre el mapa: naranja suave en avanzada, rojo pulsante en critica."""
    import math
    nivel = est.get("nivel")
    if est.get("ver_eval") or nivel not in ("avanzada", "critica"):
        return
    if nivel == "avanzada":
        col, alfa = (255, 140, 30), 25
    else:
        col = (230, 30, 20)
        alfa = int(round((37 + 18 * math.sin(pygame.time.get_ticks() / 190)) / 5) * 5)
    lado = est["n"] * CELDA
    clave = (col, alfa, lado)
    if _TINTE["clave"] != clave:
        if _TINTE["lado"] != lado or _TINTE["sup"] is None:
            _TINTE["sup"] = pygame.Surface((lado, lado), pygame.SRCALPHA)
            _TINTE["lado"] = lado
        _TINTE["sup"].fill((col[0], col[1], col[2], alfa))
        _TINTE["clave"] = clave
    pantalla.blit(_TINTE["sup"], (0, 0))

CAM_ST = {"x": 0.0, "y": 0.0, "listo": False, "sup": None}

CELDA_BASE = 16

def tam_vista(n):
    # Vista en pixeles: lo que cabe en el escritorio (menos panel y barra de titulo), sin pasar del mundo.
    # Con VISTA=<celdas> se fuerza una vista cuadrada (solo para pruebas).
    mundo = n * CELDA
    try:
        k = int(os.environ.get("VISTA", "0"))
    except ValueError:
        k = 0
    if k >= 20:
        return min(mundo, k * CELDA), min(mundo, k * CELDA)
    return (min(mundo, max(200, ALTO_PANT["w"] - PANEL_W - MARGEN_VISTA_X)),
            min(mundo, max(200, ALTO_PANT["h"] - MARGEN_VISTA_Y)))

def superficie_mundo(n):
    # Superficie donde se dibuja todo el mundo; la ventana solo muestra un recorte.
    lado = n * CELDA
    s = CAM_ST["sup"]
    if s is None or s.get_size() != (lado, lado):
        s = pygame.Surface((lado, lado))
        CAM_ST["sup"] = s
    return s

def camara_actualizar(est, n, vw, vh):
    # Camara compartida: sigue el punto medio de los dos personajes, suavizada y sin salir del mundo.
    mundo_px = n * CELDA
    # zoom: se aleja por pasos cuando los dos personajes ya no caben (con histeresis para que no parpadee)
    dx = abs(est["bx"] - est["vx"]) * CELDA + ZOOM_MARGEN_X
    dy = abs(est["by"] - est["vy"]) * CELDA + ZOOM_MARGEN_Y

    def cabe(k, f):
        z = ZOOM_NIVELES[k]
        return ((mundo_px <= vw / z or dx <= vw / z * f) and
                (mundo_px <= vh / z or dy <= vh / z * f))

    k = CAM_ST.get("nivel", 0)
    while k < len(ZOOM_NIVELES) - 1 and not cabe(k, ZOOM_CABE_SALIR):
        k += 1
    if k > 0 and cabe(k - 1, ZOOM_CABE_ENTRAR):
        k -= 1
    CAM_ST["nivel"] = k
    z_obj = ZOOM_NIVELES[k]
    if not CAM_ST["listo"] or "z" not in CAM_ST:
        z = z_obj
    else:
        z = CAM_ST["z"] + (z_obj - CAM_ST["z"]) * 0.18
        if abs(z_obj - z) < 0.004:
            z = z_obj
    CAM_ST["z"] = z
    sw = min(mundo_px, int(round(vw / z)))
    sh = min(mundo_px, int(round(vh / z)))
    dw = vw if sw < mundo_px else min(vw, int(round(mundo_px * z)))
    dh = vh if sh < mundo_px else min(vh, int(round(mundo_px * z)))
    CAM_ST["sw"], CAM_ST["sh"], CAM_ST["dw"], CAM_ST["dh"] = sw, sh, dw, dh
    CAM_ST["ox"], CAM_ST["oy"] = (vw - dw) // 2, (vh - dh) // 2
    max_x, max_y = max(0, mundo_px - sw), max(0, mundo_px - sh)
    mx = (est["bx"] + est["vx"]) / 2 * CELDA + CELDA / 2
    my = (est["by"] + est["vy"]) / 2 * CELDA + CELDA / 2
    if pygame.time.get_ticks() < CAM_ST.get("libre_hasta", 0):   # mirando otra zona desde el minimapa
        mx, my = CAM_ST["libre"]
    obj_x = max(0.0, min(float(max_x), mx - sw / 2))
    obj_y = max(0.0, min(float(max_y), my - sh / 2))
    if not CAM_ST["listo"]:
        CAM_ST["x"], CAM_ST["y"], CAM_ST["listo"] = obj_x, obj_y, True
    else:
        CAM_ST["x"] += (obj_x - CAM_ST["x"]) * 0.2
        CAM_ST["y"] += (obj_y - CAM_ST["y"]) * 0.2
    CAM_ST["x"] = max(0.0, min(float(max_x), CAM_ST["x"]))
    CAM_ST["y"] = max(0.0, min(float(max_y), CAM_ST["y"]))
    return int(CAM_ST["x"]), int(CAM_ST["y"])

ZOOM_NIVELES = (1.0, 0.75, 0.5)   # zoom de la camara: 100%, 75% y 50%
ZOOM_MARGEN_X = 120; ZOOM_MARGEN_Y = 140   # px que deben sobrar alrededor de los dos personajes
ZOOM_CABE_SALIR = 0.9; ZOOM_CABE_ENTRAR = 0.75   # histeresis: se aleja pasando 90%, se acerca bajo 75%
COLOR_BANDAS_VISTA = (10, 14, 12)   # fondo donde la vista es mas ancha o alta que el mapa
FLECHA_MARGEN = 30                  # distancia al borde de la vista de la flecha del companero


def camara_blit(destino, mundo, vw, vh, cx, cy):
    # Dibuja en la ventana lo que ve la camara (con zoom); lo que queda fuera del mapa es fondo oscuro.
    sw, sh = CAM_ST.get("sw", vw), CAM_ST.get("sh", vh)
    dw, dh = CAM_ST.get("dw", vw), CAM_ST.get("dh", vh)
    ox, oy = CAM_ST.get("ox", 0), CAM_ST.get("oy", 0)
    W, H = mundo.get_size()
    cx, cy = max(0, min(cx, W - sw)), max(0, min(cy, H - sh))
    if (sw, sh) == (dw, dh):
        destino.blit(mundo, (ox, oy), pygame.Rect(cx, cy, sw, sh))
        return
    if dw < vw or dh < vh:
        destino.fill(COLOR_BANDAS_VISTA, (0, 0, vw, vh))
    parte = mundo.subsurface(pygame.Rect(cx, cy, sw, sh))
    destino.blit(pygame.transform.scale(parte, (dw, dh)), (ox, oy))


def camara_a_pantalla(wx, wy, cam):
    # pixel de mundo -> pixel de la ventana (con zoom)
    z = CAM_ST.get("z", 1.0)
    return (int(round((wx - cam[0]) * z)) + CAM_ST.get("ox", 0),
            int(round((wy - cam[1]) * z)) + CAM_ST.get("oy", 0))


def camara_a_mundo(mx, my):
    # pixel de la ventana -> pixel de mundo (con zoom)
    z = CAM_ST.get("z", 1.0)
    return ((mx - CAM_ST.get("ox", 0)) / z + int(CAM_ST["x"]),
            (my - CAM_ST.get("oy", 0)) / z + int(CAM_ST["y"]))


def camara_en_mundo(mx, my):
    # True si el pixel de la ventana cae sobre el mapa (no sobre las bandas oscuras)
    ox, oy = CAM_ST.get("ox", 0), CAM_ST.get("oy", 0)
    return (ox <= mx < ox + CAM_ST.get("dw", 10 ** 6)) and (oy <= my < oy + CAM_ST.get("dh", 10 ** 6))


def dibujar_flechas_companero(pantalla, est, fnt, vw, vh, cam):
    # Flecha en el borde de la vista, con el color del personaje, cuando ese personaje queda fuera de cuadro.
    import math
    hechas = []
    for k, col, ini in (("b", (255, 140, 40), "B"), ("v", (90, 220, 130), "V")):
        sx, sy = camara_a_pantalla(est[k + "x"] * CELDA + CELDA // 2, est[k + "y"] * CELDA + CELDA // 2 - 12, cam)
        if 10 <= sx <= vw - 10 and 10 <= sy <= vh - 10:
            continue
        dxv, dyv = sx - vw / 2, sy - vh / 2
        t = min((vw / 2 - FLECHA_MARGEN) / abs(dxv) if dxv else 1e9,
                (vh / 2 - FLECHA_MARGEN) / abs(dyv) if dyv else 1e9)
        px, py = vw / 2 + dxv * t, vh / 2 + dyv * t
        if px < 396 and py < 82:
            py = 82            # no tapar el cuadro de datos de arriba
        if px < 636 and py > vh - 62:
            py = vh - 62       # ni la barra de estado de abajo
        a = math.atan2(dyv, dxv)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        for ext, col_f in ((3, (0, 0, 0)), (0, col)):
            tip = (px + ux * (25 + ext), py + uy * (25 + ext))
            b1 = (px + ux * (11 - ext) + nx * (9 + ext), py + uy * (11 - ext) + ny * (9 + ext))
            b2 = (px + ux * (11 - ext) - nx * (9 + ext), py + uy * (11 - ext) - ny * (9 + ext))
            pygame.draw.polygon(pantalla, col_f, [tip, b1, b2])
        pygame.draw.circle(pantalla, (0, 0, 0), (int(px), int(py)), 15)
        pygame.draw.circle(pantalla, col, (int(px), int(py)), 13)
        t_i = fnt.render(ini, True, (20, 20, 20))
        pantalla.blit(t_i, (int(px) - t_i.get_width() // 2, int(py) - t_i.get_height() // 2))
        hechas.append(ini)
    return hechas


MINI = {"sup": None, "fuego": None, "S": 0, "img": None}

def minimapa_base(est, n, S):
    # Terreno reducido + fuego + refugio. Solo se rehace cuando cambia el mapa o el tamano.
    if MINI["sup"] is est["sup"] and MINI["fuego"] is est["fuego"] and MINI["S"] == S:
        return MINI["img"]
    try:
        img = pygame.transform.smoothscale(est["sup"], (S, S))
    except ValueError:
        img = pygame.transform.scale(est["sup"], (S, S))
    k = S / n
    lado = max(2, int(k) + 1)
    for x, y in est["fuego"]:
        img.fill((255, 120, 30), (int(x * k), int(y * k), lado, lado))
    rx, ry, rw, rh = est["refugio"]
    pygame.draw.rect(img, (120, 255, 160), (int(rx * k), int(ry * k), max(2, int(rw * k)), max(2, int(rh * k))), 1)
    MINI.update(sup=est["sup"], fuego=est["fuego"], S=S, img=img)
    return img

def dibujar_minimapa(pantalla, est, n, px, py, vista_w, vista_h, cam, fnt):
    # Minimapa del mundo entero en el panel: animales, personajes y rectangulo de la camara.
    S = min(PANEL_W - 24, vista_h - (py + 22) - 10)
    if S < 64:
        CAM_ST["mini"] = None
        return
    pantalla.blit(fnt.render("MAPA", True, (90, 40, 10)), (px + 1, py + 1))
    pantalla.blit(fnt.render("MAPA", True, (255, 200, 90)), (px, py))
    pygame.draw.line(pantalla, (230, 170, 60), (px, py + 17), (px + PANEL_W - 24, py + 17), 2)
    r = pygame.Rect(px, py + 22, S, S)
    CAM_ST["mini"] = r
    pantalla.blit(minimapa_base(est, n, S), r.topleft)
    k = S / n
    for a in est["animales"]:
        col = (120, 255, 160) if a[2] == "salvo" else (255, 230, 60)
        pantalla.fill(col, (r.x + int(a[0] * k), r.y + int(a[1] * k), 2, 2))
    for qx, qy, col in ((est["bx"], est["by"], (255, 140, 40)), (est["vx"], est["vy"], (90, 200, 255))):
        x, y = r.x + int(qx * k), r.y + int(qy * k)
        pantalla.fill((0, 0, 0), (x - 2, y - 2, 6, 6))
        pantalla.fill(col, (x - 1, y - 1, 4, 4))
    f = S / (n * CELDA)
    pygame.draw.rect(pantalla, (255, 255, 255),
                     (r.x + int(cam[0] * f), r.y + int(cam[1] * f), max(3, int(CAM_ST.get("sw", vista_w) * f)), max(3, int(CAM_ST.get("sh", vista_h) * f))), 1)
    pygame.draw.rect(pantalla, (230, 170, 60), r.inflate(2, 2), 1)

def mini_clic(mx, my, n):
    # Clic en el minimapa: la camara mira ese punto 4 s y luego vuelve a seguir a los personajes.
    r = CAM_ST["mini"]
    CAM_ST["libre"] = ((mx - r.x) / r.w * n * CELDA, (my - r.y) / r.h * n * CELDA)
    CAM_ST["libre_hasta"] = pygame.time.get_ticks() + 4000

def pajaros_ambiente(est):
    """Pajaros de fondo: suenan con el bosque sano y se apagan al llegar a 15% de perdida."""
    s = AJ["snd"].get("amb_pajaros")
    if not s:
        return
    try:
        perdida = 100 - est["estado"].count(1) * 100 // est["veg0"]
        f = 0.0 if est["ver_eval"] else max(0.0, 1.0 - perdida / 15.0)
        f = round(f * 20) / 20
        if f != AJ.get("paj_f"):
            AJ["paj_f"] = f
            aplicar_volumen()
        ahora = pygame.time.get_ticks()
        if f > 0 and s.get_num_channels() == 0:
            if "t_paj" not in est:
                est["t_paj"] = ahora
            elif ahora - est["t_paj"] > 4000:
                s.play(fade_ms=800)
                est.pop("t_paj")
        else:
            est.pop("t_paj", None)
    except Exception:
        pass

def chillar_fauna(est):
    """Un chillido por especie al pasar a asustado/aislado/herido; uno por tick y con pausa."""
    ya = est.setdefault("chillaron", set())
    sts = estados_fauna(est)
    peso = {"herido": 3, "aislado": 2, "asustado": 1}
    nuevos = []
    for i, (a, st) in enumerate(zip(est["animales"], sts)):
        if a[2] == "libre" and st in peso:
            if i not in ya:
                ya.add(i)
                nuevos.append((peso[st], i))
        else:
            ya.discard(i)
    if nuevos:
        ahora = pygame.time.get_ticks()
        if ahora - est.get("t_chillido", -99999) > 1500:
            est["t_chillido"] = ahora
            nuevos.sort(reverse=True)
            sonar("chillido_" + est["animales"][nuevos[0][1]][3])

def actualizar_emergencia(est):
    veg = est["estado"].count(1)
    quem = est["estado"].count(2)
    perdida = 100 - veg * 100 // est["veg0"]
    _prev = est.get("nivel")
    est["nivel"] = "inicial" if perdida < 15 else "avanzada" if perdida < 35 else "critica"
    if est["nivel"] != _prev and "dlg" in est:
        if est["nivel"] == "avanzada":
            sonar("alerta_avanzada")
            decir(est, "b", "Se está extendiendo. Hay que priorizar los focos.", "importante", "avanzada")
        elif est["nivel"] == "critica":
            sonar("alerta_critica")
            decir(est, "b", "Ok, ahora sí se puso serio. Todos a lo suyo.", "critico", "critica")
    if est["nivel"] == "critica":
        if est["cuenta"] is None:
            est["cuenta"] = CUENTA_RONDAS
        else:
            est["cuenta"] -= 1
            if 0 < est["cuenta"] <= 3:
                sonar("alerta_tic")
    if quem == 0 or (est["cuenta"] is not None and est["cuenta"] <= 0 and est["evaluacion"] is None):
        _primera = est["evaluacion"] is None
        est["evaluacion"] = evaluar(est); est["final_pend"] = True
        est["ver_eval"] = True
        if _primera:
            try:
                _tit = str(est["evaluacion"].get("titulo", ""))
                _snd = AJ["snd"].get("derrota" if _tit.startswith("MISION FALLIDA") else "recompensa")
                if _snd:
                    _snd.play()
            except Exception:
                pass

AJUSTES_RUTA = os.path.join("output", "ajustes.json")
AJ = {"mus": 0.5, "amb": 0.5, "efx": 0.5, "mute": False, "t": -10000, "snd": {}, "f": None}
CAT_SND = {"musica": "mus", "fuego": "amb", "amb_viento": "amb", "amb_pajaros": "amb"}   # canal de cada sonido; el resto es "efx"
BASE_VOL = {"musica": 0.35, "amb_viento": 0.3, "amb_pajaros": 0.5}   # volumen base de cada sonido; los efectos usan 1.0


def aplicar_volumen():
    for k, s in AJ["snd"].items():
        try:
            s.set_volume(0.0 if AJ["mute"] else AJ[CAT_SND.get(k, "efx")] * BASE_VOL.get(k, 1.0) * (AJ.get("paj_f", 1.0) if k == "amb_pajaros" else 1.0))
        except Exception:
            pass


def cargar_ajustes():
    import json as _j
    try:
        with open(AJUSTES_RUTA, encoding="utf-8") as f:
            d = _j.load(f)
        base = float(d.get("vol", 0.5))   # compatible con ajustes antiguos
        for c in ("mus", "amb", "efx"):
            AJ[c] = max(0.0, min(1.0, float(d.get(c, base))))
        AJ["mute"] = bool(d.get("mute", False))
    except Exception:
        pass


def guardar_ajustes():
    import json as _j
    try:
        os.makedirs("output", exist_ok=True)
        with open(AJUSTES_RUTA, "w", encoding="utf-8") as f:
            _j.dump({"mus": AJ["mus"], "amb": AJ["amb"], "efx": AJ["efx"], "mute": AJ["mute"]}, f)
    except Exception:
        pass


def cambiar_volumen(delta, canal="mus"):
    AJ[canal] = round(max(0.0, min(1.0, AJ[canal] + delta)), 2)
    AJ["mute"] = False
    AJ["t"] = pygame.time.get_ticks()
    aplicar_volumen()
    guardar_ajustes()


def dibujar_barra_volumen(pantalla, x, y, ancho=150):
    if AJ["f"] is None:
        AJ["f"] = pygame.font.Font(None, 20)
    pygame.draw.rect(pantalla, (20, 24, 28), (x - 6, y - 4, ancho + 12, 40), border_radius=6)
    txt = "Silenciado" if AJ["mute"] else "Musica " + str(int(round(AJ["mus"] * 100))) + "%"
    pantalla.blit(AJ["f"].render(txt, True, (235, 235, 235)), (x, y))
    pygame.draw.rect(pantalla, (70, 70, 70), (x, y + 20, ancho, 8), border_radius=4)
    if not AJ["mute"]:
        pygame.draw.rect(pantalla, (120, 255, 160), (x, y + 20, int(ancho * AJ["mus"]), 8), border_radius=4)


PAUSA_TABS = ["Controles", "Habilidades", "Fauna", "Audio"]
PAUSA_CTRL = [
    ("BOMBERO", [("Flechas", "moverse"), ("Clic izquierdo", "cortafuegos"), ("Clic derecho", "mochila de agua"),
                 ("G", "manguera de presion"), ("T", "torre de vigilancia"), ("H", "proteccion termica")]),
    ("VETERINARIA", [("W A S D", "moverse"), ("E", "recoger o soltar un animal"), ("Z", "botiquin"),
                     ("X", "rastreo animal"), ("Q", "senal de auxilio"), ("K", "conocimiento silvestre"),
                     ("F", "apoyo al bombero")]),
    ("GENERAL", [("V", "mapa de riesgo (El Vigia)"), ("P", "pausa y ayuda"), ("O", "ajustes de audio"),
                 ("M", "silenciar"), ("N", "Cuaderno de Guardianes"), ("Retroceso", "deshacer"),
                 ("R", "reiniciar"), ("I", "imagen de resultados (al final)")]),
]
# (prefijo del icono, nombre visible, descripcion, clave de recarga, duracion)
PAUSA_HAB = [
    ("BOMBERO", [("Mochila", "Mochila de agua", "Clic derecho apaga una celda en llamas. Se recarga junto al rio.", "agua"),
                 ("Cortafuegos", "Cortafuegos", "Clic izquierdo crea una barrera que frena el fuego.", "cf"),
                 ("Manguera", "Manguera de presion (G)", "Apaga varios focos cercanos; gasta una carga por foco.", "t_mang"),
                 ("Proteccion", "Proteccion termica (H)", "Durante 6 s cruzas celdas en llamas sin dano.", "t_prot"),
                 ("Torre", "Torre de vigilancia (T)", "Marca los focos que hay alrededor del bombero.", "t_torre")]),
    ("VETERINARIA", [("Rescate", "Rescate (E)", "Recoge o suelta un animal cercano. Llevalo al refugio.", None),
                     ("Apoyo", "Apoyo al bombero (F)", "A 2 celdas o menos le da +2 de agua y +15 de vida.", "apoyo"),
                     ("Botiquin", "Botiquin (Z)", "Atiende a un animal herido, aislado o asustado.", "t_boti"),
                     ("Rastreo", "Rastreo animal (X)", "Marca los animales que hay cerca.", "t_rastreo"),
                     ("Senal", "Senal de auxilio (Q)", "Marca los animales aislados.", "t_senal"),
                     ("Conocimiento", "Conocimiento silvestre (K)", "Identifica al animal cercano y abre su ficha.", "t_conoc")]),
]

def _rects_pausa(w, h):
    marco = pygame.Rect(30, 30, w - 60, h - 60)
    tw = (marco.w - 48) // 4
    return marco, [pygame.Rect(marco.x + 24 + i * tw, marco.y + 52, tw - 6, 30) for i in range(4)]

def _recarga_pausa(est, clave):
    if clave is None:
        return ""
    if clave == "agua":
        return f"{est['agua']}/{tanque_max()}"
    if clave == "cf":
        return estado_cortafuego(est)
    if clave == "apoyo":
        return estado_apoyo(est)
    cd = {"t_mang": CD_MANGUERA_MS, "t_prot": CD_PROT_MS, "t_torre": CD_TORRE_MS, "t_boti": CD_BOTIQUIN_MS,
          "t_rastreo": CD_RASTREO_MS, "t_senal": CD_SENAL_MS, "t_conoc": CD_CONOC_MS}[clave]
    return estado_hab(est, clave, cd)

def _dibujar_pausa(pantalla, est, tab, sel, fondo, inicio):
    w, h = pantalla.get_size()
    F = _SPRITES.setdefault("pausa_f", {})
    if not F:
        F["t"] = pygame.font.Font(None, 40); F["s"] = pygame.font.Font(None, 26); F["p"] = pygame.font.Font(None, 22)
    f_t, f_s, f_p = F["t"], F["s"], F["p"]
    pantalla.blit(fondo, (0, 0))
    velo = pygame.Surface((w, h), pygame.SRCALPHA); velo.fill((0, 0, 0, 200)); pantalla.blit(velo, (0, 0))
    marco, rt = _rects_pausa(w, h)
    pygame.draw.rect(pantalla, (0, 0, 0), marco.move(4, 5), border_radius=8)
    pygame.draw.rect(pantalla, (22, 36, 28), marco, border_radius=8)
    pygame.draw.rect(pantalla, (255, 170, 60), marco, 3, border_radius=8)
    pantalla.blit(f_t.render("COMO SE JUEGA" if inicio else "PAUSA", True, (255, 170, 60)), (marco.x + 24, marco.y + 12))
    for i, r in enumerate(rt):
        pygame.draw.rect(pantalla, (255, 170, 60) if i == tab else (40, 60, 48), r, border_radius=4)
        t = f_p.render(f"{i + 1}  {PAUSA_TABS[i]}", True, (30, 20, 10) if i == tab else (220, 220, 220))
        pantalla.blit(t, t.get_rect(center=r.center))
    x1 = marco.x + 24
    x2 = marco.x + 24 + marco.w // 2
    y0 = marco.y + 98
    if tab == 0:
        def bloque(x, y, titulo, filas):
            pantalla.blit(f_s.render(titulo, True, (255, 235, 190)), (x, y))
            pygame.draw.line(pantalla, (255, 140, 40), (x, y + 20), (x + marco.w // 2 - 48, y + 20))
            y += 28
            for tecla, texto in filas:
                pantalla.blit(f_p.render(tecla, True, (255, 220, 100)), (x, y))
                pantalla.blit(f_p.render(texto, True, (230, 230, 230)), (x + 110, y))
                y += 22
            return y + 10
        y = bloque(x1, y0, PAUSA_CTRL[0][0], PAUSA_CTRL[0][1])
        bloque(x1, y, PAUSA_CTRL[1][0], PAUSA_CTRL[1][1])
        bloque(x2, y0, PAUSA_CTRL[2][0], PAUSA_CTRL[2][1])
    elif tab == 1:
        for col, (titulo, filas) in enumerate(PAUSA_HAB):
            x = x1 if col == 0 else x2
            y = y0
            pantalla.blit(f_s.render(titulo, True, (255, 235, 190)), (x, y))
            pygame.draw.line(pantalla, (255, 140, 40), (x, y + 20), (x + marco.w // 2 - 48, y + 20))
            y += 28
            for pref, nombre, desc, clave in filas:
                dibujar_icono_hab(pantalla, pref, est, x, y + 2)
                rec = _recarga_pausa(est, clave)
                pantalla.blit(f_p.render(nombre + ("   " + rec if rec else ""), True, (255, 220, 100)), (x + 20, y))
                for k, lin in enumerate(_ajustar(desc, f_p, marco.w // 2 - 80)[:2]):
                    pantalla.blit(f_p.render(lin, True, (225, 225, 225)), (x + 20, y + 18 + 18 * k))
                y += 58
    elif tab == 2:
        pantalla.blit(f_s.render("ANIMALES DEL NIVEL", True, (255, 235, 190)), (x1, y0))
        pygame.draw.line(pantalla, (255, 140, 40), (x1, y0 + 20), (x1 + marco.w // 2 - 48, y0 + 20))
        y = y0 + 28
        for i_a, (a, st) in enumerate(zip(est["animales"], estados_fauna(est))):
            if i_a in est.get("tratados", ()) and st in ("herido", "aislado", "asustado"):
                st = "atendido"
            pantalla.blit(f_p.render(a[3].capitalize() + ": " + st, True, ESP_INFO[a[3]][1]), (x1, y)); y += 22
        pantalla.blit(f_s.render("ESTADOS", True, (255, 235, 190)), (x2, y0))
        pygame.draw.line(pantalla, (255, 140, 40), (x2, y0 + 20), (x2 + marco.w // 2 - 48, y0 + 20))
        y = y0 + 28
        for lin in ("Herido: el fuego esta en su celda.", "Aislado: el fuego esta a 3 celdas o menos.",
                    "Asustado: el fuego esta a 8 celdas o menos.", "Tranquilo: el fuego esta lejos.",
                    "En evacuacion: va contigo hacia el refugio.", "A salvo: ya llego al refugio.",
                    "Los animales no mueren: si no pueden huir,", "quedan pendientes de rescate."):
            pantalla.blit(f_p.render(lin, True, (225, 225, 225)), (x2, y)); y += 22
    else:
        canales = [("mus", "Musica"), ("amb", "Ambiente (fuego, viento, aves)"), ("efx", "Efectos")]
        ancho = 300; x0 = marco.centerx - ancho // 2
        for i, (c, nom) in enumerate(canales):
            y = y0 + 20 + i * 64
            col = (255, 200, 80) if i == sel else (220, 220, 220)
            pantalla.blit(f_s.render(nom + "  " + str(int(round(AJ[c] * 100))) + "%", True, col), (x0, y))
            pygame.draw.rect(pantalla, (70, 70, 70), (x0, y + 26, ancho, 10), border_radius=5)
            if not AJ["mute"]:
                pygame.draw.rect(pantalla, (120, 255, 160) if i == sel else (90, 190, 120),
                                 (x0, y + 26, int(ancho * AJ[c]), 10), border_radius=5)
        if AJ["mute"]:
            pantalla.blit(f_s.render("SILENCIADO (M)", True, (255, 120, 120)), (x0, y0 + 20 + 3 * 64))
    pie = "Tab o 1-4: pestanas   |   Esc, P o Enter: continuar" + ("   |   Audio: arriba/abajo canal, izq/der volumen, M silenciar" if tab == 3 else "")
    pantalla.blit(f_p.render(pie, True, (200, 190, 150)), (marco.x + 24, marco.bottom - 28))

def pantalla_pausa(pantalla, est, fuente, inicio=False):
    """Pausa con ayuda en pestanas. Se abre con P y al empezar la partida."""
    fondo = pantalla.copy()
    w, h = pantalla.get_size()
    tab, sel = 0, 0
    canales = ["mus", "amb", "efx"]
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                guardar_ajustes()
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_p, pygame.K_RETURN, pygame.K_KP_ENTER):
                    sonar("ui_volver"); guardar_ajustes()
                    return None
                elif e.key == pygame.K_TAB:
                    tab = (tab + 1) % 4; sonar("ui_mover")
                elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    tab = e.key - pygame.K_1; sonar("ui_mover")
                elif e.key == pygame.K_m:
                    AJ["mute"] = not AJ["mute"]; aplicar_volumen(); guardar_ajustes()
                elif tab == 3 and e.key == pygame.K_UP:
                    sel = (sel - 1) % 3; sonar("ui_mover")
                elif tab == 3 and e.key == pygame.K_DOWN:
                    sel = (sel + 1) % 3; sonar("ui_mover")
                elif tab == 3 and e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    cambiar_volumen(0.1 if e.key == pygame.K_RIGHT else -0.1, canales[sel])
                    if canales[sel] == "efx":
                        sonar("ui_mover")
                elif e.key == pygame.K_RIGHT:
                    tab = (tab + 1) % 4; sonar("ui_mover")
                elif e.key == pygame.K_LEFT:
                    tab = (tab - 1) % 4; sonar("ui_mover")
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(_rects_pausa(w, h)[1]):
                    if r.collidepoint(e.pos) and tab != i:
                        tab = i; sonar("ui_mover")
        _dibujar_pausa(pantalla, est, tab, sel, fondo, inicio)
        pygame.display.flip()
        reloj.tick(30)

_PANEL_ICONOS = (
    ("BOMBERO", (("Mochila", "D", None), ("Cortafuegos", "I", "t_cf"), ("Manguera", "G", "t_mang"),
                 ("Proteccion", "H", "t_prot"), ("Torre", "T", "t_torre"))),
    ("VETERINARIA", (("Rescate", "E", None), ("Apoyo", "F", "t_apoyo"), ("Botiquin", "Z", "t_boti"),
                     ("Rastreo", "X", "t_rastreo"), ("Senal", "Q", "t_senal"), ("Conocimiento", "K", "t_conoc"))),
)

def panel_resumen(pantalla, est, fnt, px, py):
    """Panel minimo: fila de iconos de habilidades con recarga y una pista de ayuda."""
    for titulo, items in _PANEL_ICONOS:
        pantalla.blit(fnt.render(titulo, True, (90, 40, 10)), (px + 1, py + 1)); pantalla.blit(fnt.render(titulo, True, (255, 200, 90)), (px, py))
        pygame.draw.line(pantalla, (230, 170, 60), (px, py + 17), (px + PANEL_W - 24, py + 17), 2)
        py += 22
        for k, (pref, tecla, clave) in enumerate(items):
            x = px + k * 30
            s = pygame.Surface((12, 13), pygame.SRCALPHA)
            dibujar_icono_hab(s, pref, est, 0, 0)
            pygame.draw.rect(pantalla, (20, 28, 24), (x - 2, py - 2, 28, 30), border_radius=4); pygame.draw.rect(pantalla, (120, 90, 40), (x - 2, py - 2, 28, 30), 1, border_radius=4)
            pantalla.blit(pygame.transform.scale(s, (24, 26)), (x, py))
            t = fnt.render(tecla, True, (255, 235, 150))
            pantalla.blit(t, (x + 12 - t.get_width() // 2, py + 28))
        py += 52
    pantalla.blit(fnt.render("P: ayuda y pausa", True, (200, 200, 200)), (px, py))
    pantalla.blit(fnt.render("O: audio   N: cuaderno", True, (200, 200, 200)), (px, py + 18))
    return py + 44

def ajustes_audio(pantalla):
    """Pantalla de ajustes: tres barras independientes (musica, ambiente, efectos)."""
    fondo = pantalla.copy()
    w, h = pantalla.get_size()
    f_t = pygame.font.Font(None, 40); f_o = pygame.font.Font(None, 28); f_p = pygame.font.Font(None, 22)
    canales = [("mus", "Musica"), ("amb", "Ambiente (fuego)"), ("efx", "Efectos")]
    sel = 0
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                guardar_ajustes()
                return
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_o, pygame.K_RETURN, pygame.K_KP_ENTER):
                    sonar("ui_volver")
                    guardar_ajustes()
                    return
                elif e.key == pygame.K_UP:
                    sel = (sel - 1) % 3; sonar("ui_mover")
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % 3; sonar("ui_mover")
                elif e.key == pygame.K_LEFT:
                    cambiar_volumen(-0.1, canales[sel][0])
                    if canales[sel][0] == "efx":
                        sonar("ui_mover")
                elif e.key == pygame.K_RIGHT:
                    cambiar_volumen(0.1, canales[sel][0])
                    if canales[sel][0] == "efx":
                        sonar("ui_mover")
                elif e.key == pygame.K_m:
                    AJ["mute"] = not AJ["mute"]; aplicar_volumen(); guardar_ajustes()
        pantalla.blit(fondo, (0, 0))
        velo = pygame.Surface((w, h), pygame.SRCALPHA); velo.fill((0, 0, 0, 190)); pantalla.blit(velo, (0, 0))
        t = f_t.render("Ajustes de audio", True, (255, 255, 255))
        pantalla.blit(t, (w // 2 - t.get_width() // 2, h // 2 - 130))
        ancho = 260; x0 = w // 2 - ancho // 2
        for i, (c, nom) in enumerate(canales):
            y = h // 2 - 70 + i * 55
            col = (255, 200, 80) if i == sel else (220, 220, 220)
            pantalla.blit(f_o.render(nom + "  " + str(int(round(AJ[c] * 100))) + "%", True, col), (x0, y))
            pygame.draw.rect(pantalla, (70, 70, 70), (x0, y + 26, ancho, 10), border_radius=5)
            if not AJ["mute"]:
                pygame.draw.rect(pantalla, (120, 255, 160) if i == sel else (90, 190, 120), (x0, y + 26, int(ancho * AJ[c]), 10), border_radius=5)
        if AJ["mute"]:
            m = f_o.render("SILENCIADO (M para activar)", True, (255, 120, 120))
            pantalla.blit(m, (w // 2 - m.get_width() // 2, h // 2 + 100))
        ayuda = f_p.render("Arriba/Abajo: canal   Izq/Der: volumen   M: silenciar   Esc u O: cerrar", True, (200, 200, 200))
        pantalla.blit(ayuda, (w // 2 - ayuda.get_width() // 2, h // 2 + 135))
        pygame.display.flip()
        reloj.tick(30)


def frames_fuego():
    """6 formas de llama (3 y sus espejos) y 2 resplandores. Se construyen una vez."""
    if "fuego_frames" not in _SPRITES:
        base = obtener_tiles()["fuego"]
        fr = list(base) + [pygame.transform.flip(s, True, False) for s in base]
        glow = []
        for a in (30, 52):
            g = pygame.Surface((CELDA * 3, CELDA * 3), pygame.SRCALPHA)
            pygame.draw.circle(g, (255, 120, 30, a), (CELDA * 3 // 2, CELDA * 3 // 2), CELDA * 3 // 2)
            glow.append(g)
        _SPRITES["fuego_frames"] = (fr, glow)
    return _SPRITES["fuego_frames"]


MAX_PART = 260

def actualizar_particulas(est, n, niv):
    """Brasas, humo y cenizas. Cada particula: [x, y, vx, vy, edad, vida, tipo, tam]."""
    import math
    P = est.setdefault("part", [])
    ang = math.radians(niv["viento_ang"])
    wx, wy = math.cos(ang) * niv["viento_fuerza"], math.sin(ang) * niv["viento_fuerza"]
    fuego = est["fuego"] if isinstance(est["fuego"], (list, tuple)) else list(est["fuego"])
    if fuego and len(P) < MAX_PART:
        for x, y in random.sample(fuego, min(len(fuego), 3)):
            cx, cy = x * CELDA + CELDA // 2, y * CELDA + CELDA // 2
            if random.random() < 0.55:      # humo
                P.append([cx + random.uniform(-3, 3), cy, wx * 0.5, -0.5 + wy * 0.3,
                          0, random.randint(50, 80), "humo", random.randint(3, 5)])
            if random.random() < 0.30:      # brasa
                P.append([cx, cy, wx * 0.9 + random.uniform(-0.5, 0.5), random.uniform(-2.0, -0.9),
                          0, random.randint(14, 30), "brasa", 2])
    est_c = est["estado"]
    if len(P) < MAX_PART:
        for _ in range(3):                  # ceniza sobre celdas ya quemadas
            r = random.randrange(n * n)
            if est_c[r] == 3 and random.random() < 0.15:
                P.append([(r % n) * CELDA + random.randint(0, CELDA - 1), (r // n) * CELDA - 8,
                          wx * 0.1, 0.3, 0, random.randint(25, 45), "ceniza", 1])
    if est.get("nivel") != "critica" and sum(1 for q in P if q[6] == "hoja") < 28 and random.random() < 0.25:
        L = n * CELDA
        if abs(wx) >= abs(wy):
            hx = -4 if wx > 0 else L + 4
            hy = random.uniform(0, L)
        else:
            hx = random.uniform(0, L)
            hy = -4 if wy > 0 else L + 4
        P.append([hx, hy, wx * 2.2 + 0.3 * (1 if wx >= 0 else -1), wy * 2.2, 0,
                  random.randint(150, 260), "hoja", random.randint(0, 2)])
    for p in P:
        p[0] += p[2]; p[1] += p[3]; p[4] += 1
        if p[6] == "hoja":
            p[1] += math.sin(p[4] / 7.0 + p[7]) * 0.6
        if p[6] == "humo":
            p[7] = min(9, p[7] + 0.05)
    est["part"] = [p for p in P if p[4] < p[5]]


def dibujar_particulas(pantalla, est):
    cache = _SPRITES.setdefault("humo_surf", {})
    for x, y, vx, vy, edad, vida, tipo, tam in est.get("part", []):
        f = 1.0 - edad / vida
        if tipo == "humo":
            r = int(tam)
            tono = 0 if f > 0.75 else (1 if f > 0.5 else 2)
            s = cache.get((r, tono))
            if s is None:
                col = ((200, 145, 105), (165, 152, 145), (140, 140, 140))[tono]
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, col + (110,), (r, r), r)
                pygame.draw.circle(s, col + (255,), (r, r), max(1, int(r * 0.6)))
                cache[(r, tono)] = s
            s.set_alpha(int(100 * f))
            pantalla.blit(s, (int(x) - r, int(y) - r))
        elif tipo == "brasa":
            col = (255, int(60 + 150 * f), 20)
            pygame.draw.rect(pantalla, col, (int(x), int(y), 2, 2))
            if f > 0.35 and (edad // 3) % 2 == 0:
                pantalla.set_at((int(x), int(y)), (255, 240, 170))
            if f > 0.6:
                pantalla.set_at((int(x) + 2, int(y) - 1), (200, 60, 20))
        elif tipo == "hoja":
            _ch = ((90, 150, 60), (60, 120, 50), (170, 130, 60))[int(tam) % 3]
            pygame.draw.rect(pantalla, _ch, (int(x), int(y), 3, 2))
            pantalla.set_at((int(x) + 1, int(y)), tuple(min(255, c + 60) for c in _ch))
        else:
            _cx = int(x) + (edad // 6) % 3 - 1
            pygame.draw.rect(pantalla, (190, 190, 190) if f > 0.4 else (130, 130, 130), (_cx, int(y), 2, 2))
            if f > 0.4:
                pantalla.set_at((_cx, int(y)), (230, 230, 230))


def anim_animal(est, i, esp, sfa, ax, ay, t):
    """Centro en pixeles (x, y) de un animal: posicion suave + temblor + rebote por especie."""
    import math
    px, py, mov = pos_suave(est, "a%d" % i, ax, ay, t)
    dx = dy = 0
    if sfa in ("asustado", "aislado", "herido"):
        dx = 1 if (t // 60) % 2 else -1
    if mov:
        if esp == "loro":
            dy = -int(4 * abs(math.sin(t / 70)))
        elif esp == "jaguar":
            dy = -int(3 * abs(math.sin(t / 90)))
        elif esp == "taitetu":
            dy = -int(2 * abs(math.sin(t / 110)))
        else:
            dy = -1 if (t // 200) % 2 else 0
    elif esp == "loro" and sfa == "asustado":
        dy = -int(2 * abs(math.sin(t / 80)))
    elif sfa == "a salvo":
        dy = -1 if (t // 300 + i) % 2 else 0
    return int(px * CELDA + CELDA // 2) + dx, int(py * CELDA + CELDA // 2) + dy


def dibujar_sombra(pantalla, cx, pies_y, ancho):
    """Elipse oscura translucida bajo los pies (cacheada por ancho)."""
    ancho = max(6, ancho)
    cache = _SPRITES.setdefault("sombras", {})
    s = cache.get(ancho)
    if s is None:
        s = pygame.Surface((ancho, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 90), (0, 0, ancho, 6))
        cache[ancho] = s
    pantalla.blit(s, (cx - ancho // 2, pies_y - 3))


def dibujar_halo(pantalla, cx, pies_y, col):
    """Resplandor suave en el suelo bajo un personaje (cacheado por color)."""
    cache = _SPRITES.setdefault("halos", {})
    s = cache.get(col)
    if s is None:
        s = pygame.Surface((30, 14), pygame.SRCALPHA)
        for k, a in enumerate((18, 28, 40)):
            pygame.draw.ellipse(s, col + (a,), (k * 3, k * 1, 30 - k * 6, 14 - k * 2))
        cache[col] = s
    pantalla.blit(s, (cx - 15, pies_y - 8))


def dibujar_ignis(pantalla, cx, base, nivel, t):
    """Ignis, la llama con cara: representa el incendio. Crece y se enoja con la emergencia."""
    import math
    s = {"inicial": 0.6, "avanzada": 0.85, "critica": 1.1}[nivel]
    dx = (1 if (t // 50) % 2 else -1) if nivel == "critica" else 0

    def P(x, y):
        return (int(cx + x * s + dx), int(base + y * s))

    w1, w2 = 4 * math.sin(t / 90), 4 * math.sin(t / 110 + 1)
    ext = [(-18, 0), (-22, -20), (-13, -36), (-8, -58 + w1), (-2, -40),
           (6, -52 + w2), (12, -34), (22, -20), (18, 0)]
    pygame.draw.polygon(pantalla, (255, 110, 20), [P(x, y) for x, y in ext])
    pygame.draw.polygon(pantalla, (255, 210, 70), [P(x * 0.6, y * 0.6) for x, y in ext])
    parpadeo = nivel == "inicial" and (t % 2600) < 130
    rojo = nivel == "critica"
    for ex in (-7, 7):
        if parpadeo:
            pygame.draw.line(pantalla, (60, 20, 10), P(ex - 3, -22), P(ex + 3, -22), 2)
        else:
            pygame.draw.circle(pantalla, (255, 255, 255), P(ex, -22), max(2, int(4 * s)))
            pygame.draw.circle(pantalla, (220, 20, 20) if rojo else (40, 20, 10),
                               P(ex * 0.8, -22), max(1, int(2 * s)))
    if nivel != "inicial":
        gr = 2 if rojo else 1
        pygame.draw.line(pantalla, (90, 20, 10), P(-12, -31), P(-4, -26), gr + 1)
        pygame.draw.line(pantalla, (90, 20, 10), P(12, -31), P(4, -26), gr + 1)
    if nivel == "inicial":
        r = pygame.Rect(0, 0, max(6, int(10 * s)), max(4, int(8 * s)))
        r.center = P(0, -14)
        pygame.draw.arc(pantalla, (90, 30, 10), r, math.pi, 2 * math.pi, 2)
    elif nivel == "avanzada":
        pygame.draw.line(pantalla, (90, 30, 10), P(-5, -13), P(5, -13), 2)
    else:
        pts = [P(-6, -14), P(-3, -9), P(0, -14), P(3, -9), P(6, -14)]
        pygame.draw.lines(pantalla, (90, 20, 10), False, pts, 2)


def pos_suave(est, k, x, y, ahora):
    """Posicion dibujada (en celdas, decimal): se desliza hacia la celda real."""
    v = est.setdefault("vis", {})
    p = v.get(k)
    if p is None or abs(p[0] - x) > 3 or abs(p[1] - y) > 3:
        p = [float(x), float(y)]
    dx, dy = x - p[0], y - p[1]
    mov = abs(dx) > 0.05 or abs(dy) > 0.05
    if mov:
        p[0] += dx * 0.35
        p[1] += dy * 0.35
    else:
        p[0], p[1] = float(x), float(y)
    v[k] = p
    return p[0], p[1], mov


def sprite_paso(spr, nombre, lado=1):
    """Cuadro de caminata: la fila de abajo (botas) se desplaza 2 px a la izquierda (-1) o derecha (1)."""
    clave = (nombre, "paso", lado)
    if clave not in _SPRITES:
        w, h = spr.get_size()
        s = spr.copy()
        piernas = spr.subsurface((8, h - 4, 16, 4)).copy()
        s.fill((0, 0, 0, 0), (8, h - 4, 16, 4))
        s.blit(piernas, (8 + 2 * lado, h - 4))
        _SPRITES[clave] = s
    return _SPRITES[clave]


def voltear_sprite(spr, nombre):
    """Sprite espejado horizontalmente (cacheado)."""
    clave = (nombre, "volteado")
    if clave not in _SPRITES:
        _SPRITES[clave] = pygame.transform.flip(spr, True, False)
    return _SPRITES[clave]


def main():
    global CELDA
    os.makedirs("output", exist_ok=True)
    asegurar_motor()
    pygame.init()
    if os.environ.get("CELDA"):
        CELDA = max(3, min(24, int(os.environ["CELDA"])))
    else:   # ajusta el tamano de celda a la altura de la pantalla
        _info_pant = pygame.display.Info(); ALTO_PANT["h"] = _info_pant.current_h; ALTO_PANT["w"] = _info_pant.current_w; CELDA = CELDA_BASE
    sonidos = {}
    try:   # si no hay audio, el juego sigue sin sonido
        pygame.mixer.init()
        sonidos["CORTAFUEGO"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "cortafuegos.wav"))
        sonidos["APAGAR"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "agua.wav"))
        musica = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "musica.wav"))
        cargar_ajustes()
        musica.play(loops=-1)
        sonidos["musica"] = musica
        for _n in ("rescate", "recompensa", "derrota", "proteccion", "conocimiento", "fuego",
                   "ui_mover", "ui_aceptar", "ui_volver", "ui_jugar", "ui_tienda", "ui_salir",
                   "pip_recoger", "pip_soltar", "hab_manguera", "hab_torre", "hab_botiquin", "hab_rastreo",
                   "hab_senal", "alerta_avanzada", "alerta_critica", "alerta_tic",
                   "ui_notif", "ui_moneda", "amb_viento",
                   "chillido_jaguar", "chillido_loro", "chillido_tapir", "chillido_taitetu",
                   "amb_pajaros"):
            try:
                sonidos[_n] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, _n + ".wav"))
            except Exception:
                pass
        AJ["snd"] = sonidos; sonidos["amb_viento"].play(loops=-1) if "amb_viento" in sonidos else None
        aplicar_volumen()
    except Exception as ex:
        print("Aviso: sin audio (" + str(ex) + ")")
    pygame.display.set_caption("Guardianes del Chaco - " + nivel_actual()["nombre"])
    fuente = pygame.font.Font(None, 24)
    fuente_p = pygame.font.Font(None, 20)
    reloj = pygame.time.Clock()
    est = {}

    def reiniciar():
        h = est.get("tick", {}).get("hilo")
        if h is not None and h.is_alive():
            h.join()
        shutil.copy(ruta_mapa(nivel_actual()), MAPA_JUEGO)
        os.chmod(MAPA_JUEGO, 0o666)   # el contenedor (mpiuser) debe poder reescribirlo
        n, estado, fuel = leer_mapa(MAPA_JUEGO)
        est.update(n=n, estado=estado, fuel=fuel, paso=0, ronda=0, pend=[], msg="",
                   veg0=max(1, estado.count(1)))
        est["bx"], est["by"] = posicion_inicial(n, estado)
        est["refugio"] = (4, n - 14, 10, 10)
        est["vx"], est["vy"] = 4 + 5, n - 14 + 5
        est["animales"] = crear_animales(n, estado, est["refugio"], animales_nivel(nivel_actual())); est["chillaron"] = set()
        est["carga"] = None
        est["riesgo"] = None; est["ver_riesgo"] = False; est["info_vigia"] = []
        est.update(nivel="inicial", cuenta=None, evaluacion=None, ver_eval=False)
        est["tick"] = dict(hilo=None, res=None, t_fin=pygame.time.get_ticks(), pausa=False)
        est["vida"] = {"b": VIDA_MAX, "v": VIDA_MAX}
        est["derrota"] = False; est["t_dano"] = 0
        est["agua"] = tanque_max(); est["t_cf"] = -99999; est["t_rec"] = 0; est["t_apoyo"] = -99999
        est["dlg"] = nuevo_dialogo(); est["salon_ok"] = False
        est["marcas"] = []; est["tratados"] = set(); est["alerta_ref"] = False; est["t_dref"] = -99999; est["pendientes"] = set(); est["t_prot"] = -99999; est["t_prot_fin"] = 0; est["t_conoc"] = -99999; est["ficha_act"] = None
        dialogos_inicio(est)
        if os.environ.get("DIALOGO_PRUEBA"):   # solo para probar el sistema de globos
            decir(est, "b", "¡Buenos días, Yacuiba! Hoy el fuego se va a arrepentir de haber madrugado.", "ocasional")
            decir(est, "v", "Concéntrate. Hay animales que dependen de que no te pongas a bromear.", "importante")
            decir(est, "b", "Sal de ahí, estás hecho una brasa.", "critico", "prueba_vida")
        redibujar()

    def redibujar():
        n = est["n"]
        T = obtener_tiles()
        sup = pygame.Surface((n * CELDA, n * CELDA))
        fuego = []
        agua = []
        estado, fuel = est["estado"], est["fuel"]
        for i in range(n):
            for j in range(n):
                s = estado[i * n + j]
                var = (((i * 73856093) ^ (j * 19349663)) >> 7) & 3
                if s == 1:
                    t = T["veg"][min(2, fuel[i * n + j] // 86)][var]
                else:
                    t = T[s][var]
                    if s == 2:
                        fuego.append((j, i))
                    elif s == 5:
                        agua.append((j, i))
                sup.blit(t, (j * CELDA, i * CELDA))
                if s == 1:
                    h = (((i * 73856093) ^ (j * 19349663)) >> 4) & 7
                    if CELDA < 12 and h < 2:
                        sup.fill((9, 12, 6), (j * CELDA, i * CELDA, CELDA, CELDA), special_flags=pygame.BLEND_RGB_ADD)
                    elif CELDA < 12 and h == 7:
                        sup.fill((9, 12, 6), (j * CELDA, i * CELDA, CELDA, CELDA), special_flags=pygame.BLEND_RGB_SUB)
        suavizar_bordes(sup, estado, n)
        # V11: decorados (arboles 2x2, arbustos, rocas, troncos quemados, orilla del rio)
        C2 = CELDA * 2
        cubiertas = set()
        for i in range(0, n - 2, 3):
            for j in range(0, n - 2, 3):
                idxs = [(i + a) * n + j + b for a in range(3) for b in range(3)]
                if (all(estado[k] == 1 for k in idxs) and min(fuel[k] for k in idxs) >= 130
                        and (((i * 83492791) ^ (j * 2654435761)) >> 5) & 7 < 6):
                    cubiertas.update(idxs)
                    arbol3(sup, j * CELDA, i * CELDA, ((i + j) // 3) % 3)
        for i in range(n):
            for j in range(n):
                idx = i * n + j
                s = estado[idx]
                x0, y0 = j * CELDA, i * CELDA
                h2 = (((i * 40503) ^ (j * 9973)) >> 3) & 15
                if s == 1 and idx not in cubiertas and h2 == 3:
                    if CELDA >= 12:
                        pygame.draw.ellipse(sup, (28, 64, 30), (x0 + 1, y0 + 4, CELDA - 2, CELDA - 5))
                        pygame.draw.ellipse(sup, (52, 108, 46), (x0 + 2, y0 + 4, CELDA - 5, CELDA - 8))
                        sup.fill((110, 170, 90), (x0 + 4, y0 + 5, 3, 2))
                        sup.set_at((x0 + 9, y0 + 6), (140, 200, 110))
                    else:
                        sup.fill((46, 92, 40), (x0 + 1, y0 + 2, CELDA - 2, CELDA - 3))
                        sup.set_at((x0 + 2, y0 + 2), (110, 170, 90))
                elif s == 0 and h2 == 5:
                    if CELDA >= 12:
                        pygame.draw.ellipse(sup, (70, 70, 68), (x0 + 1, y0 + CELDA - 6, CELDA - 2, 5))
                        pygame.draw.ellipse(sup, (112, 112, 108), (x0 + 2, y0 + 4, CELDA - 4, CELDA - 8))
                        pygame.draw.ellipse(sup, (152, 152, 146), (x0 + 4, y0 + 5, CELDA - 10, CELDA - 12))
                        sup.set_at((x0 + 5, y0 + 6), (200, 200, 194))
                    else:
                        sup.fill((80, 80, 78), (x0 + 1, y0 + CELDA - 2, CELDA - 2, 1))
                        sup.fill((130, 130, 125), (x0 + 1, y0 + 2, CELDA - 2, CELDA - 4))
                        sup.set_at((x0 + 1, y0 + 2), (178, 178, 172))
                elif s == 3 and h2 < 3:
                    _tw = max(2, CELDA // 6)
                    sup.fill((24, 20, 18), (x0 + CELDA // 2 - _tw // 2, y0 + 1, _tw, CELDA - 1))
                    sup.set_at((x0 + 1, y0 + 2), (24, 20, 18))
                if s == 1 and idx not in cubiertas and h2 in (7, 9, 11) and CELDA >= 6:
                    _fc = {7: (255, 150, 190), 9: (250, 250, 240), 11: (255, 225, 80)}[h2]
                    if CELDA >= 12:
                        fx_, fy_ = x0 + CELDA // 4 + (h2 % 3) * (CELDA // 6), y0 + CELDA // 4
                        for ddx, ddy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            sup.set_at((fx_ + ddx, fy_ + ddy), _fc)
                        sup.set_at((fx_, fy_), (255, 225, 80) if h2 != 11 else (255, 250, 240))
                        sup.fill((40, 110, 50), (fx_, fy_ + 2, 1, 3))
                        sup.set_at((fx_ + 1, fy_ + 4), (70, 150, 70))
                    else:
                        sup.set_at((x0 + 2 + h2 % 3, y0 + 3), _fc)
                        sup.set_at((x0 + 3 + h2 % 3, y0 + 3), _fc)
                        sup.set_at((x0 + 2 + h2 % 3, y0 + 4), (40, 110, 50))
                if s == 5:
                    for dj, di, rr in ((0, -1, (0, 0, CELDA, 1)), (0, 1, (0, CELDA - 1, CELDA, 1)),
                                       (-1, 0, (0, 0, 1, CELDA)), (1, 0, (CELDA - 1, 0, 1, CELDA))):
                        ii, jj = i + di, j + dj
                        if 0 <= ii < n and 0 <= jj < n and estado[ii * n + jj] != 5:
                            sup.fill((170, 225, 255), (x0 + rr[0], y0 + rr[1], rr[2], rr[3]))
                elif s in (0, 1, 3):
                    for dj, di, rr in ((0, -1, (0, 0, CELDA, 1)), (0, 1, (0, CELDA - 1, CELDA, 1)),
                                       (-1, 0, (0, 0, 1, CELDA)), (1, 0, (CELDA - 1, 0, 1, CELDA))):
                        ii, jj = i + di, j + dj
                        if 0 <= ii < n and 0 <= jj < n and estado[ii * n + jj] == 5:
                            sup.fill((96, 84, 60) if s != 1 else (22, 56, 34),
                                     (x0 + rr[0], y0 + rr[1], rr[2], rr[3]))
        decorar_mapa(sup, est, cubiertas)
        est["sup"] = sup
        est["fuego"] = fuego
        est["agua_celdas"] = agua

    reiniciar()
    n = est["n"]
    pantalla = pygame.display.set_mode((tam_vista(n)[0] + PANEL_W, tam_vista(n)[1]))
    ok_menu = menu_principal(pantalla, fuente); cortina(pantalla) if ok_menu else None
    if ok_menu:
        niv = nivel_actual()
        asegurar_motor(niv)
        if not os.environ.get("CELDA"):
            CELDA = CELDA_BASE
        reiniciar()
        n = est["n"]
        pantalla = pygame.display.set_mode((tam_vista(n)[0] + PANEL_W, tam_vista(n)[1]))
        pygame.display.set_caption("Guardianes del Chaco - " + niv["nombre"])
    if ok_menu:
        intro_nivel(pantalla, fuente, est); est["tick"]["t_fin"] = pygame.time.get_ticks()
    if not ok_menu:
        pygame.quit()
        return
    est["ia_rol"] = MODO["ia"]
    corriendo = True
    while corriendo:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                corriendo = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    corriendo = False
                elif e.key == pygame.K_e:
                    if est["carga"] is None:
                        for a in est["animales"]:
                            if a[2] == "libre" and (a[0] - est["vx"]) ** 2 + (a[1] - est["vy"]) ** 2 <= 4:
                                a[2] = "cargado"; est["carga"] = a
                                fx_nuevo(est, "destello", a[0], a[1], 700, (80, 255, 140))
                                sonar("pip_recoger")
                                est["msg"] = "Animal en brazos: llévalo al refugio"
                                break
                    else:
                        est["carga"][2] = "libre"
                        est["carga"][0], est["carga"][1] = est["vx"], est["vy"]
                        est["carga"] = None
                        sonar("pip_soltar")
                elif e.key == pygame.K_v:
                    if est.get("riesgo") is not None:
                        est["ver_riesgo"] = not est["ver_riesgo"]
                    else:
                        pygame.draw.rect(pantalla, (30, 34, 40), (tam_vista(n)[0], 0, PANEL_W, tam_vista(n)[1]))
                        pantalla.blit(fuente.render("Vigia calculando...", True, (255, 220, 100)),
                                      (tam_vista(n)[0] + 10, 10))
                        pygame.display.flip()
                        try:
                            est["riesgo"], est["info_vigia"] = calcular_vigia(n)
                            desbloquear(est, "atlas:vigia")
                            est["ver_riesgo"] = True
                            est["msg"] = ""
                        except Exception as ex:
                            est["msg"] = "Error del Vigia: " + str(ex)
                elif e.key == pygame.K_c:
                    if not est["derrota"]:
                        est["ver_eval"] = False
                elif e.key == pygame.K_i and est.get("ver_eval") and est.get("evaluacion"):
                    try:
                        _ruta = imagen_resultados(est, est["evaluacion"])
                        est["img_msg"] = (id(est["evaluacion"]), "Imagen guardada: " + os.path.basename(_ruta))
                    except Exception as ex:
                        est["img_msg"] = (id(est["evaluacion"]), "No se pudo guardar la imagen: " + str(ex))
                elif e.key == pygame.K_r:
                    reiniciar()
                elif e.key == pygame.K_m and "musica" in sonidos:
                    AJ["mute"] = not AJ["mute"]; AJ["t"] = pygame.time.get_ticks(); aplicar_volumen(); guardar_ajustes()
                elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    cambiar_volumen(-0.1)
                elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    cambiar_volumen(0.1)
                elif e.key == pygame.K_BACKSPACE and est["pend"]:
                    t_, _, _ = est["pend"].pop()
                    if t_ == "APAGAR":
                        est["agua"] = min(tanque_max(), est["agua"] + 1)
                elif e.key == pygame.K_f:
                    apoyo(est, pygame.time.get_ticks())
                elif e.key == pygame.K_F9:
                    ciclo = ["veterinaria", "bombero", None]
                    est["ia_rol"] = ciclo[(ciclo.index(est.get("ia_rol", "veterinaria")) + 1) % 3]
                    est["msg"] = ("IA controla: " + est["ia_rol"]) if est["ia_rol"] else "Sin IA: dos jugadores"
                elif e.key in (pygame.K_g, pygame.K_t, pygame.K_h, pygame.K_k, pygame.K_z, pygame.K_x, pygame.K_q):
                    _t0 = est.get(HAB_T.get(e.key))
                    habilidad(est, e.key)
                    if e.key in HAB_T and est.get(HAB_T[e.key]) != _t0:
                        desbloquear(est, "manual:" + HAB_FICHA[e.key])
                elif e.key == pygame.K_o:
                    pausa_prev_ = est["tick"]["pausa"]
                    est["tick"]["pausa"] = True
                    ajustes_audio(pantalla)
                    est["tick"]["pausa"] = pausa_prev_
                    est["tick"]["t_fin"] = pygame.time.get_ticks()
                elif e.key == pygame.K_n:
                    pausa_prev_ = est["tick"]["pausa"]
                    est["tick"]["pausa"] = True
                    cuaderno(pantalla, fuente)
                    est["tick"]["pausa"] = pausa_prev_
                    est["tick"]["t_fin"] = pygame.time.get_ticks()
                elif e.key == pygame.K_p:
                    pausa_prev_ = est["tick"]["pausa"]
                    est["tick"]["pausa"] = True
                    pantalla_pausa(pantalla, est, fuente)
                    est["tick"]["pausa"] = pausa_prev_
                    est["tick"]["t_fin"] = pygame.time.get_ticks()
                elif e.key == pygame.K_RETURN:
                    est["tick"]["t_fin"] = 0     # depuracion: adelanta el siguiente tick
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
                mx, my = e.pos
                _vw, _vh = tam_vista(n)
                if CAM_ST.get("mini") is not None and CAM_ST["mini"].collidepoint(mx, my):
                    mini_clic(mx, my, n)
                elif my < _vh and mx < _vw and camara_en_mundo(mx, my):
                    tipo = "CORTAFUEGO" if e.button == 1 else "APAGAR"
                    _wx, _wy = camara_a_mundo(mx, my)
                    cx, cy = int(_wx // CELDA), int(_wy // CELDA)
                    ahora_c = pygame.time.get_ticks()
                    if (cx - est["bx"]) ** 2 + (cy - est["by"]) ** 2 > ALCANCE ** 2:
                        est["msg"] = "Fuera de alcance: acércate con el bombero"
                    elif tipo == "APAGAR" and est["agua"] <= 0:
                        est["msg"] = "Tanque vacío: recárgalo junto al río"; decir(est, "b", "Me quedé sin agua. Voy al río, no me extrañen.", "critico", "tanque")
                    elif tipo == "CORTAFUEGO" and ahora_c - est["t_cf"] < CD_CORTAFUEGO_MS:
                        est["msg"] = "Cortafuegos en recuperación"
                    else:
                        est["msg"] = ""
                        est["pend"].append((tipo, cx, cy))
                        if tipo == "APAGAR":
                            est["agua"] -= 1
                        else:
                            est["t_cf"] = ahora_c
                        desbloquear(est, "manual:cortafuego" if tipo == "CORTAFUEGO" else "manual:mochila")
                        if tipo == "CORTAFUEGO":
                            desbloquear(est, "guia:cortafuegos")
                            fx_nuevo(est, "tierra", cx, cy, 500, (150, 105, 80), AGUA_GOTAS)
                        else:
                            fx_nuevo(est, "agua", cx, cy, 600, (120, 200, 255), AGUA_GOTAS)
                        if tipo in sonidos:
                            sonidos[tipo].play()

        ahora = pygame.time.get_ticks()
        tk = est["tick"]
        if tk["res"] is None:
            if (not tk["pausa"] and not est["ver_eval"] and est["estado"].count(2) > 0
                    and ahora - tk["t_fin"] >= TICK_MS[est["nivel"]]):
                tk["res"] = {}
                envio, est["pend"] = est["pend"], []
                tk["hilo"] = threading.Thread(target=_hilo_tick, args=(est["paso"], envio, tk["res"]), daemon=True)
                tk["hilo"].start()
        elif tk["res"].get("listo"):
            if "err" in tk["res"]:
                est["msg"] = "Error del motor: " + tk["res"]["err"]
            else:
                _, est["estado"], est["fuel"] = tk["res"]["mapa"]
                est["paso"] += PASOS_RONDA; est["ronda"] += 1
                actualizar_emergencia(est)
                est["msg"] = ""
                mover_fauna(est); chillar_fauna(est)
                desbloquear(est, "atlas:propagacion"); desbloquear(est, "guia:foco")
                if est["nivel"] != "inicial":
                    desbloquear(est, "atlas:emergencia")
                redibujar()
            tk["res"] = None; tk["t_fin"] = ahora
        if est.get("ia_rol", "veterinaria") == "bombero":
            ia_bombero(est, ahora)
        elif ahora - est.get("t_mov", 0) >= 90:   # el bombero se mueve cada 90 ms
            k = pygame.key.get_pressed()
            dx = int(bool(k[pygame.K_RIGHT])) - int(bool(k[pygame.K_LEFT]))
            dy = int(bool(k[pygame.K_DOWN])) - int(bool(k[pygame.K_UP]))
            if dx or dy:
                est["t_mov"] = ahora
                nx, ny = est["bx"] + dx, est["by"] + dy
                if 0 <= nx < n and 0 <= ny < n:
                    est["bx"], est["by"] = nx, ny
                    if est["estado"][ny * n + nx] == 5:
                        est["t_mov"] = ahora + 110    # vadear el rio es mas lento

        if est.get("ia_rol", "veterinaria") == "veterinaria":
            ia_veterinaria(est, ahora)
        elif ahora - est.get("t_movv", 0) >= 90:   # la veterinaria se mueve con W A S D
            k = pygame.key.get_pressed()
            dx = int(bool(k[pygame.K_d])) - int(bool(k[pygame.K_a]))
            dy = int(bool(k[pygame.K_s])) - int(bool(k[pygame.K_w]))
            if dx or dy:
                est["t_movv"] = ahora
                nx, ny = est["vx"] + dx, est["vy"] + dy
                if 0 <= nx < n and 0 <= ny < n:
                    est["vx"], est["vy"] = nx, ny
                    if est["estado"][ny * n + nx] == 5:
                        est["t_movv"] = ahora + 110
        if est["carga"] is not None:
            est["carga"][0], est["carga"][1] = est["vx"], est["vy"]
            rx, ry, rw, rh = est["refugio"]
            if rx <= est["vx"] < rx + rw and ry <= est["vy"] < ry + rh:
                est["carga"][2] = "salvo"
                fx_nuevo(est, "estrellas", est["vx"], est["vy"], 1500, (255, 230, 60))
                fx_nuevo(est, "corazones", est["vx"], est["vy"], 1700, (255, 90, 120))
                fx_nuevo(est, "onda", est["vx"], est["vy"], 900, (120, 255, 160), 3)
                desbloquear(est, "fauna:" + est["carga"][3]); desbloquear(est, "manual:rescate")
                if "rescate" in sonidos:
                    sonidos["rescate"].play()
                nsalvos = sum(1 for a in est["animales"] if a[2] == "salvo")
                est["carga"][0] = rx + 1 + ((nsalvos - 1) % 5) * 2
                est["carga"][1] = ry + 2 + ((nsalvos - 1) // 5) * 2
                est["carga"] = None
                est["msg"] = "Animal a salvo" if nsalvos < len(est["animales"]) else "¡Todos los animales a salvo!"
                decir(est, "v", "Uno menos en peligro. Lástima que el resto no lea instrucciones." if nsalvos < len(est["animales"]) else "Todos a salvo. Esta vez no hizo falta el sarcasmo.", "importante", "salvo")

        if not est["ver_eval"] and not est["tick"]["pausa"] and est["agua"] < tanque_max() and ahora - est["t_rec"] >= RECARGA_MS:
            bx2, by2 = est["bx"], est["by"]
            if any(0 <= bx2 + dx < n and 0 <= by2 + dy < n and est["estado"][(by2 + dy) * n + bx2 + dx] == 5
                   for dy in range(-RIO_DIST, RIO_DIST + 1) for dx in range(-RIO_DIST, RIO_DIST + 1)):
                est["agua"] += 1; est["t_rec"] = ahora
        if not est["ver_eval"] and not est["tick"]["pausa"] and ahora - est["t_dano"] >= 600:
            est["t_dano"] = ahora
            rx0, ry0, rw0, rh0 = est["refugio"]
            for k_, (cx_, cy_) in (("b", (est["bx"], est["by"])), ("v", (est["vx"], est["vy"]))):
                if est["estado"][cy_ * n + cx_] == 2 and not (k_ == "b" and ahora < est.get("t_prot_fin", 0)):
                    est["vida"][k_] = max(0, est["vida"][k_] - DANO_LLAMAS); _aviso_vida(est, k_)
                elif rx0 <= cx_ < rx0 + rw0 and ry0 <= cy_ < ry0 + rh0:
                    est["vida"][k_] = min(VIDA_MAX, est["vida"][k_] + CURA_REFUGIO)
            if (est["vida"]["b"] <= 0 or est["vida"]["v"] <= 0) and not est["derrota"]:
                quien = "El bombero" if est["vida"]["b"] <= 0 else "La veterinaria"
                ev = evaluar(est)
                ev["titulo"] = "MISION FALLIDA: " + quien + " cayo"
                ev["estrellas"] = 0
                est["evaluacion"] = ev; est["ver_eval"] = True; est["derrota"] = True; est["final_pend"] = True
                if "derrota" in sonidos:
                    sonidos["derrota"].play()
        vista_w, vista_h = tam_vista(n)
        lienzo_mundo = superficie_mundo(n)
        pant_real = pantalla
        pantalla = lienzo_mundo
        pantalla.fill((20, 20, 20))
        pantalla.blit(est["sup"], (0, 0))
        cuadro = pygame.time.get_ticks() // 110
        agua_t = obtener_tiles()[5]
        for x, y in est.get("agua_celdas", ()):
            pantalla.blit(agua_t[(cuadro // 2 + x * 3 + y * 5) % 4], (x * CELDA, y * CELDA))
        llamas, brillos = frames_fuego()
        for x, y in est["fuego"]:
            if (x + y) % 2 == 0:
                pantalla.blit(brillos[(cuadro // 3 + x) % 2], (x * CELDA - CELDA, y * CELDA - CELDA))
        for x, y in est["fuego"]:
            pantalla.blit(llamas[(cuadro + x * 7 + y * 13) % 6], (x * CELDA, y * CELDA))
        actualizar_particulas(est, n, nivel_actual())
        dibujar_particulas(pantalla, est)
        if est.get("ver_riesgo") and est.get("riesgo") is not None:
            pantalla.blit(est["riesgo"], (0, 0))
        rx, ry, rw, rh = est["refugio"]
        zona = pygame.Surface((rw * CELDA, rh * CELDA), pygame.SRCALPHA)
        zona.fill((80, 200, 120, 80))
        pantalla.blit(zona, (rx * CELDA, ry * CELDA))
        pygame.draw.rect(pantalla, (120, 255, 160), (rx * CELDA, ry * CELDA, rw * CELDA, rh * CELDA), 2)
        pantalla.blit(fuente.render("Refugio", True, (255, 255, 255)), (rx * CELDA, ry * CELDA - 18))
        sa = sprite_generico("animal", SPRITE_ANIMAL, PALETA_ANIMAL)
        _t = pygame.time.get_ticks()
        _pend = est.get("pendientes", ())
        for _i, ((ax, ay, ea, esp), sfa) in enumerate(zip(est["animales"], estados_fauna(est))):
            _cx, _cy = anim_animal(est, _i, esp, sfa, ax, ay, _t)
            _sf = "parpadeo" if (sfa in ("tranquilo", "escondido") and (_t // 120 + _i * 7) % 25 == 0) else sfa
            sa = sprite_animal(esp, _sf)
            _dd = est.setdefault("dir_an", {})
            _ant = _dd.get(_i)
            if _ant is None:
                _dd[_i] = (ax, 1)
            elif ax != _ant[0]:
                _dd[_i] = (ax, 1 if ax > _ant[0] else -1)
            if _dd[_i][1] < 0:
                sa = voltear_sprite(sa, esp + ":" + str(_sf))
            dibujar_sombra(pantalla, _cx, _cy + CELDA // 2, int(sa.get_width() * 0.8))
            pantalla.blit(sa, (_cx - sa.get_width() // 2, _cy + CELDA // 2 - sa.get_height()))
            if ea == "cargado":
                dibujar_corazon(pantalla, _cx + sa.get_width() // 2 + 5,
                                _cy + CELDA // 2 - sa.get_height() + 2 - (1 if (_t // 250) % 2 else 0),
                                (255, 90, 120), 2 if (_t // 250) % 2 else 1)
            col_anillo = {"asustado": (255, 230, 60), "aislado": (255, 140, 0), "herido": (255, 40, 40)}.get(sfa)
            if col_anillo:
                pygame.draw.ellipse(pantalla, col_anillo, pygame.Rect(_cx - 15, _cy + CELDA // 2 - 6, 30, 12), 3)
            ini, col_e = ESP_INFO[esp]
            t_e = fuente.render(ini, True, col_e)
            pos_e = (_cx - t_e.get_width() // 2, _cy + CELDA // 2 - sa.get_height() - t_e.get_height())
            pantalla.fill((0, 0, 0), t_e.get_rect(topleft=pos_e))
            pantalla.blit(t_e, pos_e)
            if _i in _pend:
                marcador_alerta(pantalla, fuente, _cx, pos_e[1] - 2, _t)
            if ea == "libre" and est["estado"][ay * n + ax] == 2:
                pygame.draw.circle(pantalla, (255, 40, 40), (_cx, _cy), 12, 2)
        pygame.draw.circle(pantalla, (255, 255, 255),
                           (est["bx"] * CELDA + CELDA // 2, est["by"] * CELDA + CELDA // 2),
                           ALCANCE * CELDA, 1)
        if pygame.time.get_ticks() < est.get("t_prot_fin", 0):
            pygame.draw.circle(pantalla, (255, 150, 0),
                               (est["bx"] * CELDA + CELDA // 2, est["by"] * CELDA - 9), 26, 3)
        _t = pygame.time.get_ticks()
        for _k, _nom, _spr in (("b",) + sprite_personaje("bombero"),
                               ("v",) + sprite_personaje("vet")):
            _px, _py, _mov = pos_suave(est, _k, est[_k + "x"], est[_k + "y"], _t)
            _salto = 0
            _fase = (_t // 130) % 4
            if _mov and _fase in (1, 3):
                _spr = sprite_paso(_spr, _nom, -1 if _fase == 1 else 1)
                _salto = 2
            _pcx = int(_px * CELDA + CELDA // 2)
            _pie = int(_py * CELDA + CELDA)
            dibujar_halo(pantalla, _pcx, _pie, (255, 140, 40) if _k == "b" else (90, 220, 130))
            dibujar_sombra(pantalla, _pcx, _pie, int(_spr.get_width() * 0.9))
            pantalla.blit(_spr, (int(_px * CELDA + CELDA // 2 - _spr.get_width() // 2),
                                 int(_py * CELDA + CELDA - _spr.get_height() - _salto)))
        salvos = sum(1 for a in est["animales"] if a[2] == "salvo")
        for k_, (cx_, cy_) in (("b", (est["bx"], est["by"])), ("v", (est["vx"], est["vy"]))):
            frac_ = est["vida"][k_] / VIDA_MAX
            bx_, by_ = cx_ * CELDA + CELDA // 2 - 14, cy_ * CELDA - 52
            pygame.draw.rect(pantalla, (0, 0, 0), (bx_ - 1, by_ - 1, 30, 6), border_radius=2)
            pygame.draw.rect(pantalla, (50, 12, 12), (bx_, by_, 28, 4))
            _cb = (255, 60, 60) if frac_ < 0.35 else (80, 220, 90)
            pygame.draw.rect(pantalla, _cb, (bx_, by_, int(28 * frac_), 4))
            if frac_ > 0:
                pygame.draw.line(pantalla, tuple(min(255, c + 70) for c in _cb), (bx_, by_), (bx_ + max(0, int(28 * frac_) - 1), by_))
        for tipo, x, y in est["pend"]:   # acciones pendientes (mundo)
            col = (255, 255, 255) if tipo == "CORTAFUEGO" else (0, 255, 255)
            pygame.draw.rect(pantalla, col, (x * CELDA, y * CELDA, CELDA, CELDA), 2)
        tinte_emergencia(pantalla, est)
        dibujar_habilidades(pantalla, est, fuente_p, "mundo")
        cam_x, cam_y = camara_actualizar(est, n, vista_w, vista_h)
        camara_blit(pant_real, pantalla, vista_w, vista_h, cam_x, cam_y)
        pantalla = pant_real
        dibujar_flechas_companero(pantalla, est, fuente_p, vista_w, vista_h, (cam_x, cam_y))
        txt_v = fuente.render(f"Vida  Bombero {est['vida']['b']}  Veterinaria {est['vida']['v']}", True, (255, 255, 255))
        pass
        pass
        txt_m = fuente.render((f"Meta: {META_SALVOS} animales y {META_BOSQUE}% bosque" if MODO_ESP["id"] not in ("supervivencia", "desafio") else (f"Supervivencia: meta {META_SALVOS} animales" if MODO_ESP["id"] == "supervivencia" else f"Desafío: {META_SALVOS} animales y {META_BOSQUE}% bosque en {LIMITE_DESAFIO} rondas")), True, (255, 230, 120))
        pass
        pass
        txt_a = fuente.render(f"Animales a salvo: {salvos}/{len(est['animales'])}", True, (255, 255, 255))
        marco_dorado(pantalla, pygame.Rect(0, 0, max(txt_v.get_width(), txt_m.get_width(), txt_a.get_width()) + 14, 67)); pantalla.blit(txt_v, (6, 24)); pantalla.blit(txt_m, (6, 44))
        pantalla.blit(txt_a, (6, 4))
        quemando, veg = est["estado"].count(2), est["estado"].count(1)
        linea1 = (f"Ronda {est['ronda']}  Paso {est['paso']}  En llamas {quemando}  "
                  f"Bosque {veg * 100 // est['veg0']}%  Agua {est['agua']}/{tanque_max()}  "
                  f"Cortafuego {estado_cortafuego(est)}")
        eventos_periodicos(est, pantalla, fuente)
        try:   # fuego ambiente: suena en bucle mientras haya focos
            _fs = AJ["snd"].get("fuego")
            if _fs:
                _hay = quemando > 0 and not est["ver_eval"]
                if _hay and not AJ.get("fuego_on"):
                    _fs.play(loops=-1); AJ["fuego_on"] = True
                elif not _hay and AJ.get("fuego_on"):
                    _fs.fadeout(600); AJ["fuego_on"] = False
        except NameError:
            raise
        except Exception:
            pass
        pajaros_ambiente(est); dibujar_habilidades(pantalla, est, fuente_p, "hud", (vista_w, vista_h))
        dibujar_globo(pantalla, est, fuente_p, (cam_x, cam_y), (vista_w, vista_h))
        dibujar_notif(pantalla, est, fuente_p, (vista_w, vista_h))
        if est["msg"]:
            linea2 = est["msg"]
        elif quemando == 0:
            linea2 = f"Incendio controlado. Bosque conservado: {veg * 100 // est['veg0']}%  (R = reiniciar)"
        else:
            linea2 = "Izq: cortafuegos | Der: agua | P: ayuda y pausa"
        _l1 = fuente.render(linea1, True, (255, 255, 255)); marco_dorado(pantalla, pygame.Rect(0, vista_h - 50, max(_l1.get_width(), fuente.size(linea2)[0]) + 14, 50)); pantalla.blit(_l1, (6, vista_h - 46))
        _l2 = fuente.render(linea2, True, (200, 200, 200)); pantalla.blit(_l2, (6, vista_h - 24))
        dibujar_fondo_panel(pantalla, vista_w, PANEL_W, vista_h); marco_dorado(pantalla, pygame.Rect(vista_w, 0, PANEL_W, vista_h), 0)
        px = vista_w + 10
        pantalla.blit(fuente.render("EL VIGIA", True, (90, 40, 10)), (px + 1, 11)); pantalla.blit(fuente.render("EL VIGIA", True, (255, 170, 60)), (px, 10)); pygame.draw.line(pantalla, (230, 170, 60), (px, min(32, 10 + fuente.get_height())), (px + PANEL_W - 70, min(32, 10 + fuente.get_height())), 2)
        dibujar_icono_cuaderno(pantalla, vista_w + PANEL_W - 50, 8, fuente_p)
        if pygame.time.get_ticks() - AJ["t"] < 2500:
            dibujar_barra_volumen(pantalla, vista_w - 170, 6)
        pantalla.blit(fuente.render("V: mapa de riesgo", True, (200, 200, 200)), (px, 34))
        if est.get("riesgo") is None:
            pantalla.blit(fuente.render("(sin calcular)", True, (150, 150, 150)), (px, 62))
        else:
            pantalla.blit(fuente.render("Capa: " + ("visible" if est["ver_riesgo"] else "oculta"),
                                        True, (120, 255, 160)), (px, 62))
            for k, texto in enumerate(est["info_vigia"]):
                pantalla.blit(fuente.render(texto, True, (230, 230, 230)), (px, 90 + 24 * k))
            for bx in range(PANEL_W - 20):
                pygame.draw.line(pantalla, color_riesgo(bx * 255 // (PANEL_W - 21)),
                                 (px + bx, 200), (px + bx, 214))
            pantalla.blit(fuente.render("0%", True, (200, 200, 200)), (px, 220))
            pantalla.blit(fuente.render("100%", True, (200, 200, 200)), (px + PANEL_W - 55, 220))
            pantalla.blit(fuente.render("Riesgo de quema", True, (200, 200, 200)), (px, 244))
        py = 270
        col_n = {"inicial": (120, 255, 160), "avanzada": (255, 200, 80), "critica": (255, 80, 80)}[est["nivel"]]
        banner_emergencia(pantalla, est, fuente_p, vista_w, py)
        py += 50
        py = panel_resumen(pantalla, est, fuente_p, px, py)
        dibujar_minimapa(pantalla, est, n, px, py, vista_w, vista_h, (cam_x, cam_y), fuente_p)
        fa = est.get("ficha_act")
        if fa and pygame.time.get_ticks() < fa[2]:
            ancho_f = vista_w - 80
            partes = [("Conocimiento silvestre: " + fa[0], (255, 220, 100))]
            for lin in fa[1]:
                partes += [(p_, (235, 235, 235)) for p_ in _ajustar(lin, fuente_p, ancho_f - 24)]
            alto_f = 16 + 20 * len(partes)
            cuadro_f = pygame.Surface((ancho_f, alto_f), pygame.SRCALPHA)
            cuadro_f.fill((20, 30, 24, 230))
            pantalla.blit(cuadro_f, (40, 80))
            pygame.draw.rect(pantalla, (255, 170, 60), (40, 80, ancho_f, alto_f), 2)
            for k_f, (t_f, c_f) in enumerate(partes):
                pantalla.blit(fuente_p.render(t_f, True, c_f), (52, 88 + 20 * k_f))
        if est.get("ver_eval") and est.get("evaluacion"):
            ev = est["evaluacion"]
            lineas = [ev.get("titulo", "EVALUACION DE LA MISION"),
                      "Estrellas: " + "*" * ev["estrellas"] + "-" * (3 - ev["estrellas"]),
                      "Animales rescatados: " + str(ev["salvos"]) + "/" + str(ev["total"]),
                      "Bosque conservado: " + str(ev["bosque"]) + "%",
                      "Focos activos: " + str(ev["focos"]),
                      "Rondas usadas: " + str(ev["ronda"]),
                      "Puntuacion: " + str(ev["puntos"]) + est.get("monedas_txt", ""),
                      "C = continuar   R = reiniciar   I = imagen"]
            if MODO_ESP["id"] in ("record", "supervivencia", "desafio", "corazon"):
                lineas[7:7] = [est.get("record_msg") or "Solo cuenta si cumples la misión."]
                lineas[1:1] = [{"record": "Modo récord", "supervivencia": "Supervivencia", "desafio": "Desafío", "corazon": "El corazón del incendio"}[MODO_ESP["id"]]]
            _alto = 30 + 28 * len(lineas)
            _caja = pygame.Rect(60, 120, 440, _alto)
            pygame.draw.rect(pantalla, (0, 0, 0), _caja.move(4, 5), border_radius=8)
            pygame.draw.rect(pantalla, (18, 28, 22), _caja, border_radius=8)
            pygame.draw.rect(pantalla, (255, 170, 60), _caja, 3, border_radius=8)
            pygame.draw.line(pantalla, (255, 140, 40), (80, 135 + 24), (480, 135 + 24))
            for k, t in enumerate(lineas):
                pantalla.blit(fuente.render(t, True, (255, 220, 100) if k == 0 else (235, 235, 235)),
                              (80, 135 + 28 * k))
            _im = est.get("img_msg")
            if _im and _im[0] == id(ev):
                _ti = fuente.render(_im[1], True, (120, 230, 120))
                pantalla.fill((0, 0, 0), _ti.get_rect(topleft=(60, 120 + _alto + 12)))
                pantalla.blit(_ti, (60, 120 + _alto + 12))
        pygame.display.flip()
        reloj.tick(30)
    pygame.quit()

if __name__ == "__main__":
    main()
