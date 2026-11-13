"""差勤畫面：排班表（月班表格，選班別再點格子）、打卡紀錄、出勤日報、出勤月報、天災停班。"""
import datetime as dt

import flet as ft

from .. import rocdate
from ..attendance import DISASTER_KINDS
from . import common as C
from . import theme as T

WD = "一二三四五六日"
CELL_W, CELL_H, NAME_W = 40, 30, 150


def text_color(bg):
    h = (bg or "#9E9E9E").lstrip("#")[-6:]
    r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)
    return "#1F2937" if (r * 299 + g * 587 + b * 114) / 1000 > 160 else "#FFFFFF"


class Roster(ft.Column):
    """月排班表：上方選班別（像畫筆），再點員工的日期格子；國定假日、週末以顏色標示。
    可循環排班、匯入／匯出月班表系統 XML、CSV，以及匯出到小柯班表助手。"""

    def __init__(self, ctx, ym=None):
        self.ctx = ctx
        b = ctx.books
        self.editable = b.can("ATT", 2)
        self.ym = C.ym_dropdown(ym or C.ym_now(), lambda e: self.load())
        self.dept = C.dept_dropdown(ctx, "", lambda e: self.load(), width=150)
        self.brush = ""
        self.palette = ft.Row(spacing=6, wrap=True, run_spacing=6)
        self.table = ft.Column(spacing=0)
        self.cells = {}
        tools = [self.ym, self.dept]
        if self.editable:
            tools.append(T.btn("循環排班", ft.Icons.AUTO_MODE, lambda e: self.fill()))
        if self.editable and not ctx.app.mobile:
            tools += [
                      ft.PopupMenuButton(content=T.btn("匯入", ft.Icons.UPLOAD_FILE, None, kind="outline"), items=[
                          ft.PopupMenuItem("月班表系統 XML 備份", icon=ft.Icons.CODE, on_click=self.import_xml),
                          ft.PopupMenuItem("Excel（CSV）班表", icon=ft.Icons.TABLE_VIEW, on_click=self.import_csv)])]
        if not ctx.app.mobile:                       # 檔案匯入匯出在電腦上操作
            tools.append(ft.PopupMenuButton(content=T.btn("匯出", ft.Icons.DOWNLOAD, None, kind="outline"), items=[
                ft.PopupMenuItem("月班表系統 XML", icon=ft.Icons.CODE, on_click=self.export_xml),
                ft.PopupMenuItem("Excel（CSV）班表", icon=ft.Icons.TABLE_VIEW, on_click=self.export_csv),
                ft.PopupMenuItem("小柯班表助手（手機）", icon=ft.Icons.PHONE_IPHONE, on_click=lambda e: self.export_xk())]))
        super().__init__([T.page_header(ft.Icons.CALENDAR_VIEW_MONTH, "排班表", "選上方的班別，再點員工的日期格子；"
                                        "沒有排班的日子依預設班別（週一～五預設班、週六休息日、週日例假）", "teal", tools),
                          T.card(ft.Column([self.palette], spacing=6), padding=12),
                          ft.Container(ft.Column([ft.Row([self.table], scroll=ft.ScrollMode.AUTO)],
                                                 scroll=ft.ScrollMode.AUTO, expand=True),
                                       expand=True, bgcolor=T.CARD, border_radius=12, border=ft.Border.all(1, T.LINE),
                                       padding=8)], spacing=12, expand=True)
        self.load(False)

    def load(self, upd=True):
        b = self.ctx.books
        m = self.ctx.guard(b.roster_month, self.ym.value, self.dept.value or "")
        if not m:
            return
        self.m = m
        self.shifts = {s["code"]: s for s in m["shifts"]}
        if self.brush not in self.shifts:
            self.brush = next(iter(self.shifts), "")
        self.render_palette()
        days = m["days"]
        head = [ft.Container(ft.Text("員工", size=12, weight=ft.FontWeight.W_700), width=NAME_W, height=40,
                             alignment=ft.Alignment.CENTER_LEFT, padding=ft.Padding.only(left=6))]
        for d in days:
            hol = m["cal"].get(d)
            wk = d.weekday() >= 5
            head.append(ft.Container(ft.Column([ft.Text(str(d.day), size=12, weight=ft.FontWeight.W_700,
                                                        color=T.DANGER if hol or wk else T.TEXT),
                                                ft.Text(WD[d.weekday()], size=10, color=T.DANGER if hol or wk else T.MUTED)],
                                               spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                     width=CELL_W, height=40, alignment=ft.Alignment.CENTER, tooltip=hol or None,
                                     bgcolor="#FFF1F2" if hol else ("#F8FAFC" if wk else None)))
        head += [ft.Container(ft.Text(t, size=11, weight=ft.FontWeight.W_700), width=w, alignment=ft.Alignment.CENTER)
                 for t, w in (("上班", 44), ("時數", 52), ("休", 36))]
        rows = [ft.Row(head, spacing=0)]
        self.cells = {}
        for r in m["rows"]:
            line = [ft.Container(ft.Text("%s %s" % (r["emp"], r["name"]), size=12, max_lines=1,
                                         overflow=ft.TextOverflow.ELLIPSIS), width=NAME_W, height=CELL_H,
                                 alignment=ft.Alignment.CENTER_LEFT, padding=ft.Padding.only(left=6))]
            for c in r["cells"]:
                cell = self._cell(r["emp"], c)
                self.cells[(r["emp"], c["d"])] = cell
                line.append(cell)
            st = r["stat"]
            line += [ft.Container(ft.Text(str(st["work"]), size=12), width=44, alignment=ft.Alignment.CENTER),
                     ft.Container(ft.Text("%.0f" % st["hours"], size=12), width=52, alignment=ft.Alignment.CENTER),
                     ft.Container(ft.Text(str(st["off"]), size=12), width=36, alignment=ft.Alignment.CENTER)]
            rows.append(ft.Row(line, spacing=0))
        # 每日統計
        codes = [c for c, s in self.shifts.items() if s["day_type"] == "W"]
        for code in codes:
            if not any(dd.get(code) for dd in m["daily"]):
                continue
            s = self.shifts[code]
            line = [ft.Container(ft.Text("%s %s 人數" % (code, s["name"]), size=11, color=T.MUTED), width=NAME_W,
                                 height=24, padding=ft.Padding.only(left=6), alignment=ft.Alignment.CENTER_LEFT)]
            line += [ft.Container(ft.Text(str(dd.get(code, "")) if dd.get(code) else "", size=11, color=T.MUTED),
                                  width=CELL_W, alignment=ft.Alignment.CENTER) for dd in m["daily"]]
            rows.append(ft.Row(line, spacing=0))
        total = [ft.Container(ft.Text("合計上班人數", size=12, weight=ft.FontWeight.W_700), width=NAME_W, height=28,
                              padding=ft.Padding.only(left=6), alignment=ft.Alignment.CENTER_LEFT)]
        total += [ft.Container(ft.Text(str(sum(dd.values())), size=12, weight=ft.FontWeight.W_700), width=CELL_W,
                               alignment=ft.Alignment.CENTER) for dd in m["daily"]]
        rows.append(ft.Row(total, spacing=0))
        self.table.controls = rows if m["rows"] else [T.empty_state(ft.Icons.GROUPS, "這個月沒有在職員工")]
        if upd:
            self.update()

    def _cell(self, emp, c):
        color = c["color"] or "#9E9E9E"
        light = not c["set"]
        return ft.Container(ft.Text(c["code"], size=11, weight=ft.FontWeight.W_700,
                                    color=color if light else text_color(color)),
                            width=CELL_W - 2, height=CELL_H - 2, margin=1, border_radius=6, alignment=ft.Alignment.CENTER,
                            bgcolor=ft.Colors.with_opacity(0.12, color) if light else color,
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, color)) if light else None,
                            tooltip="%s %s（%s）" % (rocdate.show(c["d"]), c["code"], "預設" if light else "已排班"),
                            on_click=(lambda e, emp=emp, d=c["d"]: self.paint(emp, d)) if self.editable else None,
                            ink=self.editable)

    def render_palette(self):
        items = [T.muted("畫筆：", 13)]
        for code, s in self.shifts.items():
            sel = code == self.brush
            items.append(ft.Container(ft.Text("%s %s" % (code, s["name"]), size=12, weight=ft.FontWeight.W_700,
                                              color=text_color(s["color"]) if sel else s["color"]),
                                      bgcolor=s["color"] if sel else ft.Colors.with_opacity(0.1, s["color"]),
                                      border=ft.Border.all(2 if sel else 1, s["color"]), border_radius=16,
                                      padding=ft.Padding.symmetric(horizontal=10, vertical=5), ink=True,
                                      on_click=lambda e, c=code: self.set_brush(c)))
        sel = self.brush == ""
        items.append(ft.Container(ft.Text("清除（回預設）", size=12, color=ft.Colors.WHITE if sel else T.MUTED),
                                  bgcolor=T.MUTED if sel else None, border=ft.Border.all(1, T.MUTED), border_radius=16,
                                  padding=ft.Padding.symmetric(horizontal=10, vertical=5), ink=True,
                                  on_click=lambda e: self.set_brush("")))
        self.palette.controls = items

    def set_brush(self, code):
        self.brush = code
        self.render_palette()
        self.palette.update()

    def paint(self, emp, d):
        b = self.ctx.books
        if self.ctx.guard(b.set_roster, emp, d, self.brush) is None:
            return
        c = b.roster_cell(emp, d)
        cell = self.cells.get((emp, d))
        if cell:
            new = self._cell(emp, c)
            cell.content, cell.bgcolor, cell.border, cell.tooltip = new.content, new.bgcolor, new.border, new.tooltip
            cell.update()

    def fill(self):
        b = self.ctx.books
        first, last = rocdate.read(self.ym.value[:4] + "/" + self.ym.value[4:] + "/01"), None
        last = rocdate.month_last(first)
        checks = {r["emp"]: ft.Checkbox(label="%s %s" % (r["emp"], r["name"]), value=True) for r in self.m["rows"]}
        d1 = T.date_field("開始日", first, width=160)
        d2 = T.date_field("結束日", last, width=160)
        pat = T.field("循環樣式（班別代號，以逗號分隔）", "D,D,D,D,D,休,例", width=360,
                      hint_text="例：M,M,E,E,N,N,休,例 或 D,D,D,D,D,休,例")
        hol = T.switch("國定假日自動排「國」", True)
        over = T.switch("覆蓋已排的班", True)

        def go(e):
            sel = [k for k, c in checks.items() if c.value]
            if not sel:
                self.ctx.toast("請至少選一位員工", True)
                return
            n = self.ctx.guard(b.fill_roster, sel, d1.value, d2.value, pat.value, hol.value, over.value)
            if n:
                self.ctx.close()
                self.ctx.toast("已排 %d 格" % n)
                self.load()
        codes = "、".join("%s=%s" % (c, s["name"]) for c, s in self.shifts.items())
        self.ctx.dialog("循環排班", ft.Column([
            ft.Row([d1, d2], wrap=True), pat, T.muted("可用的班別：" + codes, 12), ft.Row([hol, over], wrap=True),
            T.muted("套用員工（樣式從開始日的第 1 個開始循環）", 13),
            ft.Container(ft.Column([ft.Container(c, width=260) for c in checks.values()], scroll=ft.ScrollMode.AUTO,
                                   spacing=0), height=220, border=ft.Border.all(1, T.LINE), border_radius=10, padding=6)],
            tight=True, spacing=10), [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()),
                                      T.btn("排班", ft.Icons.AUTO_MODE, go)], icon=ft.Icons.AUTO_MODE, tone="teal",
            width=560)

    async def import_xml(self, e):
        files = await ft.FilePicker().pick_files(dialog_title="選擇月班表系統 XML 備份", allowed_extensions=["xml"])
        if not files or not files[0].path:
            return
        r = self.ctx.guard(self.ctx.books.import_rcw_xml, files[0].path)
        if r:
            msg = "已匯入 %s 共 %d 格。" % ("、".join(rocdate.ym_show(x) for x in r["months"]), r["entries"])
            if r["new_shifts"]:
                msg += "\n自動建立班別：%s（時間依代號歸類，可到「班別」修改）" % "、".join(r["new_shifts"])
            if r["unknown_emps"]:
                msg += "\n找不到員工（未匯入）：%s" % "、".join(r["unknown_emps"][:20])
            self.ctx.dialog("匯入結果", ft.Text(msg, size=14, selectable=True),
                            [T.btn("確定", on_click=lambda e: self.ctx.close())], icon=ft.Icons.CODE, tone="teal")
            self.load()

    async def import_csv(self, e):
        path = await self.ctx.pick_csv("選擇 %s 的班表（CSV）" % rocdate.ym_show(self.ym.value))
        if not path:
            return
        r = self.ctx.guard(self.ctx.books.import_roster_csv, self.ym.value, path)
        if r:
            n, errs = r
            self.ctx.toast("已匯入 %d 格%s" % (n, "，%d 個錯誤：%s" % (len(errs), errs[0]) if errs else ""), bool(errs))
            self.load()

    async def export_xml(self, e):
        ym = self.ym.value
        await self.ctx.save_generated("月班表備份_%s.xml" % ym,
                                      lambda p: self.ctx.books.export_rcw_xml([ym], p, self.dept.value or ""),
                                      open_after=False)
        self.ctx.toast("已匯出（可在月班表系統「匯入 XML 備份」）")

    async def export_csv(self, e):
        ym = self.ym.value
        await self.ctx.save_generated("班表_%s.csv" % ym,
                                      lambda p: self.ctx.books.roster_csv_template(ym, p, self.dept.value or ""))

    def export_xk(self):
        b = self.ctx.books
        emp = C.emp_dropdown(self.ctx, "", width=260, blank=None)
        m1 = C.ym_dropdown(self.ym.value, label="開始月份")
        m2 = C.ym_dropdown(self.ym.value, label="結束月份")

        async def go(e):
            if not emp.value:
                self.ctx.toast("請選員工", True)
                return
            self.ctx.close()
            await self.ctx.save_generated("小柯班表_%s.zip" % emp.value,
                                          lambda p: b.export_xiaoke_shift(emp.value, m1.value, m2.value, p),
                                          open_after=False)
            self.ctx.toast("已匯出：傳到員工手機後，在小柯班表助手「⋯ → 還原班表」")
        self.ctx.dialog("匯出到小柯班表助手", ft.Column([
            emp, ft.Row([m1, m2], wrap=True),
            C.info_box("產生小柯班表助手（Android／iPhone／iPad）的備份 ZIP，內含班別時間、顏色與國定假日。"
                       "注意：「還原班表」會取代手機上原本的班表資料，建議員工先在手機「⋯ → 備份班表」。", "amber")],
            tight=True, spacing=12), [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()),
                                      T.btn("匯出", ft.Icons.PHONE_IPHONE, go)], icon=ft.Icons.PHONE_IPHONE, tone="teal")


