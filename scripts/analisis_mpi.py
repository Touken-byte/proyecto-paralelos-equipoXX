#!/usr/bin/env python3
"""Analisis de MPI y Vigia hibrido: promedio de repeticiones, speedup y eficiencia.
Uso: python3 scripts/analisis_mpi.py docs/resultados_dell"""
import collections, re, sys

carpeta = sys.argv[1] if len(sys.argv) > 1 else "docs/resultados_dell"

def leer(ruta, clave):
    datos, sums = collections.defaultdict(list), collections.defaultdict(set)
    for linea in open(ruta):
        if "RESULT" not in linea:
            continue
        c = dict(re.findall(r"(\w+)=(\S+)", linea))
        k = clave(c)
        datos[k].append(float(c["t"]))
        sums[k].add(c["checksum"])
    return {k: sum(v) / len(v) for k, v in datos.items()}, datos, sums

def tabla(titulo, prom, datos, sums, base_key, cores):
    print(f"\n=== {titulo} ===")
    t1 = prom[base_key]
    print("config           reps   T_prom(s)   S_p     E_p   checksum")
    for k in sorted(prom):
        p = cores(k)
        s = t1 / prom[k]
        ok = "OK" if len(sums[k]) == 1 else "DIFERENTE!"
        print(f"{str(k):15} {len(datos[k]):4}   {prom[k]:9.4f}  {s:6.2f}  {s/p:5.2f}   {ok}")

# MPI: clave = procesos
p, d, s = leer(f"{carpeta}/mpi.txt", lambda c: int(c["procs"]))
tabla("fire_mpi (descomposicion por filas + halo)", p, d, s, 1, lambda k: k)

# Vigia: clave = (procesos, hilos); nucleos = procesos * hilos
p, d, s = leer(f"{carpeta}/vigia.txt", lambda c: (int(c["procs"]), int(c["hilos"])))
tabla("Vigia hibrido MPI+OpenMP", p, d, s, (1, 1), lambda k: k[0] * k[1])
