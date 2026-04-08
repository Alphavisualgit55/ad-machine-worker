import os, json, math, subprocess, tempfile, requests, traceback, threading, time, random
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUBMAGIC_KEY = 'sk-65c7ec039cc99e9f86333a018e208550f8b4f9725dfe80e8a8d2103ad53aed0f'
SUBMAGIC_URL = 'https://api.submagic.co/v1'
FILM_BURN_URL = os.environ.get('FILM_BURN_URL', '')
# Filigrane Ad Machine (image PNG encodée en base64)
WATERMARK_B64 = "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"


@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Ad Machine Worker', 'status': 'running'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'ffmpeg': 'ok', 'film_burn': bool(FILM_BURN_URL)})

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
    pid        = data.get('projectId')
    video_urls = data.get('videoUrls', [])
    voice_url  = data.get('voiceUrl')
    music_url  = data.get('musicUrl')
    voiceover  = data.get('voiceover', '')
    duration   = int(data.get('duration', 30))
    style      = data.get('captionStyle', 'Hormozi 2')
    vfx        = data.get('vfx', False)
    is_free    = data.get('isFree', True)
    sb_url     = data.get('supabaseUrl')
    sb_key     = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Donnees manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, sb)
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

def get_dur(path):
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
    """
    Filigrane image Ad Machine coloré — plan gratuit uniquement.
    Gravé 3 fois en diagonale dans la vidéo, impossible à supprimer.
    Plan payant = aucun filigrane.
    """
    if not is_free:
        print("  Watermark skipped (paid plan)")
        return video_path

    import base64
    output = f"{tmp}/watermarked.mp4"

    # Décoder et sauvegarder l'image filigrane
    wm_path = f"{tmp}/watermark.png"
    with open(wm_path, 'wb') as f:
        f.write(base64.b64decode(WATERMARK_B64))

    # Overlay image 3x en diagonale avec opacité
    # Position 1 : haut gauche
    # Position 2 : centre
    # Position 3 : bas droite
    wm_esc = wm_path.replace(':', '\\:')

    overlay_filter = (
        f"[1:v]scale=360:90[wm];"
        f"[0:v][wm]overlay=x=60:y=120:format=auto[v1];"
        f"[wm]format=rgba,colorchannelmixer=aa=0.45[wm2];"
        f"[v1][wm2]overlay=x=(W-w)/2:y=(H-h)/2:format=auto[v2];"
        f"[wm]format=rgba,colorchannelmixer=aa=0.30[wm3];"
        f"[v2][wm3]overlay=x=W-w-60:y=H-h-150:format=auto[vout]"
    )

    res = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', wm_path,
        '-filter_complex', overlay_filter,
        '-map', '[vout]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
        '-c:a', 'copy',
        '-movflags', '+faststart', '-t', str(duration), output
    ], capture_output=True, text=True, timeout=120)

    if res.returncode != 0:
        print(f"  Watermark error: {res.stderr[-400:]}")
        # Fallback texte simple
        wm_filter = (
            "drawtext=text='Ad Machine':"
            "fontsize=48:fontcolor=white@0.40:"
            "x=(w-text_w)/2:y=(h-text_h)/2:"
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        )
        res2 = subprocess.run([
            'ffmpeg', '-y', '-i', video_path,
            '-vf', wm_filter,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-c:a', 'copy', '-t', str(duration), output
        ], capture_output=True, text=True, timeout=120)
        if res2.returncode != 0:
            return video_path

    print("  Watermark image added (free plan) OK")
    return output


