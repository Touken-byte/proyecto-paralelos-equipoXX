# Guardianes del Chaco - Motor de simulación paralela de incendios

Proyecto final integrador de TEL-420 Sistemas Paralelos.
Universidad Autónoma "Juan Misael Saracho" - Facultad de Ciencias Integradas de Yacuiba.

## Descripción
Simulación de propagación de incendios forestales del Gran Chaco mediante un
autómata celular estocástico, en versiones secuencial, OpenMP y MPI,
ejecutada sobre un clúster contenerizado de 3 nodos (Docker).

## Integrantes
- Touken-byte
- Integrante 2
- Integrante 3

## Estructura
- infrastructure/  Dockerfile, docker-compose.yml, hostfile
- src/sequential/  Código secuencial de referencia
- src/parallel/    Código paralelo (OpenMP / MPI)
- src/common/      Estados, reglas y RNG compartidos
- data/            Generador de mapas sintéticos
- scripts/         Smoke test, verificación y benchmark
- docs/            Informe y evidencias

## Ejecución
(Se completará con las instrucciones de docker compose up -d)
