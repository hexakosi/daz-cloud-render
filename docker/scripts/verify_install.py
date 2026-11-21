"""
Installations-Check fuer das Docker-Image.
Prueft Blender, Cycles, CUDA und Diffeomorphic.

Aufruf:
    blender -b --python verify_install.py
"""

import sys
import bpy
import addon_utils


def log(msg):
    print(f"[VERIFY] {msg}", flush=True)


def main():
    log("=" * 50)
    log("DAZ Cloud Render — Installations-Check")
    log("=" * 50)

    ok = True

    # Blender
    log(f"Blender: {bpy.app.version_string}")
    log(f"Python:  {sys.version.split()[0]}")
    log(f"Modus:   {'Hintergrund' if bpy.app.background else 'GUI'}")

    # Cycles
    try:
        bpy.context.scene.render.engine = 'CYCLES'
        log("Cycles:  verfuegbar")
    except Exception as e:
        log(f"Cycles:  FEHLER ({e})")
        ok = False

    # GPU
    prefs = bpy.context.preferences.addons.get('cycles')
    if prefs:
        cprefs = prefs.preferences
        for ctype in ['OPTIX', 'CUDA']:
            try:
                cprefs.compute_device_type = ctype
                cprefs.get_devices()
                gpus = [d for d in cprefs.devices if d.type in ('CUDA', 'OPTIX')]
                if gpus:
                    log(f"GPU:     {ctype}")
                    for d in gpus:
                        log(f"  - {d.name} ({d.type})")
                    break
            except Exception:
                continue
        else:
            log("GPU:     keine (CPU-Modus)")
    else:
        log("GPU:     Cycles-Addon nicht in Preferences")

    # Diffeomorphic
    addon_ok = False
    for name in ["import_daz", "bl_ext.user_default.import_daz"]:
        try:
            mod = addon_utils.enable(name, default_set=True)
            if mod is not None:
                log(f"DAZ Imp: {name} geladen")
                addon_ok = True

                try:
                    if "bl_ext" in name:
                        from bl_ext.user_default.import_daz import api
                    else:
                        from import_daz import api
                    log(f"API:     verfuegbar")
                    log(f"Roots:   {api.get_root_paths()}")
                except Exception as e:
                    log(f"API:     FEHLER ({e})")
                    ok = False
                break
        except Exception:
            continue

    if not addon_ok:
        log("DAZ Imp: NICHT GEFUNDEN")
        ok = False

    # Xvfb
    import shutil
    if shutil.which("Xvfb"):
        log("Xvfb:    verfuegbar (Fallback)")
    else:
        log("Xvfb:    nicht installiert")

    log("=" * 50)
    log(f"Ergebnis: {'ALLES OK' if ok else 'FEHLER'}")
    log("=" * 50)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
