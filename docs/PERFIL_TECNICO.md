# Perfil Técnico: Guardianes del Chaco

**Equipo:** [EQUIPO: firnt (por confirmar)] | **Materia:** TEL-420 Sistemas Paralelos, UAJMS Yacuiba | **Autora:** Touken-byte (trabajo individual)

## 1. Problema regional
Los incendios forestales amenazan los bosques del Gran Chaco y de Tarija, su fauna y las comunidades cercanas. Su propagación depende de factores que cambian rápido (viento, humedad, vegetación seca) y es difícil de anticipar. Simular muchos escenarios (por ejemplo, con y sin cortafuegos) exige mucho cómputo, y ahí la computación paralela aporta: permite explorar más escenarios en menos tiempo. El motor de simulación sirve de base a un videojuego educativo (*Guardianes del Chaco*) para entender el riesgo y la prevención. Los resultados son experimentales y educativos, no predicciones oficiales. [Completar con datos oficiales de la región si se desea citarlos.]

## 2. Modelo matemático
Autómata celular estocástico sobre una malla de n x n celdas, vecindad de Moore (8 vecinas) y doble buffer (el paso t+1 se calcula solo leyendo el paso t).

- **Estados:** vacía, vegetación, quemando, quemada, cortafuegos, agua. Solo la vegetación puede encenderse.
- **Quemando → quemada:** con probabilidad p_apagado = 0,25 por paso.
- **Vegetación → quemando:** por cada vecina k en llamas, p_k = min(0,95; p_base · f_c · f_h · f_v,k), con p_base = 0,30.
  - f_c = combustible/255 (más combustible, más contagio).
  - f_h = 1 − 0,8 · humedad/255 (más humedad, menos contagio).
  - f_v,k = d_k · exp(1,5 · w · cos θ_k), donde w es la fuerza del viento, θ_k el ángulo entre el viento y la dirección vecina → celda, y d_k = 1 (ortogonales) o 0,7071 (diagonales).
- **Probabilidad de ignición:** P = 1 − Π(1 − p_k). La celda se enciende si u < P.
- **Aleatoriedad determinista:** u = SplitMix64(semilla, paso, índice de celda) ∈ [0,1). Depende solo de esos tres valores, nunca del hilo o proceso, por lo que el resultado es idéntico en secuencial, OpenMP y MPI, y se verifica con un checksum del estado final.
- **Acciones del jugador:** APAGAR (quemando → quemada) y CORTAFUEGO (vegetación → cortafuegos), aplicadas antes de calcular cada paso.

## 3. Paralelización
Cada celda nueva depende solo del estado anterior, lo que da paralelismo de datos. Clasificación: MIMD (SPMD como modelo de programación); memoria compartida con OpenMP dentro de un nodo y memoria distribuida con MPI entre nodos.

- **OpenMP:** reparto de filas con `schedule(runtime)` (static, dynamic, guided), con doble buffer.
- **MPI:** descomposición por filas con halo de una fila e intercambio en cada paso.
- **Híbrido (Vigía):** simulaciones Monte Carlo independientes repartidas entre procesos MPI, con hilos OpenMP dentro de cada proceso, acumulando un mapa de probabilidad de riesgo.
- **Métricas:** tiempo, speedup S_p = T_1/T_p, eficiencia E_p = S_p/p, Amdahl (escalabilidad fuerte) y Gustafson (escalabilidad débil).

Resultado verificado (n=512, semilla 42, 100 pasos): checksum idéntico en secuencial, OpenMP (todos los schedules, 1/2/4/8 hilos) y MPI (1/2/3/6 procesos). Huella de memoria: unos 4,4 MB de RSS máximo.

## 4. Arquitectura del clúster
Tres contenedores Docker (master, worker1, worker2) en una red bridge interna con resolución de nombres. Ubuntu 22.04 con gcc/g++, OpenMP y OpenMPI; SSH sin contraseña entre nodos (claves generadas al arrancar, no subidas al repo); hostfile con 4 slots por nodo; cada contenedor con límite de 8 GB de RAM y hasta 4 CPUs (variable `CPUS_NODO`). El repositorio se monta en los tres nodos y todo se compila y ejecuta dentro del master.

Limitación honesta: los tres nodos comparten la misma CPU física del host, así que el speedup entre nodos tiene un techo y la red virtual no refleja la latencia de una red real. Las mediciones oficiales se toman en el equipo del laboratorio (Dell OptiPlex 7010, Core i7, 32 GB).
