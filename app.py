import os, json, math, subprocess, tempfile, requests, traceback, threading, time, random, base64
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUBMAGIC_KEY = 'sk-b0e3311c51f0d1251a5e43cdb7086fb05fe4cec827a848ad47bd2905a3bb7643'
SUBMAGIC_URL = 'https://api.submagic.co/v1'

VFX_OVERLAYS = [
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/filmburn.mp4',
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/fx1.mp4',
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/fx2.mp4',
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/fx3.mp4',
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/fx4.mp4',
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/fx5.mp4',
]

FILM_BURN_URL = os.environ.get('FILM_BURN_URL', '')
WATERMARK_URL = 'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/watermark/watermark.png'
WATERMARK_B64 = ""

@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Ad Machine Worker', 'status': 'running'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'ffmpeg': 'ok',
        'active_renders': active_renders,
        'max_parallel': MAX_PARALLEL,
        'slots_free': MAX_PARALLEL - active_renders,
    })

class SB:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.h = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': 'return=representation'}

    def update_project(self, pid, data):
        try: requests.patch(f"{self.url}/rest/v1/projects?id=eq.{pid}", headers=self.h, json=data, timeout=30)
        except: pass

    def refund_credit(self, pid, vfx=False):
        """Rembourse 1 ou 1.5 crédit si la vidéo échoue"""
        try:
            credit_cost = 1.5 if vfx else 1.0
            # Récupérer user_id du projet
            r = requests.get(f"{self.url}/rest/v1/projects?id=eq.{pid}&select=user_id", headers=self.h, timeout=15)
            if not r.ok: return
            data = r.json()
            if not data: return
            user_id = data[0].get('user_id')
            if not user_id: return
            # Récupérer crédits actuels
            r2 = requests.get(f"{self.url}/rest/v1/subscriptions?user_id=eq.{user_id}&select=credits_remaining", headers=self.h, timeout=15)
            if not r2.ok: return
            subs = r2.json()
            if not subs: return
            current = float(subs[0].get('credits_remaining', 0))
            new_credits = round(current + credit_cost, 1)
            # Rembourser
            requests.patch(
                f"{self.url}/rest/v1/subscriptions?user_id=eq.{user_id}",
                headers=self.h,
                json={'credits_remaining': new_credits},
                timeout=15
            )
            print(f"  [REFUND] {credit_cost} crédit remboursé → user {user_id[:8]} ({current} → {new_credits})")
        except Exception as e:
            print(f"  [REFUND ERROR] {e}")

    def update_video(self, pid, data):
        try: requests.patch(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.true", headers=self.h, json=data, timeout=30)
        except: pass

    def get_sources(self, pid):
        try:
            r = requests.get(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.false&select=*", headers=self.h, timeout=30)
            return r.json() if r.ok else []
        except: return []

    def upload(self, bucket, path, data, ct='video/mp4'):
        h = {'apikey': self.h['apikey'], 'Authorization': self.h['Authorization'], 'Content-Type': ct, 'x-upsert': 'true'}
        r = requests.post(f"{self.url}/storage/v1/object/{bucket}/{path}", headers=h, data=data, timeout=300)
        print(f"  SB upload {path}: {r.status_code} {r.text[:100]}")
        if not r.ok:
            raise Exception(f"Upload failed {r.status_code}: {r.text[:200]}")

    def public_url(self, bucket, path):
        return f"{self.url}/storage/v1/object/public/{bucket}/{path}"


# ── File d'attente avec parallélisme limité ──────────────────────────────────
import queue as _queue
MAX_PARALLEL = 3  # Max 3 rendus en parallèle (XLarge = 8 vCPU)
render_semaphore = threading.Semaphore(MAX_PARALLEL)
active_renders = 0
active_renders_lock = threading.Lock()

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
        global active_renders
        with render_semaphore:  # Max MAX_PARALLEL en simultané
            with active_renders_lock:
                active_renders += 1
            print(f"[{pid[:8]}] SLOT acquis — {active_renders}/{MAX_PARALLEL} actifs")
            sb = SB(sb_url, sb_key)
            try:
                url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, user_id, app_url, sb, sb_url=sb_url, sb_key=sb_key)
                print(f"[{pid}] DONE")
            except Exception as e:
                traceback.print_exc()
                print(f"[{pid}] ERROR: {e}")
                try:
                    sb.update_project(pid, {'status': 'failed'})
                    sb.refund_credit(pid, vfx=vfx)
                except Exception as re:
                    print(f"[{pid}] REFUND ERROR: {re}")
            finally:
                with active_renders_lock:
                    active_renders -= 1
                print(f"[{pid[:8]}] SLOT libéré — {active_renders}/{MAX_PARALLEL} actifs")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'success': True, 'queued': True})


