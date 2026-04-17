# wallpaper-engine

A production-ready Linux wallpaper service that fetches images from the [Unsplash API](https://unsplash.com/developers) and maintains a local repository of wallpapers.  It exposes an HTTP API so that any tool — a cron job, a desktop hook, or the included `wallpaperctl` CLI — can request and set a wallpaper.

---

## Features

- Fetch random landscape wallpapers from Unsplash (with retry/backoff)
- Maintain a local repository — drop images into `/data/images` and they are auto-indexed on start-up
- SHA-256 deduplication (no duplicate downloads or files)
- Four selection modes: `local`, `unsplash`, `hybrid` (default), and forced refresh
- Streams images directly or returns JSON metadata (`Accept: application/json`)
- Structured JSON logging
- `wallpaperctl` CLI — sets the wallpaper on GNOME or KDE in one command
- Docker/Podman container with a non-root user
- systemd unit file for Fedora (and any systemd Linux distro)

---

## Quick start

### 1. Get an Unsplash API key

Register at <https://unsplash.com/developers> and create an application to obtain a **Access Key**.

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set UNSPLASH_ACCESS_KEY=<your key>
```

### 3a. Run with Docker / Podman

```bash
# Build
docker build -t wallpaper-service .
# or: podman build -t wallpaper-service .

# Run
docker run -d \
  --name wallpaper-service \
  -p 8000:8000 \
  -v ./data:/data \
  --env-file .env \
  wallpaper-service
```

### 3b. Run directly (Python venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

---

## HTTP API

| Method | Path       | Description                                      |
|--------|------------|--------------------------------------------------|
| GET    | `/image`   | Return a wallpaper (file or JSON metadata)       |
| POST   | `/refresh` | Fetch a new image from Unsplash and cache it     |
| GET    | `/health`  | Health check                                     |
| GET    | `/stats`   | Repository statistics                            |

### GET /image — query parameters

| Param     | Values                        | Default            |
|-----------|-------------------------------|-------------------|
| `source`  | `local \| unsplash \| hybrid` | `DEFAULT_SOURCE`  |
| `refresh` | `true \| false`               | `false`           |

```bash
# Stream the image
curl http://localhost:8000/image?source=local -o wall.jpg

# Get JSON metadata
curl -H "Accept: application/json" http://localhost:8000/image?source=hybrid

# Force a fresh Unsplash download
curl -H "Accept: application/json" "http://localhost:8000/image?source=unsplash&refresh=true"
```

### POST /refresh

```bash
curl -s -X POST http://localhost:8000/refresh | python -m json.tool
```

### GET /stats

```bash
curl http://localhost:8000/stats
# {
#   "total_images": 12,
#   "unsplash_images": 10,
#   "local_images": 2,
#   "disk_usage_bytes": 15728640,
#   "disk_usage_mb": 15.0
# }
```

---

## wallpaperctl CLI

```bash
# Make executable (already set if cloned from git)
chmod +x wallpaperctl

# Set a random wallpaper (auto-detects GNOME / KDE)
./wallpaperctl set --random

# Force a fresh Unsplash image
./wallpaperctl set --refresh

# Use only local images
./wallpaperctl set --source local

# Pre-fetch a new wallpaper without setting it
./wallpaperctl refresh

# Show repository stats
./wallpaperctl stats

# Health check
./wallpaperctl health
```

Override the service URL:

```bash
WALLPAPER_ENGINE_URL=http://192.168.1.10:8000 ./wallpaperctl set --random
```

### Auto-set on login (GNOME example)

Add to `~/.config/autostart/wallpaper.desktop`:

```ini
[Desktop Entry]
Type=Application
Exec=/path/to/wallpaperctl set --random
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Wallpaper Engine
```

### Cron — refresh every hour

```cron
0 * * * * /path/to/wallpaperctl set --refresh
```

---

## systemd service (Fedora)

```bash
# Create a dedicated user
sudo useradd -r -s /sbin/nologin -d /opt/wallpaper-engine wallpaper

# Copy environment file
sudo cp .env.example /etc/wallpaper-engine.env
sudo nano /etc/wallpaper-engine.env   # set UNSPLASH_ACCESS_KEY

# Install code
sudo mkdir -p /opt/wallpaper-engine
sudo cp -r app requirements.txt /opt/wallpaper-engine/
cd /opt/wallpaper-engine
sudo python -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo chown -R wallpaper:wallpaper /opt/wallpaper-engine

# Create data directory
sudo mkdir -p /data/images
sudo chown -R wallpaper:wallpaper /data

# Install and start the service
sudo cp wallpaper-service.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wallpaper-service

# Check status
sudo systemctl status wallpaper-service
sudo journalctl -u wallpaper-service -f
```

---

## Configuration

All settings are read from environment variables (or `.env`):

| Variable              | Default            | Description                          |
|-----------------------|--------------------|--------------------------------------|
| `UNSPLASH_ACCESS_KEY` | *(required)*       | Unsplash API access key              |
| `IMAGE_DIR`           | `/data/images`     | Directory for stored images          |
| `DB_PATH`             | `/data/metadata.db`| SQLite database path                 |
| `DEFAULT_SOURCE`      | `hybrid`           | Default selection mode               |
| `PORT`                | `8000`             | Listening port                       |
| `MAX_IMAGE_SIZE_MB`   | `10`               | Maximum download size in MB          |
| `UNSPLASH_QUERY`      | *(empty)*          | Default topic filter (e.g. `nature`) |
| `LOG_LEVEL`           | `INFO`             | `DEBUG`, `INFO`, `WARNING`, `ERROR`  |

---

## Local image repository

Drop any `.jpg`, `.jpeg`, or `.png` files into `IMAGE_DIR` and restart the service (or it will pick them up at next start-up via the auto-scan).  Files are deduplicated by SHA-256 hash — identical files with different names are counted only once.

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run tests
pytest -v

# Run locally
uvicorn app.main:create_app --factory --reload
```

---

## Project layout

```
wallpaper-engine/
├── app/
│   ├── config.py          # Pydantic-settings (env vars)
│   ├── database.py        # Async SQLAlchemy engine/session
│   ├── logging_config.py  # JSON log formatter
│   ├── main.py            # FastAPI factory + lifespan
│   ├── models.py          # SQLAlchemy ORM model (Image)
│   ├── repository.py      # Local repo scanner & dedup
│   ├── routes.py          # HTTP route handlers
│   ├── selector.py        # Selection strategy logic
│   └── unsplash.py        # Unsplash API client + downloader
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_repository.py
│   └── test_unsplash.py
├── wallpaperctl              # CLI tool (no extra deps)
├── Dockerfile
├── wallpaper-service.service
├── .env.example
├── requirements.txt
└── requirements-dev.txt
```
