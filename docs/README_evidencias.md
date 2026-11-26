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

## Evidencias E61 a E65 (Dell OptiPlex 7010, 25/11/2026)

Tomadas con el clúster de contenedores (nodos limitados a 4 CPUs por el compose).

- E61_htop_benchmark_dell: htop con `fire_omp` (4 hilos, map_2048, 1700 pasos), cada hilo cerca de 100 % de CPU, unos 400 % en total.
- E62_docker_stats_dell: `docker stats` durante la misma corrida; `master` al 400 % de CPU con límite de 8 GiB, `worker1` y `worker2` en reposo.
- E63_verificacion_benchmark_dell: final de `benchmark.sh` con `discrepancias=0` en n=512, 1024 y 2048, un solo checksum del Vigía y `VERIFICACION EXITOSA`.
- E64_hardware_dell: Intel Core i7-13700, 24 CPUs lógicos, 31 GiB de RAM.
- E65_compose_raiz_dell: `docker compose up --build -d` desde un clon limpio, con `master`, `worker1` y `worker2` en `Up` y la línea `Acquire::Retries "5"` del Dockerfile en el build.

Mediciones completas de hoy en `docs/resultados_dell/contenedores_4cpu/`.
Las mediciones nativas originales (`dell_medicion.sh`) siguen en `docs/resultados_dell/benchmark.csv`.

## Evidencias E66 a E74 (PC2, 15 al 22/11/2026)

Capturas del juego tomadas en una PC distinta de la Dell (sufijo `_pc2`). Documentan la interfaz y los cambios visuales; no son mediciones de rendimiento.

- E66_fondo_pixel_chaco_pc2: fondo pixel art del Chaco, con noche, luna, siluetas de árboles y cactus y focos de incendio en el horizonte.
- E67_selector_dificultad_pc2: selector "Dificultad del compañero" con las opciones Asistente, Equilibrado y Experto.
- E68_introduccion_nivel_pc2: cuadro de introducción del nivel "Yacuiba III: la ribera" (1/3): apagar el incendio, llevar 6 animales al refugio y conservar el bosque.
- E69_menu_principal_final_pc2: menú principal final, con fondo pixel art, botones con iconos y barra de volumen de música.
- E70_vigia_mapa_riesgo_juego_pc2: capa de riesgo del Vigía sobre el mapa del juego (32 sims, 100 pasos, 3 procesos × 2 hilos). Muestra la integración juego + Vigía; sus tiempos no se comparan con las tablas de la Dell.
- E71_mapa_hud_iconos_pc2: mapa de Yacuiba III con el HUD de iconos de habilidades, el refugio y el minimapa.
- E72_menu_principal_v3_pc2: versión anterior del menú principal (degradado con chispas, sin fondo pixel art). Sirve de "antes".
- E73_mapa_antes_cambios_pc2: versión anterior del mapa, con el panel lateral en texto plano. Sirve de "antes".
- E74_personajes_chibi_final_pc2: diseño final de los personajes Bombero y Veterinaria (cabeza grande, coleta y botiquín).

## Variantes y capturas complementarias de E05 a E17

| Código | Archivo | Contenido | Máquina |
|--------|---------|-----------|---------|
| E05 | E05_versiones_laptop.png | Versiones de gcc, mpirun y OpenMP (respaldo) | Laptop |
| E11b | E11b_verificacion_mpi_dell.png | Checksums idénticos secuencial vs MPI (versión oficial) | Dell |
| E13b | E13b_docker_stats_mpi_dell.png | docker stats durante la ejecución MPI | Dell |
| E13b | E13b_docker_stats_mpi_dell_recorte.png | Recorte vertical de la captura anterior | Dell |
| E17 | E17_vigia_mapa_riesgo.png | Mapa de riesgo del Vigía (Monte Carlo), versión de ensayo | Laptop |

## Evidencias E25 a E39 (juego, 05/11/2026)

La máquina de origen de E27 a E39 está por confirmar.

