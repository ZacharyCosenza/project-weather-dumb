# Productionization Guide

This guide walks through containerizing the NYC Weather Nowcaster with Docker so it runs
persistently on your machine, survives reboots, and refreshes automatically every hour.

---

## What We're Building

```
┌─────────────────────────────────────────────────────┐
│  Your Machine (WSL2)                                │
│                                                     │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │  pipeline        │    │  web             │       │
│  │  container       │    │  container       │       │
│  │                  │    │                  │       │
│  │  Kedro pipelines │    │  Streamlit       │       │
│  │  (run by cron)   │    │  localhost:8501  │       │
│  └────────┬─────────┘    └────────┬─────────┘       │
│           │                       │                 │
│           └──────────┬────────────┘                 │
│                      │ shared                       │
│               ┌──────┴──────┐                       │
│               │  ./data/    │  ← lives on your      │
│               │  ./logs/    │    hard drive         │
│               └─────────────┘                       │
└─────────────────────────────────────────────────────┘
```

Two containers run from the same Docker image:
- **pipeline** — stays alive in the background; cron calls into it hourly to run predictions
- **web** — runs Streamlit continuously; reads `predictions.json` written by the pipeline

Both share your `./data/` folder directly (a "bind mount"), so models and predictions
persist forever regardless of container restarts or image rebuilds. Docker automatically
restarts both containers if they crash or your machine reboots.

The pipeline is split into two jobs:
- **Nightly at 02:00** — fetch fresh data + retrain models + run inference (slow, ~5 min)
- **Hourly at :05** — fetch fresh data + run inference only (fast, ~30 sec)

---

## Prerequisites

- Docker Desktop installed and running (Settings → Resources → WSL Integration → enabled)
- Verify in WSL2 terminal:
  ```bash
  docker --version        # should print Docker version 28+
  docker compose version  # should print Compose version 2+
  ```

---

## Step 1 — Create `.dockerignore`

This tells Docker which files to skip when building the image. Without it, Docker would
try to copy gigabytes of data files into every build, making each one very slow.

Create the file:
```bash
nano .dockerignore
```

Paste this content:
```
data/
logs/
.venv/
__pycache__/
*.pyc
.git/
notebooks/
keys.md
```

Save: `Ctrl+O` → `Enter` → `Ctrl+X`

Verify:
```bash
cat .dockerignore
```

---

## Step 2 — Create the `Dockerfile`

The Dockerfile is a recipe that tells Docker how to build the image — the self-contained
snapshot of Python, all dependencies, and your code.

Create the file:
```bash
nano Dockerfile
```

Paste this content:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system libraries needed to compile Python packages (xgboost, pyarrow)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (separate layer — Docker caches this unless pyproject.toml changes)
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Copy application code and config
# data/ and logs/ are NOT copied — they come from bind mounts at runtime
COPY conf/ conf/
COPY app/ app/
COPY run_pipeline.sh run_inference_only.sh ./
RUN chmod +x run_pipeline.sh run_inference_only.sh

