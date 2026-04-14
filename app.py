import os, json, math, subprocess, tempfile, requests, traceback, threading, time, random, base64
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUBMAGIC_KEY = 'sk-b0e3311c51f0d1251a5e43cdb7086fb05fe4cec827a848ad47bd2905a3bb7643'
SUBMAGIC_URL = 'https://api.submagic.co/v1'

# ─── OVERLAY VFX ─────────────────────────────────────────────────────────────
VFX_OVERLAYS = [
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/filmburn.mp4',
    # Ajoute ici tes autres overlays quand tu les uploades dans Supabase Storage
    # 'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/glitch.mp4',
]
# ─────────────────────────────────────────────────────────────────────────────
FILM_BURN_URL = os.environ.get('FILM_BURN_URL', '')
WATERMARK_URL = 'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/watermark/watermark.png'

WATERMARK_B64 = ""  # Remplacé par URL Supabase

@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Ad Machine Worker', 'status': 'running'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'ffmpeg': 'ok'})

class SB:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.h = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': 'return=representation'}

    def update_project(self, pid, data):
        try: requests.patch(f"{self.url}/rest/v1/projects?id=eq.{pid}", headers=self.h, json=data, timeout=30)
        except: pass

    def update_video(self, pid, data):
        try: requests.patch(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.true", headers=self.h, json=data, timeout=30)
        except: pass

    def get_sources(self, pid):
        try:
            r = requests.get(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.false&select=*", headers=self.h, timeout=30)
            return r.json() if r.ok else []
        except: return []

    def upload(self, bucket, path, data, ct='video/mp4'):
        try:
            h = {'apikey': self.h['apikey'], 'Authorization': self.h['Authorization'], 'Content-Type': ct, 'x-upsert': 'true'}
            r = requests.post(f"{self.url}/storage/v1/object/{bucket}/{path}", headers=h, data=data, timeout=300)
            print(f"  SB upload {path}: {r.status_code}")
        except Exception as e: print(f"  SB upload error: {e}")

    def public_url(self, bucket, path):
        return f"{self.url}/storage/v1/object/public/{bucket}/{path}"


@app.route('/render', methods=['POST'])
def render():
    data = request.json
    pid          = data.get('projectId')
    video_urls   = data.get('videoUrls', [])
    voice_url    = data.get('voiceUrl')
    music_url    = data.get('musicUrl')
    voiceover    = data.get('voiceover', '')
    duration     = int(data.get('duration', 30))
    style        = data.get('captionStyle', 'Hormozi 2')
    vfx          = data.get('vfx', False)
    with_captions = data.get('withCaptions', True)
    is_free      = data.get('isFree', True)
    user_id      = data.get('userId', '')
    app_url      = data.get('appUrl', 'https://admachine.io')
    sb_url       = data.get('supabaseUrl')
    sb_key       = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Donnees manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, user_id, app_url, sb, sb_url=sb_url, sb_key=sb_key)
            print(f"[{pid}] DONE")
        except Exception as e:
            traceback.print_exc()
            print(f"[{pid}] ERROR: {e}")
            try:
                srcs = sb.get_sources(pid)
                if srcs: sb.update_video(pid, {'video_url': srcs[0]['video_url']})
                sb.update_project(pid, {'status': 'done'})
            except: pass

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'success': True})


def dl(url, path):
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in r.iter_content(65536): f.write(chunk)

def get_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path], capture_output=True, text=True)
    return float(json.loads(r.stdout)['format']['duration'])

def interleave_clips(clips_by_video):
    result = []
    max_len = max(len(c) for c in clips_by_video) if clips_by_video else 0
    for i in range(max_len):
        for vc in clips_by_video:
            if i < len(vc): result.append(vc[i])
    return result


def add_watermark(video_path, tmp, duration, is_free):
    if not is_free:
        print("  Watermark skipped (paid plan)")
        return video_path

    output = f"{tmp}/watermarked.mp4"
    wm_path = f"{tmp}/watermark.png"

    # Télécharger le watermark depuis Supabase Storage
    try:
        dl(WATERMARK_URL, wm_path)
        print("  Watermark downloaded OK")
    except Exception as e:
        print(f"  Watermark download error: {e}")
        return video_path

    res = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', wm_path,
        '-filter_complex',
        '[1:v]scale=1080:-1,format=rgba,colorchannelmixer=aa=0.85[wm];'
        '[0:v][wm]overlay=(W-w)/2:(H-h)/2:format=auto[vout]',
        '-map', '[vout]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart', '-t', str(duration), output
    ], capture_output=True, text=True, timeout=300)

    if res.returncode != 0:
        print(f"  Watermark error: {res.stderr[-200:]}")
        return video_path

    print("  Watermark added (free) OK")
    return output