| Código | Archivo | Contenido | Máquina |
|--------|---------|-----------|---------|
| E25 | E25_juego_habilidades_dell.png | Panel de habilidades del juego con niveles de emergencia | Dell |
| E26 | E26_juego_evaluacion_dell.png | Pantalla de evaluación final con estrellas | Dell |
| E27 | E27_juego_fauna.png | Fauna del juego en el mapa | Por confirmar |
| E28 | E28_juego_seleccion_modo.png | Selector de modo de juego | Por confirmar |
| E28b | E28_juego_tiempo_real_ia.png | Fuego en tiempo real con IA controlando a los personajes | Por confirmar |
| E29 | E29_juego_ia_veterinaria.png | IA de la veterinaria en acción | Por confirmar |
| E30 | E30_juego_derrota_vida.png | Derrota cooperativa por vida compartida | Por confirmar |
| E31 | E31_juego_recursos.png | Tanque de agua con recarga en el río y cooldown del cortafuegos | Por confirmar |
| E32 | E32_juego_apoyo_meta.png | Apoyo de la veterinaria al bombero y meta visible | Por confirmar |
| E33 | E33_juego_menu_niveles.png | Menú de niveles con miniaturas y ficha de misión | Por confirmar |
| E34 | E34_juego_cuadro_inicio.png | Cuadro de diálogo grande de inicio de nivel | Por confirmar |
| E35 | E35_juego_globo_dialogo.png | Globo de diálogo en el juego | Por confirmar |
| E36 | E36_juego_menu_principal.png | Menú principal ampliado | Por confirmar |
| E37 | E37_juego_pantalla_maqueta.png | Menú principal en versión maqueta (sin iconos), con Campaña, Próximamente y Tienda bloqueada | Por confirmar |
| E38 | E38_juego_cuaderno.png | Cuaderno con enciclopedia de fauna | Por confirmar |
| E39 | E39_juego_habilidades.png | Habilidades adicionales y alerta de zona prioritaria | Por confirmar |

## Evidencias E40 a E55 (juego, 15/11/2026)

La máquina de origen está por confirmar.

| Código | Archivo | Contenido | Máquina |
|--------|---------|-----------|---------|
| E40 | E40_animal_pendiente.png | Animal que huyó del fuego y queda pendiente de rescate | Por confirmar |
| E41 | E41_proteccion_termica.png | Protección térmica del bombero | Por confirmar |
| E42 | E42_conocimiento_silvestre.png | Habilidad de conocimiento silvestre | Por confirmar |
| E43 | E43_cuaderno_notificacion.png | Notificación de nueva ficha del Cuaderno | Por confirmar |
| E43b | E43b_cuaderno_desbloqueado.png | Cuaderno con una ficha ya desbloqueada | Por confirmar |
| E44 | E44_ajustes_audio.png | Ajustes de audio | Por confirmar |
| E45 | E45_incendio_humo_brasas.png | Incendio con humo y brasas | Por confirmar |
| E46 | E46_rescate_animal.png | Rescate de un animal | Por confirmar |
| E47 | E47_ignis.png | Ignis, la mascota de llama del indicador de emergencia (nivel avanzada), con el mapa parcialmente quemado | Por confirmar |
| E48 | E48_campana_candado.png | Selector de nivel con los niveles de la zona Tarija bloqueados (candado de campaña) | Por confirmar |
| E49 | E49_modo_record.png | Modo récord | Por confirmar |
| E50 | E50_tienda.png | Tienda de personalización | Por confirmar |
| E51 | E51_skins_en_partida.png | Aspectos de personajes equipados en partida | Por confirmar |
| E52 | E52_imagen_resultados.png | Imagen de resultados exportada: misión fallida, 0 estrellas, puntuación, animales y bosque conservado | Por confirmar |
| E53 | E53_ia_experto_habilidades.png | IA en nivel experto usando habilidades | Por confirmar |
| E54 | E54_marco_dorado_hud_panel.png | Marco dorado en el HUD y el panel lateral | Por confirmar |
| E55 | E55_marco_dorado_detalle.png | Detalle del marco dorado | Por confirmar |

## Evidencias E56 a E60 (juego, 21 y 22/11/2026)

| Código | Archivo | Contenido | Máquina |
|--------|---------|-----------|---------|
| E56 | E56_zoom_camara_minimapa.png | Mapa con zoom de cámara, HUD de iconos y minimapa | PC2 |
| E57 | E57_cuaderno_primeros_auxilios.png | Cuaderno de Guardianes, Primeros auxilios: quemaduras leves | PC2 |
| E58 | E58_cuaderno_fauna_fuentes.png | Cuaderno de Guardianes, Enciclopedia de fauna: ficha del Jaguar con fuentes citadas | Por confirmar |
| E59 | E59_menu_principal_pixel_bosque.png | Menú principal con fondo pixel art, luna, botones con iconos y barra de música | Por confirmar |
| E60 | E60_modo_juego_pixel.png | Selector Elige el modo de juego (dos jugadores o solitario) sobre el fondo pixel art | Por confirmar |
| E75 | E75_juego_habilidades_pc2.png | Interfaz nueva del juego: panel de habilidades del bombero (teclas D, I, G, H, T) y de la veterinaria (E, F, X, Q, K), minimapa y estado del Vigía "(sin calcular)" al inicio de la ronda; no es una medición de rendimiento (Fig. 3 del informe) | PC2 |
