"""服務層測試：法令計算、員工、排班、打卡、請假加班、薪資、會計拋轉、班表匯出入。"""
import datetime as dt
import json
import os
import zipfile
from decimal import Decimal as D

import pytest

from hr import laws
from hr.core import BizError
from hr.seed import GRADES, LIP


def R(x):
    """四捨五入到元（與系統相同，0.5 進位）。"""
    return laws.r0(D(str(x)) if isinstance(x, float) else x)


# ---------------------------------------------------------------- 純計算
def test_grade_tables():
    assert len(GRADES["LI"]) == 11 and GRADES["LI"][0] == 29500 and GRADES["LI"][-1] == 45800
    assert len(GRADES["NHI"]) == 58 and GRADES["NHI"][-1] == 313000
    assert len(GRADES["PEN"]) == 62 and GRADES["PEN"][24] == 29500 and GRADES["PEN"][-1] == 150000
    assert GRADES["OC"][-1] == 72800 and len(GRADES["OC"]) == 21
    assert laws.grade_for(GRADES["LI"], 45000) == 45800
    assert laws.grade_for(GRADES["LI"], 80000) == 45800                 # 超過最高級
    assert laws.grade_for(GRADES["LI"], 20000, LIP) == 20008            # 部分工時低級距
    assert laws.grade_for(GRADES["LI"], 20000) == 29500


P = dict(li_rate=D("11.5"), ei_rate=D(1), li_emp=D(20), li_er=D(70), fund_rate=D("0.025"), nhi_rate=D("5.17"),
         nhi_emp=D(30), nhi_er=D(60), nhi_avg_dep=D("0.56"), nhi_sup_rate=D("2.11"), tax_exempt=D(101000),
         tax_std=D(136000), tax_salary_ded=D(227000), tax_brackets_s="610000:5,1380000:12,2770000:20,5190000:30,0:40",
         tax_threshold=D(90501), tax_nonreg_rate=D(5))


def test_premiums_match_official_tables():
    # 勞保局保險費分擔金額表：投保薪資 45,800 → 個人 1,145、單位 4,008（含就保）
    assert laws.labor_premium(45800, P) == (1145, 4008)
    # 29,500 → 個人 738
    assert laws.labor_premium(29500, P)[0] == 738
    assert laws.labor_premium(29500, P, employment=False)[0] == 738          # 無就保：普通事故 12.5%
    # 健保署負擔金額表：45,800 → 本人 710、單位 2,216；眷屬 1 口 1,420
    assert laws.nhi_premium(45800, P, 0) == (710, 2216)
    assert laws.nhi_premium(45800, P, 1)[0] == 1420
    assert laws.nhi_premium(45800, P, 5)[0] == 710 * 4                  # 眷屬最多計 3 口
    assert laws.pension_amount(45800, 6) == 2748
    assert laws.labor_premium(45800, P, days=15) == (573, 2004)          # 按日計
    assert laws.fund_premium(45800, P) == 11


def test_overtime_rates():
    hr = D(200)
    assert laws.ot_amount(2, "W", hr)[0] == 533                          # 2×200×4/3
    assert laws.ot_amount(3, "W", hr)[0] == 867                          # 533.33＋333.33
    assert laws.ot_amount(1, "R", hr)[0] == 267                          # 休息日依實際時數
    assert laws.ot_amount(9, "R", hr)[0] == R(2 * 200 * 4 / 3 + 6 * 200 * 5 / 3 + 1 * 200 * 8 / 3)
    assert laws.ot_amount(4, "N", hr)[0] == 1600                         # 國定假日 8 小時內加發 1 日
    assert laws.ot_amount(10, "N", hr)[0] == 1600 + 533


