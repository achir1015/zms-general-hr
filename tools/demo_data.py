"""開發用：在開發資料庫（data/）建立導入說明的範例公司「祥和貿易」（8 位員工、115 年 1 月的差勤與薪資、
114 年年終獎金），另外補上今天以前幾天的打卡，方便看畫面與測試。

用法：.venv\\Scripts\\python tools\\demo_data.py   （帳號 admin／admin123；員工帳號 E001～E008／pw1234；會清空開發資料庫）
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from hr import example  # noqa: E402
from hr.biz import Biz  # noqa: E402
from hr.database import DB  # noqa: E402
from hr.dbserver import LocalDatabaseServer  # noqa: E402
from hr.settings import Settings  # noqa: E402


def main():
    st = Settings.load()
    srv = LocalDatabaseServer(st)
    srv.start()
    try:
        db = DB(st)
        c = db.connect(use_db=False)
        with c.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS `%s`" % st.database)
        c.close()
        db.prepare()
        st.save()
        b = Biz(db)
        b.create_first_admin("admin", "系統管理員", "admin123")
        b.login("admin", "admin123")
        example.build(b)
        for code, name in [(r["code"], r["name"]) for r in b.employees("work")]:
            if not b.db.value("SELECT 1 FROM users WHERE emp_code=%s", (code,)):
                b.save_user(code, name, "員工", False, True, None, pw="pw1234", is_new=True, emp_code=code)
        # 近幾天的打卡（看首頁與出勤日報用）
        today = dt.date.today()
        d1 = today - dt.timedelta(days=6)
        emps = b.active_employees(d1, today)
        sch = b.schedules(emps, d1, today)
        for (emp, d), s in sch.items():
            if not s.is_work or (emp == "E003" and d == today):
                continue
            tin = s.start - dt.timedelta(minutes=6)
            if emp == "E005" and d == today - dt.timedelta(days=1):
                tin = s.start + dt.timedelta(minutes=12)
            rows = [(tin, "I")]
            if d < today:
                rows.append((s.end + dt.timedelta(minutes=4), "O"))
            for ts, k in rows:
                if ts <= dt.datetime.now():
                    b.db.exec("INSERT INTO punches (emp, ts, kind, source, lat, lon, accuracy, site_id, distance, ok, "
                              "created_by) VALUES (%s, %s, %s, 'gps', 25.0262, 121.5437, 12, 1, 18, 1, 'demo')",
                              (emp, ts, k))
        b.db.exec("INSERT INTO punches (emp, ts, kind, source, lat, lon, accuracy, site_id, distance, ok, note, created_by) "
                  "VALUES ('E004', %s, 'I', 'gps', 25.0480, 121.5170, 25, 1, 3520, 0, '距離「祥和貿易總公司」3520 公尺，"
                  "超出允許範圍 150 公尺，已記錄為待確認', 'demo')", (dt.datetime.combine(today, dt.time(8, 41)),))
        mon = today + dt.timedelta(days=7 - today.weekday())
        b.request_leave("E002", "PERSONAL", "%s 09:00" % mon.strftime("%Y/%m/%d"), "%s 13:00" % mon.strftime("%Y/%m/%d"),
                        "看牙醫")
        b.request_overtime("E006", today - dt.timedelta(days=1 if today.weekday() else 3), "18:00", "20:00", "P", "到貨上架")
        print("完成：祥和貿易範例資料（admin/admin123；員工帳號 E001～E008，密碼 pw1234）")
    finally:
        srv.stop()


if __name__ == "__main__":
    main()
