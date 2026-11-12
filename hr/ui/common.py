"""畫面共用小元件：年月選擇、員工與部門下拉、日期區間、說明框。"""
import datetime as dt

import flet as ft

from .. import rocdate
from . import theme as T


def ym_now(offset=0):
    d = dt.date.today().replace(day=1)
    m = d.month - 1 + offset
    y = d.year + m // 12
    return "%04d%02d" % (y, m % 12 + 1)


def ym_options(back=24, ahead=3):
    out = []
    for i in range(ahead, -back - 1, -1):
        ym = ym_now(i)
        out.append((ym, rocdate.ym_show(ym)))
    return out


def ym_dropdown(value=None, on_select=None, width=170, label="年月"):
    return T.dropdown(label, ym_options(), value or ym_now(), width=width, on_select=on_select, filterable=False)


def year_dropdown(value=None, on_select=None, width=130):
    y = dt.date.today().year
    return T.dropdown("年度", [(str(x), "%d 年" % (x - 1911)) for x in range(y + 1, y - 6, -1)], str(value or y),
                      width=width, on_select=on_select, filterable=False)


def emp_dropdown(ctx, value="", on_select=None, width=220, blank="全部員工", include_left=False, label="員工"):
    return T.dropdown(label, ctx.books.options("emp_all" if include_left else "emp"), value, width=width,
                      on_select=on_select, blank=blank)


def dept_dropdown(ctx, value="", on_select=None, width=170, blank="全部部門"):
    return T.dropdown("部門", ctx.books.options("dept"), value, width=width, on_select=on_select, blank=blank)


def info_box(text, tone="sky", icon=ft.Icons.INFO_OUTLINE):
    bg, fg = T.TONES[tone]
    return ft.Container(ft.Row([ft.Icon(icon, color=fg, size=18), ft.Text(text, size=13, color=T.TEXT, expand=True)],
                               spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
                        bgcolor=bg, border_radius=12, padding=ft.Padding.symmetric(horizontal=14, vertical=10))


def section(title, icon, tone, *controls, **kw):
    return T.card(ft.Column([ft.Row([T.icon_tile(icon, tone, 34), ft.Text(title, size=16, weight=ft.FontWeight.W_700)],
                                    spacing=10), *controls], spacing=12, tight=True), **kw)


def dt_text(v):
    if not v:
        return ""
    if isinstance(v, dt.datetime):
        return rocdate.show(v.date()) + v.strftime(" %H:%M")
    return rocdate.show(v)


def hm(v):
    return v.strftime("%H:%M") if v else ""


def hours(v):
    if v in (None, ""):
        return ""
    s = "%.2f" % float(v)
    return s.rstrip("0").rstrip(".")


class PillTabs(ft.Row):
    """簡單的分頁按鈕列（避免 Tabs 在不同平台的版面問題）。"""

    def __init__(self, labels, on_change, selected=0):
        self.labels, self.on_change, self.selected = labels, on_change, selected
        super().__init__(spacing=6, wrap=True, run_spacing=6)
        self._render()

    def _render(self):
        self.controls = [ft.Container(ft.Text(t, size=13, weight=ft.FontWeight.W_700 if i == self.selected else None,
                                              color=ft.Colors.WHITE if i == self.selected else T.PRIMARY),
                                      bgcolor=T.PRIMARY if i == self.selected else "#EAF0F8", border_radius=18,
                                      padding=ft.Padding.symmetric(horizontal=14, vertical=7), ink=True,
                                      on_click=lambda e, i=i: self.pick(i)) for i, t in enumerate(self.labels)]

    def pick(self, i):
        self.selected = i
        self._render()
        self.on_change(i)
