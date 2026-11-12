"""備份還原、版本更新、桌面捷徑。"""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from . import APP_ID, APP_NAME, APP_VERSION, GITHUB_REPO

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ================================================================ 備份／還原
def _tool(st, names):
    ext = ".exe" if os.name == "nt" else ""
    for n in names:
        p = os.path.join(st.mariadb_bin or "", n + ext)
        if st.mariadb_bin and os.path.isfile(p):
            return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    raise RuntimeError("找不到 MariaDB 工具程式：%s" % "／".join(names))


def _conn_args(st):
    return ["-h", st.host, "-P", str(st.port), "-u", st.user, "--default-character-set=utf8mb4"]


def backup(st, path):
    exe = _tool(st, ["mariadb-dump", "mysqldump"])
    p = subprocess.Popen([exe] + _conn_args(st) + ["--single-transaction", "--routines", st.database],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, MYSQL_PWD=st.password),
                         creationflags=NO_WINDOW)
    with gzip.open(path, "wb") as f:
        shutil.copyfileobj(p.stdout, f)
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        os.remove(path)
        raise RuntimeError("備份失敗：" + err)
    return os.path.getsize(path)


def restore(st, path):
    exe = _tool(st, ["mariadb", "mysql"])
    p = subprocess.Popen([exe] + _conn_args(st) + [st.database], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=dict(os.environ, MYSQL_PWD=st.password), creationflags=NO_WINDOW)
    opener = gzip.open if path.lower().endswith(".gz") else open
    with opener(path, "rb") as f:
        shutil.copyfileobj(f, p.stdin)
    p.stdin.close()
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        raise RuntimeError("還原失敗：" + err)


# ================================================================ 版本更新（GitHub Releases）
def _ver(s):
    out = []
    for part in (s or "0").lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out + [0] * (3 - len(out)))


def _plat(platform=None):
    if platform:
        return platform
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return ""


def asset_suffix(platform=None):
    return {"windows": "-Setup-", "mac": "-mac.dmg", "android": "-android.apk"}.get(_plat(platform), "")


def asset_name(ver, platform=None):
    """發佈檔名：Windows ZMSGeneralHR-Setup-1.2.0.exe；macOS …-1.2.0-mac.dmg；Android …-1.2.0-android.apk"""
    p = _plat(platform)
    if p == "windows":
        return "%s-Setup-%s.exe" % (APP_ID, ver)
    if p in ("mac", "android"):
        return "%s-%s-%s" % (APP_ID, ver, "mac.dmg" if p == "mac" else "android.apk")
    return ""


def current_app_bundle():
    """macOS：目前執行中的 .app 路徑（開發模式回傳空字串）。"""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return ""
    p = os.path.abspath(sys.executable)
    while p and p != "/" and not p.endswith(".app"):
        p = os.path.dirname(p)
    return p if p.endswith(".app") else ""


def _latest_via_page(timeout, platform=None):
    """GitHub API 有匿名次數限制（每小時 60 次／每個網路）；改從發佈頁的轉址取得最新版號（無次數限制）。"""
    req = urllib.request.Request("https://github.com/%s/releases/latest" % GITHUB_REPO, method="HEAD",
                                 headers={"User-Agent": APP_ID})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = r.geturl()                       # …/releases/tag/v1.2.3
    tag = final.rstrip("/").rsplit("/", 1)[-1]
    if "/tag/" not in final or not tag:
        raise RuntimeError("找不到發佈版本")
    ver = tag.lstrip("vV")
    assets = []
    name = asset_name(ver, platform)
    if name:
        assets = [dict(name=name, size=0, browser_download_url="https://github.com/%s/releases/download/%s/%s"
                       % (GITHUB_REPO, tag, name))]
    return dict(tag_name=tag, body="（更新內容請按「前往發佈頁」查看）", assets=assets, html_url=final)


def check_update(timeout=8, platform=None):
    """回傳 None（已是最新）或 dict(version, notes, url, size, name)。"""
    req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % GITHUB_REPO,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": APP_ID})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code not in (403, 429):
            raise
        rel = _latest_via_page(timeout, platform)
    tag = rel.get("tag_name", "")
    if _ver(tag) <= _ver(APP_VERSION):
        return None
    suffix = asset_suffix(platform)
    asset = next((a for a in rel.get("assets", []) if suffix and suffix in a["name"]
                  and a["name"].lower().endswith((".exe", ".dmg", ".apk"))), None)
    return dict(version=tag.lstrip("vV"), notes=rel.get("body") or "", url=asset["browser_download_url"] if asset
                else rel.get("html_url"), size=asset["size"] if asset else 0, name=asset["name"] if asset else "",
                page=rel.get("html_url"))


def download(url, progress=None):
    d = os.path.join(tempfile.gettempdir(), APP_ID + "-update")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, url.rsplit("/", 1)[-1])
    req = urllib.request.Request(url, headers={"User-Agent": APP_ID})
    with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got / total)
    return path


def launch_installer(path):
    """Windows：靜默安裝新版（安裝程式會關閉本程式、更新後自動重新開啟）。"""
    if os.name == "nt":
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"],
                         creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        return
    app = current_app_bundle()
    if not app or not os.access(os.path.dirname(app), os.W_OK):
        subprocess.Popen(["open", path])          # 無法自動替換：打開 DMG 讓使用者拖曳安裝
        return
    # 等本程式結束 → 掛載 DMG → 以新版取代目前的 .app → 重新開啟
    script = os.path.join(tempfile.gettempdir(), APP_ID + "-update.sh")
    with open(script, "w", encoding="utf-8", newline="\n") as f:
        f.write("""#!/bin/bash
PID=%d; DMG="%s"; APP="%s"
while kill -0 $PID 2>/dev/null; do sleep 0.5; done
sleep 2
MNT=$(mktemp -d)
hdiutil attach -nobrowse -quiet -mountpoint "$MNT" "$DMG" || { open "$DMG"; exit 1; }
SRC=$(ls -d "$MNT"/*.app | head -1)
rm -rf "$APP.old"
if mv "$APP" "$APP.old" && ditto "$SRC" "$APP"; then rm -rf "$APP.old"; else rm -rf "$APP"; mv "$APP.old" "$APP"; fi
hdiutil detach -quiet "$MNT"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
open "$APP"
""" % (os.getpid(), path, app))
    os.chmod(script, 0o755)
    subprocess.Popen(["/bin/bash", script], start_new_session=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


# ================================================================ 桌面捷徑
def create_desktop_shortcut():
    if sys.platform == "darwin":
        app = current_app_bundle()
        if not app:
            raise RuntimeError("開發模式沒有 App，請在安裝版使用此功能")
        r = subprocess.run(["osascript", "-e", 'tell application "Finder" to make alias file to POSIX file "%s" '
                            'at desktop' % app], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("建立替身失敗（請在「系統設定 → 隱私權與安全性 → 自動化」允許控制 Finder）：%s"
                               % r.stderr.strip())
        return
    if os.name != "nt":
        raise RuntimeError("目前只支援 Windows 與 macOS 建立捷徑")
    exe = sys.executable if getattr(sys, "frozen", False) else None
    if not exe:
        raise RuntimeError("開發模式沒有執行檔，請在安裝版使用此功能")
    ps = ("$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; "
          "$s=$w.CreateShortcut((Join-Path $d '%s.lnk')); $s.TargetPath='%s'; $s.WorkingDirectory='%s'; "
          "$s.IconLocation='%s,0'; $s.Description='%s'; $s.Save()"
          % (APP_NAME, exe, os.path.dirname(exe), exe, APP_NAME))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "建立捷徑失敗")
