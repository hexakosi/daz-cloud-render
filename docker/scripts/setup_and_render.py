"""
Server-seitiges Render-Skript fuer DAZ Cloud Render.

Aufruf:
    blender -b --python setup_and_render.py -- \
        --scene /workspace/scenes/meine_szene.duf \
        --output /workspace/results/render.png \
        --samples 64 \
        --resolution 1920x1080 \
        --root-paths /workspace/scenes

Dieses Skript:
  1. Aktiviert den Diffeomorphic DAZ Importer
  2. Setzt die DAZ-Root-Pfade
  3. Importiert die .duf-Szene
  4. Konfiguriert Cycles (GPU wenn verfuegbar, sonst CPU)
  5. Rendert das Bild
"""

import sys
import os
import time
import json
import argparse
import traceback

import bpy
import addon_utils


def log(msg):
    print(f"[RENDER] {msg}", flush=True)


def parse_args():
    argv = sys.argv
    custom_args = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser(description="DAZ Cloud Render")
    parser.add_argument("--scene", required=True, help="Pfad zur .duf-Datei")
    parser.add_argument("--output", required=True, help="Ausgabepfad fuer das Bild")
    parser.add_argument("--samples", type=int, default=64, help="Render-Samples")
    parser.add_argument("--resolution", default="1920x1080", help="Aufloesung (BxH)")
    parser.add_argument("--root-paths", nargs="+", default=[], help="DAZ-Root-Pfade")
    parser.add_argument("--settings-file", default=None, help="Pfad zu import_daz_settings.json")
    parser.add_argument("--material-config", default=None, help="JSON-Datei mit Material-Anpassungen")
    parser.add_argument("--use-xvfb", action="store_true", help="Xvfb-Modus (intern)")
    return parser.parse_args(custom_args)


def enable_addon():
    """Diffeomorphic-Addon aktivieren."""
    for name in ["import_daz", "bl_ext.user_default.import_daz"]:
        try:
            mod = addon_utils.enable(name, default_set=True)
            if mod is not None:
                log(f"Addon aktiviert: {name}")
                return name
        except Exception:
            continue
    raise RuntimeError("Diffeomorphic DAZ Importer nicht gefunden!")


def import_api(addon_name):
    """API importieren."""
    try:
        if "bl_ext" in addon_name:
            from bl_ext.user_default.import_daz import api
        else:
            from import_daz import api
        return api
    except (ModuleNotFoundError, ImportError):
        pass

    for pkg in ["import_daz", "bl_ext.user_default.import_daz"]:
        try:
            mod = __import__(pkg, fromlist=["api"])
            return mod.api
        except (ModuleNotFoundError, ImportError):
            continue

    raise RuntimeError("Diffeomorphic API nicht ladbar!")


def setup_root_paths(root_paths, settings_file=None):
    """Root-Pfade konfigurieren via Settings-File."""
    if settings_file and os.path.isfile(settings_file):
        log(f"Settings-File vorhanden: {settings_file}")
        return

    # Settings-File generieren
    settings_dir = os.path.expanduser("~/Documents/DAZ Importer")
    os.makedirs(settings_dir, exist_ok=True)
    settings_path = os.path.join(settings_dir, "import_daz_settings.json")

    # Root-Pfade aus Umgebungsvariable ergaenzen
    env_paths = os.environ.get("DAZ_ROOT_PATHS", "").split(os.pathsep)
    all_paths = list(root_paths) + [p for p in env_paths if p and p not in root_paths]
    all_paths = [p.replace("\\", "/") for p in all_paths if os.path.isdir(p)]

    if not all_paths:
        log("WARNUNG: Keine gueltigen Root-Pfade gefunden!")
        log("  Umgebungsvariable DAZ_ROOT_PATHS oder --root-paths setzen.")
        return

    settings = {
        "daz-settings": {
            "contentDirs": all_paths,
            "mdlDirs": [],
            "cloudDirs": [],
        }
    }

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    log(f"Settings-File geschrieben: {settings_path}")
    log(f"Root-Pfade: {all_paths}")


