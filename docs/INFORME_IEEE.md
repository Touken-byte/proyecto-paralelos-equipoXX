# Simulación paralela de incendios forestales del Gran Chaco con OpenMP, MPI y un modelo híbrido

**Autora:** Touken-byte | **Equipo:** [EQUIPO: firnt (por confirmar)] | **Materia:** TEL-420 Sistemas Paralelos, UAJMS Yacuiba | **Docente:** Ing. Elias Cassal Baldiviezo

## I. Resumen y Abstract
**Resumen.** [PENDIENTE: 150-200 palabras, al final. Estructura: problema (incendios forestales en el Gran Chaco), método (autómata celular estocástico con versiones secuencial, OpenMP, MPI e híbrida, y predictor Monte Carlo sobre un clúster Docker de 3 nodos), resultados ([DELL] speedup y eficiencia máximos) y conclusión.]

**Abstract.** [PENDIENTE: traducción al inglés del Resumen, 150-200 words.]

Palabras clave: autómata celular, incendios forestales, OpenMP, MPI, speedup, Amdahl, Gustafson.

Keywords: cellular automata, wildfire, OpenMP, MPI, speedup, Amdahl, Gustafson.

## II. Introducción y contextualización regional
Yacuiba se ubica en el Gran Chaco boliviano, en el departamento de Tarija, junto a la Serranía del Aguaragüe. Es una región de bosque seco y pastizales con una estación seca marcada, donde un incendio forestal puede extenderse con rapidez y afectar a la fauna silvestre, la vegetación y las comunidades cercanas. [PENDIENTE: dato o fuente oficial sobre incendios en Tarija o el Chaco (superficie afectada o focos de calor), por ejemplo de la ABT, el SERNAP o la Gobernación de Tarija.]

Simular la propagación del fuego con un autómata celular exige actualizar n × n celdas en cada paso, y estudiar el riesgo exige repetir la simulación muchas veces con distintas semillas (método Monte Carlo). Ambos costos crecen rápido con el tamaño del mapa y con el número de escenarios, y ambos admiten paralelismo: las celdas de un mismo paso son independientes entre sí gracias al doble buffer, y las simulaciones Monte Carlo son independientes entre sí.

Este trabajo presenta (1) un motor de simulación secuencial que sirve de referencia, (2) versiones paralelas con OpenMP, MPI y un modelo híbrido, (3) El Vigía, un predictor Monte Carlo que produce mapas de riesgo y permite comparar escenarios con y sin cortafuegos, (4) una infraestructura reproducible de tres nodos con Docker y (5) la integración del motor en Guardianes del Chaco, un videojuego educativo cooperativo orientado a la prevención de incendios y la protección de la fauna. El objetivo técnico es medir la aceleración, la eficiencia y la escalabilidad de cada modalidad y contrastarlas con las leyes de Amdahl y Gustafson. Los resultados son experimentales y educativos; no son predicciones oficiales de incendios reales.

El documento se organiza así: la Sección III presenta el marco teórico, la IV la arquitectura e infraestructura, la V la implementación paralela, la VI los resultados experimentales y la VII las conclusiones.

## III. Marco teórico y estado del arte
A. Taxonomía de Flynn: Flynn clasifica los sistemas según sus flujos de instrucciones y de datos en SISD, SIMD, MISD y MIMD [6]. La versión secuencial es SISD. MIMD, SPMD; memoria compartida (OpenMP) y distribuida (MPI). Es decir, procesadores independientes ejecutan el mismo programa sobre porciones distintas de los datos.

B. Modelo de memoria: en memoria compartida (OpenMP), los hilos de un mismo proceso ven un único espacio de direcciones y deben evitar condiciones de carrera; aquí se evitan con el doble buffer, que separa la lectura del paso t de la escritura del paso t+1. En memoria distribuida (MPI), cada proceso tiene su propia memoria y los datos se mueven con mensajes explícitos [7]. El modelo híbrido usa MPI entre procesos y OpenMP dentro de cada uno; el Vigía inicializa MPI con MPI_THREAD_FUNNELED, de modo que solo el hilo principal hace llamadas MPI.

C. Redes de interconexión: en un clúster, el costo de enviar un mensaje de m bytes se aproxima por una latencia fija más un término proporcional a m dividido por el ancho de banda. En este proyecto la red es una red bridge virtual de Docker dentro de una sola máquina física, por lo que su latencia y su ancho de banda no representan los de una red Ethernet real. [DELL: medir la latencia entre contenedores si se quiere cuantificar.]

D. Leyes de Amdahl y Gustafson: con una fracción secuencial f, la aceleración máxima con p procesadores es S(p) = 1 / (f + (1 − f)/p) [1]; si el problema crece con p, la aceleración escalada es S(p) = p − f(p − 1) [2]. La eficiencia es E(p) = S(p)/p.

E. Estado del arte: los autómatas celulares se usan para modelar la propagación de incendios con efecto del viento y del combustible [8]. Las simulaciones Monte Carlo independientes son un caso de paralelismo casi trivial. [PENDIENTE: 2 o 3 trabajos sobre simulación paralela de incendios (MPI, OpenMP o GPU) con su referencia.]

