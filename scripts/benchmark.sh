#!/bin/bash
# Benchmark completo: secuencial, OpenMP, MPI y Vigia hibrido (MPI+OpenMP). Uso (desde el host): ./scripts/benchmark.sh
# Variables opcionales: SIZES="512 1024 2048" HILOS="1 2 4 8" NPS="1 2 3 6" PASOS=100 REPS=5 SEMILLA=42 SIMS=24
SIZES=${SIZES:-"512 1024 2048"}; HILOS=${HILOS:-"1 2 4 8"}; NPS=${NPS:-"1 2 3 6"}
PASOS=${PASOS:-100}; REPS=${REPS:-5}; SEMILLA=${SEMILLA:-42}; SIMS=${SIMS:-24}
cd "$(dirname "$0")/.." || exit 1
if ! docker ps --format '{{.Names}}' | grep -qx master; then
  echo "Levantando el cluster (docker compose up --build)..."
  docker compose -f infrastructure/docker-compose.yml up -d --build || exit 1
  sleep 5
fi

docker exec -i -u mpiuser -e SIZES="$SIZES" -e HILOS="$HILOS" -e NPS="$NPS" -e PASOS=$PASOS -e REPS=$REPS -e SEMILLA=$SEMILLA -e SIMS=$SIMS master bash -s << 'EOS'
cd /home/mpiuser/proyecto || exit 1
mkdir -p bin output output/vigia
FLAGS="-std=c++17 -O2 -Wall -Wextra -I src/common"
g++ $FLAGS src/sequential/fire_seq.cpp -o bin/fire_seq || exit 1
g++ $FLAGS -fopenmp src/parallel/fire_omp.cpp -o bin/fire_omp || exit 1
mpicxx $FLAGS src/parallel/fire_mpi.cpp -o bin/fire_mpi || exit 1
mpicxx $FLAGS -fopenmp src/parallel/vigia_hibrido.cpp -o bin/vigia_hibrido || exit 1

CSV=output/benchmark.csv; CSVM=output/benchmark_mpi.csv; CSVV=output/benchmark_vigia.csv
echo "modo,n,pasos,hilos,rep,tiempo_s,checksum" > $CSV
echo "modo,n,pasos,procesos,rep,tiempo_s,checksum" > $CSVM
echo "procesos,hilos,sims,rep,tiempo_s,checksum" > $CSVV
AVISOS=0
campo() { echo "$1" | grep -o "$2" | head -1 | cut -d= -f2; }
reg() {  # archivo modo n unidad rep linea
  local t cs
  t=$(campo "$6" ' t=[0-9.]*'); cs=$(campo "$6" 'checksum=[0-9a-f]*')
  if [ -z "$t" ] || [ -z "$cs" ]; then echo "AVISO: sin resultado ($2 n=$3 unidades=$4 rep=$5)"; AVISOS=$((AVISOS+1)); return; fi
  echo "$2,$3,$PASOS,$4,$5,$t,$cs" >> $1
}

echo "Esperando SSH entre nodos..."
for i in $(seq 1 15); do
  mpirun -np 3 --hostfile infrastructure/hostfile --map-by node hostname < /dev/null > /dev/null 2>&1 && break
  sleep 2
done

echo "=== Benchmark (pasos=$PASOS, repeticiones=$REPS, semilla=$SEMILLA) ==="
for n in $SIZES; do
  MAPA=data/maps/map_$n.bin
  [ -f "$MAPA" ] || python3 data/gen_map.py --n $n --seed 42 --out "$MAPA" > /dev/null
  for r in $(seq 1 $REPS); do
    l=$(./bin/fire_seq --mapa $MAPA --pasos $PASOS --semilla $SEMILLA | grep RESULT)
    reg $CSV seq $n 1 $r "$l"
  done
  echo "n=$n secuencial listo"
  for h in $HILOS; do
    for r in $(seq 1 $REPS); do
      l=$(./bin/fire_omp --mapa $MAPA --pasos $PASOS --semilla $SEMILLA --hilos $h | grep RESULT)
      reg $CSV omp $n $h $r "$l"
    done
    echo "n=$n omp hilos=$h listo"
  done
  for np in $NPS; do
    for r in $(seq 1 $REPS); do
      l=$(mpirun -np $np --bind-to none --hostfile infrastructure/hostfile --map-by node ./bin/fire_mpi --mapa $MAPA --pasos $PASOS --semilla $SEMILLA < /dev/null 2>/dev/null | grep RESULT)
      reg $CSVM mpi $n $np $r "$l"
    done
    echo "n=$n mpi procesos=$np listo"
  done
done

