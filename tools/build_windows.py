"""一鍵建置 Windows 安裝檔：
1. 準備內附的 MariaDB 最小檔案（packaging/mariadb）
2. 產生圖示、語音說明（已存在則略過）
3. flet pack（PyInstaller）打包到 dist/ZMSGeneralHR
4. Inno Setup 產生 dist-installer/ZMSGeneralHR-Setup-<版本>.exe

用法：.venv\\Scripts\\python tools\\build_windows.py
"""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from hr import APP_ID, APP_NAME, APP_VERSION, AUTHOR  # noqa: E402

MARIADB_SRC = os.environ.get("HR_MARIADB_SRC", r"C:\mariadb")
BIN = ["mariadbd.exe", "mysqld.exe", "server.dll", "mariadb-install-db.exe", "mariadb-admin.exe", "mariadb-dump.exe",
       "mariadb.exe", "concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
       "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll"]
ISCC = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")


def mariadb():
    dst = os.path.join(HERE, "packaging", "mariadb")
    if os.path.isfile(os.path.join(dst, "bin", "mariadbd.exe")):
        return
    os.makedirs(os.path.join(dst, "bin"), exist_ok=True)
    for f in BIN:
        shutil.copy2(os.path.join(MARIADB_SRC, "bin", f), os.path.join(dst, "bin", f))
    share = os.path.join(dst, "share")
    for d in ("charsets", "english", "chinese"):
        shutil.copytree(os.path.join(MARIADB_SRC, "share", d), os.path.join(share, d), dirs_exist_ok=True)
    for f in os.listdir(os.path.join(MARIADB_SRC, "share")):
        if f.endswith(".sql") or f == "errmsg-utf8.txt":
            shutil.copy2(os.path.join(MARIADB_SRC, "share", f), share)
    for f in ("COPYING", "README.md", "THIRDPARTY"):
        if os.path.isfile(os.path.join(MARIADB_SRC, f)):
            shutil.copy2(os.path.join(MARIADB_SRC, f), dst)


def assets():
    if not os.path.isfile(os.path.join(HERE, "assets", "icon.png")):
        subprocess.run([PY, "tools/make_icon.py"], cwd=HERE, check=True)
    subprocess.run([PY, "tools/make_voice.py"], cwd=HERE, check=False)


def pack():
    flet = os.path.join(HERE, ".venv", "Scripts", "flet.exe")
    shutil.rmtree(os.path.join(HERE, "dist"), ignore_errors=True)
    cmd = [flet, "pack", "main.py", "-D", "-y", "-n", APP_ID, "-i", "packaging/icon.ico", "--distpath", "dist",
           "--add-data", "assets:assets", "--add-data", "hr/schema.sql:hr",
           "--hidden-import", "edge_tts", "--hidden-import", "pymysql", "--hidden-import", "qrcode", "--hidden-import", "qrcode.image.pil", "--hidden-import", "qrcode",
           "--hidden-import", "qrcode.image.pil", "--product-name", APP_NAME, "--file-description", APP_NAME, "--product-version", APP_VERSION,
           "--file-version", APP_VERSION + ".0", "--company-name", AUTHOR, "--copyright", "© 2026 " + AUTHOR]
    subprocess.run(cmd, cwd=HERE, check=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def installer():
    iscc = next((p for p in ISCC if os.path.isfile(p)), None)
    if not iscc:
        raise SystemExit("找不到 Inno Setup 6（ISCC.exe）")
    subprocess.run([iscc, "/DAppVer=" + APP_VERSION, os.path.join(HERE, "packaging", "installer.iss")], check=True)
    out = os.path.join(HERE, "dist-installer", "%s-Setup-%s.exe" % (APP_ID, APP_VERSION))
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print("完成：%s（%.1f MB）\nSHA256 %s" % (out, os.path.getsize(out) / 1e6, sha))


if __name__ == "__main__":
    mariadb()
    assets()
    pack()
    installer()
