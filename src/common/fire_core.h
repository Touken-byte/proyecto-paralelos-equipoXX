// fire_core.h - Regla de transicion, carga de mapa, checksum y salida PGM.
// Compartido por las versiones secuencial, OpenMP y MPI.
#pragma once
#include "fire_common.h"
#include <vector>
#include <string>
#include <cstdio>
#include <cstring>

struct Mapa {
    int n = 0;
    std::vector<uint8_t> estado, fuel, hum;
};

// Lee el formato binario generado por data/gen_map.py
inline bool cargar_mapa(const std::string& ruta, Mapa& m) {
    FILE* f = fopen(ruta.c_str(), "rb");
    if (!f) return false;
    char mg[4];
    uint32_t n = 0;
    if (fread(mg, 1, 4, f) != 4 || memcmp(mg, "FIRE", 4) != 0 || fread(&n, 4, 1, f) != 1) {
        fclose(f);
        return false;
    }
    size_t t = (size_t)n * n;
    m.n = (int)n;
    m.estado.resize(t); m.fuel.resize(t); m.hum.resize(t);
    bool ok = fread(m.estado.data(), 1, t, f) == t &&
              fread(m.fuel.data(), 1, t, f) == t &&
              fread(m.hum.data(), 1, t, f) == t;
    fclose(f);
    return ok;
}

// Vecindad de Moore (8 vecinas) con el factor de viento precalculado.
struct Vecinos {
    int di[8];
    int dj[8];
    double fv[8];
};

inline Vecinos preparar_vecinos(const Params& p) {
    Vecinos v;
    int k = 0;
    const double ang = p.viento_ang * 3.14159265358979323846 / 180.0;
    const double wx = std::cos(ang), wy = std::sin(ang);   // x = columnas (este), y = filas (sur)
    for (int di = -1; di <= 1; di++) {
        for (int dj = -1; dj <= 1; dj++) {
            if (di == 0 && dj == 0) continue;
            double norm = std::sqrt((double)(di * di + dj * dj));
            // El fuego se propaga de la vecina hacia la celda: direccion (-dj, -di)
            double dot = (-dj * wx - di * wy) / norm;
            double dist = (di != 0 && dj != 0) ? 0.7071067811865476 : 1.0;
            v.di[k] = di;
            v.dj[k] = dj;
            v.fv[k] = dist * std::exp(1.5 * p.viento_fuerza * dot);
            k++;
        }
    }
    return v;
}

// Nuevo estado de la celda (i,j). Solo LEE de 'cur' (paso anterior), nunca escribe:
// por eso se puede llamar desde cualquier hilo sin carreras (doble buffer).
inline uint8_t nueva_celda(const uint8_t* cur, const uint8_t* fuel, const uint8_t* hum,
                           int i, int j, int n, const Params& p, const Vecinos& v,
                           uint64_t paso) {
    const size_t c = idx(i, j, n);
    const uint8_t s = cur[c];

    if (s == QUEMANDO)
        return rng_celda(p.semilla, paso, c) < p.p_apagado ? QUEMADA : QUEMANDO;
    if (s != VEGETACION)
        return s;   // vacia, quemada, cortafuego y agua no cambian

    const double fh = 1.0 - 0.8 * (hum[c] / 255.0);   // mas humedad, menos contagio
    const double ff = fuel[c] / 255.0;                // mas combustible, mas contagio
    double no_enciende = 1.0;
    for (int k = 0; k < 8; k++) {
        const int ni = i + v.di[k], nj = j + v.dj[k];
        if (ni < 0 || ni >= n || nj < 0 || nj >= n) continue;
        if (cur[idx(ni, nj, n)] == QUEMANDO) {
            double pk = p.p_base * ff * fh * v.fv[k];
            if (pk > 0.95) pk = 0.95;
            no_enciende *= (1.0 - pk);
        }
    }
    if (no_enciende >= 1.0) return s;
    return rng_celda(p.semilla, paso, c) < (1.0 - no_enciende) ? QUEMANDO : VEGETACION;
}

// Checksum FNV-1a de 64 bits del estado de la malla
inline uint64_t checksum_estado(const uint8_t* d, size_t t) {
    uint64_t h = 1469598103934665603ULL;
    for (size_t i = 0; i < t; i++) {
        h ^= d[i];
        h *= 1099511628211ULL;
    }
    return h;
}

// PGM binario (P5). Valor de gris = estado * 40, para poder recolorear despues.
inline bool escribir_pgm(const std::string& ruta, const uint8_t* d, int n) {
    FILE* f = fopen(ruta.c_str(), "wb");
    if (!f) return false;
    fprintf(f, "P5\n%d %d\n255\n", n, n);
    std::vector<uint8_t> buf((size_t)n * n);
    for (size_t i = 0; i < buf.size(); i++) buf[i] = (uint8_t)(d[i] * 40);
    fwrite(buf.data(), 1, buf.size(), f);
    fclose(f);
    return true;
}
