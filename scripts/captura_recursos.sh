#!/bin/bash
# Mantiene una carga OpenMP larga para tomar las capturas de htop y docker stats.
# Uso: ./scripts/captura_recursos.sh   (opcionales: HILOS=8 N=2048 PASOS=1500)
cd "$(dirname "$0")/.." || exit 1
HILOS=${HILOS:-8}; N=${N:-2048}; PASOS=${PASOS:-1500}
echo "Carga: OpenMP con $HILOS hilos, n=$N, $PASOS pasos."
echo "Abre OTRAS dos terminales y ejecuta:"
echo "  Terminal 2:  docker exec -it master htop"
echo "  Terminal 3:  docker stats"
echo "Toma las capturas mientras esta terminal este trabajando."
docker exec -u mpiuser master bash -c "cd /home/mpiuser/proyecto && ./bin/fire_omp --mapa data/maps/map_$N.bin --pasos $PASOS --hilos $HILOS | grep -E 'Hilos|Tiempo'"