def import_scene(api, scene_path):
    """DAZ-Szene importieren."""
    log(f"Importiere: {scene_path}")

    if not os.path.isfile(scene_path):
        raise FileNotFoundError(f"Szene nicht gefunden: {scene_path}")

    dbz_path = os.path.splitext(scene_path)[0] + ".dbz"
    has_dbz = os.path.isfile(dbz_path)
    fit = "DBZFILE" if has_dbz else "MORPHED"
    log(f"  .dbz vorhanden: {has_dbz}, fitMeshes: {fit}")

    api.set_silent_mode(True)
    try:
        start = time.time()
        result = bpy.ops.daz.easy_import_daz(
            directory=os.path.dirname(scene_path),
            files=[{"name": os.path.basename(scene_path)}],
            fitMeshes=fit,
        )
        elapsed = time.time() - start

        mesh_count = len([o for o in bpy.data.objects if o.type == 'MESH'])
        total = len(bpy.data.objects)
        log(f"  Import in {elapsed:.1f}s — {total} Objekte, {mesh_count} Meshes")

        if mesh_count == 0:
            raise RuntimeError("Keine Meshes importiert!")

        # Default-Cube entfernen
        for obj in bpy.data.objects:
            if obj.name == "Cube" and obj.type == "MESH" and len(obj.data.vertices) == 8:
                bpy.data.objects.remove(obj, do_unlink=True)
                log("  Default-Cube entfernt")
                break

        return result
    finally:
        api.set_silent_mode(False)


def apply_material_config(config_path):
    """Material-Anpassungen anwenden (Iray → Cycles).

    Unterstuetzt zwei Formate:
    1. Einfach: {"subsurface_scale": 0.01, "roughness": 0.4, ...}
    2. Preset: {"global": {...}, "by_type": {"skin": {"match": [...], ...}}}
    """
    if not config_path or not os.path.isfile(config_path):
        return

    log(f"Material-Anpassungen: {config_path}")
    with open(config_path) as f:
        config = json.load(f)

    global_cfg = config.get("global", config)
    type_rules = config.get("by_type", {})
    applied = 0

    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if node.type != 'BSDF_PRINCIPLED':
                    continue

                # Typ-spezifische Regel finden
                mat_cfg = dict(global_cfg)
                mat_name = mat.name.lower()
                for type_name, rule in type_rules.items():
                    patterns = rule.get("match", [type_name])
                    if any(p.lower() in mat_name for p in patterns):
                        mat_cfg.update({k: v for k, v in rule.items()
                                       if k != "match"})
                        break

                _apply_bsdf_settings(node, mat_cfg)
                applied += 1

    log(f"  {applied} Principled-BSDF-Nodes angepasst")


