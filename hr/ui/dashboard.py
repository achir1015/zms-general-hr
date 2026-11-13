"""首頁：關鍵數字、近 12 個月人事成本、快捷功能、待辦提醒。（員工自助在 selfview.py）"""
import datetime as dt
from decimal import Decimal

import flet as ft

from .. import rocdate
from . import common as C
from . import theme as T


class Dashboard(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b, app = ctx.books, ctx.app
        d = b.dashboard()
        comp = b.company()
        hour = dt.datetime.now().hour
        hello = "早安" if hour < 11 else "午安" if hour < 18 else "晚安"
        chips = [hero_chip(ft.Icons.CALENDAR_MONTH, rocdate.show(rocdate.today())),
                 hero_chip(ft.Icons.LOCK_CLOCK, "已關帳至 %s" % rocdate.ym_show(comp["closed_ym"]) if comp.get("closed_ym")
                           else "尚未關帳")]
        if d["gl_pending"]:
            chips.append(hero_chip(ft.Icons.SYNC_ALT, "待拋轉會計 %d 筆" % d["gl_pending"]))
        hero = ft.Container(ft.Row([
            ft.Column([
                ft.Text("%s，%s" % (hello, b.user["name"]), size=26, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE),
                ft.Text(comp.get("name") or "請先到「系統管理 → 公司設定」輸入公司名稱", size=15, color="#CFE0F7"),
                ft.Container(height=6), ft.Row(chips, spacing=10, wrap=True)], spacing=2, expand=True),
            ft.Image(src="icon.png", width=96, height=96, opacity=0.95)]),
            padding=26, border_radius=20,
            gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT,
                                       colors=[T.PRIMARY_DARK, T.PRIMARY, "#178A8F"]),
            shadow=ft.BoxShadow(blur_radius=24, spread_radius=-8, color="#551E4D8C", offset=ft.Offset(0, 10)))
        tb = d.get("today") or {}
        cards = [T.kpi("在職人數", "%d 人" % d["headcount"], ft.Icons.GROUPS, "violet",
                       sub="本月到職 %d、離職 %d" % (d["joins"], d["leaves"]), on_click=lambda e: app.go("employees"))]
        if tb:
            cards.append(T.kpi("今日已打卡", "%d／%d" % (tb["punched"], tb["scheduled"]), ft.Icons.FINGERPRINT, "teal",
                               sub="請假 %d 人、未到 %d 人" % (tb["on_leave"], len(tb["not_in"])),
                               on_click=lambda e: app.go("att_daily")))
        cards.append(T.kpi("待審核", "%d 件" % (d["pending_leave"] + d["pending_ot"]), ft.Icons.PENDING_ACTIONS, "amber",
                           sub="請假 %d、加班 %d" % (d["pending_leave"], d["pending_ot"]),
                           on_click=lambda e: app.go("leaves")))
        lr = d.get("last_run")
        if b.see_salary and lr:
            cards.append(T.kpi("最近月薪（應發）", T.amt(lr["gross"]), ft.Icons.PAYMENTS, "green",
                               sub="%s　公司負擔 %s" % (rocdate.ym_show(lr["ym"]), T.amt(lr["employer_cost"])),
                               on_click=lambda e: app.go("payroll")))
        kpis = T.kpis(cards)
        quick = [("self", "我的打卡", ft.Icons.FINGERPRINT, "teal"), ("roster", "排班表", ft.Icons.CALENDAR_VIEW_MONTH, "blue"),
                 ("leaves", "請假單", ft.Icons.BEACH_ACCESS, "amber"), ("overtime", "加班單", ft.Icons.MORE_TIME, "orange"),
                 ("employees", "員工資料", ft.Icons.BADGE, "violet"), ("payroll", "薪資計算", ft.Icons.CALCULATE, "green"),
                 ("disasters", "颱風停班", ft.Icons.THUNDERSTORM, "sky"), ("occ", "公傷案件", ft.Icons.HEALING, "rose"),
                 ("gl_transfer", "會計拋轉", ft.Icons.SYNC_ALT, "pink"), ("help", "使用說明", ft.Icons.RECORD_VOICE_OVER, "green")]
        quick_tiles = ft.Row([quick_tile(t, ic, tone, lambda e, s=sid: app.go(s)) for sid, t, ic, tone in quick
                              if app.find(sid)], wrap=True, spacing=12, run_spacing=12)
        blocks = [hero, kpis, ft.Row([ft.Text("快捷功能", size=17, weight=ft.FontWeight.W_700, color=T.TEXT)]), quick_tiles]
        todo_items = []
        if d["pending_leave"]:
            todo_items.append(todo_row(ft.Icons.BEACH_ACCESS, "amber", "待審核請假", "%d 件" % d["pending_leave"],
                                       lambda e: app.go("leaves")))
        if d["pending_ot"]:
            todo_items.append(todo_row(ft.Icons.MORE_TIME, "orange", "待審核加班", "%d 件" % d["pending_ot"],
                                       lambda e: app.go("overtime")))
        if d["pending_punch"]:
            todo_items.append(todo_row(ft.Icons.WRONG_LOCATION, "rose", "待確認打卡（超出範圍）", "%d 筆" % d["pending_punch"],
                                       lambda e: app.go("punches")))
        if d["occ_open"]:
            todo_items.append(todo_row(ft.Icons.HEALING, "rose", "處理中的公傷案件", "%d 件" % d["occ_open"],
                                       lambda e: app.go("occ")))
        for ev in d["upcoming_disaster"]:
            todo_items.append(todo_row(ft.Icons.THUNDERSTORM, "sky", "%s %s" % (rocdate.show(ev["d"]), ev["title"]),
                                       "給薪" if ev["pay_policy"] == "P" else "不給薪", lambda e: app.go("disasters")))
        if d["gl_pending"]:
            todo_items.append(todo_row(ft.Icons.SYNC_ALT, "violet", "尚未拋轉會計", "%d 筆" % d["gl_pending"],
                                       lambda e: app.go("gl_transfer")))
        if tb and tb["not_in"]:
            todo_items.append(ft.Text("今日尚未打卡", size=14, weight=ft.FontWeight.W_700, color=T.TEXT))
            for r in tb["not_in"][:8]:
                todo_items.append(ft.Row([T.chip(r["code"], "slate"), ft.Text("%s %s" % (r["emp"], r["name"]), size=13,
                                                                             expand=True),
                                          T.muted(C.hm(r["start"]), 12)], spacing=8))
        if d["birthdays"]:
            todo_items.append(ft.Text("本月壽星", size=14, weight=ft.FontWeight.W_700, color=T.TEXT))
            todo_items.append(ft.Row([T.chip("%s %d/%d" % (x["name"], x["birthday"].month, x["birthday"].day), "pink",
                                             ft.Icons.CAKE) for x in d["birthdays"][:8]], wrap=True, spacing=6))
        todo = T.card(ft.Column([
            ft.Row([T.icon_tile(ft.Icons.PENDING_ACTIONS, "amber", 36),
                    ft.Text("待辦提醒", size=17, weight=ft.FontWeight.W_700)], spacing=10),
            ft.Column(todo_items or [T.empty_state(ft.Icons.TASK_ALT, "目前沒有待辦事項")], spacing=6,
                      scroll=ft.ScrollMode.AUTO, expand=True)], spacing=12), expand=2, height=340)
        if d["trend"]:
            chart = T.card(ft.Column([
                ft.Row([T.icon_tile(ft.Icons.AUTO_GRAPH, "violet", 36),
                        ft.Text("近 12 個月人事成本", size=17, weight=ft.FontWeight.W_700),
                        ft.Container(expand=True), legend("應發薪資", "#14B8A6"), legend("公司負擔保費", "#F59E0B")],
                       spacing=10), bars(d["trend"])], spacing=14), expand=3, height=340)
            blocks.append(T.split(chart, todo, spacing=16))
        else:
            blocks.append(todo)
        super().__init__(blocks, spacing=18, scroll=ft.ScrollMode.AUTO, expand=True)


