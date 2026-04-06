import os, json, math, subprocess, tempfile, requests, traceback, threading
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

class SB:
    """Client Supabase via API REST directe - pas de SDK"""
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.h = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation',
        }

    def update_project(self, pid, data):
        requests.patch(f"{self.url}/rest/v1/projects?id=eq.{pid}", headers=self.h, json=data, timeout=30)

    def update_video(self, pid, data):
        requests.patch(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.true", headers=self.h, json=data, timeout=30)

    def get_sources(self, pid):
        r = requests.get(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.false&select=*", headers=self.h, timeout=30)
        return r.json() if r.ok else []

    def upload(self, bucket, path, data, ct='video/mp4'):
        h = {**self.h, 'Content-Type': ct, 'x-upsert': 'true'}
        del h['Prefer']
        requests.post(f"{self.url}/storage/v1/object/{bucket}/{path}", headers=h, data=data, timeout=300)

    def public_url(self, bucket, path):
        return f"{self.url}/storage/v1/object/public/{bucket}/{path}"


@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Ad Machine Worker', 'status': 'running', 'version': '2.0'})

@app.route('/health', methods=['GET'])
def health():
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return jsonify({'status': 'ok', 'ffmpeg': 'ok' if r.returncode == 0 else 'error'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/render', methods=['POST'])
def render():
    data = request.json
    pid          = data.get('projectId')
    video_urls   = data.get('videoUrls', [])
    voice_url    = data.get('voiceUrl')
    music_url    = data.get('musicUrl')
    voiceover    = data.get('voiceover', '')
    duration     = int(data.get('duration', 30))
    style        = data.get('captionStyle', 'bold')
    sb_url       = data.get('supabaseUrl')
    sb_key       = data.get('supabaseKey')

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
                if srcs:
                    sb.update_video(pid, {'video_url': srcs[0]['video_url']})
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

def make_srt(words, total, path):
    if not words: return
    tpw = total / len(words)
    def ts(s):
        h=int(s//3600); m=int((s%3600)//60); sec=s%60; ms=int((sec%1)*1000)
        return f"{h:02d}:{m:02d}:{int(sec):02d},{ms:03d}"
    with open(path, 'w', encoding='utf-8') as f:
        for i, w in enumerate(words):
            f.write(f"{i+1}\n{ts(i*tpw)} --> {ts(min((i+1)*tpw,total))}\n{w.upper()}\n\n")

def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] START {duration}s {len(video_urls)} videos")

        # 1. TÉLÉCHARGER EN PARALLÈLE
        import concurrent.futures

        def dl_vid(args):
            i, url = args
            p = f"{tmp}/src_{i}.mp4"
            try: dl(url, p); return p
            except Exception as e: print(f"  dl error {i}: {e}"); return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            sources = list(filter(None, ex.map(dl_vid, enumerate(video_urls[:10]))))

        print(f"  {len(sources)} videos downloaded")
        if not sources: raise Exception("No videos downloaded")

        # 2. EXTRAIRE CLIPS 3S EN PARALLÈLE
        def extract(args):
            src, base = args
            clips = []
            try:
                d = get_dur(src); start = 0.0; idx = base
                while start + 1.5 <= d:
                    out = f"{tmp}/c_{idx:04d}.mp4"; cd = min(3.0, d - start)
                    r = subprocess.run([
                        'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                        '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-an', out
                    ], capture_output=True)
                    if r.returncode == 0: clips.append(out)
                    idx += 1; start += 3.0
            except Exception as e: print(f"  extract error: {e}")
            return clips

        all_clips = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for clips in ex.map(extract, [(s, i*100) for i, s in enumerate(sources)]):
                all_clips.extend(clips)

        all_clips.sort()
        print(f"  {len(all_clips)} clips extracted")
        if not all_clips: raise Exception("No clips extracted")

        for s in sources:
            try: os.remove(s)
            except: pass

        # 3. ASSEMBLER
        needed = math.ceil(duration / 3.0)
        selected = [all_clips[i % len(all_clips)] for i in range(needed)]

        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for c in selected: f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-t', str(duration), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', '30', assembled
        ], check=True, capture_output=True)
        print(f"  {len(selected)} clips assembled")

        for c in all_clips:
            try: os.remove(c)
            except: pass

        # 4. VOIX + MUSIQUE EN PARALLÈLE
        voice_path = music_path = None

        def dl_voice():
            nonlocal voice_path
            if not voice_url: return
            try:
                p = f"{tmp}/voice.mp3"; dl(voice_url, p); voice_path = p
                print("  voice OK")
            except Exception as e: print(f"  voice error: {e}")

        def dl_music():
            nonlocal music_path
            if not music_url: return
            try:
                p = f"{tmp}/music.mp3"; dl(music_url, p); music_path = p
                print("  music OK")
            except Exception as e: print(f"  music error: {e}")

        t1 = threading.Thread(target=dl_voice)
        t2 = threading.Thread(target=dl_music)
        t1.start(); t2.start(); t1.join(); t2.join()

        # 5. CAPTIONS SRT MOT PAR MOT
        srt = f"{tmp}/captions.srt"
        words = [w for w in voiceover.replace('\n', ' ').split() if w]
        make_srt(words, duration, srt)
        print(f"  {len(words)} words in captions")

        styles = {
            'bold':       {'size': 85, 'color': '&H00FFFFFF', 'oc': '&H00000000', 'outline': 7, 'bold': 1, 'shadow': 3},
            'minimal':    {'size': 70, 'color': '&H00FFFFFF', 'oc': '&H00000000', 'outline': 2, 'bold': 0, 'shadow': 1},
            'aggressive': {'size': 95, 'color': '&H0000FFFF', 'oc': '&H000000FF', 'outline': 9, 'bold': 1, 'shadow': 3},
        }
        st = styles.get(style, styles['bold'])
        srt_esc = srt.replace(':', '\\:')
        srt_filter = (
            f"subtitles={srt_esc}:force_style='"
            f"FontSize={st['size']},PrimaryColour={st['color']},"
            f"OutlineColour={st['oc']},BorderStyle=1,Outline={st['outline']},"
            f"Shadow={st['shadow']},Bold={st['bold']},Alignment=2,MarginV=260'"
        )

        # 6. MONTAGE FINAL HAUTE QUALITÉ
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1
        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        cmd += ['-vf', srt_filter]

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += ['-filter_complex', f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[a]', '-map', '0:v', '-map', '[a]']
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{duration}[a]', '-map', '0:v', '-map', '[a]']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[v];'
                    f'[2:a]volume=0.10,atrim=0:{duration},asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first[a]',
                    '-map', '0:v', '-map', '[a]']

        cmd += ['-t', str(duration), '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-r', '30', output]

        print("  Rendering...")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=500)
        if res.returncode != 0:
            print("FFmpeg stderr:", res.stderr[-2000:])
            raise Exception(f"FFmpeg failed: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  Render OK ({size_mb:.1f}MB)")

        # 7. UPLOAD SUPABASE
        filename = f"renders/{pid}/final.mp4"
        with open(output, 'rb') as f: video_bytes = f.read()

        sb.upload('videos', filename, video_bytes)
        public_url = sb.public_url('videos', filename)

        sb.update_video(pid, {'video_url': public_url})
        sb.update_project(pid, {'status': 'done'})

        print(f"  Upload OK → {public_url[:60]}")
        return public_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
