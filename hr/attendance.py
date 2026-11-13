"""差勤：班別與排班、行事曆、天然災害停班、GPS 打卡、出勤日報與月報。

排班與兩個既有系統相容：
* 月班表管理系統（achir1015/rcw-month）：XML 備份格式
  <scheduleSystem company department><schedules><schedule category year month><employee empId name>
  <entry day shift/>…；可匯入、匯出（匯出時 category 用 assistant，月班表系統才會接受）。
* 小柯班表助手（achir1015/xiaoke-shift，Android／iPhone）：備份 ZIP（data.json，app＝小柯班表助手、version 2），
  每位員工匯出一個檔案，在手機「⋯ → 還原班表」即可把公司班表放進手機（含班別時間、顏色、國定假日、上班鬧鐘）。

GPS 打卡參考 achir1015/gps-arrival-test：Haversine 公式算出與打卡地點的距離，在允許半徑內才有效；
距離與精確度一律在伺服器端重新判定（不相信手機傳來的「已到達」）。
"""
import datetime as dt
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal

from . import rocdate
from .core import BizError, D0, date, hhmm

DAY_TYPES = {"W": "工作日", "R": "休息日", "H": "例假", "N": "國定假日"}
DISASTER_KINDS = {"typhoon": "颱風", "quake": "地震", "flood": "水災", "epidemic": "疫情", "other": "其他"}
WEEKDAY = "一二三四五六日"


def haversine(lat1, lon1, lat2, lon2):
    R, r = 6371000, math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2 +
         math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def ym_days(ym):
    y, m = int(ym[:4]), int(ym[4:])
    first = dt.date(y, m, 1)
    last = rocdate.month_last(first)
    return first, last


def classify_code(code):
    """月班表系統的代號歸類（含 D／白值→日班、E→晚班、N／夜8→夜班、OFF／休→休息日、例→例假、國→國定假日）。"""
    c = code or ""
    if "例" in c:
        return "例"
    if "國" in c:
        return "國"
    if c.upper().startswith("OFF") or "休" in c:
        return "休"
    if c.upper().startswith("N") or "夜8" in c:
        return "N"
    if c.upper().startswith("E"):
        return "E"
    if c.upper().startswith("D") or "白值" in c:
        return "D"
    return ""


def argb(hex_color):
    """#RRGGBB → Java 的帶號 ARGB 整數（小柯班表助手的顏色格式）。"""
    h = (hex_color or "#9E9E9E").lstrip("#")[-6:]
    v = 0xFF000000 | int(h, 16)
    return v - (1 << 32)


