# Guardianes del Chaco - Videojuego educativo y motor de simulación paralela de incendios

Proyecto final integrador de TEL-420 Sistemas Paralelos.
Universidad Autónoma "Juan Misael Saracho" - Facultad de Ciencias Integradas de Yacuiba (Gran Chaco, Tarija, Bolivia).
Docente: Ing. Elias Cassal Baldiviezo.

## Descripción
Videojuego cooperativo de rescate de fauna y control de incendios forestales del Gran Chaco.
El fuego se calcula con un autómata celular estocástico (viento, humedad, vegetación,
cortafuegos y acciones del jugador) implementado en C++17 en cuatro versiones: secuencial,
OpenMP, MPI e híbrida MPI+OpenMP (El Vigía, predicción Monte Carlo). El motor se ejecuta sobre
un clúster contenerizado de 3 nodos (1 master + 2 workers) con Docker.

## Integrantes
- equipo01: Touken-byte (trabajo individual)

## Requisitos
- Linux (Ubuntu 22.04 o superior) o WSL2
- Docker y Docker Compose v2 (`docker run hello-world` debe funcionar sin sudo). Para usar
  `docker compose up` desde la raíz del repositorio hace falta Compose 2.20 o superior.
- Python 3 (para el juego, el generador de mapas y los análisis)

## Reproducibilidad: benchmark sin intervención manual
Desde un clon limpio:

    git clone https://github.com/Touken-byte/proyecto-paralelos-equipoXX.git
    cd proyecto-paralelos-equipoXX
    ./scripts/benchmark.sh

El script levanta el clúster si no está corriendo, compila las cuatro versiones dentro del
contenedor `master`, mide, verifica checksums y termina con `VERIFICACION EXITOSA`.
Genera en `output/`: `benchmark.csv` (secuencial y OpenMP), `benchmark_mpi.csv`,
`benchmark_vigia.csv` y un `*_resumen.csv` de cada uno (tiempo promedio, speedup y eficiencia).

Variables opcionales (valores por defecto entre paréntesis):

| Variable | Significado |
|----------|-------------|
| `SIZES` | Tamaños de malla ("512 1024 2048") |
| `HILOS` | Hilos de OpenMP ("1 2 4 8") |
| `NPS` | Procesos MPI ("1 2 3 6") |
| `PASOS` | Pasos de simulación (100) |
| `REPS` | Repeticiones por configuración (5) |
| `SEMILLA` | Semilla del RNG (42) |
| `SIMS` | Simulaciones Monte Carlo del Vigía (24) |

Prueba rápida:

    SIZES="512" HILOS="1 2" NPS="1 3" REPS=1 PASOS=20 SIMS=6 ./scripts/benchmark.sh

Alternativa: `docker compose up --build` desde la raíz levanta el clúster de 3 nodos (no ejecuta
el benchmark por sí solo). Si ya hay un clúster levantado con `infrastructure/docker-compose.yml`,
bájalo antes con `docker compose -f infrastructure/docker-compose.yml down`.
Para ver el análisis (speedup, eficiencia, Amdahl y Gustafson) sobre los CSV:
`python3 scripts/analisis.py` y `python3 scripts/analisis_mpi.py`.

## Topología del clúster
- 3 contenedores: `master`, `worker1`, `worker2` (imagen Ubuntu 22.04 con gcc, OpenMPI y SSH)
- Red bridge interna `clusternet`, resolución de nombres por hostname
- SSH sin contraseña con claves generadas al arrancar (no se suben al repositorio)
- Cada nodo: `CPUS_NODO` CPUs (4 por defecto) y 8 GB de RAM
- El repositorio se monta en `/home/mpiuser/proyecto` en los 3 nodos (usuario `mpiuser`)
- Los 3 nodos comparten la misma CPU física del host
- MPI se usa solo dentro de los contenedores (no en el host)

## Diseño de corrección
- Doble buffer: se lee del paso anterior y se escribe en el siguiente, sin carreras.
- RNG determinista por celda (semilla, paso, índice): el resultado no depende del número de hilos o procesos.
- Checksum FNV-1a del estado final: secuencial, OpenMP y MPI deben coincidir.
- OpenMP: `schedule(runtime)` sobre el bucle de filas, con `reduction` para los conteos. El número de
  hilos puede fijarse con `OMP_NUM_THREADS` o `--hilos`; el schedule, con `OMP_SCHEDULE`.
- MPI: descomposición por filas, halo con `MPI_Isend/Irecv`, `MPI_Reduce` y `MPI_Gatherv`.
- Híbrido (Vigía): MPI reparte las simulaciones Monte Carlo y OpenMP las acelera en cada proceso.