def apply_vfx(video_path, tmp, duration):
    """
    VFX Pro: overlay filmburn fond noir, N fois (3-5) à positions aléatoires.
    - Vérifie que l'overlay existe avant de l'appliquer
    - format=gbrp pour blend screen sans filtre rose
    - split filter pour dupliquer l'overlay en N copies indépendantes
    """
    import random
    output = f"{tmp}/vfx_output.mp4"

    try:
        actual_dur = get_duration(video_path)
        active_overlays = [u for u in VFX_OVERLAYS if u.strip() and not u.strip().startswith('#')]
        if not active_overlays:
            print("  [VFX] Aucun overlay configuré")
            return video_path

        # Essayer chaque overlay jusqu'à en trouver un qui marche
        overlay_path = f"{tmp}/vfx_overlay.mp4"
        overlay_dur = None
        random.shuffle(active_overlays)
        
        for overlay_url in active_overlays:
            try:
                print(f"  [VFX] Trying overlay: {overlay_url[-40:]}")
                dl(overlay_url, overlay_path)
                overlay_dur = get_duration(overlay_path)
                print(f"  [VFX] Overlay OK: {overlay_dur:.1f}s")
                break
            except Exception as e:
                print(f"  [VFX] Overlay failed: {e}")
                continue

        if not overlay_dur:
            print("  [VFX] Tous les overlays ont échoué")
            return video_path

        nb = random.randint(3, 5)

        # Positions espacées avec jitter
        spacing = actual_dur / (nb + 1)
        positions = []
        for i in range(nb):
            base = spacing * (i + 1)
            jitter = random.uniform(-spacing * 0.25, spacing * 0.25)
            pos = max(0.0, min(actual_dur - overlay_dur, round(base + jitter, 2)))
            positions.append(pos)
        positions.sort()
        print(f"  [VFX] {nb}x overlay pos={[round(p,1) for p in positions]}")

        filter_parts = [
            "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,format=gbrp[ovbase]",
            f"[ovbase]split={nb}" + "".join(f"[ovcopy{i}]" for i in range(nb)),
            "[0:v]format=gbrp[mainv]"
        ]

        current = "[mainv]"
        for i, pos in enumerate(positions):
            end_pos = round(pos + overlay_dur, 2)
            filter_parts.append(f"[ovcopy{i}]setpts=PTS-STARTPTS+{pos}/TB[ov{i}]")
            out = f"[v{i+1}]"
            filter_parts.append(
                f"{current}[ov{i}]blend=all_mode=lighten:all_opacity=0.8:"
                f"enable='between(t,{pos},{end_pos})':shortest=0:repeatlast=0{out}"
            )
            current = out

        filter_parts.append(f"[v{nb}]format=yuv420p[vout]")

        audio_parts = []
        for i, pos in enumerate(positions):
            audio_parts.append(
                f"[1:a]atrim=0:{overlay_dur},asetpts=PTS-STARTPTS,"
                f"adelay={int(pos*1000)}|{int(pos*1000)},volume=0.70[a{i}]"
            )
        a_labels = "".join(f"[a{i}]" for i in range(nb))
        audio_parts.append(
            f"[0:a]{a_labels}amix=inputs={nb+1}:duration=first:normalize=0[aout]"
        )

        filter_complex = ";".join(filter_parts + audio_parts)

        res = subprocess.run([
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', overlay_path,
            '-filter_complex', filter_complex,
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
            '-pix_fmt', 'yuv420p', '-r', '30',
            '-c:a', 'aac', '-b:a', '192k',
            '-t', str(actual_dur),
            output
        ], capture_output=True, text=True, timeout=400)

        if res.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 10000:
            size = os.path.getsize(output) / 1024 / 1024
            print(f"  [VFX] OK ({size:.1f}MB) — {nb}x overlay lighten blend")
            return output
        else:
            print(f"  [VFX] FFmpeg error: {res.stderr[-600:]}")
            return video_path

    except Exception as e:
        print(f"  [VFX] Exception: {e}")
        return video_path


