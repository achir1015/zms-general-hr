"""所有程式檔都要能編譯（手機版等測試不會匯入的畫面，語法錯誤也要在這裡抓到）。"""
import glob
import os
import py_compile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_all_modules_compile():
    files = [f for pat in ("hr/*.py", "hr/ui/*.py", "tools/*.py", "*.py")
             for f in glob.glob(os.path.join(ROOT, pat))]
    assert len(files) > 40
    for f in files:
        py_compile.compile(f, doraise=True)


def test_ui_modules_import():
    import importlib
    for f in glob.glob(os.path.join(ROOT, "hr", "ui", "*.py")):
        name = os.path.splitext(os.path.basename(f))[0]
        if name != "__init__":
            importlib.import_module("hr.ui." + name)
