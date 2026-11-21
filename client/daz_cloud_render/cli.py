"""
CLI fuer DAZ Cloud Render.

Befehle:
  init       — Konfiguration erstellen
  analyze    — Szene analysieren (Abhaengigkeiten auflisten)
  start      — RunPod-Pod starten
  upload     — Szene + Abhaengigkeiten hochladen
  render     — Render-Job starten
  status     — Job-Status abfragen
  download   — Ergebnis herunterladen
  destroy    — Pod zerstoeren
  go         — Kompletter Workflow (start → upload → render → download → destroy)

Lizenz: MIT
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

from . import __version__
from .config import load_config, save_config, auto_detect_daz_paths
from .deps import analyze_scene
from .runpod import RunpodClient, RunpodError
from .render_client import RenderClient, RenderClientError
from .status_file import write_status, clear_status

SESSION_FILE = Path.home() / ".daz-cloud-render-session.json"
PRESETS_DIR = Path(__file__).parent.parent.parent / "presets"


def log(msg):
    print(f"[DAZ-CR] {msg}", flush=True)


def save_session(data):
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_session():
    if not SESSION_FILE.is_file():
        return None
    try:
        with open(SESSION_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_session():
    if SESSION_FILE.is_file():
        SESSION_FILE.unlink()


def _load_preset(name_or_path):
    """Preset laden: Name (z.B. 'portrait') oder Dateipfad."""
    path = Path(name_or_path)
    if path.is_file():
        with open(path) as f:
            return json.load(f)

    # Nach Name suchen
    preset_file = PRESETS_DIR / f"{name_or_path}.json"
    if preset_file.is_file():
        with open(preset_file) as f:
            return json.load(f)

    raise FileNotFoundError(f"Preset nicht gefunden: {name_or_path}")


def cmd_presets(args):
    """Verfuegbare Presets auflisten."""
    if not PRESETS_DIR.is_dir():
        log("Kein Presets-Ordner gefunden.")
        return

    log("Verfuegbare Material-Presets:")
    for f in sorted(PRESETS_DIR.glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            name = data.get("name", f.stem)
            desc = data.get("description", "")
            log(f"  {f.stem:15s}  {name} — {desc}")
        except Exception:
            log(f"  {f.stem:15s}  (Fehler beim Lesen)")


# --- Commands ---

def cmd_init(args):
    """Konfiguration erstellen oder aktualisieren."""
    config = load_config()

    if not config["runpod_api_key"]:
        key = input("RunPod API-Key: ").strip()
        if key:
            config["runpod_api_key"] = key

    if not config["docker_image"]:
        image = input("Docker-Image (z.B. deinname/daz-cloud-render:latest): ").strip()
        if image:
            config["docker_image"] = image

    if not config["daz_root_paths"]:
        detected = auto_detect_daz_paths()
        if detected:
            log(f"DAZ-Pfade gefunden: {detected}")
            config["daz_root_paths"] = detected
        else:
            paths = input("DAZ-Root-Pfade (kommagetrennt): ").strip()
            if paths:
                config["daz_root_paths"] = [p.strip() for p in paths.split(",")]

    save_config(config)
    log(f"Konfiguration gespeichert: {Path.home() / '.daz-cloud-render.json'}")

    # Zusammenfassung
    log(f"  API-Key:    {'*' * 8 + config['runpod_api_key'][-4:] if config['runpod_api_key'] else 'NICHT GESETZT'}")
    log(f"  Image:      {config['docker_image'] or 'NICHT GESETZT'}")
    log(f"  GPU:        {config['gpu_name']}")
    log(f"  Root-Pfade: {config['daz_root_paths']}")


def cmd_analyze(args):
    """Szene analysieren und Abhaengigkeiten auflisten."""
    config = load_config()
    root_paths = args.root_paths or config["daz_root_paths"]

    if not root_paths:
        log("Keine DAZ-Root-Pfade konfiguriert. Nutze 'init' oder --root-paths.")
        sys.exit(1)

    log(f"Analysiere: {args.scene}")
    result = analyze_scene(args.scene, root_paths)

    log(f"  Referenzen:  {len(result['references'])}")
    log(f"  Aufgeloest:  {len(result['resolved'])}")
    log(f"  Fehlend:     {len(result['missing'])}")
    log(f"  Texturen:    {len(result['textures'])}")
    log(f"  Dateien:     {result['file_count']}")
    log(f"  Groesse:     {result['total_size_mb']} MB")

    if result["missing"]:
        log("")
        log("FEHLENDE DATEIEN:")
        for m in result["missing"][:20]:
            log(f"  ! {m}")
        if len(result["missing"]) > 20:
            log(f"  ... und {len(result['missing']) - 20} weitere")

    if args.verbose:
        log("")
        log("UPLOAD-LISTE:")
        for rel, abs_path in result["files_to_upload"]:
            size = os.path.getsize(abs_path) / (1024 * 1024)
            log(f"  {rel}  ({size:.1f} MB)")


def cmd_start(args):
    """RunPod-Pod starten."""
    config = load_config()
    client = RunpodClient(config["runpod_api_key"])

    gpu = args.gpu or config["gpu_name"]
    image = args.image or config["docker_image"]

    if not image:
        log("Kein Docker-Image konfiguriert. Nutze --image oder 'init'.")
        sys.exit(1)

    log(f"Suche {gpu}-Angebote...")
    offers = client.search_offers(gpu_name=gpu)

    if not offers:
        log(f"Keine {gpu}-Angebote verfuegbar!")
        sys.exit(1)

    best = offers[0]
    price = best["price_per_hour"]
    log(f"Guenstigstes Angebot: ${price:.3f}/h")
    log(f"  GPU: {best['display_name']}")
    log(f"  RAM: {best['vram_gb']} GB VRAM")

    if not args.yes:
        confirm = input(f"Pod starten fuer ${price:.3f}/h? (j/N) ").strip().lower()
        if confirm not in ("j", "ja", "y", "yes"):
            log("Abgebrochen.")
            return

    log("Erstelle Pod...")
    env_vars = {
        "DAZ_ROOT_PATHS": "/workspace/scenes",
        "MAX_SESSION_HOURS": str(config["max_session_hours"]),
        "IDLE_TIMEOUT_MINUTES": str(config["idle_timeout_minutes"]),
        "RUNPOD_API_KEY": config["runpod_api_key"],
    }

    result = client.create_pod(
        name="daz-cloud-render",
        docker_image=image,
        gpu_type_id=best["id"],
        cloud_type=best["cloud_type"],
        disk_gb=config["disk_gb"],
        env_vars=env_vars,
    )

    pod_id = result.get("id", "?")
    log(f"Pod erstellt: {pod_id}")
    log("Warte auf Start...")

    info = client.wait_for_running(pod_id)
    log("Pod laeuft!")
    log(f"  Service: http://{info['host']}:{info['service_port']}")
    log(f"  GPU:     {info['gpu']}")

    save_session({
        "instance_id": pod_id,
        "host": info["host"],
        "ssh_port": info["ssh_port"],
        "service_port": info["service_port"],
        "started": time.time(),
        "image": image,
    })

    log(f"Session gespeichert: {SESSION_FILE}")


def cmd_upload(args):
    """Szene + Abhaengigkeiten hochladen."""
    config = load_config()
    session = load_session()

    if not session:
        log("Keine aktive Session. Starte erst eine Instanz mit 'start'.")
        sys.exit(1)

    root_paths = args.root_paths or config["daz_root_paths"]
    if not root_paths:
        log("Keine DAZ-Root-Pfade konfiguriert.")
        sys.exit(1)

    log(f"Analysiere: {args.scene}")
    analysis = analyze_scene(args.scene, root_paths)
    log(f"  {analysis['file_count']} Dateien, {analysis['total_size_mb']} MB")

    if analysis["missing"]:
        log(f"  WARNUNG: {len(analysis['missing'])} fehlende Referenzen")

    client = RenderClient(session["host"], session["service_port"])

    log("Warte auf Service...")
    client.wait_for_service()

    log("Lade hoch...")
    start = time.time()

    def progress(i, total, name):
        pct = (i / total) * 100 if total else 0
        print(f"\r  [{pct:3.0f}%] {i}/{total} — {name[:60]}", end="", flush=True)

    result = client.upload_files(
        analysis["files_to_upload"],
        progress_fn=progress,
    )

    elapsed = time.time() - start
    print()
    log(f"Upload fertig in {elapsed:.0f}s")
    log(f"  Hochgeladen: {result['uploaded']}")
    log(f"  Uebersprungen: {result['skipped']}")
    if result["failed"]:
        log(f"  Fehlgeschlagen: {len(result['failed'])}")
        for path, err in result["failed"]:
            log(f"    ! {path}: {err}")

    # Scene-Pfad merken
    session["last_scene"] = analysis["files_to_upload"][0][0]
    save_session(session)


def cmd_render(args):
    """Render-Job starten."""
    config = load_config()
    session = load_session()

    if not session:
        log("Keine aktive Session.")
        sys.exit(1)

    scene = args.scene_path or session.get("last_scene")
    if not scene:
        log("Kein Szenenpfad angegeben und keiner aus Upload bekannt.")
        sys.exit(1)

    client = RenderClient(session["host"], session["service_port"])

    samples = args.samples or config["default_samples"]
    resolution = args.resolution or config["default_resolution"]

    # Material-Config laden (Preset, Datei oder DAZ-Sidebar-Export)
    material_config = None
    preset_path = getattr(args, "preset", None)
    mat_config_path = getattr(args, "material_config", None)

    if preset_path:
        material_config = _load_preset(preset_path)
    elif mat_config_path:
        with open(mat_config_path) as f:
            material_config = json.load(f)
    else:
        # DAZ-Sidebar-Export automatisch erkennen
        sidebar_config = Path.home() / ".daz-cloud-render-material-config.json"
        if sidebar_config.is_file():
            with open(sidebar_config) as f:
                material_config = json.load(f)
            log(f"  Material-Preset: {material_config.get('name', 'Benutzerdefiniert')}")

    log(f"Starte Render: {scene}")
    log(f"  Samples: {samples}, Aufloesung: {resolution}")

    result = client.start_render(
        scene_path=scene,
        output=args.output,
        samples=samples,
        resolution=resolution,
        material_config=material_config,
    )

    job_id = result.get("job_id", "?")
    log(f"Job gestartet: {job_id}")

    session["last_job_id"] = job_id
    save_session(session)

    if not args.no_wait:
        log("Warte auf Ergebnis...")

        def progress(status):
            elapsed = status.get("elapsed_s", 0)
            print(f"\r  Rendering... {elapsed:.0f}s", end="", flush=True)

        try:
            final = client.wait_for_render(job_id, progress_fn=progress)
            print()
            duration = final.get("duration_s", 0)
            size = final.get("size_mb", 0)
            log(f"Render fertig: {duration:.0f}s, {size:.1f} MB")
            session["last_output"] = final.get("output", args.output)
            save_session(session)
        except RenderClientError as e:
            print()
            log(f"Render-Fehler: {e}")
            sys.exit(1)


def cmd_status(args):
    """Job-Status abfragen."""
    session = load_session()
    if not session:
        log("Keine aktive Session.")
        sys.exit(1)

    client = RenderClient(session["host"], session["service_port"])
    job_id = args.job_id or session.get("last_job_id")

    result = client.get_status(job_id)
    print(json.dumps(result, indent=2))


def cmd_download(args):
    """Ergebnis herunterladen."""
    session = load_session()
    if not session:
        log("Keine aktive Session.")
        sys.exit(1)

    client = RenderClient(session["host"], session["service_port"])
    filename = args.filename or session.get("last_output")

    if not filename:
        log("Keine Ergebnis-Datei bekannt. Ergebnisse:")
        results = client.list_results()
        for f in results.get("files", []):
            log(f"  {f['name']}  ({f['size_mb']} MB)")
        return

    dest_dir = args.output_dir or "."
    log(f"Lade herunter: {filename}")
    path = client.download_result(filename, dest_dir)
    log(f"Gespeichert: {path}")


def cmd_destroy(args):
    """Pod zerstoeren."""
    config = load_config()
    session = load_session()

    if not session:
        log("Keine aktive Session.")
        sys.exit(1)

    instance_id = session.get("instance_id")
    if not instance_id:
        log("Keine Pod-ID in der Session.")
        sys.exit(1)

    if not args.yes:
        confirm = input(f"Pod {instance_id} zerstoeren? (j/N) ").strip().lower()
        if confirm not in ("j", "ja", "y", "yes"):
            log("Abgebrochen.")
            return

    client = RunpodClient(config["runpod_api_key"])

    log(f"Zerstoere Pod {instance_id}...")
    client.destroy_pod(instance_id)
    log("Pod zerstoert.")

    elapsed = time.time() - session.get("started", time.time())
    log(f"Session-Dauer: {elapsed / 60:.0f} Minuten")

    clear_session()


def cmd_go(args):
    """Kompletter Workflow: start → upload → render → download → destroy."""
    config = load_config()
    clear_status()

    log("=" * 60)
    log("DAZ Cloud Render — Kompletter Workflow")
    log("=" * 60)
    log(f"Szene: {args.scene}")
    log("")

    try:
        # 1. Start
        write_status("start", "Instanz wird gestartet...", 1, 5)
        log("--- 1/5: Instanz starten ---")
        start_args = argparse.Namespace(
            gpu=args.gpu, image=args.image, yes=args.yes,
        )
        cmd_start(start_args)
        log("")

        # 2. Upload
        write_status("upload", "Szene wird hochgeladen...", 2, 5)
        log("--- 2/5: Szene hochladen ---")
        upload_args = argparse.Namespace(
            scene=args.scene,
            root_paths=args.root_paths,
        )
        cmd_upload(upload_args)
        log("")

        # 3. Render
        write_status("render", "Rendering laeuft...", 3, 5)
        log("--- 3/5: Rendern ---")
        render_args = argparse.Namespace(
            scene_path=None,
            output=args.output,
            samples=args.samples,
            resolution=args.resolution,
            no_wait=False,
            preset=getattr(args, "preset", None),
            material_config=getattr(args, "material_config", None),
        )
        cmd_render(render_args)
        log("")

        # 4. Download
        write_status("download", "Ergebnis wird heruntergeladen...", 4, 5)
        log("--- 4/5: Ergebnis herunterladen ---")
        download_args = argparse.Namespace(
            filename=None,
            output_dir=args.output_dir or ".",
        )
        cmd_download(download_args)
        log("")

        # 5. Destroy
        write_status("destroy", "Instanz wird zerstoert...", 5, 5)
        log("--- 5/5: Instanz zerstoeren ---")
        destroy_args = argparse.Namespace(yes=True)
        cmd_destroy(destroy_args)

        # Ergebnis-Datei fuer DAZ-Script
        session = load_session()
        result_file = None
        if session and session.get("last_output"):
            out_dir = args.output_dir or "."
            result_file = str(Path(out_dir) / session["last_output"])

        write_status("done", "Fertig!", 5, 5, result_file=result_file)
        log("")
        log("=" * 60)
        log("FERTIG")
        log("=" * 60)

    except Exception as e:
        write_status("error", str(e), error=str(e))
        raise


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        prog="daz-cloud-render",
        description="DAZ Studio Cloud Rendering auf RunPod",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", help="Befehl")

    # init
    sub.add_parser("init", help="Konfiguration erstellen")

    # analyze
    p = sub.add_parser("analyze", help="Szene analysieren")
    p.add_argument("scene", help="Pfad zur .duf-Datei")
    p.add_argument("--root-paths", nargs="+", help="DAZ-Root-Pfade")
    p.add_argument("-v", "--verbose", action="store_true")

    # start
    p = sub.add_parser("start", help="RunPod-Pod starten")
    p.add_argument("--gpu", help="GPU-Typ (z.B. RTX_4090)")
    p.add_argument("--image", help="Docker-Image")
    p.add_argument("-y", "--yes", action="store_true", help="Ohne Rueckfrage")

    # upload
    p = sub.add_parser("upload", help="Szene + Abhaengigkeiten hochladen")
    p.add_argument("scene", help="Pfad zur .duf-Datei")
    p.add_argument("--root-paths", nargs="+", help="DAZ-Root-Pfade")

    # presets
    sub.add_parser("presets", help="Verfuegbare Material-Presets auflisten")

    # render
    p = sub.add_parser("render", help="Render-Job starten")
    p.add_argument("scene_path", nargs="?", help="Szenenpfad auf dem Server")
    p.add_argument("--output", help="Ausgabedateiname")
    p.add_argument("--samples", type=int)
    p.add_argument("--resolution", help="z.B. 1920x1080")
    p.add_argument("--preset", help="Material-Preset (Name oder Dateipfad)")
    p.add_argument("--material-config", help="Material-Config JSON-Datei")
    p.add_argument("--no-wait", action="store_true", help="Nicht auf Ergebnis warten")

    # status
    p = sub.add_parser("status", help="Job-Status abfragen")
    p.add_argument("job_id", nargs="?")

    # download
    p = sub.add_parser("download", help="Ergebnis herunterladen")
    p.add_argument("filename", nargs="?")
    p.add_argument("-o", "--output-dir", help="Zielverzeichnis")

    # destroy
    p = sub.add_parser("destroy", help="Pod zerstoeren")
    p.add_argument("-y", "--yes", action="store_true")

    # go
    p = sub.add_parser("go", help="Kompletter Workflow")
    p.add_argument("scene", help="Pfad zur .duf-Datei")
    p.add_argument("--gpu", help="GPU-Typ")
    p.add_argument("--image", help="Docker-Image")
    p.add_argument("--root-paths", nargs="+", help="DAZ-Root-Pfade")
    p.add_argument("--output", help="Ausgabedateiname")
    p.add_argument("--output-dir", help="Zielverzeichnis")
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--resolution", default="1920x1080")
    p.add_argument("--preset", help="Material-Preset (Name oder Dateipfad)")
    p.add_argument("--material-config", help="Material-Config JSON-Datei")
    p.add_argument("-y", "--yes", action="store_true")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "analyze": cmd_analyze,
        "presets": cmd_presets,
        "start": cmd_start,
        "upload": cmd_upload,
        "render": cmd_render,
        "status": cmd_status,
        "download": cmd_download,
        "destroy": cmd_destroy,
        "go": cmd_go,
    }

    try:
        commands[args.command](args)
    except (RunpodError, RenderClientError) as e:
        log(f"FEHLER: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        log("Abgebrochen.")
        sys.exit(130)


if __name__ == "__main__":
    main()
