"""語音發音。

* 使用說明：建置時預先用微軟神經語音（臺灣華語 曉臻）產生 MP3，放在 assets/voice/，離線也能播。
* 其他文字（報表重點朗讀等）：先試線上神經語音（edge-tts），沒網路時改用 Windows 內建的
  「Microsoft Hanhan」臺灣中文語音；macOS 用內建 say。
"""
import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import threading

from .settings import data_dir, resource_dir

VOICE = "zh-TW-HsiaoChenNeural"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def help_mp3(key):
    p = os.path.join(resource_dir(), "assets", "voice", key + ".mp3")
    return p if os.path.isfile(p) else ""


class _Mci:
    """Windows 內建 MCI 播放 MP3（不需額外套件）。所有指令都在同一條背景執行緒送出。"""

    def __init__(self):
        import ctypes
        import queue
        self.f = ctypes.windll.winmm.mciSendStringW
        self.buf = ctypes.create_unicode_buffer(128)
        self.opened = False
        self.q = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            s, box, done = self.q.get()
            self.f(s, self.buf, 127, 0)
            box.append(self.buf.value)
            done.set()

    def cmd(self, s):
        box, done = [], threading.Event()
        self.q.put((s, box, done))
        done.wait(5)
        return box[0] if box else ""

    def play(self, path):
        self.stop()
        self.cmd('open "%s" type mpegvideo alias zmsvoice' % path)
        self.opened = True
        self.cmd("play zmsvoice")

    def playing(self):
        return self.opened and self.cmd("status zmsvoice mode") == "playing"

    def stop(self):
        if self.opened:
            self.cmd("stop zmsvoice")
            self.cmd("close zmsvoice")
            self.opened = False


class Speaker:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.mci = _Mci() if os.name == "nt" else None
        self.token = 0
        # 手機版：由 mobile.py 接上 flet_audio 播放器與「向電腦要語音」的函式
        self.ext_play = None        # (mp3 bytes) -> None
        self.ext_stop = None
        self.ext_playing = None
        self.remote_tts = None      # (text) -> mp3 bytes

    # ---------------------------------------------------------- 播放
    def play_file(self, path):
        self.stop()
        if self.ext_play:
            with open(path, "rb") as f:
                self.ext_play(f.read())
            return
        if self.mci:
            with self.lock:
                self.mci.play(path)
        elif sys.platform == "darwin":
            self.proc = subprocess.Popen(["afplay", path])

    def playing(self):
        if self.ext_playing:
            return self.ext_playing()
        if self.mci and self.mci.playing():
            return True
        return bool(self.proc and self.proc.poll() is None)

    def stop(self):
        self.token += 1
        if self.ext_stop:
            try:
                self.ext_stop()
            except Exception:
                pass
        if self.mci:
            with self.lock:
                self.mci.stop()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    # ---------------------------------------------------------- 說說看
    def say_help(self, key, text):
        p = help_mp3(key)
        if p:
            self.play_file(p)
        else:
            self.say(text)

    def say(self, text):
        """朗讀任意文字（背景執行，不卡畫面）。"""
        self.stop()
        token = self.token
        threading.Thread(target=self._say, args=(text, token), daemon=True).start()

    def _say(self, text, token):
        if self.remote_tts:                     # 手機：請電腦產生語音
            try:
                data = self.remote_tts(text)
            except Exception:
                return
            if token == self.token and self.ext_play:
                self.ext_play(data)
            return
        mp3 = self._neural(text)
        if token != self.token:
            return
        if mp3:
            self.play_file(mp3)
            return
        self._offline(text)

    @staticmethod
    def _neural(text):
        cache = os.path.join(data_dir(), "voice_cache")
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, hashlib.sha1((VOICE + text).encode("utf-8")).hexdigest()[:20] + ".mp3")
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        try:
            import edge_tts

            async def run():
                await asyncio.wait_for(edge_tts.Communicate(text, VOICE, rate="+5%").save(path), timeout=12)
            asyncio.run(run())
            return path if os.path.getsize(path) > 0 else ""
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            return ""

    def _offline(self, text):
        if os.name == "nt":
            fd, tmp = tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "try { $s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'zh-TW') } catch {}; "
                  "$s.Rate=0; $s.Speak((Get-Content -Raw -Encoding UTF8 '%s'))" % tmp)
            self.proc = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW)
        elif sys.platform == "darwin":
            self.proc = subprocess.Popen(["say", "-v", "Meijia", text])


speaker = Speaker()
