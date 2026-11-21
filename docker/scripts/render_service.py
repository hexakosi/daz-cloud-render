"""
HTTP-Render-Service fuer DAZ Cloud Render.

Laeuft auf Port 8080 und bietet:
  POST /upload          — Dateien hochladen (Szenen, Texturen)
  POST /render          — Render-Job starten
  GET  /status          — Job-Status abfragen
  GET  /results/<name>  — Ergebnis herunterladen
  GET  /health          — Health-Check

Lizenz: GPL-2.0-or-later
"""

import os
import sys
import json
import time
import uuid
import shutil
import subprocess
import threading
from pathlib import Path

from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

SCENE_DIR = Path(os.environ.get("DAZ_ROOT_PATHS", "/workspace/scenes"))
RESULT_DIR = Path(os.environ.get("RENDER_OUTPUT", "/workspace/results"))
HEARTBEAT_FILE = Path("/tmp/daz_heartbeat")

render_jobs = {}
render_lock = threading.Lock()


def touch_heartbeat():
    HEARTBEAT_FILE.write_text(str(time.time()))


def log(msg):
    print(f"[SERVICE] {msg}", flush=True)


# --- Upload ---

@app.route("/upload", methods=["POST"])
def upload():
    """Dateien in die Szenen-Verzeichnisstruktur hochladen.

    Multipart-Upload mit 'file' (Datei) und 'path' (relativer Zielpfad).
    Mehrere Dateien: mehrere 'file'/'path' Paare.
    """
    touch_heartbeat()

    if "file" not in request.files:
        return jsonify({"error": "Kein 'file' im Request"}), 400

    files = request.files.getlist("file")
    paths = request.form.getlist("path")

    if not paths:
        paths = [f.filename for f in files]

    if len(files) != len(paths):
        return jsonify({"error": "Anzahl files != Anzahl paths"}), 400

    uploaded = []
    for f, rel_path in zip(files, paths):
        rel_path = rel_path.lstrip("/").lstrip("\\")
        if ".." in rel_path:
            return jsonify({"error": f"Ungültiger Pfad: {rel_path}"}), 400

        dest = SCENE_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.save(str(dest))
        uploaded.append(rel_path)
        log(f"Upload: {rel_path} ({dest.stat().st_size} bytes)")

    return jsonify({"uploaded": uploaded, "count": len(uploaded)})


# --- Render ---

@app.route("/render", methods=["POST"])
def render():
    """Render-Job starten.

    JSON-Body:
    {
        "scene": "People/szene.duf",       (relativ zu SCENE_DIR)
        "output": "render.png",             (Dateiname fuer Ergebnis)
        "samples": 64,
        "resolution": "1920x1080",
        "material_config": {...}            (optional)
    }
    """
    touch_heartbeat()

    data = request.get_json(silent=True)
    if not data or "scene" not in data:
        return jsonify({"error": "JSON mit 'scene' erforderlich"}), 400

    scene_rel = data["scene"].lstrip("/").lstrip("\\")
    if ".." in scene_rel:
        return jsonify({"error": "Ungültiger Szenenpfad"}), 400

    scene_path = SCENE_DIR / scene_rel
    if not scene_path.is_file():
        return jsonify({"error": f"Szene nicht gefunden: {scene_rel}"}), 404

    job_id = uuid.uuid4().hex[:12]
    output_name = data.get("output", f"{job_id}.png")
    output_path = RESULT_DIR / output_name
    samples = data.get("samples", 64)
    resolution = data.get("resolution", "1920x1080")

    # Material-Config als temporaere Datei
    mat_config_path = None
    if "material_config" in data:
        mat_config_path = f"/tmp/mat_config_{job_id}.json"
        with open(mat_config_path, "w") as f:
            json.dump(data["material_config"], f)

    with render_lock:
        render_jobs[job_id] = {
            "status": "queued",
            "scene": scene_rel,
            "output": output_name,
            "samples": samples,
            "resolution": resolution,
            "started": None,
            "finished": None,
            "error": None,
        }

    thread = threading.Thread(
        target=_run_render,
        args=(job_id, str(scene_path), str(output_path),
              samples, resolution, mat_config_path),
        daemon=True,
    )
    thread.start()

    log(f"Job {job_id} gestartet: {scene_rel}")
    return jsonify({"job_id": job_id, "status": "queued"})


