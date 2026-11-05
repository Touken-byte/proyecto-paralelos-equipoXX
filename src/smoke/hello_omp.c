#include <stdio.h>
#include <omp.h>

int main(void) {
    #pragma omp parallel
    {
        printf("Hola desde el hilo %d de %d\n",
               omp_get_thread_num(), omp_get_num_threads());
    }
    return 0;
}
