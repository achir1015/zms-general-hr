"""法令計算：投保分級、勞健保與勞退保費、加班費、特休日數、所得稅扣繳、二代健保補充保費。

純計算函式（不碰資料庫）放在模組層，方便測試；LawMixin 負責讀寫「法令參數」與「投保分級表」。
所有比例參數以百分比字串存放（例如 11.5 表示 11.5%）。
"""
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from .core import D0, BizError, date, dec
from .seed import GRADE_NAMES, LAW_NAMES, LAW_PARAMS

H = Decimal(100)


def r0(v) -> Decimal:
    return Decimal(v).quantize(Decimal(1), ROUND_HALF_UP)


# ================================================================ 投保分級
def grade_for(grades, wage, floor_grades=None):
    """依月薪資總額找投保級距：取第一個 ≥ 薪資的級距；超過最高級用最高級。
    floor_grades（部分工時低級距）：薪資低於主表第一級時改用低級距。"""
    wage = Decimal(wage or 0)
    if not grades:
        return D0
    if floor_grades and wage < grades[0]:
        for g in floor_grades:
            if g >= wage:
                return Decimal(g)
        return Decimal(grades[0])
    for g in grades:
        if g >= wage:
            return Decimal(g)
    return Decimal(grades[-1])


def labor_premium(wage, P, employment=True, days=30, labor=True):
    """勞保（普通事故）＋就業保險：(員工, 雇主)。保費＝投保薪資×費率×負擔比例，各自四捨五入後依投保日數按日計。"""
    if not labor or not wage:
        return D0, D0
    wage = Decimal(wage)
    # 普通事故費率 12.5%；有參加就業保險者依就業保險法第 41 條調降 1 個百分點（11.5%）＋就保 1%
    li = P["li_rate"] if employment else P["li_rate"] + P["ei_rate"]
    emp = r0(wage * li / H * P["li_emp"] / H)
    er = r0(wage * li / H * P["li_er"] / H)
    if employment:
        emp += r0(wage * P["ei_rate"] / H * P["li_emp"] / H)
        er += r0(wage * P["ei_rate"] / H * P["li_er"] / H)
    if days < 30:
        emp, er = r0(emp * days / 30), r0(er * days / 30)
    return emp, er


def occ_premium(wage, rate_pct, days=30):
    """職災保險：雇主全額負擔（行業別費率＋上下班災害費率）。"""
    if not wage:
        return D0
    p = r0(Decimal(wage) * Decimal(rate_pct) / H)
    return r0(p * days / 30) if days < 30 else p


def fund_premium(wage, P, days=30):
    """積欠工資墊償基金：勞保投保薪資 × 0.025%，雇主負擔。"""
    if not wage:
        return D0
    p = r0(Decimal(wage) * P["fund_rate"] / H)
    return r0(p * days / 30) if days < 30 else p


def nhi_premium(wage, P, dependents=0):
    """健保：(員工自付含眷屬, 雇主負擔)。員工＝投保金額×5.17%×30%×(1＋眷口，最多 3 口)；
    雇主＝投保金額×5.17%×60%×(1＋平均眷口數)。健保按月計收，月底在保才收當月保費。"""
    if not wage:
        return D0, D0
    wage = Decimal(wage)
    one = r0(wage * P["nhi_rate"] / H * P["nhi_emp"] / H)
    emp = one * (1 + min(int(dependents or 0), 3))
    er = r0(wage * P["nhi_rate"] / H * P["nhi_er"] / H * (1 + P["nhi_avg_dep"]))
    return emp, er


def pension_amount(wage, rate_pct, days=30):
    """勞退提繳：月提繳工資 × 提繳率，未滿一個月按日計。"""
    if not wage or not rate_pct:
        return D0
    p = r0(Decimal(wage) * Decimal(rate_pct) / H)
    return r0(p * days / 30) if days < 30 else p


def nhi_bonus_sup(year_bonus_before, bonus_now, nhi_wage, rate_pct):
    """二代健保（員工）：當年度累計獎金超過當月投保金額 4 倍部分 × 2.11%；以本次給付為上限。"""
    bonus_now = Decimal(bonus_now or 0)
    if bonus_now <= 0 or not nhi_wage:
        return D0, D0
    over = Decimal(year_bonus_before) + bonus_now - Decimal(nhi_wage) * 4
    base = min(bonus_now, over)
    if base <= 0:
        return D0, D0
    base = min(base, Decimal(10000000))
    return r0(base * Decimal(rate_pct) / H), base


