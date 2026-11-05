# Índice de evidencias (docs/evidencias/)

| Código | Archivo | Contenido | Máquina |
|--------|---------|-----------|---------|
| E01 | E01_cluster_levantado.png | docker compose up y docker ps con los 3 nodos | Laptop |
| E02 | E02_red_bridge.png | Red bridge con las 3 IPs | Laptop |
| E03 | E03_ping_nodos.png | Ping y resolución de nombres | Laptop |
| E04 | E04_ssh_sin_clave.png | SSH sin contraseña | Laptop |
| E05 | E05_versiones_laptop.png | Versiones de gcc, mpirun y OpenMP | Laptop |
| E06 | E06_smoke_openmp.png | Smoke test OpenMP | Laptop |
| E07 | E07_smoke_mpi.png | Smoke test MPI en 3 nodos | Laptop |
| E08 | E08_secuencial.png | Ejecución secuencial (T_1) | Laptop |
| E09 | E09_mapa_incendio.png | Mapa del incendio en pasos 0, 50 y 100 | Laptop |
| E10 | (pendiente) | OpenMP con 1, 2, 4, 8 hilos | Dell |
| E11 | E11_verificacion_checksum.png | Checksums idénticos secuencial vs OpenMP | Laptop |
| E11b | E11b_verificacion_mpi.png | Checksums idénticos secuencial vs MPI | Laptop |
| E12 | (pendiente) | htop durante OpenMP | Dell |
| E13 | (pendiente) | docker stats durante la ejecución | Dell |
| E14 | (pendiente) | git log --oneline --graph | Laptop |
| E15 | (pendiente) | tree -L 2 | Laptop |
| E16 | (pendiente) | lscpu, nproc y free de la Dell | Dell |
| E17 | E17_vigia_mapa_riesgo.png | Mapa de riesgo del Vigía (Monte Carlo) | Laptop |
| E18 | E18_verificacion_vigia.png | Vigía: checksums idénticos con distinto número de procesos e hilos | Laptop |
| E19 | E19_verificacion_acciones.png | Acciones de jugador: checksums idénticos en secuencial, OpenMP y MPI | Laptop |
| E20 | E20_juego_inicio.png | Visor del juego al iniciar | Laptop |
| E21 | E21_juego_dos_rondas.png | Visor del juego tras dos rondas | Laptop |
| E22 | E22_juego_graficos_inicio.png | Visor con gráficos pixel art al iniciar | Laptop |
| E23 | E23_juego_graficos_ronda1.png | Visor con gráficos pixel art tras una ronda | Laptop |
| E24 | E24_juego_graficos_ronda3.png | Visor con gráficos pixel art tras tres rondas | Laptop |

Las mediciones oficiales de tiempo y memoria se toman en la Dell OptiPlex 7010.
Los tiempos de la laptop son preliminares.

Las capturas marcadas como pendientes se toman en la Dell (E10, E12, E13, E16)
o al final del proyecto con todos los commits (E14, E15). Las versiones
oficiales de E09 y E17 se generan en la Dell con `scripts/dell_medicion.sh`
(sufijo `_dell`).
