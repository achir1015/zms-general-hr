"""介面設計系統：配色、卡片、圖示方塊、按鈕、欄位、資料表、提示。"""
import csv
import datetime as dt
import os
from decimal import Decimal

import flet as ft

from .. import rocdate
from ..core import BizError

# ---------------------------------------------------------------- 配色
PRIMARY = "#1E4D8C"
PRIMARY_DARK = "#14325C"
ACCENT = "#0FA294"
GOLD = "#E0A526"
BG = "#F2F5FA"
CARD = "#FFFFFF"
TEXT = "#1F2937"
MUTED = "#6B7280"
LINE = "#E5E9F0"
SUCCESS = "#16A34A"
DANGER = "#DC2626"
WARN = "#D97706"
SIDEBAR_TOP = "#0F2747"
SIDEBAR_BOTTOM = "#1B3E6F"
MOBILE = False          # 手機版（直向窄螢幕）時由 mobile.start() 設為 True
TABLET = False          # iPad（電腦版版面、但寬度較窄）
PHONE_W = 340           # 手機上單一控制項的最大寬度
READY = "mobile-ready"  # 控制項 data 設為此值：已專為手機排版，mobilize 不再處理
MZ_OFF = set()          # 開發除錯：暫時關閉某些手機版面規則

# 圖示方塊的色調：(底色, 圖示色)
TONES = {
    "blue": ("#E3EDFF", "#1E4D8C"), "teal": ("#D7F5F0", "#0F766E"), "amber": ("#FEF1C7", "#B45309"),
    "rose": ("#FFE4E8", "#BE123C"), "violet": ("#EEE8FF", "#6D28D9"), "green": ("#DCFCE7", "#15803D"),
    "sky": ("#DDF2FF", "#0369A1"), "slate": ("#E8ECF2", "#334155"), "orange": ("#FFEAD5", "#C2410C"),
    "pink": ("#FCE7F6", "#A21CAF"),
}
STATUS_STYLE = {0: ("未審核", "amber"), 1: ("已審核", "sky"), 2: ("已過帳", "green"), 9: ("作廢", "slate")}
VTYPE_TONE = {"收": "green", "支": "rose", "轉": "blue", "開帳": "violet", "調整": "orange", "結帳": "slate"}


# ---------------------------------------------------------------- 數字、日期
def amt(v, blank_zero=False, paren=False):
    if v is None or v == "":
        return ""
    v = Decimal(str(v))
    if blank_zero and v == 0:
        return ""
    s = "{:,.2f}".format(abs(v))
    if s.endswith(".00"):
        s = s[:-3]
    if v < 0:
        return "(%s)" % s if paren else "-" + s
    return s


def show(v, typ=""):
    if v is None:
        return ""
    if typ == "n":
        return amt(v)
    if typ == "nz":
        return amt(v, blank_zero=True)
    if typ == "b":
        return "✔" if v else ""
    if isinstance(v, dt.datetime):
        return rocdate.show(v.date()) + v.strftime(" %H:%M")
    if isinstance(v, dt.date):
        return rocdate.show(v)
    if isinstance(v, Decimal):
        return amt(v)
    return str(v)


# ---------------------------------------------------------------- 基本元件
def icon_tile(icon, tone="blue", size=40, icon_size=None, radius=12):
    bg, fg = TONES.get(tone, TONES["blue"])
    return ft.Container(ft.Icon(icon, color=fg, size=icon_size or int(size * 0.55)), width=size, height=size,
                        bgcolor=bg, border_radius=radius, alignment=ft.Alignment.CENTER)


def card(content, padding=18, expand=None, width=None, height=None, bgcolor=CARD, radius=16, **kw):
    return ft.Container(content, padding=padding, expand=expand, width=width, height=height, bgcolor=bgcolor,
                        border_radius=radius, border=ft.Border.all(1, LINE),
                        shadow=ft.BoxShadow(blur_radius=18, spread_radius=-6, color="#1A1E3A5F",
                                            offset=ft.Offset(0, 6)), **kw)


