#!/usr/bin/env python3
"""Genera la musica de fondo del visor (loop sintetizado por codigo, sin assets externos).
Uso (desde la raiz del repo): python3 juego/gen_musica.py  ->  juego/sonidos/musica.wav"""
import math, os, random, struct, wave

TASA = 22050
BPM = 70
BEAT = 60.0 / BPM
BEATS = 16
N = int(TASA * BEAT * BEATS)
buf = [0.0] * N

def nota(f, ini, dur, amp, armonico=0.0, suave=False):
    i0 = int(ini * BEAT * TASA)
    m = int(dur * BEAT * TASA)
    for k in range(m):
        t = k / m
        env = math.sin(math.pi * t) ** 2 if suave else min(1.0, k / (0.02 * TASA)) * math.exp(-3.0 * t)
        x = math.sin(2 * math.pi * f * k / TASA) + armonico * math.sin(4 * math.pi * f * k / TASA)
        buf[(i0 + k) % N] += amp * env * x   # el modulo hace que el loop sea continuo

# Progresion Am - F - C - G (4 tiempos cada acorde)
acordes = [(110.00, 130.81, 164.81), (87.31, 110.00, 130.81), (130.81, 164.81, 196.00), (98.00, 123.47, 146.83)]
for c, (raiz, terc, quin) in enumerate(acordes):
    for f in (raiz, terc, quin):
        nota(f, c * 4, 4, 0.10, suave=True)
    nota(raiz, c * 4, 2, 0.12)
    nota(raiz, c * 4 + 2, 2, 0.09)

# Melodia pentatonica de La menor, determinista
penta = [220.00, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25]
rng = random.Random(3)
b = 0.0
while b < BEATS:
    if rng.random() < 0.7:
        ac = acordes[int(b // 4) % 4]
        nota(rng.choice([f * 2 for f in ac] + [f * 4 for f in ac]), b, 1.5, 0.12, armonico=0.3)
    b += 2.0 if rng.random() < 0.6 else 1.0

# Viento: ruido filtrado con swell lento (periodo = duracion del loop)
random.seed(5)
prev = 0.0
for i in range(N):
    prev += 0.02 * (random.uniform(-1, 1) - prev)
    buf[i] += prev * 0.0 * (0.5 + 0.5 * math.sin(2 * math.pi * i / N))

pico = max(abs(x) for x in buf)
os.makedirs("juego/sonidos", exist_ok=True)
with wave.open("juego/sonidos/musica.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(TASA)
    w.writeframes(b"".join(struct.pack("<h", int(x / pico * 0.5 * 32767)) for x in buf))
print("OK: musica generada (%.1f s)" % (N / TASA))
