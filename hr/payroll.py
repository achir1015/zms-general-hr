"""薪資計算：每月變動輸入、津貼獎金規則、月薪計算、獎金發放、確認發放、關帳、銀行轉帳檔。

月薪計算順序（每位員工）：
1. 本薪：月薪 × 在職日數 ÷ 30（整月以 30 日計）；時薪人員＝時薪 ×（實際出勤＋給薪假）時數
2. 固定津貼（員工固定薪資項目）；經常性津貼同樣依在職日數比例
3. 全勤獎金：依公司設定，請影響全勤的假、曠職、遲到時依比例扣發或不發
   （生理假、婚喪假、公傷病假、產假、家庭照顧假、災害假不影響；普通傷病假一年 10 日內不影響）
4. 加班費：核准、選加班費的加班單，依勞基法費率計算；每月 46 小時內免稅
5. 請假扣款：時薪基數＝（本薪＋經常性給與）÷ 30 ÷ 8 × 時數 ×（1－給薪比例）；依曆計算的假別以日薪 × 日數
   公傷病假：先扣再以「公傷病假工資補償」（免稅）發回，原領工資不變但稅務正確
6. 遲到早退、曠職扣款（公司設定可關閉）；災害停班不給薪扣款、停班日出勤加給
7. 每月變動輸入（獎金、借支、其他加扣項，特休／補休折發）
8. 勞保（含就保，按投保日數）、健保（月底在保才收）、勞退自提、二代健保補充保費、所得稅
"""
import csv
import datetime as dt
import json
from decimal import Decimal

from . import laws, rocdate
from .attendance import ym_days
from .core import D0, BizError, date, yuan

RUN_STATUS = {0: "試算中", 1: "已確認", 2: "已發放"}
RUN_KIND = {"M": "月薪", "B": "獎金"}


def ym_of(v):
    s = str(v or "").replace("/", "").replace("-", "").strip()
    if len(s) == 5:                       # 民國 11511
        s = "%04d%02d" % (int(s[:3]) + 1911, int(s[3:]))
    if len(s) != 6 or not s.isdigit() or not 1 <= int(s[4:]) <= 12:
        raise BizError("年月格式不正確（例如 202611 或 11511）")
    return s


