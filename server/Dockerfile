# Fair Play server image — one image, every service runs a different command (docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# dependencies first (cached layer), then the code
COPY server/requirements.txt server/requirements.txt
COPY core/pyproject.toml core/pyproject.toml
COPY core/fairplay_core core/fairplay_core
RUN pip install -e core -r server/requirements.txt

COPY server server
