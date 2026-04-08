import os, json, math, subprocess, tempfile, requests, traceback, threading, time, random, base64
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUBMAGIC_KEY = 'sk-65c7ec039cc99e9f86333a018e208550f8b4f9725dfe80e8a8d2103ad53aed0f'
SUBMAGIC_URL = 'https://api.submagic.co/v1'
FILM_BURN_URL = os.environ.get('FILM_BURN_URL', '')

# Filigrane Ad Machine encodé en base64
WATERMARK_B64 = "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"

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
    sb_url       = data.get('supabaseUrl')
    sb_key       = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Donnees manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, sb)
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


def create_film_burn(tmp, duration):
    """
    Crée un effet film burn original avec FFmpeg uniquement.
    Pas de fichier externe nécessaire.
    Flash orange/ambre sur fond noir qui simule une brûlure de film.
    """
    burn_path = f"{tmp}/burn_effect.mp4"
    # Générer 2 secondes d'effet film burn avec des formes organiques
    r = subprocess.run([
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', (
            'color=c=black:size=1080x1920:rate=30,'
            'geq='
            'r=\'clip(255*pow(sin(PI*T/0.5),2)*pow(sin(PI*X/W),0.3),0,255)\':'
            'g=\'clip(120*pow(sin(PI*T/0.5),2)*pow(sin(PI*X/W),0.3),0,255)\':'
            'b=\'clip(10*pow(sin(PI*T/0.5),2),0,255)\':'
            'a=255'
        ),
        '-t', '1.5',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
        burn_path
    ], capture_output=True)

    if r.returncode != 0:
        # Fallback simple si geq ne marche pas
        r2 = subprocess.run([
            'ffmpeg', '-y',
            '-f', 'lavfi',
            '-i', 'color=c=orange:size=1080x1920:rate=30',
            '-t', '0.8',
            '-vf', 'fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st=0.6:d=0.2:alpha=1',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
            burn_path
        ], capture_output=True)
        if r2.returncode != 0:
            return None

    return burn_path


def create_whoosh_sound(tmp, duration_s=0.4):
    """Génère un son whoosh pour accompagner le film burn"""
    sound_path = f"{tmp}/whoosh.wav"
    r = subprocess.run([
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', f'sine=frequency=600:duration={duration_s}',
        '-af', (
            f'afade=t=in:st=0:d=0.05,'
            f'afade=t=out:st={duration_s-0.1}:d=0.1,'
            f'aecho=0.6:0.3:50:0.4,'
            f'volume=0.6'
        ),
        sound_path
    ], capture_output=True)
    return sound_path if r.returncode == 0 else None


def add_watermark(video_path, tmp, duration, is_free):
    """Filigrane image Ad Machine — plan gratuit uniquement"""
    if not is_free:
        print("  Watermark skipped (paid plan)")
        return video_path

    output = f"{tmp}/watermarked.mp4"
    wm_path = f"{tmp}/watermark.png"

    try:
        with open(wm_path, 'wb') as f:
            f.write(base64.b64decode(WATERMARK_B64))
    except Exception as e:
        print(f"  Watermark decode error: {e}")
        return video_path

    # 1 seul filigrane image centré au milieu
    res = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', wm_path,
        '-filter_complex',
        '[1:v]scale=380:95[wm];[0:v][wm]overlay=(W-w)/2:(H-h)/2:format=auto[vout]',
        '-map', '[vout]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
        '-c:a', 'copy',
        '-movflags', '+faststart', '-t', str(duration), output
    ], capture_output=True, text=True, timeout=300)

    if res.returncode != 0:
        print(f"  Watermark error: {res.stderr[-200:]}")
        return video_path

    print("  Watermark added (free) OK")
    return output


def apply_vfx(video_path, tmp, duration):
    """
    Film burn généré par Ad Machine (pas de fichier externe).
    Effet sonore whoosh synchronisé.
    2-3 burns à des moments aléatoires.
    """
    output = f"{tmp}/vfx.mp4"

    # Créer le film burn
    burn_path = create_film_burn(tmp, duration)
    if not burn_path:
        print("  VFX: could not create burn effect")
        return video_path

    burn_dur = min(get_dur(burn_path), 1.5)

    # Positions aléatoires bien espacées
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

    # Créer le son whoosh
    whoosh_path = create_whoosh_sound(tmp)

    # Construire filter_complex
    # blend=screen : fond noir devient transparent, feu reste visible
    fc_parts = []
    for i, t in enumerate(positions):
        t2 = round(t + burn_dur, 2)
        in_v = f'[tmp{i-1}]' if i > 0 else '[0:v]'
        out_v = f'[tmp{i}]' if i < len(positions) - 1 else '[vout]'
        fc_parts.append(
            f'[{i+1}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setpts=PTS-STARTPTS[b{i}];'
            f'{in_v}[b{i}]blend=all_mode=screen:all_opacity=1.0:enable=\'between(t,{t},{t2})\'{out_v}'
        )

    filter_complex = ';'.join(fc_parts)

    # Inputs vidéo
    cmd = ['ffmpeg', '-y', '-i', video_path]
    for _ in positions:
        cmd += ['-i', burn_path]

    # Ajouter sons whoosh si disponible
    if whoosh_path:
        sound_parts = []
        offset = len(positions) + 1
        for i, t in enumerate(positions):
            cmd += ['-i', whoosh_path]
            delay_ms = int(t * 1000)
            sound_parts.append(f'[{offset+i}:a]adelay={delay_ms}|{delay_ms}[ws{i}]')
        n = len(positions)
        mix = ''.join(f'[ws{i}]' for i in range(n))
        sound_parts.append(f'[0:a]{mix}amix=inputs={n+1}:duration=first:normalize=0[aout]')
        full_fc = filter_complex + ';' + ';'.join(sound_parts)
        cmd += [
            '-filter_complex', full_fc,
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', '-r', '30', '-t', str(duration), output
        ]
    else:
        cmd += [
            '-filter_complex', filter_complex,
            '-map', '[vout]', '-map', '0:a',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
            '-c:a', 'copy',
            '-movflags', '+faststart', '-r', '30', '-t', str(duration), output
        ]

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        print(f"  VFX error: {res.stderr[-300:]}")
        return video_path

    print("  VFX applied OK")
    return output


