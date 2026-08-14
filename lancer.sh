#!/bin/sh
# Lance Cabinet Immo. Double-cliquez sur ce fichier ou exécutez ./lancer.sh
cd "$(dirname "$0")" || exit 1
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1; then exec "$py" app.py "$@"; fi
done
echo "Python 3 est introuvable sur ce poste."
echo "Installez-le depuis https://www.python.org/downloads/ puis relancez."
read -r _
