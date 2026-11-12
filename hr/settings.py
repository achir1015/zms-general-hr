"""程式設定與資料夾位置。

* 開發時：資料放在專案下 data/
* 安裝版：Windows %LOCALAPPDATA%\\ZMSGeneralHR、macOS ~/Library/Application Support/ZMSGeneralHR
  （程式更新、解除安裝都不會動到資料）
"""
import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass, field

from . import APP_ID

DEFAULT_PORT = 3378          # 與其他 MariaDB（3306／3318／3338／3358…）錯開


def program_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """assets 等唯讀資源所在（PyInstaller 打包後在 _internal 或 _MEIPASS）。"""
    return getattr(sys, "_MEIPASS", program_dir())


def data_dir() -> str:
    env = os.environ.get("HR_DATA_DIR") or os.environ.get("FLET_APP_STORAGE_DATA")   # 後者＝手機 App 的資料夾
    if env:
        os.makedirs(env, exist_ok=True)
        return env
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:
            base = os.path.expanduser("~/.local/share")
        d = os.path.join(base, APP_ID)
    else:
        d = os.path.join(program_dir(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def bundled_mariadb() -> str:
    """安裝版附帶的 MariaDB：Windows 在程式旁 mariadb/bin；macOS 在 .app/Contents/Resources/mariadb/bin。"""
    exe = "mariadbd.exe" if os.name == "nt" else "mariadbd"
    for c in (os.path.join(program_dir(), "mariadb", "bin"),
              os.path.normpath(os.path.join(program_dir(), "..", "Resources", "mariadb", "bin"))):
        if os.path.isfile(os.path.join(c, exe)):
            return c
    return ""


def _mariadb_candidates():
    exe = "mariadbd.exe" if os.name == "nt" else "mariadbd"
    yield os.environ.get("HR_MARIADB_BIN", "")
    yield os.path.join(program_dir(), "mariadb", "bin")                                    # Windows 安裝版
    yield os.path.normpath(os.path.join(program_dir(), "..", "Resources", "mariadb", "bin"))  # macOS .app
    yield r"C:\mariadb\bin"
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    if os.path.isdir(pf):
        for n in sorted(os.listdir(pf), reverse=True):
            if n.lower().startswith("mariadb"):
                yield os.path.join(pf, n, "bin")
    yield from ("/opt/homebrew/opt/mariadb/bin", "/usr/local/opt/mariadb/bin", "/usr/bin", "/usr/sbin")
    _ = exe


def find_mariadb() -> str:
    exe = "mariadbd.exe" if os.name == "nt" else "mariadbd"
    for c in _mariadb_candidates():
        if c and os.path.isfile(os.path.join(c, exe)):
            return c
    return ""


@dataclass
class Settings:
    mode: str = "embedded"       # embedded＝程式自己啟停資料庫；server＝連到既有的 MariaDB
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    user: str = "root"
    password: str = ""
    database: str = "zms_general_hr"
    mariadb_bin: str = ""
    datadir: str = ""
    last_user: str = ""
    skipped_version: str = ""
    extra: dict = field(default_factory=dict)

    @staticmethod
    def file() -> str:
        return os.path.join(data_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        if os.path.isfile(cls.file()):
            with open(cls.file(), encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    if hasattr(s, k):
                        setattr(s, k, v)
        if not s.datadir:
            s.datadir = os.path.join(data_dir(), "mariadb")
        exe = "mariadbd.exe" if os.name == "nt" else "mariadbd"
        bundled = bundled_mariadb()
        if bundled:
            s.mariadb_bin = bundled            # 安裝版一律用附帶的資料庫程式（程式搬家或更新後路徑也對）
        elif not os.path.isfile(os.path.join(s.mariadb_bin or "", exe)):
            s.mariadb_bin = find_mariadb()
        if s.mode == "embedded" and not s.password:
            s.password = secrets.token_urlsafe(18)
        return s

    def save(self):
        with open(self.file(), "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
