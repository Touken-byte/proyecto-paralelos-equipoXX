#!/usr/bin/env python3
"""Fig. 2 (fuerte) y Fig. 3 (debil) desde docs/resultados_dell/*.csv.
Uso: /tmp/venv/bin/python scripts/fig_resultados.py"""
import csv, os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
D = "docs/resultados_dell/"
plt.rcParams.update({"font.size": 8, "axes.grid": True, "grid.alpha": 0.3})
os.makedirs("docs/figuras", exist_ok=True)

# ---- Fig. 2: escalabilidad fuerte OpenMP ----
fuerte = defaultdict(dict)
for r in csv.DictReader(open(D + "benchmark_resumen.csv")):
    if r["modo"] == "omp":
        fuerte[int(r["n"])][int(r["hilos"])] = (float(r["speedup"]), float(r["eficiencia"]))
fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.9))
hs = [1, 2, 4, 8, 16]
a.plot(hs, hs, "k--", label="Ideal")
for n, m in sorted(fuerte.items()):
    a.plot(hs, [m[h][0] for h in hs], "o-", label="n=%d" % n)
    b.plot(hs, [m[h][1] for h in hs], "o-", label="n=%d" % n)
a.set_title("(a) Speedup"); b.set_title("(b) Eficiencia")
b.axhline(1, color="k", ls="--", lw=0.8)
for ax in (a, b):
    ax.set_xlabel("Hilos OpenMP"); ax.set_xticks(hs); ax.legend()
a.set_ylabel("S = T_seq / T_p"); b.set_ylabel("E = S / p"); b.set_ylim(0.4, 1.1)
fig.tight_layout(); fig.savefig("docs/figuras/fig_fuerte.png", dpi=200)
print("OK fig_fuerte.png")

# ---- Fig. 3: escalabilidad debil ----
t = defaultdict(list); nn = {}
for r in csv.DictReader(open(D + "benchmark_debil.csv")):
    t[int(r["hilos"])].append(float(r["tiempo_s"])); nn[int(r["hilos"])] = int(r["n"])
tp = {h: sum(v) / len(v) for h, v in t.items()}
hs = sorted(tp); t1 = tp[1]
ew = [t1 / tp[h] for h in hs]; se = [h * e for h, e in zip(hs, ew)]
alfa = 0.068  # media de analisis_debil.txt
gus = [h - alfa * (h - 1) for h in hs]
fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.9))
a.plot(hs, hs, "k--", label="Ideal")
a.plot(hs, gus, "s:", label="Gustafson (α=0,068)")
a.plot(hs, se, "o-", label="Medido")
b.plot(hs, ew, "o-")
b.axhline(1, color="k", ls="--", lw=0.8)
a.set_title("(a) Speedup escalado"); b.set_title("(b) Eficiencia débil")
a.set_ylabel("S escalado = p · T_1 / T_p"); b.set_ylabel("E_w = T_1 / T_p"); b.set_ylim(0.5, 1.05)
for ax in (a, b):
    ax.set_xlabel("Hilos (n crece con p)"); ax.set_xticks(hs)
a.legend()
fig.tight_layout(); fig.savefig("docs/figuras/fig_debil.png", dpi=200)
print("OK fig_debil.png")
print("T_1 debil = %.4f s; E_w =" % t1, ["%.3f" % e for e in ew], "S =", ["%.2f" % x for x in se])
