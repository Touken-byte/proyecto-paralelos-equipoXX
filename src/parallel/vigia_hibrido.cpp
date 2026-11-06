// vigia_hibrido.cpp - El Vigia: Monte Carlo del incendio, hibrido MPI + OpenMP.
// MPI reparte simulaciones entre procesos (cada proceso toma s = rank, rank+size, ...);
// OpenMP las reparte entre hilos; cada hilo acumula en su propio mapa y luego se suman.
// Cada simulacion usa su propia semilla derivada, y la suma de enteros es conmutativa:
// el resultado es identico sin importar procesos o hilos (verificable con checksum).
#include "fire_core.h"
#include <mpi.h>
#include <omp.h>
#include <cstdlib>
#include <filesystem>
#include <utility>

int main(int argc, char** argv) {
    int provided = 0;
    MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &provided);
    std::string ruta_acc;
    int rank = 0, size = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    if (provided < MPI_THREAD_FUNNELED && rank == 0)
        fprintf(stderr, "Aviso: MPI no ofrece MPI_THREAD_FUNNELED\n");

    Params p;
    std::string ruta_mapa = "data/maps/map_512.bin";
    std::string salida = "output/vigia/riesgo.pgm";
    int sims = 64, hilos = 1;
    for (int a = 1; a < argc; a++) {
        std::string k = argv[a];
        auto sig = [&]() -> const char* { return (a + 1 < argc) ? argv[++a] : ""; };
        if (k == "--mapa") ruta_mapa = sig();
        else if (k == "--sims") sims = atoi(sig());
        else if (k == "--pasos") p.pasos = atoi(sig());
        else if (k == "--semilla") p.semilla = strtoull(sig(), nullptr, 10);
        else if (k == "--viento-ang") p.viento_ang = atof(sig());
        else if (k == "--viento-fuerza") p.viento_fuerza = atof(sig());
        else if (k == "--hilos") hilos = atoi(sig());
        else if (k == "--salida") salida = sig();
        else if (k == "--acciones") ruta_acc = sig();
        else { if (rank == 0) fprintf(stderr, "Argumento desconocido: %s\n", k.c_str()); MPI_Finalize(); return 1; }
    }
    if (hilos > 0) omp_set_num_threads(hilos);

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
    const uint8_t* fuel = m.fuel.data();
    const uint8_t* hum = m.hum.data();

    const int mis = (sims - rank + size - 1) / size;   // simulaciones de este proceso
    std::vector<Accion> acciones;
    if (!ruta_acc.empty()) cargar_acciones(ruta_acc, acciones);
    std::vector<uint32_t> acc_rank(total, 0);
    int hilos_reales = 1;

    MPI_Barrier(MPI_COMM_WORLD);
    double t0 = MPI_Wtime();

    #pragma omp parallel
    {
        #pragma omp single
        hilos_reales = omp_get_num_threads();

        std::vector<uint32_t> acc(total, 0);          // mapa privado del hilo
        std::vector<uint8_t> A(total), B(total);      // doble buffer privado del hilo

        #pragma omp for schedule(dynamic, 1)
        for (int k = 0; k < mis; k++) {
            const int s = rank + k * size;
            Params ps = p;
            ps.semilla = mezclar64(p.semilla ^ mezclar64((uint64_t)s + 1));
            A = m.estado;
            uint8_t* pc = A.data();
            uint8_t* pn = B.data();
            size_t pos_acc = 0;
            for (int t = 0; t < p.pasos; t++) {
                aplicar_acciones(pc, n, acciones, pos_acc, t);
                for (int i = 0; i < n; i++)
                    for (int j = 0; j < n; j++)
                        pn[idx(i, j, n)] = nueva_celda(pc, fuel, hum, i, j, n, ps, vec, (uint64_t)t);
                std::swap(pc, pn);
            }
            for (size_t c = 0; c < total; c++)
                if (pc[c] == QUEMANDO || pc[c] == QUEMADA) acc[c]++;
        }

        #pragma omp critical
        for (size_t c = 0; c < total; c++) acc_rank[c] += acc[c];
    }

    std::vector<uint32_t> glob(rank == 0 ? total : 1);
    MPI_Reduce(acc_rank.data(), glob.data(), (int)total, MPI_UNSIGNED, MPI_SUM, 0, MPI_COMM_WORLD);
    MPI_Barrier(MPI_COMM_WORLD);
    double seg = MPI_Wtime() - t0;

    if (rank == 0) {
        uint64_t cs = checksum_estado((const uint8_t*)glob.data(), total * sizeof(uint32_t));
        double suma = 0; size_t alto = 0, tocadas = 0;
        std::vector<uint8_t> img(total);
        for (size_t c = 0; c < total; c++) {
            suma += glob[c];
            if (glob[c] > 0) tocadas++;
            if ((uint64_t)glob[c] * 2 > (uint64_t)sims) alto++;
            img[c] = (uint8_t)((255.0 * glob[c]) / sims + 0.5);
        }
        std::filesystem::path pth(salida);
        if (pth.has_parent_path()) std::filesystem::create_directories(pth.parent_path());
        FILE* f = fopen(salida.c_str(), "wb");
        if (f) { fprintf(f, "P5\n%d %d\n255\n", n, n); fwrite(img.data(), 1, total, f); fclose(f); }

        printf("=== EL VIGIA: Monte Carlo hibrido MPI+OpenMP ===\n");
        printf("Malla        : %d x %d\n", n, n);
        printf("Simulaciones : %d   Pasos por simulacion: %d\n", sims, p.pasos);
        printf("Procesos MPI : %d   Hilos por proceso: %d\n", size, hilos_reales);
        printf("Celdas alguna vez afectadas : %zu (%.1f%%)\n", tocadas, 100.0 * tocadas / total);
        printf("Celdas con riesgo > 50%%     : %zu (%.1f%%)\n", alto, 100.0 * alto / total);
        printf("Probabilidad media de quema : %.4f\n", suma / ((double)total * sims));
        printf("Checksum     : %016llx\n", (unsigned long long)cs);
        printf("Tiempo       : %.4f s\n", seg);
        printf("Mapa de riesgo: %s\n", salida.c_str());
        printf("RESULT n=%d sims=%d pasos=%d procs=%d hilos=%d t=%.6f checksum=%016llx\n",
               n, sims, p.pasos, size, hilos_reales, seg, (unsigned long long)cs);
    }
    MPI_Finalize();
    return 0;
}
