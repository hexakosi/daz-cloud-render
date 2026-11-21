"""
Vast.ai-API-Wrapper.

Steuert Instanzen: suchen, erstellen, Status pruefen, zerstoeren.
Nutzt die Vast.ai REST-API direkt (kein CLI noetig).

Lizenz: MIT
"""

import time
import json
import urllib.request
import urllib.error
import urllib.parse

API_BASE = "https://console.vast.ai/api/v0"


class VastaiError(Exception):
    pass


class VastaiClient:
    def __init__(self, api_key):
        if not api_key:
            raise VastaiError("Kein Vast.ai API-Key konfiguriert.\n"
                              "Setze VAST_API_KEY oder trage ihn in "
                              "~/.daz-cloud-render.json ein.")
        self.api_key = api_key

    def _request(self, method, path, data=None, timeout=30):
        url = f"{API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode() if e.fp else str(e)
            raise VastaiError(f"API-Fehler {e.code}: {msg}")
        except urllib.error.URLError as e:
            raise VastaiError(f"Verbindungsfehler: {e.reason}")

    def search_offers(self, gpu_name="RTX_4090", num_gpus=1,
                      min_download=100, order="dph_total"):
        """Verfuegbare GPU-Angebote suchen."""
        query = {
            "gpu_name": {"eq": gpu_name},
            "num_gpus": {"eq": num_gpus},
            "inet_down": {"gte": min_download},
            "rentable": {"eq": True},
        }
        params = urllib.parse.urlencode({
            "q": json.dumps(query),
            "order": order,
            "type": "on-demand",
        })

        result = self._request("GET", f"/bundles?{params}")
        offers = result.get("offers", [])
        return offers

    def create_instance(self, offer_id, docker_image, disk_gb=20,
                        env_vars=None):
        """Instanz erstellen."""
        config = {
            "client_id": "me",
            "image": docker_image,
            "disk": disk_gb,
            "runtype": "ssh_direc",
        }

        if env_vars:
            env_str = " ".join(f"-e {k}={v}" for k, v in env_vars.items())
            config["env"] = env_str

        result = self._request("PUT", f"/asks/{offer_id}/", data=config)

        if "new_contract" in result:
            return result["new_contract"]
        elif "success" in result and result["success"]:
            return result
        else:
            raise VastaiError(f"Instanz-Erstellung fehlgeschlagen: {result}")

    def get_instance(self, instance_id):
        """Instanz-Status abfragen."""
        result = self._request("GET", f"/instances/{instance_id}/")
        return result

    def list_instances(self):
        """Alle eigenen Instanzen auflisten."""
        result = self._request("GET", "/instances/")
        return result.get("instances", [])

    def destroy_instance(self, instance_id):
        """Instanz zerstoeren."""
        self._request("PUT", f"/instances/{instance_id}/",
                      data={"state": "destroy"})

    def wait_for_running(self, instance_id, timeout=300, interval=10):
        """Warten bis Instanz laeuft. Gibt SSH-Info zurueck."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            info = self.get_instance(instance_id)
            status = info.get("actual_status", info.get("status_msg", ""))

            if status == "running":
                ssh_host = info.get("ssh_host", "")
                ssh_port = info.get("ssh_port", "")
                public_ip = info.get("public_ipaddr", ssh_host)
                ports = info.get("ports", {})

                return {
                    "status": "running",
                    "ssh_host": public_ip,
                    "ssh_port": ssh_port,
                    "service_port": _find_mapped_port(ports, 8080),
                    "instance_id": instance_id,
                    "gpu": info.get("gpu_name", ""),
                }

            if "error" in status.lower() or "failed" in status.lower():
                raise VastaiError(f"Instanz fehlgeschlagen: {status}")

            time.sleep(interval)

        raise VastaiError(f"Timeout nach {timeout}s — Instanz startet nicht.")


def _find_mapped_port(ports, internal_port):
    """Gemappten externen Port finden."""
    key = f"{internal_port}/tcp"
    if key in ports:
        mapping = ports[key]
        if isinstance(mapping, list) and mapping:
            return mapping[0].get("HostPort", internal_port)
        elif isinstance(mapping, dict):
            return mapping.get("HostPort", internal_port)
    return internal_port
