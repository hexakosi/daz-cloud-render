"""
Minimaler Headless-Test fuer Diffeomorphic DAZ Importer in Blender.

Aufruf:
    blender -b --python test_headless_import.py
    blender -b --python test_headless_import.py -- /pfad/zur/szene.duf

Voraussetzungen:
  - Blender mit installiertem Diffeomorphic DAZ Importer
  - Die .duf-Szene muss vorher in DAZ Studio mit "Export to Blender" exportiert
    worden sein (erzeugt eine .dbz-Datei neben der .duf)
"""

import sys
import os
import time
import traceback

import bpy
import addon_utils

results = {
    "addon_enable": False,
    "api_import": False,
    "scene_import": False,
    "cycles_setup": False,
    "render": False,
}


def log(msg):
    print(f"[DAZ-TEST] {msg}", flush=True)


def enable_diffeomorphic():
    """Diffeomorphic-Addon aktivieren."""
    log("Schritt 1: Addon aktivieren...")

    addon_names = [
        "import_daz",                       # Legacy Addon (Blender < 4.2)
        "bl_ext.user_default.import_daz",   # Extension (Blender >= 4.2)
    ]

    for name in addon_names:
        try:
            mod = addon_utils.enable(name, default_set=True)
            if mod is not None:
                log(f"  Addon aktiviert: {name}")
                results["addon_enable"] = True
                return name
            else:
                log(f"  '{name}': nicht gefunden")
        except Exception as e:
            log(f"  '{name}': {e}")

    log("  FEHLER: Diffeomorphic konnte nicht aktiviert werden!")
    log("  Ist das Addon installiert? Pruefe den Addon-Ordner.")
    return None


def import_api(addon_name):
    """Diffeomorphic-API importieren."""
    log("Schritt 2: API importieren...")

    # Reihenfolge je nach erkanntem Addon-Namen
    attempts = []
    if addon_name and "bl_ext" in addon_name:
        attempts = [
            ("bl_ext.user_default.import_daz", "api"),
            ("import_daz", "api"),
        ]
    else:
        attempts = [
            ("import_daz", "api"),
            ("bl_ext.user_default.import_daz", "api"),
        ]

    for pkg, mod_name in attempts:
        try:
            mod = __import__(pkg, fromlist=[mod_name])
            api = getattr(mod, mod_name)
            log(f"  API geladen via '{pkg}'")
            results["api_import"] = True
            return api
        except (ModuleNotFoundError, ImportError, AttributeError) as e:
            log(f"  '{pkg}': {e}")

    log("  FEHLER: API nicht ladbar!")
    return None


def import_scene(api, duf_path):
    """DAZ-Szene importieren."""
    log(f"Schritt 3: Szene importieren...")
    log(f"  Datei: {duf_path}")

    if not os.path.isfile(duf_path):
        log(f"  FEHLER: Datei nicht gefunden!")
        return False

    dbz_path = os.path.splitext(duf_path)[0] + ".dbz"
    has_dbz = os.path.isfile(dbz_path)
    log(f"  .dbz vorhanden: {has_dbz}")

    if not has_dbz:
        log("  WARNUNG: Ohne .dbz wird fitMeshes='MORPHED' verwendet (geringere Qualitaet)")

    api.set_silent_mode(True)

    directory = os.path.dirname(duf_path)
    filename = os.path.basename(duf_path)

    try:
        kwargs = {
            "directory": directory,
            "files": [{"name": filename}],
            "fitMeshes": 'DBZFILE' if has_dbz else 'MORPHED',
        }

        result = bpy.ops.daz.easy_import_daz(**kwargs)
        log(f"  Operator-Ergebnis: {result}")

        obj_count = len(bpy.data.objects)
        mesh_count = len([o for o in bpy.data.objects if o.type == 'MESH'])
        log(f"  Objekte: {obj_count} gesamt, {mesh_count} Meshes")

        if mesh_count > 0:
            results["scene_import"] = True
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    verts = len(obj.data.vertices)
                    log(f"    Mesh '{obj.name}': {verts} Vertices")
            return True
        else:
            log("  WARNUNG: Keine Meshes importiert")
            return False

    except Exception as e:
        log(f"  FEHLER: {e}")
        traceback.print_exc()
        try:
            error = api.get_error_message()
            if error:
                log(f"  Diffeomorphic-Meldung: {error}")
        except Exception:
            pass
        return False
    finally:
        api.set_silent_mode(False)