def title_text(text, size=22):
    return ft.Text(text, size=size, weight=ft.FontWeight.W_700, color=TEXT)


def muted(text, size=13, **kw):
    return ft.Text(text, size=size, color=MUTED, **kw)


def page_header(icon, title, subtitle="", tone="blue", actions=None):
    if actions and (len(actions) > 2 or (TABLET and len(actions) > 1)):
        # iPad：工具列放到標題下一行，標題才不會被擠成直的
        head = ft.Row([icon_tile(icon, tone, 48, radius=14),
                       ft.Column([title_text(title), muted(subtitle)] if subtitle else [title_text(title)],
                                 spacing=0, expand=True)], spacing=14)
        return ft.Column([head, ft.Row(list(actions), wrap=True, spacing=10, run_spacing=8,
                                       vertical_alignment=ft.CrossAxisAlignment.CENTER)], spacing=10)
    if MOBILE:
        head = ft.Row([icon_tile(icon, tone, 40, radius=12),
                       ft.Column([title_text(title, 19), muted(subtitle, 12)] if subtitle else [title_text(title, 19)],
                                 spacing=0, expand=True)], spacing=10)
        return ft.Column([head] + ([ft.Row(list(actions), wrap=True, spacing=8, run_spacing=8)] if actions else []),
                         spacing=8)
    return ft.Row([
        icon_tile(icon, tone, 48, radius=14),
        ft.Column([title_text(title), muted(subtitle)] if subtitle else [title_text(title)], spacing=0,
                  expand=True),
        *(actions or [])], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=14)


def chip(text, tone="blue", icon=None, size=12):
    bg, fg = TONES.get(tone, TONES["blue"])
    row = [ft.Icon(icon, size=size + 2, color=fg)] if icon else []
    row.append(ft.Text(text, size=size, color=fg, weight=ft.FontWeight.W_600))
    return ft.Container(ft.Row(row, spacing=4, tight=True), bgcolor=bg, border_radius=20,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=3))


def status_chip(status):
    text, tone = STATUS_STYLE.get(status, ("?", "slate"))
    return chip(text, tone)


def btn(text, icon=None, on_click=None, kind="primary", **kw):
    if kind == "primary":
        return ft.FilledButton(text, icon=icon, on_click=on_click, bgcolor=kw.pop("bgcolor", PRIMARY),
                               style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10),
                                                    padding=ft.Padding.symmetric(horizontal=18, vertical=14)), **kw)
    if kind == "accent":
        return ft.FilledButton(text, icon=icon, on_click=on_click, bgcolor=ACCENT,
                               style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10),
                                                    padding=ft.Padding.symmetric(horizontal=18, vertical=14)), **kw)
    if kind == "danger":
        return ft.OutlinedButton(text, icon=icon, on_click=on_click,
                                 style=ft.ButtonStyle(color=DANGER, shape=ft.RoundedRectangleBorder(radius=10),
                                                      side=ft.BorderSide(1, "#F3B4B4"),
                                                      padding=ft.Padding.symmetric(horizontal=16, vertical=14)), **kw)
    if kind == "ghost":
        return ft.TextButton(text, icon=icon, on_click=on_click,
                             style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), **kw)
    return ft.OutlinedButton(text, icon=icon, on_click=on_click,
                             style=ft.ButtonStyle(color=PRIMARY, shape=ft.RoundedRectangleBorder(radius=10),
                                                  side=ft.BorderSide(1, "#C7D4E8"),
                                                  padding=ft.Padding.symmetric(horizontal=16, vertical=14)), **kw)


def field(label, value="", width=None, **kw):
    return ft.TextField(label=label, value="" if value is None else str(value), width=width, dense=True,
                        border_radius=10, border_color="#CBD5E1", focused_border_color=PRIMARY,
                        bgcolor="#FBFCFE", text_size=14, **kw)


def money_field(label="", value="", width=130, **kw):
    v = "" if value in (None, "") or Decimal(str(value)) == 0 else amt(value)
    return field(label, v, width=width, text_align=ft.TextAlign.RIGHT, **kw)


