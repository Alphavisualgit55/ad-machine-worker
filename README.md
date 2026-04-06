# Ad Machine Worker — FFmpeg Server

Serveur de montage vidéo automatique.

## Variables d'environnement Koyeb

Aucune variable requise — tout est passé dans la requête POST.

## Deploy sur Koyeb

1. Push ce repo sur GitHub
2. Sur Koyeb → New App → GitHub → choisir ce repo
3. Koyeb détecte automatiquement le Dockerfile
4. Copier l'URL → ajouter dans Netlify comme WORKER_URL
