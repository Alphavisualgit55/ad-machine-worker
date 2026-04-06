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
    style      = data.get('captionStyle', 'bold')
    sb_url     = data.get('supabaseUrl')
    sb_key     = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Données manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb)
            print(f"[{pid}] ✅ DONE")
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
    result = []
    max_len = max(len(c) for c in clips_by_video) if clips_by_video else 0
    for i in range(max_len):
        for vc in clips_by_video:
            if i < len(vc): result.append(vc[i])
    return result


def submagic_process(video_with_voice_path, pid, style):
    """
    Envoie la vidéo AVEC VOIX à Submagic pour captions pro.
    Submagic transcrit la voix et génère les captions automatiquement.
    """
    key = os.environ.get('SUBMAGIC_API_KEY', '').strip()
    print(f"  SUBMAGIC_API_KEY: {'✅ OK' if key else '❌ MISSING'}")
    if not key:
        return None

    # Template selon style
    template_map = {
        'bold': 'Hormozi 2',
        'minimal': 'Sara',
        'aggressive': 'Beast',
    }
    template = template_map.get(style, 'Hormozi 2')
    print(f"  Template: {template}")

    # 1. UPLOAD FICHIER DIRECT À SUBMAGIC (avec voix dedans)
    print(f"  Uploading to Submagic...")
    try:
        with open(video_with_voice_path, 'rb') as f:
            r = requests.post(
                'https://api.submagic.co/v1/projects/upload',
                headers={'x-api-key': key},
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
        print(f"  Upload error: {e}")
        return None

    print(f"  Submagic upload: {r.status_code}")
    if not r.ok:
        print(f"  Error: {r.text[:300]}")
        return None

    sm_data = r.json()
    sm_id = sm_data.get('id')
    print(f"  Project ID: {sm_id}")

    # 2. ATTENDRE LA TRANSCRIPTION (status: transcribing → processing)
    print(f"  Waiting for transcription...")
    for i in range(30):
        time.sleep(5)
        check = requests.get(
            f'https://api.submagic.co/v1/projects/{sm_id}',
            headers={'x-api-key': key}, timeout=15
        )
        if check.ok:
            proj = check.json()
            status = proj.get('status')
            transcription = proj.get('transcriptionStatus')
            print(f"  [{i+1}] status={status} transcription={transcription}")
            if transcription == 'COMPLETED' or status == 'processing':
                break
            elif status == 'failed':
                print(f"  ❌ Failed: {proj.get('failureReason')}")
                return None

    # 3. DÉCLENCHER L'EXPORT
    print(f"  Triggering export...")
    exp = requests.post(
        f'https://api.submagic.co/v1/projects/{sm_id}/export',
        headers={'x-api-key': key, 'Content-Type': 'application/json'},
        json={'width': 1080, 'height': 1920, 'fps': 30},
        timeout=30
    )
    print(f"  Export: {exp.status_code} {exp.text[:100]}")

    # 4. POLLING JUSQU'À COMPLETED
    print(f"  Polling for result...")
    for i in range(96):
        time.sleep(5)
        check = requests.get(
            f'https://api.submagic.co/v1/projects/{sm_id}',
            headers={'x-api-key': key}, timeout=15
        )
        if check.ok:
            proj = check.json()
            status = proj.get('status')
            direct_url = proj.get('directUrl') or proj.get('downloadUrl')
            if i % 4 == 0:
                print(f"  [{i+1}] status={status}")
            if status == 'completed' and direct_url:
                print(f"  ✅ Submagic done! {direct_url[:60]}")
                return direct_url
            elif status == 'failed':
                print(f"  ❌ Failed: {proj.get('failureReason')}")
                return None

    print(f"  ⏱️ Timeout")
    return None


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
            '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-r', '30',
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

        # 4. MIXAGE FINAL — vidéo avec voix (pour Submagic)
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1
        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            # Voix originale sans modification
            cmd += ['-map', '0:v', '-map', '1:a',
                    '-c:a', 'aac', '-b:a', '192k', '-t', str(duration)]
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{duration}[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']
        else:
            # Voix 100% + musique 10%
            cmd += ['-filter_complex',
                    f'[1:a]asetpts=PTS-STARTPTS[v];'
                    f'[2:a]volume=0.10,asetpts=PTS-STARTPTS[m];'
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

        # 5. SUBMAGIC — envoie la vidéo AVEC voix pour les captions
        final_url = submagic_process(output, pid, style)

        if final_url:
            # Submagic a réussi → utiliser sa vidéo
            sb.update_video(pid, {'video_url': final_url})
            sb.update_project(pid, {'status': 'done'})
            return final_url

        # Fallback — upload sur Supabase sans captions Submagic
        print("  Fallback: uploading to Supabase...")
        filename = f"renders/{pid}/final.mp4"
        with open(output, 'rb') as f: video_bytes = f.read()
        sb.upload('videos', filename, video_bytes)
        final_url = sb.public_url('videos', filename)
        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})
        print(f"  Upload OK ✅")
        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
