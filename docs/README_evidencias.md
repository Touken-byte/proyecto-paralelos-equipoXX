# Índice de evidencias (docs/evidencias/)

| Código | Archivo | Contenido | Máquina |
|--------|---------|-----------|---------|
| E01 | E01_cluster_levantado_dell.png | docker compose up y docker ps con los 3 nodos | Dell |
| E02 | E02_red_bridge_dell.png | Red bridge con las 3 IPs | Dell |
| E03 | E03_ping_nodos_dell.png | Ping y resolución de nombres | Dell |
| E04 | E04_ssh_sin_clave_dell.png | SSH sin contraseña | Dell |
| E05 | E05_versiones_dell.png | Versiones de gcc, mpirun y OpenMP | Dell |
| E06 | E06_smoke_openmp_dell.png | Smoke test OpenMP | Dell |
| E07 | E07_smoke_mpi_dell.png | Smoke test MPI en 3 nodos | Dell |
| E08 | E08_secuencial_dell.png | Ejecución secuencial (T_1) | Dell |
| E09 | E09_mapa_incendio_dell.png | Mapa del incendio en pasos 0, 50 y 100 | Dell |
| E10 | E10_openmp_hilos_dell.png | OpenMP con 1, 2, 4, 8 hilos | Dell |
| E11 | E11_verificacion_checksum_dell.png | Checksums idénticos secuencial vs OpenMP | Dell |
| E11b | E11b_verificacion_mpi.png | Checksums idénticos secuencial vs MPI | Laptop |
| E12 | E12_htop_dell.png | htop durante OpenMP | Dell |
| E13 | E13_docker_stats_dell.png | docker stats durante la ejecución | Dell |
| E14 | E14_git_log.png | git log --oneline --graph | Dell |
| E15 | E15_estructura_repo.png | tree -L 2 | Dell |
| E16 | E16_hardware_dell.png | lscpu, nproc y free de la Dell | Dell |
| E17 | E17_vigia_riesgo_dell.png | Mapa de riesgo del Vigía (Monte Carlo) | Dell |
| E18 | E18_verificacion_vigia.png | Vigía: checksums idénticos con distinto número de procesos e hilos | Laptop |
| E19 | E19_verificacion_acciones.png | Acciones de jugador: checksums idénticos en secuencial, OpenMP y MPI | Laptop |
| E20 | E20_juego_inicio.png | Visor del juego al iniciar | Laptop |
| E21 | E21_juego_dos_rondas.png | Visor del juego tras dos rondas | Laptop |
| E22 | E22_juego_graficos_inicio.png | Visor con gráficos pixel art al iniciar | Laptop |
| E23 | E23_juego_graficos_ronda1.png | Visor con gráficos pixel art tras una ronda | Laptop |
| E24 | E24_juego_graficos_ronda3.png | Visor con gráficos pixel art tras tres rondas | Laptop |

Las mediciones oficiales de tiempo y memoria se toman en la Dell OptiPlex 7010.
Los tiempos de la laptop son preliminares.

Las evidencias E01 a E17 son las versiones oficiales tomadas en la Dell
(sufijo `_dell`). Las capturas de la laptop (E01 a E09, E11, E11b, E17) se
conservan en la misma carpeta como respaldo y ensayo.
E18 a E24 corresponden al Vigía y al visor del juego.