def submagic_process(video_path, pid, template, use_vfx_transitions=False):
    headers_sm = {'x-api-key': SUBMAGIC_KEY}

    valid_templates = [
        'Hormozi 2','Hormozi 1','Hormozi 3','Hormozi 4','Hormozi 5',
        'Beast','Sara','Karl','Ella','Matt','Jess','Nick','Laura',
        'Daniel','Dan','Dan 2','Devin','Tayo','Jason','Noah',
        'Kelly','Kelly 2','William','Mia','Tom','Zoe'
    ]
    template_map = {
        'Kelly 2': 'Kelly 2',
        'Dan 2': 'Dan 2',
        'William': 'William',
    }
    template = template_map.get(template, template)
    if template not in valid_templates:
        print(f"  [SM] Template '{template}' inconnu → Hormozi 2")
        template = 'Hormozi 2'

    print(f"  [SM] Starting — template={template} vfx={use_vfx_transitions} key={SUBMAGIC_KEY[:12]}...")

    form_data = {
        'title': f'AdMachine-{pid[:8]}',
        'language': 'fr',
        'templateName': template,
        'magicZooms': 'true',
        'cleanAudio': 'false',
        'removeSilencePace': 'natural',
    }

    if use_vfx_transitions:
        form_data['removeSilencePace'] = 'fast'
        print(f"  [SM] VFX mode: magicZooms + removeSilence(fast)")
    else:
        print(f"  [SM] Captions mode: magicZooms + removeSilence(natural)")

    try:
        with open(video_path, 'rb') as f:
            video_bytes = f.read()
        file_size = len(video_bytes)
        print(f"  [SM] Uploading {file_size/1024/1024:.1f}MB...")
        resp = requests.post(
            f'{SUBMAGIC_URL}/projects/upload',
            headers=headers_sm,
            files={'file': ('video.mp4', video_bytes, 'video/mp4')},
            data=form_data,
            timeout=300
        )
    except Exception as e:
        print(f"  [SM] Upload exception: {e}")
        return None

    print(f"  [SM] Upload: {resp.status_code} — {resp.text[:300]}")
    if not resp.ok:
        return None

    try:
        sm_data = resp.json()
    except:
        return None

    sm_id = (sm_data.get('id') or sm_data.get('projectId') or sm_data.get('_id'))
    print(f"  [SM] Project ID: {sm_id}")
    if not sm_id:
        return None

    print(f"  [SM] Waiting transcription...")
    for i in range(40):
        time.sleep(5)
        try:
            r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
            if not r.ok: continue
            proj = r.json()
            status = proj.get('status', '')
            trans = proj.get('transcriptionStatus', '')
            if i % 4 == 0:
                print(f"  [SM] [{i+1}] status={status} trans={trans}")
            if status == 'failed':
                return None
            if trans == 'COMPLETED' or status == 'completed':
                print(f"  [SM] Transcription OK!")
                break
        except: continue

    print(f"  [SM] Exporting 1080x1920...")
    try:
        exp = requests.post(
            f'{SUBMAGIC_URL}/projects/{sm_id}/export',
            headers={**headers_sm, 'Content-Type': 'application/json'},
            json={'width': 1080, 'height': 1920, 'fps': 30},
            timeout=30
        )
        print(f"  [SM] Export: {exp.status_code}")
        if not exp.ok:
            return None
    except Exception as e:
        print(f"  [SM] Export exception: {e}")
        return None

    print(f"  [SM] Waiting render...")
    for i in range(60):
        time.sleep(5)
        try:
            r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
            if not r.ok: continue
            proj = r.json()
            status = proj.get('status', '')
            url = (proj.get('directUrl') or proj.get('downloadUrl') or
                   proj.get('outputUrl') or proj.get('videoUrl') or proj.get('url'))
            if i % 6 == 0:
                print(f"  [SM] [{i+1}] status={status} url={'yes' if url else 'no'}")
            if status == 'completed' and url:
                print(f"  [SM] Done!")
                return url
            if status == 'failed':
                return None
        except: continue

    print("  [SM] Timeout — fallback vidéo locale")
    return None


BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')

