FROM python:3.12-slim

# ── Build-time metadata ───────────────────────────────────────────────────
LABEL org.opencontainers.image.title="wallpaper-engine"
LABEL org.opencontainers.image.description="Linux Wallpaper Service — Unsplash + Local Repository"

# ── System packages ───────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────────────────
RUN groupadd -r wallpaper && useradd -r -g wallpaper -d /app -s /sbin/nologin wallpaper

# ── Application code ──────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY docker-entrypoint.sh ./

# ── Data directory (override with -v ./data:/data) ────────────────────────
RUN mkdir -p /data/images && chown -R wallpaper:wallpaper /data \
    && chmod +x docker-entrypoint.sh

USER wallpaper

# ── Runtime ───────────────────────────────────────────────────────────────
ENV PORT=8000
EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
