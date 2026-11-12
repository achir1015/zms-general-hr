"""CSV 匯入／範本（Excel 另存 CSV 即可；Big5 與 UTF-8 都能讀）：員工名冊、部門、班別等基本資料、
每月變動輸入（獎金、扣款）、期初特休與補休餘額。"""
import csv

from .core import MASTERS, BizError
from .people import EMP_FIELDS

SAMPLES = {
    "employees": [dict(code="E001", name="王大明", id_no="A123456789", gender="男", birthday="70/05/12", nationality="本國",
                       hire_date="110/03/01", dept="A", title="經理", emp_type="月薪", status="在職", base_salary="52000",
                       mobile="0912-345-678", bank_code="0040037", bank_account="123456789012", labor_ins="是",
                       employment_ins="是", occ_ins="是", nhi="是", pension="是", nhi_dependents="1", pension_self="0",
                       tax_mode="依扣繳稅額表（概算）", tax_dependents="0", punch_required="是")],
    "departments": [dict(code="S", name="業務部", cost_type="推銷", active="是")],
}


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp950", "big5hkscs"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BizError("檔案編碼無法辨識，請用 Excel「另存新檔 → CSV UTF-8」")


def _fields(name):
    if name == "employees":
        return [(k, t, typ) for k, t, typ in EMP_FIELDS]
    m = MASTERS[name]
    return [(k, t, typ) for k, t, typ, _ in m["fields"]]


def master_template(name, path):
    fields = _fields(name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([t for _, t, _ in fields])
        for s in SAMPLES.get(name, []):
            w.writerow([s.get(k, "") for k, _, _ in fields])


def _convert(typ, v):
    v = v.strip()
    if typ == "b":
        return v not in ("否", "0", "N", "n", "no", "False", "false", "")
    if typ.startswith("sel:") and v:
        opts = dict(x.split("=") for x in typ[4:].split(","))
        return next((a for a, b in opts.items() if v in (a, b)), v)
    return v


def import_masters(biz, name, path):
    """依標題列對應欄位；代號已存在就更新、不存在就新增。回傳 (成功筆數, 錯誤清單)。"""
    fields = _fields(name)
    rows = list(csv.reader(read_text(path).splitlines()))
    if len(rows) < 2:
        raise BizError("檔案沒有資料（第一列要是標題）")
    titles = {t: k for k, t, _ in fields}
    titles.update({k: k for k, _, _ in fields})
    cols = [titles.get(h.strip()) for h in rows[0]]
    key = "code" if name == "employees" else MASTERS[name]["key"]
    if key != "id" and key not in cols:
        raise BizError("找不到「%s」欄，請用範本的標題列" % fields[0][1])
    types = {k: t for k, _, t in fields}
    ok, errs = 0, []
    if name == "employees":
        existing = {r["code"] for r in biz.db.rows("SELECT code FROM employees")}
    else:
        existing = {str(r[key]) for r in biz.master_rows(name)} if key != "id" else set()
    for i, r in enumerate(rows[1:], 2):
        if not any(x.strip() for x in r):
            continue
        row = {}
        for k, v in zip(cols, r):
            if k:
                row[k] = _convert(types.get(k, "s"), v)
        try:
            if name == "employees":
                for k, _, t in fields:
                    if t == "b" and k not in row:
                        row[k] = True
                biz.save_employee(row, str(row.get("code", "")) not in existing)
            else:
                for k, _, t in fields:
                    if t == "b" and k not in row:
                        row[k] = True
                biz.save_master(name, row, str(row.get(key, "")) not in existing)
            existing.add(str(row.get(key, "")))
            ok += 1
        except BizError as e:
            errs.append("第 %d 列：%s" % (i, e))
    return ok, errs


def inputs_template(path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["員工編號", "薪資科目", "金額", "說明"])
        w.writerow(["E001", "PERF", "5000", "第三季績效獎金"])
        w.writerow(["E002", "ADVANCE", "3000", "借支扣回"])


def import_inputs(biz, ym, run_kind, path):
    rows = list(csv.reader(read_text(path).splitlines()))
    ok, errs = 0, []
    for i, r in enumerate(rows[1:], 2):
        if len(r) < 3 or not r[0].strip():
            continue
        try:
            biz.add_pay_input(ym, run_kind, r[0].strip(), r[1].strip().split(" ")[0], r[2], r[3] if len(r) > 3 else "")
            ok += 1
        except BizError as e:
            errs.append("第 %d 列：%s" % (i, e))
    return ok, errs


def balances_template(path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["員工編號", "種類（特休／補休）", "剩餘時數", "可使用起日", "可使用迄日", "說明"])
        w.writerow(["E001", "特休", "40", "115/03/01", "116/02/28", "導入時剩餘特休"])


def import_balances(biz, path):
    """期初餘額：導入系統時，把人工紀錄的剩餘特休、補休時數轉成額度。"""
    rows = list(csv.reader(read_text(path).splitlines()))
    ok, errs = 0, []
    for i, r in enumerate(rows[1:], 2):
        if len(r) < 5 or not r[0].strip():
            continue
        kind = "C" if "補" in r[1] or r[1].strip().upper() == "C" else "A"
        try:
            biz.add_grant(r[0].strip(), kind, r[3], r[4], r[2], (r[5] if len(r) > 5 else "") or "期初餘額")
            ok += 1
        except BizError as e:
            errs.append("第 %d 列：%s" % (i, e))
    return ok, errs
