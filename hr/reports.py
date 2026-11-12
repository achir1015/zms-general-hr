"""報表：首頁摘要、薪資總表、勞健保退休金明細、年度扣繳彙總、補充保費、請假統計、人力統計。"""
import datetime as dt
from decimal import Decimal

from . import rocdate
from .attendance import ym_days
from .core import D0, DEPT_COST, EMP_STATUS, date


class ReportsMixin:
    def dashboard(self):
        today = dt.date.today()
        ym = rocdate.ym(today)
        out = dict(headcount=self.headcount(today), ym=ym)
        first = today.replace(day=1)
        out["joins"] = self.db.value("SELECT COUNT(*) FROM employees WHERE hire_date BETWEEN %s AND %s", (first, today)) or 0
        out["leaves"] = self.db.value("SELECT COUNT(*) FROM employees WHERE leave_date BETWEEN %s AND %s",
                                      (first, rocdate.month_last(today))) or 0
        out["pending_leave"] = self.db.value("SELECT COUNT(*) FROM leave_requests WHERE status=0") or 0
        out["pending_ot"] = self.db.value("SELECT COUNT(*) FROM overtime WHERE status=0") or 0
        out["pending_punch"] = self.db.value("SELECT COUNT(*) FROM punches WHERE ok=0 AND void=0") or 0
        out["occ_open"] = self.db.value("SELECT COUNT(*) FROM occ_cases WHERE status<>'C'") or 0
        last = self.db.row("SELECT * FROM payroll_runs WHERE kind='M' ORDER BY ym DESC LIMIT 1")
        out["last_run"] = last
        out["trend"] = []
        if self.see_salary:
            for r in self.db.rows("SELECT ym, SUM(gross) g, SUM(net) n, SUM(employer_cost) er FROM payroll_runs WHERE "
                                  "status>=1 GROUP BY ym ORDER BY ym DESC LIMIT 12"):
                out["trend"].insert(0, r)
        out["today"] = self.today_board() if self.can("ATT", 1) else None
        out["birthdays"] = self.db.rows("SELECT code, name, birthday FROM employees WHERE status<>'Q' AND birthday IS NOT NULL "
                                        "AND MONTH(birthday)=%s ORDER BY DAY(birthday)", (today.month,))
        out["upcoming_disaster"] = self.db.rows("SELECT * FROM disasters WHERE d>=%s ORDER BY d LIMIT 3", (today,))
        out["gl_pending"] = sum(self.gl_pending(dt.date(today.year - 1, 1, 1), today + dt.timedelta(days=40)).values()) \
            if self.can("GL", 1) else 0
        return out

    # ================================================================ 薪資
    def payroll_register(self, ym, kind=""):
        """薪資總表：每人一列（含應發、應扣、實發、公司負擔）。"""
        self.need("SAL", 1)
        sql = ("SELECT s.*, r.title, r.kind AS run_kind, d.name AS dept_name FROM payslips s JOIN payroll_runs r ON "
               "r.id=s.run_id LEFT JOIN departments d ON d.code=s.dept WHERE r.ym=%s")
        args = [ym]
        if kind:
            sql += " AND r.kind=%s"
            args.append(kind)
        rows = self.db.rows(sql + " ORDER BY s.dept, s.emp, r.id", tuple(args))
        for r in rows:
            r["er_total"] = r["labor_er"] + r["occ_er"] + r["fund_er"] + r["nhi_er"] + r["pension_er"]
            r["cost_total"] = r["gross"] + r["er_total"]
        return rows

    def payroll_by_item(self, ym):
        """薪資科目彙總（各科目金額合計，依部門）。"""
        self.need("SAL", 1)
        return self.db.rows("SELECT l.item, l.name, l.kind, s.dept, SUM(l.amount) amount, COUNT(DISTINCT s.emp) n FROM "
                            "payslip_lines l JOIN payslips s ON s.id=l.slip_id JOIN payroll_runs r ON r.id=s.run_id WHERE "
                            "r.ym=%s GROUP BY l.item, l.name, l.kind, s.dept ORDER BY l.kind DESC, l.item, s.dept", (ym,))

    def dept_cost(self, year):
        """各部門人事成本（月份 × 部門）。"""
        self.need("SAL", 1)
        rows = self.db.rows("SELECT r.ym, s.dept, d.name AS dept_name, d.cost_type, SUM(s.gross) gross, "
                            "SUM(s.labor_er+s.occ_er+s.fund_er+s.nhi_er+s.pension_er) er FROM payslips s JOIN payroll_runs r "
                            "ON r.id=s.run_id LEFT JOIN departments d ON d.code=s.dept WHERE r.ym LIKE %s AND r.status>=1 "
                            "GROUP BY r.ym, s.dept ORDER BY r.ym, s.dept", ("%d%%" % year,))
        for r in rows:
            r["total"] = (r["gross"] or D0) + (r["er"] or D0)
            r["cost_name"] = DEPT_COST.get(r["cost_type"] or "A", "")
            r["ym_show"] = rocdate.ym_show(r["ym"])
        return rows

    # ================================================================ 保費
    def insurance_detail(self, ym):
        """勞健保、勞退明細（可與勞保局、健保署繳款單核對）。"""
        self.need("INS", 1)
        rows = self.db.rows("SELECT s.emp, s.name, s.dept, s.labor_wage, s.occ_wage, s.nhi_wage, s.pension_wage, s.labor_emp, "
                            "s.labor_er, s.occ_er, s.fund_er, s.nhi_emp, s.nhi_er, s.pension_er, s.pension_self, "
                            "s.nhi_sup_emp FROM payslips s JOIN payroll_runs r ON r.id=s.run_id WHERE r.ym=%s AND "
                            "r.kind='M' ORDER BY s.emp", (ym,))
        for r in rows:
            r["labor_total"] = r["labor_emp"] + r["labor_er"] + r["occ_er"] + r["fund_er"]
            r["nhi_total"] = r["nhi_emp"] + r["nhi_er"]
            r["pension_total"] = r["pension_er"] + r["pension_self"]
        return rows

    def nhi_sup_report(self, year):
        self.need("INS", 1)
        emp = self.db.rows("SELECT r.ym, s.emp, s.name, s.bonus_nhi, s.nhi_sup_emp FROM payslips s JOIN payroll_runs r ON "
                           "r.id=s.run_id WHERE r.ym LIKE %s AND s.nhi_sup_emp>0 ORDER BY r.ym, s.emp",
                           ("%d%%" % year,))
        er = self.db.rows("SELECT * FROM nhi_employer_sup WHERE ym LIKE %s ORDER BY ym", ("%d%%" % year,))
        for r in emp + er:
            r["ym_show"] = rocdate.ym_show(r["ym"])
        return emp, er

    # ================================================================ 扣繳
    def tax_annual(self, year):
        """年度扣繳彙總（各類所得扣繳憑單 50 薪資所得用）：給付總額、扣繳稅額、自提勞退。"""
        self.need("SAL", 1)
        rows = self.db.rows("SELECT s.emp, e.name, e.id_no, e.address, SUM(s.taxable) taxable, SUM(s.tax) tax, "
                            "SUM(s.pension_self) pen_self, SUM(s.gross) gross FROM payslips s JOIN payroll_runs r ON "
                            "r.id=s.run_id JOIN employees e ON e.code=s.emp WHERE r.ym LIKE %s AND r.status>=1 GROUP BY "
                            "s.emp, e.name, e.id_no, e.address ORDER BY s.emp", ("%d%%" % year,))
        for r in rows:
            r["income_code"] = "50"
            r["net_pay"] = r["taxable"] - r["tax"]
        return rows

    # ================================================================ 請假、人力
    def leave_stats(self, year, dept=""):
        self.need("LEV", 1)
        rows = self.db.rows("SELECT r.emp, e.name, e.dept, t.code, t.name AS lname, SUM(r.hours) h FROM leave_requests r JOIN "
                            "employees e ON e.code=r.emp JOIN leave_types t ON t.code=r.ltype WHERE r.status=1 AND "
                            "YEAR(r.start_at)=%s" + (" AND e.dept=%s" if dept else "") +
                            " GROUP BY r.emp, e.name, e.dept, t.code, t.name ORDER BY r.emp",
                            (year, dept) if dept else (year,))
        out = {}
        for r in rows:
            o = out.setdefault(r["emp"], dict(emp=r["emp"], name=r["name"], dept=r["dept"], total=Decimal(0)))
            o[r["code"]] = r["h"]
            o["total"] += r["h"]
        return list(out.values())

    def headcount_report(self, year):
        self.need("EMP", 1)
        out = []
        for m in range(1, 13):
            first, last = ym_days("%04d%02d" % (year, m))
            if first > dt.date.today():
                break
            out.append(dict(ym=rocdate.ym_show("%04d%02d" % (year, m)), head=self.headcount(last),
                            joins=self.db.value("SELECT COUNT(*) FROM employees WHERE hire_date BETWEEN %s AND %s",
                                                (first, last)) or 0,
                            leaves=self.db.value("SELECT COUNT(*) FROM employees WHERE leave_date BETWEEN %s AND %s",
                                                 (first, last)) or 0))
        return out

    def roster_of_staff(self, on=None):
        """員工名冊（勞動檢查常用）：姓名、性別、出生、身分證、到職、職稱、投保薪資。"""
        self.need("EMP", 1)
        on = date(on) if on else dt.date.today()
        rows = self.active_employees(on, on)
        for r in rows:
            r["gender_name"] = "女" if r["gender"] == "F" else "男"
            r["status_name"] = EMP_STATUS.get(r["status"], "")
            if not self.see_salary:
                r["base_salary"] = None
        return rows
