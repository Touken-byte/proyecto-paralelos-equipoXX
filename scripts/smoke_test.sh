#!/bin/bash
# Smoke test: OpenMP y MPI en los 3 nodos del clúster.
# Uso (desde el host): ./scripts/smoke_test.sh
set -e

echo "=== Compilando dentro del master ==="
docker exec -u mpiuser master bash -c "
  cd /home/mpiuser/proyecto &&
  mkdir -p bin &&
  gcc -fopenmp src/smoke/hello_omp.c -o bin/hello_omp &&
  mpicc src/smoke/hello_mpi.c -o bin/hello_mpi &&
  echo 'Compilación OK'"

echo ""
echo "=== Versiones ==="
docker exec -u mpiuser master bash -c "gcc --version | head -1; mpirun --version | head -1"

echo ""
echo "=== Smoke test OpenMP (4 hilos) ==="
docker exec -u mpiuser master bash -c "
  cd /home/mpiuser/proyecto &&
  OMP_NUM_THREADS=4 ./bin/hello_omp"

echo ""
echo "=== Smoke test MPI (3 procesos, uno por nodo) ==="
docker exec -u mpiuser master bash -c "
  cd /home/mpiuser/proyecto &&
  mpirun -np 3 --hostfile infrastructure/hostfile --map-by node ./bin/hello_mpi"

echo ""
echo "=== Smoke test MPI (12 procesos, 4 por nodo) ==="
docker exec -u mpiuser master bash -c "
  cd /home/mpiuser/proyecto &&
  mpirun -np 12 --hostfile infrastructure/hostfile ./bin/hello_mpi | sort -k8"

echo ""
echo "SMOKE TEST COMPLETADO"
