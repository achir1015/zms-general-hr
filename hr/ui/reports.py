"""報表畫面：薪資總表、薪資科目彙總、部門人事成本、年度扣繳、勞健保勞退明細、補充保費、請假統計、員工名冊、人力統計。"""
import flet as ft

from .. import rocdate
from ..printing import page as print_page, table as print_table, write_and_open
from . import common as C
from . import theme as T


class _Report(ft.Column):
    TITLE, SUB, ICON, TONE = "", "", ft.Icons.TABLE_CHART, "orange"
    COLS = []
    TOTALS = ()
    FILTER = "ym"            # ym、year、date

    def __init__(self, ctx):
        self.ctx = ctx
        if self.FILTER == "ym":
            self.f = C.ym_dropdown(C.ym_now(-1), lambda e: self.load())
        elif self.FILTER == "year":
            self.f = C.year_dropdown(None, lambda e: self.load())
        else:
            self.f = T.date_field("基準日", rocdate.today(), width=160, on_submit=lambda e: self.load())
        self.grid = T.Grid(self.COLS, totals=self.TOTALS)
        super().__init__([T.page_header(self.ICON, self.TITLE, self.SUB, self.TONE,
                                        [self.f, T.btn("查詢", ft.Icons.SEARCH, lambda e: self.load(), kind="outline"),
                                         T.btn("列印", ft.Icons.PRINT, lambda e: self.print(), kind="outline"),
                                         ctx.export_button(self.grid, self.TITLE)]), self.grid], spacing=12, expand=True)
        self.load(False)

    def arg(self):
        if self.FILTER == "year":
            return int(self.f.value)
        return self.f.value

    def load(self, upd=True):
        self.grid.set_rows(self.ctx.guard(self.fetch, self.arg()) or [])
        if upd:
            self.update()

    def print(self):
        rows = [{c[0]: T.show(r.get(c[0]), c[2] if c[2] in ("n", "nz", "d") else "") for c in self.COLS}
                for r in self.grid.data_rows]
        sub = rocdate.ym_show(self.f.value) if self.FILTER == "ym" else str(self.f.value)
        body = print_table([(c[0], c[1], c[2] in ("n", "nz")) for c in self.COLS], rows)
        write_and_open(print_page(self.ctx.books.company().get("name") or "", self.TITLE, sub, body), self.TITLE)


class Register(_Report):
    TITLE, SUB = "薪資總表", "每人每批次的應發、應扣、實發與公司負擔"
    COLS = [("title", "批次", "s", 120), ("emp", "編號", "s", 60), ("name", "姓名", "s", 70), ("dept_name", "部門", "s", 70),
            ("base_salary", "本薪", "nz", 80), ("gross", "應發", "n", 80), ("labor_emp", "勞保", "nz", 60),
            ("nhi_emp", "健保", "nz", 60), ("pension_self", "自提", "nz", 60), ("tax", "所得稅", "nz", 60),
            ("deduct", "應扣", "n", 70), ("net", "實發", "n", 80), ("er_total", "公司負擔", "n", 80),
            ("cost_total", "人事成本", "n", 90)]
    TOTALS = ("gross", "deduct", "net", "er_total", "cost_total")

    def fetch(self, ym):
        return self.ctx.books.payroll_register(ym)


class ByItem(_Report):
    TITLE, SUB = "薪資科目彙總", "各薪資科目依部門合計（對帳、編製傳票用）"
    COLS = [("item", "科目", "s", 90), ("name", "名稱", "s", 140), ("kind_name", "加減", "s", 50), ("dept", "部門", "s", 70),
            ("n", "人數", "s", 50), ("amount", "金額", "n", 100)]

    def fetch(self, ym):
        rows = self.ctx.books.payroll_by_item(ym)
        for r in rows:
            r["kind_name"] = "加" if r["kind"] == "E" else "減"
        return rows


class DeptCost(_Report):
    TITLE, SUB, FILTER = "部門人事成本", "各月份各部門的應發薪資與公司負擔保費", "year"
    COLS = [("ym_show", "月份", "s", 100), ("dept", "部門", "s", 60), ("dept_name", "名稱", "s", 100), ("cost_name", "費用別", "s", 60),
            ("gross", "應發薪資", "n", 100), ("er", "公司負擔", "n", 100), ("total", "合計", "n", 110)]
    TOTALS = ("gross", "er", "total")

    def fetch(self, y):
        return self.ctx.books.dept_cost(y)


class TaxAnnual(_Report):
    TITLE, SUB, FILTER = "年度扣繳彙總", "填報各類所得扣繳暨免扣繳憑單（所得類別 50）用", "year"
    COLS = [("emp", "編號", "s", 60), ("name", "姓名", "s", 70), ("id_no", "身分證號", "s", 100), ("income_code", "類別", "s", 40),
            ("taxable", "給付總額", "n", 100), ("tax", "扣繳稅額", "n", 90), ("net_pay", "給付淨額", "n", 100),
            ("pen_self", "自提勞退", "nz", 80), ("address", "地址", "s", 220)]
    TOTALS = ("taxable", "tax", "pen_self")

    def fetch(self, y):
        return self.ctx.books.tax_annual(y)


