#!/bin/bash
# Keep reading pages as SAM produces figures. Stops when /srv/colophon/read/STOP exists. Budget is a TOTAL.
BUDGET=${BUDGET:-120}
cd /srv/colophon
while :; do
  [ -e read/STOP ] && { echo "$(date -u +%FT%TZ) STOP file present, exiting"; exit 0; }
  echo "$(date -u +%FT%TZ) run (budget $BUDGET)"
  ~/.venvs/colophon/bin/python app/reader.py --root /srv/colophon --workers 8 --budget-usd "$BUDGET" || echo "reader exit $?"
  sleep 180
done
