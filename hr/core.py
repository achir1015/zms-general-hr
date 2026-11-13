"""共用基礎：錯誤類別、金額格式、登入與權限、使用者、公司設定、基本資料維護。

所有規則都在服務層檢查（畫面只負責顯示），手機版與 GPS 打卡網頁透過 API 也共用同一套。
"""
import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal

from . import passwords, rocdate
from .seed import FUNC_NAMES, FUNCS, ROLES

CENT = Decimal("0.01")
ONE = Decimal("1")
D0 = Decimal(0)


class BizError(Exception):
    """可以直接顯示給使用者看的錯誤。"""


def dec(v, q=CENT) -> Decimal:
    if v in (None, ""):
        return D0
    if isinstance(v, str):
        v = v.replace(",", "").strip() or "0"
    try:
        return Decimal(str(v)).quantize(q, ROUND_HALF_UP)
    except Exception:
        raise BizError("數字格式不正確：%s" % v)


def money(v) -> Decimal:
    return dec(v, CENT)


def yuan(v) -> Decimal:
    """四捨五入到元（薪資、保費都到元）。"""
    return dec(v, ONE)


def date(v) -> dt.date:
    try:
        return rocdate.read(v)
    except ValueError as e:
        raise BizError(str(e))


def opt_date(v):
    if v in (None, ""):
        return None
    return date(v)


def hhmm(v) -> str:
    s = (v or "").strip().replace("：", ":")
    if s.isdigit() and len(s) in (3, 4):
        s = s[:-2] + ":" + s[-2:]
    try:
        h, m = (int(x) for x in s.split(":"))
        if not (0 <= h <= 24 and 0 <= m < 60):
            raise ValueError
        return "%02d:%02d" % (h, m)
    except ValueError:
        raise BizError("時間格式不正確：%s（例如 09:00）" % v)


