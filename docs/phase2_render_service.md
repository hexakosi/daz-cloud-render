# Phase 2: Render-Service + Heartbeat-Watchdog

## Architektur

```
                 ┌──────────────────────────────────┐
                 │       Vast.ai-Instanz             │
                 │                                   │
  Client ──────►│  :8080  Render-Service (Flask)     │
  (Phase 3)      │    │     POST /upload              │
                 │    │     POST /render              │
                 │    │     GET  /status/<id>         │
                 │    │     GET  /results/<name>      │
                 │    │     GET  /health              │
                 │    │                               │
                 │    ▼                               │
                 │  Heartbeat ──► /tmp/daz_heartbeat  │
                 │                     ▲              │
                 │                     │              │
                 │  Watchdog ──────────┘              │
                 │    │  prueft alle 60s              │
                 │    │  Idle > 30min? → DESTROY      │
                 │    │  Uptime > 4h?  → DESTROY      │
                 │    ▼                               │
                 │  vastai destroy instance $ID       │
                 └──────────────────────────────────┘
```

## Komponenten

### 1. Render-Service (`render_service.py`)

Flask-Server auf Port 8080.

**Endpunkte:**

| Methode | Pfad              | Zweck                            |
|---------|--------------------|----------------------------------|
| POST    | /upload            | Dateien hochladen (Multipart)    |
| POST    | /render            | Render-Job starten               |
| GET     | /status            | Alle Jobs auflisten              |
| GET     | /status/<job_id>   | Einzelnen Job abfragen           |
| GET     | /results           | Ergebnis-Dateien auflisten       |
| GET     | /results/<name>    | Ergebnis herunterladen           |
| GET     | /health            | Health-Check + GPU-Info           |
| GET     | /scenes            | Hochgeladene Szenen auflisten    |

**Upload-Beispiel:**

```bash
curl -X POST http://HOST:8080/upload \
  -F "file=@szene.duf" \
  -F "path=People/szene.duf" \
  -F "file=@szene.dbz" \
  -F "path=People/szene.dbz"
```

**Render-Beispiel:**

```bash
curl -X POST http://HOST:8080/render \
  -H "Content-Type: application/json" \
  -d '{
    "scene": "People/szene.duf",
    "output": "mein_render.png",
    "samples": 128,
    "resolution": "1920x1080"
  }'
```

Antwort: `{"job_id": "a1b2c3d4e5f6", "status": "queued"}`

**Status abfragen:**

```bash
curl http://HOST:8080/status/a1b2c3d4e5f6
```

**Ergebnis herunterladen:**

```bash
curl -O http://HOST:8080/results/mein_render.png
```

### 2. Watchdog (`watchdog.py`)

Separater Prozess, der die Instanz ueberwacht und bei Inaktivitaet zerstoert.

**Mechanismus:**

- Jeder API-Aufruf an den Render-Service schreibt einen Timestamp in
  `/tmp/daz_heartbeat`
- Der Watchdog prueft alle 60 Sekunden:
  1. **Harte Grenze**: Uptime > MAX_SESSION_HOURS → Zerstoerung
     (5 Minuten Gnadenfrist wenn Render aktiv)
  2. **Weiche Grenze**: Idle > IDLE_TIMEOUT_MINUTES UND kein Render aktiv → Zerstoerung
- Warnung bei 80% der maximalen Session-Dauer

**Selbstzerstoerung:**

- Primaer: `vastai destroy instance $ID` (braucht `vastai` CLI + API-Key)
- Fallback: Vast.ai REST-API via `curl`
- Ohne API-Key: nur Logging (manuelles Zerstoeren noetig)

**Umgebungsvariablen:**

| Variable             | Default | Beschreibung                      |
|----------------------|---------|-----------------------------------|
| MAX_SESSION_HOURS    | 4       | Maximale Laufzeit in Stunden      |
| IDLE_TIMEOUT_MINUTES | 30      | Inaktivitaets-Timeout in Minuten  |
| VAST_API_KEY         | —       | Fuer Selbstzerstoerung (Laufzeit) |

### 3. Entrypoint (`entrypoint.sh`)

- **Service-Modus** (Standard, kein Argument): Startet Supervisor mit
  Render-Service + Watchdog
- **Direkt-Modus** (mit Argument): Fuehrt den uebergebenen Befehl aus
  (z.B. `blender -b --version`)

### 4. Supervisor

Verwaltet beide Prozesse:
- `render-service`: autostart, autorestart bei Absturz
- `watchdog`: autostart, kein Neustart (Zerstoerung ist endgueltig)

## Sicherheit

- **Kein API-Key im Image**: VAST_API_KEY wird ausschliesslich als
  Laufzeit-Umgebungsvariable uebergeben
- **Pfad-Traversal-Schutz**: Upload und Ergebnis-Abruf pruefen auf `..`
- **Render-Timeout**: Blender-Prozess wird nach 1 Stunde abgebrochen
- **Instanz-Zerstoerung**: Garantiert, dass keine vergessene Instanz laeuft

## Vast.ai-Template (aktualisiert)

```
Image:    DEIN_USERNAME/daz-cloud-render:latest
Ports:    22 (SSH), 8080 (Render-Service)
Disk:     20 GB
Env:
  DAZ_ROOT_PATHS=/workspace/scenes
  MAX_SESSION_HOURS=4
  IDLE_TIMEOUT_MINUTES=30
  VAST_API_KEY=<dein-key>      ← wird NICHT im Image gespeichert!
```

## Typischer Ablauf

```
1. Instanz starten (per CLI oder Web-UI)
2. Health-Check: GET /health
3. Szene hochladen: POST /upload
4. Render starten: POST /render
5. Status pruefen: GET /status/<job_id>
6. Ergebnis holen: GET /results/<name>
7. ggf. weitere Szenen rendern
8. Instanz wird automatisch zerstoert bei Inaktivitaet
   (oder manuell: vastai destroy instance ID)
```