class InsDetail(_Report):
    TITLE, SUB, ICON, TONE = "勞健保勞退明細", "與勞保局、健保署繳款單核對；員工自付與公司負擔", ft.Icons.HEALTH_AND_SAFETY, "sky"
    COLS = [("emp", "編號", "s", 60), ("name", "姓名", "s", 70), ("labor_wage", "勞保投保", "n", 80), ("labor_emp", "勞保自付", "nz", 70),
            ("labor_er", "勞保公司", "nz", 70), ("occ_er", "職災", "nz", 60), ("fund_er", "墊償", "nz", 50),
            ("nhi_wage", "健保投保", "n", 80), ("nhi_emp", "健保自付", "nz", 70), ("nhi_er", "健保公司", "nz", 70),
            ("pension_wage", "勞退提繳工資", "n", 90), ("pension_er", "勞退 6%", "nz", 70), ("pension_self", "自提", "nz", 60)]
    TOTALS = ("labor_emp", "labor_er", "occ_er", "fund_er", "nhi_emp", "nhi_er", "pension_er", "pension_self")

    def fetch(self, ym):
        return self.ctx.books.insurance_detail(ym)


class NhiSup(_Report):
    TITLE, SUB, ICON, TONE, FILTER = ("二代健保補充保費", "員工獎金補充保費（逐筆）與投保單位補充保費（每月）",
                                      ft.Icons.ADD_MODERATOR, "sky", "year")
    COLS = [("ym_show", "月份", "s", 100), ("who", "對象", "s", 140), ("base", "計費基礎", "n", 110),
            ("premium", "補充保費", "n", 90), ("note", "說明", "s", 300)]
    TOTALS = ("premium",)

    def fetch(self, y):
        emp, er = self.ctx.books.nhi_sup_report(y)
        rows = [dict(ym_show=r["ym_show"], who="%s %s" % (r["emp"], r["name"]), base=r["bonus_nhi"], premium=r["nhi_sup_emp"],
                     note="員工：獎金年累計超過投保金額 4 倍部分") for r in emp]
        rows += [dict(ym_show=r["ym_show"], who="投保單位", base=r["wage_total"] - r["insured_total"], premium=r["premium"],
                      note="薪資總額 %s － 投保金額總額 %s" % (T.amt(r["wage_total"]), T.amt(r["insured_total"])))
                 for r in er]
        return rows


class LeaveStats(_Report):
    TITLE, SUB, ICON, TONE, FILTER = "請假統計", "每位員工全年各假別時數（核准）", ft.Icons.PIE_CHART, "amber", "year"
    COLS = [("emp", "編號", "s", 60), ("name", "姓名", "s", 70), ("ANNUAL", "特休", "s", 50), ("COMP", "補休", "s", 50),
            ("PERSONAL", "事假", "s", 50), ("FAMILY", "家照", "s", 50), ("SICK", "病假", "s", 50), ("HOSP", "住院", "s", 50),
            ("MENS", "生理", "s", 50), ("MARRIAGE", "婚假", "s", 50), ("FUNERAL", "喪假", "s", 50), ("OCC", "公傷", "s", 50),
            ("MATERNITY", "產假", "s", 50), ("PATERNITY", "陪產", "s", 50), ("PARENTAL", "育嬰", "s", 50),
            ("OFFICIAL", "公假", "s", 50), ("DISASTER", "天災", "s", 50), ("total", "合計", "s", 60)]

    def fetch(self, y):
        rows = self.ctx.books.leave_stats(y)
        for r in rows:
            for c in self.COLS[2:]:
                r[c[0]] = C.hours(r.get(c[0])) if r.get(c[0]) else ""
        return rows


class StaffRoster(_Report):
    TITLE, SUB, ICON, TONE, FILTER = "員工名冊", "勞動檢查常用（勞基法第 7 條）：姓名、性別、出生、身分證、到職、職稱、工資",\
        ft.Icons.PEOPLE_ALT, "violet", "date"
    COLS = [("code", "編號", "s", 60), ("name", "姓名", "s", 70), ("gender_name", "性別", "s", 40), ("birthday", "出生", "d", 90),
            ("id_no", "身分證號", "s", 100), ("hire_date", "到職", "d", 90), ("dept", "部門", "s", 50), ("title", "職稱", "s", 80),
            ("base_salary", "本薪", "nz", 80), ("address", "住址", "s", 220), ("status_name", "狀態", "s", 60)]

    def fetch(self, d):
        return self.ctx.books.roster_of_staff(d)


class Headcount(_Report):
    TITLE, SUB, ICON, TONE, FILTER = "人力統計", "各月月底人數、到職、離職", ft.Icons.GROUPS, "violet", "year"
    COLS = [("ym", "月份", "s", 110), ("head", "月底人數", "s", 80), ("joins", "到職", "s", 60), ("leaves", "離職", "s", 60)]

    def fetch(self, y):
        return self.ctx.books.headcount_report(y)