# ================================================================ 加班費
OT_DAY = {"W": "平日", "R": "休息日", "N": "國定假日／特休日", "H": "例假（天災、事變、突發事件）", "D": "災害停班日"}


def ot_amount(hours, day_type, hourly):
    """依勞基法第 24、39、40 條計算加班費（月薪制：本薪已含休假日工資，以下為另再加給的金額）。
    平日：前 2 小時 ×4/3、第 3～4 小時 ×5/3
    休息日：前 2 小時 ×4/3、第 3～8 小時 ×5/3、第 9～12 小時 ×8/3（依實際工作時數）
    國定假日、特休日、例假：8 小時內加發 1 日工資（例假另應給補假）；超過 8 小時部分依平日延長工時計算
    回傳 (金額, 計算說明)"""
    h = Decimal(hours or 0)
    hr = Decimal(hourly)
    parts = []

    def seg(n, rate, label):
        if n > 0:
            parts.append((n, rate, label))

    if day_type in ("W", "D"):
        seg(min(h, 2), Decimal(4) / 3, "前2小時×4/3")
        seg(max(h - 2, 0), Decimal(5) / 3, "第3小時起×5/3")
    elif day_type == "R":
        seg(min(h, 2), Decimal(4) / 3, "前2小時×4/3")
        seg(min(max(h - 2, 0), 6), Decimal(5) / 3, "第3～8小時×5/3")
        seg(max(h - 8, 0), Decimal(8) / 3, "第9小時起×8/3")
    elif day_type in ("N", "H"):
        if h > 0:
            parts.append((Decimal(8), Decimal(1), "加發1日工資"))
        seg(min(max(h - 8, 0), 2), Decimal(4) / 3, "超過8小時前2小時×4/3")
        seg(max(h - 10, 0), Decimal(5) / 3, "再超過×5/3")
    else:
        raise BizError("加班日別不正確")
    total = sum((n * rate * hr for n, rate, _ in parts), D0)
    note = "、".join("%s %s小時" % (lbl, _fmt(n)) for n, _, lbl in parts)
    return r0(total), note


def _fmt(n):
    d = Decimal(n)
    if d == d.to_integral_value():
        return "{:,}".format(int(d))
    return format(d.normalize(), "f")


def ot_rate_per_hour(day_type, hourly):
    """換補休時，未休完要折發的「原加班費率」（每小時平均）。用 1 小時的平均費率近似：平日、休息日 4/3。"""
    return (Decimal(hourly) * Decimal(4) / 3).quantize(Decimal("0.01"), ROUND_HALF_UP)


# ================================================================ 特別休假（勞基法第 38 條）
def annual_days_for_years(years_done):
    """服務滿 n 年後的那一年度可休日數（n≥1）。"""
    if years_done < 1:
        return 0
    if years_done == 1:
        return 7
    if years_done == 2:
        return 10
    if years_done < 5:
        return 14
    if years_done < 10:
        return 15
    return min(30, 15 + (years_done - 9))


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    import calendar
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def annual_periods(seniority, until):
    """週年制：[(起, 訖, 日數)]。滿 6 個月 3 日（到滿 1 年前一天）；之後每滿 1 年給一次。"""
    out = []
    if not seniority:
        return out
    s6 = add_months(seniority, 6)
    y1 = add_months(seniority, 12)
    if s6 <= until:
        out.append((s6, y1 - dt.timedelta(days=1), 3))
    n = 1
    while True:
        st = add_months(seniority, 12 * n)
        if st > until:
            break
        out.append((st, add_months(seniority, 12 * (n + 1)) - dt.timedelta(days=1), annual_days_for_years(n)))
        n += 1
    return out


def annual_calendar_year(seniority, year):
    """曆年制：把週年制各期間依落在該曆年的天數比例折算（勞動部函釋的比例計算），回傳日數（到 0.5 日，進位）。"""
    ys, ye = dt.date(year, 1, 1), dt.date(year, 12, 31)
    total = Decimal(0)
    for s, e, days in annual_periods(seniority, ye):
        o1, o2 = max(s, ys), min(e, ye)
        if o1 > o2:
            continue
        span = (e - s).days + 1
        total += Decimal(days) * ((o2 - o1).days + 1) / span
    half = (total * 2).quantize(Decimal(1), rounding="ROUND_CEILING") / 2
    return half