def _apply_bsdf_settings(node, cfg):
    """Einstellungen auf einen Principled-BSDF-Node anwenden."""
    inputs = node.inputs

    # Version-kompatible Input-Namen
    sss_key = "Subsurface Weight" if "Subsurface Weight" in inputs else "Subsurface"
    sss_scale_key = "Subsurface Scale" if "Subsurface Scale" in inputs else None
    spec_key = "Specular IOR Level" if "Specular IOR Level" in inputs else "Specular"
    coat_key = "Coat Weight" if "Coat Weight" in inputs else "Clearcoat" if "Clearcoat" in inputs else None
    coat_rough_key = "Coat Roughness" if "Coat Roughness" in inputs else "Clearcoat Roughness" if "Clearcoat Roughness" in inputs else None
    transmission_key = "Transmission Weight" if "Transmission Weight" in inputs else "Transmission"

    if "subsurface_scale" in cfg:
        target = sss_scale_key or sss_key
        inputs[target].default_value = cfg["subsurface_scale"]

    if "subsurface_color" in cfg and "Subsurface Color" in inputs:
        c = cfg["subsurface_color"]
        inputs["Subsurface Color"].default_value = (c[0], c[1], c[2], 1.0)

    if "roughness" in cfg:
        inputs["Roughness"].default_value = cfg["roughness"]
    elif "roughness_offset" in cfg:
        current = inputs["Roughness"].default_value
        inputs["Roughness"].default_value = max(0.0, min(1.0,
            current + cfg["roughness_offset"]))

    if "specular" in cfg:
        inputs[spec_key].default_value = cfg["specular"]

    if "metallic" in cfg:
        inputs["Metallic"].default_value = cfg["metallic"]

    if "transmission" in cfg and transmission_key in inputs:
        inputs[transmission_key].default_value = cfg["transmission"]

    if "ior" in cfg and "IOR" in inputs:
        inputs["IOR"].default_value = cfg["ior"]

    if "coat" in cfg and coat_key and coat_key in inputs:
        inputs[coat_key].default_value = cfg["coat"]

    if "coat_roughness" in cfg and coat_rough_key and coat_rough_key in inputs:
        inputs[coat_rough_key].default_value = cfg["coat_roughness"]


def setup_cycles(samples, resolution):
    """Cycles mit GPU einrichten."""
    width, height = [int(x) for x in resolution.split("x")]
    log(f"Cycles: {width}x{height}, {samples} Samples")

    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = samples
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    bpy.context.scene.render.resolution_percentage = 100

    # GPU-Erkennung
    prefs = bpy.context.preferences.addons.get('cycles')
    if prefs:
        cprefs = prefs.preferences
        for compute_type in ['OPTIX', 'CUDA']:
            try:
                cprefs.compute_device_type = compute_type
                cprefs.get_devices()
                gpu_devices = [d for d in cprefs.devices if d.type in ('CUDA', 'OPTIX')]
                if gpu_devices:
                    for device in cprefs.devices:
                        device.use = (device.type != 'CPU')
                    bpy.context.scene.cycles.device = 'GPU'
                    log(f"  GPU: {compute_type}")
                    for d in gpu_devices:
                        log(f"    {d.name}")
                    return
            except Exception:
                continue

    log("  Keine GPU gefunden, verwende CPU")
    bpy.context.scene.cycles.device = 'CPU'


def render(output_path):
    """Bild rendern."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    bpy.context.scene.render.filepath = output_path
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.image_settings.color_depth = '16'

    log(f"Rendere nach: {output_path}")
    start = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - start

    if os.path.isfile(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        log(f"Fertig in {elapsed:.1f}s — {size_mb:.1f} MB")
    else:
        raise RuntimeError("Render-Ergebnis nicht erzeugt!")


def main():
    args = parse_args()

    log("=" * 60)
    log("DAZ Cloud Render")
    log("=" * 60)
    log(f"Blender {bpy.app.version_string}")
    log(f"Szene:   {args.scene}")
    log(f"Output:  {args.output}")
    log(f"Samples: {args.samples}")
    log(f"Aufl.:   {args.resolution}")
    log("")

    try:
        # 1. Addon
        addon_name = enable_addon()

        # 2. API
        api = import_api(addon_name)

        # 3. Root-Pfade
        setup_root_paths(args.root_paths, args.settings_file)

        # Addon muss nach Settings-File-Erstellung neu geladen werden
        addon_utils.disable(addon_name)
        addon_name = enable_addon()
        api = import_api(addon_name)

        log(f"Root-Pfade: {api.get_root_paths()}")
        log("")

        # 4. Import
        import_scene(api, args.scene)
        log("")

        # 5. Material-Anpassungen
        apply_material_config(args.material_config)

        # 6. Cycles
        setup_cycles(args.samples, args.resolution)
        log("")

        # 7. Render
        render(args.output)

        log("")
        log("ERFOLGREICH")

    except Exception as e:
        log(f"FEHLER: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