## IV. Diseño de la arquitectura e infraestructura
A. Clúster: 3 contenedores Docker (master, worker1, worker2), red bridge, SSH sin contraseña, Ubuntu 22.04, 8 GB de RAM y hasta 4 CPUs por nodo.

B. Hardware de medición: [DELL] lscpu (modelo, núcleos físicos, hilos lógicos), RAM.

C. Asignación de recursos: cada contenedor recibe hasta 4 CPUs y 8 GB de RAM (parámetros cpus y mem_limit de docker-compose.yml). Los tres nodos comparten la CPU física del host, de modo que el clúster reproduce la lógica de un sistema distribuido pero no el costo de una red real. El archivo hostfile lista los tres nodos y los procesos MPI se reparten con --map-by node (un proceso por nodo).

D. Diagrama del clúster: [PENDIENTE: figura con el host, la red bridge interna y los tres contenedores (master, worker1, worker2) con sus CPUs y su RAM.]

## V. Implementación algorítmica paralela
A. Modelo y algoritmo base.

El incendio se modela como un autómata celular estocástico sobre una malla de n x n celdas con vecindad de Moore (8 vecinas) y doble buffer: el paso t+1 se calcula leyendo únicamente el paso t, lo que elimina dependencias dentro de un mismo paso.

Cada celda puede estar vacía, con vegetación, quemando, quemada, con cortafuegos o con agua, y solo la vegetación puede encenderse. Una celda en llamas pasa a quemada con probabilidad p_apagado = 0,25 por paso. Para una celda de vegetación, cada vecina k en llamas aporta una probabilidad de contagio p_k = min(0,95; p_base · f_c · f_h · f_v,k), con p_base = 0,30. El factor de combustible es f_c = combustible/255, el de humedad f_h = 1 − 0,8 · humedad/255, y el de viento f_v,k = d_k · exp(1,5 · w · cos θ_k), donde w es la fuerza del viento, θ_k el ángulo entre la dirección del viento y la dirección vecina → celda, y d_k vale 1 para vecinas ortogonales y 0,7071 para diagonales.

La probabilidad total de ignición combina a todas las vecinas en llamas, P = 1 − Π(1 − p_k), y la celda se enciende si u < P. El número aleatorio u se obtiene de SplitMix64 aplicado a la terna (semilla, paso, índice de celda), de modo que depende solo de esos tres valores y nunca del hilo o proceso que calcula la celda. Esta decisión de diseño hace que todas las versiones produzcan exactamente el mismo resultado y permite verificarlas con un checksum del estado final.

Las acciones del jugador son APAGAR (quemando → quemada) y CORTAFUEGO (vegetación → cortafuegos), y se aplican antes de calcular cada paso.

B. OpenMP (memoria compartida): las filas de la malla se reparten entre los hilos con la cláusula schedule(runtime), lo que permite comparar las políticas static, dynamic y guided sin recompilar. Gracias al doble buffer, los hilos escriben en el buffer de destino sin sincronización dentro del paso.

C. MPI (memoria distribuida): la malla se descompone por bloques de filas, uno por proceso. Las primeras (n mod p) filas-bloque llevan una fila extra, de modo que la diferencia de carga entre procesos es de una fila. En cada paso, cada proceso aplica primero las acciones del jugador sobre sus filas y luego intercambia la fila frontera con sus vecinos superior e inferior mediante MPI_Isend y MPI_Irecv no bloqueantes seguidos de MPI_Waitall, lo que evita interbloqueos. Después calcula solo sus filas. Al final, las métricas globales se obtienen con MPI_Reduce (suma de tres contadores globales) y el estado final se reúne en el proceso 0 con MPI_Gatherv. Limitación actual: cada proceso reserva la malla completa y solo calcula su bloque; la comunicación es la mínima necesaria, pero la memoria por proceso no se reduce (mejora prevista: bloque local más dos filas halo).

D. Híbrido y Vigía: el Vigía ejecuta simulaciones Monte Carlo independientes con distintas semillas. Las simulaciones se reparten entre procesos MPI y, dentro de cada proceso, los hilos OpenMP procesan su parte. Los resultados se acumulan en un mapa de probabilidad de riesgo de quema por celda. Al ser simulaciones independientes, casi no requieren comunicación: la única es una reducción final. La simulación s se asigna al proceso (s mod p), los hilos de cada proceso toman simulaciones con schedule(dynamic,1) y cada hilo usa un mapa acumulador y un doble buffer privados, por lo que no hay sincronización dentro de una simulación. Los acumuladores de los hilos se fusionan en una sección crítica y los de los procesos con MPI_Reduce. La semilla de cada simulación se deriva con SplitMix64 solo de la semilla base y del índice s, no del proceso ni del hilo, por lo que el mapa de riesgo no debería depender de cómo se reparta el trabajo [verificar con la Dell variando procesos e hilos]. El Vigía acepta además un archivo de acciones (--acciones), con el mismo formato que el motor secuencial, para comparar el riesgo con y sin cortafuegos; sin ese archivo el resultado es idéntico al anterior (checksum de referencia verificado con n=128, 8 simulaciones y 50 pasos: 3fcc85cb0166e9e5).

