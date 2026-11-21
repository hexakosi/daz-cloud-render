#!/bin/bash
# Entrypoint fuer DAZ Cloud Render.
# Startet Render-Service + Watchdog via Supervisor,
# oder fuehrt einen uebergebenen Befehl direkt aus.
#
# Lizenz: GPL-2.0-or-later

set -e

echo "[ENTRYPOINT] DAZ Cloud Render"
echo "[ENTRYPOINT] Blender: $(blender -b --version 2>/dev/null | head -1)"
echo "[ENTRYPOINT] Root-Pfade: ${DAZ_ROOT_PATHS:-/workspace/scenes}"
echo "[ENTRYPOINT] Max Session: ${MAX_SESSION_HOURS:-4}h"
echo "[ENTRYPOINT] Idle Timeout: ${IDLE_TIMEOUT_MINUTES:-30}min"

# Arbeitsverzeichnisse sicherstellen
mkdir -p /workspace/scenes /workspace/results /workspace/cache

# Heartbeat initialisieren
date +%s > /tmp/daz_heartbeat

# Falls ein Befehl uebergeben wurde: direkt ausfuehren (kein Service-Modus)
if [ $# -gt 0 ]; then
    echo "[ENTRYPOINT] Direkter Modus: $*"
    exec "$@"
fi

# Service-Modus: Supervisor starten
echo "[ENTRYPOINT] Service-Modus — starte Supervisor"

# Vast.ai Base-Image hat Supervisor vorinstalliert
if command -v supervisord &>/dev/null; then
    exec supervisord -n -c /etc/supervisor/supervisord.conf
else
    echo "[ENTRYPOINT] Supervisor nicht gefunden — starte Dienste manuell"
    python3 /opt/daz-cloud-render/watchdog.py &
    exec python3 /opt/daz-cloud-render/render_service.py
fi