## Scripts
| Script | Función |
|--------|---------|
| `scripts/benchmark.sh` | Benchmark completo (secuencial, OpenMP, MPI y Vigía) con verificación de checksums |
| `scripts/benchmark_debil.sh` | Escalabilidad débil, solo OpenMP (la malla crece con los hilos) |
| `scripts/analisis.py` | Speedup, eficiencia, Amdahl y Gustafson (OpenMP) |
| `scripts/analisis_mpi.py` | Speedup, eficiencia, Amdahl, Gustafson y checksum de MPI y Vigía desde los CSV |
| `scripts/analisis_debil.py` | Eficiencia débil y análisis con Gustafson |
| `scripts/smoke_test.sh` | Hola mundo OpenMP y MPI en los 3 nodos |
| `scripts/verify.sh` | Compara checksum secuencial vs OpenMP (1,2,4,8 hilos; static, dynamic, guided) |
| `scripts/verify_vigia.sh` | El Vigía da el mismo checksum con cualquier número de procesos e hilos |
| `scripts/verify_acciones.sh` | Compara las tres versiones aplicando acciones de jugador |
| `scripts/dell_medicion.sh` | Medición oficial en el equipo del laboratorio (sobrescribe `docs/resultados_dell/` y `docs/evidencias/`: no ejecutar en otro equipo) |
| `scripts/captura_recursos.sh` | Carga sostenida para capturas de `htop` y `docker stats` |
| `scripts/pgm2png.py`, `scripts/heat2png.py` | Convierten mapas y mapas de riesgo a PNG |

## Ejecución manual (dentro del master)
    docker exec -it -u mpiuser master bash
    cd /home/mpiuser/proyecto
    g++ -std=c++17 -O2 -I src/common src/sequential/fire_seq.cpp -o bin/fire_seq
    g++ -std=c++17 -O2 -fopenmp -I src/common src/parallel/fire_omp.cpp -o bin/fire_omp
    mpicxx -std=c++17 -O2 -I src/common src/parallel/fire_mpi.cpp -o bin/fire_mpi
    ./bin/fire_seq --mapa data/maps/map_1024.bin --pasos 100
    OMP_NUM_THREADS=4 ./bin/fire_omp --mapa data/maps/map_1024.bin --pasos 100
    mpirun -np 3 --hostfile infrastructure/hostfile --map-by node ./bin/fire_mpi --mapa data/maps/map_1024.bin --pasos 100

Los mapas se generan con `python3 data/gen_map.py --n 1024 --seed 42 --out data/maps/map_1024.bin`.

## El juego
Dos jugadores en una misma PC: la veterinaria (J1) y el bombero (J2). En modo individual el
compañero lo controla una IA con tres dificultades: Asistente, Equilibrado y Experto.
El fuego lo calcula el motor C++ dentro del contenedor `master`; `juego/guardianes.py` dibuja
el mundo y envía las acciones de los jugadores.

Instalación y ejecución (con el clúster levantado):

    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
    docker compose up -d
    ./venv/bin/python juego/guardianes.py        # desde la raíz del repositorio

Contenido:
- Niveles de emergencia (inicial, avanzada y crítica con cuenta regresiva) y campaña por zonas:
  Bosques de Yacuiba, Serranía del Aguaragüe, Región de Tarija y El gran incendio.
- Los animales no mueren: huyen o quedan pendientes de rescate.
- Bombero: mochila de agua, cortafuegos, manguera (G), torre (T), protección térmica (H).
- Veterinaria: rastreo (X), rescate (E), señal de auxilio (Q), conocimiento silvestre (K).
- EcoMonedas, tienda y skins, estrellas, Salón de Guardianes y modos especiales
  (Supervivencia, Desafío, El corazón del incendio, Modo récord).
- El Vigía (V): predicción Monte Carlo con mapa de riesgo. Centro de Análisis: compara
  escenarios sin y con cortafuegos.
- Cuaderno de Guardianes (N): enciclopedia de fauna, guía de prevención, manual de emergencias,
  atlas de incendios y primeros auxilios, con desbloqueo progresivo. Las fichas citan sus fuentes;
  ninguna de las de primeros auxilios es boliviana y se recomienda confirmar con la Cruz Roja
  Boliviana o Defensa Civil.

Controles básicos: clic izquierdo, cortafuegos; clic derecho, mochila de agua; flechas, mueven
al bombero; W A S D, a la veterinaria; P, ayuda y pausa; O, audio; N, Cuaderno. La interfaz
entre el juego y el motor está en `docs/INTERFAZ_MOTOR_JUEGO.md`.

## Estructura
- `infrastructure/`  Dockerfile, docker-compose.yml, hostfile, entrypoint
- `docker-compose.yml`  Atajo en la raíz que incluye el de `infrastructure/`
- `src/common/`      Estados, parámetros, RNG y regla de transición
- `src/sequential/`  Versión secuencial (T_1)
- `src/parallel/`    Versiones OpenMP, MPI e híbrida (Vigía Monte Carlo)
- `src/smoke/`       Programas de prueba de OpenMP y MPI
- `data/`            Generador de mapas sintéticos
- `scripts/`         Benchmark, verificación, análisis y utilidades
- `juego/`           Juego (pygame), sprites, fuentes y sonidos
- `docs/`            Informe final, evidencias e interfaz motor-juego

## Estado (Hito 3)
Motor secuencial, OpenMP, MPI e híbrido verificados por checksum; benchmark completo y
reproducible con `./scripts/benchmark.sh`; juego completo con campaña, modos, IA, Cuaderno y
Vigía. Informe final: `docs/informe-final-equipo01.pdf`.

## Trabajo futuro (fuera del alcance del Hito 3)
Ideas que no forman parte de esta entrega y se considerarían solo si el juego se despliega más allá del curso:
- Botiquín de la veterinaria con barra de vida de los animales (se retiró del juego porque requería un modelo de daño de la fauna).
- Más niveles, especies y contenido educativo (incluida una fuente boliviana verificada para la ficha de Cortafuegos).
- Más skins y sombreros intercambiables.

## Evidencias
Ver `docs/README_evidencias.md`.
