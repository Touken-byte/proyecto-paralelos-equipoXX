#!/usr/bin/env python3
"""Analisis del benchmark: speedup, eficiencia, ajuste de Amdahl y prediccion de Gustafson.
Uso: python3 scripts/analisis.py [output/benchmark.csv] [carpeta_graficas]"""
import collections, csv, os, sys

ruta = sys.argv[1] if len(sys.argv) > 1 else "output/benchmark.csv"
sal = sys.argv[2] if len(sys.argv) > 2 else "docs/graficas"

datos = collections.defaultdict(list)
for r in csv.DictReader(open(ruta)):
    datos[(r["modo"], int(r["n"]), int(r["hilos"]))].append(float(r["tiempo_s"]))
prom = {k: sum(v) / len(v) for k, v in datos.items()}

def amdahl(f, p):
    return 1.0 / (f + (1.0 - f) / p)

def gustafson(f, p):
    return p - f * (p - 1)

res = {}
for n in sorted({k[1] for k in prom}):
    t1 = prom[("seq", n, 1)]
    hs = sorted(h for (m, nn, h) in prom if m == "omp" and nn == n)
    S = {h: t1 / prom[("omp", n, h)] for h in hs}
    f = min((i / 1000 for i in range(1001)),
            key=lambda x: sum((S[h] - amdahl(x, h)) ** 2 for h in hs))
    res[n] = (t1, hs, S, f)
    print(f"\n=== n = {n}  (T_1 secuencial = {t1:.4f} s) ===")
    print(f"{'p':>3} {'T_p (s)':>10} {'S_p':>8} {'E_p':>8} {'Amdahl':>8} {'Gustafson':>10}")
    for h in hs:
        tp = prom[("omp", n, h)]
        print(f"{h:>3} {tp:>10.4f} {S[h]:>8.3f} {S[h]/h:>8.3f} {amdahl(f,h):>8.3f} {gustafson(f,h):>10.3f}")
    print(f"Fraccion serial efectiva (ajuste de Amdahl): f = {f:.3f}  ->  speedup maximo teorico = {1/f if f>0 else float('inf'):.1f}")
    print("(f incluye el efecto del ancho de banda de memoria, no solo codigo secuencial)")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(sal, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for n, (t1, hs, S, f) in res.items():
        ax.plot(hs, [S[h] for h in hs], "o-", label=f"medido n={n}")
        ax.plot(hs, [amdahl(f, h) for h in hs], "--", alpha=0.5, label=f"Amdahl f={f:.2f} n={n}")
    mx = max(max(v[1]) for v in res.values())
    ax.plot([1, mx], [1, mx], "k:", label="ideal")
    ax.set_xlabel("Hilos (p)"); ax.set_ylabel("Speedup S_p"); ax.set_title("Speedup OpenMP")
    ax.grid(True, alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(f"{sal}/speedup.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    for n, (t1, hs, S, f) in res.items():
        ax.plot(hs, [S[h] / h for h in hs], "o-", label=f"n={n}")
    ax.axhline(1.0, color="k", linestyle=":")
    ax.set_xlabel("Hilos (p)"); ax.set_ylabel("Eficiencia E_p"); ax.set_title("Eficiencia OpenMP")
    ax.grid(True, alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(f"{sal}/eficiencia.png", dpi=150); plt.close(fig)
    print(f"\nGraficas guardadas en {sal}/")
except ImportError:
    print("\n(matplotlib no esta instalado: no se generaron graficas)")
