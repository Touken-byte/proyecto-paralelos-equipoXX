#!/bin/bash
# Benchmark secuencial vs OpenMP. Uso (desde el host): ./scripts/benchmark.sh
# Variables opcionales: SIZES="512 1024 2048" HILOS="1 2 4 8" PASOS=100 REPS=5 SEMILLA=42
SIZES=${SIZES:-"512 1024 2048"}; HILOS=${HILOS:-"1 2 4 8"}
PASOS=${PASOS:-100}; REPS=${REPS:-5}; SEMILLA=${SEMILLA:-42}

docker exec -i -u mpiuser -e SIZES="$SIZES" -e HILOS="$HILOS" -e PASOS=$PASOS -e REPS=$REPS -e SEMILLA=$SEMILLA master bash -s << 'EOS'
cd /home/mpiuser/proyecto || exit 1
mkdir -p bin output
FLAGS="-std=c++17 -O2 -Wall -Wextra -I src/common"
g++ $FLAGS src/sequential/fire_seq.cpp -o bin/fire_seq || exit 1
g++ $FLAGS -fopenmp src/parallel/fire_omp.cpp -o bin/fire_omp || exit 1

CSV=output/benchmark.csv
echo "modo,n,pasos,hilos,rep,tiempo_s,checksum" > $CSV
echo "=== Benchmark (pasos=$PASOS, repeticiones=$REPS, semilla=$SEMILLA) ==="
for n in $SIZES; do
  MAPA=data/maps/map_$n.bin
  [ -f "$MAPA" ] || python3 data/gen_map.py --n $n --seed 42 --out "$MAPA" > /dev/null
  for r in $(seq 1 $REPS); do
    l=$(./bin/fire_seq --mapa $MAPA --pasos $PASOS --semilla $SEMILLA | grep RESULT)
    t=$(echo "$l" | grep -o ' t=[0-9.]*' | cut -d= -f2); cs=$(echo "$l" | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2)
    echo "seq,$n,$PASOS,1,$r,$t,$cs" >> $CSV
  done
  echo "n=$n secuencial listo"
  for h in $HILOS; do
    for r in $(seq 1 $REPS); do
      l=$(./bin/fire_omp --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --hilos $h | grep RESULT)
      t=$(echo "$l" | grep -o ' t=[0-9.]*' | cut -d= -f2); cs=$(echo "$l" | grep -o 'checksum=[0-9a-f]*' | cut -d= -f2)
      echo "omp,$n,$PASOS,$h,$r,$t,$cs" >> $CSV
    done
    echo "n=$n omp hilos=$h listo"
  done
done

echo ""
echo "=== Resumen (promedio de $REPS corridas) ==="
echo "modo,n,hilos,tiempo_prom_s,speedup,eficiencia" > output/benchmark_resumen.csv
awk -F, 'NR>1 { k=$1","$2","$4; s[k]+=$6; c[k]++ }
END { for (k in s) { split(k,a,","); avg=s[k]/c[k]; b=s["seq,"a[2]",1"]/c["seq,"a[2]",1"];
      sp=b/avg; printf "%s,%s,%s,%.4f,%.3f,%.3f\n", a[1],a[2],a[3],avg,sp,sp/a[3] } }' $CSV \
  | sort -t, -k2,2n -k1,1r -k3,3n >> output/benchmark_resumen.csv
column -s, -t output/benchmark_resumen.csv
echo ""
echo "CSV completo: output/benchmark.csv"
EOS
