#!/usr/bin/env python3
"""Guardianes del Chaco - visor minimo (nivel Bosques de Yacuiba, malla 128x128).
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
MAPA_BASE = "data/maps/map_128.bin"
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


def asegurar_motor():
    """Compila fire_seq y genera el mapa 128x128 dentro del contenedor si faltan."""
    orden = ("cd /home/mpiuser/proyecto && mkdir -p bin data/maps output && "
             "{ [ -x bin/fire_seq ] || g++ -std=c++17 -O2 -I src/common src/sequential/fire_seq.cpp -o bin/fire_seq; } && "
             "{ [ -f data/maps/map_128.bin ] || python3 data/gen_map.py --n 128 --seed 42 --out data/maps/map_128.bin; }")
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c", orden],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("No se pudo preparar el motor (clúster arriba? docker compose up -d):\n" + (r.stderr or r.stdout))


def correr_ronda(paso, pendientes):
    with open(ACCIONES, "w") as f:
        for tipo, x, y in pendientes:
            f.write(f"{paso} {tipo} {x} {y}\n")
    orden = (f"cd /home/mpiuser/proyecto && ./bin/fire_seq --mapa {MAPA_JUEGO} --pasos {PASOS_RONDA} "
             f"--semilla {SEMILLA} --paso-inicial {paso} --acciones {ACCIONES} --guardar-mapa {MAPA_JUEGO}")
    r = subprocess.run(["docker", "exec", "-u", "mpiuser", "master", "bash", "-c", orden],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:120])

MODO = {"ia": "veterinaria"}   # quien controla la IA: "veterinaria", "bombero" o None (dos jugadores)

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

def menu_principal(pantalla, fuente):
    # Pantalla de titulo. Devuelve True para jugar, False para salir.
    f_tit = pygame.font.Font(None, 72)
    f_sub = pygame.font.Font(None, 30)
    f_op = pygame.font.Font(None, 44)
    opciones = ["Jugar", "Cómo jugar", "Salir"]
    ayuda_txt = [
        "Eres el bombero forestal de los Bosques de Yacuiba.",
        "Clic izquierdo: cortafuegos (frena el avance del fuego).",
        "Clic derecho: mochila de agua (apaga una celda en llamas).",
        "El fuego avanza solo. P: pausa  |  Enter: adelantar el fuego (depuración).",
        "Retroceso: deshacer la última acción  |  R: reiniciar.",
        "Bombero: flechas.  Veterinaria: W A S D.  El modo se elige al pulsar Jugar.",
        "Veterinaria: E recoge o suelta un animal. Llévalos al refugio (zona verde).",
        "Meta: apagar el incendio y conservar el mayor bosque posible.",
        "M: silenciar o activar la música.",
        "",
        "Pulsa cualquier tecla para volver.",
    ]
    w, h = pantalla.get_size()
    fondo = pygame.Surface((w, h))
    for y in range(h):
        t = y / h
        pygame.draw.line(fondo, (int(15 + 90 * t), int(40 - 10 * t), int(25 - 10 * t)), (0, y), (w, y))
    rects = [pygame.Rect(w // 2 - 130, 330 + i * 70, 260, 52) for i in range(len(opciones))]
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
        if accion == 0:
            m = seleccionar_modo(pantalla, fuente)
            if m == "salir":
                return False
            if m is not None:
                MODO["ia"] = None if m == "dos" else m
                return True
        if accion == 1:
            ayuda = True
        if accion == 2:
            return False

        pantalla.blit(fondo, (0, 0))
        centrado("GUARDIANES DEL CHACO", f_tit, (255, 170, 60), 140)
        centrado("Bosques de Yacuiba - Gran Chaco boliviano", f_sub, (230, 230, 230), 205)
        if ayuda:
            for k, linea in enumerate(ayuda_txt):
                centrado(linea, fuente, (240, 240, 240), 300 + k * 34)
        else:
            for i, r in enumerate(rects):
                pygame.draw.rect(pantalla, (255, 87, 34) if i == sel else (60, 60, 60), r, border_radius=8)
                centrado(opciones[i], f_op, (255, 255, 255), r.centery)
            centrado("Flechas + Enter, o usa el ratón", fuente, (200, 200, 200), h - 40)
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
           f"--map-by node ./bin/vigia_hibrido --mapa {MAPA_JUEGO} --sims {VIGIA_SIMS} "
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


CUENTA_RONDAS = 15                           # ticks de la cuenta regresiva (~30 s en critico)
TICK_MS = {"inicial": 3000, "avanzada": 2500, "critica": 2000}   # ritmo del fuego en tiempo real

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
                puntos=puntos, ronda=est["ronda"], focos=est["estado"].count(2))

def ia_veterinaria(est, ahora):
    """IA basica de la veterinaria: camino mas corto (BFS) al animal libre mas cercano,
    lo recoge y lo lleva al refugio. Esquiva agua y celdas en llamas."""
    from collections import deque
    if est["ver_eval"] or est["tick"]["pausa"] or ahora - est.get("t_movv", 0) < 160:
        return
    est["t_movv"] = ahora
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
    usados = len(pend_apagar)
    for fx, fy in fuegos:
        if usados >= LIMITES["APAGAR"]:
            break
        if (fx - bx) ** 2 + (fy - by) ** 2 <= (ALCANCE - 1) ** 2:
            est["pend"].append(("APAGAR", fx, fy)); usados += 1
    if usados > len(pend_apagar):
        return
    tx, ty = fuegos[0]
    prev = {(bx, by): None}
    cola = deque([(bx, by)])
    meta = None
    while cola:
        c = cola.popleft()
        if (c[0] - tx) ** 2 + (c[1] - ty) ** 2 <= (ALCANCE - 2) ** 2:
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
    est["nivel"] = "inicial" if perdida < 15 else "avanzada" if perdida < 35 else "critica"
    if est["nivel"] == "critica":
        if est["cuenta"] is None:
            est["cuenta"] = CUENTA_RONDAS
        else:
            est["cuenta"] -= 1
    if quem == 0 or (est["cuenta"] is not None and est["cuenta"] <= 0 and est["evaluacion"] is None):
        est["evaluacion"] = evaluar(est)
        est["ver_eval"] = True

def main():
    global CELDA
    os.makedirs("output", exist_ok=True)
    asegurar_motor()
    pygame.init()
    if os.environ.get("CELDA"):
        CELDA = max(3, min(8, int(os.environ["CELDA"])))
    else:   # ajusta el tamano de celda a la altura de la pantalla
        CELDA = max(5, min(6, (pygame.display.Info().current_h - 110) // 128))
    sonidos = {}
    try:   # si no hay audio, el juego sigue sin sonido
        pygame.mixer.init()
        sonidos["CORTAFUEGO"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "cortafuegos.wav"))
        sonidos["APAGAR"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "agua.wav"))
        musica = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "musica.wav"))
        musica.set_volume(0.35)
        musica.play(loops=-1)
        sonidos["musica"] = musica
    except Exception as ex:
        print("Aviso: sin audio (" + str(ex) + ")")
    pygame.display.set_caption("Guardianes del Chaco - Bosques de Yacuiba")
    fuente = pygame.font.Font(None, 24)
    fuente_p = pygame.font.Font(None, 20)
    reloj = pygame.time.Clock()
    est = {}

    def reiniciar():
        h = est.get("tick", {}).get("hilo")
        if h is not None and h.is_alive():
            h.join()
        shutil.copy(MAPA_BASE, MAPA_JUEGO)
        os.chmod(MAPA_JUEGO, 0o666)   # el contenedor (mpiuser) debe poder reescribirlo
        n, estado, fuel = leer_mapa(MAPA_JUEGO)
        est.update(n=n, estado=estado, fuel=fuel, paso=0, ronda=0, pend=[], msg="",
                   veg0=max(1, estado.count(1)))
        est["bx"], est["by"] = posicion_inicial(n, estado)
        est["refugio"] = (4, n - 14, 10, 10)
        est["vx"], est["vy"] = 4 + 5, n - 14 + 5
        est["animales"] = crear_animales(n, estado, est["refugio"])
        est["carga"] = None
        est["riesgo"] = None; est["ver_riesgo"] = False; est["info_vigia"] = []
        est.update(nivel="inicial", cuenta=None, evaluacion=None, ver_eval=False)
        est["tick"] = dict(hilo=None, res=None, t_fin=pygame.time.get_ticks(), pausa=False)
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
    if not menu_principal(pantalla, fuente):
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
                    est["ver_eval"] = False
                elif e.key == pygame.K_r:
                    reiniciar()
                elif e.key == pygame.K_m and "musica" in sonidos:
                    sonidos["musica"].set_volume(0.0 if sonidos["musica"].get_volume() > 0 else 0.35)
                elif e.key == pygame.K_BACKSPACE and est["pend"]:
                    est["pend"].pop()
                elif e.key == pygame.K_F9:
                    ciclo = ["veterinaria", "bombero", None]
                    est["ia_rol"] = ciclo[(ciclo.index(est.get("ia_rol", "veterinaria")) + 1) % 3]
                    est["msg"] = ("IA controla: " + est["ia_rol"]) if est["ia_rol"] else "Sin IA: dos jugadores"
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
                    usados = sum(1 for t, _, _ in est["pend"] if t == tipo)
                    if (cx - est["bx"]) ** 2 + (cy - est["by"]) ** 2 > ALCANCE ** 2:
                        est["msg"] = "Fuera de alcance: acércate con el bombero"
                    elif usados >= LIMITES[tipo]:
                        est["msg"] = "Sin recursos de " + ("agua" if tipo == "APAGAR" else "cortafuegos") + " esta ronda"
                    else:
                        est["msg"] = ""
                        est["pend"].append((tipo, cx, cy))
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
        txt_a = fuente.render(f"Animales a salvo: {salvos}/{len(est['animales'])}", True, (255, 255, 255))
        pantalla.fill((0, 0, 0), txt_a.get_rect(topleft=(6, 4)))
        pantalla.blit(txt_a, (6, 4))
        for tipo, x, y in est["pend"]:   # acciones pendientes de la ronda
            col = (255, 255, 255) if tipo == "CORTAFUEGO" else (0, 255, 255)
            pygame.draw.rect(pantalla, col, (x * CELDA, y * CELDA, CELDA, CELDA), 2)
        quemando, veg = est["estado"].count(2), est["estado"].count(1)
        linea1 = (f"Ronda {est['ronda']}  Paso {est['paso']}  En llamas {quemando}  "
                  f"Bosque {veg * 100 // est['veg0']}%  Agua {sum(1 for t, _, _ in est['pend'] if t == 'APAGAR')}/{LIMITES['APAGAR']}  "
                  f"Cortafuego {sum(1 for t, _, _ in est['pend'] if t == 'CORTAFUEGO')}/{LIMITES['CORTAFUEGO']}")
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
            ("BOMBERO" + (" (IA)" if est.get("ia_rol", "veterinaria") == "bombero" else ""), [("Mochila de agua (clic der.) " + str(ua) + "/" + str(LIMITES["APAGAR"]), True),
                         ("Cortafuegos (clic izq.) " + str(uc) + "/" + str(LIMITES["CORTAFUEGO"]), True),
                         ("Manguera de presion (proximamente)", False),
                         ("Proteccion termica (proximamente)", False),
                         ("Torre de vigilancia (proximamente)", False)]),
            ("VETERINARIA" + (" (IA)" if est.get("ia_rol", "veterinaria") == "veterinaria" else ""), [("Rescate (E)", True),
                             ("Botiquin (proximamente)", False),
                             ("Rastreo animal (proximamente)", False),
                             ("Senal de auxilio (proximamente)", False),
                             ("Conocimiento silvestre (proximamente)", False)]),
        ]
        for titulo, habs in bloques:
            pantalla.blit(fuente_p.render(titulo, True, (255, 255, 255)), (px, py)); py += 20
            for nombre, activa in habs:
                c = (230, 230, 230) if activa else (110, 110, 110)
                pantalla.blit(fuente_p.render(("[x] " if activa else "[ ] ") + nombre, True, c), (px, py)); py += 18
            py += 10
        pantalla.blit(fuente_p.render("FAUNA", True, (255, 255, 255)), (px, py)); py += 20
        for a, st in zip(est["animales"], estados_fauna(est)):
            pantalla.blit(fuente_p.render(a[3].capitalize() + ": " + st, True, ESP_INFO[a[3]][1]), (px, py)); py += 18
        if est.get("ver_eval") and est.get("evaluacion"):
            ev = est["evaluacion"]
            pygame.draw.rect(pantalla, (15, 20, 25), (60, 120, 440, 250))
            pygame.draw.rect(pantalla, (255, 220, 100), (60, 120, 440, 250), 2)
            lineas = ["EVALUACION DE LA MISION",
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
