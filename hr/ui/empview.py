"""員工資料：清單＋右側分頁表單（基本資料、薪資與保險、固定津貼扣款、調薪紀錄、保費試算）。"""
import datetime as dt

import flet as ft

from .. import rocdate
from ..core import EMP_STATUS
from ..people import EMP_FIELDS
from . import common as C
from . import theme as T

TAB_BASIC = ["code", "name", "id_no", "gender", "birthday", "nationality", "hire_date", "seniority_date", "leave_date",
             "dept", "title", "emp_type", "status", "shift_group", "punch_required", "gps_site", "phone", "mobile", "email",
             "address", "emergency", "memo"]
TAB_PAY = ["base_salary", "hourly_wage", "bank_code", "bank_account", "labor_ins", "employment_ins", "occ_ins", "nhi",
           "pension", "labor_wage", "nhi_wage", "pension_wage", "nhi_dependents", "pension_self", "ins_date", "tax_mode",
           "tax_dependents", "tax_rate"]
FIELD = {k: (t, typ) for k, t, typ in EMP_FIELDS}
DEFAULTS = dict(gender="M", nationality="T", emp_type="M", status="A", punch_required=True, labor_ins=True,
                employment_ins=True, occ_ins=True, nhi=True, pension=True, tax_mode="T", tax_rate="5")


