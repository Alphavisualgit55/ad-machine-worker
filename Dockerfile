FROM python:3.11-slim

# Installer FFmpeg + outils polices
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-dejavu-core \
    fontconfig \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Télécharger Montserrat Black (pour les captions bold TikTok)
RUN mkdir -p /usr/share/fonts/truetype/montserrat && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Black.ttf" \
         -O /usr/share/fonts/truetype/montserrat/Montserrat-Black.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf" \
         -O /usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Regular.ttf" \
         -O /usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf && \
    fc-cache -fv && \
    echo "Polices installées :" && fc-list | grep -i montserrat

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000

# Utiliser $PORT si disponible, sinon 8000
CMD gunicorn --bind "0.0.0.0:${PORT:-8000}" --timeout 600 --workers 1 --threads 8 app:app
