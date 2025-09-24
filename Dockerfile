# syntax=docker/dockerfile:1

###############################
# Frontend build stage
###############################
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Install dependencies first (better caching)
COPY frontend/package.json frontend/package-lock.json* ./frontend/
RUN npm --prefix ./frontend ci --no-audit --silent

# Copy source and run the Vite build
COPY frontend ./frontend
# Ensure the backend/app path exists so Vite can emit to ../backend/app/static
RUN mkdir -p ./backend/app
RUN npm --prefix ./frontend run build


###############################
# Python deps build stage
###############################
FROM python:3.11-slim AS backend-builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps needed to build some pip packages in the future
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtualenv at /opt/venv
COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r backend/requirements.txt


###############################
# Runtime image
###############################
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="music_downloader" \
      org.opencontainers.image.description="Music Downloader API + SPA" \
      org.opencontainers.image.source="https://example.local/your-repo" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Default library location inside container (override with a bind mount in compose)
    LIBRARY_DIR=/app/library

WORKDIR /app

# Only the runtime binaries (ffmpeg) are needed; yt-dlp is provided by pip in the venv
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python environment
COPY --from=backend-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Copy application code
COPY backend ./backend
COPY run_api.py ./run_api.py

# Copy built frontend assets from the frontend stage
COPY --from=frontend-builder /app/backend/app/static ./backend/app/static

# Create default library directory (bind mount over this in production)
RUN mkdir -p /app/library

EXPOSE 8000

# Start uvicorn in production mode (no reload)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