def notify_user_video_ready(user_id, video_url, project_id, sb_url, sb_key):
    if not BREVO_API_KEY:
        print("  [NOTIF] BREVO_API_KEY manquant")
        return

    headers_sb = {
        'apikey': sb_key,
        'Authorization': f'Bearer {sb_key}',
        'Content-Type': 'application/json'
    }

    email = None
    try:
        r = requests.get(
            f"{sb_url}/auth/v1/admin/users/{user_id}",
            headers=headers_sb, timeout=10
        )
        print(f"  [NOTIF] auth: {r.status_code}")
        if r.ok:
            email = r.json().get('email')
    except Exception as e:
        print(f"  [NOTIF] auth error: {e}")

    if not email:
        print(f"  [NOTIF] email introuvable pour {user_id[:8]}")
        return

    first_name = 'là'
    try:
        rp = requests.get(
            f"{sb_url}/rest/v1/profiles?id=eq.{user_id}&select=first_name",
            headers=headers_sb, timeout=10
        )
        if rp.ok and rp.json():
            first_name = rp.json()[0].get('first_name') or 'là'
    except: pass

    desc = 'Ton produit'
    try:
        rj = requests.get(
            f"{sb_url}/rest/v1/projects?id=eq.{project_id}&select=product_description",
            headers=headers_sb, timeout=10
        )
        if rj.ok and rj.json():
            raw = rj.json()[0].get('product_description') or ''
            desc = raw.replace('#','').replace('*','').replace('`','')[:80]
    except: pass

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#050508;font-family:system-ui,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:40px 20px;">
    <div style="text-align:center;margin-bottom:32px;">
      <div style="background:linear-gradient(135deg,#6366f1,#a855f7);display:inline-flex;align-items:center;gap:10px;padding:10px 20px;border-radius:12px;">
        <span style="color:white;font-size:20px;font-weight:900;">⚡ Ad Machine</span>
      </div>
    </div>
    <div style="background:#0d0d14;border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:32px;text-align:center;">
      <div style="font-size:48px;margin-bottom:12px;">🎬</div>
      <h1 style="color:white;font-size:24px;font-weight:900;margin:0 0 8px;">Ta pub est prête !</h1>
      <p style="color:rgba(255,255,255,0.5);font-size:14px;margin:0 0 20px;">Bonjour {first_name}, ta vidéo publicitaire vient d'être générée.</p>
      <div style="background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.2);border-radius:12px;padding:12px;margin-bottom:24px;">
        <p style="color:rgba(255,255,255,0.5);font-size:11px;margin:0 0 4px;text-transform:uppercase;">Produit</p>
        <p style="color:white;font-size:14px;margin:0;">{desc}</p>
      </div>
      <a href="{video_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#a855f7);color:white;text-decoration:none;font-weight:700;font-size:16px;padding:16px 40px;border-radius:14px;">⬇️ Télécharger ma pub</a>
      <p style="margin-top:20px;"><a href="https://admachine.io/dashboard" style="color:#6366f1;text-decoration:none;font-size:13px;">Voir mon tableau de bord →</a></p>
    </div>
    <p style="text-align:center;color:rgba(255,255,255,0.2);font-size:11px;margin-top:20px;">Ad Machine · admachine.io</p>
  </div>
