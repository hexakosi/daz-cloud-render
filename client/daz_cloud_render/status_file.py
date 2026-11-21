"""
Status-Datei fuer die Kommunikation zwischen Python-Client und DAZ-Script.

Schreibt JSON in eine Status-Datei, die das DAZ-Script pollt.

Lizenz: MIT
"""

import json
import time
from pathlib import Path

STATUS_FILE = Path.home() / ".daz-cloud-render-status.json"


def write_status(phase, message, progress=0, total=0, error=None,
                 result_file=None, extra=None):
    """Status-Datei aktualisieren."""
    data = {
        "phase": phase,
        "message": message,
        "progress": progress,
        "total": total,
        "percent": round((progress / total * 100) if total > 0 else 0, 1),
        "timestamp": time.time(),
        "error": error,
        "result_file": result_file,
    }
    if extra:
        data.update(extra)

    try:
        STATUS_FILE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def read_status():
    """Status-Datei lesen."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def clear_status():
    """Status-Datei loeschen."""
    try:
        STATUS_FILE.unlink(missing_ok=True)
    except OSError:
        pass
