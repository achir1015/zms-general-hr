"""導入說明的數字要和系統實際算出來的一致（改說明數字前先改 hr/example.py 再跑這個測試）。"""
from decimal import Decimal

from hr import adoption, example


def n(s):
    s = str(s).replace(",", "").strip()
    return Decimal(s) if s and s.replace(".", "").isdigit() else None


def table(key, idx=0):
    ts = [b for b in adoption.BY_KEY[key]["blocks"] if b[0] == "table"]
    return ts[idx]


def test_adoption_numbers(biz):
    out = example.build(biz)
    s = example.summary(biz, out)
    slips = s["slips"]
    # 每月薪資表
    _, head, rows = table("adopt_payroll")
    tot = {}
    for r in rows:
        code = r[0].split()[0]
        if code == "合計":
            got = [n(x) for x in r[1:]]
            assert got == [tot[k] for k in ("gross", "labor_emp", "nhi_emp", "pension_self", "deduct", "net", "er")]
            continue
        x = slips[code]
        er = x["labor_er"] + x["occ_er"] + x["fund_er"] + x["nhi_er"] + x["pension_er"]
        vals = dict(gross=x["gross"], labor_emp=x["labor_emp"], nhi_emp=x["nhi_emp"], pension_self=x["pension_self"],
                    deduct=x["deduct"], net=x["net"], er=er)
        for k, v in vals.items():
            tot[k] = tot.get(k, 0) + v
        assert [n(c) for c in r[1:]] == list(vals.values()), code
    assert tot["er"] == s["run"]["employer_cost"]
    # 期初投保核對
    _, _, rows = table("adopt_opening", 0)
    for r in rows[:7]:
        x = slips[r[0].split()[0]]
        assert (n(r[2]), n(r[3]), n(r[4])) == (x["labor_wage"], x["nhi_wage"], x["pension_wage"]), r[0]
        assert n(r[1]) == biz.wage_basis(biz.employee(r[0].split()[0]))
    assert n(rows[7][2]) == slips["E008"]["labor_wage"]
    # 林總經理的保費明細
    _, _, rows = table("adopt_insurance")
    e1 = slips["E001"]
    assert [(n(r[3]), n(r[4])) for r in rows] == [(e1["labor_emp"], e1["labor_er"]), (0, e1["occ_er"]), (0, e1["fund_er"]),
                                                    (e1["nhi_emp"], e1["nhi_er"]), (e1["pension_self"], e1["pension_er"])]
    # 請假加班的薪資影響
    l4 = {ln["item"]: ln["amount"] for ln in biz.payslip(slips["E004"]["id"])["lines"]}
    l6 = {ln["item"]: ln["amount"] for ln in biz.payslip(slips["E006"]["id"])["lines"]}
    l7 = {ln["item"]: ln["amount"] for ln in biz.payslip(slips["E007"]["id"])["lines"]}
    l5 = {ln["item"]: ln["amount"] for ln in biz.payslip(slips["E005"]["id"])["lines"]}
    assert l4["LEAVE_DED"] == 740 and 1000 - l4["ATTEND"] == 24
    assert l7["LEAVE_DED"] == 573 and l7["ATTEND"] == 1000
    assert l6["OT"] == 416 and l6["OCC_WAGE"] == 1247 and l6["ATTEND"] == 1000
    assert l5["LATE_DED"] == 48
    assert biz.balance_left("E002", "A", __import__("datetime").date(2026, 1, 20)) == 88
    assert biz.balance_left("E006", "C", __import__("datetime").date(2026, 1, 30)) == 4
    # 年終
    _, _, rows = table("adopt_bonus")
    bonus = s["bonus"]
    for r in rows[:7]:
        b = bonus[r[0].split()[0]]
        assert (n(r[3]), n(r[4]), n(r[5])) == (b["gross"], b["tax"], b["net"]), r[0]
    assert "E008" not in bonus
    sup = biz.db.value("SELECT premium FROM nhi_employer_sup WHERE ym='202602'")
    assert "估算 %s 元" % "{:,}".format(int(sup)) in "".join(x for b in adoption.BY_KEY["adopt_bonus"]["blocks"]
                                                         for x in (b[1] if isinstance(b[1], list) else [b[1]]))
    # 會計分錄
    _, _, rows = table("adopt_gl_example")
    ref = {"1/31 薪資": "PAY", "1/31 公司負擔保費": "INS", "2/5 發放薪資": "BAN", "1/16 職災醫療費": "OCC"}
    cur = None
    for r in rows:
        if r[0]:
            cur = s["vouchers"][ref[r[0]]]
        acct = r[1].split()[0]
        d = sum(x["debit"] for x in cur["lines"] if x["account"] == acct)
        c = sum(x["credit"] for x in cur["lines"] if x["account"] == acct)
        assert (n(r[2]) or 0, n(r[3]) or 0) == (d, c), (r, d, c)
    assert s["vouchers"]["PAY"]["total"] == s["run"]["gross"] == 328639
    # 說明每一節都可以朗讀
    for sec in adoption.SECTIONS:
        assert len(adoption.spoken(sec)) > 20
