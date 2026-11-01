# LifeSpace backend for Railway (or any Docker host). Build context: the backend folder.
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

ENV MODE=prod
EXPOSE 8000
# one worker: the improve loop keeps its jobs in memory
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
