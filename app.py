import os, json, math, subprocess, tempfile, requests, traceback, threading, time, random, base64
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUBMAGIC_KEY = 'sk-b0e3311c51f0d1251a5e43cdb7086fb05fe4cec827a848ad47bd2905a3bb7643'
SUBMAGIC_URL = 'https://api.submagic.co/v1'

# ─── OVERLAY VFX ─────────────────────────────────────────────────────────────
# Upload ton overlay (film burn, glitch, VHS...) dans Supabase Storage
# bucket: videos / dossier: overlays/
# Le fond NOIR est rendu TRANSPARENT via le mode blend 'screen'
VFX_OVERLAYS = [
    'https://lowkevqfsfhhcaebqkxi.supabase.co/storage/v1/object/public/videos/overlays/filmburn.mp4',
]
# ─────────────────────────────────────────────────────────────────────────────
FILM_BURN_URL = os.environ.get('FILM_BURN_URL', '')

# Filigrane Ad Machine encodé en base64
WATERMARK_B64 = "iVBORw0KGgoAAAANSUhEUgAAAZAAAABaCAYAAACWuwCqAAAZSUlEQVR4nO3dd1wTdx8H8F8mYYRAIOwhIDIUFAQnioIKiBNw1FG11urTPvXpsI7n6bbLPh1WW7VqrbbWYt1VVNQ6EJUlgoMhe29IIEB2nj98sCHcJSEEcoHv+9U/yuXu+F3U+9z39/vdHQnpmIt1yGFd7xMAAEDflTcmr9bl/kjabghBAQAAg4O2wdLrAIHgAACAwam3QaJxgEBwAADA0KBpkKgNEAgOAAAYmtQFCVnVhxAeAAAwdKnLANwAgfAAAACgKgswAwTCAwAAQBe8TOgRIBAeAAAAlGFlg8oxEAAAAABPt1lYuqw+Xo+8skpX+1K2+/KsI/21bwAAAPgUZ2YZXAUC4QEAAMTwPEAMpfoAAACgP4pZYVAVCFQfAABAHFSEYOYV0b25+aWRb7yzxld5+VefH3y8+5sjufpo01A2zM3J7Fba71HKyx9l57fMmfHyNUP5HQBoy8U65HB5Y/Jqqr4boil9Vh/X7x6N9PB0ZeJ9Pn3CssvFRRVtA9kmXbubeSLa0dnOBO/zzz/e+3Df7mP5muxr5573xi1cNMsV7/PrV+/VrFm2OVmbdgIAiEPnXViDbfxjdIAPW1V4IIRQzJJI3JPlYPHimoXDKRSy2menWXPYjDnzpzsPRJsAAPplEGMg+qw+YhdHqA2HmLhZriSS1q9WMQiOznYmMyImO6hbb/mqee40Os0g/l4BAPoG/qGrQKVRyXNjZqi9mnZ0tjMZP2kMZyDapE9r1sUNV/U5lUYlr1i9wGOg2gMA0C/Cj4Hos/oImzHBjs1mGWmybuySyGEpdx409Heb9GliSKCNl487Kz+3mIf1efTcaU42tlaMgW7XYFRaUsl35Uw5oe92AKAKGe7/wBe7OHKYputGz53mxGAYUfqxOYSwam0MbhWirkIBAAweLtYhhwldgeiz+mBZMOlhsybZKy9v53dIkm6m10bNCXVSXG5qZkKNiJ7qeO7U1XJNfweNTiMvXR7tFj1vutMIbzcW09yM1tjQIsjLKeKdPXW1/PyZvypkMplcF8ejLbFILFMc04hZHOH6xfZ9D1t5fLHiev5jvC0DgkZaqdpWHUs2iz7Sz9NypJ+nxUi/ERZu7k5MWztrBtPcjGZkRKeIxWIZv61dXFvT2JnzuICbfCuj/nJCUpVQKJL25phIJBKaOi3Ybsq0YNvA4FFW9g42xhaW5nQKhUxqauQKmxpbhE/zSlqTkzLqkm9l1NXXNQl6s3+EEPLycWctWR7tFjp9vK29A8eERCajmqq6zqSb6bX798Q/ra6s61C1fW+m8Wqybl/bo4hKo5KjokMdJ08dazNmrK8Vh2NpxGIx6UKhSNrS0irKeVTATb59v/7MicSyttZ2sfo9AkNF6ADRp3kLw53pGCe/q5eTqy+cu1GhHCAIIRS7JNJV0wDx9nFn7T20faL7cJduM7wcHG1MHBxtTMJmTrRfsy7O818bPk7V/ij6LuHPG5UL4ma5dP1sbMygLFk+x+3AnviniuutWRfnqbzthXM3KlRN51V2LfmXCGsOG7cLjEIxojAYRhRrDpsxyn+E5eJl0W4tzTzRR+/uyjpz4kqZJr9j9txpTpvfXe/n5u5khvV51/fvN9rLMnZJpGtVRW3HpMBFCZoeA4VCJm3+z3q/da8uHaE8a83D05Xp4enKfGHlXPd/rvsw5erl5GpN96stXbdnyfI5bm9vXTvS1s7aWPkzGp1GNmOa0pxd7E0joqc6bv73K6N++O7XvH27j+XJ5Xq9DgL9hLCD6Pq+6zx2MfbU3PNnr1fcup5ay2/reWUVMjXIVpMxAE+vYea/n90VqhweygLG+rLjz+4KdXaxN9W85boV/1tCSWenoNsV/qq1McPJ5L9PRlbWlkZzFoR1m2xQWlLJv3HtXm1/t8+SzaLv3PPeuFdee8FL1XpkMpm049stQXsPbZ+IFx59RaVRybv3fzhhw+vLvFRNeWYwjCh7f/p4oqfXMPP+aEd/tIdKpZB2/fjB+C93bgnCCg8sTHNT2tb3Nvj9dPSLEJiZNzjp7A91MI1/uLk7mSl3xyCEUFtru/jWjbRakUgsu3r5To+rNQqFTFoQp/qKm0qjknf/+MF4TQfnHRxtTGL1eJ8Jj9smUr66d3axNw2bOfF5997yVfM9lKu1IwdPF8oH8LJz2/sb/Lx93Fl4n3/0+RsBS1fMcevPNvj4erCi503vUZliodFp5K3vbfAzlPZ8+t9NY+fHzHDB+1yV8FmT7Hd8szlIm20BsRHyqkDv1ccS7MHzxItJVWKRWIYQQhfOXa/E2VblyX7p8jluPiOHW2B9dvqPxLIZISsThzuGnZoUuChh97e/5Op7DAQhhA4fPFWovKxrwPzZ1N357oqftbd3Sv74/WKptr8v9V52w/vbdj6YO3PdtUDvuX962E87OcIp/PTU4KWX3tn4eXppSSVfeRsymUxa/89lmFVISGiQ7YsvLcScXszjtom+/HT/o/DJKxJHOIWfHuUReXZB1IbrB/Yef9rRIZBoewyamD5jor2VlYVGFxIDAa8902dMtMcKX4FAKN397S+54ZNXJHq7zDw9YXTMhXf+9UVGQ31zjzGj2CWRrqHTx9n1V9uBfsAYiBISiYQWLorAvNI6f/Z6Rdf/37qRVtvW2i5mmpvSFNfx9nFn+Y7ytMh5XMDF2gfeiezCuesVb772SVrXz1UVtR1ffXbgsaBDIH3nP6+M0upgdCQ/t5h3LzmzfmJIoE3XspDQINvhI1zNR47ytFDu0jgVf6kUq4tPnZS7WQ3ff/NLbm5OUY9pwhKJVFpWWsUvK63iX7+WUpuUHh9lamrc7e9vaBj2CWrTtnWY319DfbMgNvrVG2WlVc8DSSgUSR9kPGl6kPGk6cfvj+W/tWXtyN4eR+q97IYvtu979OThUy7bikV/7Y0XfVau6Xl/DIVCJo0O9GFfv3qvpre/YyDb8+bmns9hQwihDWveu3fj2t/rdnYKOv84llDy+OHTlvNX9odTadRuF6gbN632uXUjrd+7NcHAIVwFou/qY9wEf46Ts12PMQduS6soOSmjvutnsUgsu3LpNuagYwzO3eu2dtbGXjjdLF9/fvAJ1vL9e+LzlWc86cPPGFXIqrWxw1e/HNtt6q5cLsdcVxOvvfxBClZ4KGtsaBY8ysprUV5uZW1p5OBk2+15Xnb2HOOAsb5srP28t+WbB4rhoayhvlmw7e3/3tek7V2yMnObV8S9mZSZ/rhJKBRJa6obOt/d/HVmVmZuM9b66h6T01d9bY+dPcd4dIBPj+8vM/1xk2J4KMp5XMB9gnEBFRg00sqSzaJreSiAgHRSgQym8Q+8LqjEi0lVErFEprjswrnrFVjrL4id6fL5R3seSqXdu59GB3hbYu27qqK2A+9hjCKRWJZyN6thVlSI2seI9Kdrl5OrqypqOxQfuPjCijluyoOjSTfTa4sLy7V+sCSNTiNPCxtvN3X6ODsvH3dzF1cHMybThGpsYkzV5FlcbDbLSHFK6viJozGfENDczBMmXrxdpW078Xz56Y+PRP/v5lSUejerYUxgzxOxuVIFS7T24H1/gcGjrMoabi/qTVvIZDLJb7SXZdKNtLrebAeIi1BdWPquPoyM6JTZc7EHHRW7r7ok3Uyva+XxxeYss27/6Dg2bMaUaeNsb/6VUtt9OfYMrbLSatyr4Gef418lDxSpVCb/5eczhdve/4d/1zKsmTWHD5zUqvpACKHIOaGOH3yycYyDow3uU4HVYZp3/7OwsbPG/M5zHhVwdT2+1NkpkOI9jaC5mSvEWt6fN5/qoj1435+2rDmW8KSCQYRwXVj6FDF7ioPymAZCz65W7yVn1isvl4glssRL2FexWAPxpmYmmFebytNklQnUfD5Q4o9eKBEIhLhteTZ1N0Wr/vyFi2a57ju0fVJfwgOhZ/34ij+zWGaYXSZtWozRqFNZXtuuXHV2EQl7VgEIIUTqx6dw6qI9eN+ftsyY/VtxgYHV5wpEV91X+q4+EMKffcVms4yKam7G9WZfs6JCHMyYpjTFweR2fgfmScvYmKHyKpSh5vOBwm1pFZ09ebUcbzrs/6fu9nq/JiYM6vYv3groj3Mpj8cXYS1n9sOJTFW4SvUwm04X7cH7/rQ12J9aPdQQqgtLn6w5z7qddLU/BsOIEj1vutPx3y6UdC1rbGjG7DZwHeag8sY212GO/XLjmzYOHzhZgBUgfZm6Gxo23g6r8pPJZPK9u37LP3f6WnlVZV2HYhgfPfHN1CnTgtX+edXXNmI+hsTXz9OCTCaTiDBNmsiwpuQi9Kwa3fLmjoyBbg8gFkJ0YRGh+lgYN9NFk0Ha3lAeYMeb+eLobGfi7uGMORuHTqeRJxDoUfG5OUW8lLtZPfrVtZ26ixBC7sNdMAPy+G8JJV9+uv9Rfm4xT3nfeN+XstR72ZhjAGw2yyhi9hTH3rd2aEm7l9WItXxa+Hg75Wm6YOghRAXS124wXQRQf9zt3TUluLKith0hhOpqGzvzc4t5WFN539q6duQ/132Yorz8lVeXeikP0uvb4QMnCxVDrS9TdxFCiIZzIsLrgnlxbcxwVa/fVVRb09D54H5OM9ZU3u073grIeVzIxZukwLJg0t/esnbk+9t2PtDkdw1G1VX1HY8fPm0Z5T+i2wxCO3uO8dZ31/t98sEP2er24ebuZLZizUKPpsYW4Z7vjub1X2vBQOtTgBBh+q4uwsPbx52Fd3d4X5BIJBSzONJ119eHc7qW/frzmaJPvnw7UHnduQvCncUiieyH737NKyut5nNs2IxlK+e6v/bGSm9dt6uvLl24VanLd1VUlNe0Yy1fvmq+R0F+aevlhKSqjvZOiftwZ+aaVxZ5xuGMVeH5+ouDj4+e+Gaq8nKODZtx/uqB8H3fH8tPvHi7qqKsup1Gp5Hd3J2YMyNDHNasixvOb2uXDOUAQQihb3b89OTQbztClJeve3XpCE9vN/MjB08VZmfmNnO5rSJjE2Mqm82ie/u6s/wDfNgzIiY7+Ph6sBBCaO+u3yA8BhlCVCD6Frc0ahjW8lYeXxw8asF5VYORXXbv/3DCvIXhPd5eGLM4oluAxP+WULJ81Xx3rMCKWRzhincT4mB281pKrUAglCpPIaXTaeTPvto09rOvNo3ty/5v30yv+/Xns0VYd1+zLJj0Le+u99vy7nrM50Dx29r79XEmhuCvK3drTsRfKl2E8e9kWth4u2lh4+ERJUOUQfdh6qL6oFDIpPmxMzEfXXLmRGKZJuGBEELxR88XYy13c3cyCwwe9fzBjGKRWPb6+o9SW5p5Gs1uqalu6Dx1/LJGjyo3VE1NXOHur4/karr+/fTHTWkp2Zh983je3/rtA8UJDaB3tr65I+Pc6Wsav+sGDA0GGyC6GnifEhqM+wj2349qfsK5ezuzvrysGrMrJlapqijIL21dumDjTXV3bD/Kzm9ZumDjTbwunsHk+52/5u7bfSxf3TTgK5eSq1e/8M7tzk5hryoDmUwm3/zGjoxX175/D+thjEA1iUQq37j+o9S3X/8svTcvnwKDm9ZdWPoc/9DlrC28LqPsB7nNuU8KuZruRy6Xo+NHL5RgPfhw7oJw5w//sytLrPBIibzcYt6s0NVXXlgxxy16fpizp9cwc3OmKa2piSvMyyni/Xnmr/KzJ6+U490INhh9/vHehxfP36xc+dJCj/ETR3Ns7awZEolU3tjQLMhMf9J09tTVcuW7+3sr4c8blRfP36wMnT7Obsr0cbaBY32tHJxsTVgWTDqFQul6I6EgP7e49c7t+3XJtzJ63EA6lJ2Mv1R65kRiWdjMSfYhoUG2YwJ92fYOHGOWBZNOpVBIrW3t4rZWvriVxxc3NbYI83NLeHm5RbzcJ0W8woKyVn23H+gWSdt3og+WAAEAAKAdg+vCgvAAAABiMKgAgfAAAADi0CpA9NF9BeEBAADEYlAVCAAAAOIwiACB6gMAAIiH8AEC4QEAAMTU6wAZyPEPCA8AACAuwlcgAAAAiEnrGwk1pW3FAtUHAAAQW79WIBAeAAAweBGuCwvCAwAADAPhAgQAAIBh6LcA0ab7CqoPAAAwHISpQIZaeKyK2e60YOZGW1XrLJ37b4e4qE2Efdsb0dsHAOhfhAgQooWHg60nY8eW696vrtiN+a6QxdFb7Ncv+xbzLYar4z51Wrf0qx6vtkUIIRsrV/qOLde9PYeNNdVle3VF3XEDAIAieCc6hvGjoy0qa/IFLg6+xjZWrvT6pjKNXj+LEEJp2Re5L8Z87GTJsqO18GrFip8F+0dZtLTWiQvLMtsLSu8T7i2DfTluAMDQ0y8B0pvxD6JVHzSqEWmMb7j57+c/qQ4JirMM9o+ySLixT+O30uUVpbTz21skQX6RrKvJh5+/t5tCppICR81i3cs82yKXy9GqmO1OvLYG8dmru+oQQohKpZPmz3jddrTPdHOhqFOWV5TCN6IZkyUS0fO3GJIQCYUEx7EnBs63ZDE51GZutfh2+snmtOwE7vPfQ6GSIqe+zAkYOcPchGFOqWkoEl68ub++qOyByteQqjtuTdo3wi3YNDL0ZY4N24Xeym+UpGYn8G6n/dEkk8uwfykAwKDptQuLaOGBEEJ+XlPNBcJ2aX5xGj816wJ37KhZLAqZStJ0e5lMKr//KJEX5BfJIpH+3sxn+EQzU2MWJePRZR7WdlGh6zgergGm+469Wf7tobUlIrFA7us52UxxnfDJK62D/Wezfv/zk6oPv5tXcCZxZ23k1LWc0T5h5l3rRExZy/H3nsb85fT7Vdu/jy3MK0rhv7ToC2c2y57Wl+NW1z463Zj8YszHThkPL/E+2r2g8MDxdyqMGWZkO4475vvmAQCGjxBjIEQybnQ0K/3hJZ5cLkc5BXf4crlc7us5yUz9ln9Lf3iJZ2FuQ1Mc6wj2n816WpLezm2tFyuvT6MakSaMmWt5+dbB+uq6AkFHZ6s04ca+el5bo6RrHSqVTgodv5R9/q/v6ytq8gRisVBWXJHdcTfzbEuwfxSra53JQTGWiUk/NZZX53R2CtqkV5OPNNY3lQknB8WwtT1uTdpnZmJBoVGNSDmFd/lisVDWwqsVX751sKG6vlDQm+8OAGA4dN6FpWn3FRGrDytLR7qr0yiT+Auf1SCEkFQmkWc8uswL9p9t8Sg/qU3T/TS2VIpKKh52BPlFsZ6WZLSbm1lRR7gHmx0793EV1vpsC3s6lUonVdbmPz/ZymRSeXV9wfOfbaxcjeg0BvmlxTucEXrWnfXsPxJq5taIEULIysKeTqXQSOU1uZ2K+y+vyhXYWg+ja3vcmrSvhVsrzi9Oa39t5Q+u2bnXW4vKsjoKyzLbxRKhXNPvDQBgWPQyiE7E8EAIoXH+s1lkEhlt+0e8h+JyuVyOLMxtaFjVA5607ARebNQmOxMGkxLkF8nq7GyV5hTc5avcSMWptqs7bOehtSV1jWVCnLVwtn12DHjUHbcm7ZMjOfr5xLYKN2d/E0+3saYRoWs5McZv2R08vqkCv70AAEM24AFC1PAgkymksX4RrGN/bq/Ozr3RqvjZhmU7XYL8IlnX7vzSiLe9skf5Sa3zZ260DRg50zzIP8ri/uMrPKlMgnkKbubWiCRSsdzJ3ovRzHtWTZDJFJKDjSfjaUkaHyGE6pvKRGKJUO7lPt4U74TcxK0WSaRiubO9D6OxufL5DCpne29GccXDTqxtNDnuW6nHm9S1D6FnIVJckd1RXJHdkZh0qOH1VXuHBflFsXozCQEAYDh0Ogaij3el64q3xwRTE4Y5Jb84tUeV8KQgmR/kH9VtUFwdsUQoz8r5q3VmyCprKwsHWvrDS1xV66Y8+JMbGfqyjYOtJ8OEwaRET99gw2JaPw94sVgou5Ua3xQ+6UXrMb5h5gwjE7KluS1tQsA8i/BJK6wQQkgiEcnvZJxuiZj6EsfZ3pthbGRGCZ+00trGepjRnYzTzdoet0QqUts+Fwdf45iIt+zsbTyMqFQ6ycFmOIPF5FCbuNUwFRiAQWpAKxCiVh8IITTOf7ZFYVlmh0DY0WPO6eOnyW1zwl618Rw21vRpSYbG92+kZSdwJwTMsyiretKp7p6Ky7cO1hvRTcj/WLbTRSjqkOUWpfBzCu50O6lfTT7SyG/nSsMmrrRaPHurfSu/UZJblML/S6EySrz9UwOJREKrYz91MmYwKTUNRcJDJ7ZWdFUO2h63uvZV1uR12tu4Gy2J3upgzXai89tbJKlZF7ipWee5mn5fAADDotP3gaiqQIgcHgAAAHpPZ11YEB4AADC0wH0gAAAAtNLvAQLVBwAADE46CRC87isIDwAAGLzI5Y3Jq/tjxxAeAAAweJU3Jq+GMRAAAABa6ZcAgeoDAAAGvz4HiPL4B4QHAAAMDTqtQCA8AABg6IAxEAAAAFohI/RsNF2bjRW7r6D6AACAoaErM3RSgUB4AADA0PM8QLStQiA8AABg6FDMCq0rEEN+9wcAAIC+6xYgva1CoPoAAIChQzkjtK5AIDwAAGBo6xEg/fVsLAAAAIYLKxswKxAIEQAAAF3wMgG3CwtCBAAAgKosUDkGAiECAABDl7oMIGm6IxfrkMN9bQwAAADi07R40DhAukCQAADA4NTbXqdeB0gXCBIAABgctB2u0DpA8ECwAAAAMel6XPt/JEURFIbyKBAAAAAASUVORK5CYII="

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
    user_id      = data.get('userId', '')
    app_url      = data.get('appUrl', 'https://admachine.netlify.app')
    sb_url       = data.get('supabaseUrl')
    sb_key       = data.get('supabaseKey')

    if not pid or not video_urls:
        return jsonify({'error': 'Donnees manquantes'}), 400

    def run():
        sb = SB(sb_url, sb_key)
        try:
            url = process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, user_id, app_url, sb)
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
    """Filigrane image Ad Machine — plan gratuit uniquement. Pleine largeur, centré."""
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

    # Filigrane agrandi pleine largeur (1080px), centré verticalement
    # scale=1080:-1 = pleine largeur en gardant le ratio
    res = subprocess.run([
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', wm_path,
        '-filter_complex',
        '[1:v]scale=1080:-1,format=rgba,colorchannelmixer=aa=0.70[wm];'
        '[0:v][wm]overlay=0:(H-h)/2:format=auto[vout]',
        '-map', '[vout]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart', '-t', str(duration), output
    ], capture_output=True, text=True, timeout=300)

    if res.returncode != 0:
        print(f"  Watermark error: {res.stderr[-200:]}")
        return video_path

    print("  Watermark added (free) OK")
    return output