def dl(url, path):
    r = requests.get(url, stream=True, timeout=180)
    if not r.ok:
        raise Exception(f"HTTP {r.status_code} pour {url[-60:]}")
    r.raise_for_status()
    size = 0
    with open(path, 'wb') as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
            size += len(chunk)
    if size == 0:
        raise Exception(f"Fichier vide: {url[-60:]}")
    print(f"    dl OK: {size/1024:.0f}KB")

def get_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path], capture_output=True, text=True)
    return float(json.loads(r.stdout)['format']['duration'])

def detect_voice_cuts(voice_path, total_duration):
    try:
        r = subprocess.run([
            'ffmpeg', '-y', '-i', voice_path,
            '-af', 'silencedetect=noise=-35dB:duration=0.3',
            '-f', 'null', '-'
        ], capture_output=True, text=True, timeout=30)
        import re
        silence_ends = re.findall(r'silence_end: ([0-9.]+)', r.stderr)
        cuts = [float(t) for t in silence_ends]
        if not cuts:
            cuts = [i * 3.0 for i in range(1, int(total_duration / 3.0) + 1)]
        else:
            filtered = [cuts[0]]
            for t in cuts[1:]:
                if t - filtered[-1] >= 2.0:
                    filtered.append(t)
            cuts = filtered
        return cuts
    except:
        return [i * 3.0 for i in range(1, int(total_duration / 3.0) + 1)]

def interleave_clips(clips_by_video):
    result = []
    max_len = max(len(c) for c in clips_by_video) if clips_by_video else 0
    for i in range(max_len):
        for vc in clips_by_video:
            if i < len(vc): result.append(vc[i])
    return result


def add_watermark(video_path, tmp, duration, is_free):
    if not is_free:
        return video_path
    output = f"{tmp}/watermarked.mp4"
    wm_path = f"{tmp}/watermark.png"
    wm_downloaded = False
    try:
        dl(WATERMARK_URL, wm_path)
        if os.path.exists(wm_path) and os.path.getsize(wm_path) > 1000:
            wm_downloaded = True
    except Exception as e:
        print(f"  Watermark download error: {e}")

    if wm_downloaded:
        res = subprocess.run([
            'ffmpeg', '-y', '-i', video_path, '-i', wm_path,
            '-filter_complex',
            '[1:v]scale=1080:-1,format=rgba,colorchannelmixer=aa=0.85[wm];'
            '[0:v][wm]overlay=(W-w)/2:(H-h)/2:format=auto[vout]',
            '-map', '[vout]', '-map', '0:a?',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', '-t', str(duration), output
        ], capture_output=True, text=True, timeout=300)
    else:
        res = subprocess.run([
            'ffmpeg', '-y', '-i', video_path,
            '-vf', (
                "drawtext=text='AD MACHINE':fontsize=52:fontcolor=white@0.75:"
                "x=(w-text_w)/2:y=(h-text_h)/2:"
                "shadowcolor=black@0.5:shadowx=3:shadowy=3,"
                "drawtext=text='admachine.io':fontsize=28:fontcolor=white@0.60:"
                "x=(w-text_w)/2:y=(h-text_h)/2+65:"
                "shadowcolor=black@0.4:shadowx=2:shadowy=2"
            ),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', '-t', str(duration), output
        ], capture_output=True, text=True, timeout=300)

    if res.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 100000:
        print("  Watermark added (free) OK")
        return output
    return video_path


