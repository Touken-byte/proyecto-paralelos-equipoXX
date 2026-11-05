#!/usr/bin/env python3
"""Analisis de escalabilidad debil (Gustafson). Uso: analisis_debil.py [csv] [carpeta_graficas]"""
import sys, csv, os
from collections import defaultdict
ruta = sys.argv[1] if len(sys.argv) > 1 else "output/benchmark_debil.csv"
sal = sys.argv[2] if len(sys.argv) > 2 else "docs/graficas"
os.makedirs(sal, exist_ok=True)

datos, tam = defaultdict(list), {}
with open(ruta) as f:
    for r in csv.DictReader(f):
        h = int(r["hilos"]); datos[h].append(float(r["tiempo_s"])); tam[h] = int(r["n"])
ps = sorted(datos)
tp = {p: sum(datos[p]) / len(datos[p]) for p in ps}
t1 = tp[ps[0]]

print(f"=== Escalabilidad debil (carga por hilo constante; T_1 = {t1:.4f} s con n={tam[ps[0]]}) ===")
print("  p      n     T_p (s)     E_w    S_escalado  Gustafson(a)")
alfas, filas = [], []
for p in ps:
    ew = t1 / tp[p]; s = p * ew
    a = (p - s) / (p - 1) if p > 1 else float("nan")
    if p > 1: alfas.append(a)
    filas.append((p, ew, s))
    print(f"{p:3d} {tam[p]:6d} {tp[p]:10.4f} {ew:7.3f} {s:11.3f} {a:12.3f}")
if alfas:
    am = sum(alfas) / len(alfas)
    print(f"Fraccion serial escalada media (alfa) = {am:.3f}")
    print("(alfa incluye ancho de banda de memoria e hyperthreading, no solo codigo secuencial)")

try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.figure(); plt.plot(ps, [e for _, e, _ in filas], "o-", label="E_w medida")
    plt.axhline(1.0, ls="--", color="gray", label="ideal"); plt.xlabel("hilos p")
    plt.ylabel("eficiencia debil T1/Tp"); plt.ylim(0, 1.2); plt.legend(); plt.grid(alpha=.3)
    plt.title("Escalabilidad debil: eficiencia"); plt.savefig(f"{sal}/debil_eficiencia.png", dpi=120); plt.close()
    plt.figure(); plt.plot(ps, [s for _, _, s in filas], "o-", label="S escalado medido")
    plt.plot(ps, ps, "--", color="gray", label="ideal (S=p)"); plt.xlabel("hilos p")
    plt.ylabel("speedup escalado"); plt.legend(); plt.grid(alpha=.3)
    plt.title("Escalabilidad debil: speedup (Gustafson)"); plt.savefig(f"{sal}/debil_speedup.png", dpi=120); plt.close()
    print(f"Graficas guardadas en {sal}/")
except ImportError:
    print("matplotlib no disponible: se omiten las graficas")