def apply_vfx(video_path, tmp, duration):
    """
    VFX Pro: applique l'overlay filmburn 3 à 5 fois aléatoirement
    - Fond noir = 100% transparent via blend screen
    - Audio overlay mixé à 70% du volume
    - Positions aléatoires dans la vidéo
    """
    import random
    output = f"{tmp}/vfx_output.mp4"

    try:
        actual_dur = get_duration(video_path)
        active_overlays = [u for u in VFX_OVERLAYS if u.strip()]

        if not active_overlays:
            print("  [VFX] Aucun overlay configuré — fallback FFmpeg")
            raise Exception("no overlay")

        overlay_url = random.choice(active_overlays)
        overlay_path = f"{tmp}/vfx_overlay.mp4"
        print(f"  [VFX] Downloading overlay...")
        dl(overlay_url, overlay_path)
        overlay_dur = get_duration(overlay_path)
        print(f"  [VFX] Overlay dur={overlay_dur:.1f}s vidéo={actual_dur:.1f}s")

        # Nombre d'applications aléatoire: 3 à 5
        nb_effects = random.randint(3, 5)
        print(f"  [VFX] Applying {nb_effects} overlays...")

        # Calculer les positions aléatoires (bien espacées)
        margin = overlay_dur * 0.5
        if actual_dur <= overlay_dur * 2:
            # Vidéo courte: positions réparties uniformément
            positions = [i * (actual_dur / nb_effects) for i in range(nb_effects)]
        else:
            positions = sorted(random.sample(
                [round(x * 0.1, 1) for x in range(int(margin*10), int((actual_dur - overlay_dur)*10))],
                min(nb_effects, int((actual_dur - overlay_dur - margin) * 10))
            ))[:nb_effects]
            # Compléter si pas assez
            while len(positions) < nb_effects:
                positions.append(round(random.uniform(0, max(0.1, actual_dur - overlay_dur)), 1))
            positions = sorted(positions[:nb_effects])

        print(f"  [VFX] Positions: {[round(p,1) for p in positions]}")

        # Construire le filtre FFmpeg:
        # Chaque overlay est appliqué en mode screen à sa position temporelle
        # avec enable='between(t,start,end)'

        # Input: [0]=vidéo principale, [1]=overlay
        # On applique chaque instance avec overlay conditionnel

        # Construire filter_complex avec N applications de l'overlay
        filter_parts = []
        inputs = ['-i', video_path, '-i', overlay_path]

        # Pour chaque position, on crée un segment de l'overlay
        overlay_segments = []
        for i, pos in enumerate(positions):
            end_pos = pos + overlay_dur
            seg_label = f"ov{i}"
            # Prendre l'overlay, le trimmer et le positionner dans le temps
            filter_parts.append(
                f"[1:v]setpts=PTS-STARTPTS+{pos}/TB,trim=start=0:duration={overlay_dur}[{seg_label}]"
            )
            overlay_segments.append((seg_label, pos, end_pos))

        # Appliquer chaque overlay en blend screen sur la vidéo principale
        current = "[0:v]"
        for i, (seg_label, pos, end_pos) in enumerate(overlay_segments):
            out_label = f"[v{i}]" if i < len(overlay_segments) - 1 else "[vout]"
            # blend mode screen: fond noir = transparent
            filter_parts.append(
                f"{current}[{seg_label}]blend=all_mode=screen:all_opacity=1.0:shortest=0:repeatlast=0"
                f"{out_label}"
            )
            current = f"[v{i}]"

        # Audio: mixer la voix principale + overlay audio à 70%
        # Créer N segments audio de l'overlay aux mêmes positions
        audio_parts = []
        for i, pos in enumerate(positions):
            audio_parts.append(
                f"[1:a]adelay={int(pos*1000)}|{int(pos*1000)},atrim=start=0:duration={overlay_dur},volume=0.70[a{i}]"
            )

        # Mixer tous les audios overlay avec l'audio principal
        audio_labels = "".join([f"[a{i}]" for i in range(len(positions))])
        if audio_labels:
            audio_parts.append(
                f"[0:a]{audio_labels}amix=inputs={len(positions)+1}:duration=first:normalize=0[aout]"
            )
            audio_map = ['-map', '[aout]']
        else:
            audio_map = ['-map', '0:a']

        filter_complex = ";".join(filter_parts + audio_parts)

        res = subprocess.run([
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', overlay_path,
            '-filter_complex', filter_complex,
            '-map', '[vout]',
            *audio_map,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
            '-pix_fmt', 'yuv420p', '-r', '30',
            '-c:a', 'aac', '-b:a', '192k',
            '-t', str(actual_dur),
            output
        ], capture_output=True, text=True, timeout=400)

        if res.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 10000:
            size = os.path.getsize(output) / 1024 / 1024
            print(f"  [VFX] OK ({size:.1f}MB) — {nb_effects}x filmburn")
            return output
        else:
            print(f"  [VFX] FFmpeg error: {res.stderr[-400:]}")
            return video_path

    except Exception as e:
        print(f"  [VFX] Exception: {e} — vidéo sans overlay")
        return video_path


