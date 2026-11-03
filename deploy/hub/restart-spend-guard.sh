#!/bin/bash
# Stop the running spend guard and start it again with the given LIMIT (a TOTAL of every cost_usd under read/ and
# ident/). The guard reads LIMIT once, at start, so a new limit needs a restart.
# Run as a script, never as an inline ssh command (pkill -f would match the ssh's own command line).
LIMIT=${LIMIT:-184}
cd /srv/colophon
pkill -f "^bash app/spend-guard.sh" || true
sleep 1
setsid nohup env LIMIT="$LIMIT" bash app/spend-guard.sh > /dev/null 2>&1 < /dev/null &
sleep 2
echo "spend guard restarted with LIMIT=$LIMIT: $(pgrep -af '[s]pend-guard.sh' | head -1)"