def submagic_process(video_path, pid, template):
    headers_sm = {'x-api-key': SUBMAGIC_KEY}
    valid = ['Hormozi 2','Hormozi 1','Hormozi 3','Hormozi 4','Hormozi 5',
             'Beast','Sara','Karl','Ella','Matt','Jess','Nick','Laura',
             'Daniel','Dan','Devin','Tayo','Jason','Noah']
    if template not in valid:
        template = 'Hormozi 2'

    print(f"  [SM] Upload template={template}")
    try:
        with open(video_path, 'rb') as f:
            resp = requests.post(
                f'{SUBMAGIC_URL}/projects/upload',
                headers=headers_sm,
                files={'file': ('video.mp4', f, 'video/mp4')},
                data={'title': f'AdMachine-{pid[:8]}', 'language': 'fr',
                      'templateName': template, 'magicZooms': 'true',
                      'removeSilencePace': 'natural'},
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
        print(f"  [SM] [{i+1}] {status}/{trans}")
        if status == 'failed': return None
        if trans == 'COMPLETED': break

    exp = requests.post(f'{SUBMAGIC_URL}/projects/{sm_id}/export',
        headers={**headers_sm, 'Content-Type': 'application/json'},
        json={'width': 1080, 'height': 1920, 'fps': 30}, timeout=30)
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


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, sb):
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
                src_dur = get_dur(src)
                start = 0.0; c_idx = 0
                while start + 1.5 <= src_dur and c_idx < clips_per_video:
                    out = f"{tmp}/v{i}_c{c_idx:03d}.mp4"
                    cd = min(3.0, src_dur - start)
                    r = subprocess.run([
                        'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                        '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-an', out
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
            '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-r', '30',
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

        cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
                '-movflags', '+faststart', '-r', '30', '-t', str(duration), output]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            raise Exception(f"FFmpeg mix: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  mix OK ({size_mb:.1f}MB)")
        try: os.remove(assembled)
        except: pass

        # 5. VFX — film burn généré par Ad Machine + son whoosh
        if vfx:
            try:
                output = apply_vfx(output, tmp, duration)
            except Exception as e:
                print(f"  VFX error (skipping): {e}")

        # 6. FILIGRANE — 1 seul, image Ad Machine, au centre
        output = add_watermark(output, tmp, duration, is_free)

        # 7. SUBMAGIC captions (optionnel)
        submagic_url = submagic_process(output, pid, style) if with_captions else None
        if not with_captions:
            print("  Captions skipped by user")

        if submagic_url:
            if is_free:
                # Re-télécharger et re-appliquer filigrane sur vidéo Submagic
                try:
                    sm_local = f"{tmp}/submagic_out.mp4"
                    dl(submagic_url, sm_local)
                    sm_wm = add_watermark(sm_local, tmp, duration, is_free)
                    filename = f"renders/{pid}/final.mp4"
                    with open(sm_wm, 'rb') as f: video_bytes = f.read()
                    sb.upload('videos', filename, video_bytes)
                    final_url = sb.public_url('videos', filename)
                    print("  Submagic+watermark uploaded OK")
                except Exception as e:
                    print(f"  Re-watermark error: {e}")
                    filename = f"renders/{pid}/final.mp4"
                    with open(output, 'rb') as f: video_bytes = f.read()
                    sb.upload('videos', filename, video_bytes)
                    final_url = sb.public_url('videos', filename)
            else:
                # Plan payant — upload Submagic sur Supabase sans filigrane
                try:
                    sm_local = f"{tmp}/submagic_out.mp4"
                    dl(submagic_url, sm_local)
                    filename = f"renders/{pid}/final.mp4"
                    with open(sm_local, 'rb') as f: video_bytes = f.read()
                    sb.upload('videos', filename, video_bytes)
                    final_url = sb.public_url('videos', filename)
                    print("  Submagic uploaded to Supabase OK")
                except Exception as e:
                    print(f"  Upload error: {e}")
                    final_url = submagic_url

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
