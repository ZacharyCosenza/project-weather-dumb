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
