#!/bin/sh
set -eu
mkdir -p /var/run/clamav
chown -R clamav:clamav /var/run/clamav /var/lib/clamav
clamd --config-file=/etc/clamav/clamd.conf
exec python3 /app/server.py
