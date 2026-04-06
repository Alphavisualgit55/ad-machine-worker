import os
import json
import uuid
import subprocess
import tempfile
import requests
import math
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'ffmpeg': check_ffmpeg()})

def check_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return 'ok' if result.returncode == 0 else 'missing'
    except:
        return 'missing'

@app.route('/render', methods=['POST'])
def render():
    data = request.json
    project_id = data.get('projectId')
    video_urls = data.get('videoUrls', [])
    voice_url = data.get('voiceUrl')
    music_url = data.get('musicUrl')
    captions = data.get('captions', [])
    voiceover = data.get('voiceover', '')
    duration = int(data.get('duration', 30))
    caption_style = data.get('captionStyle', 'bold')
    supabase_url = data.get('supabaseUrl')
    supabase_key = data.get('supabaseKey')

    if not project_id or not video_urls:
        return jsonify({'error': 'projectId et videoUrls requis'}), 400

    try:
        result_url = process_video(
            project_id=project_id,
            video_urls=video_urls,
            voice_url=voice_url,
            music_url=music_url,
            captions=captions,
            voiceover=voiceover,
            duration=duration,
            caption_style=caption_style,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        )
        return jsonify({'success': True, 'url': result_url})
    except Exception as e:
        print(f'Render error: {e}')
        return jsonify({'error': str(e)}), 500

def download_file(url, path):
    """Télécharger un fichier depuis une URL"""
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return path

def get_video_duration(path):
    """Obtenir la durée d'une vidéo"""
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', path
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data['format']['duration'])

def extract_clip(input_path, output_path, start, duration):
    """Extraire un clip d'une vidéo"""
    subprocess.run([
        'ffmpeg', '-y',
        '-ss', str(start),
        '-i', input_path,
        '-t', str(duration),
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
        '-r', '30',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-an',
        output_path
    ], check=True, capture_output=True)