E. Balanceo de carga: en OpenMP, schedule(runtime) permite comparar static, dynamic y guided sin recompilar [DELL: resultado]. En MPI, el reparto por bloques de filas deja una diferencia máxima de una fila entre procesos, aunque el costo real por fila puede variar con la cantidad de fuego. En el Vigía, el reparto cíclico de simulaciones entre procesos y la planificación dinámica entre hilos compensan simulaciones de duración desigual.

F. Corrección: checksum idéntico en todas las versiones (n=512, semilla 42, 100 pasos: c5dad814f7cbeaff).

G. Integración con el videojuego: el motor secuencial (`fire_seq`) se ejecuta dentro del contenedor `master` y el videojuego en Python (pygame) lo invoca una vez por ronda de cinco pasos. Las acciones de los jugadores (cortafuegos y agua) se escriben en un archivo de acciones que el motor lee en el paso indicado, y el estado del mapa se guarda y se recupera entre rondas, de modo que la simulación continúa sin recalcularse desde cero. El cálculo corre en un hilo aparte para que la interfaz no se bloquee. Cada nivel de la campaña (Bosques de Yacuiba, Serranía del Aguaragüe, Región de Tarija y El gran incendio) define su propio tamaño de mapa (96, 112, 128 y 128 celdas de lado), su semilla y la dirección e intensidad del viento. El Vigía recibe los mismos parámetros de viento que el fuego real, para que su mapa de riesgo Monte Carlo sea coherente con la partida. Los recursos del bombero (tanque de seis cargas con recarga junto al río y tiempo de recuperación del cortafuegos) y el compañero controlado por reglas se implementan en el cliente y no modifican el motor, por lo que el checksum de referencia no cambia.

## VI. Resultados experimentales y análisis de rendimiento
A. Protocolo: tamaños [DELL: 512, 1024, 2048], hilos [DELL: 1, 2, 4, 8], procesos MPI [DELL], [DELL: número de repeticiones y promedio]. Métricas: T_p, S_p = T_1/T_p, E_p = S_p/p.

B. Reproducibilidad: `scripts/dell_medicion.sh`, semilla fija, repositorio con un comando.

C. Huella de memoria: n=512, unos 4,4 MB de RSS máximo. [DELL: n=1024 y 2048.]

D. Escalabilidad fuerte: [DELL: tabla y gráfica de tiempo, speedup y eficiencia; ajuste de Amdahl y fracción secuencial f].

E. Escalabilidad débil: [DELL: eficiencia débil y comparación con Gustafson].

F. MPI e híbrido: [DELL: tiempos con 1, 2, 3, 6 procesos; Vigía].

G. Cuellos de botella: ancho de banda de memoria, hyperthreading, los 3 nodos comparten la misma CPU física, red virtual sin latencia real.

H. Datos preliminares (laptop, no oficiales): speedup OpenMP con 2 hilos de 1,90 (n=512, 100 pasos); con 4 hilos cae a unos 0,92 por hyperthreading. Se sustituyen por los de la Dell. Vigía con cortafuegos (laptop; mapa de 128 celdas, 8 simulaciones, 50 pasos): el porcentaje de celdas con riesgo mayor al 50 % baja de 9,8 % (1611 celdas) a 7,7 % (1259 celdas) al agregar una barrera completa; es una demostración cualitativa que se repetirá en la Dell.

## VII. Conclusiones e impacto social y productivo
[Escribir con los resultados de la Dell.] Trabajo futuro: CUDA, más regiones, juego completo, otras redes.

Impacto social y productivo: el proyecto ofrece una herramienta abierta para sensibilizar sobre la prevención de incendios y la protección de la fauna del Chaco, y permite comparar escenarios, por ejemplo con y sin cortafuegos. [PENDIENTE: valorar con datos o actores locales; los resultados son experimentales y no constituyen predicciones oficiales.]

## VIII. Referencias
[1] Amdahl, G. M., "Validity of the single processor approach to achieving large scale computing capabilities," AFIPS 1967.
[2] Gustafson, J. L., "Reevaluating Amdahl's law," Commun. ACM, 1988.
[3] OpenMP Architecture Review Board, OpenMP Application Programming Interface.
[4] MPI Forum, MPI: A Message-Passing Interface Standard.
[5] Steele, G. L. et al., "Fast splittable pseudorandom number generators," OOPSLA 2014 (SplitMix64).
[6] Flynn, M. J., "Very high-speed computing systems," Proc. IEEE, 1966. [verificar datos]
[7] Pacheco, P., An Introduction to Parallel Programming, Morgan Kaufmann, 2011. [verificar datos]
[8] Karafyllidis, I. y Thanailakis, A., "A model for predicting forest fire spreading using cellular automata," Ecological Modelling, 1997. [verificar datos]
[PENDIENTE: fuente oficial de datos regionales de incendios y 2 o 3 trabajos sobre simulación paralela de incendios.]
