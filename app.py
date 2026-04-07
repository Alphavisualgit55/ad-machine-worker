import os
import json
import math
import subprocess
import tempfile
import requests
import threading
import time
import random
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
SUBMAGIC_KEY = os.environ.get('SUBMAGIC_KEY', 'sk-XXXXX')
SUBMAGIC_URL = 'https://api.submagic.co/v1'
FILM_BURN_URL = os.environ.get(
    'FILM_BURN_URL',
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/assets/film_burn.mp4'
)

# --- ROUTES ---
@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Ad Machine Worker', 'status': 'running'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'ffmpeg': 'ok', 'film_burn': bool(FILM_BURN_URL)})

# --- SUPABASE HELPER ---
class SB:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.h = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }

    def update_project(self, pid, data):
        try:
            requests.patch(f"{self.url}/rest/v1/projects?id=eq.{pid}", headers=self.h, json=data, timeout=30)
        except: pass

    def update_video(self, pid, data):
        try:
            requests.patch(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.true", headers=self.h, json=data, timeout=30)
        except: pass

    def get_sources(self, pid):
        try:
            r = requests.get(f"{self.url}/rest/v1/videos?project_id=eq.{pid}&generated=eq.false&select=*", headers=self.h, timeout=30)
            return r.json() if r.ok else []
        except:
            return []

    def upload(self, bucket, path, data, ct='video/mp4'):
        try:
            h = {
                'apikey': self.h['apikey'],
                'Authorization': self.h['Authorization'],
                'Content-Type': ct,
                'x-upsert': 'true'
            }
            r = requests.post(f"{self.url}/storage/v1/object/{bucket}/{path}", headers=h, data=data, timeout=300)
            print(f"  SB upload {path}: {r.status_code}")
        except Exception as e:
            print(f"  SB upload error: {e}")

    def public_url(self, bucket, path):
        return f"{self.url}/storage/v1/object/public/{bucket}/{path}"


# --- RENDER ROUTE ---
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
    sb_url     = data.get('supabaseUrl')
    sb_key     = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Données manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, sb)
            print(f"[{pid}] DONE: {url[:60]}")
        except Exception as e:
            traceback.print_exc()
            print(f"[{pid}] ERROR: {e}")
            try:
                srcs = sb.get_sources(pid)
                if srcs:
                    sb.update_video(pid, {'video_url': srcs[0]['video_url']})
                sb.update_project(pid, {'status': 'done'})
            except: pass

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'success': True})


# --- UTILITIES ---
def dl(url, path):
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)

def get_dur(path):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
                       capture_output=True, text=True)
    return float(json.loads(r.stdout)['format']['duration'])

def interleave_clips(clips_by_video):
    result = []
    max_len = max(len(c) for c in clips_by_video) if clips_by_video else 0
    for i in range(max_len):
        for vc in clips_by_video:
            if i < len(vc):
                result.append(vc[i])
    return result


# --- VFX & FILM BURN ---
def apply_vfx(video_path, tmp, duration, film_burn_path):
    if not film_burn_path or not os.path.exists(film_burn_path):
        print("  VFX: no film burn file, skipping")
        return video_path

    burn_dur = get_dur(film_burn_path)
    output = f"{tmp}/vfx.mp4"

    # positions aléatoires pour burns
    positions = sorted([round(random.uniform(0.15*duration, duration-0.15*duration-burn_dur), 1) for _ in range(3)])
    print(f"  VFX burns at: {positions}s")

    cmd = [
        'ffmpeg', '-y', '-i', video_path, '-i', film_burn_path,
        '-filter_complex', f"[0:v][1:v]overlay=enable='between(t,{positions[0]},{positions[0]+2})'[vout]",
        '-map', '[vout]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(duration), output
    ]
    subprocess.run(cmd, capture_output=True)
    return output


