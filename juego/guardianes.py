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
PANEL_W = 330                                # panel lateral derecho
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

def obtener_tiles():
    """Tiles pixel art dibujados por codigo (se construyen una sola vez)."""
    if _TILES:
        return _TILES
    C = CELDA

    def base(col):
        s = pygame.Surface((C, C))
        s.fill(col)
        return s

    def puntos(s, col, lista):
        for x, y in lista:
            s.set_at((x % C, y % C), col)

    veg = []
    for b in [(28, 70, 40), (34, 100, 50), (40, 135, 58)]:
        claro = tuple(min(255, c + 30) for c in b)
        oscuro = tuple(max(0, c - 18) for c in b)
        fila = []
        for v in range(4):
            s = base(b)
            pygame.draw.rect(s, claro, (1 + v % 2, 1, 3, 3))
            puntos(s, oscuro, [(v, 5), (5 - v, 0)])
            fila.append(s)
        veg.append(fila)
    _TILES["veg"] = veg

    agua, vacia, cortafuego, quemada, suelo_fuego = [], [], [], [], []
    for v in range(4):
        s = base((33, 150, 243)); y = 1 + (v % 3) * 2
        puntos(s, (120, 200, 255), [(v, y), (v + 1, y), (v + 2, y)])
        agua.append(s)
        s = base((222, 200, 150))
        puntos(s, (190, 165, 115), [(v, 1), (5 - v, 4)])
        vacia.append(s)
        s = base((121, 85, 72))
        puntos(s, (80, 55, 45), [(0, v), (1, v), (3, 5 - v), (4, 5 - v)])
        cortafuego.append(s)
        s = base((45, 45, 45))
        puntos(s, (140, 50, 20), [(v, 2), (5 - v, 4)])
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
        pygame.draw.polygon(s, (255, 110, 20), ext)
        pygame.draw.polygon(s, (255, 220, 80), inte)
        fuego.append(s)
    _TILES["fuego"] = fuego
    return _TILES


SPRITE_BOMBERO = [
    "..RRRR..",
    ".RRRRRR.",
    "RRRRRRRR",
    ".SSSSSS.",
    ".SKSSKS.",
    "..SSSS..",
    ".UUUUUU.",
    "BUUYYUUB",
    ".UUUUUU.",
    ".KK..KK.",
]
PALETA_BOMBERO = {"R": (200, 30, 30), "S": (240, 190, 150), "K": (30, 30, 30),
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
    "..GGGG..",
    ".GGGGGG.",
    "GGGGGGGG",
    ".SSSSSS.",
    ".SKSSKS.",
    "..SSSS..",
    ".WWWWWW.",
    "SWWGGWWS",
    ".WWWWWW.",
    ".PP..PP.",
]
PALETA_VET = {"G": (30, 140, 80), "S": (240, 190, 150), "K": (30, 30, 30),
              "W": (240, 240, 240), "P": (60, 60, 120)}
SPRITE_ANIMAL = [
    ".DDDD..",
    "DTTTTD.",
    "TTTTTTK",
    "TT.TT..",
]
PALETA_ANIMAL = {"D": (110, 70, 40), "T": (170, 120, 70), "K": (20, 20, 20)}

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
    dict(id="yacuiba", nombre="Bosques de Yacuiba", n=96, semilla_mapa=42, focos=None,
         semilla=42, viento_ang=0.0, viento_fuerza=0.6, animales=5,
         dialogos="facil", dificultad=1),
    dict(id="aguarague", nombre="Serranía del Aguaragüe", n=112, semilla_mapa=7, focos=None,
         semilla=7, viento_ang=45.0, viento_fuerza=0.8, animales=6,
         dialogos="medio", dificultad=2),
    dict(id="tarija", nombre="Región de Tarija", n=128, semilla_mapa=21, focos=None,
         semilla=21, viento_ang=90.0, viento_fuerza=0.9, animales=7,
         dialogos="dificil", dificultad=3),
    dict(id="gran_incendio", nombre="El gran incendio", n=128, semilla_mapa=99, focos=None,
         semilla=99, viento_ang=135.0, viento_fuerza=1.1, animales=8,
         dialogos="silencio", dificultad=4),
]
NIVEL_SEL = {"i": 0}   # indice del nivel activo (el menu de niveles lo cambiara)

def nivel_actual():
    return NIVELES[NIVEL_SEL["i"]]

def args_viento(niv):
    return f"--viento-ang {niv['viento_ang']} --viento-fuerza {niv['viento_fuerza']}"

def asegurar_motor(niv=None):
    """Compila fire_seq y genera el mapa del nivel dentro del contenedor si faltan."""
    niv = niv or nivel_actual()
    focos = f" --focos {niv['focos']}" if niv["focos"] is not None else ""
    mapa = f"data/maps/map_{niv['n']}.bin"
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