def _run_render(job_id, scene_path, output_path, samples, resolution, mat_config_path):
    with render_lock:
        render_jobs[job_id]["status"] = "rendering"
        render_jobs[job_id]["started"] = time.time()

    cmd = [
        "blender", "-b",
        "--python", "/opt/daz-cloud-render/setup_and_render.py",
        "--",
        "--scene", scene_path,
        "--output", output_path,
        "--samples", str(samples),
        "--resolution", resolution,
        "--root-paths", str(SCENE_DIR),
    ]

    if mat_config_path:
        cmd.extend(["--material-config", mat_config_path])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )

        touch_heartbeat()

        with render_lock:
            if result.returncode == 0 and os.path.isfile(output_path):
                render_jobs[job_id]["status"] = "done"
                render_jobs[job_id]["size_mb"] = round(
                    os.path.getsize(output_path) / (1024 * 1024), 2
                )
            else:
                render_jobs[job_id]["status"] = "error"
                stderr_tail = result.stderr[-2000:] if result.stderr else ""
                render_jobs[job_id]["error"] = stderr_tail or "Render fehlgeschlagen"

            render_jobs[job_id]["finished"] = time.time()

        log(f"Job {job_id}: {render_jobs[job_id]['status']}")

    except subprocess.TimeoutExpired:
        with render_lock:
            render_jobs[job_id]["status"] = "error"
            render_jobs[job_id]["error"] = "Timeout (1h)"
            render_jobs[job_id]["finished"] = time.time()
        log(f"Job {job_id}: Timeout")

    except Exception as e:
        with render_lock:
            render_jobs[job_id]["status"] = "error"
            render_jobs[job_id]["error"] = str(e)
            render_jobs[job_id]["finished"] = time.time()
        log(f"Job {job_id}: Exception {e}")

    finally:
        if mat_config_path and os.path.isfile(mat_config_path):
            os.remove(mat_config_path)


# --- Status ---

@app.route("/status", methods=["GET"])
@app.route("/status/<job_id>", methods=["GET"])
def status(job_id=None):
    touch_heartbeat()

    if job_id:
        job = render_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job nicht gefunden"}), 404
        resp = {"job_id": job_id, **job}
        if job["started"] and job["finished"]:
            resp["duration_s"] = round(job["finished"] - job["started"], 1)
        elif job["started"]:
            resp["elapsed_s"] = round(time.time() - job["started"], 1)
        return jsonify(resp)

    return jsonify({
        "jobs": {jid: j["status"] for jid, j in render_jobs.items()},
        "scene_dir": str(SCENE_DIR),
        "result_dir": str(RESULT_DIR),
    })


# --- Results ---

@app.route("/results/<filename>", methods=["GET"])
def results(filename):
    touch_heartbeat()

    if ".." in filename:
        return jsonify({"error": "Ungültiger Dateiname"}), 400

    path = RESULT_DIR / filename
    if not path.is_file():
        return jsonify({"error": "Datei nicht gefunden"}), 404

    return send_file(str(path), as_attachment=True)


@app.route("/results", methods=["GET"])
def list_results():
    touch_heartbeat()

    files = []
    for f in RESULT_DIR.iterdir():
        if f.is_file():
            files.append({
                "name": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            })

    return jsonify({"files": files})


# --- Health ---

@app.route("/health", methods=["GET"])
def health():
    touch_heartbeat()

    info = {
        "status": "ok",
        "uptime_s": round(time.time() - app.config.get("start_time", time.time()), 1),
        "active_jobs": sum(1 for j in render_jobs.values() if j["status"] == "rendering"),
        "total_jobs": len(render_jobs),
        "scene_dir": str(SCENE_DIR),
    }

    # GPU-Info
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            info["gpu"] = result.stdout.strip()
    except Exception:
        info["gpu"] = "nicht verfuegbar"

    return jsonify(info)


# --- Scenes (Dateiliste) ---

@app.route("/scenes", methods=["GET"])
def list_scenes():
    touch_heartbeat()

    scenes = []
    for f in SCENE_DIR.rglob("*.duf"):
        scenes.append({
            "path": str(f.relative_to(SCENE_DIR)),
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
        })

    return jsonify({"scenes": scenes, "root": str(SCENE_DIR)})


# --- Main ---

if __name__ == "__main__":
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    app.config["start_time"] = time.time()
    touch_heartbeat()

    port = int(os.environ.get("SERVICE_PORT", 8080))
    log(f"Starte auf Port {port}")
    log(f"Szenen:    {SCENE_DIR}")
    log(f"Ergebnis:  {RESULT_DIR}")

    app.run(host="0.0.0.0", port=port, threaded=True)