class Punches(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        today = rocdate.today()
        self.d1 = T.date_field("起", today - dt.timedelta(days=7), width=150)
        self.d2 = T.date_field("迄", today, width=150)
        self.emp = C.emp_dropdown(ctx, "", width=200)
        self.pending = T.switch("只看待確認", False, on_change=lambda e: self.load())
        self.grid = T.Grid([("ts", "時間", "s", 140), ("emp", "編號", "s", 70), ("name", "姓名", "s", 80),
                            ("kind_name", "上下班", "s", 60), ("src_name", "方式", "s", 80), ("state", "狀態", "s", 70),
                            ("distance", "距離(公尺)", "s", 80), ("site_name", "地點", "s", 100), ("accuracy", "精確度", "s", 60),
                            ("note", "說明", "s", 260), ("device", "裝置", "s", 160)], on_pick=self.pick)
        tools = [self.d1, self.d2, self.emp, T.btn("查詢", ft.Icons.SEARCH, lambda e: self.load()), self.pending,
                 ctx.export_button(self.grid, "打卡紀錄")]
        if b.can("ATT", 2):
            tools.insert(4, T.btn("補登打卡", ft.Icons.ADD_ALARM, lambda e: self.add(), kind="outline"))
        super().__init__([T.page_header(ft.Icons.FINGERPRINT, "打卡紀錄", "手機 GPS、電腦打卡與補登；超出範圍的打卡列為待確認",
                                        "teal", tools), self.grid], spacing=12, expand=True)
        self.load(False)

    def load(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.punches, self.d1.value, self.d2.value, self.emp.value or "",
                              self.pending.value) or []
        for r in rows:
            r["ts"] = C.dt_text(r["ts"]) + r["ts"].strftime(":%S") if isinstance(r["ts"], dt.datetime) else r["ts"]
            r["distance"] = "" if r["distance"] is None else str(r["distance"])
            r["accuracy"] = "" if r["accuracy"] is None else str(r["accuracy"])
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def pick(self, r):
        b = self.ctx.books
        if not b.can("ATT", 2):
            return
        acts = [T.btn("關閉", kind="ghost", on_click=lambda e: self.ctx.close())]
        if r["lat"] is not None:
            acts.insert(0, T.btn("在地圖查看", ft.Icons.MAP, lambda e: self.ctx.page.launch_url(
                "https://www.openstreetmap.org/?mlat=%s&mlon=%s#map=18/%s/%s" % (r["lat"], r["lon"], r["lat"], r["lon"])),
                kind="outline"))
        if r["void"]:
            acts.append(T.btn("還原", ft.Icons.RESTORE, lambda e: self.set(r, void=False)))
        else:
            if not r["ok"]:
                acts.append(T.btn("確認有效", ft.Icons.CHECK, lambda e: self.set(r, ok=True), kind="accent"))
            acts.append(T.btn("作廢", ft.Icons.BLOCK, lambda e: self.set(r, void=True), kind="danger"))
        self.ctx.dialog("打卡紀錄", ft.Column([
            ft.Text("%s %s　%s %s" % (r["emp"], r["name"], r["kind_name"], r["ts"]), size=15, weight=ft.FontWeight.W_700),
            T.muted("方式：%s　狀態：%s" % (r["src_name"], r["state"])), T.muted(r["note"] or ""),
            T.muted("座標：%s, %s　精確度 %s 公尺" % (r["lat"], r["lon"], r["accuracy"]) if r["lat"] is not None else "")],
            tight=True, spacing=8), acts, icon=ft.Icons.FINGERPRINT, tone="teal")

    def set(self, r, **kw):
        if self.ctx.guard(self.ctx.books.set_punch, r["id"], **kw, ok="已更新"):
            self.ctx.close()
            self.load()

    def add(self):
        emp = C.emp_dropdown(self.ctx, "", width=240, blank=None)
        ts = T.field("日期時間", rocdate.show(rocdate.today()) + " 09:00", width=200, hint_text="115/11/13 08:55")
        kind = T.dropdown("種類", [("I", "上班"), ("O", "下班")], "I", width=120, filterable=False)
        note = T.field("原因", "忘記打卡", width=300)

        def go(e):
            if self.ctx.guard(self.ctx.books.add_punch, emp.value, ts.value, kind.value, note.value, ok="已補登"):
                self.ctx.close()
                self.load()
        self.ctx.dialog("補登打卡", ft.Column([emp, ft.Row([ts, kind], wrap=True), note], tight=True, spacing=12),
                        [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("補登", ft.Icons.SAVE, go)],
                        icon=ft.Icons.ADD_ALARM, tone="teal")


class Daily(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        today = rocdate.today()
        self.d1 = T.date_field("起", today, width=150)
        self.d2 = T.date_field("迄", today, width=150)
        self.dept = C.dept_dropdown(ctx, "", width=150)
        self.only = T.switch("只看異常", False, on_change=lambda e: self.load())
        self.grid = T.Grid([("d", "日期", "d", 90), ("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("code", "班別", "s", 50),
                            ("plan", "應上班", "s", 100), ("in", "上班", "s", 60), ("out", "下班", "s", 60),
                            ("late", "遲到", "s", 50), ("early", "早退", "s", 50), ("leave", "請假(時)", "s", 70),
                            ("status", "狀態", "s", 300)], row_style=self.style)
        super().__init__([T.page_header(ft.Icons.TODAY, "出勤日報", "依排班與打卡自動判斷遲到、早退、曠職、缺打卡", "teal",
                                        [self.d1, self.d2, self.dept, T.btn("查詢", ft.Icons.SEARCH, lambda e: self.load()),
                                         self.only, ctx.export_button(self.grid, "出勤日報")]), self.grid],
                         spacing=12, expand=True)
        self.load(False)

    @staticmethod
    def style(r):
        if r.get("bad"):
            return dict(color=T.DANGER)
        return None

    def load(self, upd=True):
        b = self.ctx.books
        d1, d2 = rocdate.read(self.d1.value), rocdate.read(self.d2.value)
        if (d2 - d1).days > 62:
            self.ctx.toast("一次最多查 62 天", True)
            return
        if not b.can("ATT", 1):
            return
        recs = self.ctx.guard(b.attendance_daily, d1, d2, self.dept.value or "") or []
        rows = []
        for r in recs:
            bad = bool(r["late"] or r["early"] or r["absent"] or r["missing"])
            if self.only.value and not bad:
                continue
            rows.append(dict(d=r["d"], emp=r["emp"], name=r["name"], code=r["code"],
                             plan="%s～%s" % (C.hm(r["start"]), C.hm(r["end"])) if r["start"] else r["sname"],
                             **{"in": C.hm(r["in_ts"]), "out": C.hm(r["out_ts"])}, late=r["late"] or "",
                             early=r["early"] or "", leave=C.hours(r["leave_min"] / 60) if r["leave_min"] else "",
                             status=r["status"], bad=bad))
        self.grid.set_rows(rows)
        if upd:
            self.update()


class Monthly(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.ym = C.ym_dropdown(None, lambda e: self.load())
        self.dept = C.dept_dropdown(ctx, "", lambda e: self.load(), width=150)
        self.grid = T.Grid([("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("sched_days", "應出勤日", "s", 70),
                            ("attend_days", "出勤日", "s", 60), ("late_cnt", "遲到次", "s", 60), ("late_min", "遲到分", "s", 60),
                            ("early_min", "早退分", "s", 60), ("absent_hours", "曠職時", "s", 60), ("missing", "缺卡", "s", 50),
                            ("leave_hours", "請假時", "s", 60), ("ot_hours", "加班時", "s", 60), ("closure_days", "停班日", "s", 60)])
        super().__init__([T.page_header(ft.Icons.DATE_RANGE, "出勤月報", "每位員工整月的出勤彙總（薪資計算依此扣款與計算全勤）",
                                        "teal", [self.ym, self.dept, ctx.export_button(self.grid, "出勤月報")]), self.grid],
                         spacing=12, expand=True)
        self.load(False)

    def load(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.attendance_month, self.ym.value, self.dept.value or "") or []
        for r in rows:
            for k in ("leave_hours", "ot_hours", "absent_hours"):
                r[k] = C.hours(r[k])
        self.grid.set_rows(rows)
        if upd:
            self.update()


class Disasters(ft.Row):
    """天然災害（颱風、地震、水災）與疫情等不可預期事件的停班登錄。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.editable = ctx.books.can("ATT", 2)
        self.grid = T.Grid([("d", "日期", "d", 90), ("kind_name", "種類", "s", 60), ("title", "名稱", "s", 160),
                            ("period_name", "時段", "s", 60), ("pay_name", "工資", "s", 80), ("work_extra", "出勤加給(倍)", "s", 90),
                            ("scope", "部門", "s", 100)], on_pick=self.edit)
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        left = ft.Column([T.page_header(ft.Icons.THUNDERSTORM, "天災停班（颱風地震疫情）",
                                        "登錄後，出勤不算曠職、不扣全勤；可設定是否給薪與停班日出勤加給", "sky"), self.grid],
                         expand=True, spacing=12)
        super().__init__([left, T.card(self.form, width=460)], expand=True, spacing=14, data="split",
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.load(False)
        self.edit(None, False)

    def load(self, upd=True):
        rows = self.ctx.books.disasters()
        for r in rows:
            r["kind_name"] = DISASTER_KINDS.get(r["kind"], "")
            r["period_name"] = {"D": "全天", "A": "上午", "P": "下午"}[r["period"]]
            r["pay_name"] = "照常給薪" if r["pay_policy"] == "P" else "不給薪"
            r["work_extra"] = C.hours(r["work_extra"])
            r["scope"] = r["scope"] or "全公司"
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def edit(self, r, upd=True):
        self.cur = r
        r = r or {}
        self.f_d = T.date_field("日期", r.get("d") or rocdate.today(), width=170)
        self.f_kind = T.dropdown("種類", list(DISASTER_KINDS.items()), r.get("kind") or "typhoon", width=140, filterable=False)
        self.f_title = T.field("名稱", r.get("title") or "", hint_text="例：鳳凰颱風停止上班")
        self.f_period = T.dropdown("停班時段", [("D", "全天"), ("A", "上午"), ("P", "下午")], r.get("period") or "D",
                                   width=140, filterable=False)
        self.f_pay = T.dropdown("未出勤者的工資", [("P", "照常給薪（建議）"), ("U", "不給薪（不扣全勤、不算曠職）")],
                                r.get("pay_policy") or "P", filterable=False)
        self.f_extra = T.field("停班日仍出勤：加發幾倍日薪", r.get("work_extra") or "1", width=220,
                               text_align=ft.TextAlign.RIGHT)
        self.f_scope = T.field("適用部門代號（逗號分隔，空白＝全公司）", r.get("scope") if r.get("scope") != "全公司" else "")
        self.f_memo = T.field("說明", r.get("memo") or "", multiline=True)
        for c in (self.f_d, self.f_kind, self.f_title, self.f_period, self.f_pay, self.f_extra, self.f_scope, self.f_memo):
            c.disabled = not self.editable
        acts = []
        if self.editable:
            acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save()),
                    T.btn("新增", ft.Icons.ADD, lambda e: self.edit(None), kind="outline")]
            if self.cur:
                acts.append(T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger"))
        self.form.controls = [
            ft.Row([T.icon_tile(ft.Icons.THUNDERSTORM, "sky", 40),
                    ft.Text("修改停班事件" if self.cur else "登錄停班事件", size=17, weight=ft.FontWeight.W_700)]),
            ft.Row([self.f_d, self.f_kind], wrap=True), self.f_title, ft.Row([self.f_period]), self.f_pay, self.f_extra,
            self.f_scope, self.f_memo, ft.Row(acts, wrap=True, spacing=8),
            C.info_box("依「天然災害發生事業單位勞工出勤管理及工資給付要點」：各縣市政府宣布停止上班時，勞工未出勤不得視為"
                       "曠工、遲到或請假，不得扣發全勤獎金、解僱或為不利處分；工資是否給付由勞雇協商（鼓勵照給）。"
                       "停班日仍出勤者，雇主宜加給工資並提供必要的交通與安全保護。疫情等事件依主管機關公告辦理。")]
        if upd:
            self.update()

    def save(self):
        row = dict(d=self.f_d.value, kind=self.f_kind.value, title=self.f_title.value, period=self.f_period.value,
                   pay_policy=self.f_pay.value, work_extra=self.f_extra.value or 0, scope=self.f_scope.value,
                   memo=self.f_memo.value)
        if self.ctx.guard(self.ctx.books.save_disaster, row, self.cur["id"] if self.cur else None, ok="已儲存"):
            self.load(False)
            self.edit(None)

    def delete(self):
        if self.ctx.guard(self.ctx.books.delete_disaster, self.cur["id"], ok="已刪除"):
            self.load(False)
            self.edit(None)