ALTO_PANT = {"h": 768}          # alto del escritorio, para calcular CELDA por nivel
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
        n, estado, _ = leer_mapa(f"data/maps/map_{niv['n']}.bin")
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
    k = len(NIVELES)
    mg = 16
    cw = (w - mg * (k + 1)) // k
    lado = min(cw - 20, 170)
    ch = lado + 86
    y0 = 90
    rects = [pygame.Rect(mg + i * (cw + mg), y0, cw, ch) for i in range(k)]
    sel = NIVEL_SEL["i"]
    reloj = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "salir"
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    return None
                elif e.key == pygame.K_LEFT:
                    sel = (sel - 1) % k
                elif e.key == pygame.K_RIGHT:
                    sel = (sel + 1) % k
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return sel
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        return i
        pantalla.fill((22, 34, 26))
        t = f_tit.render("Elige el nivel", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 45)))
        for i, r in enumerate(rects):
            niv = NIVELES[i]
            pygame.draw.rect(pantalla, (40, 52, 44), r, border_radius=8)
            pygame.draw.rect(pantalla, (255, 87, 34) if i == sel else (90, 90, 90), r, 3, border_radius=8)
            pantalla.blit(miniatura_nivel(niv, lado), (r.centerx - lado // 2, r.y + 10))
            nom = f_nom.render(niv["nombre"], True, (255, 255, 255))
            if nom.get_width() > cw - 8:
                nom = f_p.render(niv["nombre"], True, (255, 255, 255))
            pantalla.blit(nom, nom.get_rect(center=(r.centerx, r.y + lado + 30)))
            dibujar_estrellas(pantalla, r.centerx - 33, r.y + lado + 56, niv["dificultad"])
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
            ("Mapa ilustrativo, no a escala real.", f_p, (170, 170, 170)),
        ]
        yy = ficha.y + 14
        for txt, fnt, col in lineas:
            pantalla.blit(fnt.render(txt, True, col), (ficha.x + 16, yy))
            yy += 30
        v = fuente.render("Izq/Der: elegir   Enter: jugar   Esc: volver", True, (170, 170, 170))
        pantalla.blit(v, v.get_rect(center=(w // 2, h - 22)))
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
                    return None
                elif e.key == pygame.K_UP:
                    sel = (sel - 1) % len(opciones)
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(opciones)
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return opciones[sel][1]
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        return opciones[i][1]
        pantalla.fill((22, 34, 26))
        t = f_tit.render("Elige el modo de juego", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 170)))
        for i, r in enumerate(rects):
            pygame.draw.rect(pantalla, (255, 87, 34) if i == sel else (60, 60, 60), r, border_radius=8)
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
    "Tienda (bloqueada)": ("Tienda de personalización (bloqueada)", [
        "Se desbloqueará con las EcoMonedas que ganes rescatando animales",
        "y protegiendo el bosque.",
        "",
        "Sombreros, accesorios, vestimentas y uniformes alternativos.",
        "Los elementos cosméticos no dan ventajas durante las partidas.",
        "",
        "Estado: bloqueada. Llegará en una etapa posterior."]),
    "Próximamente": ("Próximamente", [
        "Lo que viene después de esta versión:",
        "",
        "Tienda de personalización y EcoMonedas.",
        "Modos especiales: Supervivencia, Desafío, El corazón del incendio y Modo récord.",
        "Compartir resultados como imagen.",
        "Cámara inteligente y pantalla dividida.",
        "Arte pixel definitivo, animaciones y audio avanzado.",
        "Habilidades extra: protección térmica."]),
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

def registrar_salon(est):
    """Actualiza los records con la evaluacion de la partida (una vez por partida)."""
    import json
    if est.get("salon_ok"):
        return
    est["salon_ok"] = True
    ev = est.get("evaluacion") or {}
    if not ev:
        return
    s = cargar_salon()
    s["partidas"] += 1
    if ev.get("puntos", 0) > s["puntos"]:
        s["puntos"] = ev["puntos"]; s["nivel_puntos"] = nivel_actual()["nombre"]
    s["salvos"] = max(s["salvos"], ev.get("salvos", 0))
    s["bosque"] = max(s["bosque"], ev.get("bosque", 0))
    if str(ev.get("titulo", "")).startswith("MISION CUMPLIDA"):
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
        ("Ficha de ejemplo", ["Causas frecuentes: quemas agrícolas sin control y descuidos con fuego.",
                              "Prevención: no encender fuego con viento y avisar a las autoridades ante un foco.",
                              "[contenido de ejemplo]"])]),
    ("Manual de emergencias", [
        ("Ficha de ejemplo", ["Mochila de agua: apaga una celda en llamas. El tanque se recarga junto al río.",
                              "Cortafuegos: barrera que frena el avance. Tiene tiempo de recuperación.",
                              "[contenido de ejemplo]"])]),
    ("Atlas de incendios", [
        ("Ficha de ejemplo", ["El fuego avanza más rápido en la dirección del viento.",
                              "El Vigía (tecla V) muestra el riesgo de quema con simulaciones Monte Carlo.",
                              "[contenido de ejemplo]"])]),
]

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
                    return None
                elif e.key == pygame.K_RIGHT:
                    sec = (sec + 1) % len(CUADERNO); ent = 0
                elif e.key == pygame.K_LEFT:
                    sec = (sec - 1) % len(CUADERNO); ent = 0
                elif e.key == pygame.K_DOWN:
                    ent = (ent + 1) % len(CUADERNO[sec][1])
                elif e.key == pygame.K_UP:
                    ent = (ent - 1) % len(CUADERNO[sec][1])
        pantalla.blit(fondo, (0, 0))
        marco = pygame.Rect(30, 30, w - 60, h - 60)
        pygame.draw.rect(pantalla, (45, 25, 70), marco, border_radius=8)
        pygame.draw.rect(pantalla, (200, 180, 240), marco, 3, border_radius=8)
        t = f_tit.render("CUADERNO DE GUARDIANES", True, (255, 170, 60))
        pantalla.blit(t, t.get_rect(center=(w // 2, 68)))
        x = marco.x + 20
        for i, (nom, _) in enumerate(CUADERNO):
            s = f_s.render(nom, True, (255, 255, 255) if i == sec else (150, 140, 175))
            pantalla.blit(s, (x, 100))
            if i == sec:
                pygame.draw.line(pantalla, (255, 170, 60), (x, 122), (x + s.get_width(), 122), 2)
            x += s.get_width() + 24
        fichas = CUADERNO[sec][1]
        lista = pygame.Rect(marco.x + 20, 140, 190, marco.h - 140 - 60)
        for i, (nom, _) in enumerate(fichas):
            r = pygame.Rect(lista.x, lista.y + i * 36, lista.w, 30)
            pygame.draw.rect(pantalla, (255, 87, 34) if i == ent else (70, 50, 100), r, border_radius=6)
            pantalla.blit(f_s.render(nom, True, (255, 255, 255)), (r.x + 10, r.y + 6))
        det = pygame.Rect(lista.right + 20, 140, marco.right - lista.right - 40, lista.h)
        pygame.draw.rect(pantalla, (32, 20, 52), det, border_radius=6)
        yy = det.y + 14
        pantalla.blit(f_tit.render(fichas[ent][0], True, (240, 240, 240)), (det.x + 14, yy)); yy += 44
        for linea in fichas[ent][1]:
            for parte in _ajustar(linea, f_t, det.w - 28):
                pantalla.blit(f_t.render(parte, True, (230, 230, 230)), (det.x + 14, yy)); yy += 28
            yy += 8
        pie = f_p.render("Izq/Der: sección   Arriba/Abajo: ficha   Esc o N: cerrar", True, (190, 170, 220))
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
    fondo = pygame.Surface((w, h))
    for y in range(h):
        t = y / h
        pygame.draw.line(fondo, (int(15 + 60 * t), int(40 - 10 * t), int(25 + 20 * t)), (0, y), (w, y))
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

def menu_principal(pantalla, fuente):
    # Pantalla de titulo. Devuelve True para jugar, False para salir.
    f_tit = pygame.font.Font(None, 72)
    f_sub = pygame.font.Font(None, 30)
    f_op = pygame.font.Font(None, 32)
    opciones = ["Jugar", "Campaña", "Centro de Análisis", "Cuaderno de Guardianes",
                "Salón de Guardianes", "Tienda (bloqueada)", "Próximamente", "Cómo jugar", "Salir"]
    ayuda_txt = [
        "Eres el bombero forestal de los Bosques de Yacuiba.",
        "Clic izquierdo: cortafuegos (frena el avance del fuego).",
        "Clic derecho: mochila de agua (apaga una celda en llamas).",
        "El fuego avanza solo. P: pausa  |  Enter: adelantar el fuego (depuración).",
        "Retroceso: deshacer la última acción  |  R: reiniciar.",
        "Bombero: flechas.  Veterinaria: W A S D.  El modo se elige al pulsar Jugar.",
        "Veterinaria: E recoge o suelta un animal. Llévalos al refugio (zona verde).",
        "Meta: apagar el incendio y conservar el mayor bosque posible.",
        "M: silenciar o activar la música.  |  N: Cuaderno de Guardianes (pausa).",
        "Bombero: G manguera, T torre.  Veterinaria: Z botiquín, X rastreo, Q señal de auxilio.",
        "",
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

    def centrado(texto, fnt, col, y):
        s = fnt.render(texto, True, col)
        pantalla.blit(s, s.get_rect(center=(w // 2, y)))

    while True:
        accion = None
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
                    sel = (sel - 1) % len(opciones)
                elif e.key == pygame.K_DOWN:
                    sel = (sel + 1) % len(opciones)
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    accion = sel
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos):
                        sel = i
                        accion = i
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
                    return True
        if accion is not None:
            op = opciones[accion]
            if op == "Cómo jugar":
                ayuda = True
            elif op == "Salir":
                return False
            elif op == "Salón de Guardianes":
                if pantalla_maqueta(pantalla, "Salón de Guardianes", lineas_salon(), "TUS MEJORES RESULTADOS") == "salir":
                    return False
            elif op == "Cuaderno de Guardianes":
                if cuaderno(pantalla, fuente) == "salir":
                    return False
            elif op in MAQUETAS:
                titulo_m, lineas_m = MAQUETAS[op]
                if pantalla_maqueta(pantalla, titulo_m, lineas_m) == "salir":
                    return False

        pantalla.blit(fondo, (0, 0))
        centrado("GUARDIANES DEL CHACO", f_tit, (255, 170, 60), 60)
        centrado("Gran Chaco boliviano - Tarija", f_sub, (230, 230, 230), 105)
        if ayuda:
            for k, linea in enumerate(ayuda_txt):
                centrado(linea, fuente, (240, 240, 240), 160 + k * 34)
        else:
            for i, r in enumerate(rects):
                pygame.draw.rect(pantalla, (255, 87, 34) if i == sel else (60, 60, 60), r, border_radius=8)
                centrado(opciones[i], f_op, (140, 140, 140) if "bloqueada" in opciones[i] else (255, 255, 255), r.centery)
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

TANQUE = 6                  # cargas de agua del bombero
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
    est["agua"] = min(TANQUE, est["agua"] + 2)
    est["vida"]["b"] = min(VIDA_MAX, est["vida"]["b"] + 15)
    est["t_apoyo"] = ahora
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

def dibujar_globo(pantalla, est, fnt):
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
    px_, py_ = cx * CELDA + CELDA // 2, cy * CELDA
    lim = est["n"] * CELDA
    x = max(4, min(lim - ancho - 4, px_ - ancho // 2))
    y = py_ - alto - 14
    abajo = y < 4
    if abajo:
        y = py_ + CELDA + 14
    y = max(4, min(y, lim - alto - 4))
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

def cuadro_grande(pantalla, paginas, fuente):
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
                i += 1
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                i += 1
        if i >= len(paginas):
            break
        quien, texto = paginas[i]
        pantalla.blit(fondo, (0, 0))
        caja = pygame.Rect(30, h - 220, w - 60, 175)
        pygame.draw.rect(pantalla, (45, 25, 70), caja, border_radius=8)
        pygame.draw.rect(pantalla, (200, 180, 240), caja, 3, border_radius=8)
        pygame.draw.rect(pantalla, (120, 95, 170), caja.inflate(-14, -14), 1, border_radius=6)
        tx = caja.x + 24
        if quien:
            es_b = quien == "b"
            ret = pygame.Rect(caja.x + 24, caja.y + 26, 96, 96)
            pygame.draw.rect(pantalla, (30, 16, 50), ret, border_radius=6)
            pygame.draw.rect(pantalla, (255, 170, 60) if es_b else (120, 220, 255), ret, 3, border_radius=6)
            ini = pygame.font.Font(None, 80).render("B" if es_b else "V", True,
                                                    (255, 170, 60) if es_b else (120, 220, 255))
            pantalla.blit(ini, ini.get_rect(center=ret.center))
            nom = f_n.render("Bombero" if es_b else "Veterinaria", True,
                             (255, 170, 60) if es_b else (120, 220, 255))
            pantalla.blit(nom, (ret.right + 20, caja.y + 18))
            tx = ret.right + 20
            ty = caja.y + 50
        else:
            ty = caja.y + 26
        for k, l in enumerate(_ajustar(texto, f_t, caja.right - tx - 24)):
            pantalla.blit(f_t.render(l, True, (240, 240, 240)), (tx, ty + 28 * k))
        pie = f_p.render(f"Enter: continuar  ({i + 1}/{len(paginas)})", True, (190, 170, 220))
        pantalla.blit(pie, (caja.right - pie.get_width() - 22, caja.bottom - 30))
        pygame.display.flip()
        reloj.tick(30)

def intro_nivel(pantalla, fuente, est):
    niv = nivel_actual()
    b, v = INICIO_TXT[niv["id"]]
    pag = [(None, f"{niv['nombre']}. Apaga el incendio, lleva los {niv['animales']} animales al refugio y conserva el bosque."),
           ("b", b)]
    if v:
        pag.append(("v", v))
    cuadro_grande(pantalla, pag, fuente)
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
        cuadro_grande(pantalla, paginas_final(est), fuente)
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

def estado_hab(est, clave, cd):
    resto = cd - (pygame.time.get_ticks() - est.get(clave, -99999))
    return "listo" if resto <= 0 else f"{resto / 1000:.1f}s"

def _marcar(est, celdas, color, dur):
    fin = pygame.time.get_ticks() + dur
    est.setdefault("marcas", []).extend((x, y, color, fin) for x, y in celdas)

def habilidad(est, tecla):
    """G manguera, T torre (bombero); Z botiquin, X rastreo, Q senal de auxilio (veterinaria)."""
    if est.get("ver_eval") or est.get("derrota"):
        return
    ahora = pygame.time.get_ticks()
    n, estado = est["n"], est["estado"]
    ia = est.get("ia_rol")
    es_b = tecla in (pygame.K_g, pygame.K_t)
    if (es_b and ia == "bombero") or (not es_b and ia == "veterinaria"):
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
        est["msg"] = f"Manguera: {len(cand)} focos apuntados"
    elif tecla == pygame.K_t:
        if estado_hab(est, "t_torre", CD_TORRE_MS) != "listo":
            est["msg"] = "Torre en recuperación"; return
        fuegos = [(i % n, i // n) for i, v in enumerate(estado) if v == 2
                  and (i % n - bx) ** 2 + (i // n - by) ** 2 <= TORRE_R ** 2]
        est["t_torre"] = ahora
        _marcar(est, fuegos, (255, 140, 0), 5000)
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
        est["msg"] = "Botiquín: animal atendido"
    elif tecla == pygame.K_x:
        if estado_hab(est, "t_rastreo", CD_RASTREO_MS) != "listo":
            est["msg"] = "Rastreo en recuperación"; return
        pos = [(a[0], a[1]) for a in est["animales"] if a[2] != "salvo"
               and (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= RASTREO_R ** 2]
        est["t_rastreo"] = ahora
        _marcar(est, pos, (80, 220, 255), 6000)
        est["msg"] = f"Rastreo: {len(pos)} animales cerca"
    elif tecla == pygame.K_q:
        if estado_hab(est, "t_senal", CD_SENAL_MS) != "listo":
            est["msg"] = "Señal de auxilio en recuperación"; return
        sts = estados_fauna(est)
        pos = [(a[0], a[1]) for a, st in zip(est["animales"], sts) if st == "aislado"]
        est["t_senal"] = ahora
        _marcar(est, pos, (255, 230, 60), 6000)
        est["msg"] = f"Señal de auxilio: {len(pos)} animales aislados marcados" if pos else "Señal de auxilio: sin animales aislados"

def dibujar_habilidades(pantalla, est, fnt):
    """Anillos de las habilidades y alerta de zona prioritaria (refugio)."""
    import math
    ahora = pygame.time.get_ticks()
    est["marcas"] = [m for m in est.get("marcas", []) if m[3] > ahora]
    r = CELDA + 2 + int(2 * abs(math.sin(ahora / 200)))
    for x, y, col, _ in est["marcas"]:
        pygame.draw.circle(pantalla, col, (x * CELDA + CELDA // 2, y * CELDA + CELDA // 2), r, 2)
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
        caja = s.get_rect(center=(est["n"] * CELDA // 2, 18)).inflate(16, 8)
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

def evaluar(est):
    salvos = sum(1 for a in est["animales"] if a[2] == "salvo")
    total = len(est["animales"])
    bosque = est["estado"].count(1) * 100 // est["veg0"]
    frac = 0.5 * salvos / max(1, total) + 0.5 * bosque / 100
    estrellas = 3 if frac >= 0.75 else 2 if frac >= 0.5 else 1
    puntos = salvos * 100 + bosque * 5 + estrellas * 50
    return dict(salvos=salvos, total=total, bosque=bosque, estrellas=estrellas,
                puntos=puntos, ronda=est["ronda"], focos=est["estado"].count(2),
                titulo=("MISION CUMPLIDA" if salvos >= META_SALVOS and bosque >= META_BOSQUE
                        else "MISION FALLIDA: meta no alcanzada"))

def ia_veterinaria(est, ahora):
    """IA basica de la veterinaria: camino mas corto (BFS) al animal libre mas cercano,
    lo recoge y lo lleva al refugio. Esquiva agua y celdas en llamas."""
    from collections import deque
    if est["ver_eval"] or est["tick"]["pausa"] or ahora - est.get("t_movv", 0) < 160:
        return
    est["t_movv"] = ahora
    if est["agua"] <= 2 or est["vida"]["b"] < 60:
        apoyo(est, ahora, avisar=False)
    n, estado = est["n"], est["estado"]
    vx, vy = est["vx"], est["vy"]
    if est["carga"] is None:
        libres = [a for a in est["animales"] if a[2] == "libre"]
        for a in libres:
            if (a[0] - vx) ** 2 + (a[1] - vy) ** 2 <= 4:
                a[2] = "cargado"; est["carga"] = a
                est["msg"] = "La IA recogio un animal"
                return
        metas = {(a[0] + dx, a[1] + dy) for a in libres for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    else:
        rx, ry, rw, rh = est["refugio"]
        metas = {(x, y) for x in range(rx, rx + rw) for y in range(ry, ry + rh)}
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
    fuegos.sort(key=lambda f: (f[0] - bx) ** 2 + (f[1] - by) ** 2)
    if est["agua"] <= 0:
        est["ia_rec"] = True
    elif est["agua"] >= TANQUE:
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

def actualizar_emergencia(est):
    veg = est["estado"].count(1)
    quem = est["estado"].count(2)
    perdida = 100 - veg * 100 // est["veg0"]
    _prev = est.get("nivel")
    est["nivel"] = "inicial" if perdida < 15 else "avanzada" if perdida < 35 else "critica"
    if est["nivel"] != _prev and "dlg" in est:
        if est["nivel"] == "avanzada":
            decir(est, "b", "Se está extendiendo. Hay que priorizar los focos.", "importante", "avanzada")
        elif est["nivel"] == "critica":
            decir(est, "b", "Ok, ahora sí se puso serio. Todos a lo suyo.", "critico", "critica")
    if est["nivel"] == "critica":
        if est["cuenta"] is None:
            est["cuenta"] = CUENTA_RONDAS
        else:
            est["cuenta"] -= 1
    if quem == 0 or (est["cuenta"] is not None and est["cuenta"] <= 0 and est["evaluacion"] is None):
        est["evaluacion"] = evaluar(est); est["final_pend"] = True
        est["ver_eval"] = True

AJUSTES_RUTA = os.path.join("output", "ajustes.json")
AJ = {"vol": 0.5, "mute": False, "t": -10000, "snd": {}, "f": None}
BASE_VOL = {"musica": 0.35}   # volumen base de cada sonido; los efectos usan 1.0


def aplicar_volumen():
    for k, s in AJ["snd"].items():
        try:
            s.set_volume(0.0 if AJ["mute"] else AJ["vol"] * BASE_VOL.get(k, 1.0))
        except Exception:
            pass


def cargar_ajustes():
    import json as _j
    try:
        with open(AJUSTES_RUTA, encoding="utf-8") as f:
            d = _j.load(f)
        AJ["vol"] = max(0.0, min(1.0, float(d.get("vol", 0.5))))
        AJ["mute"] = bool(d.get("mute", False))
    except Exception:
        pass


def guardar_ajustes():
    import json as _j
    try:
        os.makedirs("output", exist_ok=True)
        with open(AJUSTES_RUTA, "w", encoding="utf-8") as f:
            _j.dump({"vol": AJ["vol"], "mute": AJ["mute"]}, f)
    except Exception:
        pass


def cambiar_volumen(delta):
    AJ["vol"] = round(max(0.0, min(1.0, AJ["vol"] + delta)), 2)
    AJ["mute"] = False
    AJ["t"] = pygame.time.get_ticks()
    aplicar_volumen()
    guardar_ajustes()


def dibujar_barra_volumen(pantalla, x, y, ancho=150):
    if AJ["f"] is None:
        AJ["f"] = pygame.font.Font(None, 20)
    pygame.draw.rect(pantalla, (20, 24, 28), (x - 6, y - 4, ancho + 12, 40), border_radius=6)
    txt = "Silenciado" if AJ["mute"] else "Volumen " + str(int(round(AJ["vol"] * 100))) + "%"
    pantalla.blit(AJ["f"].render(txt, True, (235, 235, 235)), (x, y))
    pygame.draw.rect(pantalla, (70, 70, 70), (x, y + 20, ancho, 8), border_radius=4)
    if not AJ["mute"]:
        pygame.draw.rect(pantalla, (120, 255, 160), (x, y + 20, int(ancho * AJ["vol"]), 8), border_radius=4)


def main():
    global CELDA
    os.makedirs("output", exist_ok=True)
    asegurar_motor()
    pygame.init()
    if os.environ.get("CELDA"):
        CELDA = max(3, min(8, int(os.environ["CELDA"])))
    else:   # ajusta el tamano de celda a la altura de la pantalla
        ALTO_PANT["h"] = pygame.display.Info().current_h; CELDA = max(5, min(6, (ALTO_PANT["h"] - 110) // nivel_actual()["n"]))
    sonidos = {}
    try:   # si no hay audio, el juego sigue sin sonido
        pygame.mixer.init()
        sonidos["CORTAFUEGO"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "cortafuegos.wav"))
        sonidos["APAGAR"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "agua.wav"))
        musica = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "musica.wav"))
        cargar_ajustes()
        musica.play(loops=-1)
        sonidos["musica"] = musica
        AJ["snd"] = sonidos
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
        shutil.copy(f"data/maps/map_{nivel_actual()['n']}.bin", MAPA_JUEGO)
        os.chmod(MAPA_JUEGO, 0o666)   # el contenedor (mpiuser) debe poder reescribirlo
        n, estado, fuel = leer_mapa(MAPA_JUEGO)
        est.update(n=n, estado=estado, fuel=fuel, paso=0, ronda=0, pend=[], msg="",
                   veg0=max(1, estado.count(1)))
        est["bx"], est["by"] = posicion_inicial(n, estado)
        est["refugio"] = (4, n - 14, 10, 10)
        est["vx"], est["vy"] = 4 + 5, n - 14 + 5
        est["animales"] = crear_animales(n, estado, est["refugio"], nivel_actual()["animales"])
        est["carga"] = None
        est["riesgo"] = None; est["ver_riesgo"] = False; est["info_vigia"] = []
        est.update(nivel="inicial", cuenta=None, evaluacion=None, ver_eval=False)
        est["tick"] = dict(hilo=None, res=None, t_fin=pygame.time.get_ticks(), pausa=False)
        est["vida"] = {"b": VIDA_MAX, "v": VIDA_MAX}
        est["derrota"] = False; est["t_dano"] = 0
        est["agua"] = TANQUE; est["t_cf"] = -99999; est["t_rec"] = 0; est["t_apoyo"] = -99999
        est["dlg"] = nuevo_dialogo(); est["salon_ok"] = False
        est["marcas"] = []; est["tratados"] = set(); est["alerta_ref"] = False; est["t_dref"] = -99999
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
        estado, fuel = est["estado"], est["fuel"]
        for i in range(n):
            for j in range(n):
                s = estado[i * n + j]
                var = (i * 7 + j * 13) % 4
                if s == 1:
                    t = T["veg"][min(2, fuel[i * n + j] // 86)][var]
                else:
                    t = T[s][var]
                    if s == 2:
                        fuego.append((j, i))
                sup.blit(t, (j * CELDA, i * CELDA))
        est["sup"] = sup
        est["fuego"] = fuego

    reiniciar()
    n = est["n"]
    pantalla = pygame.display.set_mode((n * CELDA + PANEL_W, n * CELDA + 56))
    ok_menu = menu_principal(pantalla, fuente)
    if ok_menu:
        niv = nivel_actual()
        asegurar_motor(niv)
        if not os.environ.get("CELDA"):
            CELDA = max(5, min(6, (ALTO_PANT["h"] - 110) // niv["n"]))
        reiniciar()
        n = est["n"]
        pantalla = pygame.display.set_mode((n * CELDA + PANEL_W, n * CELDA + 56))
        pygame.display.set_caption("Guardianes del Chaco - " + niv["nombre"])
    if ok_menu:
        intro_nivel(pantalla, fuente, est)
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
                                est["msg"] = "Animal en brazos: llévalo al refugio"
                                break
                    else:
                        est["carga"][2] = "libre"
                        est["carga"][0], est["carga"][1] = est["vx"], est["vy"]
                        est["carga"] = None
                elif e.key == pygame.K_v:
                    if est.get("riesgo") is not None:
                        est["ver_riesgo"] = not est["ver_riesgo"]
                    else:
                        pygame.draw.rect(pantalla, (30, 34, 40), (n * CELDA, 0, PANEL_W, n * CELDA + 56))
                        pantalla.blit(fuente.render("Vigia calculando...", True, (255, 220, 100)),
                                      (n * CELDA + 10, 10))
                        pygame.display.flip()
                        try:
                            est["riesgo"], est["info_vigia"] = calcular_vigia(n)
                            est["ver_riesgo"] = True
                            est["msg"] = ""
                        except Exception as ex:
                            est["msg"] = "Error del Vigia: " + str(ex)
                elif e.key == pygame.K_c:
                    if not est["derrota"]:
                        est["ver_eval"] = False
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
                        est["agua"] = min(TANQUE, est["agua"] + 1)
                elif e.key == pygame.K_f:
                    apoyo(est, pygame.time.get_ticks())
                elif e.key == pygame.K_F9:
                    ciclo = ["veterinaria", "bombero", None]
                    est["ia_rol"] = ciclo[(ciclo.index(est.get("ia_rol", "veterinaria")) + 1) % 3]
                    est["msg"] = ("IA controla: " + est["ia_rol"]) if est["ia_rol"] else "Sin IA: dos jugadores"
                elif e.key in (pygame.K_g, pygame.K_t, pygame.K_z, pygame.K_x, pygame.K_q):
                    habilidad(est, e.key)
                elif e.key == pygame.K_n:
                    pausa_prev_ = est["tick"]["pausa"]
                    est["tick"]["pausa"] = True
                    cuaderno(pantalla, fuente)
                    est["tick"]["pausa"] = pausa_prev_
                    est["tick"]["t_fin"] = pygame.time.get_ticks()
                elif e.key == pygame.K_p:
                    est["tick"]["pausa"] = not est["tick"]["pausa"]
                    est["msg"] = "PAUSA (P para continuar)" if est["tick"]["pausa"] else ""
                elif e.key == pygame.K_RETURN:
                    est["tick"]["t_fin"] = 0     # depuracion: adelanta el siguiente tick
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
                mx, my = e.pos
                if my < n * CELDA and mx < n * CELDA:
                    tipo = "CORTAFUEGO" if e.button == 1 else "APAGAR"
                    cx, cy = mx // CELDA, my // CELDA
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
                nsalvos = sum(1 for a in est["animales"] if a[2] == "salvo")
                est["carga"][0] = rx + 1 + ((nsalvos - 1) % 5) * 2
                est["carga"][1] = ry + 2 + ((nsalvos - 1) // 5) * 2
                est["carga"] = None
                est["msg"] = "Animal a salvo" if nsalvos < len(est["animales"]) else "¡Todos los animales a salvo!"
                decir(est, "v", "Uno menos en peligro. Lástima que el resto no lea instrucciones." if nsalvos < len(est["animales"]) else "Todos a salvo. Esta vez no hizo falta el sarcasmo.", "importante", "salvo")

        if not est["ver_eval"] and not est["tick"]["pausa"] and est["agua"] < TANQUE and ahora - est["t_rec"] >= RECARGA_MS:
            bx2, by2 = est["bx"], est["by"]
            if any(0 <= bx2 + dx < n and 0 <= by2 + dy < n and est["estado"][(by2 + dy) * n + bx2 + dx] == 5
                   for dy in range(-RIO_DIST, RIO_DIST + 1) for dx in range(-RIO_DIST, RIO_DIST + 1)):
                est["agua"] += 1; est["t_rec"] = ahora
        if not est["ver_eval"] and not est["tick"]["pausa"] and ahora - est["t_dano"] >= 600:
            est["t_dano"] = ahora
            rx0, ry0, rw0, rh0 = est["refugio"]
            for k_, (cx_, cy_) in (("b", (est["bx"], est["by"])), ("v", (est["vx"], est["vy"]))):
                if est["estado"][cy_ * n + cx_] == 2:
                    est["vida"][k_] = max(0, est["vida"][k_] - DANO_LLAMAS); _aviso_vida(est, k_)
                elif rx0 <= cx_ < rx0 + rw0 and ry0 <= cy_ < ry0 + rh0:
                    est["vida"][k_] = min(VIDA_MAX, est["vida"][k_] + CURA_REFUGIO)
            if (est["vida"]["b"] <= 0 or est["vida"]["v"] <= 0) and not est["derrota"]:
                quien = "El bombero" if est["vida"]["b"] <= 0 else "La veterinaria"
                ev = evaluar(est)
                ev["titulo"] = "MISION FALLIDA: " + quien + " cayo"
                ev["estrellas"] = 0
                est["evaluacion"] = ev; est["ver_eval"] = True; est["derrota"] = True; est["final_pend"] = True
        pantalla.fill((20, 20, 20))
        pantalla.blit(est["sup"], (0, 0))
        cuadro = pygame.time.get_ticks() // 140
        llamas = obtener_tiles()["fuego"]
        for x, y in est["fuego"]:
            pantalla.blit(llamas[(cuadro + x + y) % 3], (x * CELDA, y * CELDA))
        if est.get("ver_riesgo") and est.get("riesgo") is not None:
            pantalla.blit(est["riesgo"], (0, 0))
        rx, ry, rw, rh = est["refugio"]
        zona = pygame.Surface((rw * CELDA, rh * CELDA), pygame.SRCALPHA)
        zona.fill((80, 200, 120, 80))
        pantalla.blit(zona, (rx * CELDA, ry * CELDA))
        pygame.draw.rect(pantalla, (120, 255, 160), (rx * CELDA, ry * CELDA, rw * CELDA, rh * CELDA), 2)
        pantalla.blit(fuente.render("Refugio", True, (255, 255, 255)), (rx * CELDA, ry * CELDA - 18))
        sa = sprite_generico("animal", SPRITE_ANIMAL, PALETA_ANIMAL)
        for (ax, ay, ea, esp), sfa in zip(est["animales"], estados_fauna(est)):
            pantalla.blit(sa, (ax * CELDA + CELDA // 2 - sa.get_width() // 2, ay * CELDA + CELDA - sa.get_height()))
            col_anillo = {"asustado": (255, 230, 60), "aislado": (255, 140, 0), "herido": (255, 40, 40)}.get(sfa)
            if col_anillo:
                pygame.draw.circle(pantalla, col_anillo, (ax * CELDA + CELDA // 2, ay * CELDA + CELDA // 2), 16, 3)
            ini, col_e = ESP_INFO[esp]
            t_e = fuente.render(ini, True, col_e)
            pos_e = (ax * CELDA + CELDA // 2 - t_e.get_width() // 2, ay * CELDA + CELDA - sa.get_height() - t_e.get_height())
            pantalla.fill((0, 0, 0), t_e.get_rect(topleft=pos_e))
            pantalla.blit(t_e, pos_e)
            if ea == "libre" and est["estado"][ay * n + ax] == 2:
                pygame.draw.circle(pantalla, (255, 40, 40), (ax * CELDA + CELDA // 2, ay * CELDA + CELDA // 2), 12, 2)
        pygame.draw.circle(pantalla, (255, 255, 255),
                           (est["bx"] * CELDA + CELDA // 2, est["by"] * CELDA + CELDA // 2),
                           ALCANCE * CELDA, 1)
        sb = sprite_bombero()
        pantalla.blit(sb, (est["bx"] * CELDA + CELDA // 2 - sb.get_width() // 2,
                           est["by"] * CELDA + CELDA - sb.get_height()))
        sv = sprite_generico("vet", SPRITE_VET, PALETA_VET)
        pantalla.blit(sv, (est["vx"] * CELDA + CELDA // 2 - sv.get_width() // 2,
                           est["vy"] * CELDA + CELDA - sv.get_height()))
        salvos = sum(1 for a in est["animales"] if a[2] == "salvo")
        for k_, (cx_, cy_) in (("b", (est["bx"], est["by"])), ("v", (est["vx"], est["vy"]))):
            frac_ = est["vida"][k_] / VIDA_MAX
            bx_, by_ = cx_ * CELDA + CELDA // 2 - 14, cy_ * CELDA - 22
            pygame.draw.rect(pantalla, (40, 0, 0), (bx_, by_, 28, 4))
            pygame.draw.rect(pantalla, (255, 60, 60) if frac_ < 0.35 else (80, 220, 90), (bx_, by_, int(28 * frac_), 4))
        txt_v = fuente.render(f"Vida  Bombero {est['vida']['b']}  Veterinaria {est['vida']['v']}", True, (255, 255, 255))
        pantalla.fill((0, 0, 0), txt_v.get_rect(topleft=(6, 24)))
        pantalla.blit(txt_v, (6, 24))
        txt_m = fuente.render(f"Meta: {META_SALVOS} animales y {META_BOSQUE}% bosque", True, (255, 230, 120))
        pantalla.fill((0, 0, 0), txt_m.get_rect(topleft=(6, 44)))
        pantalla.blit(txt_m, (6, 44))
        txt_a = fuente.render(f"Animales a salvo: {salvos}/{len(est['animales'])}", True, (255, 255, 255))
        pantalla.fill((0, 0, 0), txt_a.get_rect(topleft=(6, 4)))
        pantalla.blit(txt_a, (6, 4))
        for tipo, x, y in est["pend"]:   # acciones pendientes de la ronda
            col = (255, 255, 255) if tipo == "CORTAFUEGO" else (0, 255, 255)
            pygame.draw.rect(pantalla, col, (x * CELDA, y * CELDA, CELDA, CELDA), 2)
        quemando, veg = est["estado"].count(2), est["estado"].count(1)
        linea1 = (f"Ronda {est['ronda']}  Paso {est['paso']}  En llamas {quemando}  "
                  f"Bosque {veg * 100 // est['veg0']}%  Agua {est['agua']}/{TANQUE}  "
                  f"Cortafuego {estado_cortafuego(est)}")
        eventos_periodicos(est, pantalla, fuente)
        dibujar_habilidades(pantalla, est, fuente_p)
        dibujar_globo(pantalla, est, fuente_p)
        if est["msg"]:
            linea2 = est["msg"]
        elif quemando == 0:
            linea2 = f"Incendio controlado. Bosque conservado: {veg * 100 // est['veg0']}%  (R = reiniciar)"
        else:
            linea2 = "Izq: cortafuegos | Der: agua | P: pausa | Retroceso: deshacer | R: reiniciar"
        pantalla.blit(fuente.render(linea1, True, (255, 255, 255)), (10, n * CELDA + 6))
        pantalla.blit(fuente.render(linea2, True, (200, 200, 200)), (10, n * CELDA + 30))
        pygame.draw.rect(pantalla, (30, 34, 40), (n * CELDA, 0, PANEL_W, n * CELDA + 56))
        px = n * CELDA + 10
        pantalla.blit(fuente.render("EL VIGIA", True, (255, 255, 255)), (px, 10))
        if pygame.time.get_ticks() - AJ["t"] < 2500:
            dibujar_barra_volumen(pantalla, n * CELDA - 170, 6)
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
        pantalla.blit(fuente_p.render("EMERGENCIA: " + est["nivel"].upper(), True, col_n), (px, py))
        if est["cuenta"] is not None:
            pantalla.blit(fuente_p.render("Cuenta regresiva: " + str(max(0, est["cuenta"]) * TICK_MS["critica"] // 1000) + " s",
                                          True, (255, 120, 120)), (px, py + 20))
        py += 50
        ua = sum(1 for t, _, _ in est["pend"] if t == "APAGAR")
        uc = sum(1 for t, _, _ in est["pend"] if t == "CORTAFUEGO")
        bloques = [
            ("BOMBERO" + (" (IA)" if est.get("ia_rol", "veterinaria") == "bombero" else ""), [("Mochila de agua (clic der.) " + str(est["agua"]) + "/" + str(TANQUE), True),
                         ("Cortafuegos (clic izq.) " + estado_cortafuego(est), True),
                         ("Manguera de presion (G) " + estado_hab(est, "t_mang", CD_MANGUERA_MS), True),
                         ("Proteccion termica (proximamente)", False),
                         ("Torre de vigilancia (T) " + estado_hab(est, "t_torre", CD_TORRE_MS), True)]),
            ("VETERINARIA" + (" (IA)" if est.get("ia_rol", "veterinaria") == "veterinaria" else ""), [("Rescate (E)", True),
                             ("Apoyo al bombero (F) " + estado_apoyo(est), True),
                             ("Botiquin (Z) " + estado_hab(est, "t_boti", CD_BOTIQUIN_MS), True),
                             ("Rastreo animal (X) " + estado_hab(est, "t_rastreo", CD_RASTREO_MS), True),
                             ("Senal de auxilio (Q) " + estado_hab(est, "t_senal", CD_SENAL_MS), True),
                             ("Conocimiento silvestre (proximamente)", False)]),
        ]
        for titulo, habs in bloques:
            pantalla.blit(fuente_p.render(titulo, True, (255, 255, 255)), (px, py)); py += 20
            for nombre, activa in habs:
                c = (230, 230, 230) if activa else (110, 110, 110)
                pantalla.blit(fuente_p.render(("[x] " if activa else "[ ] ") + nombre, True, c), (px, py)); py += 18
            py += 10
        pantalla.blit(fuente_p.render("FAUNA", True, (255, 255, 255)), (px, py)); py += 20
        for i_a, (a, st) in enumerate(zip(est["animales"], estados_fauna(est))):
            if i_a in est.get("tratados", ()) and st in ("herido", "aislado", "asustado"):
                st = "atendido"
            pantalla.blit(fuente_p.render(a[3].capitalize() + ": " + st, True, ESP_INFO[a[3]][1]), (px, py)); py += 18
        if est.get("ver_eval") and est.get("evaluacion"):
            ev = est["evaluacion"]
            pygame.draw.rect(pantalla, (15, 20, 25), (60, 120, 440, 250))
            pygame.draw.rect(pantalla, (255, 220, 100), (60, 120, 440, 250), 2)
            lineas = [ev.get("titulo", "EVALUACION DE LA MISION"),
                      "Estrellas: " + "*" * ev["estrellas"] + "-" * (3 - ev["estrellas"]),
                      "Animales rescatados: " + str(ev["salvos"]) + "/" + str(ev["total"]),
                      "Bosque conservado: " + str(ev["bosque"]) + "%",
                      "Focos activos: " + str(ev["focos"]),
                      "Rondas usadas: " + str(ev["ronda"]),
                      "Puntuacion: " + str(ev["puntos"]),
                      "C = continuar   R = reiniciar"]
            for k, t in enumerate(lineas):
                pantalla.blit(fuente.render(t, True, (255, 220, 100) if k == 0 else (235, 235, 235)),
                              (80, 135 + 28 * k))
        pygame.display.flip()
        reloj.tick(30)
    pygame.quit()

if __name__ == "__main__":
    main()
