"""首頁（關鍵數字、近 12 個月人事成本、快捷功能、待辦提醒）與員工自助（電腦打卡、請假加班、薪資單、班表匯出）。"""
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


class SelfService(ft.Column):
    """員工自助：今天的班與電腦打卡、特休補休餘額、請假加班申請、薪資單、匯出到小柯班表助手。"""

    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        if not b.my_emp:
            super().__init__([T.page_header(ft.Icons.FINGERPRINT, "我的打卡與假勤", "員工自助", "teal"),
                              C.info_box("此帳號沒有對應到員工資料。請系統管理員到「使用者與權限」把帳號對應到員工編號，"
                                         "或在「員工資料」按「建立員工帳號」。", "amber", ft.Icons.WARNING_AMBER)],
                             spacing=16, expand=True)
            return
        self.body = ft.Column(spacing=16)
        super().__init__([T.page_header(ft.Icons.FINGERPRINT, "我的打卡與假勤", "上下班打卡、請假、加班、薪資單", "teal",
                                        [T.btn("請假", ft.Icons.BEACH_ACCESS, lambda e: self.leave()),
                                         T.btn("加班", ft.Icons.MORE_TIME, lambda e: self.ot(), kind="outline"),
                                         T.btn("匯出到小柯班表助手", ft.Icons.PHONE_IPHONE, self.export_xk, kind="outline")]),
                          self.body], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
        self.refresh(False)

    def refresh(self, upd=True):
        b = self.ctx.books
        t = b.my_today()
        bal = b.balance_summary(b.my_emp)
        s = t["shift"]
        ps = t["punches"]
        shift_text = "%s %s" % (s["code"], s["name"]) + (" %s～%s" % (C.hm(s["start"]), C.hm(s["end"])) if s["start"] else "")
        punch_rows = [ft.Row([T.chip("上班" if p["kind"] == "I" else "下班", "teal" if p["kind"] == "I" else "violet"),
                              ft.Text(p["ts"].strftime("%H:%M:%S"), size=15, weight=ft.FontWeight.W_700),
                              T.muted("" if p["ok"] else "待確認", 12)], spacing=10) for p in ps]
        punch_card = C.section("今天 %s（%s）" % (rocdate.show(t["date"]), "一二三四五六日"[t["date"].weekday()]),
                               ft.Icons.TODAY, "teal",
                               ft.Text(shift_text, size=20, weight=ft.FontWeight.W_800, color=T.PRIMARY),
                               ft.Row([big_btn("上班打卡", ft.Icons.LOGIN, "#0F766E", lambda e: self.punch("I")),
                                       big_btn("下班打卡", ft.Icons.LOGOUT, "#6D28D9", lambda e: self.punch("O"))],
                                      spacing=16, wrap=True),
                               C.info_box("這裡是「電腦打卡」。在外面或要用手機定位打卡時，請用手機開啟公司提供的打卡網址"
                                          "（人資在「系統管理 → 手機打卡與連線」可以看到網址與 QR Code）。"),
                               *(punch_rows or [T.muted("今天還沒有打卡紀錄")]), expand=1)
        bal_card = C.section("我的假期額度", ft.Icons.HOURGLASS_BOTTOM, "amber",
                             ft.Row([T.kpi("特休剩餘", "%s 小時" % C.hours(bal["annual"]), ft.Icons.BEACH_ACCESS, "green",
                                           sub="約 %s 天" % C.hours(bal["annual"] / 8)),
                                     T.kpi("補休剩餘", "%s 小時" % C.hours(bal["comp"]), ft.Icons.MORE_TIME, "sky")],
                                    spacing=12), expand=1)
        today = dt.date.today()
        lv = b.leave_requests(today - dt.timedelta(days=60), today + dt.timedelta(days=120), b.my_emp)
        lgrid = T.Grid([("lname", "假別", "s", 100), ("start_at", "開始", "s", 140), ("end_at", "結束", "s", 140),
                        ("hours", "時數", "s", 60), ("status_name", "狀態", "s", 80)], height=230,
                       on_pick=self.pick_leave)
        lgrid.set_rows([dict(r, start_at=C.dt_text(r["start_at"]), end_at=C.dt_text(r["end_at"]), hours=C.hours(r["hours"]))
                        for r in lv])
        slips = b.my_payslips()
        sgrid = T.Grid([("ym", "月份", "s", 100), ("title", "名稱", "s", 160), ("gross", "應發", "n", 90),
                        ("net", "實發", "n", 90)], height=230, on_pick=self.open_slip)
        sgrid.set_rows([dict(r, ym=rocdate.ym_show(r["ym"])) for r in slips])
        self.body.controls = [T.split(punch_card, bal_card),
                              T.split(C.section("我的請假（點選可撤銷待審核的單）", ft.Icons.BEACH_ACCESS, "amber", lgrid, expand=1),
                                      C.section("我的薪資單", ft.Icons.RECEIPT_LONG, "green", sgrid, expand=1))]
        if upd:
            self.update()

    def punch(self, kind):
        import socket
        r = self.ctx.guard(self.ctx.books.punch, kind, source="pc", device="電腦 " + socket.gethostname())
        if r:
            self.ctx.toast(r["text"])
            self.refresh()

    def leave(self):
        from .leaveview import leave_dialog
        leave_dialog(self.ctx, self.ctx.books.my_emp, self.refresh)

    def ot(self):
        from .leaveview import ot_dialog
        ot_dialog(self.ctx, self.ctx.books.my_emp, self.refresh)

    def pick_leave(self, r):
        if r["status"] != 0:
            return
        self.ctx.confirm("撤銷請假", "要撤銷這張待審核的請假單嗎？",
                         lambda: self.ctx.guard(self.ctx.books.cancel_leave, r["id"], ok="已撤銷") and self.refresh())

    def open_slip(self, r):
        from ..printing import payslips_page, write_and_open
        b = self.ctx.books
        s = self.ctx.guard(b.payslip, r["id"])
        if s:
            write_and_open(payslips_page(b.company(), [s]), "薪資單")

    async def export_xk(self, e):
        b = self.ctx.books
        ym1, ym2 = C.ym_now(), C.ym_now(2)
        await self.ctx.save_generated("小柯班表_%s.zip" % b.my_emp,
                                      lambda p: b.export_xiaoke_shift(b.my_emp, ym1, ym2, p), open_after=False)
        self.ctx.toast("已匯出本月起 3 個月的班表：傳到手機後在小柯班表助手「⋯ → 還原班表」")


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
