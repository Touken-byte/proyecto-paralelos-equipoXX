FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    openmpi-bin \
    libopenmpi-dev \
    openssh-server \
    openssh-client \
    iputils-ping \
    net-tools \
    htop \
    time \
    python3 \
    python3-pip \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Usuario no root para MPI
RUN useradd -m -s /bin/bash mpiuser \
    && echo "mpiuser ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/mpiuser

# Preparar SSH
RUN mkdir -p /var/run/sshd \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Evitar avisos de OpenMPI dentro de contenedores
ENV OMPI_MCA_btl_vader_single_copy_mechanism=none
ENV OMPI_MCA_rmaps_base_oversubscribe=1

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /shared_keys && chmod 777 /shared_keys

WORKDIR /home/mpiuser/proyecto
EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
