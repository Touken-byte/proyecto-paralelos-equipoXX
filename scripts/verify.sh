#!/bin/bash
# Verifica que OpenMP produce el mismo checksum que la version secuencial.
# Uso (desde el host): ./scripts/verify.sh        (variables opcionales: N, PASOS, SEMILLA)
N=${N:-512}; PASOS=${PASOS:-100}; SEMILLA=${SEMILLA:-42}

docker exec -i -u mpiuser -e N=$N -e PASOS=$PASOS -e SEMILLA=$SEMILLA master bash -s << 'EOS'
cd /home/mpiuser/proyecto || exit 1
mkdir -p bin
FLAGS="-std=c++17 -O2 -Wall -Wextra -I src/common"
g++ $FLAGS src/sequential/fire_seq.cpp -o bin/fire_seq || exit 1
g++ $FLAGS -fopenmp src/parallel/fire_omp.cpp -o bin/fire_omp || exit 1
MAPA=data/maps/map_$N.bin
[ -f "$MAPA" ] || python3 data/gen_map.py --n $N --seed 42 --out "$MAPA" > /dev/null

echo "=== Verificacion secuencial vs OpenMP (n=$N, pasos=$PASOS, semilla=$SEMILLA) ==="
ref=$(./bin/fire_seq --mapa $MAPA --pasos $PASOS --semilla $SEMILLA | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2)
echo "Secuencial            : $ref"
fallos=0
for sched in static dynamic guided; do
  for h in 1 2 4 8; do
    cs=$(OMP_SCHEDULE=$sched ./bin/fire_omp --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --hilos $h | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2)
    if [ "$cs" = "$ref" ]; then r="OK"; else r="FALLO"; fallos=$((fallos+1)); fi
    printf "OpenMP %-8s h=%d : %s  [%s]\n" "$sched" "$h" "$cs" "$r"
  done
done
echo ""
if [ $fallos -eq 0 ]; then echo "VERIFICACION EXITOSA: todos los checksums son identicos"; else echo "VERIFICACION FALLIDA: $fallos diferencias"; exit 1; fi
EOS