def apply_vfx(video_path, tmp, duration, cut_points=None):
    output = f"{tmp}/vfx_output.mp4"
    try:
        actual_dur = get_duration(video_path)
        active_overlays = [u for u in VFX_OVERLAYS if u.strip()]
        if not active_overlays:
            return video_path

        overlay_path = f"{tmp}/vfx_overlay.mp4"
        overlay_dur = None
        random.shuffle(active_overlays)

        for overlay_url in active_overlays:
            try:
                r_check = requests.head(overlay_url, timeout=10)
                if r_check.status_code != 200:
                    continue
                dl(overlay_url, overlay_path)
                overlay_dur = get_duration(overlay_path)
                break
            except:
                continue

        if not overlay_dur:
            return video_path

        if cut_points and len(cut_points) > 0:
            positions = []
            for cut in cut_points:
                pos = max(0.0, min(actual_dur - overlay_dur, round(cut - overlay_dur / 2, 2)))
                positions.append(pos)
            positions = sorted(list(set([round(p,2) for p in positions])))
            if len(positions) > 8:
                positions = positions[:8]
        else:
            nb = min(random.randint(3, 5), max(1, int(actual_dur / 4)))
            spacing = actual_dur / (nb + 1)
            positions = [max(0.0, min(actual_dur - overlay_dur, round(spacing * (i + 1), 2))) for i in range(nb)]

        nb = len(positions)
        if nb == 0:
            return video_path

        filter_parts = [
            "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=gbrp[ovbase]",
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
        audio_parts.append(f"[0:a]{a_labels}amix=inputs={nb+1}:duration=first:normalize=0[aout]")

        filter_complex = ";".join(filter_parts + audio_parts)
        res = subprocess.run([
            'ffmpeg', '-y', '-i', video_path, '-i', overlay_path,
            '-filter_complex', filter_complex,
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
            '-pix_fmt', 'yuv420p', '-r', '30',
            '-c:a', 'aac', '-b:a', '192k',
            '-t', str(actual_dur), output
        ], capture_output=True, text=True, timeout=400)

        if res.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 10000:
            return output
        return video_path
    except:
        return video_path


def submagic_process(video_path, pid, template, use_vfx_transitions=False):
    headers_sm = {'x-api-key': SUBMAGIC_KEY}
    valid_templates = [
        'Hormozi 2','Hormozi 1','Hormozi 3','Hormozi 4','Hormozi 5',
        'Beast','Sara','Karl','Ella','Matt','Jess','Nick','Laura',
        'Daniel','Dan','Dan 2','Devin','Tayo','Jason','Noah',
        'Kelly','Kelly 2','William','Mia','Tom','Zoe'
    ]
    template_map = {'Kelly 2':'Kelly 2','Dan 2':'Dan 2','William':'William'}
    template = template_map.get(template, template)
    if template not in valid_templates:
        template = 'Hormozi 2'

    print(f"  [SM] Starting — template={template}")
    form_data = {
        'title': f'AdMachine-{pid[:8]}',
        'language': 'fr',
        'templateName': template,
        'magicZooms': 'true',
        'cleanAudio': 'false',
        'removeSilencePace': 'fast' if use_vfx_transitions else 'natural',
    }

    try:
        with open(video_path, 'rb') as f:
            video_bytes = f.read()
        print(f"  [SM] Uploading {len(video_bytes)/1024/1024:.1f}MB...")
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

    if not resp.ok:
        return None

    try:
        sm_data = resp.json()
    except:
        return None

    sm_id = sm_data.get('id') or sm_data.get('projectId') or sm_data.get('_id')
    if not sm_id:
        return None

    for i in range(40):
        time.sleep(5)
        try:
            r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
            if not r.ok: continue
            proj = r.json()
            status = proj.get('status', '')
            trans = proj.get('transcriptionStatus', '')
            if status == 'failed': return None
            if trans == 'COMPLETED' or status == 'completed':
                print(f"  [SM] Transcription OK!")
                break
        except: continue

    try:
        exp = requests.post(
            f'{SUBMAGIC_URL}/projects/{sm_id}/export',
            headers={**headers_sm, 'Content-Type': 'application/json'},
            json={'width': 1080, 'height': 1920, 'fps': 30},
            timeout=30
        )
        if not exp.ok: return None
    except:
        return None

    for i in range(60):
        time.sleep(5)
        try:
            r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
            if not r.ok: continue
            proj = r.json()
            status = proj.get('status', '')
            url = (proj.get('directUrl') or proj.get('downloadUrl') or
                   proj.get('outputUrl') or proj.get('videoUrl') or proj.get('url'))
            if status == 'completed' and url:
                print(f"  [SM] Done!")
                return url
            if status == 'failed': return None
        except: continue

    return None


BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')

def notify_user_video_ready(user_id, video_url, project_id, sb_url, sb_key):
    if not BREVO_API_KEY: return
    headers_sb = {'apikey': sb_key, 'Authorization': f'Bearer {sb_key}', 'Content-Type': 'application/json'}
    email = None
    try:
        r = requests.get(f"{sb_url}/auth/v1/admin/users/{user_id}", headers=headers_sb, timeout=10)
        print(f"  [NOTIF] auth: {r.status_code}")
        if r.ok: email = r.json().get('email')
    except: pass

    if not email: return

    first_name = 'là'
    try:
        rp = requests.get(f"{sb_url}/rest/v1/profiles?id=eq.{user_id}&select=first_name", headers=headers_sb, timeout=10)
        if rp.ok and rp.json(): first_name = rp.json()[0].get('first_name') or 'là'
    except: pass

    desc = 'Ton produit'
    try:
        rj = requests.get(f"{sb_url}/rest/v1/projects?id=eq.{project_id}&select=product_description", headers=headers_sb, timeout=10)
        if rj.ok and rj.json():
            raw = rj.json()[0].get('product_description') or ''
            desc = raw.replace('#','').replace('*','').replace('`','')[:80]
    except: pass

    html = f"""<div style="background:#050508;padding:40px;font-family:system-ui;color:white;max-width:520px;margin:0 auto;border-radius:20px">
  <div style="text-align:center;margin-bottom:24px">
    <div style="background:linear-gradient(135deg,#6366f1,#a855f7);display:inline-block;padding:10px 20px;border-radius:12px">
      <span style="color:white;font-size:18px;font-weight:900">⚡ Ad Machine</span>
    </div>
  </div>
  <div style="background:#0d0d14;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:28px;text-align:center">
    <div style="font-size:44px;margin-bottom:10px">🎬</div>
    <h1 style="color:white;font-size:22px;font-weight:900;margin:0 0 8px">Ta pub est prête !</h1>
    <p style="color:rgba(255,255,255,0.5);font-size:14px;margin:0 0 16px">Bonjour {first_name}, ta vidéo publicitaire vient d'être générée.</p>
    <div style="background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.2);border-radius:10px;padding:10px;margin-bottom:20px">
      <p style="color:rgba(255,255,255,0.5);font-size:11px;margin:0 0 3px;text-transform:uppercase">Produit</p>
      <p style="color:white;font-size:13px;margin:0">{desc}</p>
    </div>
    <a href="{video_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#a855f7);color:white;text-decoration:none;font-weight:700;font-size:15px;padding:14px 36px;border-radius:12px">⬇️ Télécharger ma pub</a>
    <p style="margin-top:16px"><a href="https://admachine.io/dashboard" style="color:#6366f1;text-decoration:none;font-size:12px">Voir mon tableau de bord →</a></p>
  </div>
  <p style="text-align:center;color:rgba(255,255,255,0.15);font-size:11px;margin-top:16px">Ad Machine · admachine.io</p>
</div>"""

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
    except Exception as e:
        print(f"  [NOTIF] Brevo exception: {e}")


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, user_id, app_url, sb, sb_url=None, sb_key=None):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] START {duration}s {len(video_urls)} videos vfx={vfx} captions={with_captions} free={is_free}")

        clips_needed = math.ceil(duration / 3.0) + 2
        nb_videos = len(video_urls)
        clips_per_video = max(1, min(3, math.ceil(clips_needed / max(nb_videos, 1)) + 1))
        print(f"  Plan: {nb_videos} vidéos × {clips_per_video} clips/vidéo pour {duration}s")

        # 1. EXTRAIRE CLIPS
        clips_by_video = []
        for i, url in enumerate(video_urls):
            src = f"{tmp}/src_{i}.mp4"
            try:
                dl(url, src)
                src_dur = get_duration(src)
                print(f"  video {i+1} downloaded ({src_dur:.1f}s)")
                clips = []

                if src_dur <= 3.0:
                    positions = [0.0]
                else:
                    # Calculer combien de clips on peut vraiment extraire de cette vidéo
                    max_possible = max(1, int(src_dur / 2.5))  # 1 clip toutes les 2.5s
                    actual_clips = min(clips_per_video, max_possible)
                    # Diviser la vidéo en segments égaux et prendre 1 position par segment
                    # → garantit que toute la vidéo est couverte sans répétition
                    segment_size = src_dur / actual_clips
                    positions = []
                    for seg in range(actual_clips):
                        seg_start = seg * segment_size
                        seg_end = min(seg_start + segment_size - 3.0, src_dur - 3.0)
                        if seg_end > seg_start:
                            pos = round(random.uniform(seg_start, seg_end), 2)
                        else:
                            pos = max(0.0, round(seg_start, 2))
                        positions.append(pos)
                    print(f"  video {i+1}: {len(positions)} positions sur {src_dur:.1f}s")

                for c_idx, start in enumerate(positions):
                    if start + 1.0 > src_dur:
                        continue
                    cd = min(3.0, src_dur - start)
                    out = f"{tmp}/v{i}_c{c_idx:03d}.mp4"
                    r = subprocess.run([
                        'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30',
                        '-r', '30', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                        '-pix_fmt', 'yuv420p', '-avoid_negative_ts', 'make_zero', '-an', out
                    ], capture_output=True)
                    if r.returncode == 0:
                        clips.append(out)
                        print(f"    clip {c_idx+1}: t={start:.1f}s ({cd:.1f}s)")

                if clips:
                    clips_by_video.append(clips)
                    print(f"  video {i+1}: {len(clips)} clips extraits")
                try: os.remove(src)
                except: pass
            except Exception as e:
                print(f"  SKIP video {i+1}: {e}")

        if not clips_by_video: raise Exception("No clips extracted")

        voice_path = None
        music_path = None
        cut_points = []

        # 2. ASSEMBLER — ── FIX ANTI-BOUCLE ──
        interleaved = interleave_clips(clips_by_video)
        needed = math.ceil(duration / 3.0)
        all_clips = list(interleaved)
        random.shuffle(all_clips)

        total_available = len(all_clips)
        # ── JAMAIS recycler les clips — chaque clip utilisé UNE SEULE FOIS ──
        max_usable = min(needed, total_available)

        selected = []
        last_video = None
        remaining = list(all_clips)  # pool SANS remise

        for _ in range(max_usable):
            if not remaining:
                break
            found = False
            for i, clip in enumerate(remaining):
                clip_video = os.path.basename(clip).split('_c')[0]
                if clip_video != last_video or len(clips_by_video) == 1:
                    selected.append(clip)
                    last_video = clip_video
                    remaining.pop(i)
                    found = True
                    break
            if not found and remaining:
                selected.append(remaining.pop(0))

        if len(selected) < needed:
            print(f"  INFO: seulement {len(selected)} clips disponibles pour {duration}s — pas de répétition")

        videos_used = len(set(os.path.basename(s).split('_c')[0] for s in selected))
        print(f"  {len(selected)} clips de {videos_used}/{len(clips_by_video)} vidéos — alternance OK (sans répétition)")

        # Sync voix
        if voice_path and os.path.exists(voice_path):
            voice_dur_for_cuts = get_duration(voice_path)
            cut_points = detect_voice_cuts(voice_path, voice_dur_for_cuts)
            seg_starts = [0.0] + cut_points
            seg_durations = []
            for j in range(len(selected)):
                if j < len(cut_points):
                    seg_dur = round(cut_points[j] - seg_starts[j], 2)
                else:
                    seg_dur = round(voice_dur_for_cuts - seg_starts[min(j, len(seg_starts)-1)], 2)
                seg_dur = max(0.5, min(6.0, seg_dur))
                seg_durations.append(seg_dur)

            synced_clips = []
            for idx, (clip_path, seg_dur) in enumerate(zip(selected, seg_durations)):
                synced = f"{tmp}/synced_{idx:03d}.mp4"
                r = subprocess.run([
                    'ffmpeg', '-y', '-i', clip_path, '-t', str(seg_dur),
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                    '-pix_fmt', 'yuv420p', '-r', '30', '-an', synced
                ], capture_output=True)
                synced_clips.append(synced if r.returncode == 0 else clip_path)
            selected = synced_clips
        else:
            print(f"  Pas de voix → clips durée standard 3s")

        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for clip in selected: f.write(f"file '{clip}'\n")

        assembled = f"{tmp}/assembled.mp4"
        res_asm = subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-r', '30', '-vsync', 'cfr', assembled
        ], capture_output=True, text=True)
        if res_asm.returncode != 0:
            raise Exception(f"Assemblage échoué: {res_asm.stderr[-200:]}")
        asm_dur = get_duration(assembled)
        print(f"  assembled OK ({asm_dur:.1f}s)")

        for clips in clips_by_video:
            for c in clips:
                try: os.remove(c)
                except: pass

        # 3. VOIX + MUSIQUE
        import re as _re
        voiceover = _re.sub(r'^[#\s\*]*[^\n]{0,60}\n', '', voiceover).strip()
        voiceover = _re.sub(r'[#\*`]', '', voiceover).strip()
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
                actual_duration = get_duration(voice_path)
                print(f"  voice duration={actual_duration:.1f}s (target={duration}s)")
            except: pass

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += [
                '-filter_complex', '[1:a]aresample=44100,asetpts=PTS-STARTPTS[aout]',
                '-map', '0:v', '-map', '[aout]',
                '-c:a', 'aac', '-b:a', '192k', '-ar', '44100'
            ]
        elif n == 2 and music_path:
            cmd += ['-filter_complex',
                    f'[1:a]aresample=44100,volume=0.10,atrim=0:{actual_duration},asetpts=PTS-STARTPTS[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]aresample=44100,asetpts=PTS-STARTPTS[v];'
                    f'[2:a]aresample=44100,volume=0.08,atrim=0:{actual_duration},asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100']

        cmd += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                '-r', '30', '-t', str(actual_duration), output]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            raise Exception(f"FFmpeg mix: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  mix OK ({size_mb:.1f}MB)")
        clean_output = output

        try: os.remove(assembled)
        except: pass

        # 5. VFX
        if vfx:
            vfx_output = apply_vfx(output, tmp, actual_duration, cut_points=cut_points if cut_points else None)
            if vfx_output != output:
                output = vfx_output

        # 6. SUBMAGIC
        submagic_url = submagic_process(output, pid, style, use_vfx_transitions=vfx) if with_captions else None

        video_final = output
        if submagic_url:
            print(f"  Downloading Submagic output...")
            try:
                sm_local = f"{tmp}/submagic_out.mp4"
                dl(submagic_url, sm_local)
                sm_size = os.path.getsize(sm_local) if os.path.exists(sm_local) else 0
                print(f"  Submagic size: {sm_size/1024/1024:.1f}MB")
                if sm_size > 500_000:
                    probe = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', sm_local], capture_output=True, text=True, timeout=15)
                    if probe.returncode == 0 and 'video' in probe.stdout:
                        video_final = sm_local
                        print("  Submagic OK")
                    else:
                        video_final = clean_output
                else:
                    video_final = clean_output
            except Exception as e:
                print(f"  Submagic error: {e}")
                video_final = clean_output

        # 7. FILIGRANE
        print(f"  Applying watermark (is_free={is_free})...")
        if is_free:
            video_final = add_watermark(video_final, tmp, duration, is_free)

        # 8. UPLOAD
        filename = f"renders/{pid}/ad_machine_{pid[:8]}.mp4"
        print(f"  Uploading to Supabase...")
        with open(video_final, 'rb') as f: video_bytes = f.read()
        file_size_mb = len(video_bytes) / 1024 / 1024
        print(f"  File size: {file_size_mb:.1f}MB")

        if len(video_bytes) < 500_000:
            print(f"  WARN: fichier trop petit — fallback clean_output")
            try:
                with open(clean_output, 'rb') as f: video_bytes = f.read()
                file_size_mb = len(video_bytes) / 1024 / 1024
            except: pass

        if file_size_mb > 45:
            print(f"  Compression ({file_size_mb:.1f}MB → max 40MB)...")
            compressed = f"{tmp}/compressed.mp4"
            vid_dur = get_duration(video_final) if os.path.exists(video_final) else actual_duration
            target_bitrate = max(800, min(int((40 * 8 * 1024) / vid_dur), 2500))
            print(f"  Target bitrate: {target_bitrate}kbps")
            res_comp = subprocess.run([
                'ffmpeg', '-y', '-i', video_final,
                '-c:v', 'libx264', '-b:v', f'{target_bitrate}k',
                '-preset', 'fast', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', compressed
            ], capture_output=True, text=True, timeout=300)
            if res_comp.returncode == 0 and os.path.exists(compressed):
                with open(compressed, 'rb') as f: video_bytes = f.read()
                file_size_mb = len(video_bytes) / 1024 / 1024
                print(f"  Compressed: {file_size_mb:.1f}MB")

        upload_ok = False
        for attempt in range(3):
            try:
                sb.upload('videos', filename, video_bytes)
                upload_ok = True
                print(f"  Upload OK attempt {attempt+1} ({file_size_mb:.1f}MB)")
                break
            except Exception as e:
                print(f"  Upload attempt {attempt+1} failed: {e}")
                if attempt < 2: time.sleep(5)

        if not upload_ok:
            try:
                filename = f"renders/{pid}/ad_{int(time.time())}.mp4"
                sb.upload('videos', filename, video_bytes)
                upload_ok = True
            except Exception as e:
                raise Exception(f"Upload Supabase échoué: {e}")

        final_url = sb.public_url('videos', filename)
        print(f"  URL: {final_url[:80]}")
        try:
            check = requests.head(final_url, timeout=10)
            print(f"  URL check: {check.status_code}")
        except: pass

        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})
        print(f"  Supabase updated: video_url + status=done")

        if user_id and sb_url and sb_key:
            def send_notif():
                try: notify_user_video_ready(user_id, final_url, pid, sb_url, sb_key)
                except: pass
            threading.Thread(target=send_notif, daemon=True).start()

        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