def setup_cycles(samples=16):
    """Cycles einrichten (CPU-Modus fuer lokalen Test)."""
    log(f"Schritt 4: Cycles einrichten (Samples: {samples})...")

    try:
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.device = 'CPU'
        bpy.context.scene.cycles.samples = samples
        bpy.context.scene.render.resolution_x = 320
        bpy.context.scene.render.resolution_y = 240
        bpy.context.scene.render.resolution_percentage = 100

        results["cycles_setup"] = True
        log("  Cycles eingerichtet (CPU, 320x240)")
        return True

    except Exception as e:
        log(f"  FEHLER: {e}")
        traceback.print_exc()
        return False


def render_image(output_path):
    """Bild rendern."""
    log(f"Schritt 5: Rendern...")

    try:
        bpy.context.scene.render.filepath = output_path
        bpy.context.scene.render.image_settings.file_format = 'PNG'

        start = time.time()
        bpy.ops.render.render(write_still=True)
        elapsed = time.time() - start

        if os.path.isfile(output_path):
            size_kb = os.path.getsize(output_path) / 1024
            log(f"  Fertig in {elapsed:.1f}s — {output_path} ({size_kb:.0f} KB)")
            results["render"] = True
            return True
        else:
            log("  FEHLER: Datei nicht erzeugt!")
            return False

    except Exception as e:
        log(f"  FEHLER: {e}")
        traceback.print_exc()
        return False


def main():
    log("=" * 60)
    log("DAZ Cloud Render — Headless-Test")
    log("=" * 60)
    log(f"Blender {bpy.app.version_string}")
    log(f"Python  {sys.version.split()[0]}")
    log(f"Modus   {'Hintergrund' if bpy.app.background else 'GUI'}")
    log("")

    # Argumente nach "--"
    argv = sys.argv
    custom_args = argv[argv.index("--") + 1:] if "--" in argv else []
    duf_path = custom_args[0] if custom_args else None

    if not duf_path:
        log("Kein Szenenpfad. Teste nur Addon-Ladevorgang.")
        log("Aufruf mit Szene: blender -b --python test_headless_import.py -- szene.duf")
        log("")

    # 1. Addon aktivieren
    addon_name = enable_diffeomorphic()
    log("")

    # 2. API importieren
    api = import_api(addon_name) if addon_name else None
    log("")

    if api:
        try:
            roots = api.get_root_paths()
            log(f"Root-Pfade: {roots if roots else '(keine)'}")
        except Exception as e:
            log(f"Root-Pfade: Fehler ({e})")

        # Root-Pfad aus Szenenpfad ableiten, falls noetig
        if duf_path:
            scene_dir = os.path.dirname(os.path.abspath(duf_path))
            # DAZ-Root ist der Ordner, der typische Unterordner wie People/data/Runtime enthaelt
            candidate = scene_dir
            for _ in range(5):
                parent = os.path.dirname(candidate)
                if parent == candidate:
                    break
                # Pruefe ob dieser Ordner wie ein DAZ-Root aussieht
                has_data = os.path.isdir(os.path.join(parent, "data"))
                has_people = os.path.isdir(os.path.join(parent, "People"))
                if has_data and has_people:
                    candidate = parent
                    break
                candidate = parent

            candidate = candidate.replace("\\", "/")
            if candidate not in [r.replace("\\", "/") for r in roots]:
                log(f"  Fuege Root-Pfad hinzu: {candidate}")
                try:
                    api.set_global_setting("rootPaths", roots + [candidate])
                    roots = api.get_root_paths()
                    log(f"  Root-Pfade jetzt: {roots}")
                except Exception as e:
                    log(f"  Root-Pfad setzen fehlgeschlagen: {e}")
        log("")

    # 3-5. Nur mit Szenenpfad
    if duf_path and api:
        import_scene(api, duf_path)
        log("")

        if results["scene_import"]:
            setup_cycles(samples=8)
            log("")

            if results["cycles_setup"]:
                out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_render.png")
                render_image(out)
                log("")

    # Zusammenfassung
    log("=" * 60)
    log("ERGEBNIS")
    log("-" * 60)

    for key, ok in results.items():
        if not ok and not duf_path and key in ("scene_import", "cycles_setup", "render"):
            tag = "SKIP"
        elif ok:
            tag = " OK "
        else:
            tag = "FAIL"
        log(f"  [{tag}] {key}")

    critical_ok = results["addon_enable"] and results["api_import"]
    log("")
    log(f"Headless-Import: {'MACHBAR' if critical_ok else 'NICHT MACHBAR'}")

    if not critical_ok:
        log("Fallback: xvfb-run -a blender --python test_headless_import.py -- szene.duf")

    log("=" * 60)
    sys.exit(0 if critical_ok else 1)


if __name__ == "__main__":
    main()
