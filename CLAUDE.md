# CLAUDE.md

Build a Linux Wallpaper Service (Unsplash + Local Repository).

## Goal

Design and implement a production-ready application (Python **or** Bash + supporting tools) that:

1. Fetches a random wallpaper image from the Unsplash API.
2. Maintains a local repository of downloaded and user-added images.
3. Exposes an HTTP API to retrieve a random image (from Unsplash cache, local repo, or user-defined source).
4. Follows best practices for reliability, security, and maintainability.
5. Is containerizable and runnable as a systemd service on Fedora Linux (Fedora 43 target).

---

## Recommended Stack (Prefer Python)

* **Language:** Python 3.12+
* **HTTP API:** FastAPI (preferred) or Flask
* **HTTP client:** httpx
* **Image handling (optional):** Pillow
* **Database (optional but recommended):** SQLite via SQLAlchemy
* **Task scheduling:** APScheduler or cron (fallback)
* **Logging:** Python `logging` module (JSON format preferred)
* **Config:** Environment variables + `.env` support
* **Containerization:** Docker (or Podman for Fedora)
* **Service manager:** systemd unit file

---

## Functional Requirements

### 1. Unsplash Integration

* Use the official Unsplash API:

  * Endpoint: `https://api.unsplash.com/photos/random`
  * Require API key via env var: `UNSPLASH_ACCESS_KEY`
* Support query parameters:

  * `orientation=landscape`
  * `content_filter=high`
  * Optional `query` (e.g., "nature", "minimal")
* Download the image (highest reasonable resolution, configurable max size).
* Store metadata:

  * `id`, `author`, `url`, `downloaded_at`, `tags`

---

### 2. Local Repository

* Directory structure:

  ```
  /data/
    images/
    metadata.db
  ```
* Support:

  * Automatically downloaded images
  * Manually added images (user drops files into `/data/images`)
* Index all images on startup (scan directory).
* Avoid duplicates using hashing (SHA256 minimum).

---

### 3. Image Selection Logic

Implement selection modes:

* `unsplash_latest` → most recently downloaded
* `local_random` → random from local repo
* `unsplash_random` → fetch new image live
* `hybrid` (default) → random from full pool

---

### 4. HTTP API

#### `GET /image`

Query params:

* `source`: `local | unsplash | hybrid`
* `refresh`: `true|false`

Response:

* Image file (streamed) OR JSON metadata (if `Accept: application/json`)

#### `POST /refresh`

* Fetch a new image from Unsplash and store it

#### `GET /health`

* Health check endpoint

#### `GET /stats`

* Return:

  * total images
  * unsplash vs local counts
  * disk usage

---

### 5. Wallpaper Setter (Optional)

Provide CLI:

```
wallpaperctl set --random
```

Desktop support:

* GNOME: `gsettings`
* KDE: `qdbus`

---

## Non-Functional Requirements

### Security

* No hardcoded API keys
* Validate inputs
* Restrict file types (jpg, png)
* Prevent path traversal

### Performance

* Cache Unsplash responses
* Use async I/O
* Avoid duplicate downloads

### Reliability

* Retry with backoff
* Graceful startup/shutdown
* Auto-create required directories

### Logging

* Structured logs (JSON preferred)
* Include request + error logs

---

## Containerization

### Requirements

* Use slim Python base image
* Run as non-root user
* Mount `/data` as volume
* Expose port (e.g., 8000)

Example:

```
docker build -t wallpaper-service .
docker run -d -p 8000:8000 -v ./data:/data wallpaper-service
```

Prefer Podman compatibility.

---

## systemd Unit

Path:

```
/etc/systemd/system/wallpaper-service.service
```

Requirements:

* Restart: always
* Use EnvironmentFile
* Run as non-root
* After=network.target

---

## Configuration

Environment variables:

* `UNSPLASH_ACCESS_KEY`
* `IMAGE_DIR=/data/images`
* `DB_PATH=/data/metadata.db`
* `DEFAULT_SOURCE=hybrid`
* `PORT=8000`

---

## Testing

* Use pytest
* Mock Unsplash API
* Test API endpoints
* Validate downloads and deduplication

---

## Suggested Enhancements

* Perceptual hashing (pHash) deduplication
* Tag filtering (nature, dark, etc.)
* Auto-refresh scheduler
* Resolution-aware filtering
* NSFW filtering
* Web UI dashboard
* ETag caching
* Rate limit handling

---

## Alternative Approach (Bash)

Tools:

* curl
* jq
* feh / gsettings

Limitations:

* Harder to scale
* Limited API capability

---

## Deliverables

* Source code
* Dockerfile
* systemd service file
* README.md with setup and usage

---

## Output Expectations

* Full Python project
* Clean, modular code
* Production-ready setup
* Clear documentation