def test_annual_leave_days():
    s = dt.date(2020, 3, 1)
    p = laws.annual_periods(s, dt.date(2026, 12, 31))
    assert p[0] == (dt.date(2020, 9, 1), dt.date(2021, 2, 28), 3)
    assert [x[2] for x in p] == [3, 7, 10, 14, 14, 15, 15]
    assert laws.annual_days_for_years(10) == 16 and laws.annual_days_for_years(30) == 30
    # 曆年制：115/7/1 到職 → 116 年＝3 日（滿 6 個月那期全落在 116 年）＋7 日 × 184/366 ＝ 6.52，進位到半日 7 日
    assert laws.annual_calendar_year(dt.date(2026, 7, 1), 2027) == D("7")
    assert laws.annual_calendar_year(dt.date(2026, 7, 1), 2026) == 0


def test_tax_withholding():
    assert laws.withhold_regular(50000, 0, P) == 0
    assert laws.withhold_regular(120000, 0, P) > 0
    assert laws.withhold_regular(120000, 3, P) < laws.withhold_regular(120000, 0, P)
    assert laws.withhold_nonregular(90000, P) == 0
    assert laws.withhold_nonregular(100000, P) == 5000
    # 二代健保：年累計 200,000 前已發 150,000、投保 45,800（4 倍 183,200）
    sup, base = laws.nhi_bonus_sup(150000, 50000, 45800, D("2.11"))
    assert base == 16800 and sup == 354


# ---------------------------------------------------------------- 資料庫流程
def setup_company(b):
    b.save_company(name="祥和貿易股份有限公司", tax_id="12345675", occ_rate="0.18", late_deduct=1, absent_deduct=1)
    b.save_master("departments", dict(code="S", name="業務部", cost_type="S", active=True), True)
    b.save_employee(dict(code="E001", name="王大明", id_no="A123456789", gender="M", hire_date="2024/01/02",
                         dept="A", title="經理", base_salary="40000", nhi_dependents=1, labor_ins=1, employment_ins=1,
                         occ_ins=1, nhi=1, pension=1, pension_self="6", bank_code="0040037", bank_account="111222333"), True)
    b.save_emp_items("E001", {"MEAL": 2000, "DUTY": 2000, "ATTEND": 1000})
    b.save_employee(dict(code="E002", name="陳美麗", id_no="B223456782", gender="F", hire_date="2026/11/16",
                         dept="S", title="業務", base_salary="36000", labor_ins=1, employment_ins=1, occ_ins=1, nhi=1,
                         pension=1), True)
    b.save_master("gps_sites", dict(name="總公司", address="臺北市", lat="25.033964", lon="121.564468", radius=150,
                                    max_accuracy=200, active=True), True)


def test_employee_and_roster(biz, tmp_path):
    b = biz
    setup_company(b)
    with pytest.raises(BizError):
        b.save_employee(dict(code="E9", name="錯", id_no="A123456788"), True)        # 檢查碼錯
    e = b.employee("E001")
    assert b.wage_basis(e) == 45000                                                     # 本薪＋伙食＋職務＋全勤
    pv = b.premium_preview("E001", dt.date(2026, 11, 1))
    assert pv["labor_wage"] == 45800 and pv["labor_emp"] == 1145 and pv["nhi_emp"] == 1420
    assert pv["pension_self"] == 2748 and pv["occ_er"] == 82
    # 預設班：週一～五 D、週六休、週日例；11/13（五）D、11/14（六）休
    sch = b.schedules([e], dt.date(2026, 11, 13), dt.date(2026, 11, 15))
    assert sch[("E001", dt.date(2026, 11, 13))].code == "D"
    assert sch[("E001", dt.date(2026, 11, 14))].day_type == "R"
    assert sch[("E001", dt.date(2026, 11, 15))].day_type == "H"
    assert sch[("E001", dt.date(2026, 11, 13))].work_min == 480
    n = b.fill_roster(["E002"], "2026/12/01", "2026/12/31", "M,M,E,E,休,例")
    assert n == 31
    m = b.roster_month("202612")
    row = next(r for r in m["rows"] if r["emp"] == "E002")
    assert row["cells"][0]["code"] == "M" and row["cells"][4]["code"] == "休"
    assert next(r for r in m["rows"] if r["emp"] == "E001")["cells"][24]["code"] == "國"    # 12/25 行憲紀念日
    # 月班表 XML 匯出→清除→匯入
    p = str(tmp_path / "rcw.xml")
    b.export_rcw_xml(["202612"], p)
    assert 'category="assistant"' in open(p, encoding="utf-8").read()
    b.clear_roster(["E002"], "2026/12/01", "2026/12/31")
    res = b.import_rcw_xml(p)
    assert res["entries"] >= 62 and not res["unknown_emps"]
    assert b.roster_month("202612")["rows"][1]["cells"][2]["code"] == "E"
    # 小柯班表助手 ZIP
    z = str(tmp_path / "xk.zip")
    b.export_xiaoke_shift("E002", "202612", "202612", z)
    data = json.loads(zipfile.ZipFile(z).read("data.json"))
    assert data["app"] == "小柯班表助手" and data["version"] == 2
    assert data["data"]["me"]["days"]["2026-12-01"] == "M"
    t = {x["code"]: x for x in data["types"]}
    assert t["M"]["start"] == "07:00" and t["休"]["off"] is True and t["M"]["color"] < 0