# Create directory stubs so Kedro doesn't error if bind mount hasn't been attached yet
RUN mkdir -p data/00_cache data/01_raw data/02_intermediate data/03_primary logs
```

Save: `Ctrl+O` → `Enter` → `Ctrl+X`

**What each section does:**
- `FROM python:3.12-slim` — start from a minimal official Python image (~200MB vs ~1GB for full)
- `WORKDIR /app` — all subsequent commands run from `/app` inside the container
- `apt-get install` — installs C compiler needed to build xgboost and pyarrow from source
- `COPY pyproject.toml + src/` then `pip install` — installs all your Python packages.
  This is done before copying the rest of your code so Docker can cache this slow layer.
  If only `app/` changes, Docker reuses the cached pip install layer.
- `COPY conf/ app/` — copies your Kedro config and Streamlit app into the image
- `chmod +x` — makes the shell scripts executable inside the container
- `mkdir -p data/...` — creates empty placeholder directories so Kedro doesn't crash on
  startup before the bind mount attaches

---

## Step 3 — Create the pipeline scripts

These replace `run_hourly.sh` for use inside the container. The key difference is there is
no `.venv` to activate — Docker's Python IS the environment.

**`run_pipeline.sh`** (nightly full retrain):
```bash
nano run_pipeline.sh
```
```bash
#!/bin/bash
set -euo pipefail
cd /app
TODAY=$(date +%Y-%m-%d)
echo "[$(date)] Nightly pipeline: fetch + retrain + inference for $TODAY"
kedro run --pipeline data_engineering --params "end_date=$TODAY"
kedro run --pipeline data_science
kedro run --pipeline inference
echo "[$(date)] Nightly pipeline done"
```

**`run_inference_only.sh`** (hourly fast inference):
```bash
nano run_inference_only.sh
```
```bash
#!/bin/bash
set -euo pipefail
cd /app
TODAY=$(date +%Y-%m-%d)
echo "[$(date)] Hourly inference for $TODAY"
kedro run --pipeline data_engineering --params "end_date=$TODAY"
kedro run --pipeline inference
echo "[$(date)] Hourly inference done"
```

**Why two scripts?**
The `data_science` pipeline retrains XGBoost on 3 years of hourly data every time it runs.
That takes ~5 minutes and the training set barely changes hour to hour. Running it once a
night keeps models fresh without burning CPU every hour. The fast hourly script just fetches
today's latest data and produces a new prediction using the existing models.

---

## Step 4 — Create `docker-compose.yml`

Docker Compose lets you define and run multiple containers together with one command.

```bash
nano docker-compose.yml
```

```yaml
services:

  pipeline:
    build: .
    image: weather
    container_name: weather-pipeline
    restart: unless-stopped
    command: tail -f /dev/null
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - PYTHONUNBUFFERED=1

  web:
    image: weather
    container_name: weather-web
    restart: unless-stopped
    command: streamlit run app/app.py --server.port 8501 --server.address 0.0.0.0
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8501:8501"
    depends_on:
      - pipeline
    environment:
      - PYTHONUNBUFFERED=1
```

**What each section does:**
- `build: .` — build the image from the `Dockerfile` in the current directory (only on `pipeline`)
- `image: weather` — both services use the same built image; no need to build twice
- `restart: unless-stopped` — Docker automatically restarts the container if it crashes or
  your machine reboots. "Unless-stopped" means it won't restart if you manually stop it.
- `command: tail -f /dev/null` — keeps the pipeline container alive doing nothing so cron
  can call `docker exec` into it. Without this the container would exit immediately.
- `volumes: ./data:/app/data` — maps your local `./data` folder to `/app/data` inside the
  container. Files written by the pipeline (models, predictions) appear on your hard drive.
- `ports: 8501:8501` — maps port 8501 inside the container to port 8501 on your machine.
  This is what makes `http://localhost:8501` work in your Windows browser.
- `depends_on: pipeline` — ensures the pipeline container starts before the web container.
- `PYTHONUNBUFFERED=1` — makes Python print logs immediately rather than buffering them,
  so you see output in real time with `docker logs`.

---

## Step 5 — Build the image

This downloads the base Python image and installs all dependencies. Takes 3–5 minutes the
first time; subsequent builds are much faster because Docker caches the pip install layer.

```bash
docker compose build
```

You should see output like:
```
[+] Building 180.3s (12/12) FINISHED
```

If it fails, the error message will tell you which step failed. Common issues:
- Network timeout → run it again, it will resume from cache
- Missing system package → the `apt-get install` line in the Dockerfile needs updating

---

## Step 6 — Start the containers

```bash
docker compose up -d
```

The `-d` flag means "detached" — runs in the background so you get your terminal back.

Verify both containers are running:
```bash
docker ps
```

