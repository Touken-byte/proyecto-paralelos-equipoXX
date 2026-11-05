# Interfaz entre el juego y el motor de simulación

El motor es un programa independiente (C++ con OpenMP/MPI). El juego no calcula
el fuego: envía un estado y acciones, y recibe la malla actualizada tras cada ronda.

## Entradas
| Dato | Descripción |
|------|-------------|
| Mapa | Archivo binario `FIRE` generado por `data/gen_map.py` (estado, combustible, humedad) |
| Viento | `--viento-ang` (grados, 0=este, 90=sur) y `--viento-fuerza` (0 a 1) |
| Semilla | `--semilla`, garantiza reproducibilidad |
| Pasos | `--pasos`, cantidad de actualizaciones del autómata por ronda |
| Acciones de jugadores | Lista de acciones aplicadas antes de simular la ronda (ver abajo) |

## Acciones de los jugadores (diseño; se implementa en el Hito 3)
| Acción | Jugador | Efecto sobre la malla |
|--------|---------|-----------------------|
| `APAGAR x y` | Bombero (mochila de agua) | Celda QUEMANDO pasa a VEGETACION húmeda o QUEMADA |
| `CORTAFUEGO x y` | Bombero | Celda pasa a CORTAFUEGO (no arde) |
| `RESCATE x y` | Veterinaria | Lógica del juego; el motor solo informa si la celda está en llamas |

## Salida por ronda
- Malla `n x n` con estados: 0 vacía, 1 vegetación, 2 quemando, 3 quemada, 4 cortafuego, 5 agua.
- Conteos: celdas quemando, quemadas y con vegetación.
- Checksum del estado (para verificar reproducibilidad).
- Tiempo de cómputo de la ronda.

## Ciclo de una ronda
1. Los jugadores se mueven y ejecutan acciones.
2. El juego envía las acciones al motor.
3. El motor aplica las acciones y avanza el incendio.
4. El motor devuelve la malla; el juego la dibuja y evalúa objetivos (animales en riesgo, refugios).

## Estado actual (Hito 2)
El motor se ejecuta por línea de comandos y genera PGM/PNG por paso. La
comunicación con el juego queda definida aquí y se implementa en el Hito 3.
