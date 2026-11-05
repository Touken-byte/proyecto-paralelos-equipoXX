#!/bin/bash
# Verifica que el Vigia da el mismo checksum con cualquier combinacion de procesos e hilos.
# Uso (desde el host): ./scripts/verify_vigia.sh   (opcionales: N, SIMS, PASOS)
N=${N:-512}; SIMS=${SIMS:-24}; PASOS=${PASOS:-60}

docker exec -i -u mpiuser -e N=$N -e SIMS=$SIMS -e PASOS=$PASOS master bash -s << 'EOS'
cd /home/mpiuser/proyecto || exit 1
mkdir -p bin
mpicxx -std=c++17 -O2 -Wall -Wextra -fopenmp -I src/common src/parallel/vigia_hibrido.cpp -o bin/vigia_hibrido || exit 1
MAPA=data/maps/map_$N.bin
[ -f "$MAPA" ] || python3 data/gen_map.py --n $N --seed 42 --out "$MAPA" > /dev/null

echo "=== Verificacion del Vigia (n=$N, sims=$SIMS, pasos=$PASOS) ==="
ref=""; fallos=0
for cfg in "1 1" "3 1" "2 4" "3 2" "6 1"; do
  set -- $cfg
  l=$(mpirun -np $1 --hostfile infrastructure/hostfile --map-by node ./bin/vigia_hibrido --mapa $MAPA --sims $SIMS --pasos $PASOS --hilos $2 --salida output/vigia/v.pgm < /dev/null | grep RESULT)
  cs=$(echo "$l" | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2)
  t=$(echo "$l" | grep -o ' t=[0-9.]*' | cut -d= -f2)
  [ -z "$ref" ] && ref=$cs
  if [ "$cs" = "$ref" ]; then r="OK"; else r="FALLO"; fallos=$((fallos+1)); fi
  printf "procesos=%s hilos=%s : %s  t=%ss  [%s]\n" $1 $2 "$cs" "$t" "$r"
done
echo ""
if [ $fallos -eq 0 ]; then echo "VERIFICACION VIGIA EXITOSA: checksums identicos"; else echo "VERIFICACION VIGIA FALLIDA: $fallos diferencias"; exit 1; fi
EOS
