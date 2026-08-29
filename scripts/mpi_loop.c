/* Long-running MPI ranks for wrap/sidecar diagnosis. Usage: mpi_loop.x [seconds] */
#define _POSIX_C_SOURCE 200809L
#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    int rank = 0, nprocs = 0, seconds = 60;
    char host[256];

    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &nprocs);
    if (argc > 1) {
        seconds = atoi(argv[1]);
        if (seconds < 1) {
            seconds = 1;
        }
    }
    gethostname(host, sizeof(host) - 1);
    fprintf(stderr, "mpi_loop.x host=%s rank=%d/%d seconds=%d pid=%d\n",
            host, rank, nprocs, seconds, (int)getpid());
    fflush(stderr);

    for (int i = 0; i < seconds; i++) {
        sleep(1);
        MPI_Barrier(MPI_COMM_WORLD);
        if (rank == 0 && ((i + 1) % 10 == 0 || i + 1 == seconds)) {
            fprintf(stderr, "mpi_loop tick %d/%d\n", i + 1, seconds);
            fflush(stderr);
        }
    }

    MPI_Finalize();
    return 0;
}
