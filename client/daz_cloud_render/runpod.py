"""
RunPod-API-Wrapper.

Steuert Pods: GPU-Typen abfragen, erstellen, Status pruefen, zerstoeren.
Nutzt die RunPod GraphQL-API direkt (keine externe Abhaengigkeit).

Lizenz: MIT
"""

import time
import json
import urllib.request
import urllib.error

API_URL = "https://api.runpod.io/graphql"


class RunpodError(Exception):
    pass


class RunpodClient:
    def __init__(self, api_key):
        if not api_key:
            raise RunpodError("Kein RunPod API-Key konfiguriert.\n"
                              "Setze RUNPOD_API_KEY oder trage ihn in "
                              "~/.daz-cloud-render.json ein.")
        self.api_key = api_key

    def _graphql(self, query, variables=None, timeout=30):
        url = f"{API_URL}?api_key={self.api_key}"
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode() if e.fp else str(e)
            raise RunpodError(f"API-Fehler {e.code}: {msg}")
        except urllib.error.URLError as e:
            raise RunpodError(f"Verbindungsfehler: {e.reason}")

        if "errors" in result and result["errors"]:
            msgs = "; ".join(e.get("message", str(e)) for e in result["errors"])
            raise RunpodError(f"GraphQL-Fehler: {msgs}")

        return result.get("data", {})

    def list_gpu_types(self):
        """Verfuegbare GPU-Typen mit Preisen abfragen."""
        query = """
        query {
            gpuTypes {
                id
                displayName
                memoryInGb
                securePrice
                communityPrice
                secureSpotPrice
            }
        }
        """
        data = self._graphql(query)
        return data.get("gpuTypes", [])

    def search_offers(self, gpu_name="NVIDIA GeForce RTX 4090",
                      cloud_type="SECURE"):
        """GPU-Angebote suchen und nach Preis sortieren."""
        gpu_types = self.list_gpu_types()
        matches = []
        for gpu in gpu_types:
            if gpu_name.lower() in gpu["id"].lower():
                price_key = "securePrice" if cloud_type == "SECURE" else "communityPrice"
                price = gpu.get(price_key)
                if price and price > 0:
                    matches.append({
                        "id": gpu["id"],
                        "display_name": gpu.get("displayName", gpu["id"]),
                        "vram_gb": gpu.get("memoryInGb", 0),
                        "price_per_hour": price,
                        "cloud_type": cloud_type,
                    })
        matches.sort(key=lambda x: x["price_per_hour"])
        return matches

    def create_pod(self, name, docker_image, gpu_type_id,
                   cloud_type="SECURE", disk_gb=20, env_vars=None,
                   ports="8080/http,22/tcp"):
        """Pod erstellen."""
        env_list = []
        if env_vars:
            for k, v in env_vars.items():
                env_list.append({"key": k, "value": v})

        query = """
        mutation($input: PodFindAndDeployOnDemandInput!) {
            podFindAndDeployOnDemand(input: $input) {
                id
                name
                desiredStatus
                imageName
                machine {
                    gpuDisplayName
                }
            }
        }
        """
        variables = {
            "input": {
                "name": name,
                "imageName": docker_image,
                "gpuTypeId": gpu_type_id,
                "cloudType": cloud_type,
                "volumeInGb": 0,
                "containerDiskInGb": disk_gb,
                "ports": ports,
                "startSsh": True,
                "env": env_list,
            }
        }

        data = self._graphql(query, variables, timeout=60)
        pod = data.get("podFindAndDeployOnDemand")
        if not pod:
            raise RunpodError("Pod-Erstellung fehlgeschlagen — keine Antwort")
        return pod

    def get_pod(self, pod_id):
        """Pod-Status abfragen."""
        query = """
        query($podId: String!) {
            pod(input: { podId: $podId }) {
                id
                name
                desiredStatus
                imageName
                runtime {
                    uptimeInSeconds
                    gpus {
                        id
                        gpuUtilPercent
                        memoryUtilPercent
                    }
                    ports {
                        ip
                        isIpPublic
                        privatePort
                        publicPort
                        type
                    }
                }
                machine {
                    gpuDisplayName
                }
            }
        }
        """
        data = self._graphql(query, {"podId": pod_id})
        pod = data.get("pod")
        if not pod:
            raise RunpodError(f"Pod {pod_id} nicht gefunden")
        return pod

    def list_pods(self):
        """Alle eigenen Pods auflisten."""
        query = """
        query {
            myself {
                pods {
                    id
                    name
                    desiredStatus
                    imageName
                    runtime {
                        uptimeInSeconds
                    }
                    machine {
                        gpuDisplayName
                    }
                }
            }
        }
        """
        data = self._graphql(query)
        return data.get("myself", {}).get("pods", [])

    def destroy_pod(self, pod_id):
        """Pod zerstoeren (terminieren)."""
        query = """
        mutation($input: PodTerminateInput!) {
            podTerminate(input: $input)
        }
        """
        self._graphql(query, {"input": {"podId": pod_id}})

    def wait_for_running(self, pod_id, timeout=300, interval=10):
        """Warten bis Pod laeuft. Gibt Verbindungsinfos zurueck."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pod = self.get_pod(pod_id)
            status = pod.get("desiredStatus", "")
            runtime = pod.get("runtime")

            if runtime and runtime.get("ports"):
                ports = runtime["ports"]
                ssh_port = None
                service_host = None
                service_port = None

                for p in ports:
                    if p.get("privatePort") == 22:
                        ssh_port = p.get("publicPort")
                    if p.get("privatePort") == 8080:
                        service_host = p.get("ip", "")
                        service_port = p.get("publicPort")

                gpu_name = ""
                machine = pod.get("machine")
                if machine:
                    gpu_name = machine.get("gpuDisplayName", "")

                return {
                    "status": "running",
                    "host": service_host or "",
                    "ssh_port": ssh_port,
                    "service_port": service_port,
                    "pod_id": pod_id,
                    "gpu": gpu_name,
                }

            if "TERMINATED" in status.upper() or "EXITED" in status.upper():
                raise RunpodError(f"Pod beendet: {status}")

            time.sleep(interval)

        raise RunpodError(f"Timeout nach {timeout}s — Pod startet nicht.")