def submagic_process(video_path, pid, template, use_vfx_transitions=False):
    """
    Submagic API v1 — Captions + MagicZooms + MagicBrolls
    Selon doc officielle: https://docs.submagic.co/api-reference/upload-project
    Les transitions (Film Burn, VHS, Glitch) ne sont PAS disponibles via API.
    Ce qui est disponible: templateName, magicZooms, magicBrolls, removeSilencePace, hookTitle, cleanAudio
    """
    headers_sm = {'x-api-key': SUBMAGIC_KEY}

    valid_templates = [
        'Hormozi 2','Hormozi 1','Hormozi 3','Hormozi 4','Hormozi 5',
        'Beast','Sara','Karl','Ella','Matt','Jess','Nick','Laura',
        'Daniel','Dan','Devin','Tayo','Jason','Noah'
    ]
    if template not in valid_templates:
        template = 'Hormozi 2'

    print(f"  [SM] Starting — template={template} vfx={use_vfx_transitions} key={SUBMAGIC_KEY[:12]}...")

    # Paramètres selon doc officielle Submagic
    # VFX Pro = magicZooms + magicBrolls (75%) + cleanAudio
    # Captions seules = magicZooms seulement
    form_data = {
        'title': f'AdMachine-{pid[:8]}',
        'language': 'fr',
        'templateName': template,
        'magicZooms': 'true',          # toujours: zooms dynamiques
        'cleanAudio': 'false',         # nettoyage audio (optionnel)
        'removeSilencePace': 'natural', # suppression silences naturelle
    }

    if use_vfx_transitions:
        # VFX Pro: magicZooms + removeSilencePace fast
        form_data['removeSilencePace'] = 'fast'
        print(f"  [SM] VFX mode: magicZooms + removeSilence(fast)")
    else:
        print(f"  [SM] Captions mode: magicZooms + removeSilence(natural)")

    try:
        with open(video_path, 'rb') as f:
            video_bytes = f.read()

        file_size = len(video_bytes)
        print(f"  [SM] Uploading {file_size/1024/1024:.1f}MB...")

        resp = requests.post(
            f'{SUBMAGIC_URL}/projects/upload',
            headers=headers_sm,
            files={'file': ('video.mp4', video_bytes, 'video/mp4')},
            data=form_data,
            timeout=300
        )
    except Exception as e:
        print(f"  [SM] Upload exception: {e}")
        return None

    print(f"  [SM] Upload: {resp.status_code} — {resp.text[:300]}")

    if not resp.ok:
        print(f"  [SM] Upload FAILED ({resp.status_code}): {resp.text[:300]}")
        return None

    try:
        sm_data = resp.json()
    except Exception as e:
        print(f"  [SM] JSON error: {resp.text[:200]}")
        return None

    sm_id = (sm_data.get('id') or sm_data.get('projectId') or sm_data.get('_id'))
    print(f"  [SM] Project ID: {sm_id} — keys: {list(sm_data.keys())}")
    if not sm_id:
        return None

    # Attendre transcription
    print(f"  [SM] Waiting transcription...")
    for i in range(40):
        time.sleep(5)
        try:
            r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
            if not r.ok: continue
            proj = r.json()
            status = proj.get('status', '')
            trans = proj.get('transcriptionStatus', '')
            if i % 4 == 0:
                print(f"  [SM] [{i+1}] status={status} trans={trans}")
            if status == 'failed':
                print(f"  [SM] Failed: {proj.get('failureReason')}")
                return None
            if trans == 'COMPLETED' or status == 'completed':
                print(f"  [SM] Transcription OK!")
                break
        except: continue

    # Exporter
    print(f"  [SM] Exporting 1080x1920...")
    try:
        exp = requests.post(
            f'{SUBMAGIC_URL}/projects/{sm_id}/export',
            headers={**headers_sm, 'Content-Type': 'application/json'},
            json={'width': 1080, 'height': 1920, 'fps': 30},
            timeout=30
        )
        print(f"  [SM] Export: {exp.status_code} — {exp.text[:200]}")
        if not exp.ok:
            return None
    except Exception as e:
        print(f"  [SM] Export exception: {e}")
        return None

    # Attendre rendu final
    print(f"  [SM] Waiting render...")
    for i in range(60):
        time.sleep(5)
        try:
            r = requests.get(f'{SUBMAGIC_URL}/projects/{sm_id}', headers=headers_sm, timeout=15)
            if not r.ok: continue
            proj = r.json()
            status = proj.get('status', '')
            url = (proj.get('directUrl') or proj.get('downloadUrl') or
                   proj.get('outputUrl') or proj.get('videoUrl') or proj.get('url'))
            if i % 6 == 0:
                print(f"  [SM] [{i+1}] status={status} url={'yes' if url else 'no'}")
            if status == 'completed' and url:
                print(f"  [SM] Done!")
                return url
            if status == 'failed':
                return None
        except: continue

    print("  [SM] Timeout — fallback vidéo locale")
    return None