def test_gps_punch_and_attendance(biz):
    b = biz
    setup_company(b)
    b.save_user("wang", "王大明", "員工", False, True, None, pw="pw1234", is_new=True, emp_code="E001")
    b.logout()
    b.login("wang", "pw1234")
    r = b.punch("I", 25.0340, 121.5645, 30, device="test")
    assert r["ok"] and r["distance"] < 150
    with pytest.raises(BizError):
        b.punch("I", 25.0340, 121.5645, 30)                     # 一分鐘內重複
    r2 = b.punch("O", 25.05, 121.60, 20)                        # 約 4 公里外 → 待確認
    assert not r2["ok"] and "超出" in r2["msg"]
    with pytest.raises(BizError):
        b.employees()                                           # 員工沒有員工資料權限
    b.logout()
    b.login("admin", "admin123")
    # 補登打卡、算出勤：11/12（四）08:58 上班、18:01 下班 → 正常；11/11 09:20 上班 → 遲到 15 分（寬限 5）
    b.add_punch("E001", "115/11/12 08:58", "I")
    b.add_punch("E001", "115/11/12 18:01", "O")
    b.add_punch("E001", "115/11/11 09:20", "I")
    b.add_punch("E001", "115/11/11 18:00", "O")
    recs = {r["d"]: r for r in b.attendance("2026/11/10", "2026/11/12", [b.employee("E001")])}
    assert recs[dt.date(2026, 11, 12)]["status"] == "正常"
    assert recs[dt.date(2026, 11, 11)]["late"] == 20
    assert recs[dt.date(2026, 11, 10)]["absent"] == 480


