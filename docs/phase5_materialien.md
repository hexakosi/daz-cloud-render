# Phase 5: Material-Sidebar + Presets

## Uebersicht

Iray-Materialien aus DAZ Studio muessen fuer Cycles angepasst werden.
Phase 5 bietet dafuer:

1. **Preset-Bibliothek** — vorgefertigte Material-Konfigurationen
2. **DAZ-Script Material-Sidebar** — visueller Editor in DAZ Studio
3. **Typ-basiertes Matching** — automatische Erkennung von Haut, Augen, Haaren etc.
4. **CLI-Integration** — `--preset` Parameter beim Rendern

## Presets

| Preset | Beschreibung | Anwendung |
|--------|-------------|-----------|
| `default` | Ausgewogene Einstellungen | Allgemeine Szenen |
| `portrait` | Realistische Haut, feine Augen | Nahaufnahmen, Portraits |
| `product` | Scharfe Materialien, hoher Kontrast | Kleidung, Objekte |
| `fast_preview` | Vereinfacht, keine Typ-Regeln | Schnelle Testrenders |

### Preset-Format

```json
{
  "name": "Portrait",
  "description": "Optimiert fuer Nahaufnahmen",
  "global": {
    "subsurface_scale": 0.015,
    "roughness_offset": 0.0,
    "specular": 0.5
  },
  "by_type": {
    "skin": {
      "match": ["skin", "face", "body", "lip"],
      "subsurface_scale": 0.03,
      "roughness": 0.35
    },
    "eye": {
      "match": ["eye", "cornea", "iris"],
      "roughness": 0.02,
      "specular": 0.9
    }
  }
}
```

### Eigene Presets erstellen

Neue `.json`-Dateien in den `presets/`-Ordner legen.
Die `match`-Listen bestimmen, welche Materialien getroffen werden
(Substring-Suche im Material-Namen, Gross-/Kleinschreibung egal).

## Typ-Matching

Der Server vergleicht jeden Material-Namen mit den `match`-Listen:

```
Material "3_SkinFace" → trifft "skin" und "face" → Haut-Regel
Material "EyeMoisture" → trifft "eye" und "moisture" → Augen-Regel
Material "TShirt_Cotton" → trifft "cotton" → Stoff-Regel
```

Globale Einstellungen gelten fuer alle Materialien, die keiner Typ-Regel
entsprechen. Typ-Regeln ueberschreiben globale Werte.

## Unterstuetzte Material-Parameter

| Parameter | Beschreibung | Blender 3.x | Blender 4.0+ |
|-----------|-------------|-------------|-------------|
| `subsurface_scale` | SSS-Staerke | Subsurface | Subsurface Weight/Scale |
| `subsurface_color` | SSS-Farbe [R,G,B] | Subsurface Color | Subsurface Color |
| `roughness` | Oberflaechenrauheit (absolut) | Roughness | Roughness |
| `roughness_offset` | Rauheit +/- (relativ) | Roughness | Roughness |
| `specular` | Spiegelung | Specular | Specular IOR Level |
| `metallic` | Metallisch | Metallic | Metallic |
| `transmission` | Transparenz | Transmission | Transmission Weight |
| `ior` | Brechungsindex | IOR | IOR |
| `coat` | Klarlack | Clearcoat | Coat Weight |
| `coat_roughness` | Klarlack-Rauheit | Clearcoat Roughness | Coat Roughness |

## DAZ-Script Material-Sidebar

`material_sidebar.dsa` — oeffnet ein Panel in DAZ Studio mit:

- **Preset-Dropdown**: Standard, Portrait, Produktfoto, Schnell, Benutzerdefiniert
- **Globale Regler**: Subsurface, Roughness-Offset, Specular
- **Haut-Regler**: SSS-Staerke, Roughness
- **Augen-Regler**: Roughness
- **Speichern**: Schreibt `~/.daz-cloud-render-material-config.json`

Die gespeicherte Konfiguration wird beim naechsten Render automatisch erkannt.

## CLI-Nutzung

```bash
# Verfuegbare Presets auflisten
daz-cloud-render presets

# Render mit Preset
daz-cloud-render render --preset portrait

# Render mit eigener Config-Datei
daz-cloud-render render --material-config meine_materialien.json

# Kompletter Workflow mit Preset
daz-cloud-render go szene.duf --preset portrait --samples 256

# Ohne Preset: nutzt automatisch die DAZ-Sidebar-Config
# (falls ~/.daz-cloud-render-material-config.json existiert)
```

## Dateien

| Datei | Zweck |
|---|---|
| `presets/default.json` | Standard-Preset (6 Typ-Regeln) |
| `presets/portrait.json` | Portrait-Preset (Haut-optimiert) |
| `presets/product.json` | Produktfoto-Preset (Stoff/Metall) |
| `presets/fast_preview.json` | Schnell-Preset (vereinfacht) |
| `daz-script/material_sidebar.dsa` | DAZ-Studio Material-Panel |
| `docker/scripts/setup_and_render.py` | Erweitertes Material-System (Server) |
