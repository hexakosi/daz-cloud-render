# DAZ Cloud Render

GPU-Rendering von DAZ-Studio-Szenen auf gemieteten Cloud-Servern (Vast.ai).

**Problem:** DAZ Studio rendert mit Iray auf der lokalen GPU. Ohne leistungsfaehige
Nvidia-GPU dauert ein Render ewig oder geht gar nicht.

**Loesung:** Szene automatisch analysieren, auf einen gemieteten GPU-Server hochladen,
dort in Blender/Cycles rendern, Ergebnis herunterladen, Server zerstoeren.

```
DAZ Studio  →  Diffeomorphic Import  →  Blender Cycles (GPU)  →  Ergebnis
   lokal          auf dem Server           RTX 4090 etc.          zurueck
```

## Schnellstart

```bash
# 1. Client installieren
cd client
pip install -e .

# 2. Konfigurieren (API-Key, Docker-Image, DAZ-Pfade)
daz-cloud-render init

# 3. Szene analysieren
daz-cloud-render analyze "E:/DAZ 3D/lib/People/MeineSzene.duf" -v

# 4. Komplett-Workflow (Start → Upload → Render → Download → Destroy)
daz-cloud-render go "E:/DAZ 3D/lib/People/MeineSzene.duf" --samples 128 -y
```

Oder direkt aus DAZ Studio: **File → Run Script → cloud_render.dsa**

## Architektur

```
┌─────────────┐          ┌──────────────────────────────────┐
│  Dein PC    │          │  Vast.ai GPU-Server              │
│             │          │                                  │
│  DAZ Studio │  .duf    │  Flask Render-Service (:8080)    │
│  ──────────►│──upload─►│  ──► Blender + Diffeomorphic     │
│             │          │  ──► Cycles GPU Render            │
│  Python     │  .png    │  ──► Ergebnis                    │
│  Client  ◄──│◄─download│                                  │
│             │          │  Watchdog (Selbstzerstoerung)    │
└─────────────┘          └──────────────────────────────────┘
```

## Komponenten

| Verzeichnis | Lizenz | Beschreibung |
|-------------|--------|-------------|
| `docker/` | GPL-2.0+ | Dockerfile, Render-Skript, Watchdog |
| `client/` | MIT | Python-CLI fuer Vast.ai + Upload + Render |
| `daz-script/` | MIT | DAZ-Studio-Skripte (Render-Dialog, Material-Sidebar) |
| `presets/` | MIT | Material-Presets (Haut, Augen, Metall etc.) |

## Features

- **Ein-Befehl-Workflow**: `daz-cloud-render go szene.duf` macht alles
- **Abhaengigkeitsanalyse**: Parst .duf-Dateien, findet alle Texturen und Geometrien
- **Inkrementeller Upload**: Nur geaenderte Dateien werden hochgeladen
- **Material-Presets**: Iray → Cycles Anpassung mit typ-basiertem Matching
- **Selbstzerstoerung**: Instanz wird nach Inaktivitaet automatisch geloescht
- **Kein Vendor-Lock-in**: Vast.ai REST-API, Standard-Docker

## Sicherheit

- **Keine Secrets im Image**: API-Keys nur als Laufzeit-Umgebungsvariablen
- **Keine kommerziellen Inhalte im Repo**: DAZ-Assets werden pro Sitzung hochgeladen
- **Gitleaks**: Automatisches Secret-Scanning in der CI-Pipeline
- **Instanz-Zerstoerung**: Watchdog + Idle-Timeout verhindern vergessene Server
- **Pfad-Traversal-Schutz**: Upload/Download validieren Pfade

## Voraussetzungen

- Python >= 3.8
- Docker (zum Bauen des Images)
- Vast.ai-Account mit API-Key
- DAZ Studio (fuer die Szenen)

## Docker-Image bauen

```bash
docker build -t daz-cloud-render:latest docker/
docker tag daz-cloud-render:latest DEIN_USERNAME/daz-cloud-render:latest
docker push DEIN_USERNAME/daz-cloud-render:latest
```

Details: [docs/phase1_anleitung.md](docs/phase1_anleitung.md)

## Material-Presets

```bash
# Verfuegbare Presets
daz-cloud-render presets

# Render mit Portrait-Preset
daz-cloud-render go szene.duf --preset portrait
```

| Preset | Beschreibung |
|--------|-------------|
| `default` | Ausgewogen fuer allgemeine Szenen |
| `portrait` | Realistische Haut, feine Augen |
| `product` | Scharfe Stoffe, glaenzendes Metall |
| `fast_preview` | Vereinfacht fuer schnelle Tests |

Eigene Presets: JSON-Datei in `presets/` ablegen.
Details: [docs/phase5_materialien.md](docs/phase5_materialien.md)

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [Phase 0: Machbarkeit](docs/phase0_machbarkeit.md) | Headless-Import, Blender-Versionen, Lizenzen |
| [Phase 1: Docker-Image](docs/phase1_anleitung.md) | Build, Push, Vast.ai-Template, manueller Test |
| [Phase 2: Render-Service](docs/phase2_render_service.md) | HTTP-API, Watchdog, Selbstzerstoerung |
| [Phase 3: Python-Client](docs/phase3_client.md) | CLI-Befehle, Konfiguration, Upload |
| [Phase 4: DAZ-Script](docs/phase4_daz_script.md) | Render-Dialog, Blender-Export, Fortschritt |
| [Phase 5: Materialien](docs/phase5_materialien.md) | Presets, Sidebar, Typ-Matching |

## Lizenz

- **Docker-Image + Server-Skripte**: GPL-2.0-or-later (wegen Blender + Diffeomorphic)
- **Client + DAZ-Skripte**: MIT

Siehe [LICENSE-GPL](LICENSE-GPL) und [LICENSE-MIT](LICENSE-MIT).
