# Pitchcraft: one image with the API, the built web UI and LibreOffice for rendering.
#   docker build -t pitchcraft .
#   docker run -p 127.0.0.1:8600:8600 -v pitchcraft-data:/data pitchcraft

ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=22

# ---- 1. web UI (Next.js static export) ----
FROM node:${NODE_VERSION}-bookworm-slim AS web
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime ----
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

LABEL org.opencontainers.image.title="Pitchcraft" \
      org.opencontainers.image.description="Open-source AI proposal generator: writes Word proposals in your company's exact template style with Claude." \
      org.opencontainers.image.licenses="MIT"

# LibreOffice renders previews and checks the document opens; Poppler reads PDFs;
# the font packages cover common Office fonts (Calibri/Cambria metric clones) and Arabic and other scripts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tini \
      libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
      poppler-utils \
      fonts-dejavu fonts-liberation fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea fonts-noto-core \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY pitchcraft ./pitchcraft
RUN pip install . && rm -rf /root/.cache

COPY --from=web /web/out /app/web

# Run as an unprivileged user. LibreOffice needs a writable HOME.
RUN useradd --uid 10001 --create-home --home-dir /home/pitchcraft --shell /usr/sbin/nologin pitchcraft \
 && mkdir -p /data \
 && chown pitchcraft:pitchcraft /data
USER pitchcraft

ENV HOME=/home/pitchcraft \
    PITCHCRAFT_WEB=/app/web \
    PITCHCRAFT_DATA=/data \
    PITCHCRAFT_FONT_CACHE=/data/.cache/fonts

VOLUME ["/data"]
EXPOSE 8600

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8600/api/health', timeout=4).status == 200 else 1)"]

# tini reaps LibreOffice child processes and forwards signals for a clean shutdown.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["pitchcraft", "serve", "--host", "0.0.0.0", "--port", "8600", "--data", "/data"]

# ---- 3. tests (optional): docker build --target test . ----
FROM runtime AS test
USER root
RUN pip install pytest httpx
COPY --chown=pitchcraft:pitchcraft pytest.ini ./
COPY --chown=pitchcraft:pitchcraft tests ./tests
USER pitchcraft
RUN python -m pytest -q -p no:cacheprovider && pitchcraft doctor --data /tmp/doctor-check
