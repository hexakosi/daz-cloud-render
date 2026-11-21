# Phase 0: Machbarkeitsanalyse — Headless-Import mit Diffeomorphic

## Kurzfassung

**Ergebnis: Machbar.** Der Diffeomorphic DAZ Importer laesst sich per Python-Skript
in Blender steuern. Eine offizielle Headless-Doku (`blender -b`) gibt es nicht,
aber die technischen Voraussetzungen sind erfuellt. Falls UI-abhaengige Operatoren
Probleme machen, ist Xvfb als Fallback erprobt und zuverlaessig.

---

## 1. Diffeomorphic DAZ Importer — aktueller Stand

| Eigenschaft         | Wert                                                         |
|---------------------|--------------------------------------------------------------|
| Aktuelle Version    | 5.2.0 (August 2026)                                         |
| Blender-Kompat.     | 3.0 bis 5.2 (getestet auf 3.6 und 5.2)                      |
| Repository          | github.com/Diffeomorphic/import_daz                          |
| Lizenz              | GPL-2.0-or-later                                             |
| Skript-Beispiele    | github.com/Diffeomorphic/daz_importer_scripts                |
| API-Dokumentation   | Wiki: Scripting/DAZ Importer Functions + Operators            |

### API-Funktionen (api.py)

Relevante Funktionen fuer unseren Anwendungsfall:

- `set_silent_mode(True)` — Fehlerdialoge unterdruecken (essenziell fuer Headless)
- `get_absolute_path(path)` — DAZ-Pfade relativ zu Root-Pfaden aufloesen
- `get_root_paths()` — konfigurierte DAZ-Root-Pfade auslesen
- `set_global_setting(key, value)` — Einstellungen per Skript setzen
- `update_drivers(ob)` — Treiber nach Morph-Aenderungen aktualisieren
- `set_slider(ob, prop, value)` — Morph-Regler setzen
- `load_daz_file(filepath)` — .duf/.dsf als Python-Dict laden (fuer Abhaengigkeitsanalyse!)

### Import-Operator

```python
bpy.ops.daz.easy_import_daz(
    directory="/pfad/zum/ordner",
    files=[{"name": "szene.duf"}],
    useExpressions=True,
    useJcms=True,
    # ... weitere Optionen
)
```

### Blender 4.2+ Extension-Problem

Ab Blender 4.2 ist das Addon eine "Extension". Der Import-Pfad aendert sich:

```python
try:
    from import_daz import api          # Blender <= 4.1
except ModuleNotFoundError:
    from bl_ext.user_default.import_daz import api  # Blender >= 4.2
```

---

## 2. Headless-Betrieb (`blender -b`)

### Was funktioniert

- **Blender-Hintergrundmodus** (`blender -b --python skript.py`) ist offiziell
  unterstuetzt und wird in der CI-Pipeline von Blender selbst verwendet.
- **Addon-Aktivierung per Skript**: `addon_utils.enable("addon_name")` funktioniert
  im Hintergrundmodus.
- **Cycles-Rendering** funktioniert headless (GPU und CPU).
- **Silent Mode** des Importers unterdrueckt UI-Dialoge.

### Risiken

1. **UI-abhaengige Operatoren**: Manche Blender-Operatoren brauchen ein Fenster-Kontext
   (`bpy.context.window`). Falls `easy_import_daz` intern solche Kontexte nutzt,
   schlaegt er in `blender -b` fehl. Das ist das groesste Risiko — und nur durch
   Testen verifizierbar.

2. **Addon-Pfade**: Im Docker-Container muss das Addon korrekt installiert sein,
   damit `addon_utils` es findet.

3. **Root-Pfade**: Die DAZ-Root-Pfade muessen per Skript gesetzt werden, da es
   im Container keine gespeicherten Blender-Preferences gibt.

### Fallback: Xvfb (virtueller Bildschirm)

Falls der reine Headless-Modus nicht geht:

```bash
apt-get install xvfb
xvfb-run -a blender --python skript.py -- szene.duf
```

Xvfb erzeugt einen virtuellen Bildschirm. Blender laeuft dann nicht im
Hintergrundmodus, hat aber ein vollstaendiges UI-Kontext — nur eben unsichtbar.
Das ist der Standard-Ansatz fuer Blender-Rendering auf Linux-Servern und
funktioniert zuverlaessig.

**Kosten**: Xvfb verbraucht minimal Ressourcen (kein GPU-Speicher, kaum CPU).
Im Docker-Image kommen ca. 5 MB hinzu.

---

## 3. Empfohlene Blender-Version fuer das Docker-Image

