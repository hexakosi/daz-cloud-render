# DAZ Cloud Render — Docker-Image fuer Vast.ai GPU-Rendering
#
# Blender + Diffeomorphic DAZ Importer auf CUDA-Basis.
# Kommerzielle DAZ-Inhalte werden zur Laufzeit hochgeladen, nie ins Image gebaut.
# Keine Secrets im Image — API-Keys kommen als Umgebungsvariablen.
#
# Build:
#   docker build -t daz-cloud-render:latest docker/
#
# Manueller Test (CPU):
#   docker run --rm -it daz-cloud-render:latest blender -b --version
#
# Vast.ai (GPU):
#   Template mit diesem Image erstellen, SSH-Modus, Port 22 + 8080

ARG BASE_IMAGE=vastai/base-image:cuda-12.8.1-cudnn-devel-ubuntu22.04
FROM ${BASE_IMAGE}

LABEL maintainer="daz-cloud-render"
LABEL description="Blender + Diffeomorphic DAZ Importer fuer GPU Cloud Rendering"

# --- Versionen (als Build-Args, leicht aktualisierbar) ---
ARG BLENDER_VERSION=5.2.0
ARG BLENDER_MAJOR=5.2
ARG DIFFEOMORPHIC_BRANCH=master

# --- Systempakete ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xz-utils \
    libxi6 \
    libxxf86vm1 \
    libxfixes3 \
    libxrender1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    xvfb \
    rsync \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# --- Python-Abhaengigkeiten (Render-Service + Watchdog) ---
RUN pip3 install --no-cache-dir flask vastai

# --- Blender installieren ---
RUN BLENDER_URL="https://download.blender.org/release/Blender${BLENDER_MAJOR}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
    && echo "Lade Blender von: ${BLENDER_URL}" \
    && wget -q --show-progress -O /tmp/blender.tar.xz "${BLENDER_URL}" \
    && mkdir -p /opt/blender \
    && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
    && rm /tmp/blender.tar.xz \
    && ln -s /opt/blender/blender /usr/local/bin/blender \
    && blender -b --version

# --- Diffeomorphic DAZ Importer installieren ---
# Blender-Addon-Pfad ermitteln und Addon dorthin kopieren
RUN BLENDER_ADDONS="/opt/blender/${BLENDER_MAJOR}/scripts/addons" \
    && echo "Addon-Pfad: ${BLENDER_ADDONS}" \
    && wget -q -O /tmp/import_daz.zip "https://github.com/Diffeomorphic/import_daz/archive/refs/heads/${DIFFEOMORPHIC_BRANCH}.zip" \
    && mkdir -p /tmp/daz_extract \
    && unzip -q /tmp/import_daz.zip -d /tmp/daz_extract \
    && mv /tmp/daz_extract/import_daz-${DIFFEOMORPHIC_BRANCH} "${BLENDER_ADDONS}/import_daz" \
    && rm -rf /tmp/import_daz.zip /tmp/daz_extract \
    && echo "Diffeomorphic installiert in ${BLENDER_ADDONS}/import_daz"

# Fuer Blender >= 4.2: Extension-Pfad als Fallback
# (import_daz im addons-Ordner wird auch als Legacy-Addon erkannt)

# --- Render-Skripte kopieren ---
COPY scripts/ /opt/daz-cloud-render/
RUN chmod +x /opt/daz-cloud-render/*.py /opt/daz-cloud-render/*.sh 2>/dev/null || true

# --- Arbeitsverzeichnisse ---
RUN mkdir -p /workspace/scenes /workspace/results /workspace/cache

# --- Supervisor-Konfiguration ---
COPY supervisor/render-service.conf /etc/supervisor/conf.d/

# --- Standard-DAZ-Importer-Settings (Root-Pfade werden zur Laufzeit gesetzt) ---
RUN mkdir -p /root/Documents/DAZ\ Importer

# --- Ports ---
# 8080: Render-Service (Phase 2)
# 22: SSH (von Vast.ai-Base-Image bereitgestellt)
EXPOSE 8080

# --- Healthcheck ---
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD blender -b --version > /dev/null 2>&1 || exit 1

# --- Umgebungsvariablen (Defaults, zur Laufzeit ueberschreibbar) ---
ENV DAZ_ROOT_PATHS="/workspace/scenes"
ENV RENDER_OUTPUT="/workspace/results"
ENV MAX_SESSION_HOURS="4"
ENV IDLE_TIMEOUT_MINUTES="30"
# VAST_API_KEY wird zur Laufzeit gesetzt, NIE ins Image!

# --- Entrypoint ---
COPY scripts/entrypoint.sh /opt/daz-cloud-render/entrypoint.sh
RUN chmod +x /opt/daz-cloud-render/entrypoint.sh

ENTRYPOINT ["/opt/daz-cloud-render/entrypoint.sh"]
CMD []
