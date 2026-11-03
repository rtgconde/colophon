#!/bin/bash
# Stop every process that calls the Meta API (reader loop, reader, identifier). Local work (SAM, index, serve) continues.
cd /srv/colophon
touch read/STOP
pkill -f "^bash app/read-loop.sh" || true
pkill -f "^bash app/run-identify-all.sh" || true
pkill -f "[a]pp/reader.py --root" || true
pkill -f "[a]pp/identify.py" || true
sleep 3
echo "API users still running: $(pgrep -af "[a]pp/reader.py|[a]pp/identify.py|^bash app/read-loop.sh|^bash app/run-identify-all.sh" | wc -l)"
