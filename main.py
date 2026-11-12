"""資料助秘之一般公司人事薪資差勤 — 程式進入點。

桌面版：python main.py
伺服器模式（不開視窗，只提供資料庫與手機連線）：python main.py --server [--port 8765]
網頁預覽（測試用）：python run_web.py（http://127.0.0.1:8570）。
"""
import os
import sys

if "--server" in sys.argv:
    from hr.headless import run
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else None
    run(port)
    sys.exit(0)

import flet as ft  # noqa: E402

from hr.settings import resource_dir  # noqa: E402
from hr.ui.shell import main  # noqa: E402

if __name__ == "__main__":
    if getattr(sys, "frozen", False) and os.name == "nt":
        # 讓工作列顯示本程式的圖示（而不是 Python／Flet 的）
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZMS.GeneralHR")
        except Exception:
            pass
    assets = os.path.join(resource_dir(), "assets")
    port = os.environ.get("HR_WEB_PORT")
    if port:
        ft.run(main, view=None, port=int(port), host="127.0.0.1", assets_dir=assets)
    else:
        ft.run(main, assets_dir=assets)
