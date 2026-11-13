"""請假、加班、特休與補休額度、年度結算（折發工資或遞延）。

* 請假時數依員工當天的班別計算（扣除休息時間）；產假、育嬰留停等「依曆計算」的假別以日 × 8 小時計。
* 特休依年資自動產生額度（週年制或曆年制），補休由加班換休產生；請特休、補休時依「先到期先用」扣抵。
* 年度終結（或離職）未休完：特休可「折發工資」或經勞雇協商「遞延一年」；補休依原加班費率折發。
  折發金額會進入指定月份的薪資（特休未休工資、補休未休折發），會計拋轉時記為薪資費用。
"""
import datetime as dt
from decimal import ROUND_DOWN, Decimal

from . import laws
from .core import D0, BizError, date, hhmm, yuan

STATUS = {0: "待審核", 1: "核准", 9: "駁回／撤銷"}
HOURS_DAY = Decimal(8)


def _dt(v, default_time="09:00"):
    """可以傳 datetime，或「115/11/13 09:00」文字。"""
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        h, m = (int(x) for x in default_time.split(":"))
        return dt.datetime(v.year, v.month, v.day, h, m)
    s = (v or "").strip()
    parts = s.split()
    d = date(parts[0])
    t = hhmm(parts[1]) if len(parts) > 1 else default_time
    h, m = (int(x) for x in t.split(":"))
    if h == 24:
        return dt.datetime(d.year, d.month, d.day) + dt.timedelta(days=1)
    return dt.datetime(d.year, d.month, d.day, h, m)


