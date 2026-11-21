"""
Konfiguration fuer DAZ Cloud Render Client.

Laedt Einstellungen aus:
  1. ~/.daz-cloud-render.json  (persistent)
  2. Umgebungsvariablen        (ueberschreiben Datei)

Lizenz: MIT
"""

import os
import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".daz-cloud-render.json"

DEFAULTS = {
    "vast_api_key": "",
    "docker_image": "ghcr.io/hexakosi/daz-cloud-render:latest",
    "gpu_name": "RTX_4090",
    "disk_gb": 20,
    "max_session_hours": 4,
    "idle_timeout_minutes": 30,
    "default_samples": 128,
    "default_resolution": "1920x1080",
    "daz_root_paths": [],
}

ENV_MAP = {
    "VAST_API_KEY": "vast_api_key",
    "DAZ_CLOUD_IMAGE": "docker_image",
    "DAZ_ROOT_PATHS": "daz_root_paths",
}


def load_config():
    config = dict(DEFAULTS)

    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE) as f:
                stored = json.load(f)
            config.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass

    for env_key, cfg_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val:
            if cfg_key == "daz_root_paths":
                config[cfg_key] = val.split(os.pathsep)
            else:
                config[cfg_key] = val

    return config


def save_config(config):
    saveable = {k: v for k, v in config.items() if k in DEFAULTS and k != "vast_api_key"}
    if config.get("vast_api_key"):
        saveable["vast_api_key"] = config["vast_api_key"]

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(saveable, f, indent=2)


def auto_detect_daz_paths():
    """DAZ-Root-Pfade automatisch finden."""
    candidates = [
        Path.home() / "Documents" / "My DAZ 3D Library",
        Path("C:/Users/Public/Documents/My DAZ 3D Library"),
        Path("E:/DAZ 3D/lib"),
        Path("D:/DAZ 3D/lib"),
    ]
    return [str(p) for p in candidates if p.is_dir()]
