"""
Installiert das DAZ Cloud Render Script in DAZ Studio.

Kopiert cloud_render.dsa in den DAZ-Scripts-Ordner und
erstellt optional eine Custom Action.

Aufruf:
    python install.py

Lizenz: MIT
"""

import os
import sys
import shutil
from pathlib import Path


def find_daz_scripts_dir():
    """DAZ-Scripts-Ordner finden."""
    candidates = [
        Path.home() / "Documents" / "DAZ 3D" / "Studio" / "My Library" / "Scripts",
        Path("C:/Users/Public/Documents/My DAZ 3D Library/Scripts"),
        Path.home() / "Documents" / "My DAZ 3D Library" / "Scripts",
    ]

    for p in candidates:
        if p.is_dir():
            return p

    # Fallback: ersten Kandidaten erstellen
    return candidates[0]


def install():
    script_dir = Path(__file__).parent
    source = script_dir / "cloud_render.dsa"

    if not source.is_file():
        print(f"FEHLER: {source} nicht gefunden!")
        sys.exit(1)

    dest_dir = find_daz_scripts_dir()
    cloud_dir = dest_dir / "Cloud Render"
    cloud_dir.mkdir(parents=True, exist_ok=True)

    dest = cloud_dir / "cloud_render.dsa"
    shutil.copy2(source, dest)
    print(f"Script installiert: {dest}")

    print()
    print("Naechste Schritte in DAZ Studio:")
    print("  1. File > Run Script... > cloud_render.dsa")
    print("  2. Oder: einen Custom Action Button erstellen:")
    print("     Edit > Preferences > Custom Actions > Add")
    print(f"     Script: {dest}")
    print()
    print("Stelle sicher, dass der Python-Client installiert ist:")
    print("  cd daz-cloud-render/client")
    print("  pip install -e .")
    print("  daz-cloud-render init")


if __name__ == "__main__":
    install()
