"""開發用：以網頁模式啟動（http://127.0.0.1:8580），方便在瀏覽器預覽畫面。"""
import os
import runpy
import sys

os.environ.setdefault("HR_WEB_PORT", "8580")
os.environ.setdefault("FLET_FORCE_WEB_SERVER", "true")
os.environ.setdefault("HR_DEV_LOGIN", "admin:admin123")
here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
sys.path.insert(0, here)
runpy.run_path(os.path.join(here, "main.py"), run_name="__main__")
