# Phase 3: Lokaler Python-Client

## Uebersicht

Der Client laeuft auf dem lokalen PC und steuert den gesamten Render-Workflow:

```
daz-cloud-render go szene.duf
```

Das fuehrt automatisch aus:
1. Vast.ai-Instanz starten (guenstigstes Angebot)
2. Szene analysieren (Abhaengigkeiten finden)
3. Dateien inkrementell hochladen
4. Render starten und warten
5. Ergebnis herunterladen
6. Instanz zerstoeren

## Installation

```bash
cd daz-cloud-render/client
pip install -e .
```

Oder ohne Installation:

```bash
cd daz-cloud-render/client
python -m daz_cloud_render --help
```

## Ersteinrichtung

```bash
daz-cloud-render init
```

Fragt nach:
- **Vast.ai API-Key** (von vast.ai/account)
- **Docker-Image** (z.B. `deinname/daz-cloud-render:latest`)
- **DAZ-Root-Pfade** (werden automatisch gesucht)

Speichert in `~/.daz-cloud-render.json`.

## Befehle

### analyze — Szene analysieren

```bash
daz-cloud-render analyze "E:/DAZ 3D/lib/People/szene.duf" -v
```

Zeigt:
- Anzahl Referenzen (Geometrien, Texturen, Morphs)
- Aufgeloeste vs. fehlende Dateien
- Upload-Groesse
- Mit `-v`: komplette Dateiliste

### start — Instanz starten

```bash
daz-cloud-render start --gpu RTX_4090
```

Sucht das guenstigste Angebot, zeigt den Preis, fragt nach Bestaetigung.
Speichert die Session-Daten (Host, Ports) in `~/.daz-cloud-render-session.json`.

### upload — Dateien hochladen

```bash
daz-cloud-render upload "E:/DAZ 3D/lib/People/szene.duf"
```

- Analysiert die Szene und findet alle Abhaengigkeiten
- Laedt nur geaenderte Dateien hoch (Hash-basiert)
- Fortschrittsanzeige

### render — Rendern

```bash
daz-cloud-render render --samples 256 --resolution 3840x2160
```

Ohne Argumente: nutzt den Szenenpfad vom letzten Upload.
Wartet auf das Ergebnis (mit `--no-wait` sofort zurueck).

### status — Status pruefen

```bash
daz-cloud-render status          # alle Jobs
daz-cloud-render status abc123   # bestimmter Job
```

### download — Ergebnis holen

```bash
daz-cloud-render download -o ./renders/
```

### destroy — Instanz zerstoeren

```bash
daz-cloud-render destroy -y
```

### go — Alles auf einmal

```bash
daz-cloud-render go "E:/DAZ 3D/lib/People/szene.duf" \
  --samples 128 \
  --resolution 1920x1080 \
  --output-dir ./renders/ \
  -y
```

## Abhaengigkeitsanalyse

Der Client parst .duf-Dateien direkt (gzip-JSON) ohne Blender.
Er extrahiert:

- **Geometrien** (.dsf) — Mesh-Daten
- **Texturen** (.png, .jpg, .tif, ...) — Oberflaechenbilder
- **Morphs** (.dsf/.duf) — Formveraenderungen
- **Materialien** — referenzierte Shader-Daten
- **Rekursiv**: referenzierte .duf/.dsf werden ebenfalls analysiert

Fehlende Dateien werden gewarnt, aber der Upload laeuft trotzdem.

## Inkrementeller Upload

Bei wiederholten Uploads werden nur geaenderte Dateien uebertragen:

```
  Upload fertig in 12s
    Hochgeladen:   3
    Uebersprungen: 847
```

Die Hashes werden pro Session im Speicher gehalten.

## Konfiguration

`~/.daz-cloud-render.json`:

```json
{
  "vast_api_key": "...",
  "docker_image": "deinname/daz-cloud-render:latest",
  "gpu_name": "RTX_4090",
  "disk_gb": 20,
  "max_session_hours": 4,
  "idle_timeout_minutes": 30,
  "default_samples": 128,
  "default_resolution": "1920x1080",
  "daz_root_paths": [
    "E:/DAZ 3D/lib",
    "C:/Users/Public/Documents/My DAZ 3D Library"
  ]
}
```

Umgebungsvariablen ueberschreiben die Datei:
- `VAST_API_KEY`
- `DAZ_CLOUD_IMAGE`
- `DAZ_ROOT_PATHS` (Trennzeichen: `;` auf Windows, `:` auf Linux)

## Architektur

```
client/
  daz_cloud_render/
    __init__.py         — Version
    __main__.py         — python -m Einstieg
    cli.py              — CLI-Befehle (argparse)
    config.py           — Konfiguration laden/speichern
    deps.py             — DAZ-Abhaengigkeitsanalyse
    vastai.py           — Vast.ai REST-API-Wrapper
    render_client.py    — HTTP-Client fuer den Render-Service
  setup.py              — pip install
```

Keine externen Abhaengigkeiten — nur Python-Standardbibliothek.
