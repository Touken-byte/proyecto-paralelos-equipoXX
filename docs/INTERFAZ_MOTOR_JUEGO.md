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
| Acciones de jugadores | `--acciones archivo.txt`: lista de acciones aplicadas antes de simular cada paso (ver abajo) |

## Acciones de los jugadores (implementadas en secuencial, OpenMP y MPI)
| Acción | Jugador | Efecto sobre la malla |
|--------|---------|-----------------------|
| `APAGAR x y` | Bombero (mochila de agua) | Celda QUEMANDO pasa a QUEMADA (el fuego se extingue). Si la celda no está en llamas, no hace nada |
| `CORTAFUEGO x y` | Bombero | Celda VEGETACION pasa a CORTAFUEGO (no arde). Si es agua, está en llamas o ya quemada, no hace nada |
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
comunicación con el juego es por archivo de acciones (`--acciones`); un canal en tiempo real queda para el Hito 3.

## Formato del archivo de acciones
Una acción por línea: `PASO ACCION x y`, donde `x` es la columna e `y` la fila (origen arriba a la izquierda).
Las líneas que empiezan con `#` son comentarios. Ejemplo: `data/acciones_ejemplo.txt`.

- Las acciones con `PASO = t` se aplican sobre el estado actual, justo antes de calcular el paso `t`.
- Las coordenadas fuera de la malla se ignoran.
- Determinismo: el resultado (checksum) es idéntico en secuencial, OpenMP y MPI. En MPI cada proceso aplica solo las acciones de sus filas, antes del intercambio de halo.
- Verificación automática: `./scripts/verify_acciones.sh`.
- `RESCATE x y` es lógica del juego y no pasa por el motor.
