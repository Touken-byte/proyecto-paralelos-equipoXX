// fire_mpi.cpp - Version MPI (memoria distribuida): descomposicion por filas con halo.
// Cada proceso calcula solo sus filas; en cada paso intercambia con sus vecinos
// la fila frontera (halo) mediante Isend/Irecv no bloqueantes.
// NOTA (esqueleto Hito 2): cada proceso guarda la malla completa para reutilizar
// nueva_celda sin cambios. En el Hito 3 se puede reducir a bloque local + 2 filas halo.
#include "fire_core.h"
#include <mpi.h>
#include <cstdlib>
#include <utility>

int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);
    int rank = 0, size = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    Params p;
    std::string ruta_mapa = "data/maps/map_512.bin";
    std::string ruta_acc;
    for (int a = 1; a < argc; a++) {
        std::string k = argv[a];
        auto sig = [&]() -> const char* { return (a + 1 < argc) ? argv[++a] : ""; };
        if (k == "--mapa") ruta_mapa = sig();
        else if (k == "--pasos") p.pasos = atoi(sig());
        else if (k == "--semilla") p.semilla = strtoull(sig(), nullptr, 10);
        else if (k == "--viento-ang") p.viento_ang = atof(sig());
        else if (k == "--viento-fuerza") p.viento_fuerza = atof(sig());
        else if (k == "--acciones") ruta_acc = sig();
        else { if (rank == 0) fprintf(stderr, "Argumento desconocido: %s\n", k.c_str()); MPI_Finalize(); return 1; }
    }

    Mapa m;
    if (!cargar_mapa(ruta_mapa, m)) {
        if (rank == 0) fprintf(stderr, "No se pudo leer el mapa: %s\n", ruta_mapa.c_str());
        MPI_Finalize();
        return 1;
    }
    p.n = m.n;
    const int n = p.n;
    const size_t total = (size_t)n * n;
    const Vecinos vec = preparar_vecinos(p);

    // Todos los procesos cargan la lista (pequena); cada uno aplica solo las acciones de sus filas
    std::vector<Accion> acc;
    size_t pos_acc = 0;
    if (!ruta_acc.empty() && !cargar_acciones(ruta_acc, acc)) {
        if (rank == 0) fprintf(stderr, "No se pudo leer el archivo de acciones: %s\n", ruta_acc.c_str());
        MPI_Finalize();
        return 1;
    }

    // Reparto de filas: las primeras 'resto' filas-bloque llevan una fila extra
    const int base = n / size, resto = n % size;
    auto filas_de = [&](int r) { return base + (r < resto ? 1 : 0); };
    auto inicio_de = [&](int r) { return r * base + (r < resto ? r : resto); };
    const int ini = inicio_de(rank), nf = filas_de(rank), fin = ini + nf;

    std::vector<uint8_t> bufA = m.estado, bufB(total);
    uint8_t* pc = bufA.data();
    uint8_t* pn = bufB.data();
    const uint8_t* fuel = m.fuel.data();
    const uint8_t* hum = m.hum.data();

    MPI_Barrier(MPI_COMM_WORLD);
    double t0 = MPI_Wtime();

    for (int t = 0; t < p.pasos; t++) {
        // 0) Acciones de jugador sobre las filas propias, ANTES del halo: el vecino recibe la fila ya modificada
        aplicar_acciones(pc, n, acc, pos_acc, t, ini, fin);

        // 1) Intercambio de halo (no bloqueante, sin riesgo de deadlock)
        MPI_Request req[4];
        int nreq = 0;
        if (rank > 0) {
            MPI_Irecv(pc + (size_t)(ini - 1) * n, n, MPI_UNSIGNED_CHAR, rank - 1, 0, MPI_COMM_WORLD, &req[nreq++]);
            MPI_Isend(pc + (size_t)ini * n,       n, MPI_UNSIGNED_CHAR, rank - 1, 1, MPI_COMM_WORLD, &req[nreq++]);
        }
        if (rank < size - 1) {
            MPI_Irecv(pc + (size_t)fin * n,       n, MPI_UNSIGNED_CHAR, rank + 1, 1, MPI_COMM_WORLD, &req[nreq++]);
            MPI_Isend(pc + (size_t)(fin - 1) * n, n, MPI_UNSIGNED_CHAR, rank + 1, 0, MPI_COMM_WORLD, &req[nreq++]);
        }
        MPI_Waitall(nreq, req, MPI_STATUSES_IGNORE);

        // 2) Calculo de las filas propias (lee pc, escribe pn)
        for (int i = ini; i < fin; i++)
            for (int j = 0; j < n; j++)
                pn[idx(i, j, n)] = nueva_celda(pc, fuel, hum, i, j, n, p, vec, (uint64_t)t);
        std::swap(pc, pn);
    }

    MPI_Barrier(MPI_COMM_WORLD);
    double seg = MPI_Wtime() - t0;

    // Conteo local y reduccion global
    long long loc[3] = {0, 0, 0}, glob[3] = {0, 0, 0};
    for (size_t c = (size_t)ini * n; c < (size_t)fin * n; c++) {
        if (pc[c] == QUEMANDO) loc[0]++;
        else if (pc[c] == QUEMADA) loc[1]++;
        else if (pc[c] == VEGETACION) loc[2]++;
    }
    MPI_Reduce(loc, glob, 3, MPI_LONG_LONG, MPI_SUM, 0, MPI_COMM_WORLD);

    // Recoleccion de la malla en el proceso 0 para el checksum
    std::vector<int> cnt(size), dsp(size);
    for (int r = 0; r < size; r++) { cnt[r] = filas_de(r) * n; dsp[r] = inicio_de(r) * n; }
    std::vector<uint8_t> final_(rank == 0 ? total : 1);
    MPI_Gatherv(pc + (size_t)ini * n, nf * n, MPI_UNSIGNED_CHAR,
                final_.data(), cnt.data(), dsp.data(), MPI_UNSIGNED_CHAR, 0, MPI_COMM_WORLD);

    if (rank == 0) {
        uint64_t cs = checksum_estado(final_.data(), total);
        printf("=== Automata de incendio MPI ===\n");
        printf("Malla        : %d x %d (%zu celdas)\n", n, n, total);
        printf("Pasos        : %d\n", p.pasos);
        printf("Semilla      : %llu\n", (unsigned long long)p.semilla);
        printf("Procesos     : %d\n", size);
        printf("Acciones     : %zu procesadas\n", pos_acc);
        printf("Estado final : quemando=%lld quemada=%lld vegetacion=%lld\n", glob[0], glob[1], glob[2]);
        printf("Checksum     : %016llx\n", (unsigned long long)cs);
        printf("Tiempo T_p   : %.4f s\n", seg);
        printf("RESULT n=%d pasos=%d procs=%d t=%.6f checksum=%016llx\n", n, p.pasos, size, seg,
               (unsigned long long)cs);
    }
    MPI_Finalize();
    return 0;
}
