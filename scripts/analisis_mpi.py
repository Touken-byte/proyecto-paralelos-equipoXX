#!/usr/bin/env python3
"""Analisis de MPI y Vigia hibrido a partir de los CSV que genera benchmark.sh:
promedio de repeticiones, speedup, eficiencia, ajuste de Amdahl y verificacion de checksums.
Uso: python3 scripts/analisis_mpi.py [carpeta_con_los_csv]   (por defecto: output)"""
import collections, csv, os, sys

carpeta = sys.argv[1] if len(sys.argv) > 1 else "output"

def leer(nombre):
    ruta = os.path.join(carpeta, nombre)
    if not os.path.exists(ruta):
        print(f"(no existe {ruta})")
        return []
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def media(v):
    return sum(v) / len(v)

def amdahl(f, p):
    return 1.0 / (f + (1.0 - f) / p)

def gustafson(f, p):
    return p - f * (p - 1)

def ajustar(S):
    return min((i / 1000 for i in range(1001)),
               key=lambda x: sum((S[p] - amdahl(x, p)) ** 2 for p in S))

seq, seq_cs = collections.defaultdict(list), collections.defaultdict(set)
for r in leer("benchmark.csv"):
    if r["modo"] == "seq":
        seq[int(r["n"])].append(float(r["tiempo_s"]))
        seq_cs[int(r["n"])].add(r["checksum"])

mpi, mpi_cs = collections.defaultdict(list), collections.defaultdict(set)
for r in leer("benchmark_mpi.csv"):
    k = (int(r["n"]), int(r["procesos"]))
    mpi[k].append(float(r["tiempo_s"]))
    mpi_cs[k].add(r["checksum"])

for n in sorted({k[0] for k in mpi}):
    if n not in seq:
        continue
    t1 = media(seq[n])
    ps = sorted(p for (nn, p) in mpi if nn == n)
    S = {p: t1 / media(mpi[(n, p)]) for p in ps}
    f = ajustar(S)
    print(f"\n=== MPI, n = {n}  (T_1 secuencial = {t1:.4f} s) ===")
    print(f"{'p':>3} {'reps':>4} {'T_p (s)':>10} {'S_p':>8} {'E_p':>8} {'Amdahl':>8} {'Gustafson':>10}  checksum")
    for p in ps:
        ok = "OK" if mpi_cs[(n, p)] == seq_cs[n] else "DIFERENTE"
        print(f"{p:>3} {len(mpi[(n, p)]):>4} {media(mpi[(n, p)]):>10.4f} {S[p]:>8.3f} {S[p] / p:>8.3f} {amdahl(f, p):>8.3f} {gustafson(f, p):>10.3f}  {ok}")
    lim = f"{1 / f:.1f}" if f > 0 else "sin limite"
    print(f"Fraccion serial efectiva (ajuste de Amdahl): f = {f:.3f}  ->  speedup maximo teorico = {lim}")
    print("(los 3 nodos comparten la misma CPU fisica; f incluye ese efecto y la comunicacion del halo)")

vig, vig_cs = collections.defaultdict(list), set()
for r in leer("benchmark_vigia.csv"):
    k = (int(r["procesos"]), int(r["hilos"]))
    vig[k].append(float(r["tiempo_s"]))
    vig_cs.add(r["checksum"])
if (1, 1) in vig:
    b = media(vig[(1, 1)])
    print("\n=== Vigia hibrido MPI+OpenMP ===")
    print(f"{'procs':>5} {'hilos':>5} {'nucleos':>7} {'reps':>4} {'T (s)':>9} {'S':>7} {'E':>7}")
    for (pr, hi) in sorted(vig):
        t = media(vig[(pr, hi)]); s = b / t; c = pr * hi
        print(f"{pr:>5} {hi:>5} {c:>7} {len(vig[(pr, hi)]):>4} {t:>9.4f} {s:>7.3f} {s / c:>7.3f}")
    print("Checksums:", "IGUALES en todas las configuraciones" if len(vig_cs) == 1 else f"DIFERENTES ({len(vig_cs)} valores)")
