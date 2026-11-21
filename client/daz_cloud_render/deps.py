"""
DAZ-Szenen-Abhaengigkeitsanalyse.

Parst .duf/.dsf-Dateien (gzip-JSON) und extrahiert alle referenzierten Assets:
Geometrien, Texturen, Morphs, Materialien.

Lizenz: MIT
"""

import os
import re
import json
import gzip
from pathlib import Path


def load_daz_file(filepath):
    """DAZ-Datei laden (.duf/.dsf — gzip-JSON oder plain JSON)."""
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {filepath}")

    data = filepath.read_bytes()

    # gzip-komprimiert?
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)

    return json.loads(data)


def extract_references(daz_data, seen=None):
    """Alle Datei-Referenzen aus einer DAZ-Datenstruktur extrahieren."""
    if seen is None:
        seen = set()
    refs = set()

    if isinstance(daz_data, dict):
        for key, value in daz_data.items():
            if key == "url" and isinstance(value, str):
                clean = _clean_ref(value)
                if clean:
                    refs.add(clean)
            elif key in ("geometry", "source") and isinstance(value, str):
                clean = _clean_ref(value)
                if clean:
                    refs.add(clean)
            elif key == "map" and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and "url" in item:
                        clean = _clean_ref(item["url"])
                        if clean:
                            refs.add(clean)
            else:
                refs.update(extract_references(value, seen))
    elif isinstance(daz_data, list):
        for item in daz_data:
            refs.update(extract_references(item, seen))

    return refs


def _clean_ref(ref):
    """DAZ-Referenz bereinigen (Fragment entfernen, normalisieren)."""
    if not ref or not isinstance(ref, str):
        return None

    # Fragment (#...) entfernen
    ref = ref.split("#")[0]
    if not ref:
        return None

    # Relative Referenzen (./ oder ohne /) ueberspringen
    if not ref.startswith("/"):
        return None

    # Fuehrenden Slash entfernen
    ref = ref.lstrip("/")

    # Backslashes normalisieren
    ref = ref.replace("\\", "/")

    return ref


def resolve_references(refs, root_paths):
    """Referenzen gegen Root-Pfade aufloesen. Gibt {ref: absoluter_pfad} zurueck."""
    resolved = {}

    for ref in refs:
        for root in root_paths:
            candidate = Path(root) / ref
            if candidate.is_file():
                resolved[ref] = str(candidate)
                break

    return resolved


def find_texture_references(daz_data):
    """Speziell Textur-Referenzen finden (Bilder)."""
    texture_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".hdr", ".exr"}
    all_refs = extract_references(daz_data)
    return {r for r in all_refs if Path(r).suffix.lower() in texture_exts}


def analyze_scene(scene_path, root_paths):
    """Komplette Szenen-Analyse: alle Abhaengigkeiten finden und aufloesen.

    Returns:
        dict mit:
          - scene_file: Pfad zur Szenendatei
          - references: alle gefundenen Referenzen
          - resolved: {ref: absoluter_pfad} fuer gefundene Dateien
          - missing: Referenzen ohne passende Datei
          - textures: nur Textur-Referenzen
          - total_size_mb: Gesamtgroesse aller gefundenen Dateien
          - files_to_upload: Liste von (relativer_pfad, absoluter_pfad)
    """
    scene_path = Path(scene_path)
    daz_data = load_daz_file(scene_path)

    refs = extract_references(daz_data)
    textures = find_texture_references(daz_data)
    resolved = resolve_references(refs, root_paths)
    missing = refs - set(resolved.keys())

    # Rekursiv: referenzierte .duf/.dsf-Dateien auch analysieren
    sub_refs = set()
    for ref, abs_path in list(resolved.items()):
        ext = Path(abs_path).suffix.lower()
        if ext in (".duf", ".dsf"):
            try:
                sub_data = load_daz_file(abs_path)
                sub = extract_references(sub_data)
                sub_refs.update(sub)
            except Exception:
                pass

    if sub_refs:
        new_refs = sub_refs - refs
        if new_refs:
            sub_resolved = resolve_references(new_refs, root_paths)
            resolved.update(sub_resolved)
            missing.update(new_refs - set(sub_resolved.keys()))
            refs.update(new_refs)

    # Upload-Liste zusammenstellen
    files_to_upload = []

    # Szenendatei selbst
    scene_rel = scene_path.name
    files_to_upload.append((scene_rel, str(scene_path)))

    # .dbz neben der Szene
    dbz_path = scene_path.with_suffix(".dbz")
    if dbz_path.is_file():
        files_to_upload.append((dbz_path.name, str(dbz_path)))

    # Alle aufgeloesten Abhaengigkeiten
    for ref, abs_path in sorted(resolved.items()):
        files_to_upload.append((ref, abs_path))

    # Gesamtgroesse berechnen
    total_bytes = sum(
        os.path.getsize(abs_path)
        for _, abs_path in files_to_upload
        if os.path.isfile(abs_path)
    )

    return {
        "scene_file": str(scene_path),
        "references": sorted(refs),
        "resolved": resolved,
        "missing": sorted(missing),
        "textures": sorted(textures),
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "file_count": len(files_to_upload),
        "files_to_upload": files_to_upload,
    }