class Employees(ft.Row):
    def __init__(self, ctx, code=None):
        self.ctx = ctx
        b = ctx.books
        self.editable = b.can("EMP", 2)
        self.search = T.field("搜尋", "", width=180, prefix_icon=ft.Icons.SEARCH, on_submit=lambda e: self.reload())
        self.dept = C.dept_dropdown(ctx, "", lambda e: self.reload(), width=150)
        self.status = T.dropdown("狀態", [("work", "在職＋留停"), ("A", "在職"), ("L", "留職停薪"), ("Q", "離職"), ("", "全部")],
                                 "work", width=140, on_select=lambda e: self.reload(), filterable=False)
        self.grid = T.Grid([("code", "編號", "s", 80), ("name", "姓名", "s", 90), ("dept_name", "部門", "s", 90),
                            ("title", "職稱", "s", 90), ("status_name", "狀態", "s", 70), ("hire_date", "到職日", "d", 90),
                            ("mobile", "手機", "s", 110)], on_pick=lambda r: self.edit(r["code"]))
        tools = [self.search, self.dept, self.status, ctx.export_button(self.grid, "員工資料")]
        if self.editable:
            tools.append(ft.PopupMenuButton(
                content=T.btn("更多", ft.Icons.MORE_HORIZ, None, kind="outline"),
                items=[ft.PopupMenuItem("下載名冊範本（CSV）", icon=ft.Icons.DOWNLOAD, on_click=self.template),
                       ft.PopupMenuItem("匯入員工名冊", icon=ft.Icons.UPLOAD_FILE, on_click=self.do_import),
                       ft.PopupMenuItem("建立員工帳號（打卡、請假用）", icon=ft.Icons.PERSON_ADD,
                                        on_click=lambda e: self.make_accounts())]))
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        left = ft.Column([T.page_header(ft.Icons.BADGE, "員工資料", "基本資料、到離職、薪資、保險與扣繳設定", "violet", tools),
                          self.grid], expand=True, spacing=12)
        super().__init__([left, T.card(self.form, width=560, padding=18)], expand=True, spacing=14, data="split",
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.reload(False)
        self.edit(code, refresh=False)

    def reload(self, upd=True):
        rows = self.ctx.books.employees(self.status.value or "", self.dept.value or "", (self.search.value or "").strip())
        self.grid.set_rows(rows)
        if upd:
            self.update()

    # ---------------------------------------------------------------- 表單
    def edit(self, code, refresh=True):
        b = self.ctx.books
        self.code = code
        self.e = dict(b.employee_view(code)) if code else dict(DEFAULTS)
        self.inputs = {}
        for k in TAB_BASIC + TAB_PAY:
            self.inputs[k] = self._input(k, self.e.get(k))
        self.inputs["code"].read_only = bool(code)
        self.salary_eff = T.date_field("調薪生效日", rocdate.today(), width=170)
        self.salary_reason = T.field("調薪原因", "", width=200, hint_text="試用期滿、年度調薪…")
        self.tabs = C.PillTabs(["基本資料", "薪資與保險", "固定津貼與扣款", "調薪紀錄", "保費試算"], self.show_tab)
        self.tab_body = ft.Column(spacing=10)
        acts = []
        if self.editable:
            acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save()),
                    T.btn("新增", ft.Icons.PERSON_ADD, lambda e: self.edit(None), kind="outline")]
            if code:
                acts += [T.btn("離職", ft.Icons.EXIT_TO_APP, lambda e: self.resign(), kind="outline"),
                         T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger")]
        title = "%s %s" % (self.e["code"], self.e["name"]) if code else "新增員工"
        sub = ""
        if code:
            from ..laws import service_text
            sen = self.e.get("seniority_date") or self.e.get("hire_date")
            sub = "%s　年資 %s" % (EMP_STATUS.get(self.e["status"], ""), service_text(sen, dt.date.today()) if sen else "")
        self.form.controls = [ft.Row([T.icon_tile(ft.Icons.BADGE, "violet", 40),
                                      ft.Column([ft.Text(title, size=17, weight=ft.FontWeight.W_700), T.muted(sub, 12)],
                                                spacing=0, expand=True)], spacing=12),
                              self.tabs, self.tab_body, ft.Row(acts, wrap=True, spacing=8)]
        self.show_tab(0, False)
        if refresh:
            self.update()

    def _input(self, k, v):
        b = self.ctx.books
        title, typ = FIELD[k]
        if typ == "b":
            c = T.switch(title, v)
        elif typ.startswith("sel:"):
            opts = [tuple(x.split("=")) for x in typ[4:].split(",")]
            c = T.dropdown(title, opts, v if v not in (None, "") else opts[0][0], filterable=False)
        elif typ in ("dept", "shift", "site"):
            c = T.dropdown(title, b.options(typ), "" if v in (None, 0) else str(v), blank="（無）")
        elif typ == "d":
            c = T.field(title, rocdate.show(v) if v else "", hint_text="115/11/13", prefix_icon=ft.Icons.CALENDAR_MONTH)
        elif typ in ("n", "i"):
            c = T.field(title, "" if v is None else (T.amt(v) if typ == "n" else str(v)), text_align=ft.TextAlign.RIGHT)
        else:
            c = T.field(title, v or "", multiline=k in ("memo", "address"))
        c.disabled = not self.editable
        c.expand = True
        return c

    def _rows(self, keys):
        out, pair, switches = [], [], []
        for k in keys:
            c = self.inputs[k]
            if FIELD[k][1] == "b":
                c.expand = False
                switches.append(ft.Container(c, width=160))
                continue
            if k in ("memo", "address"):
                if pair:
                    out.append(ft.Row(pair, spacing=10))
                    pair = []
                out.append(ft.Row([c]))
                continue
            pair.append(c)
            if len(pair) == 2:
                out.append(ft.Row(pair, spacing=10))
                pair = []
        if pair:
            out.append(ft.Row(pair, spacing=10))
        if switches:
            out.append(ft.Row(switches, spacing=6, wrap=True, run_spacing=4))
        return out

    def show_tab(self, i, refresh=True):
        b = self.ctx.books
        if i == 0:
            self.tab_body.controls = self._rows(TAB_BASIC)
        elif i == 1:
            if self.code and not b.see_salary:
                self.tab_body.controls = [C.info_box("您沒有「薪資個資」權限，看不到薪資與投保資料。", "amber")]
            else:
                ctl = self._rows(TAB_PAY)
                ctl.insert(0, C.info_box("投保薪資、投保金額、月提繳工資填 0 時，依「本薪＋經常性津貼」自動對照官方分級表。"
                                         "65 歲以上、外國籍不加就業保險；勞退自提可自當年度薪資所得扣除。"))
                if self.code:
                    ctl.append(ft.Row([self.salary_eff, self.salary_reason], wrap=True, spacing=10))
                self.tab_body.controls = ctl
        elif i == 2:
            self.tab_body.controls = self._items_tab()
        elif i == 3:
            if not self.code:
                self.tab_body.controls = [T.muted("新增員工儲存後才有調薪紀錄")]
            else:
                g = T.Grid([("eff_date", "生效日", "d", 90), ("base_salary", "本薪", "n", 90), ("hourly_wage", "時薪", "nz", 70),
                            ("reason", "原因", "s", 120), ("created_by", "輸入者", "s", 70)], height=320)
                g.set_rows(self.ctx.guard(b.salary_history, self.code) or [])
                self.tab_body.controls = [g]
        elif i == 4:
            self.tab_body.controls = self._premium_tab()
        if refresh:
            self.update()

    def _items_tab(self):
        b = self.ctx.books
        if not self.code:
            return [T.muted("請先儲存員工基本資料")]
        if not b.see_salary:
            return [C.info_box("您沒有「薪資個資」權限。", "amber")]
        have = {r["item"]: r["amount"] for r in b.emp_items(self.code)}
        items = b.db.rows("SELECT * FROM pay_items WHERE active=1 AND method='F' ORDER BY kind DESC, sort")
        self.item_inputs = {}
        rows = [C.info_box("每月固定發給的津貼（例如職務加給、伙食津貼、全勤獎金）與固定扣款（例如職工福利金）。"
                           "經常性津貼會計入加班費與投保薪資的基數。")]
        for it in items:
            f = T.money_field("%s（%s）" % (it["name"], "加" if it["kind"] == "E" else "減"), have.get(it["code"], ""),
                              width=200)
            f.disabled = not self.editable
            self.item_inputs[it["code"]] = f
            rows.append(ft.Row([f, T.muted(it["memo"], 11)], spacing=10))
        if self.editable:
            rows.append(T.btn("儲存固定項目", ft.Icons.SAVE, lambda e: self.save_items(), kind="accent"))
        return rows

    def save_items(self):
        vals = {k: (c.value or "0").replace(",", "") for k, c in self.item_inputs.items()}
        if self.ctx.guard(self.ctx.books.save_emp_items, self.code, vals, ok="固定項目已儲存"):
            self.show_tab(2)

    def _premium_tab(self):
        b = self.ctx.books
        if not self.code:
            return [T.muted("請先儲存員工資料")]
        if not b.see_salary:
            return [C.info_box("您沒有「薪資個資」權限。", "amber")]
        pv = self.ctx.guard(b.premium_preview, self.code)
        if not pv:
            return []
        rows = [("經常性薪資（本薪＋經常性津貼）", pv["basis"], ""), ("勞保投保薪資", pv["labor_wage"], ""),
                ("職災投保薪資", pv["occ_wage"], ""), ("健保投保金額", pv["nhi_wage"], ""),
                ("勞退月提繳工資", pv["pension_wage"], "")]
        cost = [("勞保（含就保）", pv["labor_emp"], pv["labor_er"]), ("職災保險", 0, pv["occ_er"]),
                ("工資墊償基金", 0, pv["fund_er"]), ("健保（含眷屬）", pv["nhi_emp"], pv["nhi_er"]),
                ("勞退", pv["pension_self"], pv["pension_er"])]
        g = T.Grid([("k", "項目", "s", 200), ("emp", "員工自付", "n", 100), ("er", "公司負擔", "n", 100)], height=250,
                   totals=("emp", "er"))
        g.set_rows([dict(k=a, emp=x, er=y) for a, x, y in cost])
        return [ft.Column([ft.Row([T.muted(a, 13), ft.Container(expand=True), ft.Text(T.amt(v), size=14,
                                                                                     weight=ft.FontWeight.W_700)])
                           for a, v, _ in rows], spacing=4), g,
                T.muted("試算以本月整月投保計算；實際依每月在職、投保日數於薪資計算時產生。", 11)]

    def collect(self):
        row = {}
        for k, c in self.inputs.items():
            typ = FIELD[k][1]
            v = c.value
            if typ in ("n", "i"):
                v = (v or "0").replace(",", "")
            row[k] = v
        row["salary_eff"] = self.salary_eff.value
        row["salary_reason"] = self.salary_reason.value
        return row

    def save(self):
        b = self.ctx.books
        row = self.collect()
        if self.code and not b.see_salary:
            for k in TAB_PAY:
                row.pop(k, None)
        code = self.ctx.guard(b.save_employee, row, self.code is None, ok="員工資料已儲存")
        if code:
            self.reload(False)
            self.edit(code)

    def resign(self):
        d = T.date_field("最後在職日（離職日）", rocdate.today(), width=220)
        why = T.field("離職原因", "", width=320)

        def go(e):
            if self.ctx.guard(self.ctx.books.resign, self.code, d.value, why.value, ok="已登錄離職"):
                self.ctx.close()
                self.reload(False)
                self.edit(self.code)
        self.ctx.dialog("登錄離職", ft.Column([d, why, C.info_box(
            "離職後請：①到「特休與補休額度」結算未休特休與補休（依法折發工資）②計算最後一個月薪資（在職日數自動比例）"
            "③辦理勞健保退保與勞退停繳（系統依離職日計算保費）。")], tight=True, spacing=12),
            [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("確定", ft.Icons.CHECK, go)],
            icon=ft.Icons.EXIT_TO_APP, tone="rose")

    def delete(self):
        def go():
            if self.ctx.guard(self.ctx.books.delete_employee, self.code, ok="已刪除"):
                self.reload(False)
                self.edit(None)
        self.ctx.confirm("刪除員工", "確定要刪除 %s %s 嗎？（已有出勤或薪資紀錄的員工不能刪除，請登錄離職）"
                         % (self.e["code"], self.e["name"]), go, yes="刪除")

    async def template(self, e):
        from .. import csvio
        await self.ctx.save_generated("員工名冊範本.csv", lambda p: csvio.master_template("employees", p))

    async def do_import(self, e):
        from .. import csvio
        path = await self.ctx.pick_csv("選擇員工名冊（CSV）")
        if not path:
            return
        r = self.ctx.guard(csvio.import_masters, self.ctx.books, "employees", path)
        if not r:
            return
        ok, errs = r
        self.reload()
        msg = ft.Column([ft.Text("成功匯入（新增或更新）%d 筆。" % ok, size=15, color=T.SUCCESS, weight=ft.FontWeight.W_600)] +
                        ([ft.Text("以下 %d 列未匯入：" % len(errs), color=T.DANGER)] +
                         [ft.Text(x, size=12, selectable=True) for x in errs[:30]] if errs else []),
                        tight=True, scroll=ft.ScrollMode.AUTO, height=None if len(errs) < 10 else 360)
        self.ctx.dialog("匯入結果", msg, [T.btn("確定", on_click=lambda e: self.ctx.close())], icon=ft.Icons.UPLOAD_FILE,
                        tone="green" if not errs else "amber", width=520)

    def make_accounts(self):
        def go():
            r = self.ctx.guard(self.ctx.books.create_employee_accounts)
            if r is None:
                return
            if not r or r is True:
                self.ctx.toast("所有在職員工都已有帳號")
                return
            g = T.Grid([("uid", "帳號", "s", 100), ("name", "姓名", "s", 100), ("pw", "預設密碼", "s", 120)], height=360)
            g.set_rows([dict(uid=a, name=n, pw=p) for a, n, p in r])
            self.ctx.dialog("已建立 %d 個員工帳號" % len(r), ft.Column([
                C.info_box("請把帳號與預設密碼交給員工，第一次登入後請自行變更密碼。可按「匯出 Excel」留存。", "amber"),
                g, self.ctx.export_button(g, "員工帳號")], tight=True, spacing=10),
                [T.btn("確定", on_click=lambda e: self.ctx.close())], icon=ft.Icons.PERSON_ADD, tone="green", width=520)
        self.ctx.confirm("建立員工帳號", "替還沒有帳號的在職員工建立「員工」帳號（帳號＝員工編號；預設密碼＝身分證後 4 碼＋生日月日）。"
                         "員工可以用這個帳號在手機 GPS 打卡、請假、看自己的薪資單。", go, yes="建立", danger=False)
