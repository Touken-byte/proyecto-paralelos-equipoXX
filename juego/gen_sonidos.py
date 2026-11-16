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

def _nota(f0, f1, dur, amp=0.6, atk=0.01, decay=4.0, arm=0.0):
    # Tono con barrido f0->f1, ataque corto y caida exponencial
    n = int(TASA * dur); out = []; fase = 0.0
    for i in range(n):
        t = i / n
        fase += 2 * math.pi * (f0 + (f1 - f0) * t) / TASA
        env = min(1.0, i / (atk * TASA)) * math.exp(-decay * t) * (1 - t ** 8)
        out.append(amp * env * (math.sin(fase) + arm * math.sin(2 * fase)))
    return out

def rescate():
    # Arpegio ascendente corto: animal a salvo
    s = []
    for f in (523.25, 659.25, 783.99):
        s += _nota(f, f, 0.12, 0.5, decay=2.5, arm=0.3)
    return s + _nota(1046.5, 1046.5, 0.4, 0.5, decay=3.0, arm=0.3)

def recompensa():
    # Dos notas brillantes: estrella / objetivo cumplido
    return _nota(880.0, 880.0, 0.12, 0.5, decay=2.0, arm=0.4) + _nota(1318.5, 1318.5, 0.45, 0.5, decay=3.0, arm=0.4)

def derrota():
    # Cuatro notas descendentes y lentas
    s = []
    for f in (392.0, 329.63, 261.63, 196.0):
        s += _nota(f, f, 0.28, 0.5, decay=2.0, arm=0.2)
    return s

def proteccion():
    # Zumbido ascendente con vibrato: proteccion termica
    base = _nota(180.0, 520.0, 0.4, 0.5, decay=1.5, arm=0.5)
    return [v * (0.7 + 0.3 * math.sin(2 * math.pi * 18 * i / TASA)) for i, v in enumerate(base)]

def conocimiento():
    # Ping claro: ficha identificada / cuaderno
    a = _nota(1046.5, 1046.5, 0.35, 0.45, decay=4.0, arm=0.3)
    b = _nota(1568.0, 1568.0, 0.35, 0.25, decay=5.0)
    return [x + y for x, y in zip(a, b)]

def fuego():
    # Loop de 4 s: rumor grave muy tenue + chasquidos agudos y cortos; el final se mezcla con el inicio
    random.seed(7)
    n = int(TASA * 4.0); out = []; grave = 0.0; pop = 0.0; prev_r = 0.0
    for i in range(n):
        r = random.uniform(-1, 1)
        grave += 0.03 * (r - grave)
        brillo = r - prev_r; prev_r = r
        pop *= 0.985
        if random.random() < 0.0009:
            pop = random.random() ** 2 + 0.1
        out.append(grave * 0.5 + brillo * 0.03 + pop * brillo * 0.5)
    f = int(TASA * 0.25)
    for i in range(f):
        a = i / f
        out[i] = out[i] * a + out[n - f + i] * (1 - a)
    out = out[:n - f]
    rms = (sum(v * v for v in out) / len(out)) ** 0.5
    k = 0.025 / rms   # nivel RMS fijo y bajo (ajustable)
    return [max(-1.0, min(1.0, v * k)) for v in out]

def ui_mover():
    return _nota(700.0, 700.0, 0.05, 0.35, decay=6.0)

def ui_aceptar():
    return _nota(520.0, 700.0, 0.07, 0.45, decay=3.0, arm=0.3) + _nota(880.0, 880.0, 0.12, 0.45, decay=4.0, arm=0.3)

def ui_volver():
    return _nota(620.0, 620.0, 0.06, 0.4, decay=4.0) + _nota(420.0, 420.0, 0.1, 0.4, decay=5.0)

def ui_jugar():
    s = []
    for f in (392.0, 523.25, 659.25):
        s += _nota(f, f, 0.08, 0.5, decay=2.5, arm=0.3)
    return s + _nota(783.99, 783.99, 0.3, 0.5, decay=3.0, arm=0.3)

def ui_tienda():
    return _nota(1318.5, 1318.5, 0.06, 0.45, decay=3.0, arm=0.4) + _nota(1760.0, 1760.0, 0.25, 0.45, decay=4.0, arm=0.4)

def ui_salir():
    return _nota(330.0, 220.0, 0.12, 0.5, decay=3.0, arm=0.2) + _nota(220.0, 130.0, 0.28, 0.5, decay=3.0, arm=0.2)

def _silencio(seg):
    return [0.0] * int(TASA * seg)

