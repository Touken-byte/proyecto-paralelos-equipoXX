# Simulación paralela de incendios forestales del Gran Chaco con OpenMP, MPI y un modelo híbrido

**Autora:** Touken-byte | **Equipo:** [EQUIPO: firnt (por confirmar)] | **Materia:** TEL-420 Sistemas Paralelos, UAJMS Yacuiba | **Docente:** Ing. Elias Cassal Baldiviezo

## I. Resumen
[Escribir al final, 150-200 palabras: problema, método (autómata celular estocástico paralelo), resultados principales ([DELL] speedup y eficiencia máximos) y conclusión.]
Palabras clave: autómata celular, incendios forestales, OpenMP, MPI, speedup, Amdahl, Gustafson.

## II. Introducción
Problema regional (ver docs/PERFIL_TECNICO.md). Motivación para paralelizar: muchos escenarios y muchas celdas. Objetivos y contribuciones: motor secuencial, OpenMP, MPI, híbrido con Vigía Monte Carlo, infraestructura reproducible en Docker. [Agregar fuente oficial sobre incendios en la región si se consigue.]

## III. Modelo y algoritmo
Autómata celular estocástico, malla n x n, vecindad de Moore, doble buffer. Regla de transición, probabilidad de ignición P = 1 - Π(1 - p_k) y RNG determinista por celda (semilla, paso, índice). Acciones del jugador. Ver docs/PERFIL_TECNICO.md, sección 2.

## IV. Implementación paralela
A. OpenMP: reparto de filas, schedule(runtime), doble buffer.
B. MPI: descomposición por filas, halo de una fila, reducción de métricas.
C. Híbrido y Vigía: simulaciones Monte Carlo independientes entre procesos, hilos dentro de cada proceso.
D. Clasificación: MIMD, SPMD; memoria compartida (OpenMP) y distribuida (MPI).
E. Corrección: checksum idéntico en todas las versiones (n=512, semilla 42, 100 pasos: c5dad814f7cbeaff).

## V. Infraestructura y metodología experimental
A. Clúster: 3 contenedores Docker (master, worker1, worker2), red bridge, SSH sin contraseña, Ubuntu 22.04, 8 GB de RAM y hasta 4 CPUs por nodo.
B. Hardware de medición: [DELL] lscpu (modelo, núcleos físicos, hilos lógicos), RAM.
C. Protocolo: tamaños [DELL: 512, 1024, 2048], hilos [DELL: 1, 2, 4, 8], procesos MPI [DELL], [DELL: número de repeticiones y promedio]. Métricas: T_p, S_p = T_1/T_p, E_p = S_p/p.
D. Reproducibilidad: `scripts/dell_medicion.sh`, semilla fija, repositorio con un comando.

## VI. Resultados y análisis
A. Huella de memoria: n=512, unos 4,4 MB de RSS máximo. [DELL: n=1024 y 2048.]
B. Escalabilidad fuerte: [DELL: tabla y gráfica de tiempo, speedup y eficiencia; ajuste de Amdahl y fracción secuencial f].
C. Escalabilidad débil: [DELL: eficiencia débil y comparación con Gustafson].
D. MPI e híbrido: [DELL: tiempos con 1, 2, 3, 6 procesos; Vigía].
E. Cuellos de botella: ancho de banda de memoria, hyperthreading, los 3 nodos comparten la misma CPU física, red virtual sin latencia real.
F. Datos preliminares (laptop, no oficiales): speedup OpenMP con 2 hilos de 1,90 (n=512, 100 pasos); con 4 hilos cae a unos 0,92 por hyperthreading. Se sustituyen por los de la Dell.

## VII. Conclusiones y trabajo futuro
[Escribir con los resultados de la Dell.] Trabajo futuro: CUDA, más regiones, juego completo, otras redes.

## VIII. Referencias
[1] Amdahl, G. M., "Validity of the single processor approach to achieving large scale computing capabilities," AFIPS 1967.
[2] Gustafson, J. L., "Reevaluating Amdahl's law," Commun. ACM, 1988.
[3] OpenMP Architecture Review Board, OpenMP Application Programming Interface.
[4] MPI Forum, MPI: A Message-Passing Interface Standard.
[5] Steele, G. L. et al., "Fast splittable pseudorandom number generators," OOPSLA 2014 (SplitMix64).
[Agregar referencias sobre autómatas celulares de incendio y datos regionales.]
