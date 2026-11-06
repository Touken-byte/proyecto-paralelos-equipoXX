# Perfil Técnico: Guardianes del Chaco

**Materia:** TEL-420 Sistemas Paralelos, UAJMS Yacuiba | **Autora:** Touken-byte (trabajo individual)

## 1. Problema regional
Los incendios forestales amenazan los bosques del Gran Chaco y de Tarija, su fauna y las comunidades cercanas. Su propagación depende de factores que cambian rápido (viento, humedad, vegetación seca) y es difícil de anticipar. Simular muchos escenarios, por ejemplo con y sin cortafuegos, exige mucho cómputo, y la computación paralela permite explorar más escenarios en menos tiempo. El motor sirve de base a un videojuego educativo (*Guardianes del Chaco*) sobre riesgo y prevención. Los resultados son experimentales y educativos, no predicciones oficiales. [Completar con datos oficiales de la región si se desea citarlos.]

## 2. Modelo matemático
Autómata celular estocástico sobre una malla de n x n celdas, vecindad de Moore (8 vecinas) y doble buffer (el paso t+1 solo lee el paso t).

- **Estados:** vacía, vegetación, quemando, quemada, cortafuegos, agua. Solo la vegetación puede encenderse.
- **Quemando → quemada:** con probabilidad p_apagado = 0,25 por paso.
- **Vegetación → quemando:** por cada vecina k en llamas, p_k = min(0,95; p_base · f_c · f_h · f_v,k), con p_base = 0,30.
  - f_c = combustible/255.
  - f_h = 1 − 0,8 · humedad/255.
  - f_v,k = d_k · exp(1,5 · w · cos θ_k): w es la fuerza del viento, θ_k el ángulo entre el viento y la dirección vecina → celda, y d_k = 1 (ortogonales) o 0,7071 (diagonales).
- **Ignición:** P = 1 − Π(1 − p_k); la celda se enciende si u < P.
- **Aleatoriedad determinista:** u = SplitMix64(semilla, paso, índice de celda) ∈ [0,1). No depende del hilo ni del proceso, así el resultado es idéntico en secuencial, OpenMP y MPI y se verifica con un checksum.
- **Acciones del jugador:** APAGAR (quemando → quemada) y CORTAFUEGO (vegetación → cortafuegos), aplicadas antes de cada paso.

## 3. Paralelización
Cada celda nueva depende solo del estado anterior (paralelismo de datos). Clasificación: MIMD (SPMD); memoria compartida con OpenMP y distribuida con MPI.

- **OpenMP:** reparto de filas con `schedule(runtime)` y doble buffer.
- **MPI:** descomposición por filas con halo de una fila.
- **Híbrido (Vigía):** simulaciones Monte Carlo independientes entre procesos MPI, con hilos OpenMP dentro de cada uno, acumulando un mapa de riesgo.
- **Métricas:** tiempo, speedup S_p = T_1/T_p, eficiencia E_p = S_p/p, Amdahl (fuerte) y Gustafson (débil).

Verificado (n=512, semilla 42, 100 pasos): checksum idéntico en secuencial, OpenMP (todos los schedules, 1/2/4/8 hilos) y MPI (1/2/3/6 procesos). Memoria: unos 4,4 MB de RSS máximo.

## 4. Arquitectura del clúster
Tres contenedores Docker (master, worker1, worker2) en una red bridge interna, con Ubuntu 22.04, gcc/g++, OpenMP y OpenMPI. SSH sin contraseña (claves generadas al arrancar, no subidas al repo), hostfile con 4 slots por nodo, 8 GB de RAM y hasta `CPUS_NODO` CPUs por contenedor (4 por defecto, 16 en la Dell). El repositorio se monta en los tres nodos y todo se compila y ejecuta en el master.

Limitación: los tres nodos comparten la CPU física del host, así que el speedup entre nodos tiene techo y la red virtual no refleja una red real. Las mediciones oficiales se toman en el equipo del laboratorio (Dell OptiPlex 7010, Core i7, 32 GB).