def service_text(seniority, on):
    if not seniority:
        return ""
    m = (on.year - seniority.year) * 12 + on.month - seniority.month - (on.day < seniority.day)
    if m < 0:
        return "未到職"
    return "%d 年 %d 個月" % divmod(m, 12)


# ================================================================ 所得稅
def parse_brackets(s):
    out = []
    for part in (s or "").split(","):
        if ":" in part:
            a, b = part.split(":")
            out.append((Decimal(a.strip() or 0), Decimal(b.strip())))
    return out


def progressive_tax(net, brackets):
    tax, prev = D0, D0
    for cap, rate in brackets:
        if cap == 0 or net <= cap:
            tax += max(net - prev, D0) * rate / H
            return tax
        tax += (cap - prev) * rate / H
        prev = cap
    return tax


def withhold_regular(monthly, dependents, P):
    """固定薪資的扣繳（概算）：月薪資 × 12 － 免稅額 ×（1＋扶養人數）－ 標準扣除額 － 薪資特別扣除額，
    依綜所稅級距算出全年稅額 ÷ 12，取整到 10 元。未達無扶養起扣額不扣。
    正式扣繳以財政部「薪資所得扣繳稅額表」為準（可在員工資料改用固定扣繳率或每月手動調整）。"""
    monthly = Decimal(monthly or 0)
    if monthly < P["tax_threshold"]:
        return D0
    net = monthly * 12 - P["tax_exempt"] * (1 + int(dependents or 0)) - P["tax_std"] - P["tax_salary_ded"]
    if net <= 0:
        return D0
    tax = progressive_tax(net, parse_brackets(P["tax_brackets_s"])) / 12
    return (tax / 10).quantize(Decimal(1), ROUND_HALF_UP) * 10


def withhold_nonregular(amount, P):
    """非固定薪資（獎金等）：單次給付達起扣額按 5% 扣繳。"""
    amount = Decimal(amount or 0)
    if amount < P["tax_threshold"]:
        return D0
    return r0(amount * P["tax_nonreg_rate"] / H)