def test_leave_overtime_balance(biz):
    b = biz
    setup_company(b)
    n = b.grant_annual(2026)
    assert n >= 1
    left = b.balance_left("E001", "A", dt.date(2026, 11, 20))
    assert left == 10 * 8                                         # 113/01/02 到職，115/01/02 滿 2 年 10 日
    rid = b.request_leave("E001", "ANNUAL", "115/11/20 09:00", "115/11/20 18:00", "家事", approve=True)
    assert b.db.value("SELECT hours FROM leave_requests WHERE id=%s", (rid,)) == 8
    assert b.balance_left("E001", "A", dt.date(2026, 11, 21)) == 72
    with pytest.raises(BizError):
        b.request_leave("E001", "MENS", "115/11/23 09:00", "115/11/23 18:00")      # 男性不能請生理假
    with pytest.raises(BizError):
        b.request_leave("E001", "ANNUAL", "115/11/21 09:00", "115/11/21 18:00")   # 週六沒有班
    b.request_leave("E002", "MENS", "115/11/24 09:00", "115/11/24 18:00", approve=True)
    with pytest.raises(BizError):
        b.request_leave("E002", "MENS", "115/11/25 09:00", "115/11/25 13:00")     # 每月 1 日
    oid = b.request_overtime("E001", "2026/11/18", "18:00", "21:00", "P", "結帳", approve=True)
    o = b.db.row("SELECT * FROM overtime WHERE id=%s", (oid,))
    assert o["hours"] == 3 and o["day_type"] == "W"
    hr = D(45000) / 30 / 8
    assert o["amount"] == R(hr * 2 * 4 / 3 + hr * 5 / 3)
    oid2 = b.request_overtime("E001", "2026/11/21", "09:00", "13:00", "C", "盤點", approve=True)   # 休息日換補休
    assert b.balance_left("E001", "C", dt.date(2026, 11, 25)) == 4
    with pytest.raises(BizError):
        b.request_overtime("E001", "2026/11/19", "18:00", "23:00", "P", day_type="W") if False else \
            b.request_overtime("E001", "2026/11/19", "08:00", "22:00", "P")     # 一日超過 12 小時
    # 年度結算：補休折發
    out = b.settle_grants(["E001"], "2026/12/31", "P", "202612", kind="C")
    assert out and out[0][1] == 4
    assert b.db.value("SELECT amount FROM pay_inputs WHERE item='COMP_PAY'") > 0
    _ = oid2


def test_payroll_and_gl(biz, tmp_path):
    b = biz
    setup_company(b)
    b.grant_annual(2026)
    # 11 月：E001 事假 4 小時、加班 2 小時；E002 11/16 到職（半個月）
    b.request_leave("E001", "PERSONAL", "115/11/05 09:00", "115/11/05 13:00", approve=True)
    b.request_overtime("E001", "2026/11/18", "18:00", "20:00", "P", approve=True)
    b.save_employee(dict(code="E001", punch_required=0), False)
    b.save_employee(dict(code="E002", punch_required=0), False)
    b.add_pay_input("202611", "M", "E002", "PERF", 3000, "業績")
    rid = b.create_run("202611")
    res = b.calculate(rid)
    assert res["count"] == 2 and not res["warnings"]
    slips = {s["emp"]: s for s in b.payslips(rid)}
    s1 = b.payslip(slips["E001"]["id"])
    L = {ln["item"]: ln["amount"] for ln in s1["lines"]}
    hr = D(45000) / 30 / 8
    assert L["BASE"] == 40000 and L["MEAL"] == 2000 and L["DUTY"] == 2000
    assert L["LEAVE_DED"] == R(hr * 3)                         # 事假 09:00～13:00 扣午休＝3 小時，不給薪
    assert L["ATTEND"] == R(1000 - 1000 * D(3) / D(21 * 8))    # 依比例扣（11 月 21 個工作日）
    assert L["OT"] == R(hr * 2 * 4 / 3)
    assert L["LABOR"] == 1145 and L["NHI"] == 1420 and L["PEN_SELF"] == 2748     # 眷屬 1 口、自提 6%
    assert s1["labor_er"] == 4008 and s1["nhi_er"] == 2216 and s1["pension_er"] == 2748
    s2 = b.payslip(slips["E002"]["id"])
    L2 = {ln["item"]: ln["amount"] for ln in s2["lines"]}
    assert L2["BASE"] == 18000                                      # 36,000 × 15/30
    assert L2["LABOR"] == laws.labor_premium(36300, b.params(dt.date(2026, 11, 30)), days=15)[0]   # 按 15 日
    assert L2["PERF"] == 3000
    assert s2["gross"] - s2["deduct"] == s2["net"]
    # 確認 → 拋轉（借貸平衡）
    b.confirm_run(rid)
    b.mark_paid(rid)
    vs, _ = b.gl_preview("2026/11/01", "2026/12/31")
    refs = [v["ref"] for v in vs]
    assert "PAY%d" % rid in refs and "INS%d" % rid in refs and "BANK%d" % rid in refs
    for v in vs:
        assert sum(x["debit"] for x in v["lines"]) == sum(x["credit"] for x in v["lines"])
    pay = next(v for v in vs if v["ref"] == "PAY%d" % rid)
    accts = {x["account"] for x in pay["lines"]}
    assert {"6211", "6111", "6224", "6228", "2173", "2141"} <= accts
    bid = b.create_gl_batch("2026/11/01", "2026/12/31")
    p = str(tmp_path / "b.zmsgl")
    b.export_gl_batch(bid, p)
    data = json.load(open(p, encoding="utf-8"))
    assert data["format"] == "zms-gl" and data["source"].startswith("資料助秘之一般公司人事薪資差勤")
    with pytest.raises(BizError):
        b.unconfirm_run(rid)
    b.cancel_gl_batch(bid)
    b.mark_paid(rid, False)
    b.unconfirm_run(rid)
    # 年終獎金規則：1.5 個月（本薪＋經常性），依在職月數
    b.save_master("bonus_rules", dict(name="年終獎金", item="YEAREND", basis="M", value="1.5", prorate="Y", min_months=0,
                                      depts="", exclude_left=True, active=True), True)
    rule = b.db.value("SELECT id FROM bonus_rules")
    pv = {x["emp"]: x for x in b.bonus_preview(rule, "2026/12/31")}
    assert pv["E001"]["amount"] == 67500
    assert pv["E002"]["amount"] < 10000
    cnt, tot = b.generate_bonus(rule, "2026/12/31", "202612", "B")
    rb = b.create_run("202612", "B", "115 年年終獎金", "2027/01/20")
    b.calculate(rb)
    sb = {s["emp"]: s for s in b.payslips(rb)}
    assert sb["E001"]["gross"] == 67500 and sb["E001"]["tax"] == 0
    assert os.path.getsize(b.payslip_html([sb["E001"]["id"]], str(tmp_path / "slip.html"))) > 1000


