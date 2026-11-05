#!/bin/bash
# Mediciones oficiales en la Dell. Uso (desde cualquier carpeta): ./scripts/dell_medicion.sh
# Variables opcionales: CPUS_NODO=16  HILOS="1 2 4 8 16"
cd "$(dirname "$0")/.." || exit 1
export CPUS_NODO=${CPUS_NODO:-16}
export HILOS=${HILOS:-"1 2 4 8 16"}
export SIZES=${SIZES:-"512 1024 2048"}
export REPS=${REPS:-5}
# Limitar a las CPUs logicas reales del host (evita rechazo de Docker y sobresuscripcion)
LOGICAS=$(nproc)
if [ "$CPUS_NODO" -gt "$LOGICAS" ]; then CPUS_NODO=$LOGICAS; export CPUS_NODO; fi
H_OK=""
for h in $HILOS; do [ "$h" -le "$LOGICAS" ] && H_OK="$H_OK $h"; done
HILOS=$(echo $H_OK); export HILOS
echo "CPUs logicas del host: $LOGICAS -> CPUS_NODO=$CPUS_NODO HILOS=\"$HILOS\""
NMAX=${NMAX:-2048}
SIMS=${SIMS:-48}
OUT=docs/resultados_dell
mkdir -p $OUT docs/evidencias docs/graficas output bin data/maps
chmod -R a+rwX output bin data docs 2>/dev/null
X="docker exec -u mpiuser master bash -c"

echo "##### 1. CLUSTER (cpus por nodo: $CPUS_NODO) #####"
docker compose -f infrastructure/docker-compose.yml up -d --build --force-recreate
sleep 10

echo "##### 2. DATOS DEL SISTEMA #####"
{ echo "### lscpu"; LC_ALL=C lscpu; echo; echo "### nproc"; nproc; echo; echo "### memoria"; free -h
  echo; echo "### sistema"; uname -a; docker --version; echo; echo "### asignacion por nodo"
  echo "cpus=$CPUS_NODO mem_limit=8g (3 nodos comparten la misma CPU fisica)"; } > $OUT/sistema.txt
$X "gcc --version | head -1; mpirun --version | head -1" >> $OUT/sistema.txt
LC_ALL=C lscpu | grep -E "Model name|^CPU\(s\)|Thread|Core|Socket"; nproc; free -h | head -2

echo; echo "##### 3. COMPILACION #####"
$X "cd /home/mpiuser/proyecto && F='-std=c++17 -O2 -Wall -Wextra -I src/common' &&
  mpicxx \$F src/parallel/fire_mpi.cpp -o bin/fire_mpi &&
  mpicxx \$F -fopenmp src/parallel/vigia_hibrido.cpp -o bin/vigia_hibrido && echo Compilacion OK"

echo; echo "##### 4. BENCHMARK OPENMP (puede tardar varios minutos) #####"
./scripts/benchmark.sh | tee $OUT/benchmark_salida.txt
cp output/benchmark.csv output/benchmark_resumen.csv $OUT/

echo; echo "##### 5. HUELLA DE MEMORIA #####"
: > $OUT/memoria.txt
for n in $SIZES; do
  echo "n=$n" >> $OUT/memoria.txt
  $X "cd /home/mpiuser/proyecto && /usr/bin/time -v ./bin/fire_seq --mapa data/maps/map_$n.bin --pasos 100 2>&1 >/dev/null | grep -E 'Maximum resident|Elapsed'" >> $OUT/memoria.txt
done
cat $OUT/memoria.txt

echo; echo "##### 6. MPI (n=$NMAX, 100 pasos) #####"
for np in 1 2 3 6; do
  $X "cd /home/mpiuser/proyecto && mpirun -np $np --hostfile infrastructure/hostfile --map-by node ./bin/fire_mpi --mapa data/maps/map_$NMAX.bin --pasos 100 | grep RESULT"
done | tee $OUT/mpi.txt

echo; echo "##### 7. VIGIA (n=512, $SIMS simulaciones, 100 pasos) #####"
for cfg in "1 1" "1 4" "3 1" "3 4"; do
  set -- $cfg
  $X "cd /home/mpiuser/proyecto && mpirun -np $1 --hostfile infrastructure/hostfile --map-by node ./bin/vigia_hibrido --mapa data/maps/map_512.bin --sims $SIMS --pasos 100 --hilos $2 --salida output/vigia/riesgo_dell.pgm | grep RESULT"
done | tee $OUT/vigia.txt

echo; echo "##### 8. IMAGENES Y ANALISIS #####"
$X "cd /home/mpiuser/proyecto && ./bin/fire_seq --mapa data/maps/map_512.bin --pasos 100 --pgm-cada 50 --salida output/seq_512 > /dev/null"
python3 scripts/pgm2png.py --montaje docs/evidencias/E09_mapa_incendio_dell.png output/seq_512/paso_0000.pgm output/seq_512/paso_0050.pgm output/seq_512/paso_0100.pgm
python3 scripts/heat2png.py output/vigia/riesgo_dell.pgm
cp output/vigia/riesgo_dell.png docs/evidencias/E17_vigia_riesgo_dell.png
python3 scripts/analisis.py $OUT/benchmark.csv docs/graficas | tee $OUT/analisis.txt

echo; echo "MEDICION TERMINADA. Resultados en $OUT/ y docs/graficas/"
