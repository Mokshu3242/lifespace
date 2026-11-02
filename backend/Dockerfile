# LifeSpace backend for Render (or any Docker host). Build context: the backend folder.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# OpenCV (headless) and onnxruntime need these small system libraries
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# the app finds its data next to the backend folder (repo root), so keep that shape: /srv/backend
WORKDIR /srv/backend
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install rapidocr-onnxruntime==1.2.3 --no-deps
COPY . .

# MODE=prod; on a 512 MB server read plan text in tiles (about 350 MB instead of 900 MB) and keep memory
# tidy; the live site calls the backend directly for long requests (Cloudflare cuts proxied ones at 100 s)
ENV MODE=prod OCR_TILE=1000 MALLOC_ARENA_MAX=2 \
    FRONTEND_ORIGIN=https://lifespace.mokshadsankhe.me,https://lifespace-9ke.pages.dev,http://localhost:5173
EXPOSE 8000
# one worker: the improve loop keeps its jobs in memory
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
