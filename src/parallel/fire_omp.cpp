// fire_omp.cpp - Version OpenMP (memoria compartida) del automata de incendio.
// Misma regla que la secuencial (nueva_celda); solo cambia el bucle.
#include "fire_core.h"
#include <omp.h>
#include <cstdlib>
#include <filesystem>
#include <utility>

int main(int argc, char** argv) {
    Params p;
    std::string ruta_mapa = "data/maps/map_512.bin";
    std::string salida = "output/omp";
    int pgm_cada = 0;
    int hilos = 0;

    for (int a = 1; a < argc; a++) {
        std::string k = argv[a];
        auto sig = [&]() -> const char* { return (a + 1 < argc) ? argv[++a] : ""; };
        if (k == "--mapa") ruta_mapa = sig();
        else if (k == "--pasos") p.pasos = atoi(sig());
        else if (k == "--semilla") p.semilla = strtoull(sig(), nullptr, 10);
        else if (k == "--viento-ang") p.viento_ang = atof(sig());
        else if (k == "--viento-fuerza") p.viento_fuerza = atof(sig());
        else if (k == "--pgm-cada") pgm_cada = atoi(sig());
        else if (k == "--salida") salida = sig();
        else if (k == "--hilos") hilos = atoi(sig());
        else { fprintf(stderr, "Argumento desconocido: %s\n", k.c_str()); return 1; }
    }
    if (hilos > 0) omp_set_num_threads(hilos);

    Mapa m;
    if (!cargar_mapa(ruta_mapa, m)) {
        fprintf(stderr, "No se pudo leer el mapa: %s\n", ruta_mapa.c_str());
        return 1;
    }
    p.n = m.n;
    const int n = p.n;
    const size_t total = (size_t)n * n;
    const Vecinos vec = preparar_vecinos(p);

    // Doble buffer con punteros: se lee de pc y se escribe en pn; luego se intercambian
    std::vector<uint8_t> bufA = m.estado, bufB(total);
    uint8_t* pc = bufA.data();
    uint8_t* pn = bufB.data();
    const uint8_t* fuel = m.fuel.data();
    const uint8_t* hum = m.hum.data();

    if (pgm_cada > 0) {
        std::filesystem::create_directories(salida);
        char nombre[512];
        snprintf(nombre, sizeof nombre, "%s/paso_%04d.pgm", salida.c_str(), 0);
        escribir_pgm(nombre, pc, n);
    }

    int hilos_reales = 1;
    double t0 = omp_get_wtime();

    #pragma omp parallel
    {
        #pragma omp single
        hilos_reales = omp_get_num_threads();   // barrera implicita al terminar

        for (int t = 0; t < p.pasos; t++) {
            // Cada celda se escribe una sola vez y solo se lee de pc: sin carreras
            // Copias locales: evitan que el compilador recargue pc/pn/p (compartidos) en cada celda
            const auto cur = pc; auto nxt = pn; const Params pl = p;
            #pragma omp for schedule(runtime)
            for (int i = 0; i < n; i++)
                for (int j = 0; j < n; j++)
                    nxt[idx(i, j, n)] = nueva_celda(cur, fuel, hum, i, j, n, pl, vec, (uint64_t)t);
            // barrera implicita: todos terminaron de escribir pn

            #pragma omp single
            {
                std::swap(pc, pn);
                if (pgm_cada > 0 && (t + 1) % pgm_cada == 0) {
                    char nombre[512];
                    snprintf(nombre, sizeof nombre, "%s/paso_%04d.pgm", salida.c_str(), t + 1);
                    escribir_pgm(nombre, pc, n);
                }
            }
            // barrera implicita: nadie empieza el paso siguiente antes del swap
        }
    }
    double seg = omp_get_wtime() - t0;

    // Conteo de estados con reduction (sin contadores compartidos ni false sharing)
    long long quemando = 0, quemada = 0, veg = 0;
    #pragma omp parallel for reduction(+:quemando,quemada,veg)
    for (long long i = 0; i < (long long)total; i++) {
        if (pc[i] == QUEMANDO) quemando++;
        else if (pc[i] == QUEMADA) quemada++;
        else if (pc[i] == VEGETACION) veg++;
    }
    uint64_t cs = checksum_estado(pc, total);

    omp_sched_t kind; int chunk;
    omp_get_schedule(&kind, &chunk);
    const char* nom = kind == omp_sched_static ? "static" : kind == omp_sched_dynamic ? "dynamic"
                    : kind == omp_sched_guided ? "guided" : "auto";

    printf("=== Automata de incendio OPENMP ===\n");
    printf("Malla        : %d x %d (%zu celdas)\n", n, n, total);
    printf("Pasos        : %d\n", p.pasos);
    printf("Semilla      : %llu\n", (unsigned long long)p.semilla);
    printf("Hilos        : %d   Schedule: %s (chunk %d)\n", hilos_reales, nom, chunk);
    printf("Estado final : quemando=%lld quemada=%lld vegetacion=%lld\n", quemando, quemada, veg);
    printf("Checksum     : %016llx\n", (unsigned long long)cs);
    printf("Tiempo T_p   : %.4f s\n", seg);
    printf("RESULT n=%d pasos=%d hilos=%d t=%.6f checksum=%016llx\n", n, p.pasos, hilos_reales,
           seg, (unsigned long long)cs);
    return 0;
}