class PayMixin:
    # ================================================================ 每月變動輸入
    def pay_inputs(self, ym, run_kind="M", emp=""):
        self.need("PAY", 1)
        sql = ("SELECT x.*, e.name, p.name AS item_name, p.kind FROM pay_inputs x JOIN employees e ON e.code=x.emp JOIN "
               "pay_items p ON p.code=x.item WHERE x.ym=%s AND x.run_kind=%s")
        args = [ym_of(ym), run_kind]
        if emp:
            sql += " AND x.emp=%s"
            args.append(emp)
        return self.db.rows(sql + " ORDER BY x.emp, p.sort", tuple(args))

    def add_pay_input(self, ym, run_kind, emp, item, amount, note=""):
        self.need("PAY")
        ym = ym_of(ym)
        self._check_run_open(ym, run_kind)
        p = self.db.row("SELECT * FROM pay_items WHERE code=%s", (item,))
        if not p:
            raise BizError("薪資科目 %s 不存在" % item)
        if p["method"] == "S" and item != "TAX":
            raise BizError("「%s」由系統計算，不能手動輸入" % p["name"])
        self.employee(emp)
        a = yuan(amount)
        if a == 0:
            raise BizError("金額不能是 0")
        iid = self.db.exec("INSERT INTO pay_inputs (ym, run_kind, emp, item, amount, note, created_by) VALUES "
                           "(%s, %s, %s, %s, %s, %s, %s)", (ym, run_kind, emp, item, a, (note or "")[:100], self.uid))
        self.log("pay_input", "%s %s" % (ym, emp), "%s %s" % (item, a))
        return iid

    def delete_pay_input(self, iid):
        self.need("PAY")
        x = self.db.row("SELECT * FROM pay_inputs WHERE id=%s", (iid,))
        if not x:
            return
        self._check_run_open(x["ym"], x["run_kind"])
        if x["source"] == "leave":
            self.db.exec("UPDATE leave_grants SET settled='', settled_ym='', settled_hours=0, settled_amount=0 WHERE id=%s",
                         (x["ref_id"],))
        self.db.exec("DELETE FROM pay_inputs WHERE id=%s", (iid,))

    def _check_run_open(self, ym, kind):
        r = self.db.row("SELECT status FROM payroll_runs WHERE ym=%s AND kind=%s AND status>=1 LIMIT 1", (ym, kind))
        if r:
            raise BizError("%s %s薪資已確認，不能再修改變動輸入（請先取消確認）" % (rocdate.ym_show(ym), RUN_KIND[kind]))

    # ================================================================ 津貼獎金規則
    def bonus_rule_list(self):
        self.need("BON", 1)
        return self.db.rows("SELECT id, name FROM bonus_rules WHERE active=1 ORDER BY id")

    def bonus_preview(self, rule_id, as_of):
        """依規則試算每位員工的金額：[(員工, 姓名, 基數, 比例, 金額, 說明)]。"""
        self.need("BON", 1)
        r = self.db.row("SELECT * FROM bonus_rules WHERE id=%s", (rule_id,))
        if not r:
            raise BizError("獎金規則不存在")
        as_of = date(as_of)
        ys = dt.date(as_of.year, 1, 1)
        ye = dt.date(as_of.year, 12, 31)
        depts = [x.strip() for x in (r["depts"] or "").split(",") if x.strip()]
        out = []
        for e in self.active_employees(ys, as_of):
            if depts and e["dept"] not in depts:
                continue
            if r["exclude_left"] and e["leave_date"] and e["leave_date"] < as_of:
                continue
            sen = e["seniority_date"] or e["hire_date"] or ys
            nxt = as_of + dt.timedelta(days=1)             # 到基準日當天為止的完整月數（10/1 到職、12/31 基準＝3 個月）
            months_srv = (nxt.year - sen.year) * 12 + nxt.month - sen.month - (nxt.day < sen.day)
            if months_srv < r["min_months"]:
                continue
            base, _ = self.salary_on(e, as_of)
            if r["basis"] == "M":
                basis = self.wage_basis(dict(e, base_salary=base))
                amt = basis * Decimal(r["value"])
            elif r["basis"] == "B":
                basis = base
                amt = base * Decimal(r["value"])
            else:
                basis = Decimal(r["value"])
                amt = basis
            s = max(e["hire_date"] or ys, ys)
            en = min(e["leave_date"] or ye, ye)
            if r["prorate"] == "Y":
                m = (en.year - s.year) * 12 + en.month - s.month + (1 if en.day >= s.day - 1 or en.month != s.month else 0)
                ratio = min(Decimal(max(m, 0)) / 12, Decimal(1))
                if s == ys and en == ye:
                    ratio = Decimal(1)
            elif r["prorate"] == "D":
                ratio = min(Decimal((en - s).days + 1) / Decimal((ye - ys).days + 1), Decimal(1))
            else:
                ratio = Decimal(1)
            amt = yuan(amt * ratio)
            if amt <= 0:
                continue
            note = "%s × %s%s" % (laws._fmt(basis), laws._fmt(Decimal(r["value"])) + " 個月" if r["basis"] != "A" else "1",
                                  "" if ratio == 1 else " × 在職比例 %.2f" % ratio)
            out.append(dict(emp=e["code"], name=e["name"], dept=e["dept"], basis=basis, ratio=ratio, amount=amt, note=note))
        return out

    def generate_bonus(self, rule_id, as_of, ym, run_kind="B", emps=None):
        """依規則產生每月變動輸入（同一規則同一月份重新產生時會先刪除舊的）。回傳 (筆數, 合計)。"""
        self.need("BON")
        ym = ym_of(ym)
        self._check_run_open(ym, run_kind)
        r = self.db.row("SELECT * FROM bonus_rules WHERE id=%s", (rule_id,))
        rows = self.bonus_preview(rule_id, as_of)
        if emps:
            rows = [x for x in rows if x["emp"] in emps]
        with self.db.transaction():
            self.db.exec("DELETE FROM pay_inputs WHERE ym=%s AND run_kind=%s AND source='bonus' AND ref_id=%s",
                         (ym, run_kind, rule_id))
            self.db.exec_many("INSERT INTO pay_inputs (ym, run_kind, emp, item, amount, note, source, ref_id, created_by) "
                              "VALUES (%s, %s, %s, %s, %s, %s, 'bonus', %s, %s)",
                              [(ym, run_kind, x["emp"], r["item"], x["amount"], (r["name"] + "：" + x["note"])[:100],
                                rule_id, self.uid) for x in rows])
        tot = sum((x["amount"] for x in rows), D0)
        self.log("bonus_gen", r["name"], "%s %d 人 %s" % (ym, len(rows), tot))
        return len(rows), tot

    # ================================================================ 薪資批次
    def payroll_runs(self, year=None):
        self.need("PAY", 1)
        sql = "SELECT * FROM payroll_runs" + (" WHERE ym LIKE %s" if year else "") + " ORDER BY ym DESC, kind, id DESC"
        rows = self.db.rows(sql, ("%d%%" % year,) if year else ())
        for r in rows:
            r["status_name"] = RUN_STATUS.get(r["status"], "")
            r["kind_name"] = RUN_KIND.get(r["kind"], "")
            r["ym_show"] = rocdate.ym_show(r["ym"])
        return rows

    def payroll_run(self, rid):
        self.need("PAY", 1)
        r = self.db.row("SELECT * FROM payroll_runs WHERE id=%s", (rid,))
        if not r:
            raise BizError("薪資批次不存在")
        r["status_name"] = RUN_STATUS.get(r["status"], "")
        r["kind_name"] = RUN_KIND.get(r["kind"], "")
        return r

    def create_run(self, ym, kind="M", title="", pay_date=None):
        self.need("PAY")
        ym = ym_of(ym)
        if kind not in RUN_KIND:
            raise BizError("薪資種類不正確")
        title = (title or ("%s薪資" % rocdate.ym_show(ym) if kind == "M" else "%s獎金" % rocdate.ym_show(ym))).strip()
        if kind == "M" and self.db.value("SELECT 1 FROM payroll_runs WHERE ym=%s AND kind='M'", (ym,)):
            raise BizError("%s 已經有月薪批次" % rocdate.ym_show(ym))
        if self.db.value("SELECT 1 FROM payroll_runs WHERE ym=%s AND kind=%s AND title=%s", (ym, kind, title)):
            raise BizError("同名的薪資批次已存在")
        if pay_date:
            pd = date(pay_date)
        else:
            day = int(self.company().get("pay_day") or 5)
            first, last = ym_days(ym)
            nxt = last + dt.timedelta(days=1)
            import calendar
            pd = dt.date(nxt.year, nxt.month, min(day, calendar.monthrange(nxt.year, nxt.month)[1])) if kind == "M" else last
        rid = self.db.exec("INSERT INTO payroll_runs (ym, kind, title, pay_date, created_by) VALUES (%s, %s, %s, %s, %s)",
                           (ym, kind, title[:60], pd, self.uid))
        self.log("run_new", str(rid), "%s %s" % (ym, title))
        return rid

    def delete_run(self, rid):
        self.need("PAY")
        r = self.payroll_run(rid)
        if r["status"] != 0:
            raise BizError("已確認的薪資批次不能刪除，請先取消確認")
        with self.db.transaction():
            self.db.exec("DELETE l FROM payslip_lines l JOIN payslips s ON s.id=l.slip_id WHERE s.run_id=%s", (rid,))
            self.db.exec("DELETE FROM payslips WHERE run_id=%s", (rid,))
            self.db.exec("DELETE FROM payroll_runs WHERE id=%s", (rid,))
        self.log("run_delete", str(rid))

    def calculate(self, rid):
        """重新計算整批（試算中才能算）。回傳 dict(count, gross, net, warnings)。"""
        self.need("PAY")
        run = self.payroll_run(rid)
        if run["status"] != 0:
            raise BizError("已確認的批次不能重算，請先取消確認")
        ym = run["ym"]
        first, last = ym_days(ym)
        P = self.params(last)
        comp = self.company()
        items = {r["code"]: r for r in self.db.rows("SELECT * FROM pay_items")}
        warnings = []
        if run["kind"] == "M":
            emps = self.active_employees(first, last)
            att = {}
            for rec in self.attendance(first, last, emps):
                att.setdefault(rec["emp"], []).append(rec)
        else:
            codes = [r["emp"] for r in self.db.rows("SELECT DISTINCT emp FROM pay_inputs WHERE ym=%s AND run_kind='B'", (ym,))]
            emps = [dict(self.employee(c)) for c in codes]
            att = {}
        inputs = {}
        for x in self.db.rows("SELECT * FROM pay_inputs WHERE ym=%s AND run_kind=%s", (ym, run["kind"])):
            inputs.setdefault(x["emp"], []).append(x)
        with self.db.transaction():
            self.db.exec("DELETE l FROM payslip_lines l JOIN payslips s ON s.id=l.slip_id WHERE s.run_id=%s", (rid,))
            self.db.exec("DELETE FROM payslips WHERE run_id=%s", (rid,))
            tot_g = tot_n = tot_er = D0
            for e in emps:
                if run["kind"] == "M":
                    slip, lines, notes = self._calc_month(e, ym, first, last, P, comp, items, att.get(e["code"], []),
                                                          inputs.get(e["code"], []))
                else:
                    slip, lines, notes = self._calc_bonus(e, ym, last, P, items, inputs.get(e["code"], []))
                if slip["net"] < 0:
                    warnings.append("%s %s 實發為負數 %s" % (e["code"], e["name"], slip["net"]))
                slip.update(run_id=rid, emp=e["code"], name=e["name"], dept=e["dept"] or "",
                            cost_type=e.get("cost_type") or "A", notes=json.dumps(notes, ensure_ascii=False))
                cols = list(slip)
                sid = self.db.exec("INSERT INTO payslips (%s) VALUES (%s)" % (", ".join(cols), ", ".join(["%s"] * len(cols))),
                                   tuple(slip.values()))
                self.db.exec_many("INSERT INTO payslip_lines (slip_id, item, name, kind, amount, note, taxable, regular, "
                                  "nhi_bonus, gl_account, sort) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                  [(sid, ln["item"], ln["name"], ln["kind"], ln["amount"], ln["note"][:120], ln["taxable"],
                                    ln["regular"], ln["nhi_bonus"], ln["gl_account"], ln["sort"]) for ln in lines])
                tot_g += slip["gross"]
                tot_n += slip["net"]
                tot_er += sum(slip.get(k, D0) for k in ("labor_er", "occ_er", "fund_er", "nhi_er", "pension_er"))
            self.db.exec("UPDATE payroll_runs SET emp_count=%s, gross=%s, net=%s, employer_cost=%s WHERE id=%s",
                         (len(emps), tot_g, tot_n, tot_er, rid))
            self.recompute_employer_sup(ym)
        self.log("run_calc", str(rid), "%d 人 應發 %s 實發 %s" % (len(emps), tot_g, tot_n))
        return dict(count=len(emps), gross=tot_g, net=tot_n, warnings=warnings)

    # ---------------------------------------------------------------- 一位員工的月薪
    def _calc_month(self, e, ym, first, last, P, comp, items, recs, inputs):
        lines, notes = [], []

        def add(code, amount, note="", name=None, taxable=None):
            amount = yuan(amount)
            if amount == 0:
                return
            it = items.get(code) or dict(code=code, name=code, kind="E", taxable=1, regular=0, nhi_bonus=0, gl_account="",
                                         sort=100)
            lines.append(dict(item=code, name=name or it["name"], kind=it["kind"], amount=amount, note=note or "",
                              taxable=it["taxable"] if taxable is None else taxable, regular=it["regular"],
                              nhi_bonus=it["nhi_bonus"], gl_account=it["gl_account"] or "", sort=it["sort"]))

        start = max(e["hire_date"] or first, first)
        end = min(e["leave_date"] or last, last)
        cal_days = (end - start).days + 1
        full = start == first and end == last
        days = Decimal(30 if full else min(cal_days, 30))
        base, hourly = self.salary_on(e, last)
        basis = self.wage_basis(dict(e, base_salary=base))
        hb = basis / 30 / 8                                  # 平日每小時工資額
        daily = basis / 30
        hourly_emp = e["emp_type"] == "H"
        # 1. 本薪
        if hourly_emp:
            worked = sum(r["worked_min"] for r in recs) / Decimal(60)
            paid_leave = D0
            for r in recs:
                for code, lname, m in r["leaves"]:
                    ratio = self._leave_ratio(code, e, r["d"])
                    paid_leave += Decimal(m) / 60 * ratio
            hrs = (worked + paid_leave).quantize(Decimal("0.01"))
            add("BASE", hourly * hrs, "時薪 %s × %s 小時" % (laws._fmt(hourly), laws._fmt(hrs)))
            hb = hourly
            daily = hourly * 8
        else:
            add("BASE", base * days / 30, "月薪 %s" % laws._fmt(base) + ("" if full else " × %s/30 日" % laws._fmt(days)))
        if not full:
            notes.append("本月在職 %s～%s，以 %s 日計" % (rocdate.show(start), rocdate.show(end), laws._fmt(days)))
        # 2. 固定項目
        fixed = self.db.rows("SELECT x.item, x.amount FROM emp_items x WHERE x.emp=%s", (e["code"],))
        attend_amt = D0
        for f in fixed:
            it = items.get(f["item"])
            if not it or not it["active"]:
                continue
            amt = Decimal(f["amount"])
            if it["kind"] == "E" and not full:
                amt = amt * days / 30
            if f["item"] == "ATTEND":
                attend_amt = amt
                continue
            if f["item"] == "MEAL" and it["kind"] == "E" and amt > P["meal_taxfree"]:
                add("MEAL", P["meal_taxfree"], "免稅額內")
                add("MEAL", amt - P["meal_taxfree"], "超過每月 %s 免稅額部分" % laws._fmt(P["meal_taxfree"]),
                    name="伙食津貼（應稅）", taxable=1)
                continue
            add(f["item"], amt)
        # 3. 請假、遲到、曠職、災害
        leave_min_by = {}
        late = early = absent = 0
        late_cnt = 0
        dis_ded = dis_extra = D0
        sched_min = 0
        for r in recs:
            sched_min += r["work_min"] if r["day_type"] == "W" else 0
            for code, lname, m in r["leaves"]:
                leave_min_by[code] = leave_min_by.get(code, 0) + m
            late += r["late"]
            early += r["early"]
            absent += r["absent"]
            late_cnt += 1 if r["late"] or r["early"] else 0
            ev = r["disaster"]
            if ev and r["closure_min"]:
                worked_in_closure = bool(r["in_ts"])
                if worked_in_closure and Decimal(ev["work_extra"]) > 0:
                    dis_extra += daily * Decimal(ev["work_extra"]) * Decimal(r["closure_min"]) / max(r["work_min"], 1)
                elif not worked_in_closure and ev["pay_policy"] == "U" and not hourly_emp:
                    dis_ded += hb * Decimal(r["closure_min"]) / 60
        ltypes = {t["code"]: t for t in self.db.rows("SELECT * FROM leave_types")}
        leave_ded = D0
        occ_wage = D0
        leave_notes = []
        affect_h = D0
        total_leave_h = D0
        for code, m in leave_min_by.items():
            t = ltypes.get(code)
            if not t or t["calendar_days"]:
                continue
            h = Decimal(m) / 60
            total_leave_h += h
            ratio = self._leave_ratio(code, e, last)
            if not hourly_emp:
                if code == "OCC":
                    leave_ded += hb * h
                    occ_wage += hb * h
                else:
                    leave_ded += hb * h * (1 - ratio)
            leave_notes.append("%s %s小時" % (t["name"], laws._fmt(h.quantize(Decimal("0.01")))))
            if t["affects_attend"]:
                affect_h += h
        # 依曆計算的假別（產假、育嬰留停…）：日薪 × 日數
        for lv in self.db.rows("SELECT r.*, t.name AS lname, t.pay_ratio FROM leave_requests r JOIN leave_types t ON "
                               "t.code=r.ltype WHERE r.emp=%s AND r.status=1 AND t.calendar_days=1 AND r.start_at<=%s AND "
                               "r.end_at>=%s", (e["code"], dt.datetime.combine(last, dt.time(23, 59)),
                                                dt.datetime.combine(first, dt.time()))):
            d1 = max(lv["start_at"].date(), start)
            d2 = min(lv["end_at"].date(), end)
            if d2 < d1:
                continue
            nd = min(Decimal((d2 - d1).days + 1), days)
            ratio = self._leave_ratio(lv["ltype"], e, d1)
            if not hourly_emp:
                leave_ded += daily * nd * (1 - ratio)
            total_leave_h += nd * 8
            leave_notes.append("%s %s日（依曆）" % (lv["lname"], laws._fmt(nd)))
        # 普通傷病假：一年 10 日內不影響全勤
        sick_h = Decimal(leave_min_by.get("SICK", 0)) / 60
        if sick_h and ltypes.get("SICK", {}).get("affects_attend"):
            prior = Decimal(self.db.value(
                "SELECT COALESCE(SUM(hours), 0) FROM leave_requests WHERE emp=%s AND status=1 AND ltype='SICK' AND "
                "start_at>=%s AND start_at<%s", (e["code"], dt.datetime(first.year, 1, 1),
                                                  dt.datetime.combine(first, dt.time()))) or 0)
            free = P["sick_attend_free"] * 8
            exempt = max(min(sick_h, free - prior), D0)
            affect_h -= exempt
            if exempt:
                notes.append("普通傷病假 %s 小時在每年 %s 日內，不影響全勤" % (laws._fmt(exempt), laws._fmt(P["sick_attend_free"])))
        if leave_ded:
            add("LEAVE_DED", leave_ded, "、".join(leave_notes))
        if occ_wage:
            add("OCC_WAGE", occ_wage, "公傷病假 %s 小時原領工資" % laws._fmt((Decimal(leave_min_by["OCC"]) / 60).quantize(Decimal("0.01"))))
        if comp.get("late_deduct") and (late or early) and not hourly_emp:
            add("LATE_DED", hb * Decimal(late + early) / 60, "遲到 %d 分、早退 %d 分" % (late, early))
        if comp.get("absent_deduct") and absent and not hourly_emp:
            add("ABSENT_DED", hb * Decimal(absent) / 60, "曠職 %s 小時" % laws._fmt((Decimal(absent) / 60).quantize(Decimal("0.01"))))
        if dis_ded:
            add("DIS_DED", dis_ded, "災害停班（公司公告不給薪）")
        if dis_extra:
            add("DISASTER", dis_extra, "停班日出勤加給")
        # 全勤獎金
        if attend_amt:
            lost = D0
            reason = []
            if affect_h:
                reason.append("請假 %s 小時" % laws._fmt(affect_h.quantize(Decimal("0.01"))))
            if absent:
                reason.append("曠職")
            if late_cnt:
                reason.append("遲到早退 %d 次" % late_cnt)
            if comp.get("attend_rule") == "A":
                if affect_h > 0 or absent or late_cnt:
                    lost = attend_amt
            else:
                hours_base = Decimal(sched_min) / 60 or Decimal(240)
                lost = attend_amt * min((affect_h + Decimal(absent) / 60) / hours_base, Decimal(1))
            add("ATTEND", attend_amt - lost, ("扣發 %s（%s）" % (laws._fmt(yuan(lost)), "、".join(reason))) if lost else "")
        # 4. 加班費
        ot_rows = self.db.rows("SELECT * FROM overtime WHERE emp=%s AND status=1 AND comp='P' AND d BETWEEN %s AND %s "
                               "ORDER BY d, start_at", (e["code"], first, last))
        free_h = P["ot_taxfree_hours"]
        ot_free = ot_tax = D0
        ot_h = D0
        for o in ot_rows:
            a, note = laws.ot_amount(o["hours"], o["day_type"], self.hourly_rate(e, o["d"]))
            self.db.exec("UPDATE overtime SET amount=%s WHERE id=%s", (a, o["id"]))
            h = Decimal(o["hours"])
            ot_h += h
            if free_h >= h:
                ot_free += a
                free_h -= h
            else:
                part = a * free_h / h if h else D0
                ot_free += part
                ot_tax += a - part
                free_h = D0
        if ot_free:
            add("OT", ot_free, "核准加班 %s 小時" % laws._fmt(ot_h))
        if ot_tax:
            add("OT_TAX", ot_tax, "超過每月 %s 小時免稅標準" % laws._fmt(P["ot_taxfree_hours"]))
        # 5. 每月變動輸入
        tax_override = None
        for x in inputs:
            if x["item"] == "TAX":
                tax_override = Decimal(x["amount"])
                continue
            add(x["item"], x["amount"], x["note"])
        # 6. 保險、勞退（時薪人員依本月實際工資對照分級表）
        ins_basis = next((ln["amount"] for ln in lines if ln["item"] == "BASE"), D0) if hourly_emp else basis
        lw, ow, nw, pw = self.insured_wages(e, ins_basis, last)
        ins_start = max(e["ins_date"] or e["hire_date"] or first, first)
        ins_days = 30 if (ins_start == first and end == last) else min((end - ins_start).days + 1, 30)
        on_leave = e["status"] == "L"
        lemp, ler = laws.labor_premium(lw, P, bool(e["employment_ins"]), ins_days, bool(e["labor_ins"] or e["employment_ins"]))
        occ_er = laws.occ_premium(ow, comp.get("occ_rate") or 0, ins_days) if e["occ_ins"] else D0
        fund_er = laws.fund_premium(lw, P, ins_days) if e["labor_ins"] else D0
        at_month_end = end == last
        nemp, ner = laws.nhi_premium(nw, P, e["nhi_dependents"]) if (e["nhi"] and at_month_end) else (D0, D0)
        pen_er = laws.pension_amount(pw, P["pension_er"], ins_days) if e["pension"] else D0
        pen_self = laws.pension_amount(pw, e["pension_self"], ins_days) if e["pension_self"] else D0
        if on_leave:
            notes.append("育嬰留職停薪：雇主負擔保費免繳、員工負擔可遞延 3 年繳納（本月不扣）；留停期間不提繳勞退")
            ler = fund_er = ner = occ_er = pen_er = pen_self = D0
            lemp = nemp = D0
        if not at_month_end and e["nhi"]:
            notes.append("月底前離職：健保當月不收（由下一個投保單位或地區收取）")
        gross = sum((ln["amount"] for ln in lines if ln["kind"] == "E"), D0)
        bonus_nhi = sum((ln["amount"] for ln in lines if ln["kind"] == "E" and ln["nhi_bonus"]), D0)
        # 7. 二代健保補充保費（員工）
        sup = D0
        if e["nhi"] and nw:
            before = self._year_bonus_before(e["code"], ym)
            sup, base_sup = laws.nhi_bonus_sup(before, bonus_nhi, nw, P["nhi_sup_rate"])
            if sup:
                notes.append("獎金年累計超過投保金額 4 倍，補充保費基數 %s" % laws._fmt(base_sup))
        elif not e["nhi"] and gross >= P["min_wage"]:
            sup = laws.r0(gross * P["nhi_sup_rate"] / 100)
            notes.append("健保不在本公司投保（兼職）：單次給付達基本工資，扣補充保費 2.11%")
        # 8. 所得稅
        taxable = sum((ln["amount"] if ln["kind"] == "E" else -ln["amount"]) for ln in lines if ln["taxable"]) - pen_self
        taxable = max(taxable, D0)
        nonreg = sum((ln["amount"] for ln in lines if ln["kind"] == "E" and ln["taxable"] and ln["nhi_bonus"]), D0)
        if tax_override is not None:
            tax = tax_override
            notes.append("所得稅依手動指定")
        elif e["tax_mode"] == "N":
            tax = D0
        elif e["tax_mode"] == "R":
            tax = laws.r0(taxable * Decimal(e["tax_rate"]) / 100)
        else:
            tax = laws.withhold_regular(taxable - nonreg, e["tax_dependents"], P) + laws.withhold_nonregular(nonreg, P)
        add("LABOR", lemp, "投保薪資 %s%s" % (laws._fmt(lw), "" if ins_days == 30 else "，%d 日" % ins_days))
        add("NHI", nemp, "投保金額 %s，眷屬 %d 口" % (laws._fmt(nw), min(e["nhi_dependents"], 3)))
        add("NHI_SUP", sup)
        add("PEN_SELF", pen_self, "自提 %s%%" % laws._fmt(Decimal(e["pension_self"])))
        add("TAX", tax)
        deduct = sum((ln["amount"] for ln in lines if ln["kind"] == "D"), D0)
        slip = dict(base_salary=base, work_days=days, gross=gross, deduct=deduct, net=gross - deduct, taxable=taxable,
                    bonus_nhi=bonus_nhi, labor_wage=lw, occ_wage=ow, nhi_wage=nw if at_month_end else D0, pension_wage=pw,
                    labor_emp=lemp, nhi_emp=nemp, nhi_sup_emp=sup, pension_self=pen_self, tax=tax, labor_er=ler,
                    occ_er=occ_er, fund_er=fund_er, nhi_er=ner, pension_er=pen_er, ot_hours=ot_h,
                    leave_hours=total_leave_h.quantize(Decimal("0.01")), late_min=late + early)
        return slip, lines, notes

    def _leave_ratio(self, code, e, on):
        t = self.db.row("SELECT pay_ratio FROM leave_types WHERE code=%s", (code,))
        ratio = Decimal(t["pay_ratio"]) if t else Decimal(1)
        if code in ("MATERNITY", "MISCARRY"):
            sen = e["seniority_date"] or e["hire_date"]
            if sen and laws.add_months(sen, 6) > on:
                ratio = Decimal("0.5")
        return ratio

    def _year_bonus_before(self, emp, ym):
        return Decimal(self.db.value(
            "SELECT COALESCE(SUM(s.bonus_nhi), 0) FROM payslips s JOIN payroll_runs r ON r.id=s.run_id WHERE s.emp=%s AND "
            "r.ym LIKE %s AND (r.ym<%s OR (r.ym=%s AND r.kind='B' AND r.status>=1))",
            (emp, ym[:4] + "%", ym, ym)) or 0)

    # ---------------------------------------------------------------- 獎金批次
    def _calc_bonus(self, e, ym, last, P, items, inputs):
        lines, notes = [], []
        for x in inputs:
            it = items.get(x["item"])
            if not it or x["item"] == "TAX":
                continue
            lines.append(dict(item=x["item"], name=it["name"], kind=it["kind"], amount=yuan(x["amount"]), note=x["note"] or "",
                              taxable=it["taxable"], regular=it["regular"], nhi_bonus=it["nhi_bonus"],
                              gl_account=it["gl_account"] or "", sort=it["sort"]))
        gross = sum((ln["amount"] for ln in lines if ln["kind"] == "E"), D0)
        bonus_nhi = sum((ln["amount"] for ln in lines if ln["kind"] == "E" and ln["nhi_bonus"]), D0)
        basis = self.wage_basis(e)
        _, _, nw, _ = self.insured_wages(e, basis, last)
        sup = D0
        if e["nhi"] and nw:
            before = self._year_bonus_before(e["code"], ym) + Decimal(self.db.value(
                "SELECT COALESCE(SUM(s.bonus_nhi), 0) FROM payslips s JOIN payroll_runs r ON r.id=s.run_id WHERE s.emp=%s "
                "AND r.ym=%s AND r.kind='M'", (e["code"], ym)) or 0)
            sup, base_sup = laws.nhi_bonus_sup(before, bonus_nhi, nw, P["nhi_sup_rate"])
            if sup:
                notes.append("年累計獎金超過投保金額 %s 的 4 倍，補充保費基數 %s" % (laws._fmt(nw), laws._fmt(base_sup)))
        elif gross >= P["min_wage"]:
            sup = laws.r0(gross * P["nhi_sup_rate"] / 100)
        taxable = sum((ln["amount"] if ln["kind"] == "E" else -ln["amount"]) for ln in lines if ln["taxable"])
        override = next((Decimal(x["amount"]) for x in inputs if x["item"] == "TAX"), None)
        if override is not None:
            tax = override
        elif e["tax_mode"] == "N":
            tax = D0
        elif e["tax_mode"] == "R":
            tax = laws.r0(taxable * Decimal(e["tax_rate"]) / 100)
        else:
            tax = laws.withhold_nonregular(taxable, P)
            if tax:
                notes.append("非固定薪資達起扣額 %s，扣繳 %s%%" % (laws._fmt(P["tax_threshold"]), laws._fmt(P["tax_nonreg_rate"])))
        for code, amt in (("NHI_SUP", sup), ("TAX", tax)):
            if amt:
                it = items[code]
                lines.append(dict(item=code, name=it["name"], kind="D", amount=yuan(amt), note="", taxable=0, regular=0,
                                  nhi_bonus=0, gl_account=it["gl_account"], sort=it["sort"]))
        deduct = sum((ln["amount"] for ln in lines if ln["kind"] == "D"), D0)
        slip = dict(base_salary=D0, work_days=D0, gross=gross, deduct=deduct, net=gross - deduct, taxable=max(taxable, D0),
                    bonus_nhi=bonus_nhi, nhi_wage=D0, nhi_sup_emp=sup, tax=tax)
        return slip, lines, notes

    # ---------------------------------------------------------------- 投保單位補充保費
    def recompute_employer_sup(self, ym):
        """投保單位補充保費＝（當月支付薪資所得總額－當月受僱者健保投保金額總額）× 2.11%。"""
        first, last = ym_days(ym)
        P = self.params(last)
        wages = Decimal(self.db.value("SELECT COALESCE(SUM(s.taxable + s.pension_self), 0) FROM payslips s JOIN payroll_runs r "
                                      "ON r.id=s.run_id WHERE r.ym=%s", (ym,)) or 0)
        if self.db.value("SELECT 1 FROM payroll_runs WHERE ym=%s AND kind='M'", (ym,)):
            insured = Decimal(self.db.value("SELECT COALESCE(SUM(s.nhi_wage), 0) FROM payslips s JOIN payroll_runs r ON "
                                            "r.id=s.run_id WHERE r.ym=%s AND r.kind='M'", (ym,)) or 0)
        else:                       # 當月月薪還沒算：依月底在職、健保在本公司投保的員工估算
            insured = D0
            for e in self.active_employees(last, last):
                if e["nhi"]:
                    insured += self.insured_wages(e, self.wage_basis(e), last)[2]
        prem = laws.r0(max(wages - insured, D0) * P["nhi_sup_rate"] / 100)
        old = self.db.row("SELECT gl_batch_id FROM nhi_employer_sup WHERE ym=%s", (ym,))
        if old and old["gl_batch_id"]:
            return prem
        self.db.exec("REPLACE INTO nhi_employer_sup (ym, wage_total, insured_total, premium) VALUES (%s, %s, %s, %s)",
                     (ym, wages, insured, prem))
        return prem

    # ---------------------------------------------------------------- 查詢
    def payslips(self, rid):
        if not self.see_salary:
            self.need("SAL", 1)
        rows = self.db.rows("SELECT s.*, d.name AS dept_name FROM payslips s LEFT JOIN departments d ON d.code=s.dept "
                            "WHERE s.run_id=%s ORDER BY s.dept, s.emp", (rid,))
        for r in rows:
            r["ins_emp"] = r["labor_emp"] + r["nhi_emp"]
            r["er_total"] = r["labor_er"] + r["occ_er"] + r["fund_er"] + r["nhi_er"] + r["pension_er"]
        return rows

    def payslip(self, sid):
        s = self.db.row("SELECT s.*, r.ym, r.kind AS run_kind, r.title, r.pay_date, r.status AS run_status FROM payslips s "
                        "JOIN payroll_runs r ON r.id=s.run_id WHERE s.id=%s", (sid,))
        if not s:
            raise BizError("薪資單不存在")
        if s["emp"] != self.my_emp:
            self.need("SAL", 1)
        elif s["run_status"] < 1:
            raise BizError("薪資尚未確認")
        s["lines"] = self.db.rows("SELECT * FROM payslip_lines WHERE slip_id=%s ORDER BY kind DESC, sort, id", (sid,))
        s["notes"] = json.loads(s["notes"] or "[]")
        return s

    def my_payslips(self, year=None):
        """員工自己的薪資單（已確認的批次）。"""
        if not self.my_emp:
            return []
        return self.db.rows("SELECT s.id, s.gross, s.deduct, s.net, r.ym, r.title, r.pay_date FROM payslips s JOIN payroll_runs r "
                            "ON r.id=s.run_id WHERE s.emp=%s AND r.status>=1" + (" AND r.ym LIKE %s" if year else "") +
                            " ORDER BY r.ym DESC, r.id DESC", (self.my_emp, "%d%%" % year) if year else (self.my_emp,))

    # ================================================================ 確認、發放、關帳
    def confirm_run(self, rid):
        self.need("PAY")
        r = self.payroll_run(rid)
        if r["status"] != 0:
            raise BizError("此批次已確認")
        if not self.db.value("SELECT COUNT(*) FROM payslips WHERE run_id=%s", (rid,)):
            raise BizError("請先計算薪資")
        self.db.exec("UPDATE payroll_runs SET status=1, confirmed_by=%s, confirmed_at=NOW() WHERE id=%s", (self.uid, rid))
        self.log("run_confirm", str(rid))

    def unconfirm_run(self, rid):
        self.need("PAY")
        r = self.payroll_run(rid)
        if r["gl_batch_id"] or r["pay_gl_batch_id"]:
            raise BizError("已拋轉會計，請先到「拋轉紀錄」取消拋轉")
        if self.closed_ym() and r["ym"] <= self.closed_ym():
            raise BizError("此月份已關帳")
        self.db.exec("UPDATE payroll_runs SET status=0 WHERE id=%s", (rid,))
        self.log("run_unconfirm", str(rid))

    def mark_paid(self, rid, paid=True):
        self.need("PAY")
        r = self.payroll_run(rid)
        if r["status"] < 1:
            raise BizError("請先確認薪資")
        if not paid and r["pay_gl_batch_id"]:
            raise BizError("發放分錄已拋轉會計，請先取消拋轉")
        self.db.exec("UPDATE payroll_runs SET status=%s WHERE id=%s", (2 if paid else 1, rid))
        self.log("run_paid" if paid else "run_unpaid", str(rid))

    def close_month(self, ym):
        """關帳：該月出勤、請假、加班、排班不能再修改。"""
        self.need("PAY")
        ym = ym_of(ym)
        r = self.db.row("SELECT status FROM payroll_runs WHERE ym=%s AND kind='M'", (ym,))
        if not r or r["status"] < 1:
            raise BizError("%s 月薪尚未確認，不能關帳" % rocdate.ym_show(ym))
        if ym <= self.closed_ym():
            raise BizError("此月份已關帳")
        self.db.exec("UPDATE company SET closed_ym=%s WHERE id=1", (ym,))
        self.log("close_month", ym)

    def reopen_month(self, ym):
        self.need("SYS")
        ym = ym_of(ym)
        if ym != self.closed_ym():
            raise BizError("只能取消最近一次關帳的月份（%s）" % (rocdate.ym_show(self.closed_ym()) if self.closed_ym() else "無"))
        y, m = int(ym[:4]), int(ym[4:])
        prev = "%04d%02d" % ((y, m - 1) if m > 1 else (y - 1, 12))
        self.db.exec("UPDATE company SET closed_ym=%s WHERE id=1", (prev,))
        self.log("reopen_month", ym)

    # ================================================================ 銀行轉帳與薪資單
    def bank_file(self, rid, path):
        """銀行薪資轉帳明細（CSV：銀行代號、帳號、戶名、金額、員工編號、身分證號）。"""
        self.need("PAY")
        self.need("SAL", 1)
        r = self.payroll_run(rid)
        if r["status"] < 1:
            raise BizError("請先確認薪資")
        rows = self.db.rows("SELECT s.emp, s.name, s.net, e.bank_code, e.bank_account, e.id_no FROM payslips s JOIN "
                            "employees e ON e.code=s.emp WHERE s.run_id=%s AND s.net>0 ORDER BY s.emp", (rid,))
        missing = [x["emp"] + " " + x["name"] for x in rows if not x["bank_account"]]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["銀行代號", "帳號", "戶名", "金額", "員工編號", "身分證號", "轉帳日"])
            for x in rows:
                w.writerow([x["bank_code"], x["bank_account"], x["name"], int(x["net"]), x["emp"], x["id_no"],
                            r["pay_date"].strftime("%Y%m%d")])
        self.log("bank_file", str(rid), path)
        return dict(count=len(rows), total=sum((x["net"] for x in rows), D0), missing=missing)

    def payslip_html(self, sids, path):
        from .printing import payslips_page
        slips = [self.payslip(s) for s in sids]
        with open(path, "w", encoding="utf-8") as f:
            f.write(payslips_page(self.company(), slips))
        return path