# 基本資料定義：(欄位, 標題, 型別, 寬度)；型別 s 文字、n 數字、i 整數、b 是否、d 日期、t 時間、
# dept 部門、emp 員工、item 薪資科目、sel:選項
MASTERS = {
    "departments": dict(title="部門", table="departments", key="code", fields=[
        ("code", "部門代號", "s", 100), ("name", "部門名稱", "s", 180),
        ("cost_type", "費用別", "sel:A=管理,S=推銷,M=製造,R=研發", 100), ("manager", "部門主管", "emp", 150),
        ("active", "使用中", "b", 70)]),
    "shifts": dict(title="班別", table="shifts", key="code", fields=[
        ("code", "班別代號", "s", 90), ("name", "班別名稱", "s", 120), ("start_t", "上班時間", "t", 90),
        ("end_t", "下班時間", "t", 90), ("break_min", "休息（分鐘）", "i", 90),
        ("day_type", "日別", "sel:W=工作日,R=休息日,H=例假,N=國定假日", 110), ("color", "顏色", "s", 90),
        ("sort", "排序", "i", 70), ("memo", "說明", "s", 200), ("active", "使用中", "b", 70)]),
    "leave_types": dict(title="假別", table="leave_types", key="code", fields=[
        ("code", "假別代號", "s", 100), ("name", "假別名稱", "s", 130), ("pay_ratio", "給薪比例（1全薪、0.5半薪）", "n", 110),
        ("min_hours", "最小單位（小時）", "n", 100), ("quota_days", "每年上限（日）", "n", 100),
        ("gender", "限定性別", "sel:=不限,F=女性,M=男性", 100), ("affects_attend", "影響全勤", "b", 80),
        ("balance", "扣抵額度", "sel:=不扣額度,A=特休額度,C=補休額度", 120), ("calendar_days", "依曆計算", "b", 80),
        ("color", "顏色", "s", 90), ("sort", "排序", "i", 70), ("law_note", "法令說明", "s", 300),
        ("active", "使用中", "b", 70)], readonly_sys=("code", "balance")),
    "pay_items": dict(title="薪資科目", table="pay_items", key="code", fields=[
        ("code", "科目代號", "s", 100), ("name", "科目名稱", "s", 140), ("kind", "類別", "sel:E=應發,D=應扣", 80),
        ("method", "方式", "sel:F=員工固定金額,M=每月輸入,S=系統計算", 130), ("taxable", "應稅", "b", 60),
        ("regular", "經常性給與", "b", 90), ("nhi_bonus", "補充保費獎金", "b", 100),
        ("income_code", "所得類別", "s", 80), ("gl_account", "會計科目（空白＝依部門）", "s", 120),
        ("sort", "排序", "i", 70), ("memo", "說明", "s", 260), ("active", "使用中", "b", 70)],
        readonly_sys=("code", "kind", "method")),
    "gps_sites": dict(title="打卡地點", table="gps_sites", key="id", fields=[
        ("name", "地點名稱", "s", 150), ("address", "地址", "s", 260), ("lat", "緯度", "n", 110), ("lon", "經度", "n", 110),
        ("radius", "允許半徑（公尺）", "i", 110), ("max_accuracy", "精確度上限（公尺）", "i", 110),
        ("active", "使用中", "b", 70)]),
    "calendar": dict(title="行事曆（國定假日）", table="calendar", key="d", fields=[
        ("d", "日期", "d", 110), ("kind", "類別", "sel:N=國定假日（休）,C=公司休假（給薪）,W=補班（工作日）", 160),
        ("name", "名稱", "s", 240)]),
    "bonus_rules": dict(title="津貼獎金規則", table="bonus_rules", key="id", fields=[
        ("name", "規則名稱", "s", 150), ("item", "薪資科目", "item", 130),
        ("basis", "計算基礎", "sel:M=月數 ×（本薪＋經常性津貼）,B=月數 × 本薪,A=固定金額", 200),
        ("value", "月數或金額", "n", 100), ("prorate", "比例", "sel:Y=依當年在職月數,D=依當年在職日數,N=不打折", 150),
        ("min_months", "在職滿幾個月才發", "i", 110), ("depts", "適用部門（逗號分隔，空白＝全部）", "s", 160),
        ("exclude_left", "已離職者不發", "b", 100), ("memo", "說明", "s", 220), ("active", "使用中", "b", 70)]),
}
NUMERIC = ("n", "i")
DEPT_COST = {"A": "管理", "S": "推銷", "M": "製造", "R": "研發"}
EMP_STATUS = {"A": "在職", "L": "留職停薪", "Q": "離職"}
EMP_TYPE = {"M": "月薪", "H": "時薪", "P": "部分工時"}


