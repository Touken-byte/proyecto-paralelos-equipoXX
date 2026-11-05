#!/bin/bash
# Verifica que las acciones de jugador dan el mismo checksum en secuencial, OpenMP y MPI.
# Uso (desde el host): ./scripts/verify_acciones.sh   (variables opcionales: N, PASOS, SEMILLA)
N=${N:-512}; PASOS=${PASOS:-100}; SEMILLA=${SEMILLA:-42}

docker exec -i -u mpiuser -e N=$N -e PASOS=$PASOS -e SEMILLA=$SEMILLA master bash -s << 'EOS'
cd /home/mpiuser/proyecto || exit 1
mkdir -p bin output
FLAGS="-std=c++17 -O2 -Wall -Wextra -I src/common"
g++ $FLAGS src/sequential/fire_seq.cpp -o bin/fire_seq || exit 1
g++ $FLAGS -fopenmp src/parallel/fire_omp.cpp -o bin/fire_omp || exit 1
mpicxx $FLAGS src/parallel/fire_mpi.cpp -o bin/fire_mpi 2> /tmp/warn_mpi.txt || { cat /tmp/warn_mpi.txt; exit 1; }
MAPA=data/maps/map_$N.bin
[ -f "$MAPA" ] || python3 data/gen_map.py --n $N --seed 42 --out "$MAPA" > /dev/null
# Prueba de borde: cortafuegos en toda la columna central (cruza todos los bordes entre procesos MPI)
awk -v n=$N 'BEGIN{c=int(n/2); for(y=0;y<n;y++) print "0 CORTAFUEGO " c " " y; print "20 APAGAR 100 100"}' > output/acciones_borde.txt
cs() { grep -o 'checksum=[0-9a-f]*' | cut -d= -f2; }
fallos=0
chk() { if [ "$2" = "$ref" ]; then r="OK"; else r="FALLO"; fallos=$((fallos+1)); fi; printf "%-22s : %s  [%s]\n" "$1" "$2" "$r"; }

echo "=== Verificacion de acciones de jugador (n=$N, pasos=$PASOS, semilla=$SEMILLA) ==="
echo "Sin acciones (referencia del motor): $(./bin/fire_seq --mapa $MAPA --pasos $PASOS --semilla $SEMILLA | cs)"
for ACC in data/acciones_ejemplo.txt output/acciones_borde.txt; do
  echo ""; echo "--- $ACC ---"
  ref=$(./bin/fire_seq --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --acciones $ACC < /dev/null | cs)
  echo "Secuencial             : $ref"
  for sched in static dynamic guided; do for h in 1 2 4 8; do
    chk "OpenMP $sched h=$h" "$(OMP_SCHEDULE=$sched ./bin/fire_omp --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --hilos $h --acciones $ACC | cs)"
  done; done
  for np in 1 2 3 6; do
    chk "MPI np=$np" "$(mpirun -np $np --hostfile infrastructure/hostfile --map-by node ./bin/fire_mpi --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --acciones $ACC < /dev/null | cs)"
  done
done
echo ""
if [ $fallos -eq 0 ]; then echo "VERIFICACION EXITOSA: acciones identicas en secuencial, OpenMP y MPI"; else echo "VERIFICACION FALLIDA: $fallos diferencias"; exit 1; fi
EOS
