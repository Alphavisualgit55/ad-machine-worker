import os, json, math, subprocess, tempfile, requests, traceback, threading, time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUBMAGIC_KEY = 'sk-65c7ec039cc99e9f86333a018e208550f8b4f9725dfe80e8a8d2103ad53aed0f'
SUBMAGIC_URL = 'https://api.submagic.co/v1'

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
    pid        = data.get('projectId')
    video_urls = data.get('videoUrls', [])
    voice_url  = data.get('voiceUrl')
    music_url  = data.get('musicUrl')
    voiceover  = data.get('voiceover', '')
    duration   = int(data.get('duration', 30))
    style      = data.get('captionStyle', 'Hormozi 2')
    sb_url     = data.get('supabaseUrl')
    sb_key     = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Données manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb)
            print(f"[{pid}] DONE: {url[:60]}")
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


def submagic_process(video_path, pid, template):
    """
    Flow exact Submagic :
    1. Upload fichier → obtenir project ID
    2. Attendre transcriptionStatus = COMPLETED
    3. Déclencher export
    4. Poll jusqu'à status = completed
    5. Retourner directUrl
    """
    headers_sm = {'x-api-key': SUBMAGIC_KEY}

    # Templates valides Submagic (depuis la doc)
    valid_templates = ['Hormozi 2', 'Hormozi 1', 'Hormozi 3', 'Hormozi 4', 'Hormozi 5',
                       'Beast', 'Sara', 'Karl', 'Ella', 'Matt', 'Jess', 'Nick',
                       'Laura', 'Daniel', 'Dan', 'Devin', 'Tayo', 'Jason', 'Noah']
    if template not in valid_templates:
        template = 'Hormozi 2'

    print(f"  [SM] Upload → template={template}")

    # 1. UPLOAD FICHIER
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
                },
                timeout=180
            )
    except Exception as e:
        print(f"  [SM] Upload error: {e}")
        return None

    print(f"  [SM] Upload: {resp.status_code} {resp.text[:200]}")
    if not resp.ok:
        return None

    sm_id = resp.json().get('id')
    print(f"  [SM] Project: {sm_id}")

    # 2. ATTENDRE TRANSCRIPTION
    print(f"  [SM] Waiting transcription...")
    for i in range(60):
        time.sleep(5)
        r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
        if not r.ok: continue
        proj = r.json()
        status = proj.get('status')
        transcription = proj.get('transcriptionStatus')
        print(f"  [SM] [{i+1}] status={status} trans={transcription}")
        if status == 'failed':
            print(f"  [SM] Failed: {proj.get('failureReason')}")
            return None
        if transcription == 'COMPLETED':
            print(f"  [SM] Transcription OK")
            break

    # 3. DÉCLENCHER EXPORT
    print(f"  [SM] Triggering export...")
    exp = requests.post(
        f'{SUBMAGIC_URL}/projects/{sm_id}/export',
        headers={**headers_sm, 'Content-Type': 'application/json'},
        json={'width': 1080, 'height': 1920, 'fps': 30},
        timeout=30
    )
    print(f"  [SM] Export: {exp.status_code}")
    if not exp.ok:
        print(f"  [SM] Export error: {exp.text[:100]}")
        return None

    # 4. POLL JUSQU'À COMPLETED
    print(f"  [SM] Polling...")
    for i in range(120):
        time.sleep(5)
        r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
        if not r.ok: continue
        proj = r.json()
        status = proj.get('status')
        url = proj.get('directUrl') or proj.get('downloadUrl')
        if i % 6 == 0: print(f"  [SM] [{i+1}] {status}")
        if status == 'completed' and url:
            print(f"  [SM] Done! {url[:60]}")
            return url
        if status == 'failed':
            print(f"  [SM] Failed: {proj.get('failureReason')}")
            return None

    print(f"  [SM] Timeout")
    return None


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] START {duration}s {len(video_urls)} videos style={style}")

        clips_needed = math.ceil(duration / 3.0) + 2
        clips_per_video = math.ceil(clips_needed / max(len(video_urls), 1)) + 2

        # 1. TÉLÉCHARGER ET EXTRAIRE CLIPS EN ALTERNANT
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
                    # Filtre qualité : scale + unsharp pour netteté
                    vf = 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,unsharp=5:5:0.8:3:3:0.4'
                    r = subprocess.run([
                        'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                        '-vf', vf, '-r', '30',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
                        '-an', out
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

        # 2. INTERLEAVE + ASSEMBLER AVEC TRANSITIONS XFADE
        interleaved = interleave_clips(clips_by_video)
        needed = math.ceil(duration / 3.0)
        selected = [interleaved[i % len(interleaved)] for i in range(needed)]
        print(f"  {len(selected)} clips interleaved")

        # Assembler avec concat simple (xfade trop complexe pour ultrafast)
        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for c in selected: f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print(f"  assembled OK")

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

        # 4. MIXAGE FINAL HAUTE QUALITÉ
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1
        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += ['-map', '0:v', '-map', '1:a',
                    '-c:a', 'aac', '-b:a', '192k', '-t', str(duration)]
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{duration}[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]asetpts=PTS-STARTPTS[v];'
                    f'[2:a]volume=0.10,asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']

        # Filtre vidéo final : contraste + saturation + netteté
        video_filter = 'eq=contrast=1.05:saturation=1.15:brightness=0.02,unsharp=3:3:0.5'
        cmd += [
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '17',
            '-movflags', '+faststart', '-r', '30', '-t', str(duration), output
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise Exception(f"FFmpeg: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  mix OK ({size_mb:.1f}MB)")
        try: os.remove(assembled)
        except: pass

        # 5. SUBMAGIC — captions pro + transitions + effets sonores
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
        print(f"  Upload OK")
        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