def big_btn(text, icon, color, on_click):
    return ft.Container(ft.Row([ft.Icon(icon, color=ft.Colors.WHITE, size=26),
                                ft.Text(text, size=18, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE)],
                               spacing=10, tight=True), bgcolor=color, border_radius=16, ink=True, on_click=on_click,
                        padding=ft.Padding.symmetric(horizontal=26, vertical=18),
                        shadow=ft.BoxShadow(blur_radius=16, spread_radius=-6, color="#55000000", offset=ft.Offset(0, 6)))


def hero_chip(icon, text):
    return ft.Container(ft.Row([ft.Icon(icon, size=15, color=ft.Colors.WHITE), ft.Text(text, size=12,
                                                                                    color=ft.Colors.WHITE)],
                               spacing=6, tight=True), bgcolor="#33FFFFFF", border_radius=20,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=5))


def quick_tile(title, icon, tone, on_click):
    return ft.Container(ft.Column([T.icon_tile(icon, tone, 48, radius=14),
                                   ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=T.TEXT)],
                                  horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        width=112, padding=ft.Padding.symmetric(vertical=16), bgcolor=T.CARD, border_radius=16,
                        border=ft.Border.all(1, T.LINE), on_click=on_click, ink=True,
                        shadow=ft.BoxShadow(blur_radius=14, spread_radius=-6, color="#1A1E3A5F",
                                            offset=ft.Offset(0, 4)))


def todo_row(icon, tone, title, value, on_click):
    return ft.Container(ft.Row([T.icon_tile(icon, tone, 30, radius=9), ft.Text(title, size=13, expand=True),
                                ft.Text(value, size=13, weight=ft.FontWeight.W_700, color=T.TEXT),
                                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=T.MUTED)], spacing=10),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6), border_radius=10, bgcolor="#F7F9FC",
                        on_click=on_click, ink=True)


def legend(text, color):
    return ft.Row([ft.Container(width=12, height=12, bgcolor=color, border_radius=3), T.muted(text, 12)],
                  spacing=5, tight=True)


def bars(months, h=200):
    top = max([Decimal(1)] + [Decimal(m["g"] or 0) + Decimal(m["er"] or 0) for m in months])
    cols = []
    for m in months:
        g, er = Decimal(m["g"] or 0), Decimal(m["er"] or 0)
        cols.append(ft.Column([
            ft.Column([ft.Container(width=22, height=max(2, float(er / top) * h), bgcolor="#F59E0B",
                                    border_radius=ft.BorderRadius.only(top_left=4, top_right=4),
                                    tooltip="公司負擔 %s" % T.amt(er)),
                       ft.Container(width=22, height=max(2, float(g / top) * h), bgcolor="#14B8A6",
                                    tooltip="應發 %s" % T.amt(g))], spacing=0),
            T.muted("%d月" % int(m["ym"][4:]), 11)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
            alignment=ft.MainAxisAlignment.END))
    return ft.Container(ft.Row(cols, alignment=ft.MainAxisAlignment.SPACE_AROUND,
                               vertical_alignment=ft.CrossAxisAlignment.END), height=h + 26,
                        border=ft.Border.only(bottom=ft.BorderSide(1, T.LINE)))
