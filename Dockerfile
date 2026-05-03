FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
    ffmpeg fonts-dejavu-core fonts-liberation \
    libfreetype6-dev libjpeg-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -q -r requirements.txt
COPY app.py .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "import requests; r=requests.get('http://localhost:${PORT:-8000}/health',timeout=5); exit(0 if r.ok else 1)" || exit 1

EXPOSE 8000

# 1 worker (threading géré par app.py avec Semaphore)
# 8 threads pour gérer les requêtes HTTP entrantes en parallèle
# timeout 700s > durée max d'un rendu (~600s)
CMD gunicorn --bind "0.0.0.0:${PORT:-8000}" \
    --timeout 700 \
    --workers 1 \
    --threads 16 \
    --worker-class gthread \
    --keep-alive 5 \
    --log-level info \
    app:app
