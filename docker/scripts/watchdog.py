"""
Heartbeat-Watchdog mit Selbstzerstoerung.

Ueberwacht die Aktivitaet des Render-Service und zerstoert die Vast.ai-Instanz
wenn:
  - MAX_SESSION_HOURS ueberschritten (harte Grenze)
  - IDLE_TIMEOUT_MINUTES ohne Aktivitaet (weiche Grenze, kein aktiver Job)

Die Selbstzerstoerung braucht VAST_API_KEY (Laufzeit-Umgebungsvariable).
Ohne API-Key loggt der Watchdog nur Warnungen.

Lizenz: GPL-2.0-or-later
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path

HEARTBEAT_FILE = Path("/tmp/daz_heartbeat")
SHUTDOWN_FILE = Path("/tmp/daz_shutdown")

MAX_SESSION_HOURS = float(os.environ.get("MAX_SESSION_HOURS", "4"))
IDLE_TIMEOUT_MINUTES = float(os.environ.get("IDLE_TIMEOUT_MINUTES", "30"))
CHECK_INTERVAL = 60

START_TIME = time.time()


def log(msg):
    print(f"[WATCHDOG] {msg}", flush=True)


def get_last_heartbeat():
    try:
        return float(HEARTBEAT_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return START_TIME


def has_active_render():
    """Prueft ob Blender-Render-Prozesse laufen."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "blender.*setup_and_render"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_instance_id():
    """Vast.ai-Instance-ID ermitteln."""
    # Methode 1: Umgebungsvariable
    iid = os.environ.get("VAST_CONTAINERLABEL", "")
    if iid:
        return iid

    # Methode 2: Datei (von Vast.ai geschrieben)
    try:
        return Path("/etc/vast_containerlabel").read_text().strip()
    except FileNotFoundError:
        pass

    # Methode 3: Container-ID aus hostname
    try:
        result = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def destroy_instance():
    """Vast.ai-Instanz zerstoeren."""
    api_key = os.environ.get("VAST_API_KEY", "")
    instance_id = get_instance_id()

    if not api_key:
        log("KEIN VAST_API_KEY — kann Instanz nicht zerstoeren!")
        log("Instanz muss manuell zerstoert werden.")
        SHUTDOWN_FILE.write_text("no_api_key")
        return False

    if not instance_id:
        log("Instance-ID nicht ermittelbar — kann nicht zerstoeren!")
        SHUTDOWN_FILE.write_text("no_instance_id")
        return False

    log(f"ZERSTOERE Instanz {instance_id}...")

    try:
        result = subprocess.run(
            ["vastai", "destroy", "instance", instance_id,
             "--api-key", api_key],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0:
            log(f"Instanz {instance_id} zerstoert.")
            SHUTDOWN_FILE.write_text("destroyed")
            return True
        else:
            log(f"vastai destroy fehlgeschlagen: {result.stderr}")

            # Fallback: curl
            log("Versuche Fallback via curl...")
            result = subprocess.run(
                ["curl", "-s", "-X", "PUT",
                 f"https://console.vast.ai/api/v0/instances/{instance_id}/",
                 "-H", f"Authorization: Bearer {api_key}",
                 "-H", "Content-Type: application/json",
                 "-d", '{"state": "destroy"}'],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                log(f"Instanz via API zerstoert: {result.stdout}")
                SHUTDOWN_FILE.write_text("destroyed_via_api")
                return True
            else:
                log(f"Auch API-Fallback fehlgeschlagen: {result.stderr}")

    except Exception as e:
        log(f"Fehler beim Zerstoeren: {e}")

    SHUTDOWN_FILE.write_text("destroy_failed")
    return False


def main():
    max_seconds = MAX_SESSION_HOURS * 3600
    idle_seconds = IDLE_TIMEOUT_MINUTES * 60

    log("=" * 50)
    log("DAZ Cloud Render — Watchdog")
    log("=" * 50)
    log(f"Max Session:    {MAX_SESSION_HOURS}h ({max_seconds:.0f}s)")
    log(f"Idle Timeout:   {IDLE_TIMEOUT_MINUTES}min ({idle_seconds:.0f}s)")
    log(f"Check-Intervall: {CHECK_INTERVAL}s")
    log(f"API-Key:        {'gesetzt' if os.environ.get('VAST_API_KEY') else 'NICHT GESETZT'}")
    log(f"Instance-ID:    {get_instance_id() or 'unbekannt'}")
    log("")

    while True:
        time.sleep(CHECK_INTERVAL)

        if SHUTDOWN_FILE.exists():
            log("Shutdown-Datei gefunden — beende Watchdog.")
            break

        now = time.time()
        uptime = now - START_TIME
        last_hb = get_last_heartbeat()
        idle_time = now - last_hb
        active = has_active_render()

        # Status-Log (alle 5 Minuten)
        if int(uptime) % 300 < CHECK_INTERVAL:
            log(f"Uptime: {uptime/60:.0f}min | "
                f"Idle: {idle_time/60:.1f}min | "
                f"Render aktiv: {active}")

        # Harte Grenze: Maximale Session-Dauer
        if uptime >= max_seconds:
            log(f"MAX SESSION ERREICHT ({MAX_SESSION_HOURS}h)")
            if active:
                log("Render laeuft noch — warte 5 Minuten Gnadenfrist...")
                time.sleep(300)
                if has_active_render():
                    log("Render laeuft immer noch — zerstoere trotzdem.")
            destroy_instance()
            break

        # Weiche Grenze: Inaktivitaet (nur wenn kein Render laeuft)
        if idle_time >= idle_seconds and not active:
            log(f"IDLE TIMEOUT ({IDLE_TIMEOUT_MINUTES}min ohne Aktivitaet)")
            destroy_instance()
            break

        # Warnung bei 80% der Max-Session
        if uptime >= max_seconds * 0.8 and int(uptime) % 300 < CHECK_INTERVAL:
            remaining = (max_seconds - uptime) / 60
            log(f"WARNUNG: Noch {remaining:.0f} Minuten bis zur Zerstoerung!")


if __name__ == "__main__":
    main()
