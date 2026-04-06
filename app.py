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

    def run():
        try:
            url = process_video(
                project_id, video_urls, voice_url, music_url,
                voiceover, duration, caption_style, sb_url, sb_key
            )
            print(f"[{project_id}] ✅ Terminé: {url}")
        except Exception as e:
            traceback.print_exc()
            print(f"[{project_id}] ❌ Erreur: {e}")
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

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'success': True, 'message': 'Traitement en cours'})

def download_parallel(url_path_pairs):
    """Télécharger plusieurs fichiers en parallèle"""
    import concurrent.futures
    def dl(args):
        url, path = args
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        return path

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(dl, pair): pair for pair in url_path_pairs}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"  Download error: {e}")
    return results

def get_duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
        capture_output=True, text=True
    )
    return float(json.loads(r.stdout)['format']['duration'])

def extract_clips_parallel(src, tmp, start_idx, clip_dur=3.0):
    """Extraire tous les clips d'une vidéo source"""
    try:
        src_dur = get_duration(src)
    except:
        return []

    clips = []
    start = 0.0
    idx = start_idx

    while start + 1.5 <= src_dur:
        clip_path = f"{tmp}/clip_{idx:03d}.mp4"
        cd = min(clip_dur, src_dur - start)

        result = subprocess.run([
            'ffmpeg', '-y',
            '-ss', str(start), '-i', src,
            '-t', str(cd),
            '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
            '-r', '30',
            '-c:v', 'libx264',
            '-preset', 'veryfast',  # Plus rapide que ultrafast mais meilleure qualité
            '-crf', '20',           # Haute qualité
            '-an', clip_path
        ], capture_output=True)

        if result.returncode == 0:
            clips.append(clip_path)
            idx += 1
        start += clip_dur

    return clips

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
        print(f"[{project_id}] 🎬 Démarrage {duration}s — {len(video_urls)} vidéos")

        # 1. TÉLÉCHARGER TOUTES LES VIDÉOS EN PARALLÈLE
        pairs = [(url, f"{tmp}/src_{i}.mp4") for i, url in enumerate(video_urls[:10])]
        downloaded = download_parallel(pairs)
        sources = [p for p in [pair[1] for pair in pairs] if os.path.exists(p)]
        print(f"  {len(sources)} vidéos téléchargées ✓")

        if not sources:
            raise Exception("Aucune vidéo téléchargée")

        # 2. EXTRAIRE LES CLIPS EN PARALLÈLE
        import concurrent.futures
        all_clips = []
        start_idx = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futures = []
            for src in sources:
                futures.append(ex.submit(extract_clips_parallel, src, tmp, start_idx))
                start_idx += 50  # Espace pour les index

            for future in concurrent.futures.as_completed(futures):
                clips = future.result()
                all_clips.extend(clips)
                print(f"  +{len(clips)} clips extraits")

        all_clips.sort()  # Trier par nom pour garder l'ordre
        print(f"  Total: {len(all_clips)} clips disponibles ✓")

        if not all_clips:
            raise Exception("Aucun clip extrait")

        # 3. SÉLECTIONNER ET ASSEMBLER LES CLIPS
        needed = math.ceil(duration / 3.0)
        selected = [all_clips[i % len(all_clips)] for i in range(needed)]

        concat_file = f"{tmp}/concat.txt"
        with open(concat_file, 'w') as f:
            for c in selected:
                f.write(f"file '{c}'\n")

        assembled = f"{tmp}/assembled.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', concat_file, '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print(f"  {len(selected)} clips assemblés ✓")

        # Libérer les clips
        for c in all_clips:
            try: os.remove(c)
            except: pass
        for s in sources:
            try: os.remove(s)
            except: pass

        # 4. VOIX + MUSIQUE EN PARALLÈLE
        voice_path = music_path = None

        def dl_voice():
            nonlocal voice_path
            if not voice_url: return
            try:
                p = f"{tmp}/voice.mp3"
                r = requests.get(voice_url, timeout=60)
                r.raise_for_status()
                with open(p, 'wb') as f: f.write(r.content)
                voice_path = p
                print("  Voix ✓")
            except Exception as e: print(f"  Voix erreur: {e}")

        def dl_music():
            nonlocal music_path
            if not music_url: return
            try:
                p = f"{tmp}/music.mp3"
                r = requests.get(music_url, timeout=60)
                r.raise_for_status()
                with open(p, 'wb') as f: f.write(r.content)
                music_path = p
                print("  Musique ✓")
            except Exception as e: print(f"  Musique erreur: {e}")

        t1 = threading.Thread(target=dl_voice)
        t2 = threading.Thread(target=dl_music)
        t1.start(); t2.start()
        t1.join(); t2.join()

        # 5. CAPTIONS SRT MOT PAR MOT
        srt_path = f"{tmp}/captions.srt"
        words = [w for w in voiceover.replace('\n', ' ').split() if w]
        make_srt(words, duration, srt_path)
        print(f"  {len(words)} mots en captions ✓")

        styles = {
            'bold':       {'size': 85, 'color': '&H00FFFFFF', 'outline_color': '&H00000000', 'outline': 7, 'bold': 1, 'shadow': 3},
            'minimal':    {'size': 70, 'color': '&H00FFFFFF', 'outline_color': '&H00000000', 'outline': 2, 'bold': 0, 'shadow': 1},
            'aggressive': {'size': 95, 'color': '&H0000FFFF', 'outline_color': '&H000000FF', 'outline': 9, 'bold': 1, 'shadow': 3},
        }
        st = styles.get(caption_style, styles['bold'])
        srt_escaped = srt_path.replace(':', '\\:').replace("'", "\\'")
        srt_filter = (
            f"subtitles={srt_escaped}:force_style='"
            f"FontSize={st['size']},"
            f"PrimaryColour={st['color']},"
            f"OutlineColour={st['outline_color']},"
            f"BorderStyle=1,Outline={st['outline']},"
            f"Shadow={st['shadow']},"
            f"Bold={st['bold']},Alignment=2,MarginV=260'"
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
            cmd += ['-filter_complex',
                    f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[aout]',
                    '-map', '0:v', '-map', '[aout]']
        elif n == 2 and music_path:
            cmd += ['-filter_complex',
                    f'[1:a]volume=0.10,atrim=0:{duration}[aout]',
                    '-map', '0:v', '-map', '[aout]']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[v];'
                    f'[2:a]volume=0.10,atrim=0:{duration},asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first[aout]',
                    '-map', '0:v', '-map', '[aout]']

        cmd += [
            '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',  # Haute qualité
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            '-r', '30',
            output
        ]

        print("  🎞️ Rendu final haute qualité...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=500)
        if result.returncode != 0:
            print("stderr:", result.stderr[-3000:])
            raise Exception(f"FFmpeg: {result.stderr[-400:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  ✅ Rendu OK ({size_mb:.1f}MB)")

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

        print(f"  ✅ Upload OK → {public_url[:60]}...")
        return public_url

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