def apply_vfx(video_path, tmp, duration, film_burn_path):
    """
    Film burn : prend la partie GAUCHE de l'effet, agrandie en plein écran
    Overlay en mode screen à opacité 100%
    + Glitch RGB après chaque burn
    + Sons synchronisés
    """
    try:
        burn_dur = min(get_dur(film_burn_path), 2.0)
        output = f"{tmp}/vfx.mp4"

        margin = max(2.0, duration * 0.15)
        n_burns = random.randint(2, 3)
        positions = []
        attempts = 0
        while len(positions) < n_burns and attempts < 100:
            t = round(random.uniform(margin, duration - margin - burn_dur), 1)
            if all(abs(t - p) > 4.0 for p in positions):
                positions.append(t)
            attempts += 1
        positions.sort()
        print(f"  VFX burns at: {positions}s")

        # Préparer le film burn :
        # 1. Prendre la moitié gauche (crop w/2:h:0:0)
        # 2. Agrandir en plein écran 1080x1920
        # 3. Mode screen pour rendre le noir transparent
        burn_prep = f"{tmp}/burn_prep.mp4"
        r = subprocess.run([
            'ffmpeg', '-y', '-i', film_burn_path,
            '-t', str(burn_dur),
            '-vf', (
                'crop=iw/2:ih:0:0,'             # Partie gauche seulement
                'scale=1080:1920:force_original_aspect_ratio=increase,'
                'crop=1080:1920'                 # Centrer après scale
            ),
            '-pix_fmt', 'yuv420p',
            '-c:v', 'libx264', '-preset', 'ultrafast',
            burn_prep
        ], capture_output=True)

        if r.returncode != 0:
            print("  VFX burn prep error")
            return video_path

        # Construire filter_complex
        # blend=screen à 100% : les pixels noirs disparaissent, les pixels clairs s'ajoutent
        fc_parts = []
        for i, t in enumerate(positions):
            t2 = round(t + burn_dur, 2)
            in_label = f'[tmp{i-1}]' if i > 0 else '[0:v]'
            out_label = f'[tmp{i}]' if i < len(positions) - 1 else '[vburn]'
            part = (
                f"{in_label}[{i+1}:v]"
                f"blend=all_mode=screen:all_opacity=1.0:"
                f"enable='between(t,{t},{t2})'"
                f"{out_label}"
            )
            fc_parts.append(part)

        # Glitch RGB : décalage horizontal des canaux rouge/bleu — vrai effet glitch
        glitch = []
        for t in positions:
            gt = round(t + burn_dur + 0.15, 1)
            gt2 = round(gt + 0.06, 2)
            gt3 = round(gt + 0.12, 2)
            if gt3 < duration:
                # Décale légèrement la luminosité — effet scan line
                glitch.append(
                    f"curves=all='0/0 0.5/0.45 1/1':enable='between(t,{gt},{gt2})'"
                )
                glitch.append(
                    f"curves=all='0/0 0.5/0.55 1/1':enable='between(t,{gt2},{gt3})'"
                )

        if glitch:
            fc_parts.append(f'[vburn]{",".join(glitch)}[vout]')
        else:
            fc_parts.append('[vburn]copy[vout]')

        filter_complex = ';'.join(fc_parts)

        # Extraire audio burns pour effets sonores
        burn_audio = f"{tmp}/burn_audio.wav"
        subprocess.run([
            'ffmpeg', '-y', '-i', film_burn_path,
            '-t', str(burn_dur), '-vn', '-c:a', 'pcm_s16le', burn_audio
        ], capture_output=True)
        has_audio = os.path.exists(burn_audio) and os.path.getsize(burn_audio) > 1000

        cmd = ['ffmpeg', '-y', '-i', video_path]
        for _ in positions:
            cmd += ['-i', burn_prep]

        if has_audio:
            sp = []
            offset = len(positions) + 1
            for i, t in enumerate(positions):
                cmd += ['-i', burn_audio]
                delay_ms = int(t * 1000)
                sp.append(f'[{offset+i}:a]adelay={delay_ms}|{delay_ms}[bs{i}]')
            n = len(positions)
            mix = ''.join(f'[bs{i}]' for i in range(n))
            sp.append(f'[0:a]{mix}amix=inputs={n+1}:duration=first:normalize=0[aout]')
            full_fc = filter_complex + ';' + ';'.join(sp)
            cmd += [
                '-filter_complex', full_fc,
                '-map', '[vout]', '-map', '[aout]',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-b:a', '192k',
                '-movflags', '+faststart', '-r', '30', '-t', str(duration), output
            ]
        else:
            cmd += [
                '-filter_complex', filter_complex,
                '-map', '[vout]', '-map', '0:a',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'copy',
                '-movflags', '+faststart', '-r', '30', '-t', str(duration), output
            ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            print(f"  VFX error: {res.stderr[-300:]}")
            return video_path

        print("  VFX applied OK")
        return output

    except Exception as e:
        print(f"  VFX exception (skipping): {e}")
        return video_path


def submagic_process(video_path, pid, template):
    headers_sm = {'x-api-key': SUBMAGIC_KEY}
    valid = ['Hormozi 2', 'Hormozi 1', 'Hormozi 3', 'Hormozi 4', 'Hormozi 5',
             'Beast', 'Sara', 'Karl', 'Ella', 'Matt', 'Jess', 'Nick', 'Laura',
             'Daniel', 'Dan', 'Devin', 'Tayo', 'Jason', 'Noah']
    if template not in valid:
        template = 'Hormozi 2'

    print(f"  [SM] Upload template={template}")
    try:
        with open(video_path, 'rb') as f:
            resp = requests.post(
                f'{SUBMAGIC_URL}/projects/upload',
                headers=headers_sm,
                files={'file': ('video.mp4', f, 'video/mp4')},
                data={
                    'title': f'AdMachine-{pid[:8]}',
                    'language': 'fr',
                    'templateName': template,
                    'magicZooms': 'true',
                    'removeSilencePace': 'natural',
                },
                timeout=180
            )
    except Exception as e:
        print(f"  [SM] Error: {e}")
        return None

    print(f"  [SM] Upload: {resp.status_code}")
    if not resp.ok: return None

    sm_id = resp.json().get('id')
    print(f"  [SM] ID: {sm_id}")

    for i in range(60):
        time.sleep(5)
        r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
        if not r.ok: continue
        proj = r.json()
        status = proj.get('status')
        trans = proj.get('transcriptionStatus')
        print(f"  [SM] [{i+1}] {status} / {trans}")
        if status == 'failed': return None
        if trans == 'COMPLETED': break

    exp = requests.post(
        f'{SUBMAGIC_URL}/projects/{sm_id}/export',
        headers={**headers_sm, 'Content-Type': 'application/json'},
        json={'width': 1080, 'height': 1920, 'fps': 30}, timeout=30
    )
    print(f"  [SM] Export: {exp.status_code}")
    if not exp.ok: return None

    for i in range(120):
        time.sleep(5)
        r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
        if not r.ok: continue
        proj = r.json()
        status = proj.get('status')
        url = proj.get('directUrl') or proj.get('downloadUrl')
        if i % 6 == 0: print(f"  [SM] [{i+1}] {status}")
        if status == 'completed' and url:
            print(f"  [SM] Done!")
            return url
        if status == 'failed':
            print(f"  [SM] Failed: {proj.get('failureReason')}")
            return None

    print("  [SM] Timeout")
    return None


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, sb):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] START {duration}s {len(video_urls)} videos style={style} vfx={vfx} free={is_free}")

        clips_needed = math.ceil(duration / 3.0) + 2
        clips_per_video = math.ceil(clips_needed / max(len(video_urls), 1)) + 2

        # 1. TÉLÉCHARGER ET EXTRAIRE CLIPS
        clips_by_video = []
        for i, url in enumerate(video_urls[:8]):
            src = f"{tmp}/src_{i}.mp4"
            try:
                dl(url, src)
                print(f"  video {i+1} downloaded")
                clips = []
                src_dur = get_dur(src)
                start = 0.0; c_idx = 0
                while start + 1.5 <= src_dur and c_idx < clips_per_video:
                    out = f"{tmp}/v{i}_c{c_idx:03d}.mp4"
                    cd = min(3.0, src_dur - start)
                    r = subprocess.run([
                        'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                        '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-an', out
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

        # 2. INTERLEAVE + ASSEMBLER
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
            '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print("  assembled OK")

        for clips in clips_by_video:
            for c in clips:
                try: os.remove(c)
                except: pass

        # 3. VOIX + MUSIQUE
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

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += ['-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-t', str(duration)]
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{duration}[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]asetpts=PTS-STARTPTS[v];[2:a]volume=0.10,asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']

        cmd += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-movflags', '+faststart', '-r', '30', '-t', str(duration), output]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise Exception(f"FFmpeg mix: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  mix OK ({size_mb:.1f}MB)")
        try: os.remove(assembled)
        except: pass

        # 5. VFX (optionnel)
        if vfx and FILM_BURN_URL:
            try:
                film_burn_path = f"{tmp}/film_burn.mp4"
                dl(FILM_BURN_URL, film_burn_path)
                print("  Film burn downloaded")
                output = apply_vfx(output, tmp, duration, film_burn_path)
            except Exception as e:
                print(f"  VFX error (skipping): {e}")
        elif vfx:
            print("  VFX skipped: FILM_BURN_URL not set")

        # 6. FILIGRANE PERMANENT — gravé avant Submagic
        # Comme ça le filigrane est présent même sur la vidéo Submagic téléchargée
        output = add_watermark(output, tmp, duration, is_free)

        # 7. SUBMAGIC
        final_url = submagic_process(output, pid, style)

        if final_url:
            sb.update_video(pid, {'video_url': final_url})
            sb.update_project(pid, {'status': 'done'})
            return final_url

        # Fallback Supabase
        print("  Fallback Supabase...")
        filename = f"renders/{pid}/final.mp4"
        with open(output, 'rb') as f: video_bytes = f.read()
        sb.upload('videos', filename, video_bytes)
        final_url = sb.public_url('videos', filename)
        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})
        print("  Upload OK")
        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
