# Phase 4: DAZ-Script-Button + Session-Fenster

## Uebersicht

Ein DAZ-Studio-Script mit Render-Dialog, das den gesamten Cloud-Render-Workflow
direkt aus DAZ Studio heraus steuert.

```
DAZ Studio
  ┌─────────────────────────────┐
  │  Cloud Render               │
  │                             │
  │  Szene: MeinePose           │
  │  Status: Rendering laeuft  │
  │  ████████░░░░  60%          │
  │                             │
  │  Samples:    [===128===]    │
  │  Aufloesung: [1920x1080 ▼] │
  │                             │
  │     [Render starten] [X]    │
  └─────────────────────────────┘
         │
         ▼ startet Python-Client
  python -m daz_cloud_render go szene.duf -y
         │
         ▼ schreibt Status-Datei
  ~/.daz-cloud-render-status.json
         │
         ▼ DAZ-Script pollt
  Fortschrittsanzeige + Ergebnis oeffnen
```

## Installation

### Automatisch

```bash
cd daz-cloud-render/daz-script
python install.py
```

### Manuell

1. `cloud_render.dsa` kopieren nach:
   `Dokumente/DAZ 3D/Studio/My Library/Scripts/Cloud Render/`
2. In DAZ Studio: **File → Run Script...** → `cloud_render.dsa`

### Als Custom Button

1. **Edit → Preferences → Custom Actions → Add**
2. Script-Pfad angeben
3. Button erscheint in der Toolbar

## Workflow im Detail

### 1. Szene vorbereiten

- Szene in DAZ Studio oeffnen und speichern (.duf)
- Beleuchtung, Kamera, Posen etc. einstellen

### 2. Script starten

- **File → Run Script... → cloud_render.dsa**
- Oder: Custom Button klicken

### 3. Blender-Export

Das Script prueft, ob eine .dbz-Datei neben der .duf existiert:
- **Vorhanden**: Fragt ob neu exportiert oder vorhandene genutzt werden soll
- **Nicht vorhanden**: Versucht den Blender-Export auszuloesen
- **Export fehlschlaegt**: Warnt, dass Mesh-Qualitaet reduziert ist (MORPHED statt DBZFILE)

### 4. Render-Dialog

- **Samples**: 16-1024 (Slider)
- **Aufloesung**: 640x480 bis 3840x2160 (Dropdown)
- **Render starten**: Startet den Python-Client im Hintergrund

### 5. Fortschritt

Das Script pollt `~/.daz-cloud-render-status.json` alle 2 Sekunden:

| Phase | Fortschritt | Beschreibung |
|-------|-------------|-------------|
| start | 1/5 | Vast.ai-Instanz wird gestartet |
| upload | 2/5 | Szene + Abhaengigkeiten hochladen |
| render | 3/5 | GPU-Rendering laeuft |
| download | 4/5 | Ergebnis herunterladen |
| destroy | 5/5 | Instanz zerstoeren |
| done | 5/5 | Fertig — Ergebnis oeffnen |
| error | — | Fehler aufgetreten |

### 6. Ergebnis

- Wird automatisch im Standard-Bildbetrachter geoeffnet
- Liegt im selben Ordner wie die .duf-Datei
- Dateiname: `<job_id>.png` oder benutzerdefiniert

## Status-Datei Format

`~/.daz-cloud-render-status.json`:

```json
{
  "phase": "render",
  "message": "Rendering laeuft...",
  "progress": 3,
  "total": 5,
  "percent": 60.0,
  "timestamp": 1732185600.0,
  "error": null,
  "result_file": null
}
```

Bei Abschluss:
```json
{
  "phase": "done",
  "message": "Fertig!",
  "progress": 5,
  "total": 5,
  "percent": 100.0,
  "result_file": "C:/Users/.../renders/render.png"
}
```

## Dateien

| Datei | Zweck |
|---|---|
| `daz-script/cloud_render.dsa` | DAZ-Studio-Script mit Render-Dialog |
| `daz-script/install.py` | Automatische Installation |
| `client/daz_cloud_render/status_file.py` | Status-Datei-Kommunikation |

## Voraussetzungen

- Python 3 im PATH (`python` aufrufbar)
- `daz-cloud-render` Client installiert und konfiguriert
- DAZ Studio mit gespeicherter Szene
