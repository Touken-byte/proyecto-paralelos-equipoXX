#!/bin/bash
# Uso (desde cualquier lugar): ./scripts/mover_captura.sh NOMBRE_SIN_EXTENSION
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/docs/evidencias"
if [ -z "$1" ]; then echo "Falta el nombre. Ejemplo: $0 E12_htop"; exit 1; fi
ULTIMA=$(find "$HOME/Imágenes" "$HOME/Pictures" "$HOME/Descargas" "$HOME/Downloads" -maxdepth 2 -type f \( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" \) -not -path "$REPO/*" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
if [ -z "$ULTIMA" ]; then echo "No encontré ninguna imagen"; exit 1; fi
EDAD=$(( $(date +%s) - $(stat -c %Y "$ULTIMA") ))
if [ "$EDAD" -gt 120 ]; then
  echo "AVISO: la imagen más reciente tiene $EDAD segundos: $ULTIMA"
  read -p "¿Moverla igual? (s/N) " R
  [ "$R" = "s" ] || { echo "Cancelado. Toma una captura nueva."; exit 1; }
fi
mkdir -p "$DEST"
mv "$ULTIMA" "$DEST/$1.png"
echo "Movida: $ULTIMA"
echo "Nueva ubicación: $DEST/$1.png"
