"""請假單、加班單、特休與補休額度（產生特休、手動調整、年度結算折發或遞延、期初餘額匯入）。"""
import datetime as dt

import flet as ft

from .. import laws, rocdate
from . import common as C
from . import theme as T


def leave_dialog(ctx, emp, on_done, approve=False):
    b = ctx.books
    emp_dd = C.emp_dropdown(ctx, emp or "", width=240, blank=None) if not emp or b.can("LEV") else None
    types = b.leave_types()
    lt = T.dropdown("假別", [(t["code"], t["name"]) for t in types], "ANNUAL", width=200, filterable=False)
    today = rocdate.show(rocdate.today())
    s = T.field("開始（日期 時間）", today + " 09:00", width=200)
    e_ = T.field("結束（日期 時間）", today + " 18:00", width=200)
    reason = T.field("事由", "", width=420)
    proxy = C.emp_dropdown(ctx, "", width=240, blank="（無）", label="職務代理人")
    calc = ft.Text("", size=13, color=T.PRIMARY)
    note = ft.Text("", size=12, color=T.MUTED)
    auto = T.switch("直接核准", approve) if b.can("LEV") else None

    def code():
        return (emp_dd.value if emp_dd else None) or emp

    def show_note(ev=None):
        t = next((x for x in types if x["code"] == lt.value), None)
        note.value = t["law_note"] if t else ""
        if t and t["balance"] and code():
            try:
                left = b.balance_info(code(), t["balance"])
                note.value += "　目前剩餘 %s 小時。" % C.hours(left)
            except Exception:
                pass
        try:
            h, txt = b.leave_hours_check(code(), lt.value, s.value, e_.value)
            calc.value = "試算：%s 小時（%s）" % (C.hours(h), txt)
        except Exception as ex:
            calc.value = str(ex)
        try:
            note.update()
            calc.update()
        except Exception:
            pass
    lt.on_select = show_note
    s.on_blur = show_note
    e_.on_blur = show_note

    def go(ev):
        if ctx.guard(b.request_leave, code(), lt.value, s.value, e_.value, reason.value, proxy.value or "",
                     auto.value if auto else False, ok="請假單已送出"):
            ctx.close()
            on_done()
    ctl = ([emp_dd] if emp_dd else []) + [lt, ft.Row([s, e_], wrap=True), calc, reason, proxy, note] + ([auto] if auto else [])
    ctx.dialog("請假", ft.Column(ctl, tight=True, spacing=12),
               [T.btn("取消", kind="ghost", on_click=lambda e: ctx.close()), T.btn("送出", ft.Icons.SEND, go)],
               icon=ft.Icons.BEACH_ACCESS, tone="amber", width=520)
    show_note()


def ot_dialog(ctx, emp, on_done, approve=False):
    b = ctx.books
    emp_dd = C.emp_dropdown(ctx, emp or "", width=240, blank=None) if not emp or b.can("LEV") else None
    d = T.date_field("加班日期", rocdate.today(), width=170)
    s = T.field("開始時間", "18:00", width=110)
    e_ = T.field("結束時間", "20:00", width=110)
    comp = T.dropdown("補償方式", [("P", "加班費"), ("C", "換補休（1 小時換 1 小時）")], "P", width=240, filterable=False)
    dtype = T.dropdown("日別（空白＝依班表自動判斷）", list(laws.OT_DAY.items()), None, width=260, blank="自動判斷",
                       filterable=False)
    reason = T.field("事由", "", width=420)
    auto = T.switch("直接核准", approve) if b.can("LEV") else None

    def go(ev):
        code = (emp_dd.value if emp_dd else None) or emp
        if ctx.guard(b.request_overtime, code, d.value, s.value, e_.value, comp.value, reason.value, dtype.value or None,
                     auto.value if auto else False, ok="加班單已送出"):
            ctx.close()
            on_done()
    ctl = ([emp_dd] if emp_dd else []) + [ft.Row([d, s, e_], wrap=True), comp, dtype, reason,
                                          C.info_box("每月延長工時上限 46 小時；平日前 2 小時 ×4/3、之後 ×5/3；休息日依實際時數"
                                                     " ×4/3、×5/3、×8/3；國定假日、特休日出勤 8 小時內加發 1 日工資。"
                                                     "換補休者，期限內未休完依原加班費率折發工資。")] + ([auto] if auto else [])
    ctx.dialog("加班申請", ft.Column(ctl, tight=True, spacing=12),
               [T.btn("取消", kind="ghost", on_click=lambda e: ctx.close()), T.btn("送出", ft.Icons.SEND, go)],
               icon=ft.Icons.MORE_TIME, tone="orange", width=520)


