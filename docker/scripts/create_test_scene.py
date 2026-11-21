"""
Erzeugt eine einfache Testszene ohne kommerzielle Inhalte.
Fuer CI-Tests und Installations-Checks.

Aufruf:
    blender -b --python create_test_scene.py -- --output /pfad/test_scene.blend

Die Szene enthaelt:
  - Eine Kugel mit Principled BSDF (Hautfarbe)
  - Einen Boden
  - Ein Licht (Area Light)
  - Eine Kamera
"""

import sys
import os
import math

import bpy


def log(msg):
    print(f"[TEST-SCENE] {msg}", flush=True)


def main():
    argv = sys.argv
    custom_args = argv[argv.index("--") + 1:] if "--" in argv else []
    output = custom_args[0] if custom_args else "/workspace/test_scene.blend"
    if custom_args and custom_args[0] == "--output" and len(custom_args) > 1:
        output = custom_args[1]

    log("Erstelle Testszene...")

    # Alles loeschen
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Boden
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Boden"
    mat_floor = bpy.data.materials.new("Boden_Material")
    mat_floor.use_nodes = True
    bsdf = mat_floor.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
    floor.data.materials.append(mat_floor)

    # Kugel (Kopf-Ersatz)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0, 0, 1.6), segments=32, ring_count=16)
    head = bpy.context.active_object
    head.name = "Kopf"
    mat_skin = bpy.data.materials.new("Haut_Material")
    mat_skin.use_nodes = True
    bsdf = mat_skin.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.8, 0.6, 0.5, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    # Blender 4.0+: "Subsurface Weight", Blender 3.x: "Subsurface"
    sss_name = "Subsurface Weight" if "Subsurface Weight" in bsdf.inputs else "Subsurface"
    bsdf.inputs[sss_name].default_value = 0.3
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (0.5, 0.2, 0.1)
    head.data.materials.append(mat_skin)

    # Koerper (Zylinder)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=1.2, location=(0, 0, 0.9))
    body = bpy.context.active_object
    body.name = "Koerper"
    body.data.materials.append(mat_skin)

    # Area Light
    bpy.ops.object.light_add(type='AREA', location=(2, -2, 3))
    light = bpy.context.active_object
    light.name = "Hauptlicht"
    light.data.energy = 200
    light.data.size = 2
    light.rotation_euler = (math.radians(45), 0, math.radians(45))

    # Kamera
    bpy.ops.object.camera_add(location=(2.5, -2.5, 1.8))
    cam = bpy.context.active_object
    cam.name = "Kamera"
    cam.rotation_euler = (math.radians(70), 0, math.radians(45))
    bpy.context.scene.camera = cam

    # Render-Settings
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = 32
    bpy.context.scene.render.resolution_x = 640
    bpy.context.scene.render.resolution_y = 480

    # Speichern
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(output))
    log(f"Testszene gespeichert: {output}")


if __name__ == "__main__":
    main()