def process(pid, video_urls, voice_url, music_url, voiceover, duration, style, vfx, is_free, with_captions, user_id, app_url, sb):
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
                        '-r', '30', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p', '-an', out
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
        # Ne pas couper ici - on coupera après avoir la durée exacte de la voix
        subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-r', '30', assembled
        ], check=True, capture_output=True)
        print("  assembled OK")

        for clips in clips_by_video:
            for c in clips:
                try: os.remove(c)
                except: pass

        # 3. VOIX + MUSIQUE
        # Nettoyer voiceover des titres parasites
        import re as _re
        voiceover = _re.sub(r'^[#\s\*]*[^\n]{0,60}\n', '', voiceover).strip()
        voiceover = _re.sub(r'[#\*`]', '', voiceover).strip()
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

        # Durée réelle = durée exacte de la voix off
        actual_duration = duration
        if voice_path:
            try:
                voice_dur = get_duration(voice_path)
                actual_duration = voice_dur
                print(f"  voice duration={actual_duration:.1f}s (target={duration}s)")
            except Exception as e:
                print(f"  get_duration error: {e}")

        if n == 1:
            cmd += ['-an']
        elif n == 2 and voice_path:
            cmd += ['-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k']
        elif n == 2 and music_path:
            cmd += ['-filter_complex', f'[1:a]volume=0.10,atrim=0:{actual_duration}[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += ['-filter_complex',
                    f'[1:a]asetpts=PTS-STARTPTS[v];[2:a]volume=0.10,asetpts=PTS-STARTPTS[m];'
                    f'[v][m]amix=inputs=2:duration=first:normalize=0[a]',
                    '-map', '0:v', '-map', '[a]', '-c:a', 'aac', '-b:a', '192k']

        cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', '-r', '30', '-t', str(actual_duration), output]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            raise Exception(f"FFmpeg mix: {res.stderr[-300:]}")

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  mix OK ({size_mb:.1f}MB)")
        try: os.remove(assembled)
        except: pass

        # 5. VFX Pro FFmpeg natif (zoom + grain + vignette) — indépendant de Submagic
        if vfx:
            print("  Applying VFX Pro (Ken Burns + film grain + vignette)...")
            vfx_output = apply_vfx(output, tmp, actual_duration)
            if vfx_output != output:
                output = vfx_output
                print("  VFX Pro OK")

        # 5b. VFX Pro → utiliser transitions Submagic au lieu de film burn maison
        # Le film burn FFmpeg est désormais remplacé par les effets Submagic natifs
        # (magicZooms + transitions activés dans submagic_process quand vfx=True)

        # 7. SUBMAGIC captions (optionnel) — passer vfx pour activer transitions
        submagic_url = submagic_process(output, pid, style, use_vfx_transitions=vfx) if with_captions else None
        if not with_captions:
            print("  Captions skipped by user")

        # Choisir la vidéo finale — fallback sur vidéo locale si Submagic échoue
        video_final = output  # défaut = vidéo locale
        if submagic_url:
            print(f"  Downloading Submagic output...")
            try:
                sm_local = f"{tmp}/submagic_out.mp4"
                dl(submagic_url, sm_local)
                if os.path.exists(sm_local) and os.path.getsize(sm_local) > 10000:
                    video_final = sm_local
                    print("  Submagic downloaded OK")
                else:
                    print("  Submagic file trop petit — fallback vidéo locale")
            except Exception as e:
                print(f"  Submagic download error: {e} — fallback vidéo locale")

        # Appliquer filigrane si plan gratuit
        print(f"  Applying watermark (is_free={is_free})...")
        if is_free:
            video_final = add_watermark(video_final, tmp, duration, is_free)

        # Upload sur Supabase
        filename = f"renders/{pid}/ad_machine_{pid[:8]}.mp4"
        print(f"  Uploading to Supabase...")
        with open(video_final, 'rb') as f: video_bytes = f.read()
        sb.upload('videos', filename, video_bytes)
        final_url = sb.public_url('videos', filename)
        print(f"  Upload OK: {final_url[:60]}")

        sb.update_video(pid, {'video_url': final_url})
        sb.update_project(pid, {'status': 'done'})

        # Notifier l'utilisateur par email si plan Business/Business+
        if user_id:
            try:
                requests.post(f"{app_url}/api/send-notification", json={
                    'type': 'video_ready',
                    'userId': user_id,
                    'videoUrl': final_url,
                    'projectId': pid,
                }, timeout=10)
                print(f"  Notification sent for user {user_id[:8]}")
            except Exception as e:
                print(f"  Notification error (non-blocking): {e}")

        return final_url


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
