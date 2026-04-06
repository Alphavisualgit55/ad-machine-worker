FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --quiet -r requirements.txt
COPY . .

EXPOSE 8000
CMD gunicorn --bind "0.0.0.0:${PORT:-8000}" --timeout 600 --workers 1 --threads 8 app:app
