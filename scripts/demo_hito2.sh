#!/bin/bash
# Demo del Hito 2. Uso (desde la raiz del repo): ./scripts/demo_hito2.sh
N=${N:-1024}; PASOS=${PASOS:-100}
cd "$(dirname "$0")/.." || exit 1
X="docker exec -u mpiuser master bash -c"

echo "##### 1. CLUSTER #####"
docker compose -f infrastructure/docker-compose.yml up -d
sleep 8
docker ps --filter "name=^master$" --filter "name=^worker1$" --filter "name=^worker2$" --format "table {{.Names}}\t{{.Status}}"

echo; echo "##### 2. CONECTIVIDAD #####"
$X "ping -c 1 worker1 | head -2; ping -c 1 worker2 | head -2"
$X "ssh worker1 hostname; ssh worker2 hostname"
$X "cd /home/mpiuser/proyecto && mkdir -p bin && mpicc src/smoke/hello_mpi.c -o bin/hello_mpi && mpirun -np 3 --hostfile infrastructure/hostfile --map-by node ./bin/hello_mpi"

echo; echo "##### 3. COMPILACION Y DATOS #####"
$X "cd /home/mpiuser/proyecto && F='-std=c++17 -O2 -Wall -Wextra -I src/common' &&
  g++ \$F src/sequential/fire_seq.cpp -o bin/fire_seq &&
  g++ \$F -fopenmp src/parallel/fire_omp.cpp -o bin/fire_omp &&
  mpicxx \$F src/parallel/fire_mpi.cpp -o bin/fire_mpi &&
  { [ -f data/maps/map_$N.bin ] || python3 data/gen_map.py --n $N --seed 42 --out data/maps/map_$N.bin; } && echo Compilacion OK"

echo; echo "##### 4. SECUENCIAL (T_1) + HUELLA DE MEMORIA #####"
$X "cd /home/mpiuser/proyecto && /usr/bin/time -v ./bin/fire_seq --mapa data/maps/map_$N.bin --pasos $PASOS --pgm-cada 50 --salida output/demo 2> output/time.txt | grep -E 'Malla|Pasos|Checksum|Tiempo'; grep -E 'Maximum resident' output/time.txt"

echo; echo "##### 5. OPENMP 1,2,4,8 HILOS Y VERIFICACION #####"
ref=$($X "cd /home/mpiuser/proyecto && ./bin/fire_seq --mapa data/maps/map_$N.bin --pasos $PASOS | grep -o 'checksum=[0-9a-f]*'" | cut -d= -f2)
for h in 1 2 4 8; do
  l=$($X "cd /home/mpiuser/proyecto && ./bin/fire_omp --mapa data/maps/map_$N.bin --pasos $PASOS --hilos $h | grep RESULT")
  cs=$(echo "$l" | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2); t=$(echo "$l" | grep -o ' t=[0-9.]*' | cut -d= -f2)
  [ "$cs" = "$ref" ] && r="CHECKSUM IGUAL" || r="CHECKSUM DISTINTO"
  echo "hilos=$h  tiempo=${t}s  $r"
done

echo; echo "##### 6. MPI (3 procesos, un nodo cada uno) #####"
$X "cd /home/mpiuser/proyecto && mpirun -np 3 --hostfile infrastructure/hostfile --map-by node ./bin/fire_mpi --mapa data/maps/map_$N.bin --pasos $PASOS | grep -E 'Procesos|Checksum|Tiempo'"

echo; echo "##### 7. RECURSOS #####"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" master worker1 worker2
echo; echo "DEMO COMPLETADA (checksum de referencia: $ref)"