def pip_recoger():
    return _nota(600.0, 950.0, 0.09, 0.4, decay=4.0, arm=0.2)

def pip_soltar():
    return _nota(520.0, 300.0, 0.12, 0.4, decay=4.0, arm=0.2)

def hab_manguera():
    import random
    random.seed(7)
    n = int(TASA * 0.55); out = []; prev = 0.0
    for i in range(n):
        t = i / n
        prev = 0.6 * prev + 0.4 * random.uniform(-1, 1)
        out.append(0.45 * prev * min(1.0, i / (0.05 * TASA)) * (1 - t ** 3))
    return out

def hab_torre():
    return _nota(1250.0, 1250.0, 0.1, 0.4, decay=3.0) + _silencio(0.06) + _nota(1250.0, 1250.0, 0.28, 0.3, decay=5.0)

def hab_botiquin():
    return _nota(1046.5, 1046.5, 0.09, 0.45, decay=3.0, arm=0.3) + _nota(1568.0, 1568.0, 0.32, 0.45, decay=4.0, arm=0.3)

def hab_rastreo():
    return _nota(900.0, 900.0, 0.07, 0.4, decay=3.0) + _silencio(0.07) + _nota(900.0, 900.0, 0.07, 0.4, decay=3.0)

def hab_senal():
    return _nota(1500.0, 2300.0, 0.4, 0.4, decay=1.5, arm=0.2)

def alerta_avanzada():
    return _nota(660.0, 660.0, 0.16, 0.45, decay=3.0, arm=0.3) + _silencio(0.05) + _nota(784.0, 784.0, 0.22, 0.45, decay=3.5, arm=0.3)

def alerta_critica():
    s = []
    for f in (880.0, 660.0, 880.0, 660.0):
        s += _nota(f, f, 0.13, 0.5, decay=2.5, arm=0.4) + _silencio(0.03)
    return s

def alerta_tic():
    return _nota(900.0, 900.0, 0.05, 0.35, decay=6.0)

def ui_notif():
    return _nota(1318.5, 1318.5, 0.08, 0.3, decay=3.0, arm=0.3) + _nota(1760.0, 1760.0, 0.22, 0.3, decay=4.0, arm=0.3)

def ui_moneda():
    return _nota(1568.0, 1568.0, 0.05, 0.4, decay=3.0, arm=0.5) + _nota(2093.0, 2093.0, 0.05, 0.4, decay=3.0, arm=0.5) + _nota(2637.0, 2637.0, 0.22, 0.4, decay=4.0, arm=0.5)

def amb_viento():
    import random
    random.seed(11)
    N = int(TASA * 6.0); M = int(TASA * 0.4)
    raw = []; prev = 0.0
    for _ in range(N + M):
        prev = 0.96 * prev + 0.04 * random.uniform(-1, 1)
        raw.append(prev)
    out = []
    for i in range(N):
        v = raw[i]
        if i < M:
            a = i / M
            v = raw[i] * a + raw[N + i] * (1 - a)
        mod = 0.65 + 0.35 * math.sin(2 * math.pi * 2 * i / N)
        out.append(max(-1.0, min(1.0, v * mod * 5.0)) * 0.5)
    return out

if __name__ == "__main__":
    os.makedirs("juego/sonidos", exist_ok=True)
    guardar("juego/sonidos/agua.wav", agua())
    guardar("juego/sonidos/cortafuegos.wav", cortafuegos())
    for nom, fn in (("rescate", rescate), ("recompensa", recompensa), ("derrota", derrota),
                    ("proteccion", proteccion), ("conocimiento", conocimiento), ("fuego", fuego),
                    ("ui_mover", ui_mover), ("ui_aceptar", ui_aceptar), ("ui_volver", ui_volver),
                    ("ui_jugar", ui_jugar), ("ui_tienda", ui_tienda), ("ui_salir", ui_salir),
                    ("pip_recoger", pip_recoger), ("pip_soltar", pip_soltar), ("hab_manguera", hab_manguera),
                    ("hab_torre", hab_torre), ("hab_botiquin", hab_botiquin), ("hab_rastreo", hab_rastreo),
                    ("hab_senal", hab_senal), ("alerta_avanzada", alerta_avanzada),
                    ("alerta_critica", alerta_critica), ("alerta_tic", alerta_tic),
                    ("ui_notif", ui_notif), ("ui_moneda", ui_moneda), ("amb_viento", amb_viento)):
        guardar("juego/sonidos/" + nom + ".wav", fn())
    print("OK: sonidos generados en juego/sonidos/")
