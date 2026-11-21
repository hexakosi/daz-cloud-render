# Phase 1: Docker-Image bauen und auf Vast.ai testen

## Voraussetzungen

- Docker installiert (lokal oder auf einem Linux-Rechner)
- Vast.ai-Account mit API-Key
- SSH-Key bei Vast.ai hinterlegt

## 1. Docker-Image bauen

```bash
cd daz-cloud-render
docker build -t daz-cloud-render:latest docker/
```

### Blender-Version anpassen

Die Standard-Version ist Blender 5.2.0. Fuer eine andere Version:

```bash
docker build \
  --build-arg BLENDER_VERSION=5.2.2 \
  --build-arg BLENDER_MAJOR=5.2 \
  -t daz-cloud-render:5.2.2 docker/
```

### Lokaler Test (CPU, kein CUDA noetig)

```bash
# Installations-Check
docker run --rm daz-cloud-render:latest \
  blender -b --python /opt/daz-cloud-render/verify_install.py

# Testszene rendern (CPU)
docker run --rm -v /pfad/zu/testszene:/workspace/scenes \
  daz-cloud-render:latest \
  blender -b /workspace/scenes/test_scene.blend \
  --python-expr "import bpy; bpy.context.scene.render.engine='CYCLES'; bpy.context.scene.cycles.device='CPU'; bpy.context.scene.cycles.samples=8; bpy.context.scene.render.filepath='/workspace/results/test'; bpy.ops.render.render(write_still=True)"
```

## 2. Image auf Docker Hub pushen

```bash
# Docker Hub Login
docker login

# Taggen (ersetze DEIN_USERNAME)
docker tag daz-cloud-render:latest DEIN_USERNAME/daz-cloud-render:latest
docker tag daz-cloud-render:latest DEIN_USERNAME/daz-cloud-render:5.2.0

# Pushen
docker push DEIN_USERNAME/daz-cloud-render:latest
docker push DEIN_USERNAME/daz-cloud-render:5.2.0
```

## 3. Vast.ai-Template erstellen

1. Gehe zu [vast.ai/templates](https://cloud.vast.ai/templates/)
2. Klicke "+ New"
3. Einstellungen:
   - **Image:** `DEIN_USERNAME/daz-cloud-render:latest`
   - **Launch Mode:** SSH
   - **Ports:** 22 (SSH)
   - **Disk Space:** 20 GB (fuer Szenen und Texturen)
   - **Umgebungsvariablen:**
     - `DAZ_ROOT_PATHS=/workspace/scenes`
     - `MAX_SESSION_HOURS=4`
     - **NICHT:** VAST_API_KEY (das kommt in die Account-Einstellungen!)
4. Speichern

## 4. Instanz starten

### Per Web-UI
1. Gehe zu [vast.ai/create](https://cloud.vast.ai/create/)
2. Waehle eine GPU (empfohlen: RTX 4090, ~0.30-0.50 $/h)
3. Waehle dein Template
4. "Rent" klicken
5. Warten bis Status "Running"
6. SSH-Verbindung angezeigt kopieren

### Per CLI
```bash
# Vast.ai CLI installieren
pip install vastai

# API-Key setzen
vastai set api-key DEIN_API_KEY

# Angebote suchen (RTX 4090, guenstigster Preis)
vastai search offers 'gpu_name=RTX_4090 num_gpus=1 inet_down>100' -o 'dph_total'

# Instanz erstellen (OFFER_ID aus der Suche)
vastai create instance OFFER_ID \
  --image DEIN_USERNAME/daz-cloud-render:latest \
  --disk 20 \
  --env '-e DAZ_ROOT_PATHS=/workspace/scenes -e MAX_SESSION_HOURS=4'
```

## 5. Manueller Test auf der Instanz

### Verbinden
```bash
ssh -p PORT root@IP_ADRESSE
```

### Installations-Check
```bash
blender -b --python /opt/daz-cloud-render/verify_install.py
```

Erwartete Ausgabe:
```
[VERIFY] Blender: 5.2.0
[VERIFY] Cycles:  verfuegbar
[VERIFY] GPU:     OPTIX
[VERIFY]   - NVIDIA GeForce RTX 4090 (OPTIX)
[VERIFY] DAZ Imp: import_daz geladen
[VERIFY] Ergebnis: ALLES OK
```

### Szene hochladen
```bash
# Auf deinem PC:
scp -P PORT /pfad/zur/szene.duf root@IP:/workspace/scenes/
scp -P PORT /pfad/zur/szene.dbz root@IP:/workspace/scenes/

# Abhaengigkeiten hochladen (Texturen, Geometrien)
# Die Pfadstruktur muss identisch sein wie in der DAZ-Bibliothek!
rsync -avz -e "ssh -p PORT" \
  /pfad/zur/bibliothek/data/ \
  root@IP:/workspace/scenes/data/

rsync -avz -e "ssh -p PORT" \
  /pfad/zur/bibliothek/Runtime/ \
  root@IP:/workspace/scenes/Runtime/
```

### Rendern
```bash
blender -b --python /opt/daz-cloud-render/setup_and_render.py -- \
  --scene /workspace/scenes/szene.duf \
  --output /workspace/results/render.png \
  --samples 128 \
  --resolution 1920x1080 \
  --root-paths /workspace/scenes
```

### Ergebnis herunterladen
```bash
# Auf deinem PC:
scp -P PORT root@IP:/workspace/results/render.png .
```

## 6. Instanz ZERSTOEREN (wichtig!)

```bash
# Per CLI (INSTANCE_ID aus 'vastai show instances')
vastai destroy instance INSTANCE_ID

# NICHT nur stoppen! Gestoppte Instanzen kosten weiter Speichergebuehren.
```

## Haeufige Probleme

### Blender-Download schlaegt fehl
Die Blender-Download-URL kann sich aendern. Pruefe die aktuelle URL auf
blender.org/download und passe BLENDER_VERSION im Dockerfile an.

### "Some assets were not found"
Die DAZ-Root-Pfade stimmen nicht. Stelle sicher, dass die hochgeladene
Ordnerstruktur identisch ist mit der lokalen Bibliothek:
```
/workspace/scenes/
  data/
    daz 3d/genesis 8/female/genesis8female.dsf
  Runtime/
    Textures/DAZ/Characters/...
  People/
    Genesis 8 Female/szene.duf
```

### GPU nicht erkannt
Pruefe mit `nvidia-smi`, ob der CUDA-Treiber korrekt geladen ist.
Falls OptiX nicht geht, faellt das Skript automatisch auf CUDA zurueck.
