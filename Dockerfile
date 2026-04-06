FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-dejavu-core \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000

# Timeout 600s, 1 seul worker pour économiser la RAM
CMD gunicorn --bind 0.0.0.0:$PORT --timeout 600 --workers 1 --threads 4 app:app
