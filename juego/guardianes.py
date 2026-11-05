#!/usr/bin/env python3
"""Guardianes del Chaco - visor minimo (nivel Bosques de Yacuiba, malla 128x128).
El fuego lo calcula el motor C++ (fire_seq) dentro del contenedor 'master'.
Este programa solo dibuja y envia las acciones del bombero.
Uso (desde la raiz del repo): python3 juego/guardianes.py
Controles: clic izq = cortafuegos | clic der = mochila de agua | Enter = avanzar ronda
           Retroceso = deshacer ultima accion | R = reiniciar | Esc = salir"""
import os, shutil, struct, subprocess
import pygame

CELDA = 6; PASOS_RONDA = 5; MAX_ACCIONES = 12; SEMILLA = 42
MAPA_BASE = "data/maps/map_128.bin"
DIR_SONIDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonidos")
MAPA_JUEGO = "output/juego_mapa.bin"
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
        "Enter: avanzar una ronda (el motor calcula 5 pasos).",
        "Retroceso: deshacer la última acción  |  R: reiniciar.",
        "Meta: apagar el incendio y conservar el mayor bosque posible.",
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


def main():
    os.makedirs("output", exist_ok=True)
    asegurar_motor()
    pygame.init()
    sonidos = {}
    try:   # si no hay audio, el juego sigue sin sonido
        pygame.mixer.init()
        sonidos["CORTAFUEGO"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "cortafuegos.wav"))
        sonidos["APAGAR"] = pygame.mixer.Sound(os.path.join(DIR_SONIDOS, "agua.wav"))
    except Exception as ex:
        print("Aviso: sin audio (" + str(ex) + ")")
    pygame.display.set_caption("Guardianes del Chaco - Bosques de Yacuiba")
    fuente = pygame.font.Font(None, 24)
    reloj = pygame.time.Clock()
    est = {}

    def reiniciar():
        shutil.copy(MAPA_BASE, MAPA_JUEGO)
        os.chmod(MAPA_JUEGO, 0o666)   # el contenedor (mpiuser) debe poder reescribirlo
        n, estado, fuel = leer_mapa(MAPA_JUEGO)
        est.update(n=n, estado=estado, fuel=fuel, paso=0, ronda=0, pend=[], msg="",
                   veg0=max(1, estado.count(1)))
        redibujar()

    def redibujar():
        n = est["n"]
        sup = pygame.Surface((n, n))
        for i in range(n):
            for j in range(n):
                sup.set_at((j, i), color(est["estado"][i * n + j], est["fuel"][i * n + j]))
        est["sup"] = pygame.transform.scale(sup, (n * CELDA, n * CELDA))

    reiniciar()
    n = est["n"]
    pantalla = pygame.display.set_mode((n * CELDA, n * CELDA + 56))
    if not menu_principal(pantalla, fuente):
        pygame.quit()
        return
    corriendo = True
    while corriendo:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                corriendo = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    corriendo = False
                elif e.key == pygame.K_r:
                    reiniciar()
                elif e.key == pygame.K_BACKSPACE and est["pend"]:
                    est["pend"].pop()
                elif e.key == pygame.K_RETURN:
                    pantalla.blit(fuente.render("Simulando ronda...", True, (255, 255, 255)), (10, n * CELDA + 18))
                    pygame.display.flip()
                    try:
                        correr_ronda(est["paso"], est["pend"])
                        _, est["estado"], est["fuel"] = leer_mapa(MAPA_JUEGO)
                        est["paso"] += PASOS_RONDA; est["ronda"] += 1
                        est["pend"] = []; est["msg"] = ""
                        redibujar()
                    except Exception as ex:
                        est["msg"] = "Error del motor: " + str(ex)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
                mx, my = e.pos
                if my < n * CELDA and len(est["pend"]) < MAX_ACCIONES:
                    tipo = "CORTAFUEGO" if e.button == 1 else "APAGAR"
                    est["pend"].append((tipo, mx // CELDA, my // CELDA))
                    if tipo in sonidos:
                        sonidos[tipo].play()

        pantalla.fill((20, 20, 20))
        pantalla.blit(est["sup"], (0, 0))
        for tipo, x, y in est["pend"]:   # acciones pendientes de la ronda
            col = (255, 255, 255) if tipo == "CORTAFUEGO" else (0, 255, 255)
            pygame.draw.rect(pantalla, col, (x * CELDA, y * CELDA, CELDA, CELDA), 2)
        quemando, veg = est["estado"].count(2), est["estado"].count(1)
        linea1 = (f"Ronda {est['ronda']}  Paso {est['paso']}  En llamas {quemando}  "
                  f"Bosque {veg * 100 // est['veg0']}%  Acciones {len(est['pend'])}/{MAX_ACCIONES}")
        if est["msg"]:
            linea2 = est["msg"]
        elif quemando == 0:
            linea2 = f"Incendio controlado. Bosque conservado: {veg * 100 // est['veg0']}%  (R = reiniciar)"
        else:
            linea2 = "Izq: cortafuegos | Der: agua | Enter: ronda | Retroceso: deshacer | R: reiniciar"
        pantalla.blit(fuente.render(linea1, True, (255, 255, 255)), (10, n * CELDA + 6))
        pantalla.blit(fuente.render(linea2, True, (200, 200, 200)), (10, n * CELDA + 30))
        pygame.display.flip()
        reloj.tick(30)
    pygame.quit()

if __name__ == "__main__":
    main()