You should see two rows: `weather-pipeline` and `weather-web`, both with status `Up`.

---

## Step 7 — Run the pipeline for the first time

The containers are running but no models or predictions exist yet. Run the full pipeline
manually to bootstrap everything:

```bash
docker exec weather-pipeline /app/run_pipeline.sh
```

`docker exec` runs a command inside a running container. This is the same command cron will
use — you're testing the exact thing that will run automatically.

This takes ~5 minutes. When done, verify the outputs exist:
```bash
ls data/03_primary/
```

You should see `model_precip.pkl`, `model_temp.pkl`, `predictions.json`, and the PNG plots.

---

## Step 8 — Open the website

Go to `http://localhost:8501` in your Windows browser.

If the page shows "No predictions found", the pipeline in Step 7 hasn't finished yet or
there was an error. Check the logs:
```bash
docker logs weather-pipeline
```

---

## Step 9 — Set up cron for automatic refresh

Cron runs on your WSL2 host (not inside the container) and calls `docker exec` to trigger
jobs in the pipeline container.

First, make sure the cron daemon is running in WSL2:
```bash
sudo service cron start
```

Open your cron schedule:
```bash
crontab -e
```

Add these two lines at the bottom:
```
# Hourly: fast inference (at :05 past the hour — gives NYISO time to publish)
5 * * * * docker exec weather-pipeline /app/run_inference_only.sh >> /home/zaccosenza/code/project-weather-dumb/logs/cron.log 2>&1

# Nightly: full retrain at 02:00
0 2 * * * docker exec weather-pipeline /app/run_pipeline.sh >> /home/zaccosenza/code/project-weather-dumb/logs/cron.log 2>&1
```

Save and exit: `Ctrl+O` → `Enter` → `Ctrl+X`

**Why :05 and not :00?** NYISO publishes Zone J load data ~5 minutes after the hour. Running
at :05 ensures the freshest data is available when the pipeline fetches it.

---

## Step 10 — Make cron survive WSL2 reboots

WSL2 does not start the cron daemon automatically on boot. Add this to your `~/.bashrc` so
it starts whenever you open a terminal:

```bash
echo '[ "$(pgrep cron)" = "" ] && sudo service cron start 2>/dev/null' >> ~/.bashrc
```

This checks if cron is already running and starts it if not. It's harmless to run multiple
times.

For the change to take effect in the current terminal:
```bash
source ~/.bashrc
```

---

## Ongoing Operations

### Check if containers are running
```bash
docker ps
```

### View live logs
```bash
docker logs -f weather-web       # Streamlit logs
docker logs -f weather-pipeline  # Pipeline container logs
docker logs --tail 50 weather-pipeline  # Last 50 lines only
```

### View cron job history
```bash
tail -50 logs/cron.log
```

### Restart containers
```bash
docker compose restart
```

### Stop everything
```bash
docker compose down
```

### Update code and rebuild
After changing any source file:
```bash
docker compose build
docker compose up -d
```

The `./data` bind mount is unaffected by rebuilds. Models and predictions are never lost.

---

## Troubleshooting

**`docker exec` fails with "no such container"**
The pipeline container has stopped. Run `docker compose up -d` to restart it.

**Website shows "No predictions found"**
`predictions.json` doesn't exist yet. Run Step 7 manually:
```bash
docker exec weather-pipeline /app/run_pipeline.sh
```

**Cron job isn't running**
Check if the daemon is alive: `pgrep cron`. If no output, run `sudo service cron start`.
Check your crontab: `crontab -l`.
Check the log: `tail -20 logs/cron.log`.

**Build fails at `pip install`**
Usually a network timeout. Run `docker compose build` again — Docker resumes from cache.

**Port 8501 not accessible from Windows browser**
Make sure Docker Desktop WSL2 integration is enabled for your distro.
Try `http://127.0.0.1:8501` instead of `localhost:8501`.
