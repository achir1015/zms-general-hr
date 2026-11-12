"""導入說明的範例公司「祥和貿易股份有限公司」：建立部門、員工、班別、GPS 打卡地點、期初假期餘額，
115 年 1 月的排班、打卡、請假、加班、公傷，計算 1 月薪資並拋轉會計；另以 114 年度試算年終獎金。

說明文字（adoption.py）裡的數字都由這裡實際跑出，tests/test_adoption.py 逐格核對。
"""
import datetime as dt

COMPANY = dict(name="祥和貿易股份有限公司", short_name="祥和貿易", tax_id="12345675", owner="林志明",
               phone="02-2700-1234", address="臺北市大安區和平東路二段 100 號", labor_ins_no="01234567",
               nhi_no="34567890", tax_unit_no="12345675", occ_rate="0.13", pay_day=5, late_grace=5,
               slip_footer="薪資有疑問請洽管理部 李專員（分機 101）")
DEPTS = [("A", "管理部", "A"), ("S", "業務部", "S"), ("W", "倉儲部", "A"), ("R", "門市部", "S")]

# (編號, 姓名, 身分證, 性別, 生日, 到職, 部門, 職稱, 計薪, 本薪, 時薪, 眷屬, 自提%, 固定項目)
EMPLOYEES = [
    ("E001", "林志明", "A123456789", "M", "1975/04/12", "2015/03/01", "A", "總經理", "M", 60000, 0, 2, 6,
     dict(DUTY=5000, MEAL=2400, ATTEND=1000)),
    ("E002", "陳淑芬", "B223456782", "F", "1985/09/03", "2019/08/01", "A", "會計", "M", 42000, 0, 0, 0,
     dict(MEAL=2400, ATTEND=1000)),
    ("E003", "李佳穎", "F223456786", "F", "1994/02/20", "2023/02/01", "A", "行政專員", "M", 36000, 0, 0, 0,
     dict(MEAL=2400, ATTEND=1000)),
    ("E004", "吳建宏", "H123456786", "M", "1990/06/30", "2021/05/01", "S", "業務", "M", 38000, 0, 1, 0,
     dict(TRANS=3000, MEAL=2400, ATTEND=1000)),
    ("E005", "黃雅婷", "J223456789", "F", "1996/11/11", "2024/07/15", "A", "採購", "M", 37000, 0, 0, 0,
     dict(MEAL=2400, ATTEND=1000)),
    ("E006", "周俊傑", "K123456788", "M", "1988/01/25", "2018/11/01", "W", "倉管", "M", 34000, 0, 1, 0,
     dict(MEAL=2400, ATTEND=1000)),
    ("E007", "鄭雅雯", "L223456780", "F", "2000/05/05", "2025/10/01", "R", "門市店員", "M", 31000, 0, 0, 0,
     dict(MEAL=2400, ATTEND=1000)),
    ("E008", "張家豪", "M123456789", "M", "2003/08/08", "2025/12/01", "W", "倉庫助理（部分工時）", "H", 0, 200, 0, 0, {}),
]
OPENING = [("E001", 30 * 8, "2025/03/01", "2026/02/28"), ("E002", 12 * 8, "2025/08/01", "2026/07/31"),
           ("E004", 10 * 8, "2025/05/01", "2026/04/30"), ("E006", 5 * 8, "2025/11/01", "2026/10/31")]
SITE = dict(name="祥和貿易總公司", address="臺北市大安區和平東路二段 100 號", lat="25.026120", lon="121.543640",
            radius=150, max_accuracy=200, active=True)


