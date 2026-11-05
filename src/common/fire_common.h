// fire_common.h - Estados, parámetros y utilidades compartidas
// por las versiones secuencial, OpenMP y MPI del autómata de incendio.
#pragma once
#include <cstdint>
#include <cstddef>
#include <cmath>

// Estados de cada celda del terreno
enum Estado : uint8_t {
    VACIA      = 0,  // claro sin combustible
    VEGETACION = 1,  // combustible, puede arder
    QUEMANDO   = 2,  // en llamas
    QUEMADA    = 3,  // ya consumida
    CORTAFUEGO = 4,  // barrera creada por el bombero
    AGUA       = 5   // río o cuerpo de agua, no arde
};

// Parámetros de la simulación
struct Params {
    int      n            = 512;   // lado de la malla (n x n)
    int      pasos        = 100;   // pasos (rondas) a simular
    uint64_t semilla      = 42;    // semilla del RNG determinista
    double   viento_ang   = 0.0;   // grados hacia donde sopla: 0=este, 90=sur
    double   viento_fuerza= 0.6;   // 0 = sin viento
    double   p_base       = 0.30;  // probabilidad base de contagio por vecina
    double   p_apagado    = 0.25;  // probabilidad por paso de que una celda deje de arder
};

// Índice lineal de la celda (fila i, columna j)
inline size_t idx(int i, int j, int n) {
    return (size_t)i * (size_t)n + (size_t)j;
}
