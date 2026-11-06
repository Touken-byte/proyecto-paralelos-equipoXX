#!/bin/bash
# Riesgo del Vigía sin y con cortafuegos (mismos parámetros y semilla).
# Uso (desde la raíz del repo): ./scripts/vigia_comparacion.sh
cd "$(dirname "$0")/.." || exit 1
MAPA=${MAPA:-data/maps/map_128.bin}; SIMS=${SIMS:-8}; PASOS=${PASOS:-50}
mkdir -p output/vigia
for k in $(seq 0 127); do echo "0 CORTAFUEGO $k 64"; done > data/acc_barrera_fila64.txt  # barrera = FILA 64 (x=k, y=64)
run() {
  docker exec -u mpiuser master bash -c "cd /home/mpiuser/proyecto && mpirun -np 3 --hostfile infrastructure/hostfile --map-by node ./bin/vigia_hibrido --mapa $MAPA --sims $SIMS --pasos $PASOS --hilos 2 --salida $1 $2 < /dev/null" | grep -E 'RESULT|riesgo >'
}
echo "== SIN cortafuegos =="; run output/vigia/sin_cortafuegos.pgm ""
echo "== CON cortafuegos =="; run output/vigia/con_cortafuegos.pgm "--acciones data/acc_barrera_fila64.txt"
