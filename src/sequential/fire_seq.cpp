// fire_seq.cpp - Version secuencial (T_1) del automata celular estocastico de incendio.
#include "fire_core.h"
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <utility>

int main(int argc, char** argv) {
    Params p;
    std::string ruta_mapa = "data/maps/map_512.bin";
    std::string salida = "output/seq";
    int pgm_cada = 0;
    std::string ruta_acc;

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
        else if (k == "--acciones") ruta_acc = sig();
        else { fprintf(stderr, "Argumento desconocido: %s\n", k.c_str()); return 1; }
    }

    Mapa m;
    if (!cargar_mapa(ruta_mapa, m)) {
        fprintf(stderr, "No se pudo leer el mapa: %s\n", ruta_mapa.c_str());
        return 1;
    }
    p.n = m.n;
    const int n = p.n;
    const size_t total = (size_t)n * n;
    const Vecinos vec = preparar_vecinos(p);
    std::vector<Accion> acc;
    size_t pos_acc = 0;
    if (!ruta_acc.empty() && !cargar_acciones(ruta_acc, acc)) {
        fprintf(stderr, "No se pudo leer el archivo de acciones: %s\n", ruta_acc.c_str());
        return 1;
    }

    // Doble buffer: se lee de 'cur' y se escribe en 'nxt'; luego se intercambian
    std::vector<uint8_t> cur = m.estado, nxt(total);
    if (pgm_cada > 0) {
        std::filesystem::create_directories(salida);
        char nombre[512];
        snprintf(nombre, sizeof nombre, "%s/paso_%04d.pgm", salida.c_str(), 0);
        escribir_pgm(nombre, cur.data(), n);
    }

    auto t0 = std::chrono::steady_clock::now();
    for (int t = 0; t < p.pasos; t++) {
        aplicar_acciones(cur.data(), n, acc, pos_acc, t);
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++)
                nxt[idx(i, j, n)] = nueva_celda(cur.data(), m.fuel.data(), m.hum.data(),
                                                i, j, n, p, vec, (uint64_t)t);
        std::swap(cur, nxt);
        if (pgm_cada > 0 && (t + 1) % pgm_cada == 0) {
            char nombre[512];
            snprintf(nombre, sizeof nombre, "%s/paso_%04d.pgm", salida.c_str(), t + 1);
            escribir_pgm(nombre, cur.data(), n);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    double seg = std::chrono::duration<double>(t1 - t0).count();

    size_t quemando = 0, quemada = 0, veg = 0;
    for (size_t i = 0; i < total; i++) {
        if (cur[i] == QUEMANDO) quemando++;
        else if (cur[i] == QUEMADA) quemada++;
        else if (cur[i] == VEGETACION) veg++;
    }
    uint64_t cs = checksum_estado(cur.data(), total);

    printf("=== Automata de incendio SECUENCIAL ===\n");
    printf("Malla        : %d x %d (%zu celdas)\n", n, n, total);
    printf("Pasos        : %d\n", p.pasos);
    printf("Semilla      : %llu\n", (unsigned long long)p.semilla);
    printf("Viento       : angulo %.0f, fuerza %.2f\n", p.viento_ang, p.viento_fuerza);
    printf("Acciones     : %zu procesadas\n", pos_acc);
    printf("Huella teorica: %.2f MB (2 buffers de estado + combustible + humedad)\n",
           4.0 * total / 1e6);
    printf("Estado final : quemando=%zu quemada=%zu vegetacion=%zu\n", quemando, quemada, veg);
    printf("Checksum     : %016llx\n", (unsigned long long)cs);
    printf("Tiempo T_1   : %.4f s\n", seg);
    printf("RESULT n=%d pasos=%d t=%.6f checksum=%016llx\n", n, p.pasos, seg,
           (unsigned long long)cs);
    return 0;
}