class LeaveMixin:
    # ================================================================ 假別
    def leave_types(self, active_only=True):
        return self.db.rows("SELECT * FROM leave_types%s ORDER BY sort, code" % (" WHERE active=1" if active_only else ""))

    def leave_type(self, code):
        t = self.db.row("SELECT * FROM leave_types WHERE code=%s", (code,))
        if not t:
            raise BizError("假別 %s 不存在" % code)
        return t

    # ================================================================ 請假
    def leave_hours(self, emp, ltype, start, end):
        """試算請假時數（依班表）。回傳 (時數, 起, 訖, 說明)。"""
        e = self.employee(emp)
        t = self.leave_type(ltype)
        s, en = _dt(start, "00:00" if t["calendar_days"] else "09:00"), _dt(end, "23:59" if t["calendar_days"] else "18:00")
        if t["calendar_days"]:
            s = dt.datetime.combine(s.date(), dt.time())
            en = dt.datetime.combine(en.date(), dt.time(23, 59))
            days = (en.date() - s.date()).days + 1
            if days <= 0:
                raise BizError("結束日不能早於開始日")
            return Decimal(days) * HOURS_DAY, s, en, "依曆計算 %d 日" % days
        if en <= s:
            raise BizError("請假結束時間要晚於開始時間")
        if (en - s).days > 62:
            raise BizError("一次請假最長 62 天，請分開申請")
        sch = self.schedules([e], s.date() - dt.timedelta(days=1), en.date())
        mins = 0
        work_days = 0
        for (code, d), sc in sch.items():
            m = sc.overlap(s, en)
            if m:
                mins += m
                work_days += 1
        if mins <= 0:
            raise BizError("請假期間沒有排班的工作時間（休息日、例假、國定假日不用請假）")
        hrs = (Decimal(mins) / 60).quantize(Decimal("0.01"))
        return hrs, s, en, "共 %d 個工作日、%s 小時" % (work_days, laws._fmt(hrs))

    def _may_see(self, emp):
        if emp != self.my_emp and not (self.can("LEV", 1) or self.is_manager_of(emp)):
            self.need("LEV", 1)

    def leave_hours_check(self, emp, ltype, start, end):
        """請假視窗試算用。回傳 (時數, 說明)。"""
        self._may_see(emp)
        h, _, _, txt = self.leave_hours(emp, ltype, start, end)
        return h, txt

    def balance_info(self, emp, kind):
        self._may_see(emp)
        return self.balance_left(emp, kind, dt.date.today())

    def request_leave(self, emp, ltype, start, end, reason="", proxy="", approve=False, occ_case=0, disaster=0):
        emp = emp or self.my_emp
        if emp != self.my_emp:
            self.need("LEV")
        e = self.employee(emp)
        t = self.leave_type(ltype)
        if not t["active"]:
            raise BizError("假別「%s」已停用" % t["name"])
        if t["gender"] and t["gender"] != e["gender"]:
            raise BizError("「%s」限%s員工申請" % (t["name"], "女性" if t["gender"] == "F" else "男性"))
        hrs, s, en, _ = self.leave_hours(emp, ltype, start, end)
        self.check_open(s.date(), "請假")
        if hrs < Decimal(t["min_hours"]) and not t["calendar_days"]:
            raise BizError("「%s」最小請假單位是 %s 小時" % (t["name"], laws._fmt(Decimal(t["min_hours"]))))
        if self.db.value("SELECT 1 FROM leave_requests WHERE emp=%s AND status IN (0,1) AND start_at<%s AND end_at>%s",
                         (emp, en, s)):
            raise BizError("這段時間已經有請假紀錄")
        self._check_quota(e, t, s, hrs)
        if t["balance"]:
            left = self.balance_left(emp, t["balance"], s.date())
            if hrs > left:
                raise BizError("%s剩餘 %s 小時，不夠請 %s 小時" % ("特休" if t["balance"] == "A" else "補休",
                                                           laws._fmt(left), laws._fmt(hrs)))
        st = 1 if approve and (self.can("LEV") or self.is_manager_of(emp)) else 0
        rid = self.db.exec("INSERT INTO leave_requests (emp, ltype, start_at, end_at, hours, reason, proxy, status, approver, "
                           "approved_at, occ_case, disaster, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                           "%s, %s, %s)", (emp, ltype, s, en, hrs, (reason or "")[:200], proxy or "", st,
                                           self.uid if st else "", dt.datetime.now() if st else None, occ_case or 0,
                                           disaster or 0, self.uid))
        self.log("leave_new", "%s#%s" % (emp, rid), "%s %s %s" % (t["name"], s, hrs))
        return rid

    def _check_quota(self, e, t, s, hrs, exclude_id=0):
        if not t["quota_days"]:
            return
        y = s.year
        codes = [t["code"]]
        if t["code"] in ("PERSONAL", "FAMILY"):
            codes = ["PERSONAL", "FAMILY"]
            quota = Decimal(14)
        elif t["code"] in ("SICK",):
            quota = Decimal(t["quota_days"])
        else:
            quota = Decimal(t["quota_days"])
        used = self.db.value("SELECT COALESCE(SUM(hours), 0) FROM leave_requests WHERE emp=%%s AND status IN (0,1) AND "
                             "YEAR(start_at)=%%s AND ltype IN (%s) AND id<>%%s" % ",".join(["%s"] * len(codes)),
                             (e["code"], y, *codes, exclude_id)) or 0
        if t["code"] == "MENS":
            m_used = self.db.value("SELECT COALESCE(SUM(hours), 0) FROM leave_requests WHERE emp=%s AND status IN (0,1) AND "
                                   "ltype='MENS' AND YEAR(start_at)=%s AND MONTH(start_at)=%s AND id<>%s",
                                   (e["code"], y, s.month, exclude_id)) or 0
            if Decimal(m_used) + hrs > HOURS_DAY:
                raise BizError("生理假每月以 1 日為限")
            return
        if Decimal(used) + hrs > quota * HOURS_DAY:
            raise BizError("「%s」今年已申請 %s 小時，加上這次會超過上限 %s 日" %
                           (t["name"], laws._fmt(Decimal(used)), laws._fmt(quota)))

    def leave_requests(self, d1, d2, emp="", status=None, dept=""):
        if emp != self.my_emp or not emp:
            if not (self.can("LEV", 1) or self.my_emp):
                self.need("LEV", 1)
        sql = ("SELECT r.*, e.name, e.dept, t.name AS lname, t.pay_ratio, t.color FROM leave_requests r JOIN employees e ON "
               "e.code=r.emp JOIN leave_types t ON t.code=r.ltype WHERE r.start_at<=%s AND r.end_at>=%s")
        args = [dt.datetime.combine(date(d2), dt.time(23, 59, 59)), dt.datetime.combine(date(d1), dt.time())]
        if emp:
            sql += " AND r.emp=%s"
            args.append(emp)
        elif not self.can("LEV", 1):
            # 部門主管看自己部門
            sql += " AND (r.emp=%s OR e.dept IN (SELECT code FROM departments WHERE manager=%s))"
            args += [self.my_emp, self.my_emp]
        if status is not None:
            sql += " AND r.status=%s"
            args.append(status)
        if dept:
            sql += " AND e.dept=%s"
            args.append(dept)
        rows = self.db.rows(sql + " ORDER BY r.start_at DESC", tuple(args))
        for r in rows:
            r["status_name"] = STATUS.get(r["status"], "")
        return rows

    def approve_leave(self, rid, ok=True, note=""):
        r = self.db.row("SELECT * FROM leave_requests WHERE id=%s", (rid,))
        if not r:
            raise BizError("請假單不存在")
        if not (self.can("LEV") or self.is_manager_of(r["emp"])):
            self.need("LEV")
        if r["emp"] == self.my_emp and not self.can("LEV"):
            raise BizError("不能審核自己的請假")
        self.check_open(r["start_at"].date(), "請假")
        if ok:
            t = self.leave_type(r["ltype"])
            if t["balance"]:
                left = self.balance_left(r["emp"], t["balance"], r["start_at"].date(), exclude_id=rid)
                if Decimal(r["hours"]) > left:
                    raise BizError("額度不足：剩餘 %s 小時" % laws._fmt(left))
        self.db.exec("UPDATE leave_requests SET status=%s, approver=%s, approved_at=NOW(), reason=CONCAT(reason, %s) "
                     "WHERE id=%s", (1 if ok else 9, self.uid, (" ／審核：" + note) if note else "", rid))
        self.log("leave_" + ("ok" if ok else "reject"), str(rid))

    def cancel_leave(self, rid):
        r = self.db.row("SELECT * FROM leave_requests WHERE id=%s", (rid,))
        if not r:
            raise BizError("請假單不存在")
        if not self.can("LEV"):
            if r["emp"] != self.my_emp or r["status"] != 0:
                raise BizError("已審核的請假要請人資撤銷")
        self.check_open(r["start_at"].date(), "請假")
        self.db.exec("UPDATE leave_requests SET status=9, reason=CONCAT(reason, ' ／撤銷') WHERE id=%s", (rid,))
        self.log("leave_cancel", str(rid))

    # ================================================================ 加班
    def ot_hours_of(self, start, end):
        comp = self.company()
        unit = int(comp.get("ot_round_min") or 30) or 1
        mins = int((end - start).total_seconds() // 60)
        mins = mins // unit * unit
        return (Decimal(mins) / 60).quantize(Decimal("0.01"))

    def ot_day_type(self, emp, d):
        e = self.employee(emp)
        s = self.schedules([e], d, d)[(emp, d)]
        if self.db.value("SELECT 1 FROM leave_requests WHERE emp=%s AND status=1 AND ltype='ANNUAL' AND DATE(start_at)<=%s "
                         "AND DATE(end_at)>=%s", (emp, d, d)):
            return "N"
        return {"W": "W", "R": "R", "H": "H", "N": "N"}.get(s.day_type, "W")

    def hourly_rate(self, e, on=None):
        """平日每小時工資額＝（本薪＋經常性給與）÷ 30 ÷ 8；時薪人員用時薪。"""
        if e.get("emp_type") == "H":
            return Decimal(self.salary_on(e, on or dt.date.today())[1] or e["hourly_wage"] or 0)
        base, _ = self.salary_on(e, on or dt.date.today())
        basis = self.wage_basis(dict(e, base_salary=base))
        return (basis / 30 / 8).quantize(Decimal("0.0001"))

    def request_overtime(self, emp, d, start, end, comp="P", reason="", day_type=None, approve=False):
        emp = emp or self.my_emp
        if emp != self.my_emp:
            self.need("LEV")
        e = self.employee(emp)
        d = date(d)
        self.check_open(d, "加班")
        s = start if isinstance(start, dt.datetime) else _dt("%s %s" % (d.isoformat(), hhmm(start)))
        en = end if isinstance(end, dt.datetime) else _dt("%s %s" % (d.isoformat(), hhmm(end)))
        if en <= s:
            en += dt.timedelta(days=1)
        hrs = self.ot_hours_of(s, en)
        if hrs <= 0:
            raise BizError("加班時數不足一個計算單位")
        if hrs > 12:
            raise BizError("一日工作時間連同加班不得超過 12 小時")
        dtp = day_type or self.ot_day_type(emp, d)
        if dtp not in laws.OT_DAY:
            raise BizError("加班日別不正確")
        if comp not in ("P", "C"):
            raise BizError("請選擇加班費或補休")
        if self.db.value("SELECT 1 FROM overtime WHERE emp=%s AND status IN (0,1) AND start_at<%s AND end_at>%s",
                         (emp, en, s)):
            raise BizError("這段時間已經有加班紀錄")
        if dtp in ("W", "R", "D"):
            P = self.params(d)
            used = self.db.value("SELECT COALESCE(SUM(hours), 0) FROM overtime WHERE emp=%s AND status IN (0,1) AND "
                                 "day_type IN ('W','R','D') AND YEAR(d)=%s AND MONTH(d)=%s", (emp, d.year, d.month)) or 0
            if Decimal(used) + hrs > P["ot_month_max"]:
                raise BizError("本月延長工時已 %s 小時，加上這次會超過每月上限 %s 小時（勞基法第 32 條）" %
                               (laws._fmt(Decimal(used)), laws._fmt(P["ot_month_max"])))
        amt, note = laws.ot_amount(hrs, dtp, self.hourly_rate(e, d))
        st = 1 if approve and (self.can("LEV") or self.is_manager_of(emp)) else 0
        oid = self.db.exec("INSERT INTO overtime (emp, d, start_at, end_at, hours, day_type, comp, reason, status, approver, "
                           "approved_at, amount, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                           (emp, d, s, en, hrs, dtp, comp, (reason or "")[:200], st, self.uid if st else "",
                            dt.datetime.now() if st else None, amt, self.uid))
        if st and comp == "C":
            self._comp_grant(oid)
        self.log("ot_new", "%s#%s" % (emp, oid), "%s %s小時 %s" % (d, hrs, note))
        return oid

    def _comp_grant(self, oid):
        o = self.db.row("SELECT * FROM overtime WHERE id=%s", (oid,))
        if o["grant_id"]:
            return
        rate = (Decimal(o["amount"]) / Decimal(o["hours"])).quantize(Decimal("0.01")) if o["hours"] else D0
        gid = self.db.exec("INSERT INTO leave_grants (emp, kind, start_d, end_d, hours, pay_rate, source, ref_id, memo) VALUES "
                           "(%s, 'C', %s, %s, %s, %s, 'ot', %s, %s)",
                           (o["emp"], o["d"], dt.date(o["d"].year, 12, 31), o["hours"], rate, oid,
                            "%s 加班換補休" % o["d"].strftime("%m/%d")))
        self.db.exec("UPDATE overtime SET grant_id=%s WHERE id=%s", (gid, oid))

    def overtime_list(self, d1, d2, emp="", status=None, dept=""):
        if emp != self.my_emp or not emp:
            if not (self.can("LEV", 1) or self.my_emp):
                self.need("LEV", 1)
        sql = ("SELECT o.*, e.name, e.dept FROM overtime o JOIN employees e ON e.code=o.emp WHERE o.d BETWEEN %s AND %s")
        args = [date(d1), date(d2)]
        if emp:
            sql += " AND o.emp=%s"
            args.append(emp)
        elif not self.can("LEV", 1):
            sql += " AND (o.emp=%s OR e.dept IN (SELECT code FROM departments WHERE manager=%s))"
            args += [self.my_emp, self.my_emp]
        if status is not None:
            sql += " AND o.status=%s"
            args.append(status)
        if dept:
            sql += " AND e.dept=%s"
            args.append(dept)
        rows = self.db.rows(sql + " ORDER BY o.d DESC, o.start_at DESC", tuple(args))
        for r in rows:
            r["status_name"] = STATUS.get(r["status"], "")
            r["day_name"] = laws.OT_DAY.get(r["day_type"], "")
            r["comp_name"] = "補休" if r["comp"] == "C" else "加班費"
            if not self.see_salary and r["emp"] != self.my_emp:
                r["amount"] = None
        return rows

    def approve_overtime(self, oid, ok=True):
        o = self.db.row("SELECT * FROM overtime WHERE id=%s", (oid,))
        if not o:
            raise BizError("加班單不存在")
        if not (self.can("LEV") or self.is_manager_of(o["emp"])):
            self.need("LEV")
        if o["emp"] == self.my_emp and not self.can("LEV"):
            raise BizError("不能審核自己的加班")
        self.check_open(o["d"], "加班")
        with self.db.transaction():
            self.db.exec("UPDATE overtime SET status=%s, approver=%s, approved_at=NOW() WHERE id=%s",
                         (1 if ok else 9, self.uid, oid))
            if ok and o["comp"] == "C":
                self._comp_grant(oid)
            if not ok and o["grant_id"]:
                self.db.exec("DELETE FROM leave_grants WHERE id=%s", (o["grant_id"],))
                self.db.exec("UPDATE overtime SET grant_id=0 WHERE id=%s", (oid,))
        self.log("ot_" + ("ok" if ok else "reject"), str(oid))

    # ================================================================ 額度
    def grant_annual(self, year, emps=None):
        """依年資產生特休額度（已產生的不重複）。回傳新增筆數。"""
        self.need("LEV")
        comp = self.company()
        system = comp.get("leave_system") or "A"
        ys, ye = dt.date(year, 1, 1), dt.date(year, 12, 31)
        rows = self.active_employees(ys, ye)
        if emps:
            rows = [e for e in rows if e["code"] in emps]
        n = 0
        for e in rows:
            sen = e["seniority_date"] or e["hire_date"]
            if not sen:
                continue
            if system == "C":
                days = laws.annual_calendar_year(sen, year)
                if days <= 0 or self.db.value("SELECT 1 FROM leave_grants WHERE emp=%s AND kind='A' AND source='law' AND "
                                              "start_d=%s", (e["code"], ys)):
                    continue
                self.db.exec("INSERT INTO leave_grants (emp, kind, start_d, end_d, hours, source, memo) VALUES "
                             "(%s, 'A', %s, %s, %s, 'law', %s)",
                             (e["code"], ys, ye, days * HOURS_DAY, "%d 年度特休 %s 日（曆年制）" % (year, laws._fmt(days))))
                n += 1
            else:
                for s, en, days in laws.annual_periods(sen, ye):
                    if s.year != year or days <= 0:
                        continue
                    if e["leave_date"] and s > e["leave_date"]:
                        continue
                    if self.db.value("SELECT 1 FROM leave_grants WHERE emp=%s AND kind='A' AND source='law' AND start_d=%s",
                                     (e["code"], s)):
                        continue
                    self.db.exec("INSERT INTO leave_grants (emp, kind, start_d, end_d, hours, source, memo) VALUES "
                                 "(%s, 'A', %s, %s, %s, 'law', %s)",
                                 (e["code"], s, en, Decimal(days) * HOURS_DAY,
                                  "年資 %s 特休 %d 日" % (laws.service_text(sen, s), days)))
                    n += 1
        self.log("grant_annual", str(year), "%d 筆" % n)
        return n

    def add_grant(self, emp, kind, start, end, hours, memo=""):
        self.need("LEV")
        if kind not in ("A", "C"):
            raise BizError("額度種類不正確")
        s, e = date(start), date(end)
        if e < s:
            raise BizError("有效期限不正確")
        h = Decimal(str(hours or 0))
        if h <= 0:
            raise BizError("時數要大於 0")
        self.employee(emp)
        gid = self.db.exec("INSERT INTO leave_grants (emp, kind, start_d, end_d, hours, source, memo) VALUES "
                           "(%s, %s, %s, %s, %s, 'manual', %s)", (emp, kind, s, e, h, (memo or "手動調整")[:100]))
        self.log("grant_add", emp, "%s %s %s" % (kind, h, memo))
        return gid

    def delete_grant(self, gid):
        self.need("LEV")
        g = self.db.row("SELECT * FROM leave_grants WHERE id=%s", (gid,))
        if not g:
            return
        if g["settled"] in ("P", "D"):
            raise BizError("已結算的額度不能刪除")
        if g["source"] == "ot":
            raise BizError("加班換補休的額度請到加班單駁回")
        self.db.exec("DELETE FROM leave_grants WHERE id=%s", (gid,))

    def _allocate(self, emp, kind, exclude_id=0):
        """把請假依「先到期先用」分配到各額度；回傳 (grants, 未分配到的請假時數)。"""
        grants = self.db.rows("SELECT * FROM leave_grants WHERE emp=%s AND kind=%s ORDER BY end_d, start_d, id", (emp, kind))
        for g in grants:
            g["used"] = D0
        ltypes = [r["code"] for r in self.db.rows("SELECT code FROM leave_types WHERE balance=%s", (kind,))]
        if not ltypes:
            return grants, D0
        reqs = self.db.rows("SELECT id, start_at, hours FROM leave_requests WHERE emp=%%s AND status IN (0,1) AND id<>%%s "
                            "AND ltype IN (%s) ORDER BY start_at" % ",".join(["%s"] * len(ltypes)),
                            (emp, exclude_id, *ltypes))
        short = D0
        for r in reqs:
            need = Decimal(r["hours"])
            d = r["start_at"].date()
            for g in grants:
                if need <= 0:
                    break
                if not (g["start_d"] <= d <= g["end_d"]):
                    continue
                cap = Decimal(g["hours"]) - Decimal(g["settled_hours"] or 0) - g["used"]
                if g["settled"] in ("P", "D", "X"):
                    cap = Decimal(g["hours"]) - Decimal(g["settled_hours"] or 0) - g["used"]
                take = min(cap, need)
                if take > 0:
                    g["used"] += take
                    need -= take
            short += max(need, D0)
        for g in grants:
            g["left"] = Decimal(g["hours"]) - g["used"] - Decimal(g["settled_hours"] or 0)
        return grants, short

    def balance_left(self, emp, kind, on, exclude_id=0):
        grants, _ = self._allocate(emp, kind, exclude_id)
        return sum((g["left"] for g in grants if g["start_d"] <= on <= g["end_d"] and not g["settled"]), D0)

    def balances(self, emp="", year=None, dept=""):
        """額度明細（每筆額度一列）。"""
        if emp != self.my_emp or not emp:
            self.need("LEV", 1)
        emps = [emp] if emp else [r["code"] for r in self.db.rows(
            "SELECT code FROM employees WHERE status<>'Q'" + (" AND dept=%s" if dept else "") + " ORDER BY code",
            (dept,) if dept else ())]
        names = {r["code"]: r["name"] for r in self.db.rows("SELECT code, name FROM employees")}
        out = []
        for c in emps:
            for kind in ("A", "C"):
                grants, _ = self._allocate(c, kind)
                for g in grants:
                    if year and not (g["start_d"].year <= year <= g["end_d"].year):
                        continue
                    g["name"] = names.get(c, "")
                    g["kind_name"] = "特休" if kind == "A" else "補休"
                    g["state"] = {"": "使用中" if g["end_d"] >= dt.date.today() else "已到期未結算", "P": "已折發",
                                  "D": "已遞延", "X": "已休完"}[g["settled"]]
                    out.append(g)
        return out

    def balance_summary(self, emp, on=None):
        on = on or dt.date.today()
        return dict(annual=self.balance_left(emp, "A", on), comp=self.balance_left(emp, "C", on))

    def settle_grants(self, emps, as_of, method, ym, kind="A"):
        """年度終結（或離職）結算：到期（或離職日前）仍有剩餘的額度
        method：P 折發工資（寫入 ym 月薪資）、D 遞延一年（僅特休）。回傳 [(員工, 時數, 金額)]。"""
        self.need("LEV")
        self.need("PAY")
        as_of = date(as_of)
        if method not in ("P", "D"):
            raise BizError("請選擇折發工資或遞延")
        if method == "D" and kind != "A":
            raise BizError("補休未休完依法應折發工資，不能遞延")
        if len(ym) != 6:
            raise BizError("請指定折發的薪資月份")
        out = []
        with self.db.transaction():
            for emp in emps:
                e = self.employee(emp)
                leaving = e["leave_date"] and e["leave_date"] <= as_of
                grants, _ = self._allocate(emp, kind)
                for g in grants:
                    if g["settled"] or g["left"] <= 0:
                        if not g["settled"] and g["left"] <= 0 and g["end_d"] <= as_of:
                            self.db.exec("UPDATE leave_grants SET settled='X' WHERE id=%s", (g["id"],))
                        continue
                    if g["end_d"] > as_of and not leaving:
                        continue
                    hrs = g["left"]
                    if method == "D" and not leaving:
                        ns = g["end_d"] + dt.timedelta(days=1)
                        self.db.exec("INSERT INTO leave_grants (emp, kind, start_d, end_d, hours, source, ref_id, memo) "
                                     "VALUES (%s, 'A', %s, %s, %s, 'defer', %s, %s)",
                                     (emp, ns, laws.add_months(ns, 12) - dt.timedelta(days=1), hrs, g["id"],
                                      "遞延自 %s 到期的特休" % g["end_d"]))
                        self.db.exec("UPDATE leave_grants SET settled='D', settled_ym=%s, settled_hours=%s WHERE id=%s",
                                     (ym, hrs, g["id"]))
                        out.append((emp, hrs, D0))
                        continue
                    if kind == "A":
                        daily = self.wage_basis(e) / 30
                        amt = yuan(daily * hrs / HOURS_DAY)
                        item = "LEAVE_PAY"
                    else:
                        amt = yuan(Decimal(g["pay_rate"]) * hrs)
                        item = "COMP_PAY"
                    self.db.exec("INSERT INTO pay_inputs (ym, run_kind, emp, item, amount, note, source, ref_id, created_by) "
                                 "VALUES (%s, 'M', %s, %s, %s, %s, 'leave', %s, %s)",
                                 (ym, emp, item, amt, "%s 未休 %s 小時" % ("特休" if kind == "A" else "補休", laws._fmt(hrs)),
                                  g["id"], self.uid))
                    self.db.exec("UPDATE leave_grants SET settled='P', settled_ym=%s, settled_hours=%s, settled_amount=%s "
                                 "WHERE id=%s", (ym, hrs, amt, g["id"]))
                    out.append((emp, hrs, amt))
        self.log("settle_" + kind, ym, "%s %d 筆" % (method, len(out)))
        return out

    def unused_leave_liability(self, as_of):
        """未休特休估列（應付休假給付）：剩餘時數 × 日薪 ÷ 8。"""
        self.need("LEV", 1)
        as_of = date(as_of)
        out = []
        for e in self.active_employees(as_of, as_of):
            left = self.balance_left(e["code"], "A", as_of)
            if left <= 0:
                continue
            daily = self.wage_basis(e) / 30
            out.append(dict(emp=e["code"], name=e["name"], dept=e["dept"], hours=left,
                            daily=daily.quantize(Decimal("0.01"), ROUND_DOWN), amount=yuan(daily * left / HOURS_DAY)))
        return out

    # ================================================================ 員工自助（GPS 打卡網頁、手機）
    def my_balance(self):
        if not self.my_emp:
            raise BizError("此帳號沒有對應員工")
        return self.balance_summary(self.my_emp)

    def my_profile(self):
        if not self.my_emp:
            return None
        e = self.employee(self.my_emp)
        return dict(code=e["code"], name=e["name"], dept=e["dept_name"] or "", title=e["title"], gender=e["gender"])

    def company_brief(self):
        return dict(name=self.company().get("name") or "")

    def leave_hours_self(self, ltype, start, end):
        if not self.my_emp:
            raise BizError("此帳號沒有對應員工")
        h, s, e, txt = self.leave_hours(self.my_emp, ltype, start, end)
        return dict(hours=h, text=txt)
