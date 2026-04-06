import os, json, math, subprocess, tempfile, requests, traceback, threading, time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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
            print(f"  upload {path}: {r.status_code}")
        except Exception as e: print(f"  upload error: {e}")

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
    style      = data.get('captionStyle', 'bold')
    sb_url     = data.get('supabaseUrl')
    sb_key     = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Données manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb)
            print(f"[{pid}] ✅ DONE: {url[:80]}")
        except Exception as e:
            traceback.print_exc()
            print(f"[{pid}] ❌ ERROR: {e}")
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
    """v1c1, v2c1, v3c1, v1c2, v2c2..."""
    result = []
    max_len = max(len(c) for c in clips_by_video) if clips_by_video else 0
    for i in range(max_len):
        for vc in clips_by_video:
            if i < len(vc): result.append(vc[i])
    return result


def submagic_process(raw_url, pid, sb, style):
    """Envoyer à Submagic pour captions pro + zooms"""
    key = os.environ.get('SUBMAGIC_API_KEY', '').strip()
    print(f"  SUBMAGIC_API_KEY present: {bool(key)} len={len(key)}")

    if not key:
        print("  ❌ No SUBMAGIC_API_KEY — returning raw video")
        return raw_url

    template_map = {'bold': 'Hormozi 2', 'minimal': 'Sara', 'aggressive': 'Hormozi'}
    template = template_map.get(style, 'Hormozi 2')

    # 1. Créer le projet Submagic
    print(f"  Creating Submagic project (template={template})...")
    r = requests.post('https://api.submagic.co/v1/projects',
        headers={'x-api-key': key, 'Content-Type': 'application/json'},
        json={
            'title': f'AdMachine-{pid[:8]}',
            'language': 'fr',
            'videoUrl': raw_url,
            'templateName': template,
            'magicZooms': True,
        }, timeout=30)

    print(f"  Submagic create: {r.status_code} {r.text[:200]}")
    if not r.ok:
        return raw_url

    sm_id = r.json().get('id')
    print(f"  Submagic project ID: {sm_id}")

    # 2. Déclencher l'export
    exp = requests.post(f'https://api.submagic.co/v1/projects/{sm_id}/export',
        headers={'x-api-key': key, 'Content-Type': 'application/json'},
        json={'width': 1080, 'height': 1920, 'fps': 30},
        timeout=30)
    print(f"  Submagic export: {exp.status_code}")

    # 3. Polling jusqu'à 8 minutes
    print(f"  Polling Submagic...")
    for i in range(96):
        time.sleep(5)
        check = requests.get(f'https://api.submagic.co/v1/projects/{sm_id}',
            headers={'x-api-key': key}, timeout=15)
        if check.ok:
            proj = check.json()
            status = proj.get('status')
            direct_url = proj.get('directUrl') or proj.get('downloadUrl')
            print(f"  Submagic [{i+1}]: status={status}")
            if status == 'completed' and direct_url:
                print(f"  ✅ Submagic done!")
                return direct_url
            elif status == 'failed':
                print(f"  ❌ Submagic failed")
                return raw_url

    print(f"  ⏱️ Submagic timeout — using raw video")
    return raw_url


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] ===== START {duration}s {len(video_urls)} videos =====")

        clips_needed = math.ceil(duration / 3.0) + 2
        clips_per_video = math.ceil(clips_needed / max(len(video_urls), 1)) + 2

        # 1. TÉLÉCHARGER ET EXTRAIRE EN ALTERNANT
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
                        '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-an', out
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

        # 2. INTERLEAVE
        interleaved = interleave_clips(clips_by_video)
        needed = math.ceil(duration / 3.0)
        selected = [interleaved[i % len(interleaved)] for i in range(needed)]
        print(f"  {len(selected)} clips interleaved")

        # 3. ASSEMBLER
        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for c in selected: f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print(f"  assembled OK")

        for clips in clips_by_video:
            for c in clips:
                try: os.remove(c)
                except: pass

        # 4. VOIX + MUSIQUE
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

        # 5. MIXAGE FINAL
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1
        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        if n == 1:
            cmd += ['-c:v', 'copy', '-an']
        elif n == 2 and voice_path:
            cmd += ['-filter_complex', f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[a]',
                    '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{duration}[a]',
                    '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[v];'
                    f'[2:a]volume=0.10,atrim=0:{duration},asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first[a]',
                    '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']

        cmd += ['-t', str(duration), '-movflags', '+faststart', output]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise Exception(f"FFmpeg mix: {res.stderr[-300:]}")
        print(f"  mix OK ({os.path.getsize(output)/1024/1024:.1f}MB)")

        try: os.remove(assembled)
        except: pass

        # 6. UPLOAD VIDÉO BRUTE → SUPABASE
        filename = f"renders/{pid}/raw.mp4"
        with open(output, 'rb') as f: raw_bytes = f.read()
        sb.upload('videos', filename, raw_bytes)
        raw_url = sb.public_url('videos', filename)
        print(f"  raw uploaded: {raw_url[:80]}")

        # 7. SUBMAGIC — CAPTIONS PRO
        final_url = submagic_process(raw_url, pid, sb, style)

        # 8. SAUVEGARDER
        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})
        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