class Sched:
    """某員工某日的班。"""
    __slots__ = ("code", "name", "day_type", "start", "end", "brk", "work_min", "color", "cal")

    def __init__(self, d, sh, cal=""):
        self.code, self.name, self.day_type = sh["code"], sh["name"], sh["day_type"]
        self.color = sh.get("color", "#9E9E9E")
        self.cal = cal
        self.start = self.end = self.brk = None
        self.work_min = 0
        if self.day_type == "W":
            h1, m1 = (int(x) for x in sh["start_t"].split(":"))
            h2, m2 = (int(x) for x in sh["end_t"].split(":"))
            self.start = dt.datetime(d.year, d.month, d.day) + dt.timedelta(hours=h1, minutes=m1)
            self.end = dt.datetime(d.year, d.month, d.day) + dt.timedelta(hours=h2, minutes=m2)
            if self.end <= self.start:
                self.end += dt.timedelta(days=1)
            brk = int(sh.get("break_min") or 0)
            if brk:
                noon = dt.datetime(d.year, d.month, d.day, 12)
                b1 = noon if self.start <= noon and noon + dt.timedelta(minutes=brk) <= self.end else \
                    self.start + dt.timedelta(hours=4)
                self.brk = (b1, b1 + dt.timedelta(minutes=brk))
            self.work_min = int((self.end - self.start).total_seconds() // 60) - brk

    @property
    def is_work(self):
        return self.day_type == "W" and self.work_min > 0

    def overlap(self, a, b):
        """[a, b] 與上班時間重疊的分鐘數（扣除休息時間）。"""
        if not self.is_work:
            return 0
        m = _ov(a, b, self.start, self.end)
        if self.brk:
            m -= _ov(a, b, *self.brk)
        return max(m, 0)

    def as_dict(self):
        return dict(code=self.code, name=self.name, day_type=self.day_type, start=self.start, end=self.end,
                    work_min=self.work_min, color=self.color)


def _ov(a1, a2, b1, b2):
    s, e = max(a1, b1), min(a2, b2)
    return max(int((e - s).total_seconds() // 60), 0)


class AttMixin:
    # ================================================================ 班表
    def shift_map(self):
        return {r["code"]: r for r in self.db.rows("SELECT * FROM shifts")}

    def calendar_map(self, d1, d2):
        return {r["d"]: r for r in self.db.rows("SELECT * FROM calendar WHERE d BETWEEN %s AND %s", (d1, d2))}

    def default_shift(self, emp, d, cal, shifts):
        c = cal.get(d)
        if c and c["kind"] in ("N", "C"):
            return shifts.get("國") or dict(code="國", name="國定假日", day_type="N", start_t="00:00", end_t="00:00")
        wd = d.weekday()
        if wd < 5 or (c and c["kind"] == "W"):
            code = emp.get("shift_group") or "D"
            return shifts.get(code) or shifts.get("D")
        return shifts.get("休" if wd == 5 else "例") or dict(code="休", name="休息日", day_type="R" if wd == 5 else "H",
                                                              start_t="00:00", end_t="00:00")

    def schedules(self, emps, d1, d2):
        """{(員工, 日期): Sched}；有排班用排班，沒有排班用預設班別（週一～五預設班、週六休息日、週日例假、國定假日休）。"""
        shifts = self.shift_map()
        cal = self.calendar_map(d1, d2)
        codes = [e["code"] for e in emps]
        roster = {}
        if codes:
            for r in self.db.rows("SELECT emp, d, shift FROM roster WHERE d BETWEEN %s AND %s AND emp IN (%s)"
                                  % ("%s", "%s", ",".join(["%s"] * len(codes))), (d1, d2, *codes)):
                roster[(r["emp"], r["d"])] = r["shift"]
        out = {}
        d = d1
        while d <= d2:
            for e in emps:
                code = roster.get((e["code"], d))
                sh = shifts.get(code) if code else None
                if code and not sh:
                    base = shifts.get(classify_code(code)) or shifts.get("D")
                    sh = dict(base, code=code, name=code)
                if not sh:
                    sh = self.default_shift(e, d, cal, shifts)
                c = cal.get(d)
                out[(e["code"], d)] = Sched(d, sh, c["kind"] if c else "")
            d += dt.timedelta(days=1)
        return out

    def roster_cell(self, emp, d):
        """排班表點格子後重畫該格用。"""
        self.need("ATT", 1)
        d = date(d)
        s = self.schedules([self.employee(emp)], d, d)[(emp, d)]
        explicit = bool(self.db.value("SELECT 1 FROM roster WHERE emp=%s AND d=%s", (emp, d)))
        return dict(d=d, code=s.code, color=s.color, day_type=s.day_type, set=explicit)

    def my_roster(self, ym):
        """員工自己的整月班表（手機、員工自助用）。"""
        if not self.my_emp:
            raise BizError("此帳號沒有對應員工")
        first, last = ym_days(ym)
        e = self.employee(self.my_emp)
        sch = self.schedules([e], first, last)
        cal = self.calendar_map(first, last)
        out = []
        d = first
        while d <= last:
            s = sch[(e["code"], d)]
            out.append(dict(d=d, code=s.code, name=s.name, color=s.color, day_type=s.day_type, start=s.start,
                            end=s.end, holiday=cal[d]["name"] if d in cal else ""))
            d += dt.timedelta(days=1)
        return out

    def roster_month(self, ym, dept=""):
        self.need("ATT", 1)
        first, last = ym_days(ym)
        emps = self.active_employees(first, last, dept)
        sch = self.schedules(emps, first, last)
        explicit = {(r["emp"], r["d"]) for r in self.db.rows("SELECT emp, d FROM roster WHERE d BETWEEN %s AND %s",
                                                              (first, last))}
        days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
        cal = self.calendar_map(first, last)
        rows = []
        for e in emps:
            cells = []
            stat = dict(work=0, hours=0.0, off=0)
            for d in days:
                s = sch[(e["code"], d)]
                cells.append(dict(d=d, code=s.code, color=s.color, day_type=s.day_type, set=(e["code"], d) in explicit))
                if s.is_work:
                    stat["work"] += 1
                    stat["hours"] += s.work_min / 60
                else:
                    stat["off"] += 1
            rows.append(dict(emp=e["code"], name=e["name"], dept=e["dept"], cells=cells, stat=stat))
        daily = []
        for i, d in enumerate(days):
            cnt = {}
            for r in rows:
                c = r["cells"][i]
                if c["day_type"] == "W":
                    cnt[c["code"]] = cnt.get(c["code"], 0) + 1
            daily.append(cnt)
        return dict(days=days, rows=rows, daily=daily, cal={d: c["name"] for d, c in cal.items()},
                    shifts=self.db.rows("SELECT * FROM shifts WHERE active=1 ORDER BY sort, code"))

    def set_roster(self, emp, d, code, note=""):
        self.need("ATT")
        d = date(d)
        self.check_open(d, "排班")
        code = (code or "").strip()
        if not code:
            self.db.exec("DELETE FROM roster WHERE emp=%s AND d=%s", (emp, d))
        else:
            if not self.db.value("SELECT 1 FROM shifts WHERE code=%s", (code,)):
                raise BizError("班別 %s 不存在，請先到「班別」新增" % code)
            self.db.exec("REPLACE INTO roster (emp, d, shift, note) VALUES (%s, %s, %s, %s)", (emp, d, code, note[:60]))

    def fill_roster(self, emps, d1, d2, pattern, holidays_off=True, overwrite=True):
        """依循環樣式排班（例如 D,D,D,D,D,休,例 或 M,M,E,E,休,例）。國定假日預設排「國」。回傳筆數。"""
        self.need("ATT")
        d1, d2 = date(d1), date(d2)
        self.check_open(d1, "排班")
        pat = [p.strip() for p in re.split(r"[,，\s]+", pattern or "") if p.strip()]
        if not pat:
            raise BizError("請輸入排班樣式，例如 D,D,D,D,D,休,例")
        shifts = self.shift_map()
        bad = [p for p in pat if p not in shifts]
        if bad:
            raise BizError("班別 %s 不存在" % "、".join(bad))
        if (d2 - d1).days > 400:
            raise BizError("一次最多排一年")
        cal = self.calendar_map(d1, d2)
        n = 0
        with self.db.transaction():
            for emp in emps:
                d, i = d1, 0
                while d <= d2:
                    code = pat[i % len(pat)]
                    if holidays_off and d in cal and cal[d]["kind"] in ("N", "C") and shifts[code]["day_type"] == "W":
                        code = "國" if "國" in shifts else code
                    if overwrite or not self.db.value("SELECT 1 FROM roster WHERE emp=%s AND d=%s", (emp, d)):
                        self.db.exec("REPLACE INTO roster (emp, d, shift) VALUES (%s, %s, %s)", (emp, d, code))
                        n += 1
                    d += dt.timedelta(days=1)
                    i += 1
        self.log("roster_fill", ",".join(emps)[:60], "%s～%s %s" % (d1, d2, pattern))
        return n

    def clear_roster(self, emps, d1, d2):
        self.need("ATT")
        d1, d2 = date(d1), date(d2)
        self.check_open(d1, "排班")
        n = 0
        for e in emps:
            n += self.db.exec("DELETE FROM roster WHERE emp=%s AND d BETWEEN %s AND %s", (e, d1, d2))
        return n

    # ---------------------------------------------------------------- 月班表系統 XML
    def export_rcw_xml(self, ym_list, path, dept=""):
        self.need("ATT", 1)
        comp = self.company()
        dname = self.db.value("SELECT name FROM departments WHERE code=%s", (dept,)) if dept else "全公司"
        root = ET.Element("scheduleSystem", company=comp.get("name") or "", department=dname or "")
        sch_el = ET.SubElement(root, "schedules")
        for ym in ym_list:
            m = self.roster_month(ym, dept)
            s = ET.SubElement(sch_el, "schedule", category="assistant", year=str(int(ym[:4])), month=str(int(ym[4:])))
            for r in m["rows"]:
                e = ET.SubElement(s, "employee", empId=r["emp"], name=r["name"])
                for c in r["cells"]:
                    ET.SubElement(e, "entry", day=str(c["d"].day), shift=c["code"])
        ET.indent(root)
        with open(path, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(ET.tostring(root, encoding="utf-8"))
        return path

    def import_rcw_xml(self, path, overwrite=True):
        """匯入月班表系統的 XML：員工以員工編號對應（沒有編號時用姓名）；陌生的班別代號依規則自動建立。
        回傳 dict(months, entries, unknown_emps, new_shifts)。"""
        self.need("ATT")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            raise BizError("XML 格式錯誤：%s" % e)
        if root.tag != "scheduleSystem":
            raise BizError("這不是月班表系統的備份檔（根節點應為 scheduleSystem）")
        by_code = {r["code"]: r["code"] for r in self.db.rows("SELECT code FROM employees")}
        by_name = {r["name"]: r["code"] for r in self.db.rows("SELECT code, name FROM employees")}
        shifts = self.shift_map()
        res = dict(months=[], entries=0, unknown_emps=[], new_shifts=[])
        with self.db.transaction():
            for s in root.iter("schedule"):
                y, m = int(s.get("year") or 0), int(s.get("month") or 0)
                if not (y and 1 <= m <= 12):
                    continue
                first = dt.date(y, m, 1)
                last = rocdate.month_last(first)
                self.check_open(first, "排班")
                res["months"].append("%04d%02d" % (y, m))
                for e in s.iter("employee"):
                    code = by_code.get(e.get("empId") or "") or by_name.get(e.get("name") or "")
                    if not code:
                        res["unknown_emps"].append("%s %s" % (e.get("empId") or "", e.get("name") or ""))
                        continue
                    if overwrite:
                        self.db.exec("DELETE FROM roster WHERE emp=%s AND d BETWEEN %s AND %s", (code, first, last))
                    for en in e.iter("entry"):
                        day, sc = int(en.get("day") or 0), (en.get("shift") or "").strip()
                        if not sc or not 1 <= day <= last.day:
                            continue
                        if sc not in shifts:
                            base = shifts.get(classify_code(sc)) or shifts["D"]
                            self.db.exec("INSERT INTO shifts (code, name, start_t, end_t, break_min, day_type, color, sort, "
                                         "memo) VALUES (%s, %s, %s, %s, %s, %s, %s, 200, '月班表匯入自動建立')",
                                         (sc[:12], sc[:30], base["start_t"], base["end_t"], base["break_min"],
                                          base["day_type"], base["color"]))
                            shifts[sc] = dict(base, code=sc)
                            res["new_shifts"].append(sc)
                        self.db.exec("REPLACE INTO roster (emp, d, shift) VALUES (%s, %s, %s)", (code, dt.date(y, m, day), sc[:12]))
                        res["entries"] += 1
        self.log("roster_xml", ",".join(res["months"])[:60], "%d 筆" % res["entries"])
        return res

    def import_roster_csv(self, ym, path):
        """CSV：第一列標題「員工編號, 姓名, 1, 2, …31」，每格填班別代號。回傳 (筆數, 錯誤)。"""
        self.need("ATT")
        import csv
        from .csvio import read_text
        first, last = ym_days(ym)
        self.check_open(first, "排班")
        rows = list(csv.reader(read_text(path).splitlines()))
        if len(rows) < 2:
            raise BizError("檔案沒有資料")
        head = [h.strip() for h in rows[0]]
        day_cols = {}
        for i, h in enumerate(head):
            m = re.match(r"^(\d{1,2})(日)?$", h) or re.match(r"^\d{1,2}/(\d{1,2})$", h)
            if m and 1 <= int(m.group(1)) <= last.day:
                day_cols[i] = int(m.group(1))
        if not day_cols:
            raise BizError("標題列要有日期欄（1、2、…31）")
        shifts = self.shift_map()
        n, errs = 0, []
        with self.db.transaction():
            for ln, r in enumerate(rows[1:], 2):
                if not r or not r[0].strip():
                    continue
                code = r[0].strip()
                if not self.db.value("SELECT 1 FROM employees WHERE code=%s", (code,)):
                    errs.append("第 %d 列：員工 %s 不存在" % (ln, code))
                    continue
                for i, day in day_cols.items():
                    if i >= len(r) or not r[i].strip():
                        continue
                    sc = r[i].strip()
                    if sc not in shifts:
                        errs.append("第 %d 列 %d 日：班別 %s 不存在" % (ln, day, sc))
                        continue
                    self.db.exec("REPLACE INTO roster (emp, d, shift) VALUES (%s, %s, %s)",
                                 (code, dt.date(first.year, first.month, day), sc))
                    n += 1
        return n, errs

    def roster_csv_template(self, ym, path, dept=""):
        import csv
        m = self.roster_month(ym, dept)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["員工編號", "姓名"] + [str(d.day) for d in m["days"]])
            for r in m["rows"]:
                w.writerow([r["emp"], r["name"]] + [c["code"] for c in r["cells"]])

    # ---------------------------------------------------------------- 小柯班表助手
    def export_xiaoke_shift(self, emp, ym_from, ym_to, path):
        """把員工的班表匯出成小柯班表助手的備份 ZIP（手機「⋯ → 還原班表」）。"""
        if emp != self.my_emp:
            self.need("ATT", 1)
        e = self.employee(emp)
        d1 = ym_days(ym_from)[0]
        d2 = ym_days(ym_to)[1]
        if d2 < d1:
            raise BizError("結束月份不能早於開始月份")
        sch = self.schedules([e], d1, d2)
        used = {}
        days = {}
        for (code, d), s in sorted(sch.items(), key=lambda x: x[0][1]):
            days[d.isoformat()] = s.code
            used[s.code] = s
        shifts = self.shift_map()
        types = []
        for code in sorted(used, key=lambda c: (shifts.get(c, {}).get("sort", 999), c)):
            sh = shifts.get(code) or {}
            s = used[code]
            off = s.day_type != "W"
            types.append(dict(code=code, name=sh.get("name") or s.name, color=argb(sh.get("color") or s.color),
                              start=(sh.get("start_t") or "08:00") if not off else "00:00",
                              end=(sh.get("end_t") or "17:00") if not off else "00:00", off=off,
                              desc=DAY_TYPES.get(s.day_type, ""), hidden=False, pay=0, alarmOn=False,
                              alarmBefore=False, alarmTime="06:30"))
        comp = self.company()
        hol = {r["d"].isoformat(): r["name"] for r in self.db.rows("SELECT d, name FROM calendar WHERE kind IN ('N','C') "
                                                                       "AND d BETWEEN %s AND %s", (d1, d2))}
        data = {"app": "小柯班表助手", "version": 2, "types": types, "patterns": [],
                "data": {"me": {"days": days, "notes": {}}}, "extra": {}, "holidays": hol,
                "profiles": {"me": ("%s班表" % (comp.get("short_name") or comp.get("name") or "公司"))[:20]}}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
        self.log("xk_export", emp, "%s～%s" % (ym_from, ym_to))
        return path

    # ================================================================ 行事曆與災害
    def disasters(self, d1=None, d2=None):
        self.need("ATT", 1)
        sql, args = "SELECT * FROM disasters", ()
        if d1 and d2:
            sql += " WHERE d BETWEEN %s AND %s"
            args = (date(d1), date(d2))
        return self.db.rows(sql + " ORDER BY d DESC, id DESC", args)

    def save_disaster(self, row, did=None):
        """登錄停班事件。row：d, kind, title, scope, period, pay_policy, work_extra, memo。"""
        self.need("ATT")
        d = date(row.get("d"))
        self.check_open(d, "災害停班")
        kind = row.get("kind") or "typhoon"
        if kind not in DISASTER_KINDS:
            raise BizError("事件種類不正確")
        period = row.get("period") or "D"
        if period not in ("D", "A", "P"):
            raise BizError("停班時段不正確")
        vals = (d, kind, (row.get("title") or DISASTER_KINDS[kind] + "停班")[:60], (row.get("scope") or "").strip()[:200],
                period, "U" if row.get("pay_policy") == "U" else "P", Decimal(str(row.get("work_extra") or 0)),
                (row.get("memo") or "")[:200])
        if did:
            self.db.exec("UPDATE disasters SET d=%s, kind=%s, title=%s, scope=%s, period=%s, pay_policy=%s, work_extra=%s, "
                         "memo=%s WHERE id=%s", vals + (did,))
        else:
            did = self.db.exec("INSERT INTO disasters (d, kind, title, scope, period, pay_policy, work_extra, memo, "
                               "created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", vals + (self.uid,))
        self.log("disaster", str(did), "%s %s" % (d, vals[2]))
        return did

    def delete_disaster(self, did):
        self.need("ATT")
        r = self.db.row("SELECT * FROM disasters WHERE id=%s", (did,))
        if r:
            self.check_open(r["d"], "災害停班")
            self.db.exec("DELETE FROM disasters WHERE id=%s", (did,))

    def _disaster_map(self, d1, d2):
        out = {}
        for r in self.db.rows("SELECT * FROM disasters WHERE d BETWEEN %s AND %s", (d1, d2)):
            out.setdefault(r["d"], []).append(r)
        return out

    @staticmethod
    def _closure_window(ev, s: Sched, d):
        if ev["period"] == "D":
            return s.start, s.end
        noon = dt.datetime(d.year, d.month, d.day, 12)
        return (s.start, noon) if ev["period"] == "A" else (noon, s.end)

    # ================================================================ 打卡
    def gps_sites(self):
        return self.db.rows("SELECT * FROM gps_sites WHERE active=1 ORDER BY id")

    def punch(self, kind, lat=None, lon=None, accuracy=None, device="", ip="", emp=None, source="gps", note=""):
        """員工打卡（GPS 或電腦）。回傳 dict(ok, ts, kind, distance, site, msg)。"""
        emp = emp or self.my_emp
        if not emp:
            raise BizError("此帳號沒有對應員工，不能打卡（請系統管理員在「使用者與權限」設定）")
        if emp != self.my_emp:
            self.need("ATT")
        if kind not in ("I", "O"):
            raise BizError("請選擇上班或下班")
        e = self.employee(emp)
        if e["status"] == "Q":
            raise BizError("已離職，不能打卡")
        now = dt.datetime.now().replace(microsecond=0)
        last = self.db.row("SELECT ts, kind FROM punches WHERE emp=%s AND void=0 ORDER BY ts DESC LIMIT 1", (emp,))
        if last and last["kind"] == kind and (now - last["ts"]).total_seconds() < 60:
            raise BizError("一分鐘內已經打過%s卡了" % ("上班" if kind == "I" else "下班"))
        ok, dist, site_id, msg = 1, None, 0, ""
        if source == "gps":
            if lat is None or lon is None:
                raise BizError("沒有取得 GPS 座標，請允許定位後再試")
            lat, lon = float(lat), float(lon)
            acc = int(float(accuracy or 0))
            sites = self.gps_sites()
            if e["gps_site"]:
                sites = [s for s in sites if s["id"] == e["gps_site"]] or sites
            if sites:
                best = min(sites, key=lambda s: haversine(lat, lon, float(s["lat"]), float(s["lon"])))
                dist = int(round(haversine(lat, lon, float(best["lat"]), float(best["lon"]))))
                site_id = best["id"]
                if dist > best["radius"]:
                    ok, msg = 0, "距離「%s」%d 公尺，超出允許範圍 %d 公尺，已記錄為待確認" % (best["name"], dist, best["radius"])
                elif acc and acc > best["max_accuracy"]:
                    ok, msg = 0, "GPS 精確度 %d 公尺不足，已記錄為待確認（請到空曠處再打一次）" % acc
                else:
                    msg = "已在「%s」範圍內（距離 %d 公尺）" % (best["name"], dist)
            else:
                msg = "公司尚未設定打卡地點，僅記錄座標"
            accuracy = acc
        else:
            lat = lon = accuracy = None
        pid = self.db.exec("INSERT INTO punches (emp, ts, kind, source, lat, lon, accuracy, site_id, distance, ok, device, "
                           "ip, note, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                           (emp, now, kind, source, lat, lon, accuracy, site_id, dist, ok, (device or "")[:120],
                            (ip or "")[:45], (note or msg)[:100], self.uid))
        return dict(id=pid, ok=bool(ok), ts=now, kind=kind, distance=dist, msg=msg,
                    text="%s %s 打卡%s" % ("上班" if kind == "I" else "下班", now.strftime("%H:%M"),
                                         "成功" if ok else "（待確認）"))

    def add_punch(self, emp, ts, kind, note="補登"):
        """人資補登打卡（忘記打卡、打卡機故障）。"""
        self.need("ATT")
        if isinstance(ts, str):
            ts = ts.strip()
            m = re.match(r"^(.+?)\s+(\d{1,2}:\d{2})$", ts)
            if not m:
                raise BizError("時間格式：115/11/13 08:55")
            d = date(m.group(1))
            h, mi = (int(x) for x in hhmm(m.group(2)).split(":"))
            ts = dt.datetime(d.year, d.month, d.day, h, mi)
        self.check_open(ts.date(), "打卡")
        if kind not in ("I", "O"):
            raise BizError("請選擇上班或下班")
        self.employee(emp)
        pid = self.db.exec("INSERT INTO punches (emp, ts, kind, source, ok, note, created_by) VALUES (%s, %s, %s, 'fix', 1, "
                           "%s, %s)", (emp, ts, kind, (note or "補登")[:100], self.uid))
        self.log("punch_fix", emp, "%s %s %s" % (ts, kind, note))
        return pid

    def set_punch(self, pid, ok=None, void=None, note=None):
        self.need("ATT")
        p = self.db.row("SELECT * FROM punches WHERE id=%s", (pid,))
        if not p:
            raise BizError("打卡紀錄不存在")
        self.check_open(p["ts"].date(), "打卡")
        if ok is not None:
            self.db.exec("UPDATE punches SET ok=%s WHERE id=%s", (int(bool(ok)), pid))
        if void is not None:
            self.db.exec("UPDATE punches SET void=%s WHERE id=%s", (int(bool(void)), pid))
        if note is not None:
            self.db.exec("UPDATE punches SET note=%s WHERE id=%s", (note[:100], pid))
        self.log("punch_set", str(pid), "ok=%s void=%s" % (ok, void))

    def punches(self, d1, d2, emp="", pending_only=False):
        if emp != self.my_emp or not emp:
            self.need("ATT", 1)
        sql = ("SELECT p.*, e.name, s.name AS site_name FROM punches p JOIN employees e ON e.code=p.emp LEFT JOIN "
               "gps_sites s ON s.id=p.site_id WHERE p.ts BETWEEN %s AND %s")
        args = [dt.datetime.combine(date(d1), dt.time()), dt.datetime.combine(date(d2), dt.time(23, 59, 59))]
        if emp:
            sql += " AND p.emp=%s"
            args.append(emp)
        if pending_only:
            sql += " AND p.ok=0 AND p.void=0"
        rows = self.db.rows(sql + " ORDER BY p.ts DESC", tuple(args))
        for r in rows:
            r["kind_name"] = "上班" if r["kind"] == "I" else "下班"
            r["state"] = "作廢" if r["void"] else ("有效" if r["ok"] else "待確認")
            r["src_name"] = {"gps": "手機 GPS", "pc": "電腦", "fix": "補登", "import": "匯入"}.get(r["source"], r["source"])
        return rows

    def my_today(self):
        """員工自己今天的班與打卡（打卡網頁、首頁用）。"""
        emp = self.my_emp
        if not emp:
            return None
        e = self.employee(emp)
        today = dt.date.today()
        s = self.schedules([e], today, today)[(emp, today)]
        ps = self.db.rows("SELECT ts, kind, ok FROM punches WHERE emp=%s AND void=0 AND ts>=%s ORDER BY ts",
                          (emp, dt.datetime.combine(today, dt.time())))
        return dict(emp=emp, name=e["name"], date=today, shift=s.as_dict(), punches=ps,
                    sites=[dict(name=x["name"], lat=float(x["lat"]), lon=float(x["lon"]), radius=x["radius"])
                           for x in self.gps_sites() if not e["gps_site"] or x["id"] == e["gps_site"]])

    # ================================================================ 出勤計算
    def attendance(self, d1, d2, emps=None, dept=""):
        """出勤日報：每人每日的班別、上下班時間、遲到早退、曠職、請假、停班。"""
        d1, d2 = date(d1), date(d2)
        if emps is None:
            emps = self.active_employees(d1, d2, dept)
        if not emps:
            return []
        comp = self.company()
        grace = int(comp.get("late_grace") or 0)
        sch = self.schedules(emps, d1, d2)
        codes = [e["code"] for e in emps]
        inq = ",".join(["%s"] * len(codes))
        t1 = dt.datetime.combine(d1, dt.time()) - dt.timedelta(hours=8)
        t2 = dt.datetime.combine(d2, dt.time(23, 59, 59)) + dt.timedelta(hours=12)
        pmap = {}
        for p in self.db.rows("SELECT emp, ts, kind FROM punches WHERE void=0 AND ok=1 AND ts BETWEEN %%s AND %%s AND emp IN "
                              "(%s) ORDER BY ts" % inq, (t1, t2, *codes)):
            pmap.setdefault(p["emp"], []).append(p)
        lmap = {}
        for lv in self.db.rows("SELECT r.*, t.name AS lname, t.pay_ratio, t.affects_attend FROM leave_requests r JOIN "
                               "leave_types t ON t.code=r.ltype WHERE r.status=1 AND r.end_at>=%%s AND r.start_at<=%%s AND "
                               "r.emp IN (%s)" % inq, (t1, t2, *codes)):
            lmap.setdefault(lv["emp"], []).append(lv)
        dis = self._disaster_map(d1, d2)
        emp_by = {e["code"]: e for e in emps}
        out = []
        d = d1
        while d <= d2:
            for code in codes:
                e = emp_by[code]
                if (e["hire_date"] and d < e["hire_date"]) or (e["leave_date"] and d > e["leave_date"]):
                    continue
                s = sch[(code, d)]
                rec = dict(emp=code, name=e["name"], dept=e["dept"], d=d, code=s.code, sname=s.name, day_type=s.day_type,
                           start=s.start, end=s.end, work_min=s.work_min, in_ts=None, out_ts=None, late=0, early=0,
                           absent=0, missing=0, leave_min=0, leaves=[], closure_min=0, disaster=None, worked_min=0,
                           status="")
                if s.is_work:
                    lo, hi = s.start - dt.timedelta(hours=4), s.end + dt.timedelta(hours=6)
                else:
                    lo, hi = dt.datetime.combine(d, dt.time(4)), dt.datetime.combine(d, dt.time(4)) + dt.timedelta(days=1)
                ps = [p for p in pmap.get(code, []) if lo <= p["ts"] <= hi]
                ins = [p["ts"] for p in ps if p["kind"] == "I"]
                outs = [p["ts"] for p in ps if p["kind"] == "O"]
                rec["in_ts"] = min(ins) if ins else (ps[0]["ts"] if ps and not outs else None)
                rec["out_ts"] = max(outs) if outs else None
                if rec["in_ts"] and rec["out_ts"] and rec["out_ts"] > rec["in_ts"]:
                    rec["worked_min"] = s.overlap(rec["in_ts"], rec["out_ts"]) if s.is_work else \
                        int((rec["out_ts"] - rec["in_ts"]).total_seconds() // 60)
                # 請假
                cover = []
                if s.is_work:
                    for lv in lmap.get(code, []):
                        m = s.overlap(lv["start_at"], lv["end_at"])
                        if m > 0:
                            rec["leave_min"] += m
                            rec["leaves"].append((lv["ltype"], lv["lname"], m))
                            cover.append((max(lv["start_at"], s.start), min(lv["end_at"], s.end)))
                # 災害停班
                for ev in dis.get(d, []):
                    if ev["scope"] and e["dept"] not in [x.strip() for x in ev["scope"].split(",")]:
                        continue
                    rec["disaster"] = ev
                    if s.is_work:
                        w1, w2 = self._closure_window(ev, s, d)
                        rec["closure_min"] = s.overlap(w1, w2)
                        cover.append((w1, w2))
                rec["leave_min"] = min(rec["leave_min"], s.work_min)
                now = dt.datetime.now()
                if s.is_work and e["punch_required"] and now < s.end:
                    # 班還沒結束：只判斷遲到，不判斷曠職、早退、缺卡
                    if rec["in_ts"]:
                        lt = int((rec["in_ts"] - s.start).total_seconds() // 60)
                        rec["late"] = lt if lt > grace and not rec["leave_min"] else 0
                    rec["status"] = ("遲到%d分、" % rec["late"] if rec["late"] else "") +                         ("上班中" if rec["in_ts"] else ("未到上班時間" if now < s.start else "尚未打卡"))
                    out.append(rec)
                    continue
                if s.is_work and e["punch_required"]:
                    need = s.work_min - rec["leave_min"] - rec["closure_min"]
                    if need > 0:
                        if not ps:
                            rec["absent"] = need
                        else:
                            st = s.start
                            for a, b in sorted(cover):
                                if a <= st < b:
                                    st = b
                            en = s.end
                            for a, b in sorted(cover, reverse=True):
                                if a < en <= b:
                                    en = a
                            if rec["in_ts"]:
                                lt = int((rec["in_ts"] - st).total_seconds() // 60)
                                rec["late"] = lt if lt > grace else 0
                            if rec["out_ts"]:
                                ea = int((en - rec["out_ts"]).total_seconds() // 60)
                                rec["early"] = max(ea, 0)
                            else:
                                rec["missing"] = 1
                            if not rec["in_ts"] or not ins:
                                rec["missing"] = 1
                rec["status"] = self._att_status(rec)
                out.append(rec)
            d += dt.timedelta(days=1)
        return out

    @staticmethod
    def _att_status(r):
        tags = []
        if r["day_type"] != "W":
            tags.append(DAY_TYPES.get(r["day_type"], "休"))
        if r["disaster"]:
            tags.append(r["disaster"]["title"])
        if r["leaves"]:
            tags.append("、".join(sorted({x[1] for x in r["leaves"]})))
        if r["absent"]:
            tags.append("曠職")
        if r["late"]:
            tags.append("遲到%d分" % r["late"])
        if r["early"]:
            tags.append("早退%d分" % r["early"])
        if r["missing"]:
            tags.append("缺打卡")
        if not tags and r["day_type"] == "W":
            tags.append("正常")
        return "、".join(tags)

    def attendance_daily(self, d1, d2, dept=""):
        """出勤日報畫面用（需要出勤管理查詢權限）。"""
        self.need("ATT", 1)
        return self.attendance(d1, d2, None, dept)

    def attendance_month(self, ym, dept="", emp=""):
        """出勤月報（每人一列）。"""
        if emp != self.my_emp or not emp:
            self.need("ATT", 1)
        first, last = ym_days(ym)
        emps = self.active_employees(first, last, dept)
        if emp:
            emps = [e for e in emps if e["code"] == emp]
        recs = self.attendance(first, last, emps)
        ot = {r["emp"]: Decimal(r["h"] or 0) for r in self.db.rows(
            "SELECT emp, SUM(hours) h FROM overtime WHERE status=1 AND d BETWEEN %s AND %s GROUP BY emp", (first, last))}
        out = {}
        for r in recs:
            o = out.setdefault(r["emp"], dict(emp=r["emp"], name=r["name"], dept=r["dept"], sched_days=0, attend_days=0,
                                              late_cnt=0, late_min=0, early_min=0, absent_min=0, missing=0,
                                              leave_hours=Decimal(0), closure_days=0, ot_hours=ot.get(r["emp"], D0)))
            if r["day_type"] == "W" and r["work_min"]:
                o["sched_days"] += 1
                if r["in_ts"] or r["out_ts"]:
                    o["attend_days"] += 1
            o["late_cnt"] += 1 if r["late"] else 0
            o["late_min"] += r["late"]
            o["early_min"] += r["early"]
            o["absent_min"] += r["absent"]
            o["missing"] += r["missing"]
            o["leave_hours"] += Decimal(r["leave_min"]) / 60
            o["closure_days"] += 1 if r["closure_min"] else 0
        for o in out.values():
            o["leave_hours"] = o["leave_hours"].quantize(Decimal("0.01"))
            o["absent_hours"] = (Decimal(o["absent_min"]) / 60).quantize(Decimal("0.01"))
        return list(out.values())

    def today_board(self):
        """首頁：今天應出勤、已打卡、請假、未到的人數。"""
        today = dt.date.today()
        recs = self.attendance(today, today) if self.can("ATT", 1) else []
        work = [r for r in recs if r["day_type"] == "W" and r["work_min"]]
        return dict(scheduled=len(work), punched=sum(1 for r in work if r["in_ts"]),
                    on_leave=sum(1 for r in work if r["leave_min"] >= r["work_min"]),
                    not_in=[r for r in work if not r["in_ts"] and r["leave_min"] < r["work_min"] and not r["closure_min"]
                            and r["start"] and r["start"] <= dt.datetime.now()],
                    pending=self.db.value("SELECT COUNT(*) FROM punches WHERE ok=0 AND void=0") or 0)


_ = io