# ================================================================ 讀寫參數
class LawMixin:
    def law(self, k, on=None):
        on = on or dt.date.today()
        v = self.db.value("SELECT v FROM law_params WHERE k=%s AND eff_date<=%s ORDER BY eff_date DESC LIMIT 1", (k, on))
        if v is None:
            v = self.db.value("SELECT v FROM law_params WHERE k=%s ORDER BY eff_date LIMIT 1", (k,))
        if v is None:
            v = next((x[2] for x in LAW_PARAMS if x[0] == k), "0")
        return v

    def params(self, on=None):
        """計算用的參數字典（數字一律 Decimal；tax_brackets 另存字串）。"""
        on = on or dt.date.today()
        P = {}
        for k, _, _, _ in LAW_PARAMS:
            v = self.law(k, on)
            if k == "tax_brackets":
                P["tax_brackets_s"] = v
            else:
                P[k] = Decimal(v)
        return P

    def law_table(self):
        self.need("INS", 1)
        rows = self.db.rows("SELECT k, eff_date, v FROM law_params ORDER BY k, eff_date DESC")
        notes = {k: (n, d) for k, n, _, d in LAW_PARAMS}
        for r in rows:
            r["name"], r["note"] = notes.get(r["k"], (r["k"], ""))
        order = [x[0] for x in LAW_PARAMS]
        rows.sort(key=lambda r: (order.index(r["k"]) if r["k"] in order else 999, -r["eff_date"].toordinal()))
        return rows

    def save_law(self, k, eff, v):
        self.need("INS")
        if k not in LAW_NAMES:
            raise BizError("參數代號不正確")
        v = (v or "").strip()
        if k != "tax_brackets":
            dec(v)
        else:
            if not parse_brackets(v):
                raise BizError("級距格式：上限:稅率，以逗號分隔，最後一級上限填 0")
        self.db.exec("REPLACE INTO law_params (k, eff_date, v) VALUES (%s, %s, %s)", (k, date(eff), v))
        self.log("law", k, "%s %s" % (eff, v))

    def delete_law(self, k, eff):
        self.need("INS")
        if self.db.value("SELECT COUNT(*) FROM law_params WHERE k=%s", (k,)) <= 1:
            raise BizError("每個參數至少要保留一筆")
        self.db.exec("DELETE FROM law_params WHERE k=%s AND eff_date=%s", (k, date(eff)))

    def grade_dates(self, kind):
        return [r["eff_date"] for r in self.db.rows("SELECT DISTINCT eff_date FROM ins_grades WHERE kind=%s ORDER BY "
                                                     "eff_date DESC", (kind,))]

    def grades(self, kind, on=None):
        on = on or dt.date.today()
        eff = self.db.value("SELECT MAX(eff_date) FROM ins_grades WHERE kind=%s AND eff_date<=%s", (kind, on)) or \
            self.db.value("SELECT MIN(eff_date) FROM ins_grades WHERE kind=%s", (kind,))
        if not eff:
            return []
        return [Decimal(r["amount"]) for r in self.db.rows("SELECT amount FROM ins_grades WHERE kind=%s AND eff_date=%s "
                                                             "ORDER BY amount", (kind, eff))]

    def grade_table(self, kind):
        """畫面用：(各級金額, 生效日清單)。"""
        self.need("INS", 1)
        return self.grades(kind), self.grade_dates(kind)

    def save_grades(self, kind, eff, amounts):
        """以新的生效日儲存一整份分級表（例如明年基本工資調整後）。amounts 可以是文字（逗號或換行分隔）。"""
        self.need("INS")
        if kind not in GRADE_NAMES:
            raise BizError("分級表種類不正確")
        if isinstance(amounts, str):
            t = amounts.replace("，", ",").replace("、", "\n")
            # 有換行：一行一級（金額內的千分位逗號拿掉）；沒有換行：以逗號分隔
            parts = t.splitlines() if "\n" in t else t.split(",")
            amounts = [x.replace(",", "").strip() for x in parts if x.strip()]
        vals = sorted({int(dec(a)) for a in amounts})
        if not vals or vals[0] <= 0:
            raise BizError("分級表至少要有一級，且金額要大於 0")
        e = date(eff)
        with self.db.transaction():
            self.db.exec("DELETE FROM ins_grades WHERE kind=%s AND eff_date=%s", (kind, e))
            self.db.exec_many("INSERT INTO ins_grades (kind, eff_date, amount) VALUES (%s, %s, %s)",
                              [(kind, e, v) for v in vals])
        self.log("grades", kind, "%s 共 %d 級" % (e, len(vals)))

    def insured_wages(self, emp, wage_basis, on):
        """依員工設定與分級表求出 (勞保, 職災, 健保, 勞退) 投保金額；員工資料有手動設定時用手動值。"""
        li = self.grades("LI", on)
        part_time = emp.get("emp_type") in ("H", "P")
        labor = Decimal(emp.get("labor_wage") or 0) or grade_for(li, wage_basis, self.grades("LIP", on) if part_time else None)
        if labor > li[-1]:
            labor = li[-1]
        occ_g = self.grades("OC", on)
        occ = grade_for(occ_g, max(Decimal(wage_basis), labor), self.grades("LIP", on) if part_time else None)             if emp.get("occ_ins") else D0
        if emp.get("labor_wage") and Decimal(emp["labor_wage"]) > occ:
            occ = grade_for(occ_g, emp["labor_wage"])
        nhi = Decimal(emp.get("nhi_wage") or 0) or grade_for(self.grades("NHI", on), wage_basis)
        pen = Decimal(emp.get("pension_wage") or 0) or grade_for(self.grades("PEN", on), wage_basis)
        return (labor if emp.get("labor_ins") or emp.get("employment_ins") else D0, occ,
                nhi if emp.get("nhi") else D0, pen if emp.get("pension") or emp.get("pension_self") else D0)

    def premium_preview(self, emp_code, on=None):
        """員工資料畫面用：依目前薪資試算每月保費。"""
        on = on or dt.date.today()
        if emp_code != self.my_emp:
            self.need("SAL", 1)
        e = self.employee(emp_code)
        P = self.params(on)
        basis = self.wage_basis(e)
        lw, ow, nw, pw = self.insured_wages(e, basis, on)
        lemp, ler = labor_premium(lw, P, bool(e["employment_ins"]), labor=bool(e["labor_ins"] or e["employment_ins"]))
        nemp, ner = nhi_premium(nw, P, e["nhi_dependents"])
        comp = self.company()
        return dict(basis=basis, labor_wage=lw, occ_wage=ow, nhi_wage=nw, pension_wage=pw, labor_emp=lemp,
                    labor_er=ler, occ_er=occ_premium(ow, comp.get("occ_rate") or 0), fund_er=fund_premium(lw, P),
                    nhi_emp=nemp, nhi_er=ner,
                    pension_er=pension_amount(pw, P["pension_er"]) if e["pension"] else D0,
                    pension_self=pension_amount(pw, e["pension_self"]))
