"""內建 MariaDB：第一次使用自動建立資料夾；開程式啟動、關程式停止。"""
import os
import socket
import subprocess
import time

from .settings import Settings

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

INI = """[mysqld]
datadir={datadir}
port={port}
bind-address=127.0.0.1
{extra}character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
default-time-zone=+08:00
innodb_buffer_pool_size=96M
max_connections=40
[client]
port={port}
default-character-set=utf8mb4
"""


def listening(host, port) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


class LocalDatabaseServer:
    def __init__(self, st: Settings):
        self.st = st
        self.proc = None

    def _bin(self, name):
        return os.path.join(self.st.mariadb_bin, name + (".exe" if os.name == "nt" else ""))

    @property
    def ini_path(self):
        return os.path.join(self.st.datadir, "my.ini")

    @property
    def log_path(self):
        return os.path.join(os.path.dirname(self.st.datadir), "mariadb.log")

    @property
    def basedir(self):
        return os.path.dirname(self.st.mariadb_bin.rstrip("/\\"))

    def _share(self):
        """錯誤訊息與字元集資料夾（Homebrew 版程式內建的路徑是佔位字串，必須明確指定）。"""
        for sub in ("mysql", "mariadb"):
            d = os.path.join(self.basedir, "share", sub)
            if os.path.isdir(os.path.join(d, "english")):
                return d
        return ""

    def _unix_opts(self):
        share = self._share()
        opts = {"basedir": self.basedir, "socket": os.path.join(self.st.datadir, "mysql.sock"),
                "pid-file": os.path.join(self.st.datadir, "mariadbd.pid")}
        if share:
            opts["lc-messages-dir"] = share
            opts["character-sets-dir"] = os.path.join(share, "charsets")
        return opts

    def _write_ini(self):
        extra = ""
        datadir = self.st.datadir.replace("\\", "/")
        if os.name != "nt":
            # macOS 資料夾在 Application Support（含空白），值一律加引號
            extra = "".join('%s="%s"\n' % kv for kv in self._unix_opts().items())
            datadir = '"%s"' % datadir
        with open(self.ini_path, "w", encoding="utf-8") as f:
            f.write(INI.format(datadir=datadir, port=self.st.port, extra=extra))

    def _can_login(self) -> bool:
        try:
            import pymysql
            pymysql.connect(host=self.st.host, port=int(self.st.port), user=self.st.user,
                            password=self.st.password, connect_timeout=3).close()
            return True
        except Exception:
            return False

    def _our_datadir_running(self) -> bool:
        """有沒有 mariadbd 已經在用我們的資料夾（避免開第二份把資料弄壞）。"""
        ib = os.path.join(self.st.datadir, "ibdata1")
        if os.name == "nt" and os.path.isfile(ib):
            try:                            # Windows：資料庫執行中時 ibdata1 被鎖住，打不開
                with open(ib, "r+b"):
                    pass
            except PermissionError:
                return True
            except OSError:
                pass
        try:
            if os.name == "nt":
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                     "Get-CimInstance Win32_Process -Filter \"Name='mariadbd.exe'\" | % { $_.CommandLine }"],
                    capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW,
                    encoding="utf-8", errors="replace").stdout
            else:
                out = subprocess.run(["ps", "-Ao", "command"], capture_output=True, text=True, timeout=10).stdout
        except Exception:
            return False
        return os.path.normcase(self.ini_path) in os.path.normcase(out)

    def start(self, timeout=40):
        if not self.st.mariadb_bin:
            raise RuntimeError("找不到 MariaDB 資料庫程式。請重新安裝本系統，或在「資料庫設定」改連既有的 MariaDB。")
        if listening(self.st.host, self.st.port):
            for _ in range(20):             # 另一個視窗剛啟動資料庫、還在初始化時，稍等再登入
                if self._can_login():
                    return                  # 已經在跑（另一個視窗或上次沒關乾淨）
                if not self._our_datadir_running():
                    break
                time.sleep(0.5)
            if self._our_datadir_running():
                raise RuntimeError("人事薪資資料庫已在執行中，但無法登入。請關閉所有人事薪資系統視窗後再開一次。")
            for p in range(DEFAULT_SCAN_START, DEFAULT_SCAN_START + 80):   # 連接埠被別的程式佔走 → 換一個
                if not listening(self.st.host, p):
                    self.st.port = p
                    break
            self.st.save()
        os.makedirs(os.path.dirname(self.st.datadir), exist_ok=True)
        if not os.path.isdir(os.path.join(self.st.datadir, "mysql")):
            self._initialize()
        self._write_ini()
        log = open(self.log_path, "ab")
        self.proc = subprocess.Popen([self._bin("mariadbd"), "--defaults-file=" + self.ini_path, "--console"],
                                     stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError("資料庫啟動失敗，詳細內容請看：" + self.log_path)
            if listening(self.st.host, self.st.port):
                if os.name != "nt" and (getattr(self, "_need_pw", False) or not self._can_login()):
                    # macOS 初始化時 root 是空密碼；若上次在設定密碼前中斷，這裡補設
                    time.sleep(0.5)
                    try:
                        self._set_root_pw()
                    except Exception:
                        if getattr(self, "_need_pw", False):
                            raise
                return
            time.sleep(0.3)
        raise RuntimeError("資料庫啟動逾時，詳細內容請看：" + self.log_path)

    def _initialize(self):
        if os.name == "nt":
            cmd = [self._bin("mariadb-install-db"), "--datadir=" + self.st.datadir, "--port=%d" % self.st.port,
                   "--password=" + self.st.password]
        else:
            o = self._unix_opts()
            cmd = [self._bin("mariadb-install-db"), "--no-defaults", "--basedir=" + self.basedir,
                   "--datadir=" + self.st.datadir, "--auth-root-authentication-method=normal", "--skip-test-db",
                   "--skip-name-resolve"]
            cmd += ["--%s=%s" % (k, o[k]) for k in ("lc-messages-dir", "character-sets-dir") if k in o]
            self._need_pw = True
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError("建立資料庫失敗：\n%s%s" % (r.stdout or "", r.stderr or ""))
        self.st.save()

    def _set_root_pw(self):
        import pymysql
        c = pymysql.connect(host=self.st.host, port=int(self.st.port), user="root", password="")
        with c.cursor() as cur:
            cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (self.st.password,))
        c.close()
        self._need_pw = False

    def stop(self):
        if not self.proc:
            return
        try:
            subprocess.run([self._bin("mariadb-admin"), "-h127.0.0.1", "-P%d" % self.st.port, "-uroot",
                            "-p" + self.st.password, "shutdown"], capture_output=True, timeout=25,
                           creationflags=NO_WINDOW)
            self.proc.wait(timeout=25)
        except Exception:
            self.proc.kill()
        self.proc = None


DEFAULT_SCAN_START = 3379
