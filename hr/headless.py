"""伺服器模式（不開視窗）：只啟動人事薪資資料庫與手機連線服務，給一直開著的公司電腦使用。

用法：ZMSGeneralHR.exe --server [--port 8785]    （按 Ctrl+C 或結束程序即停止，資料庫會正常關閉）
"""
import logging
import signal
import sys
import threading

from .api import ApiServer, lan_addresses
from .database import DB
from .dbserver import LocalDatabaseServer
from .settings import Settings

log = logging.getLogger("hr")


def run(port=None):
    st = Settings.load()
    server = None
    if st.mode == "embedded":
        server = LocalDatabaseServer(st)
        server.start()
    db = DB(st)
    db.prepare()
    st.save()
    port = int(port or st.extra.get("api_port") or 8785)
    api = ApiServer(db, port=port)
    api.start()
    print("人事薪資系統伺服器模式已啟動，手機連線網址：")
    for ip in lan_addresses() or ["127.0.0.1"]:
        print("  http://%s:%d" % (ip, port))
    tunnel = None
    if st.extra.get("tunnel_enabled"):
        from .tunnel import Tunnel
        tunnel = Tunnel(port, st.extra.get("tunnel_mode") or "quick", st.extra.get("tunnel_token", ""),
                        st.extra.get("tunnel_url", ""))
        try:
            print("  外出連線：%s" % tunnel.start())
        except Exception as e:
            print("  外出連線啟動失敗：%s" % e)
            tunnel = None
    print("按 Ctrl+C 停止。")
    sys.stdout.flush()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *a: stop.set())
        except Exception:
            pass
    try:
        while not stop.wait(1):
            pass
    finally:
        if tunnel:
            tunnel.stop()
        api.stop()
        db.close()
        if server:
            server.stop()
        print("已停止。")