class Base:
    def __init__(self, db):
        self.db = db
        self.user = None
        self.perms = {}

    # ================================================================ 登入、權限、紀錄
    @property
    def uid(self):
        return self.user["uid"] if self.user else ""

    @property
    def my_emp(self):
        return (self.user or {}).get("emp_code") or ""

    def has_users(self) -> bool:
        return bool(self.db.value("SELECT COUNT(*) FROM users"))

    def login(self, uid, pw):
        u = self.db.row("SELECT * FROM users WHERE uid=%s", ((uid or "").strip(),))
        if not u or not passwords.verify(pw, u["pw_hash"]):
            self.db.exec("INSERT INTO audit_log (uid, action, detail) VALUES (%s, 'login_fail', '')", (uid or "",))
            raise BizError("帳號或密碼錯誤")
        if not u["active"]:
            raise BizError("此帳號已停用，請洽系統管理員")
        self.user = u
        self.perms = {r["func"]: r["lvl"] for r in self.db.rows("SELECT func, lvl FROM user_perms WHERE uid=%s",
                                                                 (u["uid"],))}
        self.db.exec("UPDATE users SET last_login=NOW() WHERE uid=%s", (u["uid"],))
        self.log("login", u["uid"])
        return u

    def logout(self):
        if self.user:
            self.log("logout", self.uid)
        self.user, self.perms = None, {}

    def level(self, func) -> int:
        if not self.user:
            return 0
        if self.user["is_admin"]:
            return 2
        return int(self.perms.get(func, 0))

    def can(self, func, lvl=1) -> bool:
        return self.level(func) >= lvl

    def need(self, func, lvl=2):
        if not self.can(func, lvl):
            raise BizError("您沒有「%s」的%s權限" % (FUNC_NAMES.get(func, func), "維護" if lvl >= 2 else "查詢"))

    @property
    def employee_only(self):
        """只有員工自助（沒有任何管理權限）的帳號。"""
        return bool(self.user) and not self.user["is_admin"] and not any(int(v or 0) for v in self.perms.values())

    @property
    def see_salary(self):
        return self.can("SAL", 1)

    def is_manager_of(self, emp):
        """部門主管可以審核自己部門員工的請假加班。"""
        if not self.my_emp:
            return False
        return bool(self.db.value("SELECT 1 FROM employees e JOIN departments d ON d.code=e.dept WHERE e.code=%s AND "
                                  "d.manager=%s", (emp, self.my_emp)))

    def log(self, action, target="", detail=""):
        try:
            self.db.exec("INSERT INTO audit_log (uid, action, target, detail) VALUES (%s, %s, %s, %s)",
                         (self.uid, action, str(target)[:60], str(detail)[:500]))
        except Exception:
            pass

    # ================================================================ 使用者
    def users(self):
        self.need("SYS", 1)
        rows = self.db.rows("SELECT u.uid, u.name, u.role, u.is_admin, u.active, u.last_login, u.emp_code, "
                            "e.name AS emp_name FROM users u LEFT JOIN employees e ON e.code=u.emp_code ORDER BY u.uid")
        perms = self.db.rows("SELECT uid, func, lvl FROM user_perms")
        for u in rows:
            u["perms"] = {p["func"]: p["lvl"] for p in perms if p["uid"] == u["uid"]}
        return rows

    def create_first_admin(self, uid, name, pw):
        if self.has_users():
            raise BizError("系統已有使用者")
        self._check_new_password(pw)
        self._insert_user(uid, name, pw, "系統管理員", True)

    def save_user(self, uid, name, role, is_admin, active, perms, pw=None, is_new=False, emp_code=""):
        self.need("SYS")
        uid = (uid or "").strip()
        emp_code = (emp_code or "").strip()
        if not uid or not (name or "").strip():
            raise BizError("帳號與姓名必填")
        if emp_code:
            if not self.db.value("SELECT 1 FROM employees WHERE code=%s", (emp_code,)):
                raise BizError("員工 %s 不存在" % emp_code)
            other = self.db.value("SELECT uid FROM users WHERE emp_code=%s AND uid<>%s", (emp_code, uid))
            if other:
                raise BizError("員工 %s 已對應到帳號 %s" % (emp_code, other))
        if is_new:
            if self.db.value("SELECT 1 FROM users WHERE uid=%s", (uid,)):
                raise BizError("帳號 %s 已存在" % uid)
            self._check_new_password(pw)
            self._insert_user(uid, name, pw, role, is_admin, perms, emp_code)
        else:
            if uid == self.uid and (not is_admin or not active) and self.user["is_admin"]:
                raise BizError("不能取消自己的管理員身分或停用自己")
            if (not is_admin or not active) and not self.db.value(
                    "SELECT COUNT(*) FROM users WHERE is_admin=1 AND active=1 AND uid<>%s", (uid,)):
                raise BizError("至少要保留一位啟用中的系統管理員")
            self.db.exec("UPDATE users SET name=%s, role=%s, is_admin=%s, active=%s, emp_code=%s WHERE uid=%s",
                         (name.strip(), role, int(bool(is_admin)), int(bool(active)), emp_code, uid))
            self._write_perms(uid, perms)
            if pw:
                self._check_new_password(pw)
                self.db.exec("UPDATE users SET pw_hash=%s WHERE uid=%s", (passwords.make(pw), uid))
        self.log("user_save", uid, json.dumps({"role": role, "admin": bool(is_admin), "emp": emp_code,
                                               "perms": perms}, ensure_ascii=False))

    def _insert_user(self, uid, name, pw, role, is_admin, perms=None, emp_code=""):
        uid = (uid or "").strip()
        if not uid:
            raise BizError("請輸入帳號")
        self.db.exec("INSERT INTO users (uid, name, pw_hash, role, is_admin, emp_code) VALUES (%s, %s, %s, %s, %s, %s)",
                     (uid, (name or uid).strip(), passwords.make(pw), role, int(bool(is_admin)), emp_code or ""))
        self._write_perms(uid, perms if perms is not None else ROLES.get(role, {}))

    def _write_perms(self, uid, perms):
        perms = perms or {}
        self.db.exec("DELETE FROM user_perms WHERE uid=%s", (uid,))
        self.db.exec_many("INSERT INTO user_perms (uid, func, lvl) VALUES (%s, %s, %s)",
                          [(uid, f, int(perms.get(f, 0))) for f, _, _ in FUNCS])

    def create_employee_accounts(self, pw_rule="id4"):
        """替還沒有帳號的在職員工建立「員工」帳號（帳號＝員工編號；預設密碼＝身分證後 4 碼＋生日月日，
        沒有身分證或生日時為員工編號＋1234）。回傳 [(帳號, 姓名, 預設密碼)]。"""
        self.need("SYS")
        out = []
        for e in self.db.rows("SELECT * FROM employees WHERE status<>'Q' AND code NOT IN "
                              "(SELECT emp_code FROM users WHERE emp_code<>'') ORDER BY code"):
            uid = e["code"]
            if self.db.value("SELECT 1 FROM users WHERE uid=%s", (uid,)):
                continue
            idn = (e["id_no"] or "")[-4:]
            pw = (idn + e["birthday"].strftime("%m%d")) if idn and e["birthday"] else uid + "1234"
            if len(pw) < 6:
                pw = (pw + "123456")[:6]
            self._insert_user(uid, e["name"], pw, "員工", False, None, e["code"])
            out.append((uid, e["name"], pw))
        self.log("emp_accounts", "", "%d 個" % len(out))
        return out

    @staticmethod
    def _check_new_password(pw):
        if len(pw or "") < 6:
            raise BizError("密碼至少 6 個字")

    def change_password(self, old, new):
        if not passwords.verify(old, self.db.value("SELECT pw_hash FROM users WHERE uid=%s", (self.uid,))):
            raise BizError("舊密碼不正確")
        self._check_new_password(new)
        self.db.exec("UPDATE users SET pw_hash=%s WHERE uid=%s", (passwords.make(new), self.uid))
        self.log("password", self.uid)

    def delete_user(self, uid):
        self.need("SYS")
        if uid == self.uid:
            raise BizError("不能刪除自己")
        if self.db.value("SELECT 1 FROM payroll_runs WHERE created_by=%s LIMIT 1", (uid,)) or \
                self.db.value("SELECT 1 FROM leave_requests WHERE approver=%s LIMIT 1", (uid,)):
            raise BizError("此帳號已有作業紀錄，請改為「停用」以保留稽核軌跡")
        self.db.exec("DELETE FROM user_perms WHERE uid=%s", (uid,))
        self.db.exec("DELETE FROM users WHERE uid=%s", (uid,))
        self.log("user_delete", uid)

    def audit(self, limit=500, uid=""):
        self.need("SYS", 1)
        sql = "SELECT * FROM audit_log" + (" WHERE uid=%s" if uid else "") + " ORDER BY id DESC LIMIT %s"
        return self.db.rows(sql, ((uid, limit) if uid else (limit,)))

    # ================================================================ 公司設定
    COMPANY_FIELDS = ("name", "short_name", "tax_id", "owner", "phone", "email", "address", "labor_ins_no", "nhi_no",
                      "tax_unit_no", "occ_rate", "pay_day", "leave_system", "ot_round_min", "late_grace", "late_deduct",
                      "absent_deduct", "attend_rule", "week_start", "slip_footer")

    def company(self):
        return self.db.row("SELECT * FROM company WHERE id=1") or {}

    def save_company(self, **kw):
        self.need("SYS")
        vals = {k: kw[k] for k in self.COMPANY_FIELDS if k in kw}
        if "tax_id" in vals and vals["tax_id"] and (not str(vals["tax_id"]).isdigit() or len(vals["tax_id"]) != 8):
            raise BizError("統一編號應為 8 位數字")
        if "occ_rate" in vals:
            r = dec(vals["occ_rate"], Decimal("0.0001"))
            if r < 0 or r > 5:
                raise BizError("職災保險費率請輸入百分比（例如 0.18）")
            vals["occ_rate"] = r
        if "leave_system" in vals and vals["leave_system"] not in ("A", "C"):
            raise BizError("特休制度不正確")
        if "pay_day" in vals and not 1 <= int(vals["pay_day"] or 0) <= 31:
            raise BizError("發薪日要在 1～31 之間")
        if vals:
            self.db.exec("UPDATE company SET %s WHERE id=1" % ", ".join("%s=%%s" % k for k in vals),
                         tuple(vals.values()))
        self.log("company", "", json.dumps({k: str(v) for k, v in vals.items()}, ensure_ascii=False))

    def closed_ym(self):
        return self.company().get("closed_ym") or ""

    def check_open(self, d, what="資料"):
        """已關帳的月份不能再改出勤、請假、加班。"""
        c = self.closed_ym()
        if c and rocdate.ym(d) <= c:
            raise BizError("%s 已關帳（薪資已發放），不能再修改%s" % (rocdate.ym_show(rocdate.ym(d)), what))

    # ================================================================ 基本資料
    def master_rows(self, name, active_only=False, search=""):
        self.need("BAS", 1)
        m = MASTERS[name]
        where, args = [], []
        if active_only and any(f[0] == "active" for f in m["fields"]):
            where.append("active=1")
        if search:
            cols = [f[0] for f in m["fields"] if f[2] == "s"][:4]
            where.append("(" + " OR ".join("%s LIKE %%s" % c for c in cols) + ")")
            args += ["%" + search + "%"] * len(cols)
        order = {"shifts": "sort, code", "leave_types": "sort, code", "pay_items": "kind DESC, sort, code",
                 "calendar": "d DESC"}.get(name, m["key"])
        sql = "SELECT * FROM %s%s ORDER BY %s" % (m["table"], (" WHERE " + " AND ".join(where)) if where else "", order)
        return self.db.rows(sql, tuple(args))

    def options(self, name):
        """下拉選單：(代號, 顯示文字)"""
        if name in ("dept", "departments"):
            return [(r["code"], "%s %s" % (r["code"], r["name"])) for r in
                    self.db.rows("SELECT code, name FROM departments WHERE active=1 ORDER BY code")]
        if name in ("emp", "employees"):
            return [(r["code"], "%s %s" % (r["code"], r["name"])) for r in
                    self.db.rows("SELECT code, name FROM employees WHERE status<>'Q' ORDER BY code")]
        if name == "emp_all":
            return [(r["code"], "%s %s%s" % (r["code"], r["name"], "（離職）" if r["status"] == "Q" else "")) for r in
                    self.db.rows("SELECT code, name, status FROM employees ORDER BY code")]
        if name in ("shift", "shifts"):
            return [(r["code"], "%s %s" % (r["code"], r["name"])) for r in
                    self.db.rows("SELECT code, name FROM shifts WHERE active=1 ORDER BY sort, code")]
        if name in ("ltype", "leave_types"):
            return [(r["code"], r["name"]) for r in
                    self.db.rows("SELECT code, name FROM leave_types WHERE active=1 ORDER BY sort, code")]
        if name in ("item", "pay_items"):
            return [(r["code"], "%s %s" % (r["code"], r["name"])) for r in
                    self.db.rows("SELECT code, name FROM pay_items WHERE active=1 ORDER BY kind DESC, sort, code")]
        if name == "item_input":       # 每月輸入的科目
            return [(r["code"], "%s %s（%s）" % (r["code"], r["name"], "加" if r["kind"] == "E" else "減")) for r in
                    self.db.rows("SELECT code, name, kind FROM pay_items WHERE active=1 AND method IN ('M','F') "
                                 "ORDER BY kind DESC, sort, code")]
        if name in ("site", "gps_sites"):
            return [(str(r["id"]), r["name"]) for r in
                    self.db.rows("SELECT id, name FROM gps_sites WHERE active=1 ORDER BY id")]
        return []

    def save_master(self, name, row: dict, is_new: bool):
        self.need("BAS")
        m = MASTERS[name]
        key = m["key"]
        data = {}
        old = None
        if not is_new:
            old = self.db.row("SELECT * FROM %s WHERE %s=%%s" % (m["table"], key), (row.get(key),))
        locked = m.get("readonly_sys", ()) if old and old.get("sys") else ()
        for f, title, typ, _ in m["fields"]:
            if f not in row or f in locked:
                continue
            v = row[f]
            if typ == "n":
                v = dec(v, Decimal("0.000001") if f in ("lat", "lon") else Decimal("0.001"))
            elif typ == "i":
                try:
                    v = int(str(v or 0).replace(",", ""))
                except ValueError:
                    raise BizError("「%s」要是整數" % title)
            elif typ == "b":
                v = int(bool(v))
            elif typ == "d":
                v = date(v)
            elif typ == "t":
                v = hhmm(v)
            else:
                v = ("" if v is None else str(v)).strip()
            data[f] = v
        if key not in ("id",):
            if not data.get(key) and not (old and key in locked):
                raise BizError("請輸入%s" % m["fields"][0][1])
            if isinstance(data.get(key), str) and any(ch in data[key] for ch in " ,'\"\\"):
                raise BizError("代號不能有空白、逗號或引號")
        name_field = next((f[0] for f in m["fields"] if f[0] in ("name",)), None)
        if name_field and name_field in data and not data[name_field]:
            raise BizError("請輸入%s" % next(f[1] for f in m["fields"] if f[0] == name_field))
        if name == "leave_types" and "pay_ratio" in data and not D0 <= data["pay_ratio"] <= 1:
            raise BizError("給薪比例要在 0～1 之間")
        if name == "gps_sites":
            if data.get("radius", 1) < 20:
                raise BizError("允許半徑至少 20 公尺")
            if not (-90 <= data.get("lat", D0) <= 90 and -180 <= data.get("lon", D0) <= 180):
                raise BizError("經緯度不正確")
        if name == "bonus_rules" and data.get("item") and not self.db.value(
                "SELECT 1 FROM pay_items WHERE code=%s AND kind='E'", (data["item"],)):
            raise BizError("獎金規則的薪資科目要是「應發」科目")
        if is_new:
            if key != "id" and self.db.value("SELECT 1 FROM %s WHERE %s=%%s" % (m["table"], key), (data[key],)):
                raise BizError("代號 %s 已存在" % data[key])
            cols = list(data)
            self.db.exec("INSERT INTO %s (%s) VALUES (%s)" % (m["table"], ", ".join(cols), ", ".join(["%s"] * len(cols))),
                         tuple(data.values()))
        else:
            kv = row.get(key)
            upd = {k: v for k, v in data.items() if k != key}
            if upd:
                self.db.exec("UPDATE %s SET %s WHERE %s=%%s" % (m["table"], ", ".join("%s=%%s" % k for k in upd), key),
                             tuple(upd.values()) + (kv,))
        self.log("master_" + ("new" if is_new else "edit"), "%s:%s" % (name, data.get(key, row.get(key, ""))))

    def delete_master(self, name, keyval):
        self.need("BAS")
        m = MASTERS[name]
        r = self.db.row("SELECT * FROM %s WHERE %s=%%s" % (m["table"], m["key"]), (keyval,))
        if r and r.get("sys"):
            raise BizError("系統內建的資料不能刪除（可改為停用）")
        used = {
            "departments": [("employees", "dept")], "shifts": [("roster", "shift")],
            "leave_types": [("leave_requests", "ltype")], "pay_items": [("payslip_lines", "item"), ("emp_items", "item")],
            "gps_sites": [("punches", "site_id")],
        }.get(name, [])
        for table, col in used:
            if self.db.value("SELECT 1 FROM %s WHERE %s=%%s LIMIT 1" % (table, col), (keyval,)):
                raise BizError("此資料已被使用，不能刪除（可改為停用）")
        self.db.exec("DELETE FROM %s WHERE %s=%%s" % (m["table"], m["key"]), (keyval,))
        self.log("master_delete", "%s:%s" % (name, keyval))
