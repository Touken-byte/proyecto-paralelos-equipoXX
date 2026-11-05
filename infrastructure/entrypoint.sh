#!/bin/bash
# Arranque de cada nodo: prepara SSH sin contraseña y levanta sshd
set -e
KEYDIR=/shared_keys
HOME_DIR=/home/mpiuser

mkdir -p "$HOME_DIR/.ssh"

# El primer nodo en arrancar genera la clave; los demás la reutilizan
if [ ! -f "$KEYDIR/id_ed25519" ]; then
    ssh-keygen -t ed25519 -N "" -f "$KEYDIR/id_ed25519" -C "mpiuser@cluster" >/dev/null
fi

cp "$KEYDIR/id_ed25519" "$HOME_DIR/.ssh/id_ed25519"
cp "$KEYDIR/id_ed25519.pub" "$HOME_DIR/.ssh/id_ed25519.pub"
cp "$KEYDIR/id_ed25519.pub" "$HOME_DIR/.ssh/authorized_keys"
printf "Host *\n    StrictHostKeyChecking no\n    UserKnownHostsFile /dev/null\n    LogLevel ERROR\n" > "$HOME_DIR/.ssh/config"

chown -R mpiuser:mpiuser "$HOME_DIR/.ssh"
chmod 700 "$HOME_DIR/.ssh"
chmod 600 "$HOME_DIR/.ssh/id_ed25519" "$HOME_DIR/.ssh/authorized_keys" "$HOME_DIR/.ssh/config"

exec /usr/sbin/sshd -D -e
