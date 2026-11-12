"""開發用：iPad（平板）版面預覽（http://127.0.0.1:8582），連到本機的手機連線服務。"""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("HR_WEB_PORT", "8582")
os.environ.setdefault("FLET_FORCE_WEB_SERVER", "true")
os.environ.setdefault("HR_MOBILE", "1")
os.environ.setdefault("HR_TABLET", "1")
os.environ.setdefault("HR_DATA_DIR", os.path.join(here, "data_mobile"))
os.environ.setdefault("HR_DEV_SERVER", "http://127.0.0.1:8785")
os.environ.setdefault("HR_DEV_LOGIN", "admin:admin123")
os.chdir(here)
sys.path.insert(0, here)
runpy.run_path(os.path.join(here, "main.py"), run_name="__main__")