# --- SUBMAGIC PROCESS ---
def submagic_process(video_path, pid, template):
    headers_sm = {'x-api-key': SUBMAGIC_KEY}
    valid = ['Hormozi 2','Hormozi 1','Hormozi 3','Hormozi 4','Hormozi 5',
             'Beast','Sara','Karl','Ella','Matt','Jess','Nick','Laura',
             'Daniel','Dan','Devin','Tayo','Jason','Noah']
    if template not in valid:
        template = 'Hormozi 2'

    with open(video_path, 'rb') as f:
        resp = requests.post(
            f'{SUBMAGIC_URL}/projects/upload',
            headers=headers_sm,
            files={'file': ('video.mp4', f, 'video/mp4')},
            data={'title': f'AdMachine-{pid[:8]}', 'language': 'fr',
                  'templateName': template, 'magicZooms': 'true'},
            timeout=180
        )
    if not resp.ok: return None
    sm_id = resp.json().get('id')

    for _ in range(60):
        time.sleep(5)
        r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
        if not r.ok: continue
        proj = r.json()
        if proj.get('status') == 'failed': return None
        if proj.get('transcriptionStatus') == 'COMPLETED': break

    exp = requests.post(f'{SUBMAGIC_URL}/projects/{sm_id}/export',
        headers={**headers_sm, 'Content-Type': 'application/json'},
        json={'width': 1080, 'height': 1920, 'fps': 30}, timeout=30)
    if not exp.ok: return None

    for _ in range(120):
        time.sleep(5)
        r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
        if not r.ok: continue
        proj = r.json()
        url = proj.get('directUrl') or proj.get('downloadUrl')
        if proj.get('status') == 'completed' and url:
            return url
        if proj.get('status') == 'failed':
            return None
    return None


# --- MAIN PROCESS ---
def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, sb):
    with tempfile.TemporaryDirectory() as tmp:
        # --- DOWNLOAD CLIPS ---
        clips_by_video = []
        clips_per_video = math.ceil((math.ceil(duration / 3.0)+2) / max(len(video_urls), 1))
        for i, url in enumerate(video_urls[:8]):
            src = f"{tmp}/src_{i}.mp4"
            dl(url, src)
            clips = []
            src_dur = get_dur(src)
            start = 0.0; c_idx = 0
            while start + 1.5 <= src_dur and c_idx < clips_per_video:
                out = f"{tmp}/v{i}_c{c_idx:03d}.mp4"
                cd = min(3.0, src_dur - start)
                subprocess.run([
                    'ffmpeg','-y','-ss',str(start),'-i',src,'-t',str(cd),
                    '-vf','scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
                    '-r','30','-c:v','libx264','-preset','ultrafast','-crf','20','-an',out
                ], capture_output=True)
                clips.append(out)
                start += 3.0; c_idx += 1
            clips_by_video.append(clips)

        interleaved = interleave_clips(clips_by_video)
        needed = math.ceil(duration / 3.0)
        selected = [interleaved[i % len(interleaved)] for i in range(needed)]
        concat = f"{tmp}/concat.txt"
        with open(concat, 'w') as f:
            for c in selected: f.write(f"file '{c}'\n")
        assembled = f"{tmp}/assembled.mp4"
        subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',concat,
                        '-t',str(duration),'-c:v','libx264','-preset','ultrafast','-crf','20','-r','30',assembled],
                       capture_output=True)

        # --- MIX AUDIO ---
        output = f"{tmp}/final.mp4"
        cmd = ['ffmpeg','-y','-i',assembled]
        if voice_url: voice_path = f"{tmp}/voice.mp3"; dl(voice_url, voice_path); cmd += ['-i',voice_path]
        if music_url: music_path = f"{tmp}/music.mp3"; dl(music_url, music_path); cmd += ['-i',music_path]
        cmd += ['-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k','-t',str(duration), output]
        subprocess.run(cmd, capture_output=True)

        # --- VFX ---
        if vfx and FILM_BURN_URL:
            film_burn_path = f"{tmp}/film_burn.mp4"
            dl(FILM_BURN_URL, film_burn_path)
            output = apply_vfx(output, tmp, duration, film_burn_path)

        # --- SUBMAGIC ---
        final_url = submagic_process(output, pid, style)
        if final_url:
            sb.update_video(pid, {'video_url': final_url})
            sb.update_project(pid, {'status': 'done'})
            return final_url

        # --- FALLBACK SUPABASE ---
        filename = f"renders/{pid}/final.mp4"
        with open(output, 'rb') as f: video_bytes = f.read()
        sb.upload('videos', filename, video_bytes)
        final_url = sb.public_url('videos', filename)
        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})
        return final_url


# --- MAIN ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
