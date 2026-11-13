"""員工資料：基本資料、到離職、調薪紀錄、固定薪資項目（津貼、固定扣款）。"""
import datetime as dt
import json
from decimal import Decimal

from .core import D0, EMP_STATUS, BizError, date, dec, opt_date, yuan

# 員工欄位：(欄位, 標題, 型別)；型別同 MASTERS（s、n、i、b、d、dept、shift、site、sel:）
EMP_FIELDS = [
    ("code", "員工編號", "s"), ("name", "姓名", "s"), ("id_no", "身分證號", "s"),
    ("gender", "性別", "sel:M=男,F=女"), ("birthday", "生日", "d"),
    ("nationality", "國籍", "sel:T=本國,F=外國籍,P=外籍（永久居留／本國人配偶）"),
    ("hire_date", "到職日", "d"), ("seniority_date", "年資起算日", "d"), ("leave_date", "離職日", "d"),
    ("dept", "部門", "dept"), ("title", "職稱", "s"), ("emp_type", "計薪方式", "sel:M=月薪,H=時薪,P=部分工時（月薪）"),
    ("status", "狀態", "sel:A=在職,L=留職停薪,Q=離職"),
    ("base_salary", "本薪（月）", "n"), ("hourly_wage", "時薪", "n"),
    ("shift_group", "預設班別", "shift"), ("punch_required", "需要打卡", "b"), ("gps_site", "預設打卡地點", "site"),
    ("phone", "電話", "s"), ("mobile", "手機", "s"), ("email", "電子郵件", "s"), ("address", "地址", "s"),
    ("emergency", "緊急聯絡人", "s"), ("bank_code", "銀行代號", "s"), ("bank_account", "銀行帳號", "s"),
    ("labor_ins", "勞保", "b"), ("employment_ins", "就業保險", "b"), ("occ_ins", "職災保險", "b"),
    ("nhi", "健保", "b"), ("pension", "勞退 6%", "b"),
    ("labor_wage", "勞保投保薪資（0＝自動）", "n"), ("nhi_wage", "健保投保金額（0＝自動）", "n"),
    ("pension_wage", "勞退月提繳工資（0＝自動）", "n"), ("nhi_dependents", "健保眷屬人數", "i"),
    ("pension_self", "勞退自提率 %", "n"), ("ins_date", "加保日", "d"),
    ("tax_mode", "扣繳方式", "sel:T=依扣繳稅額表（概算）,R=固定扣繳率,N=不扣繳"),
    ("tax_dependents", "扶養人數", "i"), ("tax_rate", "固定扣繳率 %", "n"),
    ("memo", "備註", "s"),
]
SALARY_FIELDS = {"base_salary", "hourly_wage", "labor_wage", "nhi_wage", "pension_wage", "bank_code", "bank_account"}
ID_LETTERS = "ABCDEFGHJKLMNPQRSTUVXYWZIO"


def valid_id_no(s):
    """身分證（A123456789）與新式居留證（A800000014）檢查碼。"""
    s = (s or "").strip().upper()
    if len(s) != 10 or s[0] not in ID_LETTERS or not s[1:].isdigit():
        return False
    n = ID_LETTERS.index(s[0]) + 10
    total = n // 10 + (n % 10) * 9
    for i, ch in enumerate(s[1:9]):
        total += int(ch) * (8 - i)
    total += int(s[9])
    return total % 10 == 0


