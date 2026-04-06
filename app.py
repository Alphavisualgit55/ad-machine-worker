import os, json, math, subprocess, tempfile, requests, traceback, threading
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
            requests.post(f"{self.url}/storage/v1/object/{bucket}/{path}", headers=h, data=data, timeout=300)
        except: pass

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


def make_ass(words, total_duration, path, style='bold'):
    """Captions ASS style TikTok — fond coloré, centré, animé"""
    if not words: return

    tpw = total_duration / len(words)

    # Couleurs highlight BGR pour ASS
    COLORS = ['&H00F16363', '&H0008A9EA', '&H0085B810', '&H004444EF', '&H00CF55A8']

    if style == 'aggressive':
        font_size, primary, outline_color, outline, bold = 85, '&H0000FFFF', '&H000000FF', 8, -1
    elif style == 'minimal':
        font_size, primary, outline_color, outline, bold = 68, '&H00FFFFFF', '&H00000000', 3, 0
    else:
        font_size, primary, outline_color, outline, bold = 78, '&H00FFFFFF', '&H00000000', 7, -1

    def ts(s):
        h=int(s//3600); m=int((s%3600)//60); sec=s%60; cs=int((sec%1)*100)
        return f"{h}:{m:02d}:{int(sec):02d}.{cs:02d}"

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Normal,Arial,{font_size},{primary},&H000000FF,{outline_color},&H00000000,{bold},0,0,0,100,100,2,0,1,{outline},3,2,60,60,280,1",
    ]

    # Un style par couleur highlight
    for i, color in enumerate(COLORS):
        lines.append(f"Style: HL{i},Arial,{font_size},&H00FFFFFF,&H000000FF,{color},&H00000000,{bold},0,0,0,100,100,2,0,3,0,0,2,60,60,280,1")

    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    for i, word in enumerate(words):
        start = i * tpw
        end = min((i + 1) * tpw, total_duration)
        text = word.upper()
        is_highlight = (i % 5 == 2) or len(word) > 5
        hl_idx = (i // 5) % len(COLORS)
        style_name = f"HL{hl_idx}" if is_highlight else "Normal"
        # Animation pop-in
        anim = "{\\t(0,80,\\fscx115\\fscy115)\\t(80,180,\\fscx100\\fscy100)}"
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},{style_name},,0,0,0,,{anim}{text}")

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def extract_clips_from_source(src, tmp, src_idx, clips_needed):
    """Extraire les clips 3s d'une vidéo source"""
    clips = []
    try:
        src_dur = get_dur(src)
        start = 0.0
        clip_num = 0
        while start + 1.5 <= src_dur and len(clips) < clips_needed:
            out = f"{tmp}/v{src_idx}_c{clip_num:03d}.mp4"
            cd = min(3.0, src_dur - start)
            r = subprocess.run([
                'ffmpeg', '-y', '-ss', str(start), '-i', src, '-t', str(cd),
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
                '-an', out
            ], capture_output=True)
            if r.returncode == 0:
                clips.append(out)
            clip_num += 1
            start += 3.0
    except Exception as e:
        print(f"  extract error src{src_idx}: {e}")
    return clips


def interleave_clips(clips_by_video):
    """
    Alterner les clips entre les vidéos pour un montage professionnel
    Ex: vid1_c1, vid2_c1, vid3_c1, vid1_c2, vid2_c2...
    """
    if not clips_by_video:
        return []

    result = []
    max_len = max(len(c) for c in clips_by_video)

    for i in range(max_len):
        for video_clips in clips_by_video:
            if i < len(video_clips):
                result.append(video_clips[i])

    return result


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, sb):
    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{pid}] START {duration}s {len(video_urls)} videos")

        clips_needed = math.ceil(duration / 3.0) + 2
        clips_per_video = math.ceil(clips_needed / max(len(video_urls), 1)) + 1

        # 1. TÉLÉCHARGER ET EXTRAIRE EN ALTERNANT LES VIDÉOS
        clips_by_video = []

        for i, url in enumerate(video_urls[:8]):
            src = f"{tmp}/src_{i}.mp4"
            try:
                dl(url, src)
                print(f"  video {i+1} downloaded")
                clips = extract_clips_from_source(src, tmp, i, clips_per_video)
                if clips:
                    clips_by_video.append(clips)
                    print(f"  video {i+1}: {len(clips)} clips extraits")
                try: os.remove(src)
                except: pass
            except Exception as e:
                print(f"  error video {i}: {e}")

        if not clips_by_video:
            raise Exception("No clips extracted")

        # 2. INTERLEAVE — ALTERNER LES CLIPS ENTRE LES VIDÉOS
        interleaved = interleave_clips(clips_by_video)
        print(f"  Interleaved: {len(interleaved)} clips disponibles")
        print(f"  Ordre: {[os.path.basename(c) for c in interleaved[:6]]}...")

        # 3. SÉLECTIONNER LES CLIPS NÉCESSAIRES
        needed = math.ceil(duration / 3.0)
        selected = [interleaved[i % len(interleaved)] for i in range(needed)]

        # 4. ASSEMBLER
        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for c in selected: f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print(f"  {len(selected)} clips assembled (alternés)")

        for clips in clips_by_video:
            for c in clips:
                try: os.remove(c)
                except: pass

        # 5. VOIX + MUSIQUE
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

        # 6. CAPTIONS ASS STYLE TIKTOK
        ass_path = f"{tmp}/captions.ass"
        words = [w for w in voiceover.replace('\n', ' ').split() if w]
        make_ass(words, duration, ass_path, style)
        print(f"  {len(words)} words in captions")

        ass_esc = ass_path.replace(':', '\\:')
        vf = f"ass={ass_esc}"

        # 7. RENDU FINAL
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1
        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        cmd += ['-vf', vf]

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

        cmd += ['-t', str(duration), '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-r', '30', output]

        print("  Rendering...")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=500)
        if res.returncode != 0:
            print("FFmpeg error:", res.stderr[-2000:])
            raise Exception(f"FFmpeg: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  Render OK ({size_mb:.1f}MB)")

        try: os.remove(assembled)
        except: pass

        # 8. UPLOAD
        filename = f"renders/{pid}/final.mp4"
        with open(output, 'rb') as f: video_bytes = f.read()

        sb.upload('videos', filename, video_bytes)
        public_url = sb.public_url('videos', filename)
        sb.update_video(pid, {'video_url': public_url})
        sb.update_project(pid, {'status': 'done'})

        print(f"  Upload OK")
        return public_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