def date_field(label="日期", value=None, width=150, **kw):
    from . import textscale
    if width and textscale.FACTOR < 1:          # Windows 大字體：日期欄加寬，免得 115/11/13 被截
        width += 18
    if width and MOBILE:                        # 手機字體通常較大
        width += 50
    return field(label, rocdate.show(value or rocdate.today()), width=width, hint_text="115/11/12",
                 prefix_icon=ft.Icons.CALENDAR_MONTH, **kw)


def dropdown(label, options, value=None, width=None, on_select=None, blank=None, filterable=True, **kw):
    opts = [ft.DropdownOption(key="", text=blank)] if blank is not None else []
    opts += [ft.DropdownOption(key=str(k), text=t) for k, t in options]
    return ft.Dropdown(label=label, options=opts, value=None if value is None else str(value), width=width,
                       dense=True, on_select=on_select, enable_filter=filterable, editable=filterable,
                       menu_height=380, border_radius=10, border_color="#CBD5E1", focused_border_color=PRIMARY,
                       filled=True, fill_color="#FBFCFE", text_size=14, **kw)


def switch(label, value=False, **kw):
    return ft.Switch(label=label, value=bool(value), active_color=ACCENT, **kw)


def empty_state(icon, text, sub=""):
    return ft.Container(ft.Column([icon_tile(icon, "slate", 64, radius=20), ft.Text(text, size=15, color=MUTED),
                                   muted(sub, 12)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        alignment=ft.Alignment.CENTER, padding=40)


def kpi(title, value, icon, tone, sub="", on_click=None):
    bg, fg = TONES[tone]
    return ft.Container(
        ft.Row([icon_tile(icon, tone, 36 if MOBILE else 52, radius=12 if MOBILE else 16),
                ft.Column([muted(title, 12 if MOBILE else 13),
                           ft.Text(value, size=(16 if len(value) <= 7 else 13 if len(value) <= 10 else 11)
                                   if MOBILE else 22, weight=ft.FontWeight.W_800, color=TEXT,
                                   no_wrap=True), muted(sub or " ", 11)],
                          spacing=1, expand=True)], spacing=10 if MOBILE else 14),
        padding=12 if MOBILE else 18, bgcolor=CARD, border_radius=18, border=ft.Border.all(1, LINE), expand=True, on_click=on_click,
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=-6, color="#1A1E3A5F", offset=ft.Offset(0, 6)),
        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                   colors=[CARD, ft.Colors.with_opacity(0.45, bg)]))


def kpis(items, spacing=16):
    """關鍵數字卡片一列：電腦版一排，手機版兩欄換行。"""
    if MOBILE:
        for k in items:
            k.expand = False
            k.col = 6
        return ft.ResponsiveRow(items, spacing=10, run_spacing=10)
    if TABLET and len(items) > 4:
        for k in items:
            k.expand = False
            k.col = 4
        return ft.ResponsiveRow(items, spacing=12, run_spacing=12)
    return ft.Row(items, spacing=spacing)


