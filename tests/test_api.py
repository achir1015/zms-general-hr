"""手機連線：真的啟動 API 服務，用 RemoteBooks 走 HTTP 測試（與電腦版同一套服務、同一套權限）。"""
import datetime as dt
from decimal import Decimal

import pytest

from hr.api import ApiServer
from hr.core import BizError
from hr.remote import Client, RemoteBooks
from hr.seed import ROLES

PORT = 8798


@pytest.fixture()
def api(biz):
    from tests.test_core import setup_company
    setup_company(biz)
    biz.save_user("wang", "王大明", "員工", False, True, None, pw="pass123", is_new=True, emp_code="E001")
    biz.save_user("hr", "人資", "人資專員", False, True, ROLES["人資專員"], pw="pass123", is_new=True)
    srv = ApiServer(biz.db, port=PORT, host="127.0.0.1")
    srv.start()
    yield srv
    srv.stop()


def connect(uid, pw):
    rb = RemoteBooks(Client("127.0.0.1:%d" % PORT))
    rb.login(uid, pw)
    return rb


def test_ping_and_login(api):
    c = Client("http://127.0.0.1:%d" % PORT)
    assert c.ping()["app"] == "資料助秘之一般公司人事薪資差勤"
    rb = RemoteBooks(c)
    with pytest.raises(BizError, match="帳號或密碼錯誤"):
        rb.login("admin", "wrong")
    rb.login("admin", "admin123")
    assert rb.user["uid"] == "admin" and "pw_hash" not in rb.user and rb.can("SYS")


def test_punch_page_and_self_service(api, biz):
    import urllib.request
    html = urllib.request.urlopen("http://127.0.0.1:%d/punch" % PORT).read().decode("utf-8")
    assert "GPS 打卡" in html and "navigator.geolocation" in html
    assert b"standalone" in urllib.request.urlopen("http://127.0.0.1:%d/manifest.webmanifest" % PORT).read()
    rb = connect("wang", "pass123")
    t = rb.my_today()
    assert t["emp"] == "E001"
    # 手機傳來的 emp、source、ip 一律被忽略：只能替自己打 GPS 卡
    r = rb.punch("I", **dict(lat=25.0340, lon=121.5645, accuracy=20, emp="E002", source="pc",
                                                  ip="1.2.3.4", device="pytest"))
    assert r["ok"]
    p = biz.db.row("SELECT * FROM punches ORDER BY id DESC LIMIT 1")
    assert p["emp"] == "E001" and p["source"] == "gps" and p["ip"] == "127.0.0.1"
    assert rb.my_profile()["code"] == "E001"
    lid = rb.request_leave(None, "PERSONAL", "115/12/01 09:00", "115/12/01 13:00")
    assert biz.db.value("SELECT emp FROM leave_requests WHERE id=%s", (lid,)) == "E001"
    with pytest.raises(BizError):
        rb._c.call("books", "employees", [], {})                       # 員工沒有員工資料權限
    for bad in ("premium_preview", "employee", "wage_basis", "salary_on", "insured_wages", "schedules", "login", "db",
                "export_gl_batch", "export_xiaoke_shift", "balance_summary"):
        with pytest.raises(BizError, match="不允許"):
            rb._c.call("books", bad, [], {})


def test_permissions_enforced_on_server(api, biz):
    rb = connect("hr", "pass123")
    rows = rb.employees()
    assert rows and rows[0]["base_salary"] is None                     # 人資專員沒有薪資個資權限
    with pytest.raises(BizError, match="系統管理"):
        rb._c.call("books", "save_company", [], dict(name="X"))
    with pytest.raises(BizError, match="薪資"):
        rb._c.call("books", "create_run", ["202611"], {})
    biz.save_user("hr", "人資", "人資專員", False, False, ROLES["人資專員"], is_new=False)
    with pytest.raises(BizError, match="停用"):
        rb._c.call("books", "employees", [], {})


def test_client_ip_trust():
    from hr.api import client_ip
    h = {"Cf-Connecting-Ip": "203.0.113.9", "X-Forwarded-For": "198.51.100.1"}
    assert client_ip("127.0.0.1", h) == "203.0.113.9"
    assert client_ip("192.168.6.50", h) == "192.168.6.50"


def test_switch_to_alternate_url(api):
    c = Client("127.0.0.1:1", alternates=["127.0.0.1:%d" % PORT])
    rb = RemoteBooks(c)
    switched = []
    c.on_switch = switched.append
    rb.login("admin", "admin123")
    assert c.url.endswith(":%d" % PORT) and switched


def test_login_throttle(api):
    rb = RemoteBooks(Client("127.0.0.1:%d" % PORT))
    for _ in range(8):
        with pytest.raises(BizError):
            rb.login("admin", "bad")
    with pytest.raises(BizError, match="次數太多"):
        rb.login("admin", "admin123")
