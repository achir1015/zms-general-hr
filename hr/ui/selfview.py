"""員工自助：今天的班與打卡（手機 App 用 GPS 定位、電腦用電腦打卡）、我的班表、特休補休餘額、
請假加班申請、薪資單，以及把班表匯出到小柯班表助手（電腦版）。"""
import datetime as dt

import flet as ft

from .. import rocdate
from . import common as C
from . import theme as T
from .dashboard import big_btn


class SelfService(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        self.mobile = bool(getattr(ctx.app, "mobile", False))
        if not b.my_emp:
            super().__init__([T.page_header(ft.Icons.FINGERPRINT, "我的打卡與假勤", "員工自助", "teal"),
                              C.info_box("此帳號沒有對應到員工資料。請系統管理員到「使用者與權限」把帳號對應到員工編號，"
                                         "或在「員工資料」按「建立員工帳號」。", "amber", ft.Icons.WARNING_AMBER)],
                             spacing=16, expand=True)
            return
        self.ym = C.ym_now()
        self.body = ft.Column(spacing=16)
        acts = [T.btn("請假", ft.Icons.BEACH_ACCESS, lambda e: self.leave()),
                T.btn("加班", ft.Icons.MORE_TIME, lambda e: self.ot(), kind="outline")]
        if not self.mobile:
            acts.append(T.btn("匯出到小柯班表助手", ft.Icons.PHONE_IPHONE, self.export_xk, kind="outline"))
        super().__init__([T.page_header(ft.Icons.FINGERPRINT, "我的打卡與假勤", "上下班打卡、班表、請假、加班、薪資單",
                                        "teal", acts), self.body], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
        self.refresh(False)

    def refresh(self, upd=True):
        b = self.ctx.books
        t = b.my_today()
        bal = b.my_balance()
        s = t["shift"]
        shift_text = "%s %s" % (s["code"], s["name"]) + (
            " %s～%s" % (C.hm(s["start"]), C.hm(s["end"])) if s["start"] else "")
        punch_rows = [ft.Row([T.chip("上班" if p["kind"] == "I" else "下班", "teal" if p["kind"] == "I" else "violet"),
                              ft.Text(p["ts"].strftime("%H:%M:%S"), size=15, weight=ft.FontWeight.W_700),
                              T.muted("" if p["ok"] else "待確認", 12)], spacing=10) for p in t["punches"]]
        self.status = ft.Text("", size=14)
        hint = (C.info_box("按下打卡時會取得手機的 GPS 定位，系統確認您在公司打卡範圍內才算有效；"
                           "第一次請允許「使用位置資訊」。") if self.mobile else
                C.info_box("這裡是「電腦打卡」。在外面或要用手機定位打卡時，請用手機 App 或公司公告的打卡網址。"))
        punch_card = C.section("今天 %s（%s）" % (rocdate.show(t["date"]), "一二三四五六日"[t["date"].weekday()]),
                               ft.Icons.TODAY, "teal",
                               ft.Text(shift_text, size=20, weight=ft.FontWeight.W_800, color=T.PRIMARY),
                               ft.Row([big_btn("上班打卡", ft.Icons.LOGIN, "#0F766E", lambda e: self.punch("I")),
                                       big_btn("下班打卡", ft.Icons.LOGOUT, "#6D28D9", lambda e: self.punch("O"))],
                                      spacing=12, wrap=True, run_spacing=10),
                               self.status, hint, *(punch_rows or [T.muted("今天還沒有打卡紀錄")]), expand=1)
        bal_card = C.section("我的假期額度", ft.Icons.HOURGLASS_BOTTOM, "amber",
                             ft.Row([stat_box("特休剩餘", "%s 小時" % C.hours(bal["annual"]),
                                              "約 %s 天" % C.hours(bal["annual"] / 8), "green"),
                                     stat_box("補休剩餘", "%s 小時" % C.hours(bal["comp"]), "", "sky")], spacing=10),
                             expand=1)
        today = dt.date.today()
        lv = b.leave_requests(today - dt.timedelta(days=60), today + dt.timedelta(days=120), b.my_emp)
        lrows = [ft.Container(ft.Row([T.chip(r["lname"], "amber"), ft.Column([
            ft.Text("%s～%s" % (C.dt_text(r["start_at"]), C.dt_text(r["end_at"])[-5:]), size=13),
            T.muted("%s 小時　%s" % (C.hours(r["hours"]), r["status_name"]), 12)], spacing=0, expand=True)], spacing=8),
            padding=ft.Padding.symmetric(vertical=6), on_click=lambda e, r=r: self.pick_leave(r), ink=True)
            for r in lv[:12]] or [T.muted("沒有請假紀錄")]
        srows = [ft.Container(ft.Row([ft.Icon(ft.Icons.RECEIPT_LONG, color=T.ACCENT, size=20), ft.Column([
            ft.Text(r["title"], size=13, weight=ft.FontWeight.W_600),
            T.muted("應發 %s　實發 %s" % (T.amt(r["gross"]), T.amt(r["net"])), 12)], spacing=0, expand=True),
            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=T.MUTED, size=18)], spacing=10),
            padding=ft.Padding.symmetric(vertical=6), on_click=lambda e, r=r: self.open_slip(r), ink=True)
            for r in b.my_payslips()[:12]] or [T.muted("還沒有已確認的薪資單")]
        self.body.controls = [T.split(punch_card, bal_card), self.roster_card(),
                              T.split(C.section("我的請假（點選可撤銷待審核的單）", ft.Icons.BEACH_ACCESS, "amber", *lrows,
                                                expand=1),
                                      C.section("我的薪資單", ft.Icons.RECEIPT_LONG, "green", *srows, expand=1))]
        if upd:
            self.update()

    def roster_card(self):
        """我的月班表（月曆）。"""
        days = self.ctx.books.my_roster(self.ym)
        first = days[0]["d"]
        rows = [ft.Row([ft.Container(ft.Text(w, size=12, color=T.DANGER if w in "六日" else T.MUTED,
                                             weight=ft.FontWeight.W_700), alignment=ft.Alignment.CENTER, height=24,
                                     expand=True) for w in "一二三四五六日"], spacing=4)]
        week = [ft.Container(expand=True) for _ in range(first.weekday())]
        today = dt.date.today()
        for x in days:
            work = x["day_type"] == "W"
            week.append(ft.Container(ft.Column([
                ft.Text(str(x["d"].day), size=11, color=T.DANGER if x["holiday"] or x["d"].weekday() >= 5 else T.MUTED,
                        weight=ft.FontWeight.W_800 if x["d"] == today else None),
                ft.Text(x["code"], size=13, weight=ft.FontWeight.W_800, color=x["color"] if work else T.MUTED,
                        max_lines=1)], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=True, height=50, border_radius=8, alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.with_opacity(0.12, x["color"]) if work else "#F7F9FC",
                border=ft.Border.all(2, T.PRIMARY) if x["d"] == today else None,
                tooltip="%s %s%s" % (x["name"], ("%s～%s" % (C.hm(x["start"]), C.hm(x["end"]))) if x["start"] else "",
                                     ("　" + x["holiday"]) if x["holiday"] else ""),
                on_click=lambda e, x=x: self.ctx.toast("%s %s %s%s" % (
                    rocdate.show(x["d"]), x["name"],
                    ("%s～%s" % (C.hm(x["start"]), C.hm(x["end"]))) if x["start"] else "",
                    ("（%s）" % x["holiday"]) if x["holiday"] else ""))))
            if len(week) == 7:
                rows.append(ft.Row(week, spacing=4))
                week = []
        if week:
            week += [ft.Container(expand=True) for _ in range(7 - len(week))]
            rows.append(ft.Row(week, spacing=4))
        nav = ft.Row([ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda e: self.move(-1)),
                      ft.Text(rocdate.ym_show(self.ym), size=15, weight=ft.FontWeight.W_700),
                      ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self.move(1))],
                     alignment=ft.MainAxisAlignment.CENTER, spacing=4)
        work_days = sum(1 for x in days if x["day_type"] == "W")
        box = C.section("我的班表", ft.Icons.CALENDAR_MONTH, "blue", nav, ft.Column(rows, spacing=4),
                        T.muted("本月上班 %d 天；點日期可看上下班時間" % work_days, 12))
        box.data = T.READY
        return box

    def move(self, n):
        y, m = int(self.ym[:4]), int(self.ym[4:]) - 1 + n
        self.ym = "%04d%02d" % (y + m // 12, m % 12 + 1)
        self.refresh()

    def punch(self, kind):
        if self.mobile:
            self.ctx.page.run_task(self.gps_punch, kind)
            return
        import socket
        r = self.ctx.guard(self.ctx.books.punch, kind, source="pc", device="電腦 " + socket.gethostname())
        if r:
            self.ctx.toast(r["text"])
            self.refresh()

    async def gps_punch(self, kind):
        """手機 App：取得 GPS 定位後打卡（距離由公司電腦判定，手機傳來的結果不採信）。"""
        import flet_geolocator as ftg
        page = self.ctx.page
        self.status.value, self.status.color = "正在取得 GPS 定位…", T.MUTED
        self.status.update()
        geo = getattr(self.ctx.app, "geo", None)
        if geo is None:
            geo = ftg.Geolocator()
            page.services.append(geo)
            page.update()
            self.ctx.app.geo = geo
        try:
            if not await geo.is_location_service_enabled():
                raise RuntimeError("手機的定位服務（GPS）沒有開啟，請到設定開啟「位置」後再打卡")
            perm = await geo.request_permission()
            if perm in (ftg.GeolocatorPermissionStatus.DENIED, ftg.GeolocatorPermissionStatus.DENIED_FOREVER):
                raise RuntimeError("沒有允許本 App 使用位置資訊：請到手機設定 → 應用程式 → 權限 → 位置，選「使用 App 時允許」")
            pos = await geo.get_current_position(ftg.GeolocatorConfiguration(
                accuracy=ftg.GeolocatorPositionAccuracy.BEST))
        except Exception as ex:
            self.status.value, self.status.color = "❌ %s" % ex, T.DANGER
            self.status.update()
            return
        device = "%s App" % ("iPhone" if page.platform == ft.PagePlatform.IOS else "Android")
        if getattr(pos, "mocked", False):
            device += "（模擬定位）"
        r = self.ctx.guard(self.ctx.books.punch, kind, lat=pos.latitude, lon=pos.longitude,
                           accuracy=int(pos.accuracy or 0), device=device)
        if not r:
            self.status.value = ""
            self.status.update()
            return
        self.refresh()
        self.status.value = ("✅ " if r["ok"] else "⚠ ") + r["text"] + ("\n" + r["msg"] if r["msg"] else "")
        self.status.color = T.SUCCESS if r["ok"] else T.WARN
        self.status.update()

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


def stat_box(title, value, sub, tone):
    bg, fg = T.TONES[tone]
    return ft.Container(ft.Column([T.muted(title, 12), ft.Text(value, size=20, weight=ft.FontWeight.W_800, color=fg),
                                   T.muted(sub or " ", 11)], spacing=2), bgcolor=bg, border_radius=14, padding=12,
                        expand=True)