def build(b, through_payroll=True):
    """在空白資料庫建立範例（b 已以管理員登入）。回傳 dict 供說明與測試使用。"""
    b.save_company(**COMPANY)
    for code, name, ct in DEPTS:
        b.save_master("departments", dict(code=code, name=name, cost_type=ct, manager="E001", active=True),
                      not b.db.value("SELECT 1 FROM departments WHERE code=%s", (code,)))
    for (code, name, idn, g, bd, hire, dept, title, typ, base, hourly, dep, ps, items) in EMPLOYEES:
        b.save_employee(dict(code=code, name=name, id_no=idn, gender=g, birthday=bd, hire_date=hire, dept=dept,
                             title=title, emp_type=typ, base_salary=base, hourly_wage=hourly, nhi_dependents=dep,
                             pension_self=ps, labor_ins=1, employment_ins=1, occ_ins=1, nhi=1 if typ != "H" else 0,
                             pension=1, punch_required=1, shift_group="D", bank_code="0040037",
                             bank_account="0000%s123456" % code[1:], tax_mode="T", tax_dependents=dep), True)
        if items:
            b.save_emp_items(code, items)
    b.save_master("gps_sites", SITE, True)
    # 期初特休餘額（導入前人工紀錄）＋115 年依年資產生的特休
    for emp, h, s, e in OPENING:
        b.add_grant(emp, "A", s, e, h, "導入時剩餘特休")
    b.grant_annual(2026)
    # 排班：門市部 E007 早晚班輪值；倉庫助理 E008 週一三五 下午班
    b.save_master("shifts", dict(code="P4", name="下午班", start_t="13:00", end_t="17:00", break_min=0, day_type="W",
                                 color="#8E24AA", sort=55, active=True), True)
    b.fill_roster(["E007"], "2026/01/01", "2026/01/31", "M,M,E,E,M,休,例")
    b.fill_roster(["E008"], "2026/01/05", "2026/01/31", "P4,休,P4,休,P4,休,例")
    b.db.exec("UPDATE roster SET shift='國' WHERE d='2026-01-01'")
    # 打卡：除了範例中的請假、遲到外，排班日都正常打卡
    b.save_user("hr", "李佳穎", "人資專員", False, True, None, pw="hr1234", is_new=True, emp_code="E003")
    first, last = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    emps = b.active_employees(first, last)
    sch = b.schedules(emps, first, last)
    skip = {("E002", dt.date(2026, 1, 9)), ("E006", dt.date(2026, 1, 16)), ("E007", dt.date(2026, 1, 12))}
    for (emp, d), s in sch.items():
        if not s.is_work or (emp, d) in skip:
            continue
        tin = s.start - dt.timedelta(minutes=8)
        tout = s.end + dt.timedelta(minutes=3)
        if emp == "E004" and d == dt.date(2026, 1, 14):
            tin = dt.datetime(2026, 1, 14, 14, 0) - dt.timedelta(minutes=5)       # 上午事假
        if emp == "E005" and d == dt.date(2026, 1, 22):
            tin = s.start + dt.timedelta(minutes=17)                               # 遲到 17 分
        if emp == "E006" and d in (dt.date(2026, 1, 20),):
            tout = dt.datetime(2026, 1, 20, 20, 2)                                 # 加班到 20:00
        for ts, k in ((tin, "I"), (tout, "O")):
            b.db.exec("INSERT INTO punches (emp, ts, kind, source, ok, created_by) VALUES (%s, %s, %s, 'gps', 1, 'demo')",
                      (emp, ts, k))
    # 休息日加班打卡
    for ts, k in ((dt.datetime(2026, 1, 24, 8, 55), "I"), (dt.datetime(2026, 1, 24, 13, 2), "O")):
        b.db.exec("INSERT INTO punches (emp, ts, kind, source, ok, created_by) VALUES ('E006', %s, %s, 'gps', 1, 'demo')",
                  (ts, k))
    # 請假、加班、公傷
    b.request_leave("E002", "ANNUAL", "115/01/09 09:00", "115/01/09 18:00", "家庭旅遊", approve=True)
    b.request_leave("E004", "PERSONAL", "115/01/14 09:00", "115/01/14 14:00", "辦理房屋過戶", approve=True)
    b.request_leave("E007", "MENS", "115/01/12 07:00", "115/01/12 16:00", "", approve=True)
    b.request_overtime("E006", "2026/01/20", "18:00", "20:00", "P", "月中到貨上架", approve=True)
    b.request_overtime("E006", "2026/01/24", "09:00", "13:00", "C", "年前盤點", approve=True)
    cid = b.save_occ_case(dict(emp="E006", injury_at="115/01/15 16:20", kind="W", place="倉庫 B 區",
                               description="搬運紙箱時扭傷腰部", injury="下背部扭傷", hospital="台大醫院", status="R",
                               return_date="115/01/17", reported_at="115/01/15"))
    b.occ_leave(cid, "115/01/16 09:00", "115/01/16 18:00")
    b.add_occ_cost(cid, "2026/01/16", "medical", 1200, "門診與藥費")
    # 每月變動輸入：業務獎金
    b.add_pay_input("202601", "M", "E004", "PERF", 6000, "12 月業績獎金")
    out = dict(occ_case=cid)
    if not through_payroll:
        return out
    rid = b.create_run("202601", "M", "", "2026/02/05")
    out["calc"] = b.calculate(rid)
    out["run"] = rid
    b.confirm_run(rid)
    b.mark_paid(rid)
    # 114 年年終獎金（1.5 個月，依在職月數比例；到職滿 3 個月才發），115/02/10 發放
    b.save_master("bonus_rules", dict(name="年終獎金", item="YEAREND", basis="M", value="1.5", prorate="Y", min_months=3,
                                      depts="", exclude_left=True, memo="依 114 年在職月數比例", active=True), True)
    rule = b.db.value("SELECT id FROM bonus_rules WHERE name='年終獎金'")
    out["bonus"] = b.generate_bonus(rule, "2025/12/31", "202602", "B")
    rb = b.create_run("202602", "B", "114 年年終獎金", "2026/02/10")
    b.calculate(rb)
    out["bonus_run"] = rb
    return out


def summary(b, out):
    """說明文字要用的數字。"""
    slips = {s["emp"]: s for s in b.payslips(out["run"])}
    run = b.payroll_run(out["run"])
    vs, _ = b.gl_preview("2026/01/01", "2026/02/28", ["payroll", "paid", "occ"])
    bonus = {s["emp"]: s for s in b.payslips(out["bonus_run"])}
    return dict(slips=slips, run=run, vouchers={v["ref"][:3]: v for v in vs}, bonus=bonus)
