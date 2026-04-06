# Ad Machine Worker — Serveur de montage vidéo

Serveur Python Flask + FFmpeg pour le montage vidéo automatique.

## Variables d'environnement Railway

```
SUPABASE_URL = https://lowkevqfsfhhcaebqkxi.supabase.co
SUPABASE_SERVICE_ROLE_KEY = ta_clé_service_role
```

## Ce que fait ce serveur

1. Reçoit les vidéos b-roll depuis Supabase
2. Les découpe en clips de 3 secondes
3. Assemble le montage final
4. Ajoute les captions mot par mot synchronisées
5. Mixe la voix off + musique (10%)
6. Exporte en MP4 1080x1920
7. Upload le résultat dans Supabase
