"""Windows「設定 → 協助工具 → 文字大小」放很大時（例如 210%）的版面保護。

Flutter 會把 Windows 的文字大小倍數套到所有文字上，但版面寬度（側邊欄、卡片）不會跟著變，
字就會被切掉或擠出視窗。這裡把程式內的字級先乘上 FACTOR，讓實際放大倍數最多 MAX_SCALE：
字仍然比一般大，但放得進版面。圖示大小不受文字大小影響，不需處理。
"""
import os
import sys

import flet as ft

MAX_SCALE = 1.35        # 程式內文字最多放大到 1.35 倍
FACTOR = 1.0            # 實際套用的字級倍數（1.0＝不調整）
SCALE = 1.0             # Windows 的文字大小倍數

# Material 3 預設字級（Flutter Typography 2021）
_M3 = {"display_large": 57, "display_medium": 45, "display_small": 36,
       "headline_large": 32, "headline_medium": 28, "headline_small": 24,
       "title_large": 22, "title_medium": 16, "title_small": 14,
       "body_large": 16, "body_medium": 14, "body_small": 12,
       "label_large": 14, "label_medium": 12, "label_small": 11}


def windows_text_scale() -> float:
    """讀 Windows 文字大小設定（100～225%），讀不到就當 1。HR_TEXT_SCALE 可指定（測試用）。"""
    if os.environ.get("HR_TEXT_SCALE"):
        try:
            return max(1.0, float(os.environ["HR_TEXT_SCALE"]))
        except ValueError:
            return 1.0
    if sys.platform != "win32":
        return 1.0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility") as k:
            return max(1.0, int(winreg.QueryValueEx(k, "TextScaleFactor")[0]) / 100)
    except OSError:
        return 1.0


def _scale(v):
    return round(v * FACTOR, 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def _wrap(cls, keys):
    orig = cls.__init__
    if getattr(orig, "_zms_scaled", False):
        return

    def init(self, *a, **kw):
        for key in keys:
            if key in kw:
                kw[key] = _scale(kw[key])
        orig(self, *a, **kw)
    init._zms_scaled = True
    cls.__init__ = init


def install(page: ft.Page) -> float:
    """在建立任何畫面之前呼叫。只在 Windows 桌面視窗生效（網頁、手機不受 Windows 設定影響）。"""
    global FACTOR, SCALE
    if page.web or page.platform != ft.PagePlatform.WINDOWS:
        return 1.0
    SCALE = windows_text_scale()
    if SCALE <= MAX_SCALE:
        return 1.0
    FACTOR = MAX_SCALE / SCALE
    _wrap(ft.Text, ("size",))
    _wrap(ft.TextField, ("text_size",))
    _wrap(ft.Dropdown, ("text_size",))
    return FACTOR


def text_theme(color):
    """配合 FACTOR 縮小的預設字級（沒指定 size 的文字、按鈕、表格都用這組）。
    Flet 會整組取代預設字型主題，所以顏色也要給，不然沒指定顏色的文字會變透明。"""
    if FACTOR == 1.0:
        return None
    return ft.TextTheme(**{k: ft.TextStyle(size=round(v * FACTOR, 2), color=color) for k, v in _M3.items()})