MV=data/maps/map_512.bin
[ -f "$MV" ] || python3 data/gen_map.py --n 512 --seed 42 --out "$MV" > /dev/null
for cfg in "1 1" "1 4" "3 1" "3 4"; do
  set -- $cfg
  for r in $(seq 1 $REPS); do
    l=$(mpirun -np $1 --bind-to none --hostfile infrastructure/hostfile --map-by node ./bin/vigia_hibrido --mapa $MV --sims $SIMS --pasos $PASOS --hilos $2 --semilla $SEMILLA --salida output/vigia/riesgo.pgm < /dev/null 2>/dev/null | grep RESULT)
    t=$(campo "$l" ' t=[0-9.]*'); cs=$(campo "$l" 'checksum=[0-9a-f]*')
    if [ -z "$t" ] || [ -z "$cs" ]; then echo "AVISO: Vigia sin resultado (np=$1 hilos=$2 rep=$r)"; AVISOS=$((AVISOS+1)); continue; fi
    echo "$1,$2,$SIMS,$r,$t,$cs" >> $CSVV
  done
  echo "vigia procesos=$1 hilos=$2 listo"
done

echo ""
echo "=== Resumen OpenMP (promedio de $REPS corridas) ==="
echo "modo,n,hilos,tiempo_prom_s,speedup,eficiencia" > output/benchmark_resumen.csv
awk -F, 'NR>1 { k=$1","$2","$4; s[k]+=$6; c[k]++ }
END { for (k in s) { split(k,a,","); avg=s[k]/c[k]; b=s["seq,"a[2]",1"]/c["seq,"a[2]",1"];
      sp=b/avg; printf "%s,%s,%s,%.4f,%.3f,%.3f\n", a[1],a[2],a[3],avg,sp,sp/a[3] } }' $CSV \
  | sort -t, -k2,2n -k1,1r -k3,3n >> output/benchmark_resumen.csv
awk -F, '{printf "%-6s %-6s %-6s %-15s %-9s %-9s\n",$1,$2,$3,$4,$5,$6}' output/benchmark_resumen.csv

echo ""
echo "=== Resumen MPI (speedup contra secuencial) ==="
echo "modo,n,procesos,tiempo_prom_s,speedup,eficiencia" > output/benchmark_mpi_resumen.csv
awk -F, 'NR==FNR { if (FNR>1 && $1=="seq") { s[$2]+=$6; c[$2]++ } next }
FNR>1 { k=$2","$4; t[k]+=$6; m[k]++ }
END { for (k in t) { split(k,a,","); avg=t[k]/m[k]; b=s[a[1]]/c[a[1]];
      printf "mpi,%s,%s,%.4f,%.3f,%.3f\n", a[1],a[2],avg,b/avg,b/avg/a[2] } }' $CSV $CSVM \
  | sort -t, -k2,2n -k3,3n >> output/benchmark_mpi_resumen.csv
awk -F, '{printf "%-6s %-6s %-9s %-15s %-9s %-9s\n",$1,$2,$3,$4,$5,$6}' output/benchmark_mpi_resumen.csv

echo ""
echo "=== Resumen Vigia hibrido (n=512, $SIMS simulaciones) ==="
echo "procesos,hilos,tiempo_prom_s,speedup" > output/benchmark_vigia_resumen.csv
awk -F, 'NR>1 { k=$1","$2; s[k]+=$5; c[k]++ }
END { b=s["1,1"]/c["1,1"]; for (k in s) { a=s[k]/c[k]; printf "%s,%.4f,%.3f\n", k,a,b/a } }' $CSVV | sort >> output/benchmark_vigia_resumen.csv
awk -F, '{printf "%-9s %-6s %-15s %-9s\n",$1,$2,$3,$4}' output/benchmark_vigia_resumen.csv

echo ""
echo "=== Verificacion de checksums ==="
malos=0
for n in $SIZES; do
  ref=$(grep "^seq,$n," $CSV | head -1 | cut -d, -f7)
  b=$(cat $CSV $CSVM | awk -F, -v n=$n -v r=$ref '$2==n && $1!="modo" && $7!=r' | wc -l)
  echo "n=$n referencia=$ref discrepancias=$b"
  malos=$((malos+b))
done
distintos=$(tail -n +2 $CSVV | cut -d, -f6 | sort -u | wc -l)
echo "Vigia: checksums distintos entre configuraciones = $((distintos>0 ? distintos-1 : 0))"
echo ""
echo "CSV: output/benchmark.csv, output/benchmark_mpi.csv, output/benchmark_vigia.csv"
if [ $malos -eq 0 ] && [ $distintos -le 1 ] && [ $AVISOS -eq 0 ]; then echo "VERIFICACION EXITOSA"; else echo "VERIFICACION CON PROBLEMAS (discrepancias=$malos, avisos=$AVISOS)"; exit 1; fi
EOS