class _ReqList(ft.Column):
    """請假與加班清單的共用框架。"""
    TITLE = ""
    ICON = ft.Icons.BEACH_ACCESS
    TONE = "amber"

    def __init__(self, ctx):
        self.ctx = ctx
        today = rocdate.today()
        self.d1 = T.date_field("起", today.replace(day=1) - dt.timedelta(days=31), width=150)
        self.d2 = T.date_field("迄", today + dt.timedelta(days=60), width=150)
        self.emp = C.emp_dropdown(ctx, "", width=200)
        self.status = T.dropdown("狀態", [("", "全部"), ("0", "待審核"), ("1", "核准"), ("9", "駁回／撤銷")], "", width=140,
                                 filterable=False, on_select=lambda e: self.load())
        self.grid = self.make_grid()
        tools = [self.d1, self.d2, self.emp, self.status, T.btn("查詢", ft.Icons.SEARCH, lambda e: self.load()),
                 T.btn("新增", ft.Icons.ADD, lambda e: self.new(), kind="accent"), ctx.export_button(self.grid, self.TITLE)]
        super().__init__([T.page_header(self.ICON, self.TITLE, self.SUB, self.TONE, tools), self.grid], spacing=12,
                         expand=True)
        self.load(False)

    def st(self):
        return None if self.status.value in (None, "") else int(self.status.value)


