import os, json, math, subprocess, tempfile, requests, traceback, threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Ad Machine Worker', 'status': 'running'})

@app.route('/health', methods=['GET'])
def health():
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return jsonify({'status': 'ok', 'ffmpeg': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/render', methods=['POST'])
def render():
    data = request.json
    project_id    = data.get('projectId')
    video_urls    = data.get('videoUrls', [])
    voice_url     = data.get('voiceUrl')
    music_url     = data.get('musicUrl')
    voiceover     = data.get('voiceover', '')
    duration      = int(data.get('duration', 30))
    caption_style = data.get('captionStyle', 'bold')
    sb_url        = data.get('supabaseUrl')
    sb_key        = data.get('supabaseKey')

    if not project_id or not video_urls:
        return jsonify({'error': 'Données manquantes'}), 400

    # Lancer en thread pour éviter le timeout HTTP
    def run():
        try:
            url = process_video(
                project_id, video_urls, voice_url, music_url,
                voiceover, duration, caption_style, sb_url, sb_key
            )
            print(f"[{project_id}] Terminé: {url}")
        except Exception as e:
            traceback.print_exc()
            try:
                sb = create_client(sb_url, sb_key)
                vids = sb.table('videos').select('*') \
                    .eq('project_id', project_id).eq('generated', False).execute()
                if vids.data:
                    sb.table('videos').insert({
                        'project_id': project_id,
                        'video_url': vids.data[0]['video_url'],
                        'generated': True
                    }).execute()
                sb.table('projects').update({'status': 'done'}) \
                    .eq('id', project_id).execute()
            except: pass

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Répondre immédiatement — le traitement continue en background
    return jsonify({'success': True, 'message': 'Traitement en cours'})

def download(url, path):
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

def get_duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
        capture_output=True, text=True
    )
    return float(json.loads(r.stdout)['format']['duration'])

def make_srt(words, total_duration, path):
    if not words: return
    tpw = total_duration / len(words)
    def ts(s):
        h=int(s//3600); m=int((s%3600)//60)
        sec=s%60; ms=int((sec%1)*1000)
        return f"{h:02d}:{m:02d}:{int(sec):02d},{ms:03d}"
    with open(path, 'w', encoding='utf-8') as f:
        for i, w in enumerate(words):
            s = i * tpw
            e = min((i+1)*tpw, total_duration)
            f.write(f"{i+1}\n{ts(s)} --> {ts(e)}\n{w.upper()}\n\n")

def process_video(project_id, video_urls, voice_url, music_url,
                  voiceover, duration, caption_style, sb_url, sb_key):

    with tempfile.TemporaryDirectory() as tmp:
        print(f"[{project_id}] Démarrage {duration}s")

        # 1. TÉLÉCHARGER LES VIDÉOS (max 5 pour économiser RAM)
        sources = []
        for i, url in enumerate(video_urls[:5]):
            try:
                p = f"{tmp}/src_{i}.mp4"
                download(url, p)
                sources.append(p)
                print(f"  Vidéo {i+1} ✓")
            except Exception as e:
                print(f"  Erreur vidéo {i}: {e}")

        if not sources:
            raise Exception("Aucune vidéo téléchargée")

        # 2. DÉCOUPER EN CLIPS 3S (ultrafast pour économiser RAM)
        clips = []
        clip_idx = 0
        clips_needed = math.ceil(duration / 3.0) + 1

        for src in sources:
            try:
                src_dur = get_duration(src)
                start = 0.0
                while start + 2.0 <= src_dur and len(clips) < clips_needed:
                    clip_path = f"{tmp}/clip_{clip_idx:03d}.mp4"
                    clip_dur = min(3.0, src_dur - start)
                    subprocess.run([
                        'ffmpeg', '-y',
                        '-ss', str(start), '-i', src,
                        '-t', str(clip_dur),
                        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                        '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                        '-an', clip_path
                    ], check=True, capture_output=True)
                    clips.append(clip_path)
                    clip_idx += 1
                    start += 3.0
                    print(f"  Clip {clip_idx} ✓")
            except Exception as e:
                print(f"  Clip error: {e}")

        if not clips:
            raise Exception("Aucun clip extrait")

        # 3. ASSEMBLER
        needed = math.ceil(duration / 3.0)
        selected = [clips[i % len(clips)] for i in range(needed)]

        concat_file = f"{tmp}/concat.txt"
        with open(concat_file, 'w') as f:
            for c in selected:
                f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_file, '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26', '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print(f"  {len(selected)} clips assemblés ✓")

        # Libérer les clips de la mémoire
        for c in clips:
            try: os.remove(c)
            except: pass

        # 4. VOIX + MUSIQUE
        voice_path = music_path = None
        if voice_url:
            try:
                voice_path = f"{tmp}/voice.mp3"
                download(voice_url, voice_path)
                print("  Voix ✓")
            except Exception as e:
                print(f"  Voix erreur: {e}")

        if music_url:
            try:
                music_path = f"{tmp}/music.mp3"
                download(music_url, music_path)
                print("  Musique ✓")
            except Exception as e:
                print(f"  Musique erreur: {e}")

        # 5. CAPTIONS SRT MOT PAR MOT
        srt_path = f"{tmp}/captions.srt"
        words = [w for w in voiceover.replace('\n', ' ').split() if w]
        make_srt(words, duration, srt_path)
        print(f"  {len(words)} mots ✓")

        # Style captions
        styles = {
            'bold':       {'size': 80, 'color': '&H00FFFFFF', 'outline_color': '&H00000000', 'outline': 6, 'bold': 1},
            'minimal':    {'size': 65, 'color': '&H00FFFFFF', 'outline_color': '&H00000000', 'outline': 2, 'bold': 0},
            'aggressive': {'size': 90, 'color': '&H0000FFFF', 'outline_color': '&H000000FF', 'outline': 8, 'bold': 1},
        }
        st = styles.get(caption_style, styles['bold'])

        srt_escaped = srt_path.replace(':', '\\:')
        srt_filter = (
            f"subtitles={srt_escaped}:force_style='"
            f"FontSize={st['size']},"
            f"PrimaryColour={st['color']},"
            f"OutlineColour={st['outline_color']},"
            f"BorderStyle=1,Outline={st['outline']},Shadow=2,"
            f"Bold={st['bold']},Alignment=2,MarginV=250'"
        )

        # 6. MONTAGE FINAL
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg', '-y', '-i', assembled]
        n = 1

        if voice_path: cmd += ['-i', voice_path]; n += 1
        if music_path: cmd += ['-i', music_path]; n += 1

        cmd += ['-vf', srt_filter]

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += ['-filter_complex', f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[aout]',
                    '-map', '0:v', '-map', '[aout]']
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{duration}[aout]',
                    '-map', '0:v', '-map', '[aout]']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[v];'
                    f'[2:a]volume=0.10,atrim=0:{duration},asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first[aout]',
                    '-map', '0:v', '-map', '[aout]']

        cmd += [
            '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart', '-r', '30',
            output
        ]

        print("  Rendu FFmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=400)
        if result.returncode != 0:
            print("FFmpeg stderr:", result.stderr[-2000:])
            raise Exception(f"FFmpeg: {result.stderr[-300:]}")

        print(f"  Rendu OK ✓ ({os.path.getsize(output)/1024/1024:.1f}MB)")

        # 7. UPLOAD SUPABASE
        sb = create_client(sb_url, sb_key)
        filename = f"renders/{project_id}/final.mp4"

        with open(output, 'rb') as f:
            video_bytes = f.read()

        sb.storage.from_('videos').upload(
            filename, video_bytes,
            {'content-type': 'video/mp4', 'upsert': 'true'}
        )

        url_result = sb.storage.from_('videos').get_public_url(filename)
        public_url = url_result if isinstance(url_result, str) else url_result.get('publicUrl', '')

        sb.table('videos').update({'video_url': public_url}) \
            .eq('project_id', project_id).eq('generated', True).execute()
        sb.table('projects').update({'status': 'done'}) \
            .eq('id', project_id).execute()

        print(f"  Upload OK ✓")
        return public_url

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
