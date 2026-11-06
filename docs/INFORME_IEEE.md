# Simulación paralela de incendios forestales del Gran Chaco con OpenMP, MPI y un modelo híbrido

**Autora:** Touken-byte | **Equipo:** [EQUIPO: firnt (por confirmar)] | **Materia:** TEL-420 Sistemas Paralelos, UAJMS Yacuiba | **Docente:** Ing. Elias Cassal Baldiviezo

## I. Resumen
[Escribir al final, 150-200 palabras: problema, método (autómata celular estocástico paralelo), resultados principales ([DELL] speedup y eficiencia máximos) y conclusión.]
Palabras clave: autómata celular, incendios forestales, OpenMP, MPI, speedup, Amdahl, Gustafson.

## II. Introducción
Problema regional (ver docs/PERFIL_TECNICO.md). Motivación para paralelizar: muchos escenarios y muchas celdas. Objetivos y contribuciones: motor secuencial, OpenMP, MPI, híbrido con Vigía Monte Carlo, infraestructura reproducible en Docker. [Agregar fuente oficial sobre incendios en la región si se consigue.]

## III. Modelo y algoritmo
El incendio se modela como un autómata celular estocástico sobre una malla de n x n celdas con vecindad de Moore (8 vecinas) y doble buffer: el paso t+1 se calcula leyendo únicamente el paso t, lo que elimina dependencias dentro de un mismo paso.

Cada celda puede estar vacía, con vegetación, quemando, quemada, con cortafuegos o con agua, y solo la vegetación puede encenderse. Una celda en llamas pasa a quemada con probabilidad p_apagado = 0,25 por paso. Para una celda de vegetación, cada vecina k en llamas aporta una probabilidad de contagio p_k = min(0,95; p_base · f_c · f_h · f_v,k), con p_base = 0,30. El factor de combustible es f_c = combustible/255, el de humedad f_h = 1 − 0,8 · humedad/255, y el de viento f_v,k = d_k · exp(1,5 · w · cos θ_k), donde w es la fuerza del viento, θ_k el ángulo entre la dirección del viento y la dirección vecina → celda, y d_k vale 1 para vecinas ortogonales y 0,7071 para diagonales.

La probabilidad total de ignición combina a todas las vecinas en llamas, P = 1 − Π(1 − p_k), y la celda se enciende si u < P. El número aleatorio u se obtiene de SplitMix64 aplicado a la terna (semilla, paso, índice de celda), de modo que depende solo de esos tres valores y nunca del hilo o proceso que calcula la celda. Esta decisión de diseño hace que todas las versiones produzcan exactamente el mismo resultado y permite verificarlas con un checksum del estado final.

Las acciones del jugador son APAGAR (quemando → quemada) y CORTAFUEGO (vegetación → cortafuegos), y se aplican antes de calcular cada paso.

## IV. Implementación paralela
A. OpenMP (memoria compartida): las filas de la malla se reparten entre los hilos con la cláusula schedule(runtime), lo que permite comparar las políticas static, dynamic y guided sin recompilar. Gracias al doble buffer, los hilos escriben en el buffer de destino sin sincronización dentro del paso.
B. MPI (memoria distribuida): la malla se descompone por bloques de filas, uno por proceso. En cada paso los procesos intercambian una fila de halo con sus vecinos para poder evaluar las celdas del borde, y las métricas globales se obtienen con una reducción.
C. Híbrido y Vigía: el Vigía ejecuta simulaciones Monte Carlo independientes con distintas semillas. Las simulaciones se reparten entre procesos MPI y, dentro de cada proceso, los hilos OpenMP procesan su parte. Los resultados se acumulan en un mapa de probabilidad de riesgo de quema por celda. Al ser simulaciones independientes, casi no requieren comunicación.
D. Clasificación: MIMD, SPMD; memoria compartida (OpenMP) y distribuida (MPI).
E. Corrección: checksum idéntico en todas las versiones (n=512, semilla 42, 100 pasos: c5dad814f7cbeaff).

F. Integración con el videojuego: el motor secuencial (`fire_seq`) se ejecuta dentro del contenedor `master` y el videojuego en Python (pygame) lo invoca una vez por ronda de cinco pasos. Las acciones de los jugadores (cortafuegos y agua) se escriben en un archivo de acciones que el motor lee en el paso indicado, y el estado del mapa se guarda y se recupera entre rondas, de modo que la simulación continúa sin recalcularse desde cero. El cálculo corre en un hilo aparte para que la interfaz no se bloquee. Cada nivel de la campaña (Bosques de Yacuiba, Serranía del Aguaragüe, Región de Tarija y El gran incendio) define su propio tamaño de mapa (96, 112, 128 y 128 celdas de lado), su semilla y la dirección e intensidad del viento. El Vigía recibe los mismos parámetros de viento que el fuego real, para que su mapa de riesgo Monte Carlo sea coherente con la partida. Los recursos del bombero (tanque de seis cargas con recarga junto al río y tiempo de recuperación del cortafuegos) y el compañero controlado por reglas se implementan en el cliente y no modifican el motor, por lo que el checksum de referencia no cambia.

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