class Leaves(_ReqList):
    TITLE, SUB = "請假單", "依班表計算時數；特休、補休自動扣額度；點選可審核或撤銷"

    def make_grid(self):
        return T.Grid([("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("lname", "假別", "s", 90),
                       ("start", "開始", "s", 130), ("end", "結束", "s", 130), ("hrs", "時數", "s", 50),
                       ("status_name", "狀態", "s", 80), ("reason", "事由", "s", 220)], on_pick=self.pick)

    def load(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.leave_requests, self.d1.value, self.d2.value, self.emp.value or "",
                              self.st()) or []
        for r in rows:
            r["start"], r["end"], r["hrs"] = C.dt_text(r["start_at"]), C.dt_text(r["end_at"]), C.hours(r["hours"])
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def new(self):
        leave_dialog(self.ctx, self.emp.value or "", self.load, approve=True)

    def pick(self, r):
        b = self.ctx.books
        acts = [T.btn("關閉", kind="ghost", on_click=lambda e: self.ctx.close())]
        can_ok = b.can("LEV") or b.is_manager_of(r["emp"])
        if r["status"] == 0 and can_ok:
            acts += [T.btn("駁回", ft.Icons.CLOSE, lambda e: self.act(b.approve_leave, r["id"], False), kind="danger"),
                     T.btn("核准", ft.Icons.CHECK, lambda e: self.act(b.approve_leave, r["id"], True))]
        if r["status"] in (0, 1) and (b.can("LEV") or (r["emp"] == b.my_emp and r["status"] == 0)):
            acts.insert(1, T.btn("撤銷", ft.Icons.UNDO, lambda e: self.act(b.cancel_leave, r["id"]), kind="outline"))
        self.ctx.dialog("請假單", ft.Column([
            ft.Text("%s %s　%s %s 小時" % (r["emp"], r["name"], r["lname"], r["hrs"]), size=15, weight=ft.FontWeight.W_700),
            T.muted("%s ～ %s" % (r["start"], r["end"])), T.muted("事由：%s" % (r["reason"] or "")),
            T.muted("狀態：%s　審核：%s" % (r["status_name"], r["approver"] or ""))], tight=True, spacing=8), acts,
            icon=ft.Icons.BEACH_ACCESS, tone="amber")

    def act(self, fn, *a):
        if self.ctx.guard(fn, *a, ok="已更新"):
            self.ctx.close()
            self.load()


class Overtime(_ReqList):
    TITLE, SUB, ICON, TONE = "加班單", "依勞基法計算加班費；可選換補休；每月 46 小時上限", ft.Icons.MORE_TIME, "orange"

    def make_grid(self):
        return T.Grid([("d", "日期", "d", 90), ("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("time", "時間", "s", 100),
                       ("hrs", "時數", "s", 50), ("day_name", "日別", "s", 110), ("comp_name", "補償", "s", 70),
                       ("amount", "加班費", "n", 80), ("status_name", "狀態", "s", 70), ("reason", "事由", "s", 200)],
                      on_pick=self.pick, totals=("amount",))

    def load(self, upd=True):
        d1, d2 = rocdate.read(self.d1.value), rocdate.read(self.d2.value)
        rows = self.ctx.guard(self.ctx.books.overtime_list, d1, d2, self.emp.value or "", self.st()) or []
        for r in rows:
            r["time"] = "%s～%s" % (C.hm(r["start_at"]), C.hm(r["end_at"]))
            r["hrs"] = C.hours(r["hours"])
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def new(self):
        ot_dialog(self.ctx, self.emp.value or "", self.load, approve=True)

    def pick(self, r):
        b = self.ctx.books
        acts = [T.btn("關閉", kind="ghost", on_click=lambda e: self.ctx.close())]
        if r["status"] == 0 and (b.can("LEV") or b.is_manager_of(r["emp"])):
            acts += [T.btn("駁回", ft.Icons.CLOSE, lambda e: self.act(r["id"], False), kind="danger"),
                     T.btn("核准", ft.Icons.CHECK, lambda e: self.act(r["id"], True))]
        elif r["status"] == 1 and b.can("LEV"):
            acts.append(T.btn("取消核准（駁回）", ft.Icons.UNDO, lambda e: self.act(r["id"], False), kind="danger"))
        self.ctx.dialog("加班單", ft.Column([
            ft.Text("%s %s　%s %s %s 小時" % (r["emp"], r["name"], rocdate.show(r["d"]), r["time"], r["hrs"]), size=15,
                    weight=ft.FontWeight.W_700),
            T.muted("%s　%s　%s" % (r["day_name"], r["comp_name"],
                                   ("加班費約 %s" % T.amt(r["amount"])) if r["amount"] is not None else "")),
            T.muted("事由：%s" % (r["reason"] or "")), T.muted("狀態：%s" % r["status_name"])], tight=True, spacing=8),
            acts, icon=ft.Icons.MORE_TIME, tone="orange")

    def act(self, oid, ok):
        if self.ctx.guard(self.ctx.books.approve_overtime, oid, ok, ok="已更新"):
            self.ctx.close()
            self.load()


class Balances(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        self.year = C.year_dropdown(None, lambda e: self.load())
        self.emp = C.emp_dropdown(ctx, "", lambda e: self.load(), width=200)
        self.dept = C.dept_dropdown(ctx, "", lambda e: self.load(), width=150)
        self.grid = T.Grid([("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("kind_name", "種類", "s", 50),
                            ("start_d", "可用起", "d", 90), ("end_d", "可用迄", "d", 90), ("hrs", "額度(時)", "s", 70),
                            ("used_h", "已用(時)", "s", 70), ("left_h", "剩餘(時)", "s", 70), ("state", "狀態", "s", 100),
                            ("memo", "說明", "s", 240)], on_pick=self.pick)
        tools = [self.year, self.emp, self.dept]
        if b.can("LEV"):
            tools += [T.btn("產生特休", ft.Icons.AUTO_AWESOME, lambda e: self.gen()),
                      ft.PopupMenuButton(content=T.btn("更多", ft.Icons.MORE_HORIZ, None, kind="outline"), items=[
                          ft.PopupMenuItem("手動新增額度", icon=ft.Icons.ADD, on_click=lambda e: self.add()),
                          ft.PopupMenuItem("年度結算（折發／遞延）", icon=ft.Icons.FACT_CHECK, on_click=lambda e: self.settle()),
                          ft.PopupMenuItem("期初餘額範本（CSV）", icon=ft.Icons.DOWNLOAD, on_click=self.tpl),
                          ft.PopupMenuItem("匯入期初餘額", icon=ft.Icons.UPLOAD_FILE, on_click=self.imp),
                          ft.PopupMenuItem("未休特休估列（會計）", icon=ft.Icons.ACCOUNT_BALANCE, on_click=lambda e: self.accrue())])]
        tools.append(ctx.export_button(self.grid, "假期額度"))
        super().__init__([T.page_header(ft.Icons.HOURGLASS_BOTTOM, "特休與補休額度",
                                        "特休依年資自動產生（週年制或曆年制）；請假時先到期先用", "amber", tools),
                          self.grid], spacing=12, expand=True)
        self.load(False)

    def load(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.balances, self.emp.value or "", int(self.year.value), self.dept.value or "") or []
        for r in rows:
            r["hrs"], r["used_h"], r["left_h"] = C.hours(r["hours"]), C.hours(r["used"]), C.hours(r["left"])
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def gen(self):
        y = int(self.year.value)

        def go():
            n = self.ctx.guard(self.ctx.books.grant_annual, y)
            if n is not None:
                self.ctx.toast("已產生 %d 筆特休額度" % (0 if n is True else n))
                self.load()
        sysname = "週年制" if self.ctx.books.company().get("leave_system") != "C" else "曆年制"
        self.ctx.confirm("產生 %d 年特休" % (y - 1911), "依每位員工的年資（%s）產生今年的特休額度；已產生的不會重複。"
                         "可以每月執行一次（週年制：當月滿週年的員工才會新增）。" % sysname, go, yes="產生", danger=False)

    def add(self):
        emp = C.emp_dropdown(self.ctx, self.emp.value or "", width=240, blank=None)
        kind = T.dropdown("種類", [("A", "特休"), ("C", "補休")], "A", width=120, filterable=False)
        hrs = T.field("時數", "8", width=100)
        s = T.date_field("可用起", rocdate.today(), width=160)
        e_ = T.date_field("可用迄", dt.date(rocdate.today().year, 12, 31), width=160)
        memo = T.field("說明", "手動調整", width=300)

        def go(ev):
            if self.ctx.guard(self.ctx.books.add_grant, emp.value, kind.value, s.value, e_.value, hrs.value, memo.value,
                              ok="已新增"):
                self.ctx.close()
                self.load()
        self.ctx.dialog("新增額度", ft.Column([emp, ft.Row([kind, hrs], wrap=True), ft.Row([s, e_], wrap=True), memo],
                                          tight=True, spacing=12),
                        [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("新增", ft.Icons.ADD, go)],
                        icon=ft.Icons.HOURGLASS_BOTTOM, tone="amber")

    def pick(self, r):
        if not self.ctx.books.can("LEV") or r["settled"] or r["source"] == "ot":
            return
        self.ctx.confirm("刪除額度", "刪除 %s %s 的%s額度 %s 小時？" % (r["emp"], r["name"], r["kind_name"], r["hrs"]),
                         lambda: self.ctx.guard(self.ctx.books.delete_grant, r["id"], ok="已刪除") and self.load(),
                         yes="刪除")

    def settle(self):
        b = self.ctx.books
        kind = T.dropdown("種類", [("A", "特休"), ("C", "補休")], "A", width=120, filterable=False)
        as_of = T.date_field("結算基準日（此日以前到期）", dt.date(int(self.year.value), 12, 31), width=240)
        method = T.dropdown("處理方式", [("P", "折發工資（併入薪資）"), ("D", "遞延至次一年度（僅特休，須勞雇協商）")], "P",
                            width=320, filterable=False)
        ym = C.ym_dropdown(None, label="折發的薪資月份")
        emps = [r["code"] for r in b.employees("")]

        def go(ev):
            r = self.ctx.guard(b.settle_grants, emps, as_of.value, method.value, ym.value, kind.value)
            if r is not None:
                self.ctx.close()
                tot = sum((x[2] for x in r), 0) if r is not True else 0
                self.ctx.toast("已結算 %d 筆，折發金額合計 %s" % (0 if r is True else len(r), T.amt(tot)))
                self.load()
        self.ctx.dialog("年度結算", ft.Column([
            ft.Row([kind, as_of], wrap=True), method, ym,
            C.info_box("勞基法第 38 條：特休因年度終結或契約終止而未休完，雇主應發給工資；經勞雇雙方協商可遞延至次一年度，"
                       "遞延後仍未休完就要發給工資。補休（第 32-1 條）期限屆滿未休完，依原加班費率發給工資。"
                       "離職員工（離職日在基準日前）一律折發。折發金額會進入指定月份的薪資（特休未休工資、補休未休折發）。")],
            tight=True, spacing=12), [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()),
                                      T.btn("結算", ft.Icons.FACT_CHECK, go)], icon=ft.Icons.FACT_CHECK, tone="amber",
            width=560)

    async def tpl(self, e):
        from .. import csvio
        await self.ctx.save_generated("期初假期餘額範本.csv", csvio.balances_template)

    async def imp(self, e):
        from .. import csvio
        path = await self.ctx.pick_csv("選擇期初假期餘額（CSV）")
        if path:
            r = self.ctx.guard(csvio.import_balances, self.ctx.books, path)
            if r:
                ok, errs = r
                self.ctx.toast("已匯入 %d 筆%s" % (ok, "；%s" % errs[0] if errs else ""), bool(errs))
                self.load()

    def accrue(self):
        ym = C.ym_dropdown(None, label="估列月份（通常為 12 月）")

        def go(ev):
            r = self.ctx.guard(self.ctx.books.accrue_leave, ym.value)
            if r:
                self.ctx.close()
                self.ctx.toast("已估列 %d 人，金額 %s；請到「會計拋轉」產生傳票" % (r[1], T.amt(r[0])))
        self.ctx.dialog("未休特休估列", ft.Column([ym, C.info_box(
            "依財務會計準則，期末應估列員工已賺得但尚未使用的特休（應付休假給付）。系統以月底剩餘特休時數 × 日薪 ÷ 8 估算，"
            "拋轉時借 薪資支出／貸 應付休假給付，並於次月 1 日自動迴轉。")], tight=True, spacing=12),
            [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("估列", ft.Icons.CHECK, go)],
            icon=ft.Icons.ACCOUNT_BALANCE, tone="amber")