def split(left, right, spacing=14):
    """左右兩欄（清單＋明細）：手機版改成上下排列。"""
    if MOBILE:
        return ft.Column([left, right], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    return ft.Row([left, right], expand=True, spacing=spacing, vertical_alignment=ft.CrossAxisAlignment.START)


def mobilize(c, parent="col", bounded=False):
    """手機版版面轉換（可重複執行）：取消 expand、限制過寬的寬度、表格固定高度、橫列自動換行、
    不在固定高度容器內的直欄取消各自捲動（整頁一起捲）。"""
    if c is None or isinstance(c, (str, int, float)):
        return
    if getattr(c, "data", None) == READY:          # 已專為手機排版的區塊
        return
    if isinstance(c, Grid):
        if "grid" not in MZ_OFF:
            c.fit_mobile()
        return
    # 左右兩欄的畫面（data="split"）：改成一欄、填滿寬度
    if isinstance(c, ft.Row) and getattr(c, "data", None) == "split":
        c.controls = [ft.Column(list(c.controls), expand=True, spacing=12, data="split-col",
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH)]
        c.data = "split-done"
    # 直向的 expand 在整頁捲動時會出錯；橫列內的 expand 則是限制寬度用，保留
    if (getattr(c, "expand", None) and parent == "col" and getattr(c, "data", None) != "split-col"
            and "expand" not in MZ_OFF):
        c.expand = False
    w = getattr(c, "width", None)
    if isinstance(w, (int, float)) and w > PHONE_W and not isinstance(c, ft.Image) and "width" not in MZ_OFF:
        c.width = PHONE_W if parent == "row" else None
    if isinstance(c, ft.Column) and getattr(c, "scroll", None) and not bounded and "scroll" not in MZ_OFF:
        c.scroll = None
    # 只含一般欄位、按鈕的橫列：可以安全地自動換行（含直欄或 expand 子項的橫列換行會出錯，不動）
    if (isinstance(c, ft.Row) and not getattr(c, "scroll", None) and not c.wrap and c.controls
            and getattr(c, "data", None) not in ("split-done",) and "rowwrap" not in MZ_OFF
            and not any(isinstance(x, (ft.Column, ft.Row, ft.ResponsiveRow)) or getattr(x, "expand", None)
                        for x in c.controls)):
        c.wrap = True
        c.run_spacing = c.run_spacing or 8
    if isinstance(c, ft.Container) and getattr(c, "height", None):
        bounded = True
    kind = "row" if isinstance(c, ft.Row) else "col"
    for child in (getattr(c, "controls", None) or []):
        mobilize(child, kind, bounded)
    content = getattr(c, "content", None)
    if content is not None and not isinstance(content, str):
        mobilize(content, "col", bounded)


def install_mobile_hooks():
    """手機版：任何控制項更新前先做版面轉換（畫面重新產生的部分也適用）。"""
    orig = ft.Control.update

    def update(self, *a, **kw):
        try:
            mobilize(self)
        except Exception:
            pass
        return orig(self, *a, **kw)
    ft.Control.update = update


# ---------------------------------------------------------------- 資料表
class Grid(ft.Column):
    """資料表。columns=[(key, 標題, 型別, 寬度)]；型別：s 文字、n 金額、nz 金額（0 不顯示）、d 日期、b 勾選、
    status 傳票狀態、vtype 傳票類別。可勾選（selectable=True）與點選列（on_pick）。"""

    def __init__(self, columns, on_pick=None, selectable=False, totals=(), height=None, empty="沒有資料",
                 row_style=None):
        self.cols = columns
        self.on_pick = on_pick
        self.selectable = selectable
        self.totals = totals
        self.data_rows = []
        self.checked = set()
        self.empty_text = empty
        self.row_style = row_style
        self.table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c[1], weight=ft.FontWeight.W_700, size=13, color="#334155"),
                                   numeric=c[2] in ("n", "nz")) for c in columns],
            rows=[], heading_row_height=40, data_row_min_height=36, data_row_max_height=44, column_spacing=20,
            heading_row_color="#EEF3FA", border_radius=12, show_checkbox_column=selectable,
            horizontal_lines=ft.BorderSide(0.6, "#EDF1F6"), divider_thickness=0.6,
            on_select_all=self._select_all if selectable else None)
        self.footer = ft.Row([], spacing=18, wrap=True)
        self.empty = empty_state(ft.Icons.INBOX_OUTLINED, empty)
        self.body = ft.Column([ft.Row([self.table], scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.AUTO,
                              expand=True)
        super().__init__([ft.Container(self.body, border=ft.Border.all(1, LINE), border_radius=12, bgcolor=CARD,
                                       expand=height is None, height=height),
                          self.footer], expand=height is None, spacing=6)

    def fit_mobile(self, height=440):
        """手機：表格固定高度（整頁捲動時，表格自己在框內捲動）。"""
        self.expand = False
        box = self.controls[0]
        box.expand = False
        box.height = box.height or height

    def _select_all(self, e):
        on = str(getattr(e, "data", "")).lower() == "true"
        self.checked = set(range(len(self.data_rows))) if on else set()
        for i, r in enumerate(self.table.rows):
            r.selected = i in self.checked
        self.update()

    def _toggle(self, i, row_ctrl):
        if i in self.checked:
            self.checked.discard(i)
        else:
            self.checked.add(i)
        row_ctrl.selected = i in self.checked
        self.update()

    def selected_rows(self):
        return [self.data_rows[i] for i in sorted(self.checked) if i < len(self.data_rows)]

    def cell(self, r, key, typ, width):
        v = r.get(key)
        if typ == "status":
            return status_chip(v)
        if typ == "vtype":
            return chip(v or "", VTYPE_TONE.get(v, "slate"))
        s = show(v, typ)
        color = DANGER if typ in ("n", "nz") and isinstance(v, (Decimal, int, float)) and v < 0 else TEXT
        weight = None
        if self.row_style:
            st = self.row_style(r) or {}
            weight = st.get("weight")
            color = st.get("color", color)
        return ft.Text(s, width=width, size=13, color=color, weight=weight, no_wrap=True, max_lines=1,
                       overflow=ft.TextOverflow.ELLIPSIS,
                       text_align=ft.TextAlign.RIGHT if typ in ("n", "nz") else ft.TextAlign.LEFT,
                       tooltip=s if len(s) > 14 else None)

    def set_rows(self, rows, extra_footer=None):
        self.data_rows = list(rows)
        self.checked = set()
        out = []
        for i, r in enumerate(self.data_rows):
            row = ft.DataRow(cells=[ft.DataCell(self.cell(r, *c[0:1], c[2], c[3])) for c in self.cols])
            if self.selectable:
                row.on_select_change = lambda e, i=i, rc=row: self._toggle(i, rc)
            elif self.on_pick:
                row.on_select_change = lambda e, r=r: self.on_pick(r)
            out.append(row)
        self.table.rows = out
        info = [muted("共 %d 筆" % len(self.data_rows), 12)]
        for k in self.totals:
            tot = sum((Decimal(str(r.get(k) or 0)) for r in self.data_rows), Decimal(0))
            title = next(c[1] for c in self.cols if c[0] == k)
            info.append(ft.Text("%s合計 %s" % (title, amt(tot)), size=12, color=PRIMARY, weight=ft.FontWeight.W_600))
        if extra_footer:
            info += extra_footer
        self.footer.controls = info
        self.body.controls = [ft.Row([self.table], scroll=ft.ScrollMode.AUTO)] if self.data_rows else [self.empty]

    def csv_text(self):
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([c[1] for c in self.cols])
        for r in self.data_rows:
            w.writerow([(show(r.get(c[0]), c[2]).replace(",", "") if c[2] in ("n", "nz") else
                         show(r.get(c[0]), "" if c[2] in ("status", "vtype") else c[2])) for c in self.cols])
        return buf.getvalue()

    def export_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(self.csv_text())


# ---------------------------------------------------------------- 畫面共用環境
class Ctx:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.books = app.books
        self.reports = app.reports

    def toast(self, msg, error=False):
        self.page.show_dialog(ft.SnackBar(
            ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE if error else ft.Icons.CHECK_CIRCLE, color=ft.Colors.WHITE),
                    ft.Text(msg, color=ft.Colors.WHITE, size=14, expand=True)]),
            bgcolor=DANGER if error else SUCCESS, duration=4500 if error else 2200,
            behavior=ft.SnackBarBehavior.FLOATING, width=560))

    def guard(self, fn, *a, ok=None, **kw):
        try:
            r = fn(*a, **kw)
            if ok:
                self.toast(ok)
            return True if r is None else r
        except (BizError, ValueError) as e:
            self.toast(str(e), True)
        except Exception as e:
            import logging
            logging.getLogger("hr").exception("guard")
            self.toast("發生錯誤：%s" % e, True)
        return None

    def confirm(self, title, msg, on_yes, yes="確定", danger=True):
        def go(e):
            self.page.pop_dialog()
            on_yes()
        self.page.show_dialog(ft.AlertDialog(
            modal=True, icon=ft.Row([icon_tile(ft.Icons.HELP_OUTLINE if not danger else ft.Icons.WARNING_AMBER,
                                               "rose" if danger else "blue", 44)], alignment=ft.MainAxisAlignment.CENTER),
            title=ft.Text(title, size=18, weight=ft.FontWeight.W_700), content=ft.Text(msg, size=14),
            actions=[btn("取消", kind="ghost", on_click=lambda e: self.page.pop_dialog()),
                     btn(yes, on_click=go, bgcolor=DANGER if danger else PRIMARY)]))

    def dialog(self, title, content, actions, icon=None, tone="blue", width=560):
        if MOBILE:
            mobilize(content)
            width = None
            content = ft.Column([content], scroll=ft.ScrollMode.AUTO, tight=True)
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            icon=ft.Row([icon_tile(icon, tone, 44)], alignment=ft.MainAxisAlignment.CENTER) if icon else None,
            title=ft.Text(title, size=18, weight=ft.FontWeight.W_700),
            content=ft.Container(content, width=width), actions=actions, shape=ft.RoundedRectangleBorder(radius=18),
            inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24) if MOBILE else None))

    def close(self):
        """關閉最上層的對話框（不是提示訊息 SnackBar；成功訊息常在關閉對話框前先顯示）。"""
        try:
            dlg = next((d for d in reversed(self.page._dialogs.controls)
                        if d.open and not isinstance(d, ft.SnackBar)), None)
        except Exception:
            dlg = None
        if dlg is None:
            self.page.pop_dialog()
            return
        dlg.open = False
        dlg.update()

    async def save_as(self, name, ext):
        path = await ft.FilePicker().save_file(dialog_title="另存新檔", file_name=name, allowed_extensions=[ext])
        if path and not path.lower().endswith("." + ext):
            path += "." + ext
        return path

    async def save_generated(self, filename, writer, open_after=True):
        """產生檔案（writer(path) 負責寫入）：電腦版另存後開啟；手機版存到手機。"""
        if MOBILE:
            import tempfile
            p = os.path.join(tempfile.gettempdir(), filename)
            writer(p)
            with open(p, "rb") as f:
                await self.save_bytes(filename, f.read())
            return
        path = await self.save_as(filename, filename.rsplit(".", 1)[-1])
        if path:
            writer(path)
            if open_after:
                open_file(path)
        return path

    async def pick_csv(self, title):
        """選 CSV 檔，回傳本機路徑（手機版讀入內容後存到暫存檔）。"""
        files = await ft.FilePicker().pick_files(dialog_title=title, allowed_extensions=["csv"], with_data=MOBILE)
        if not files:
            return ""
        f = files[0]
        if f.path and os.path.isfile(f.path):
            return f.path
        if f.bytes:
            import tempfile
            p = os.path.join(tempfile.gettempdir(), "import_" + (f.name or "data.csv"))
            with open(p, "wb") as out:
                out.write(f.bytes)
            return p
        return ""

    async def save_bytes(self, filename, data):
        """手機：把檔案另存到手機（Android 會開啟儲存位置選擇）。"""
        ext = filename.rsplit(".", 1)[-1]
        path = await ft.FilePicker().save_file(dialog_title="儲存檔案", file_name=filename, allowed_extensions=[ext],
                                               src_bytes=data)
        if path:
            self.toast("已儲存：%s（可用瀏覽器或 Excel 開啟）" % os.path.basename(path))

    def export_button(self, grid, name):
        async def go(e):
            if not grid.data_rows:
                self.toast("沒有資料可以匯出", True)
                return
            if MOBILE:
                await self.save_bytes("%s_%s.csv" % (name, rocdate.today().strftime("%Y%m%d")),
                                      grid.csv_text().encode("utf-8-sig"))
                return
            path = await self.save_as("%s_%s.csv" % (name, rocdate.today().strftime("%Y%m%d")), "csv")
            if path:
                grid.export_csv(path)
                self.toast("已匯出：%s" % os.path.basename(path))
        return btn("匯出 Excel", ft.Icons.DOWNLOAD, go, kind="outline")


def open_file(path):
    if os.name == "nt":
        os.startfile(path)  # noqa
    else:
        import subprocess
        import sys
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