| Version | Typ  | Support bis | CUDA/OptiX | Empfehlung                          |
|---------|------|-------------|------------|-------------------------------------|
| 3.6     | LTS  | Juni 2025   | Ja         | Veraltet, kein Support mehr         |
| 4.2     | LTS  | Juli 2026   | Ja         | Stabil, aber Support laeuft aus     |
| 4.4     | LTS  | Jan 2027    | Ja         | **Empfohlen**: aktuelles LTS        |
| 5.2     | Aktuell | -        | Ja         | Cutting Edge, fuer Tests geeignet   |

**Empfehlung: Blender 4.4 LTS** als Standardversion.
- Langzeitsupport (Sicherheitsupdates bis 2027)
- Diffeomorphic 5.2.0 ist kompatibel (3.0 bis 5.2)
- LTS = keine ueberraschenden API-Aenderungen

---

## 4. Workflow DAZ → Blender (auf dem Server)

```
1. Nutzer exportiert in DAZ Studio: "Export to Blender" (erzeugt .dbz neben .duf)
2. Client laedt .duf + .dbz + alle Abhaengigkeiten auf den Server
3. Server: Blender-Skript importiert .duf via Diffeomorphic
   → easy_import_daz mit fitMeshes='DBZFILE'
4. Server: Material-Anpassungen anwenden (Iray → Cycles)
5. Server: Cycles-Rendering
6. Server: Ergebnis (.png) zum Client zuruecksenden
```

### Wichtig: "Export to Blender" muss lokal passieren

Der Schritt "Export to Blender" in DAZ Studio erzeugt die .dbz-Datei, die
Mesh-Fitting-Daten enthaelt. Dieser Schritt erfordert DAZ Studio und kann
**nicht** auf dem Server laufen.

Das bedeutet:
- Der Nutzer muss vor dem Cloud-Rendern einmal "Export to Blender" in DAZ ausfuehren
- Die .dbz-Datei wird zusammen mit der .duf hochgeladen
- Der DAZ-Script-Button kann diesen Export automatisch ausloesen

**Alternative ohne .dbz**: Diffeomorphic kann auch ohne .dbz importieren
(fitMeshes='MORPHED'), aber die Qualitaet ist schlechter.

---

## 5. Abhaengigkeitsanalyse der Szene

Die Funktion `api.load_daz_file(filepath)` laedt .duf-Dateien als Python-Dict.
Das Format ist dokumentiert (DAZ Studio File Format). Daraus lassen sich alle
referenzierten Assets extrahieren:

- Geometrien (.dsf)
- Morphs (.dsf/.duf)
- Texturen (.png, .jpg, .tif, ...)
- Materialien
- Posen

Das ist die Grundlage fuer den inkrementellen Upload in Phase 3.

---

## 6. Lizenz-Situation

| Komponente         | Lizenz        | Auswirkung                                |
|--------------------|---------------|-------------------------------------------|
| Blender            | GPL-2.0+      | Docker-Image: GPL-kompatibel sein          |
| Diffeomorphic      | GPL-2.0+      | Verbreitung im Image: GPL einhalten        |
| Unser Projekt      | ?             | Muss GPL-2.0-kompatibel sein               |

**Da Blender und Diffeomorphic unter GPL stehen und wir deren Code im
Docker-Image verteilen, muss unser Docker-Image GPL-kompatibel lizenziert sein.**

Fuer den Client-Code (DAZ-Script, Python-Hilfsdienst) gilt:
- Er interagiert nur ueber CLI/API mit dem Server → keine abgeleitete Arbeit
- Der Client kann unter einer freieren Lizenz stehen (z.B. MIT)

**Empfehlung:**
- Docker-Image + Server-Skripte: GPL-2.0-or-later
- Client-Code: MIT
- Oder alles GPL-2.0-or-later fuer Einfachheit

---

## 7. Testanleitung

### Voraussetzungen
- Blender >= 4.2 installiert (lokal, zum Testen)
- Diffeomorphic DAZ Importer installiert und aktiviert
- Eine DAZ-Szene (.duf) mit "Export to Blender" exportiert (.dbz vorhanden)

### Test ohne Szene (nur Addon-Check)

```
blender -b --python tests/test_headless_import.py
```

Prueft: Kann das Addon geladen und aktiviert werden?

### Test mit Szene

```
blender -b --python tests/test_headless_import.py -- "C:/pfad/zur/szene.duf"
```

Prueft: Import, Cycles-Setup, Rendering.

### Falls Headless fehlschlaegt

```
# Unter WSL oder Linux:
xvfb-run -a blender --python tests/test_headless_import.py -- /pfad/zur/szene.duf
```

---

## 8. Naechste Schritte (Phase 1)

Wenn der Headless-Test bestanden ist:
1. Dockerfile erstellen (Blender 4.4 LTS + CUDA + Diffeomorphic)
2. Testszene ohne kommerzielle Inhalte erstellen (leere Szene mit Primitiven)
3. Docker-Image bauen und lokal testen
4. Auf Vast.ai manuell testen
