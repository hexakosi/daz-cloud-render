"""
HTTP-Client fuer den Render-Service auf der Vast.ai-Instanz.

Kommuniziert mit dem Flask-Service (Port 8080):
  - Dateien hochladen (inkrementell, Hash-basiert)
  - Render-Jobs starten und ueberwachen
  - Ergebnisse herunterladen

Lizenz: MIT
"""

import os
import sys
import time
import json
import hashlib
import urllib.request
import urllib.error
from pathlib import Path


class RenderClientError(Exception):
    pass


class RenderClient:
    def __init__(self, host, port=8080):
        self.base_url = f"http://{host}:{port}"
        self._upload_hashes = {}

    def _url(self, path):
        return f"{self.base_url}{path}"

    def _get_json(self, path, timeout=30):
        req = urllib.request.Request(self._url(path))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode() if e.fp else str(e)
            raise RenderClientError(f"HTTP {e.code}: {msg}")
        except urllib.error.URLError as e:
            raise RenderClientError(f"Verbindung fehlgeschlagen: {e.reason}")

    def _post_json(self, path, data, timeout=30):
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            self._url(path), data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode() if e.fp else str(e)
            raise RenderClientError(f"HTTP {e.code}: {msg}")

    # --- Health ---

    def health(self):
        return self._get_json("/health")

    def wait_for_service(self, timeout=120, interval=5):
        """Warten bis der Render-Service erreichbar ist."""
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                info = self.health()
                return info
            except RenderClientError as e:
                last_error = e
                time.sleep(interval)
        raise RenderClientError(
            f"Service nicht erreichbar nach {timeout}s: {last_error}"
        )

    # --- Upload ---

    def upload_file(self, local_path, remote_path):
        """Einzelne Datei hochladen."""
        local_path = str(local_path)
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"Datei nicht gefunden: {local_path}")

        # Multipart-Upload bauen
        boundary = "----DazCloudRender" + hashlib.md5(
            local_path.encode()
        ).hexdigest()[:8]

        with open(local_path, "rb") as f:
            file_data = f.read()

        body = bytearray()

        # path-Feld
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="path"\r\n\r\n'.encode())
        body.extend(f"{remote_path}\r\n".encode())

        # file-Feld
        filename = os.path.basename(local_path)
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\n'.encode()
        )
        body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        body.extend(file_data)
        body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            self._url("/upload"),
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode() if e.fp else str(e)
            raise RenderClientError(f"Upload fehlgeschlagen: {msg}")

    def upload_files(self, files_to_upload, skip_existing=True, progress_fn=None):
        """Mehrere Dateien inkrementell hochladen.

        Args:
            files_to_upload: Liste von (remote_path, local_path)
            skip_existing: Hash-basiert ueberspringen
            progress_fn: Callback(uploaded, total, current_file)
        """
        total = len(files_to_upload)
        uploaded = 0
        skipped = 0
        failed = []

        for i, (remote_path, local_path) in enumerate(files_to_upload):
            if progress_fn:
                progress_fn(i, total, remote_path)

            if skip_existing:
                file_hash = _file_hash(local_path)
                cached = self._upload_hashes.get(remote_path)
                if cached == file_hash:
                    skipped += 1
                    continue

            try:
                self.upload_file(local_path, remote_path)
                uploaded += 1
                if skip_existing:
                    self._upload_hashes[remote_path] = _file_hash(local_path)
            except Exception as e:
                failed.append((remote_path, str(e)))

        return {
            "total": total,
            "uploaded": uploaded,
            "skipped": skipped,
            "failed": failed,
        }

    # --- Render ---

    def start_render(self, scene_path, output=None, samples=128,
                     resolution="1920x1080", material_config=None):
        """Render-Job starten."""
        data = {
            "scene": scene_path,
            "samples": samples,
            "resolution": resolution,
        }
        if output:
            data["output"] = output
        if material_config:
            data["material_config"] = material_config

        return self._post_json("/render", data)

    def get_status(self, job_id=None):
        """Job-Status abfragen."""
        path = f"/status/{job_id}" if job_id else "/status"
        return self._get_json(path)

    def wait_for_render(self, job_id, timeout=3600, interval=10, progress_fn=None):
        """Warten bis Render fertig ist."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_status(job_id)
            state = status.get("status", "")

            if progress_fn:
                progress_fn(status)

            if state == "done":
                return status
            elif state == "error":
                raise RenderClientError(
                    f"Render fehlgeschlagen: {status.get('error', 'unbekannt')}"
                )

            time.sleep(interval)

        raise RenderClientError(f"Render-Timeout nach {timeout}s")

    # --- Results ---

    def list_results(self):
        return self._get_json("/results")

    def download_result(self, filename, local_dir="."):
        """Ergebnis herunterladen."""
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        dest = local_dir / filename

        req = urllib.request.Request(self._url(f"/results/{filename}"))
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                dest.write_bytes(resp.read())
            return str(dest)
        except urllib.error.HTTPError as e:
            raise RenderClientError(f"Download fehlgeschlagen: {e.code}")

    # --- Scenes ---

    def list_scenes(self):
        return self._get_json("/scenes")


def _file_hash(filepath):
    """Schneller Hash einer Datei (MD5, 64KB-Bloecke)."""
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()
