"""MariaDB 連線（PyMySQL）、建表與版本升級。"""
import os
import threading
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from .settings import Settings

SCHEMA_VERSION = 1
UPGRADES = {
    # 版本號: [SQL…]（之後的版本在這裡加欄位，舊資料庫開啟時自動升級）
}


class DB:
    def __init__(self, st: Settings):
        self.st = st
        self._tl = threading.local()

    def connect(self, use_db=True):
        return pymysql.connect(host=self.st.host, port=int(self.st.port), user=self.st.user,
                               password=self.st.password, database=self.st.database if use_db else None,
                               charset="utf8mb4", autocommit=True, connect_timeout=8,
                               cursorclass=pymysql.cursors.DictCursor)

    @property
    def conn(self):
        c = getattr(self._tl, "c", None)
        if c is not None:
            try:
                c.ping(reconnect=False)
                return c
            except Exception:
                pass
        c = self.connect()
        self._tl.c = c
        return c

    def close(self):
        c = getattr(self._tl, "c", None)
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
            self._tl.c = None

    def rows(self, sql, args=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def row(self, sql, args=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()

    def value(self, sql, args=None):
        r = self.row(sql, args)
        return None if r is None else next(iter(r.values()))

    def exec(self, sql, args=None):
        with self.conn.cursor() as cur:
            n = cur.execute(sql, args)
            return cur.lastrowid if sql.lstrip()[:6].upper() == "INSERT" else n

    def exec_many(self, sql, seq):
        seq = list(seq)
        if not seq:
            return 0
        with self.conn.cursor() as cur:
            return cur.executemany(sql, seq)

    @contextmanager
    def transaction(self):
        c = self.conn
        c.begin()
        try:
            yield
            c.commit()
        except Exception:
            c.rollback()
            raise

    # ------------------------------------------------------------ 建立／升級
    def prepare(self):
        """建立資料庫與資料表；第一次使用時寫入預設科目等資料。"""
        c = self.connect(use_db=False)
        try:
            with c.cursor() as cur:
                cur.execute("CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                            % self.st.database.replace("`", ""))
        finally:
            c.close()
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "schema.sql"), encoding="utf-8") as f:
            for stmt in split_sql(f.read()):
                self.exec(stmt)
        ver = int(self.value("SELECT v FROM meta WHERE k='schema_version'") or 0)
        if ver == 0:
            from .seed import seed_all
            seed_all(self)
        for v in sorted(UPGRADES):
            if v > ver:
                for stmt in UPGRADES[v]:
                    self.exec(stmt)
        self.exec("REPLACE INTO meta (k, v) VALUES ('schema_version', %s)", (str(max(SCHEMA_VERSION, ver)),))


def split_sql(text):
    out, buf = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        if s.endswith(";"):
            out.append("\n".join(buf).rstrip().rstrip(";"))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out


def explain_error(e) -> str:
    s = str(e.args[1] if len(getattr(e, "args", ())) > 1 else e)
    if "auth_gssapi" in s:
        return ("帳號或密碼錯誤（Windows 版 MariaDB 密碼不對時會改用 Windows 驗證）。"
                "請建立專用帳號：CREATE USER 'hr'@'localhost' IDENTIFIED BY '密碼'; "
                "GRANT ALL ON zms_general_hr.* TO 'hr'@'localhost';")
    if "Access denied" in s:
        return "帳號或密碼錯誤：" + s
    if "Can't connect" in s or "10061" in s or "timed out" in s:
        return "伺服器沒有回應，請確認 MariaDB 已啟動、位址與連接埠正確：" + s
    return s


def try_connect(host, port, user, password, database):
    try:
        c = pymysql.connect(host=host, port=int(port), user=user, password=password, connect_timeout=5)
    except Exception as e:
        return False, explain_error(e)
    try:
        with c.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()[0]
            cur.execute("SHOW DATABASES LIKE %s", (database,))
            has = cur.fetchone() is not None
        return True, "連線成功（MariaDB %s），資料庫 %s %s" % (ver, database, "已存在" if has else "不存在，儲存後自動建立")
    finally:
        c.close()
