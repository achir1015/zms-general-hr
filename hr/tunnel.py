"""外出連線：用 Cloudflare 通道（cloudflared）把手機連線服務安全地開放到網際網路（HTTPS 加密）。

兩種模式：
* quick ：快速通道，免帳號；啟動後取得 https://xxxx.trycloudflare.com，**每次啟動網址都會改變**。
* token ：固定網址，使用者在 Cloudflare 建立具名通道，把「通道權杖」貼進來；網址固定為使用者設定的公開網址。

cloudflared 為 Cloudflare 官方開源程式，第一次使用時從其 GitHub Releases 下載到資料夾。
"""
import os
import re
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

from .settings import data_dir

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
QUICK_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
BASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/"


def binary_path():
    d = os.path.join(data_dir(), "cloudflared")
    return os.path.join(d, "cloudflared.exe" if os.name == "nt" else "cloudflared")


def download_name():
    if os.name == "nt":
        return "cloudflared-windows-amd64.exe"
    if sys.platform == "darwin":
        import platform
        return "cloudflared-darwin-%s.tgz" % ("arm64" if platform.machine() == "arm64" else "amd64")
    return "cloudflared-linux-amd64"


def ensure_binary(progress=None):
    """沒有 cloudflared 就從官方 GitHub 下載。回傳路徑。"""
    path = binary_path()
    if os.path.isfile(path) and os.path.getsize(path) > 1_000_000:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    name = download_name()
    tmp = path + ".download"
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "ZMSGeneralHR"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total, got = int(r.headers.get("Content-Length") or 0), 0
        while True:
            chunk = r.read(512 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got / total)
    if name.endswith(".tgz"):
        with tarfile.open(tmp) as t:
            member = next(m for m in t.getmembers() if m.name.endswith("cloudflared"))
            with t.extractfile(member) as src, open(path, "wb") as dst:
                dst.write(src.read())
        os.remove(tmp)
    else:
        os.replace(tmp, path)
    if os.name != "nt":
        os.chmod(path, 0o755)
    return path


def parse_quick_url(line):
    m = QUICK_RE.search(line or "")
    return m.group(0) if m else ""


class Tunnel:
    def __init__(self, port, mode="quick", token="", public_url=""):
        self.port = int(port)
        self.mode = mode
        self.token = (token or "").strip()
        self.public_url = (public_url or "").strip().rstrip("/")
        self.proc = None
        self.url = ""
        self.connected = False
        self.log = []
        self.error = ""

    @property
    def running(self):
        return bool(self.proc and self.proc.poll() is None)

    def start(self, timeout=60, progress=None):
        if self.running:
            return self.url
        if self.mode == "token":
            if not self.token:
                raise RuntimeError("請貼上 Cloudflare 通道權杖")
            if not self.public_url.startswith("https://"):
                raise RuntimeError("請輸入通道的公開網址（https:// 開頭）")
        exe = ensure_binary(progress)
        cmd = [exe, "tunnel", "--no-autoupdate"]
        if self.mode == "token":
            cmd += ["run", "--token", self.token]
        else:
            cmd += ["--url", "http://127.0.0.1:%d" % self.port]
        self.url, self.connected, self.error, self.log = "", False, "", []
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        threading.Thread(target=self._reader, daemon=True).start()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not self.running:
                raise RuntimeError("通道程式結束：%s" % ("\n".join(self.log[-5:]) or "未知原因"))
            if self.mode == "quick" and self.url and self.connected:
                return self.url
            if self.mode == "token" and self.connected:
                self.url = self.public_url
                return self.url
            time.sleep(0.3)
        self.stop()
        raise RuntimeError("通道連線逾時，請確認網路正常。%s" % ("\n".join(self.log[-3:])))

    def _reader(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            self.log = (self.log + [line])[-200:]
            if not self.url:
                self.url = parse_quick_url(line)
            if "Registered tunnel connection" in line or "Connection " in line and "registered" in line:
                self.connected = True

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.connected = False