class EmpMixin:
    # ================================================================ 查詢
    def employees(self, status="", dept="", search=""):
        if not (self.can("EMP", 1) or self.can("ATT", 1) or self.can("LEV", 1) or self.can("PAY", 1)):
            self.need("EMP", 1)
        where, args = [], []
        if status == "work":
            where.append("e.status<>'Q'")
        elif status:
            where.append("e.status=%s")
            args.append(status)
        if dept:
            where.append("e.dept=%s")
            args.append(dept)
        if search:
            where.append("(e.code LIKE %s OR e.name LIKE %s OR e.title LIKE %s OR e.mobile LIKE %s)")
            args += ["%" + search + "%"] * 4
        rows = self.db.rows("SELECT e.*, d.name AS dept_name FROM employees e LEFT JOIN departments d ON d.code=e.dept"
                            + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY e.code", tuple(args))
        for r in rows:
            r["status_name"] = EMP_STATUS.get(r["status"], r["status"])
            if not self.see_salary:
                for k in SALARY_FIELDS:
                    r[k] = None
        return rows

    def employee(self, code):
        e = self.db.row("SELECT e.*, d.name AS dept_name, d.cost_type FROM employees e LEFT JOIN departments d ON "
                        "d.code=e.dept WHERE e.code=%s", (code,))
        if not e:
            raise BizError("員工 %s 不存在" % code)
        return e

    def employee_view(self, code):
        """畫面用：無薪資權限者看不到薪資相關欄位（自己的資料除外）。"""
        if code != self.my_emp:
            self.need("EMP", 1)
        e = dict(self.employee(code))
        if not self.see_salary and code != self.my_emp:
            for k in SALARY_FIELDS:
                e[k] = None
        return e

    def active_employees(self, on_first, on_last, dept=""):
        """期間內有在職的員工（計薪、排班用）。"""
        sql = ("SELECT e.*, d.cost_type FROM employees e LEFT JOIN departments d ON d.code=e.dept WHERE "
               "(e.hire_date IS NULL OR e.hire_date<=%s) AND (e.leave_date IS NULL OR e.leave_date>=%s)")
        args = [on_last, on_first]
        if dept:
            sql += " AND e.dept=%s"
            args.append(dept)
        return self.db.rows(sql + " ORDER BY e.dept, e.code", tuple(args))

    def wage_basis(self, e):
        """經常性薪資（本薪＋經常性的固定津貼）：投保薪資、加班費、請假扣薪的基數。"""
        if e.get("emp_type") == "H":
            base = yuan(Decimal(e.get("hourly_wage") or 0) * 176)
        else:
            base = Decimal(e.get("base_salary") or 0)
        extra = self.db.value("SELECT COALESCE(SUM(x.amount), 0) FROM emp_items x JOIN pay_items p ON p.code=x.item "
                              "WHERE x.emp=%s AND p.kind='E' AND p.regular=1 AND p.code<>'BASE'", (e["code"],))
        return base + Decimal(extra or 0)

    # ================================================================ 維護
    def save_employee(self, row: dict, is_new: bool):
        self.need("EMP")
        types = {k: t for k, _, t in EMP_FIELDS}
        data = {}
        for k, title, typ in EMP_FIELDS:
            if k not in row:
                continue
            if k in SALARY_FIELDS and not self.see_salary and not is_new:
                continue
            v = row[k]
            if typ == "n":
                v = dec(v)
            elif typ == "i":
                try:
                    v = int(str(v or 0).replace(",", ""))
                except ValueError:
                    raise BizError("「%s」要是整數" % title)
            elif typ == "b":
                v = int(bool(v))
            elif typ == "d":
                v = opt_date(v)
            elif typ == "site":
                v = int(v or 0)
            else:
                v = ("" if v is None else str(v)).strip()
            data[k] = v
        code = data.get("code") or row.get("code")
        if not code:
            raise BizError("請輸入員工編號")
        if any(ch in code for ch in " ,'\"\\/"):
            raise BizError("員工編號不能有空白、逗號、斜線或引號")
        if is_new and not data.get("name"):
            raise BizError("請輸入姓名")
        if data.get("id_no"):
            data["id_no"] = data["id_no"].upper()
            if data.get("nationality", "T") == "T" and not valid_id_no(data["id_no"]):
                raise BizError("身分證號 %s 檢查碼不正確" % data["id_no"])
        if data.get("pension_self") is not None and not D0 <= data.get("pension_self", D0) <= 6:
            raise BizError("勞退自提率要在 0～6% 之間")
        if data.get("leave_date") and data.get("hire_date") and data["leave_date"] < data["hire_date"]:
            raise BizError("離職日不能早於到職日")
        if data.get("nhi_dependents", 0) < 0:
            raise BizError("眷屬人數不正確")
        if data.get("leave_date") and data.get("status", "A") == "A" and data["leave_date"] < dt.date.today():
            data["status"] = "Q"
        if data.get("nationality") == "F":
            data.setdefault("employment_ins", 0)
        old = None if is_new else self.employee(code)
        if is_new:
            if self.db.value("SELECT 1 FROM employees WHERE code=%s", (code,)):
                raise BizError("員工編號 %s 已存在" % code)
            data.setdefault("hire_date", dt.date.today())
            cols = list(data)
            self.db.exec("INSERT INTO employees (%s) VALUES (%s)" % (", ".join(cols), ", ".join(["%s"] * len(cols))),
                         tuple(data.values()))
            if data.get("base_salary") or data.get("hourly_wage"):
                self.db.exec("INSERT INTO salary_history (emp, eff_date, base_salary, hourly_wage, reason, created_by) "
                             "VALUES (%s, %s, %s, %s, '到職', %s)", (code, data.get("hire_date") or dt.date.today(),
                                                                     data.get("base_salary") or 0,
                                                                     data.get("hourly_wage") or 0, self.uid))
        else:
            upd = {k: v for k, v in data.items() if k != "code"}
            if upd:
                self.db.exec("UPDATE employees SET %s WHERE code=%%s" % ", ".join("%s=%%s" % k for k in upd),
                             tuple(upd.values()) + (code,))
            if self.see_salary and old and (Decimal(old["base_salary"]) != Decimal(data.get("base_salary", old["base_salary"]))
                                            or Decimal(old["hourly_wage"]) != Decimal(data.get("hourly_wage", old["hourly_wage"]))):
                self.db.exec("INSERT INTO salary_history (emp, eff_date, base_salary, hourly_wage, reason, created_by) "
                             "VALUES (%s, %s, %s, %s, %s, %s)",
                             (code, opt_date(row.get("salary_eff")) or dt.date.today(), data.get("base_salary", 0),
                              data.get("hourly_wage", 0), (row.get("salary_reason") or "調薪")[:60], self.uid))
        self.log("emp_" + ("new" if is_new else "edit"), code,
                 json.dumps({k: str(v) for k, v in data.items() if k not in SALARY_FIELDS}, ensure_ascii=False)[:480])
        return code

    def delete_employee(self, code):
        self.need("EMP")
        for t, c in (("payslips", "emp"), ("punches", "emp"), ("leave_requests", "emp"), ("overtime", "emp")):
            if self.db.value("SELECT 1 FROM %s WHERE %s=%%s LIMIT 1" % (t, c), (code,)):
                raise BizError("此員工已有出勤或薪資紀錄，不能刪除（請輸入離職日）")
        with self.db.transaction():
            for t in ("emp_items", "salary_history", "roster", "leave_grants"):
                self.db.exec("DELETE FROM %s WHERE emp=%%s" % t, (code,))
            self.db.exec("DELETE FROM employees WHERE code=%s", (code,))
        self.log("emp_delete", code)

    def resign(self, code, leave_date, reason=""):
        """離職：寫入離職日；之後到「假期額度」結算特休、補休，再計算最後一個月薪資。"""
        self.need("EMP")
        d = date(leave_date)
        e = self.employee(code)
        if e["hire_date"] and d < e["hire_date"]:
            raise BizError("離職日不能早於到職日")
        self.db.exec("UPDATE employees SET leave_date=%s, status=%s, memo=CONCAT(memo, %s) WHERE code=%s",
                     (d, "Q" if d <= dt.date.today() else e["status"], (" 離職原因：" + reason) if reason else "", code))
        self.log("emp_resign", code, "%s %s" % (d, reason))

    # ---------------------------------------------------------------- 調薪紀錄
    def salary_history(self, code):
        if code != self.my_emp:
            self.need("SAL", 1)
        return self.db.rows("SELECT * FROM salary_history WHERE emp=%s ORDER BY eff_date DESC, id DESC", (code,))

    def salary_on(self, e, on):
        """某日適用的本薪／時薪（依調薪紀錄；沒有紀錄時用員工資料）。"""
        r = self.db.row("SELECT base_salary, hourly_wage FROM salary_history WHERE emp=%s AND eff_date<=%s ORDER BY "
                        "eff_date DESC, id DESC LIMIT 1", (e["code"], on))
        if r:
            return Decimal(r["base_salary"]), Decimal(r["hourly_wage"])
        return Decimal(e["base_salary"] or 0), Decimal(e["hourly_wage"] or 0)

    # ---------------------------------------------------------------- 固定薪資項目
    def emp_items(self, code):
        if code != self.my_emp:
            self.need("SAL", 1)
        return self.db.rows("SELECT x.item, x.amount, p.name, p.kind, p.regular, p.taxable FROM emp_items x JOIN pay_items p "
                            "ON p.code=x.item WHERE x.emp=%s ORDER BY p.kind DESC, p.sort", (code,))

    def pay_items_fixed(self):
        """員工固定薪資項目可選的科目。"""
        self.need("EMP", 1)
        return self.db.rows("SELECT * FROM pay_items WHERE active=1 AND method='F' ORDER BY kind DESC, sort")

    def save_emp_items(self, code, items):
        """items＝{科目: 金額}；金額 0 表示刪除。"""
        self.need("EMP")
        self.need("SAL", 1)
        valid = {r["code"]: r for r in self.db.rows("SELECT code, method, kind FROM pay_items")}
        with self.db.transaction():
            for item, amount in items.items():
                if item not in valid:
                    raise BizError("薪資科目 %s 不存在" % item)
                if item == "BASE":
                    raise BizError("本薪請在員工資料的「本薪」欄輸入")
                a = yuan(amount)
                if a < 0:
                    raise BizError("金額不能是負數（扣款請用應扣科目）")
                if a == 0:
                    self.db.exec("DELETE FROM emp_items WHERE emp=%s AND item=%s", (code, item))
                else:
                    self.db.exec("REPLACE INTO emp_items (emp, item, amount) VALUES (%s, %s, %s)", (code, item, a))
        self.log("emp_items", code, json.dumps({k: str(v) for k, v in items.items()}, ensure_ascii=False))

    def headcount(self, on=None):
        on = on or dt.date.today()
        return self.db.value("SELECT COUNT(*) FROM employees WHERE (hire_date IS NULL OR hire_date<=%s) AND "
                             "(leave_date IS NULL OR leave_date>=%s)", (on, on)) or 0