def process_video(project_id, video_urls, voice_url, music_url, captions,
                  voiceover, duration, caption_style, supabase_url, supabase_key):

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Traitement projet {project_id}, durée: {duration}s")

        # ===== 1. TÉLÉCHARGER LES VIDÉOS B-ROLL =====
        downloaded_videos = []
        for i, url in enumerate(video_urls[:10]):
            try:
                path = os.path.join(tmpdir, f'source_{i}.mp4')
                download_file(url, path)
                downloaded_videos.append(path)
                print(f"Vidéo {i+1} téléchargée")
            except Exception as e:
                print(f"Erreur téléchargement vidéo {i}: {e}")

        if not downloaded_videos:
            raise Exception("Aucune vidéo téléchargée")

        # ===== 2. DÉCOUPER EN CLIPS DE 3 SECONDES =====
        clips = []
        clip_duration = 3.0
        clips_needed = math.ceil(duration / clip_duration)
        clip_index = 0

        for video_path in downloaded_videos:
            try:
                vid_duration = get_video_duration(video_path)
                # Extraire plusieurs clips de 3s depuis chaque vidéo
                start = 0
                while start + clip_duration <= vid_duration and len(clips) < clips_needed * 2:
                    clip_path = os.path.join(tmpdir, f'clip_{clip_index}.mp4')
                    extract_clip(video_path, clip_path, start, clip_duration)
                    clips.append(clip_path)
                    clip_index += 1
                    start += clip_duration
                    print(f"Clip {clip_index} extrait ({start:.1f}s)")
            except Exception as e:
                print(f"Erreur extraction clip: {e}")

        if not clips:
            raise Exception("Aucun clip extrait")

        # Sélectionner les clips nécessaires (cyclique si pas assez)
        selected_clips = []
        for i in range(clips_needed):
            selected_clips.append(clips[i % len(clips)])

        print(f"{len(selected_clips)} clips sélectionnés pour {duration}s")

        # ===== 3. CRÉER LA LISTE DE CLIPS (concat) =====
        concat_list = os.path.join(tmpdir, 'concat.txt')
        with open(concat_list, 'w') as f:
            for clip in selected_clips:
                f.write(f"file '{clip}'\n")

        # Assembler les clips
        assembled = os.path.join(tmpdir, 'assembled.mp4')
        subprocess.run([
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_list,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '22',
            '-r', '30',
            assembled
        ], check=True, capture_output=True)
        print("Clips assemblés")

        # ===== 4. TÉLÉCHARGER LA VOIX OFF =====
        voice_path = None
        if voice_url:
            try:
                voice_path = os.path.join(tmpdir, 'voice.mp3')
                download_file(voice_url, voice_path)
                print("Voix off téléchargée")
            except Exception as e:
                print(f"Erreur voix: {e}")

        # ===== 5. TÉLÉCHARGER LA MUSIQUE =====
        music_path = None
        if music_url:
            try:
                music_path = os.path.join(tmpdir, 'music.mp3')
                download_file(music_url, music_path)
                print("Musique téléchargée")
            except Exception as e:
                print(f"Erreur musique: {e}")

        # ===== 6. GÉNÉRER LES CAPTIONS SRT =====
        srt_path = os.path.join(tmpdir, 'captions.srt')

        # Construire les captions mot par mot depuis le voiceover
        words = voiceover.split() if voiceover else []
        total_words = len(words)
        srt_entries = []

        if words and duration > 0:
            time_per_word = duration / total_words
            for i, word in enumerate(words):
                start_sec = i * time_per_word
                end_sec = (i + 1) * time_per_word

                def sec_to_srt(s):
                    h = int(s // 3600)
                    m = int((s % 3600) // 60)
                    sec = s % 60
                    ms = int((sec % 1) * 1000)
                    return f"{h:02d}:{m:02d}:{int(sec):02d},{ms:03d}"

                srt_entries.append(
                    f"{i+1}\n{sec_to_srt(start_sec)} --> {sec_to_srt(end_sec)}\n{word.upper()}\n"
                )

        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_entries))

        # ===== 7. STYLE CAPTIONS =====
        styles = {
            'bold': {
                'fontsize': 90,
                'fontcolor': 'white',
                'bordercolor': 'black',
                'borderw': 8,
                'box': 0,
                'font': 'Montserrat-Black',
            },
            'minimal': {
                'fontsize': 72,
                'fontcolor': 'white',
                'bordercolor': 'black',
                'borderw': 4,
                'box': 1,
                'boxcolor': 'black@0.5',
                'boxborderw': 12,
                'font': 'Montserrat-Bold',
            },
            'aggressive': {
                'fontsize': 96,
                'fontcolor': 'yellow',
                'bordercolor': 'red',
                'borderw': 9,
                'box': 0,
                'font': 'Montserrat-Black',
            },
        }
        s = styles.get(caption_style, styles['bold'])

        # ===== 8. ASSEMBLER TOUT AVEC FFMPEG =====
        output_path = os.path.join(tmpdir, 'final.mp4')

        # Construire le filtre subtitles
        subtitle_filter = (
            f"subtitles={srt_path}:force_style='"
            f"FontName=DejaVu Sans Bold,"
            f"FontSize={s['fontsize']},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=1,"
            f"Outline={s['borderw']},"
            f"Shadow=3,"
            f"Alignment=2,"
            f"MarginV=300'"
        )

        # Construire la commande FFmpeg selon les pistes disponibles
        cmd = ['ffmpeg', '-y', '-i', assembled]
        audio_inputs = []
        input_count = 1

        if voice_path:
            cmd += ['-i', voice_path]
            audio_inputs.append(f'[{input_count}:a]')
            input_count += 1

        if music_path:
            cmd += ['-i', music_path]
            audio_inputs.append(f'[{input_count}:a]volume=0.10')
            input_count += 1

        # Filtre vidéo avec captions
        vf = subtitle_filter

        if audio_inputs:
            if len(audio_inputs) == 1:
                filter_complex = f"{audio_inputs[0]}atrim=0:{duration}[aout]"
                if music_path and not voice_path:
                    filter_complex = f"[1:a]volume=0.10,atrim=0:{duration}[aout]"
                cmd += [
                    '-vf', vf,
                    '-filter_complex', filter_complex,
                    '-map', '0:v',
                    '-map', '[aout]',
                ]
            else:
                # Voix + musique : mixer
                filter_complex = (
                    f"[1:a]atrim=0:{duration}[voice];"
                    f"[2:a]volume=0.10,atrim=0:{duration}[music];"
                    f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
                cmd += [
                    '-vf', vf,
                    '-filter_complex', filter_complex,
                    '-map', '0:v',
                    '-map', '[aout]',
                ]
        else:
            cmd += ['-vf', vf, '-an']

        cmd += [
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '20',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-r', '30',
            output_path
        ]

        print(f"Lancement FFmpeg final...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            print("FFmpeg stderr:", result.stderr[-2000:])
            raise Exception(f"FFmpeg échoué: {result.stderr[-500:]}")

        print("Vidéo finale générée")

        # ===== 9. UPLOAD VERS SUPABASE =====
        sb = create_client(supabase_url, supabase_key)
        filename = f"renders/{project_id}/final.mp4"

        with open(output_path, 'rb') as f:
            video_data = f.read()

        sb.storage.from_('videos').upload(
            filename,
            video_data,
            {'content-type': 'video/mp4', 'upsert': 'true'}
        )

        url_data = sb.storage.from_('videos').get_public_url(filename)
        public_url = url_data if isinstance(url_data, str) else url_data.get('publicUrl', '')

        print(f"Vidéo uploadée: {public_url}")

        # Mettre à jour Supabase
        sb.table('videos').update({'video_url': public_url}) \
            .eq('project_id', project_id).eq('generated', True).execute()
        sb.table('projects').update({'status': 'done'}) \
            .eq('id', project_id).execute()

        return public_url

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