</body></html>"""

    try:
        res = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={'Content-Type': 'application/json', 'api-key': BREVO_API_KEY},
            json={
                'sender': {'name': 'Ad Machine', 'email': os.environ.get('BREVO_SENDER_EMAIL', 'alphadiagne902@gmail.com')},
                'to': [{'email': email, 'name': first_name}],
                'subject': '🎬 Ta pub vidéo Ad Machine est prête !',
                'htmlContent': html,
            },
            timeout=15
        )
        print(f"  [NOTIF] Brevo: {res.status_code} → {email}")
        if not res.ok:
            print(f"  [NOTIF] Brevo error: {res.text[:200]}")
    except Exception as e:
        print(f"  [NOTIF] Brevo exception: {e}")


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, user_id, app_url, sb, sb_url=None, sb_key=None):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] START {duration}s {len(video_urls)} videos vfx={vfx} captions={with_captions} free={is_free}")

        clips_needed = math.ceil(duration / 3.0) + 2
        clips_per_video = math.ceil(clips_needed / max(len(video_urls), 1)) + 2

        # 1. EXTRAIRE CLIPS
        clips_by_video = []
        for i, url in enumerate(video_urls[:8]):
            src = f"{tmp}/src_{i}.mp4"
            try:
                dl(url, src)
                print(f"  video {i+1} downloaded")
                clips = []
                src_dur = get_duration(src)
                start = 0.0; c_idx = 0
                while start + 1.5 <= src_dur and c_idx < clips_per_video:
                    out = f"{tmp}/v{i}_c{c_idx:03d}.mp4"
                    cd = min(3.0, src_dur - start)
                    r = subprocess.run([
                        'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                        '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p', '-an', out
                    ], capture_output=True)
                    if r.returncode == 0: clips.append(out)
                    c_idx += 1; start += 3.0
                if clips:
                    clips_by_video.append(clips)
                    print(f"  video {i+1}: {len(clips)} clips")
                try: os.remove(src)
                except: pass
            except Exception as e:
                print(f"  error video {i}: {e}")

        if not clips_by_video: raise Exception("No clips extracted")

        # 2. ASSEMBLER
        interleaved = interleave_clips(clips_by_video)
        needed = math.ceil(duration / 3.0)
        selected = [interleaved[i % len(interleaved)] for i in range(needed)]
        print(f"  {len(selected)} clips interleaved")

        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for c in selected: f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-r', '30', assembled
        ], check=True, capture_output=True)
        print("  assembled OK")

        for clips in clips_by_video:
            for c in clips:
                try: os.remove(c)
                except: pass

        # 3. VOIX + MUSIQUE
        import re as _re
        voiceover = _re.sub(r'^[#\s\*]*[^\n]{0,60}\n', '', voiceover).strip()
        voiceover = _re.sub(r'[#\*`]', '', voiceover).strip()
        voice_path = music_path = None
        if voice_url:
            try:
                p = f"{tmp}/voice.mp3"; dl(voice_url, p); voice_path = p
                print("  voice OK")
            except Exception as e: print(f"  voice error: {e}")
        if music_url:
            try:
                p = f"{tmp}/music.mp3"; dl(music_url, p); music_path = p
                print("  music OK")
            except Exception as e: print(f"  music error: {e}")

        # 4. MIXAGE
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1
        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        actual_duration = duration
        if voice_path:
            try:
                voice_dur = get_duration(voice_path)
                actual_duration = voice_dur
                print(f"  voice duration={actual_duration:.1f}s (target={duration}s)")
            except Exception as e:
                print(f"  get_duration error: {e}")

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += ['-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k']
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{actual_duration}[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]asetpts=PTS-STARTPTS[v];[2:a]volume=0.10,asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']

        cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', '-r', '30', '-t', str(actual_duration), output]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            raise Exception(f"FFmpeg mix: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  mix OK ({size_mb:.1f}MB)")
        try: os.remove(assembled)
        except: pass

        # 5. VFX Pro
        if vfx:
            print("  Applying VFX Pro...")
            vfx_output = apply_vfx(output, tmp, actual_duration)
            if vfx_output != output:
                output = vfx_output
                print("  VFX Pro OK")

        # 6. SUBMAGIC captions
        submagic_url = submagic_process(output, pid, style, use_vfx_transitions=vfx) if with_captions else None
        if not with_captions:
            print("  Captions skipped by user")

        video_final = output
        if submagic_url:
            print(f"  Downloading Submagic output...")
            try:
                sm_local = f"{tmp}/submagic_out.mp4"
                dl(submagic_url, sm_local)
                if os.path.exists(sm_local) and os.path.getsize(sm_local) > 10000:
                    video_final = sm_local
                    print("  Submagic downloaded OK")
                else:
                    print("  Submagic file trop petit — fallback vidéo locale")
            except Exception as e:
                print(f"  Submagic download error: {e} — fallback vidéo locale")

        # 7. FILIGRANE
        print(f"  Applying watermark (is_free={is_free})...")
        if is_free:
            video_final = add_watermark(video_final, tmp, duration, is_free)

        # 8. UPLOAD SUPABASE
        filename = f"renders/{pid}/ad_machine_{pid[:8]}.mp4"
        print(f"  Uploading to Supabase...")
        with open(video_final, 'rb') as f: video_bytes = f.read()
        sb.upload('videos', filename, video_bytes)
        final_url = sb.public_url('videos', filename)
        print(f"  Upload OK: {final_url[:60]}")

        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})

        # 9. NOTIFICATION EMAIL — dans un thread séparé pour ne pas bloquer
        if user_id and sb_url and sb_key:
            def send_notif():
                try:
                    notify_user_video_ready(user_id, final_url, pid, sb_url, sb_key)
                except Exception as e:
                    print(f"  Notification error: {e}")
                    try:
                        requests.post(f"{app_url}/api/send-notification", json={
                            'type': 'video_ready',
                            'userId': user_id,
                            'videoUrl': final_url,
                            'projectId': pid,
                        }, timeout=15)
                    except: pass
            threading.Thread(target=send_notif, daemon=True).start()

        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
