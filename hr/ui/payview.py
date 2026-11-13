"""薪資畫面：每月變動輸入、薪資計算與發放、獎金與年終、法令參數與投保分級表。"""
import datetime as dt

import flet as ft

from .. import rocdate
from ..payroll import RUN_KIND
from ..seed import GRADE_NAMES
from . import common as C
from . import theme as T


class Inputs(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        self.ym = C.ym_dropdown(None, lambda e: self.load())
        self.kind = T.dropdown("批次", list(RUN_KIND.items()), "M", width=120, filterable=False,
                               on_select=lambda e: self.load())
        self.grid = T.Grid([("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("item", "科目", "s", 80),
                            ("item_name", "名稱", "s", 120), ("amount", "金額", "n", 90), ("note", "說明", "s", 260),
                            ("source", "來源", "s", 70)], on_pick=self.pick, totals=("amount",))
        tools = [self.ym, self.kind]
        if b.can("PAY"):
            tools += [T.btn("新增", ft.Icons.ADD, lambda e: self.add()),
                      ft.PopupMenuButton(content=T.btn("Excel", ft.Icons.TABLE_VIEW, None, kind="outline"), items=[
                          ft.PopupMenuItem("下載範本（CSV）", icon=ft.Icons.DOWNLOAD, on_click=self.tpl),
                          ft.PopupMenuItem("匯入", icon=ft.Icons.UPLOAD_FILE, on_click=self.imp)])]
        tools.append(ctx.export_button(self.grid, "變動輸入"))
        super().__init__([T.page_header(ft.Icons.EDIT_NOTE, "每月變動輸入", "獎金、夜班津貼、借支扣回、其他加扣項；"
                                        "特休與補休折發、獎金規則產生的金額也會出現在這裡", "green", tools),
                          self.grid], spacing=12, expand=True)
        self.load(False)

    def load(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.pay_inputs, self.ym.value, self.kind.value) or []
        src = {"manual": "手動", "bonus": "獎金規則", "leave": "假期結算", "occ": "職災"}
        for r in rows:
            r["source"] = src.get(r["source"], r["source"])
            if r["kind"] == "D":
                r["amount"] = -r["amount"]
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def add(self):
        b = self.ctx.books
        emp = C.emp_dropdown(self.ctx, "", width=240, blank=None)
        opts = b.options("item_input") + [("TAX", "TAX 所得稅（手動指定本次扣繳金額）")]
        item = T.dropdown("薪資科目", opts, "BONUS", width=320)
        amt = T.money_field("金額", "", width=160)
        note = T.field("說明", "", width=320)

        def go(e):
            if self.ctx.guard(b.add_pay_input, self.ym.value, self.kind.value, emp.value, item.value,
                              (amt.value or "0").replace(",", ""), note.value, ok="已新增"):
                self.ctx.close()
                self.load()
        self.ctx.dialog("新增變動輸入（%s %s）" % (rocdate.ym_show(self.ym.value), RUN_KIND[self.kind.value]),
                        ft.Column([emp, item, amt, note, T.muted("應扣科目也輸入正數，系統會自動扣除。", 12)],
                                  tight=True, spacing=12),
                        [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("新增", ft.Icons.ADD, go)],
                        icon=ft.Icons.EDIT_NOTE, tone="green")

    def pick(self, r):
        if not self.ctx.books.can("PAY"):
            return
        self.ctx.confirm("刪除", "刪除 %s %s 的 %s %s？" % (r["emp"], r["name"], r["item_name"], T.amt(abs(r["amount"]))),
                         lambda: self.ctx.guard(self.ctx.books.delete_pay_input, r["id"], ok="已刪除") and self.load(),
                         yes="刪除")

    async def tpl(self, e):
        from .. import csvio
        await self.ctx.save_generated("變動輸入範本.csv", csvio.inputs_template)

    async def imp(self, e):
        from .. import csvio
        path = await self.ctx.pick_csv("選擇變動輸入（CSV）")
        if path:
            r = self.ctx.guard(csvio.import_inputs, self.ctx.books, self.ym.value, self.kind.value, path)
            if r:
                ok, errs = r
                self.ctx.toast("已匯入 %d 筆%s" % (ok, "；%s" % errs[0] if errs else ""), bool(errs))
                self.load()


class Payroll(ft.Column):
    def __init__(self, ctx, rid=None):
        self.ctx = ctx
        b = ctx.books
        self.edit_ok = b.can("PAY")
        self.year = C.year_dropdown(None, lambda e: self.load())
        self.runs = T.Grid([("ym_show", "月份", "s", 80), ("title", "名稱", "s", 120),
                            ("status_name", "狀態", "s", 50), ("net", "實發", "n", 70)], on_pick=lambda r: self.open(r["id"]))
        tools = [self.year]
        if self.edit_ok:
            tools.append(T.btn("新增薪資批次", ft.Icons.ADD, lambda e: self.new_run()))
        self.detail = ft.Column(spacing=12, expand=True)
        body = ft.Row([ft.Container(self.runs, width=430), ft.Container(self.detail, expand=True)], expand=True,
                      spacing=14, data="split", vertical_alignment=ft.CrossAxisAlignment.START)
        super().__init__([ft.Column([T.page_header(ft.Icons.CALCULATE, "薪資計算與發放",
                                                   "計算 → 檢查 → 確認 → 發放 → 關帳 → 拋轉會計", "green", tools), body],
                                    expand=True, spacing=12)], expand=True)
        self.rid = rid
        self.load(False)
        if rid:
            self.open(rid, False)
        else:
            self.detail.controls = [T.card(T.empty_state(ft.Icons.CALCULATE, "選擇左邊的薪資批次，或按「新增薪資批次」",
                                                         "每月一個月薪批次；年終、三節等獎金另開獎金批次"))]

    def load(self, upd=True):
        self.runs.set_rows(self.ctx.guard(self.ctx.books.payroll_runs, int(self.year.value)) or [])
        if upd:
            self.update()

    def new_run(self):
        ym = C.ym_dropdown(C.ym_now(-1) if dt.date.today().day < 20 else C.ym_now())
        kind = T.dropdown("種類", list(RUN_KIND.items()), "M", width=120, filterable=False)
        title = T.field("名稱（空白自動命名）", "", width=300, hint_text="例：115 年年終獎金")
        pay = T.field("發放日（空白＝公司設定的發薪日）", "", width=300, hint_text="115/12/05")

        def go(e):
            rid = self.ctx.guard(self.ctx.books.create_run, ym.value, kind.value, title.value, pay.value or None)
            if rid:
                self.ctx.close()
                self.load(False)
                self.open(rid)
        self.ctx.dialog("新增薪資批次", ft.Column([ft.Row([ym, kind], wrap=True), title, pay, C.info_box(
            "月薪批次每月一個，依出勤、請假、加班與每月變動輸入計算；獎金批次只計算「每月變動輸入」中批次＝獎金的項目"
            "（年終、三節獎金可由「獎金與年終」依規則產生）。")], tight=True, spacing=12),
            [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("建立", ft.Icons.ADD, go)],
            icon=ft.Icons.CALCULATE, tone="green")

    def open(self, rid, upd=True):
        b = self.ctx.books
        self.rid = rid
        r = self.ctx.guard(b.payroll_run, rid)
        if not r:
            return
        slips = b.payslips(rid) if b.see_salary else []
        g = T.Grid([("emp", "編號", "s", 60), ("name", "姓名", "s", 70), ("dept_name", "部門", "s", 70),
                    ("gross", "應發", "n", 80), ("deduct", "應扣", "n", 70), ("net", "實發", "n", 80),
                    ("ins_emp", "勞健保", "n", 70), ("pension_self", "自提", "nz", 60), ("tax", "所得稅", "nz", 60),
                    ("er_total", "公司負擔", "n", 80)], on_pick=self.slip, totals=("gross", "net", "er_total"))
        g.set_rows(slips)
        st = r["status"]
        acts = []
        if self.edit_ok:
            if st == 0:
                acts += [T.btn("計算薪資", ft.Icons.CALCULATE, lambda e: self.calc()),
                         T.btn("確認", ft.Icons.VERIFIED, lambda e: self.do(b.confirm_run, "已確認"), kind="accent"),
                         T.btn("刪除批次", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger")]
            elif st == 1:
                acts += [T.btn("標示已發放", ft.Icons.PAID, lambda e: self.do(b.mark_paid, "已標示發放")),
                         T.btn("取消確認", ft.Icons.UNDO, lambda e: self.do(b.unconfirm_run, "已取消確認"), kind="outline")]
            else:
                acts.append(T.btn("取消發放標示", ft.Icons.UNDO, lambda e: self.do(lambda i: b.mark_paid(i, False),
                                                                             "已取消"), kind="outline"))
            if st >= 1 and not self.ctx.app.mobile:          # 轉帳檔在電腦上產生
                acts.append(T.btn("銀行轉帳檔", ft.Icons.ACCOUNT_BALANCE, self.bank, kind="outline"))
                if r["kind"] == "M":
                    acts.append(T.btn("關帳本月", ft.Icons.LOCK, lambda e: self.close_month(r["ym"]), kind="outline"))
        if slips:
            acts.append(T.btn("列印薪資單", ft.Icons.PRINT, lambda e: self.print_all(slips), kind="outline"))
            acts.append(self.ctx.export_button(g, "薪資_%s" % r["ym"]))
        info = ft.Row([T.chip(r["status_name"], {0: "amber", 1: "sky", 2: "green"}[st]),
                       T.chip(RUN_KIND[r["kind"]], "violet"), T.muted("發放日 %s" % rocdate.show(r["pay_date"])),
                       T.muted("已拋轉會計" if r["gl_batch_id"] else "", 12)], spacing=10, wrap=True)
        kp = ft.Row([T.chip("%d 人" % r["emp_count"], "violet", ft.Icons.GROUPS, 14),
                     T.chip("應發 %s" % T.amt(r["gross"]), "green", ft.Icons.PAYMENTS, 14),
                     T.chip("實發 %s" % T.amt(r["net"]), "teal", ft.Icons.ACCOUNT_BALANCE_WALLET, 14),
                     T.chip("公司負擔保費 %s" % T.amt(r["employer_cost"]), "sky", ft.Icons.HEALTH_AND_SAFETY, 14)],
                    wrap=True, spacing=8, run_spacing=6)
        self.detail.controls = [T.card(ft.Column([ft.Text(r["title"], size=19, weight=ft.FontWeight.W_800), info, kp,
                                                  ft.Row(acts, wrap=True, spacing=8, run_spacing=8)], spacing=10)),
                                g if slips or b.see_salary else C.info_box("您沒有薪資個資權限", "amber")]
        if upd:
            self.update()

    def calc(self):
        r = self.ctx.guard(self.ctx.books.calculate, self.rid)
        if r:
            msg = "已計算 %d 人：應發 %s、實發 %s" % (r["count"], T.amt(r["gross"]), T.amt(r["net"]))
            if r["warnings"]:
                self.ctx.dialog("計算完成（請檢查）", ft.Column([ft.Text(msg)] + [ft.Text("⚠ " + w, color=T.DANGER)
                                                                            for w in r["warnings"]], tight=True),
                                [T.btn("確定", on_click=lambda e: self.ctx.close())], icon=ft.Icons.WARNING_AMBER,
                                tone="amber")
            else:
                self.ctx.toast(msg)
            self.load(False)
            self.open(self.rid)

    def do(self, fn, ok):
        if self.ctx.guard(fn, self.rid, ok=ok):
            self.load(False)
            self.open(self.rid)

    def delete(self):
        def go():
            if self.ctx.guard(self.ctx.books.delete_run, self.rid, ok="已刪除"):
                self.rid = None
                self.load(False)
                self.detail.controls = []
                self.update()
        self.ctx.confirm("刪除薪資批次", "確定要刪除這個試算中的批次嗎？", go, yes="刪除")

    def close_month(self, ym):
        self.ctx.confirm("關帳 %s" % rocdate.ym_show(ym), "關帳後，這個月的排班、打卡、請假、加班都不能再修改（系統管理員可取消最近一次關帳）。",
                         lambda: self.ctx.guard(self.ctx.books.close_month, ym, ok="已關帳"), yes="關帳", danger=False)

    def slip(self, r):
        b = self.ctx.books
        s = self.ctx.guard(b.payslip, r["id"])
        if not s:
            return
        g = T.Grid([("name", "項目", "s", 150), ("amt", "金額", "n", 90), ("note", "說明", "s", 300)], height=380)
        g.set_rows([dict(name=("＋ " if x["kind"] == "E" else "－ ") + x["name"], amt=x["amount"], note=x["note"])
                    for x in s["lines"]])
        er = s["labor_er"] + s["occ_er"] + s["fund_er"] + s["nhi_er"] + s["pension_er"]
        self.ctx.dialog("%s %s 薪資單" % (s["emp"], s["name"]), ft.Column([
            ft.Row([T.chip("應發 %s" % T.amt(s["gross"]), "green"), T.chip("應扣 %s" % T.amt(s["deduct"]), "rose"),
                    T.chip("實發 %s" % T.amt(s["net"]), "blue")], wrap=True, spacing=8),
            g, T.muted("投保：勞保 %s／健保 %s／勞退 %s；公司負擔 %s（勞保 %s、職災 %s、墊償 %s、健保 %s、勞退 %s）" % (
                T.amt(s["labor_wage"]), T.amt(s["nhi_wage"]), T.amt(s["pension_wage"]), T.amt(er), T.amt(s["labor_er"]),
                T.amt(s["occ_er"]), T.amt(s["fund_er"]), T.amt(s["nhi_er"]), T.amt(s["pension_er"])), 12),
            *[T.muted("・" + n, 12) for n in s["notes"]]], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
            [T.btn("列印", ft.Icons.PRINT, lambda e: self.print_all([r]), kind="outline"),
             T.btn("關閉", on_click=lambda e: self.ctx.close())], icon=ft.Icons.RECEIPT_LONG, tone="green", width=680)

    def print_all(self, slips):
        from ..printing import payslips_page, write_and_open
        b = self.ctx.books
        data = [b.payslip(s["id"]) for s in slips]
        write_and_open(payslips_page(b.company(), data), "薪資單")

    async def bank(self, e):
        b = self.ctx.books
        r = b.payroll_run(self.rid)
        res = {}

        def w(p):
            res.update(b.bank_file(self.rid, p))
        await self.ctx.save_generated("薪資轉帳_%s.csv" % r["ym"], w)
        if res:
            self.ctx.toast("轉帳 %d 人，共 %s%s" % (res["count"], T.amt(res["total"]),
                                                 "；缺銀行帳號：%s" % "、".join(res["missing"][:5]) if res["missing"] else ""),
                           bool(res["missing"]))


class Bonus(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        rules = b.bonus_rule_list()
        self.rule = T.dropdown("獎金規則", [(str(r["id"]), r["name"]) for r in rules], str(rules[0]["id"]) if rules else None,
                               width=220, filterable=False, on_select=lambda e: self.preview())
        self.as_of = T.date_field("計算基準日", dt.date(dt.date.today().year, 12, 31), width=170)
        self.ym = C.ym_dropdown(None, label="發放月份")
        self.kind = T.dropdown("併入批次", list(RUN_KIND.items()), "B", width=120, filterable=False)
        self.grid = T.Grid([("emp", "編號", "s", 70), ("name", "姓名", "s", 80), ("dept", "部門", "s", 60),
                            ("basis", "基數", "n", 90), ("ratio_t", "比例", "s", 60), ("amount", "金額", "n", 90),
                            ("note", "計算", "s", 320)], totals=("amount",))
        tools = [self.rule, self.as_of, T.btn("試算", ft.Icons.CALCULATE, lambda e: self.preview(), kind="outline"),
                 self.ym, self.kind]
        if b.can("BON"):
            tools.append(T.btn("產生", ft.Icons.CARD_GIFTCARD, lambda e: self.gen()))
        hint = C.info_box("先到「津貼獎金規則」設定：例如年終獎金 1.5 個月（本薪＋經常性津貼）、依在職月數比例；三節獎金固定 3,000 元。"
                          "產生後的金額寫入「每月變動輸入」，再到「薪資計算與發放」建立獎金批次（或併入月薪）計算扣繳與補充保費。"
                          "獎金屬非經常性給與：當年累計超過健保投保金額 4 倍的部分扣 2.11% 補充保費；單次達 90,501 元扣繳 5% 所得稅。")
        super().__init__([T.page_header(ft.Icons.CARD_GIFTCARD, "獎金與年終", "依規則（月數或固定金額）計算津貼、獎金與年終獎金",
                                        "green", tools), hint, self.grid] if rules else
                         [T.page_header(ft.Icons.CARD_GIFTCARD, "獎金與年終", "", "green"), hint,
                          T.btn("新增獎金規則", ft.Icons.ADD, lambda e: ctx.app.go("bonus_rules"))],
                         spacing=12, expand=True)
        if rules:
            self.preview(False)

    def preview(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.bonus_preview, int(self.rule.value), self.as_of.value) or []
        for r in rows:
            r["ratio_t"] = "%.2f" % r["ratio"]
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def gen(self):
        r = self.ctx.guard(self.ctx.books.generate_bonus, int(self.rule.value), self.as_of.value, self.ym.value,
                           self.kind.value)
        if r:
            self.ctx.toast("已產生 %d 人，共 %s（寫入 %s %s 的變動輸入）" % (r[0], T.amt(r[1]), rocdate.ym_show(self.ym.value),
                                                                RUN_KIND[self.kind.value]))


class LawParams(ft.Row):
    """法令參數（依生效日）與投保分級表（勞保、職災、健保、勞退）。"""

    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        self.edit_ok = b.can("INS")
        self.pgrid = T.Grid([("name", "參數", "s", 200), ("v", "值", "s", 120), ("eff_date", "生效日", "d", 90),
                             ("note", "說明", "s", 240)], on_pick=self.edit_param)
        self.kind = T.dropdown("分級表", list(GRADE_NAMES.items()), "LI", width=200, filterable=False,
                               on_select=lambda e: self.load_grades())
        self.gtext = T.field("各級金額（逗號或換行分隔）", "", multiline=True, min_lines=10, max_lines=16)
        self.geff = T.date_field("新的生效日", dt.date(dt.date.today().year + 1, 1, 1), width=170)
        self.ginfo = T.muted("", 12)
        left = ft.Column([T.page_header(ft.Icons.GAVEL, "法令參數與分級表",
                                        "依勞動部、衛福部、財政部公告；每年調整時新增一組生效日即可，舊月份仍依舊參數計算",
                                        "sky"),
                          C.info_box("目前內建 115 年 1 月 1 日起適用的數字：基本工資 29,500、勞保 11 級（29,500～45,800）、"
                                     "職災 21 級（到 72,800）、健保 58 級（到 313,000）、勞退 62 級（1,500～150,000），"
                                     "勞保 12.5%（含就保 1%）、健保 5.17%、平均眷口數 0.56、補充保費 2.11%。"),
                          self.pgrid], expand=True, spacing=12)
        right = T.card(ft.Column([ft.Row([T.icon_tile(ft.Icons.STACKED_BAR_CHART, "sky", 36),
                                          ft.Text("投保分級表", size=16, weight=ft.FontWeight.W_700)], spacing=10),
                                  self.kind, self.ginfo, self.gtext,
                                  ft.Row([self.geff, T.btn("以新生效日儲存", ft.Icons.SAVE, lambda e: self.save_grades())],
                                         wrap=True) if self.edit_ok else ft.Container()],
                                 spacing=10, scroll=ft.ScrollMode.AUTO), width=420)
        super().__init__([left, right], expand=True, spacing=14, data="split", vertical_alignment=ft.CrossAxisAlignment.START)
        self.load(False)
        self.load_grades(False)

    def load(self, upd=True):
        self.pgrid.set_rows(self.ctx.books.law_table())
        if upd:
            self.update()

    def load_grades(self, upd=True):
        b = self.ctx.books
        g, dates = b.grade_table(self.kind.value)
        self.gtext.value = "\n".join("{:,}".format(int(x)) for x in g)
        self.ginfo.value = "共 %d 級；生效日：%s" % (len(g), "、".join(rocdate.show(d) for d in dates))
        if upd:
            self.update()

    def edit_param(self, r):
        if not self.edit_ok:
            return
        v = T.field(r["name"], r["v"], width=360)
        eff = T.date_field("生效日", r["eff_date"], width=170)

        def go(e):
            if self.ctx.guard(self.ctx.books.save_law, r["k"], eff.value, v.value, ok="已儲存"):
                self.ctx.close()
                self.load()
        self.ctx.dialog("修改法令參數", ft.Column([v, eff, T.muted(r["note"] or "", 12), C.info_box(
            "改成新的生效日會新增一筆（保留舊值給以前月份使用）；生效日相同則覆蓋。")], tight=True, spacing=12),
            [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("儲存", ft.Icons.SAVE, go)],
            icon=ft.Icons.GAVEL, tone="sky")

    def save_grades(self):
        if self.ctx.guard(self.ctx.books.save_grades, self.kind.value, self.geff.value, self.gtext.value, ok="分級表已儲存"):
            self.load_grades()
