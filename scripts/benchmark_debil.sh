#!/bin/bash
# Escalabilidad debil: la carga por hilo es constante (n = N0 * raiz(p)).
# Uso (desde el host): ./scripts/benchmark_debil.sh
# Variables opcionales: N0=512 HILOS="1 2 4 8" PASOS=100 REPS=5 SEMILLA=42
N0=${N0:-512}; HILOS=${HILOS:-"1 2 4 8"}
PASOS=${PASOS:-100}; REPS=${REPS:-5}; SEMILLA=${SEMILLA:-42}

docker exec -i -u mpiuser -e N0=$N0 -e HILOS="$HILOS" -e PASOS=$PASOS -e REPS=$REPS -e SEMILLA=$SEMILLA master bash -s << 'EOS'
cd /home/mpiuser/proyecto || exit 1
mkdir -p bin output
FLAGS="-std=c++17 -O2 -Wall -Wextra -I src/common"
g++ $FLAGS -fopenmp src/parallel/fire_omp.cpp -o bin/fire_omp || exit 1
CSV=output/benchmark_debil.csv
echo "n,hilos,rep,tiempo_s,checksum" > $CSV
echo "=== Escalabilidad debil (N0=$N0, pasos=$PASOS, repeticiones=$REPS) ==="
for h in $HILOS; do
  n=$(awk -v a=$N0 -v h=$h 'BEGIN{printf "%d", a*sqrt(h)+0.5}')
  MAPA=data/maps/map_$n.bin
  [ -f "$MAPA" ] || python3 data/gen_map.py --n $n --seed 42 --out "$MAPA" > /dev/null
  for r in $(seq 1 $REPS); do
    l=$(./bin/fire_omp --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --hilos $h | grep RESULT)
    t=$(echo "$l" | grep -o ' t=[0-9.]*' | cut -d= -f2); cs=$(echo "$l" | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2)
    echo "$n,$h,$r,$t,$cs" >> $CSV
  done
  echo "hilos=$h n=$n listo"
done
EOS
