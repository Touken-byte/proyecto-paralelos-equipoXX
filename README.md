# Guardianes del Chaco - Motor de simulación paralela de incendios

Proyecto final integrador de TEL-420 Sistemas Paralelos.
Universidad Autónoma "Juan Misael Saracho" - Facultad de Ciencias Integradas de Yacuiba.

## Descripción
Simulación de propagación de incendios forestales del Gran Chaco mediante un
autómata celular estocástico, en versiones secuencial, OpenMP y MPI, ejecutada
sobre un clúster contenerizado de 3 nodos (1 master + 2 workers) con Docker.
Es el motor de cómputo del videojuego educativo "Guardianes del Chaco".

## Integrantes
- Touken-byte
- Integrante 2
- Integrante 3

## Requisitos
- Linux (Ubuntu 22.04 o superior) o WSL2
- Docker y Docker Compose v2 (`docker run hello-world` debe funcionar sin sudo)
- Python 3 (para generar mapas y convertir imágenes)

## Inicio rápido (reproducibilidad)
```bash
git clone https://github.com/Touken-byte/proyecto-paralelos-equipoXX.git
cd proyecto-paralelos-equipoXX
cd infrastructure && docker compose up -d --build && cd ..
./scripts/demo_hito2.sh
```

## Topología del clúster
- 3 contenedores: `master`, `worker1`, `worker2` (imagen Ubuntu 22.04 con gcc, OpenMPI y SSH)
- Red bridge interna `clusternet`, resolución de nombres por hostname
- SSH sin contraseña con claves generadas al arrancar (no se suben al repositorio)
- Cada nodo: 4 CPUs y 8 GB de RAM (`cpus` y `mem_limit` en docker-compose.yml)
- El repositorio se monta en la misma ruta en los 3 nodos
- Los 3 nodos comparten la misma CPU física del host

## Scripts
| Script | Función |
|--------|---------|
| `scripts/smoke_test.sh` | Hola mundo OpenMP y MPI en los 3 nodos |
| `scripts/verify.sh` | Compara checksum secuencial vs OpenMP (1,2,4,8 hilos; static, dynamic, guided) |
| `scripts/benchmark.sh` | Tiempos, speedup y eficiencia (CSV en `output/`) |
| `scripts/demo_hito2.sh` | Demostración completa del Hito 2 |
| `scripts/pgm2png.py` | Convierte los mapas PGM a PNG coloreado |

## Ejecución manual
```bash
# Generar mapa (n, semilla)
python3 data/gen_map.py --n 1024 --seed 42 --out data/maps/map_1024.bin

# Dentro del master
docker exec -it -u mpiuser master bash
cd /home/mpiuser/proyecto
g++ -std=c++17 -O2 -I src/common src/sequential/fire_seq.cpp -o bin/fire_seq
g++ -std=c++17 -O2 -fopenmp -I src/common src/parallel/fire_omp.cpp -o bin/fire_omp
mpicxx -std=c++17 -O2 -I src/common src/parallel/fire_mpi.cpp -o bin/fire_mpi
./bin/fire_seq --mapa data/maps/map_1024.bin --pasos 100
OMP_SCHEDULE=dynamic ./bin/fire_omp --mapa data/maps/map_1024.bin --pasos 100 --hilos 4
mpirun -np 3 --hostfile infrastructure/hostfile --map-by node ./bin/fire_mpi --mapa data/maps/map_1024.bin --pasos 100
```

## Diseño de corrección
- Doble buffer: se lee del paso anterior y se escribe en el siguiente, sin carreras.
- RNG determinista por celda (semilla, paso, índice): el resultado no depende del número de hilos o procesos.
- Checksum FNV-1a del estado final: secuencial, OpenMP y MPI deben coincidir.
- OpenMP: `#pragma omp for schedule(runtime)` solo sobre el bucle de filas (el bucle de columnas queda interno), con doble buffer y copias locales de punteros y parámetros; `reduction` para los conteos. El schedule se cambia sin recompilar: `OMP_SCHEDULE=dynamic,4 ./bin/fire_omp ...`.
- MPI: descomposición por filas, halo con `MPI_Isend/Irecv`, `MPI_Reduce` y `MPI_Gatherv`.

## Estructura
- `infrastructure/`  Dockerfile, docker-compose.yml, hostfile, entrypoint
- `src/common/`      Estados, parámetros, RNG y regla de transición
- `src/sequential/`  Versión secuencial (T_1)
- `src/parallel/`    Versiones OpenMP y MPI
- `src/smoke/`       Programas de prueba de OpenMP y MPI
- `data/`            Generador de mapas sintéticos
- `scripts/`         Smoke test, verificación, benchmark y demo
- `docs/`            Evidencias, interfaz motor-juego e informe

## Estado (Hito 2)
Clúster operativo, secuencial verificado, OpenMP verificado, MPI con halo
funcional y benchmark preliminar. Pendiente para el Hito 3: híbrido
MPI+OpenMP, Monte Carlo del Vigía, benchmark completo y análisis con las
leyes de Amdahl y Gustafson.

## Evidencias
Ver `docs/README_evidencias.md`.