def test_occ_and_disaster(biz):
    b = biz
    setup_company(b)
    b.save_employee(dict(code="E001", punch_required=1), False)
    cid = b.save_occ_case(dict(emp="E001", injury_at="115/11/03 10:30", kind="W", place="倉庫", description="搬貨扭傷",
                               status="T"))
    b.occ_leave(cid, "115/11/04 09:00", "115/11/04 18:00")
    b.add_occ_cost(cid, "2026/11/05", "medical", 2500, "門診")
    b.add_occ_cost(cid, "2026/11/20", "ins", 1000, "職災保險傷病給付")
    c = b.occ_case(cid)
    assert c["cost_company"] == 2500 and c["cost_ins"] == 1000 and c["leave_hours"] == 8
    # 颱風停班（不給薪）：11/06 全天
    b.save_disaster(dict(d="2026/11/06", kind="typhoon", title="鳳凰颱風停班", period="D", pay_policy="U", work_extra=1))
    recs = {r["d"]: r for r in b.attendance("2026/11/04", "2026/11/06", [b.employee("E001")])}
    assert recs[dt.date(2026, 11, 6)]["absent"] == 0 and recs[dt.date(2026, 11, 6)]["closure_min"] == 480
    assert recs[dt.date(2026, 11, 4)]["absent"] == 0                     # 公傷病假不算曠職
    b.save_employee(dict(code="E001", punch_required=0), False)
    rid = b.create_run("202611")
    b.calculate(rid)
    s = b.payslip(b.payslips(rid)[0]["id"])
    L = {ln["item"]: ln["amount"] for ln in s["lines"]}
    hr = D(45000) / 30 / 8
    assert L["OCC_WAGE"] == R(hr * 8)
    assert L["LEAVE_DED"] == R(hr * 8)                                # 先扣後以免稅補償發回
    assert L["ATTEND"] == 1000                                             # 公傷、災害不影響全勤
