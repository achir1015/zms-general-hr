"""會計拋轉：把薪資、公司負擔保費、薪資發放、職災費用、未休特休估列，依「會計科目對照」產生傳票，
送到「資料助秘之一般公司會計」（與進銷存相同的 zms-gl 拋轉格式）。

送法有兩種：
1. 拋轉檔（.zmsgl，JSON）：在會計系統「傳票作業 → 進銷存拋轉」匯入（同一個匯入功能）。
2. 直接傳送：會計系統開著「手機連線服務」時，用會計系統的帳號密碼直接送過去。

會計端匯入後產生「未審核」傳票；同一批次（batch_uid）不會重複匯入。拋轉過的薪資批次會被鎖住，要修改須先取消拋轉。

分錄規則：
* 薪資（每個薪資批次一張，日期＝月底；獎金批次＝發放日）：
  借 薪資支出（依部門費用別：管理 6211、推銷 6111、研發 6311…；加班費 6228、伙食費 6224 等依薪資科目設定）
  貸 代扣勞健保 2173、代扣自提勞退 2175、代扣補充保費 2174、代扣所得稅 2172、借支 1172…、應付薪資 2141（實發）
  請假、遲到、曠職扣款直接減少薪資支出（貸方）。
* 公司負擔保費（每月一張）：借 勞健保費 6226（勞保、就保、職災、墊償、健保、投保單位補充保費）、退休金 6227／貸 應付費用 2142
* 薪資發放（批次標示已發放後）：借 應付薪資／貸 銀行存款
* 職災費用（公司支付部分）：借 職災費用科目／貸 銀行存款（保險給付抵充只做紀錄、不入帳）
* 未休特休估列（年底）：借 薪資支出／貸 應付休假給付 2145，並於次月 1 日迴轉
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

from . import APP_NAME, APP_VERSION, rocdate
from .attendance import ym_days
from .core import D0, BizError, date, yuan
from .seed import GL_DEFAULT, GL_MAP

SCOPES = {"payroll": "薪資與公司負擔保費", "paid": "薪資發放", "occ": "職災費用", "accrual": "未休特休估列"}
FORMAT = "zms-gl"


class GLMixin:
    # ================================================================ 科目對照
    def gl_map(self):
        rows = {r["k"]: r for r in self.db.rows("SELECT * FROM gl_map")}
        out = []
        for k, a, n, desc in GL_MAP:
            r = rows.get(k) or {}
            out.append(dict(k=k, account=r.get("account") or a, name=r.get("name") or n, desc=desc, default=a))
        return out

    def save_gl_map(self, items):
        self.need("GL")
        for it in items:
            k = it["k"]
            if k not in GL_DEFAULT:
                continue
            a = (it.get("account") or "").strip()
            n = (it.get("name") or "").strip()
            if not (a.isdigit() and len(a) == 4):
                raise BizError("%s 的科目代號要是四碼明細科目" % GL_DEFAULT[k][1])
            self.db.exec("REPLACE INTO gl_map (k, account, name) VALUES (%s, %s, %s)", (k, a, n or GL_DEFAULT[k][1]))
        self.log("gl_map")

    def _acct(self):
        return {r["k"]: (r["account"], r["name"]) for r in self.gl_map()}

    # ================================================================ 未休特休估列
    def accrue_leave(self, ym):
        """估列 ym 月底未休特休（應付休假給付）。重新估列會覆蓋尚未拋轉的估列。"""
        self.need("GL")
        from .payroll import ym_of
        ym = ym_of(ym)
        old = self.db.row("SELECT * FROM leave_accruals WHERE ym=%s", (ym,))
        if old and old["gl_batch_id"]:
            raise BizError("此月份的估列已拋轉，請先取消拋轉")
        rows = self.unused_leave_liability(ym_days(ym)[1])
        amt = sum((r["amount"] for r in rows), D0)
        detail = json.dumps([dict(emp=r["emp"], dept=r["dept"], hours=str(r["hours"]), amount=str(r["amount"]))
                             for r in rows], ensure_ascii=False)
        self.db.exec("REPLACE INTO leave_accruals (ym, amount, detail, created_by) VALUES (%s, %s, %s, %s)",
                     (ym, amt, detail, self.uid))
        self.log("leave_accrue", ym, str(amt))
        return amt, len(rows)

    # ================================================================ 待拋轉
    def gl_pending(self, date_from, date_to):
        f, t = date(date_from), date(date_to)
        cnt = dict(payroll=0, paid=0, occ=0, accrual=0)
        for r in self.db.rows("SELECT * FROM payroll_runs WHERE status>=1"):
            if r["gl_batch_id"] is None and f <= self._run_date(r) <= t:
                cnt["payroll"] += 1
            if r["status"] == 2 and r["pay_gl_batch_id"] is None and f <= r["pay_date"] <= t:
                cnt["paid"] += 1
        cnt["occ"] = self.db.value("SELECT COUNT(*) FROM occ_costs WHERE payer='C' AND gl_batch_id IS NULL AND d BETWEEN "
                                   "%s AND %s", (f, t)) or 0
        for r in self.db.rows("SELECT ym FROM leave_accruals WHERE gl_batch_id IS NULL AND amount>0"):
            if f <= ym_days(r["ym"])[1] <= t:
                cnt["accrual"] += 1
        return cnt

    def gl_first_pending(self):
        ds = []
        for r in self.db.rows("SELECT * FROM payroll_runs WHERE status>=1 AND (gl_batch_id IS NULL OR "
                              "(status=2 AND pay_gl_batch_id IS NULL))"):
            ds.append(self._run_date(r) if r["gl_batch_id"] is None else r["pay_date"])
        d = self.db.value("SELECT MIN(d) FROM occ_costs WHERE payer='C' AND gl_batch_id IS NULL")
        if d:
            ds.append(d)
        return min(ds) if ds else None

    @staticmethod
    def _run_date(r):
        return ym_days(r["ym"])[1] if r["kind"] == "M" else r["pay_date"]

    # ================================================================ 產生分錄
    def gl_preview(self, date_from, date_to, scopes=None):
        """回傳 (傳票清單, 來源清單)；不寫入資料庫。"""
        self.need("GL", 1)
        f, t = date(date_from), date(date_to)
        if f > t:
            raise BizError("起始日不能晚於結束日")
        scopes = set(scopes or SCOPES)
        A = self._acct()
        sal_key = {"A": "SAL_A", "S": "SAL_S", "M": "SAL_M", "R": "SAL_R"}
        vouchers, sources = [], []

        def acct(code, cost_type):
            if not code:
                return A[sal_key.get(cost_type, "SAL_A")][0]
            if code.startswith("@"):
                return A[code[1:]][0]
            return code

        def V(ref, d, memo, lines, src):
            merged = {}
            for ln in lines:
                if not ln["amount"]:
                    continue
                k = (ln["account"], ln["dept"], ln["side"], ln["summary"])
                merged[k] = merged.get(k, D0) + ln["amount"]
            out = []
            for (a, dept, side, summ), amt in merged.items():
                if amt < 0:
                    side, amt = ("C" if side == "D" else "D"), -amt
                if amt == 0:
                    continue
                out.append(dict(account=a, summary=summ[:60], debit=amt if side == "D" else D0,
                                credit=amt if side == "C" else D0, partner_kind="", partner="", dept=dept))
            out.sort(key=lambda x: (0 if x["debit"] else 1, x["account"], x["dept"]))
            dr = sum((x["debit"] for x in out), D0)
            cr = sum((x["credit"] for x in out), D0)
            if dr != cr:
                raise BizError("%s 借貸不平衡（借 %s、貸 %s），請檢查薪資科目的會計科目設定" % (ref, dr, cr))
            if out:
                vouchers.append(dict(ref=ref, date=d, type="轉", memo=memo, lines=out, total=dr))
                sources.append(src)

        def L(account, amount, side, summary, dept=""):
            return dict(account=account, amount=yuan(amount or 0), side=side, summary=summary, dept=dept or "")

        if "payroll" in scopes:
            for r in self.db.rows("SELECT * FROM payroll_runs WHERE status>=1 AND gl_batch_id IS NULL ORDER BY ym, id"):
                d = self._run_date(r)
                if not f <= d <= t:
                    continue
                lines = []
                net = D0
                for s in self.db.rows("SELECT * FROM payslips WHERE run_id=%s", (r["id"],)):
                    net += s["net"]
                    for ln in self.db.rows("SELECT * FROM payslip_lines WHERE slip_id=%s", (s["id"],)):
                        a = acct(ln["gl_account"], s["cost_type"])
                        side = "D" if ln["kind"] == "E" else "C"
                        summ = ln["name"] if (ln["gl_account"] or ln["kind"] == "D") else "薪資"
                        lines.append(L(a, ln["amount"], side, "%s %s" % (r["title"], summ), s["dept"]))
                lines.append(L(A["SALARY_PAY"][0], net, "C", "%s 實發" % r["title"]))
                V("PAY%d" % r["id"], d, "%s（%d 人）" % (r["title"], r["emp_count"]), lines, [("run", r["id"])])
                if r["kind"] == "M":
                    lines = []
                    tot = D0
                    for s in self.db.rows("SELECT dept, SUM(labor_er+occ_er+fund_er+nhi_er) ins, SUM(pension_er) pen FROM "
                                          "payslips WHERE run_id=%s GROUP BY dept", (r["id"],)):
                        lines.append(L(A["INS_ER"][0], s["ins"], "D", "公司負擔勞健保、職災、墊償", s["dept"]))
                        lines.append(L(A["PENSION_ER"][0], s["pen"], "D", "公司提繳勞退 6%", s["dept"]))
                        tot += Decimal(s["ins"] or 0) + Decimal(s["pen"] or 0)
                    sup = self.db.row("SELECT * FROM nhi_employer_sup WHERE ym=%s AND gl_batch_id IS NULL", (r["ym"],))
                    if sup and sup["premium"]:
                        lines.append(L(A["INS_ER"][0], sup["premium"], "D", "投保單位二代健保補充保費"))
                        tot += Decimal(sup["premium"])
                    lines.append(L(A["ACCRUED"][0], tot, "C", "應付勞保局、健保署、勞退"))
                    V("INS%d" % r["id"], d, "%s 公司負擔保費" % rocdate.ym_show(r["ym"]), lines,
                      [("ins", r["id"])] + ([("sup", r["ym"])] if sup and sup["premium"] else []))
        if "paid" in scopes:
            for r in self.db.rows("SELECT * FROM payroll_runs WHERE status=2 AND pay_gl_batch_id IS NULL AND pay_date BETWEEN "
                                  "%s AND %s ORDER BY pay_date, id", (f, t)):
                V("BANK%d" % r["id"], r["pay_date"], "發放%s" % r["title"],
                  [L(A["SALARY_PAY"][0], r["net"], "D", "發放%s" % r["title"]),
                   L(A["BANK"][0], r["net"], "C", "薪資轉帳")], [("pay", r["id"])])
        if "occ" in scopes:
            from .occ import COST_KIND
            for x in self.db.rows("SELECT x.*, c.case_no, e.name, e.dept FROM occ_costs x JOIN occ_cases c ON c.id=x.case_id "
                                  "JOIN employees e ON e.code=c.emp WHERE x.payer='C' AND x.gl_batch_id IS NULL AND x.d "
                                  "BETWEEN %s AND %s ORDER BY x.d, x.id", (f, t)):
                summ = "職災 %s %s %s" % (x["case_no"], x["name"], COST_KIND.get(x["kind"], ""))
                V("OCC%d" % x["id"], x["d"], summ, [L(A["OCC_EXP"][0], x["amount"], "D", summ, x["dept"]),
                                                    L(A["BANK"][0], x["amount"], "C", summ)], [("occ", x["id"])])
        if "accrual" in scopes:
            ct = {r["code"]: r["cost_type"] for r in self.db.rows("SELECT code, cost_type FROM departments")}
            for a in self.db.rows("SELECT * FROM leave_accruals WHERE gl_batch_id IS NULL AND amount>0 ORDER BY ym"):
                d = ym_days(a["ym"])[1]
                if not f <= d <= t:
                    continue
                by_dept = {}
                for it in json.loads(a["detail"] or "[]"):
                    by_dept[it.get("dept", "")] = by_dept.get(it.get("dept", ""), D0) + Decimal(it["amount"])
                lines = [L(acct("", ct.get(dp, "A")), v, "D", "估列未休特休", dp) for dp, v in by_dept.items()]
                lines.append(L(A["LEAVE_ACCR"][0], a["amount"], "C", "應付休假給付"))
                V("ACC%s" % a["ym"], d, "%s 未休特休估列" % rocdate.ym_show(a["ym"]), lines, [("acc", a["ym"])])
                rev = [dict(x, side="C" if x["side"] == "D" else "D", summary="迴轉" + x["summary"]) for x in lines]
                V("ACR%s" % a["ym"], d + dt.timedelta(days=1), "迴轉 %s 未休特休估列" % rocdate.ym_show(a["ym"]), rev, [])
        return vouchers, sources

    def next_batch_no(self):
        prefix = "HR" + rocdate.compact(rocdate.today())
        last = self.db.value("SELECT MAX(batch_no) FROM gl_batches WHERE batch_no LIKE %s", (prefix + "%",))
        return "%s%03d" % (prefix, int(last[len(prefix):]) + 1 if last else 1)

    def create_gl_batch(self, date_from, date_to, scopes=None):
        self.need("GL")
        vouchers, sources = self.gl_preview(date_from, date_to, scopes)
        if not vouchers:
            raise BizError("這段期間沒有尚未拋轉的資料（薪資批次要先「確認」才能拋轉）")
        comp = self.company()
        A = self._acct()
        no = self.next_batch_no()
        uid = "%s-HR-%s" % (comp.get("tax_id") or "ZMS", uuid.uuid4().hex)
        used = {x["account"] for v in vouchers for x in v["lines"]}
        acct_names = {a: n for a, n in A.values()}
        for p in self.db.rows("SELECT gl_account, name FROM pay_items WHERE gl_account<>'' AND gl_account NOT LIKE '@%%'"):
            acct_names.setdefault(p["gl_account"], p["name"])
        depts = sorted({x["dept"] for v in vouchers for x in v["lines"] if x["dept"]})
        dinfo = [dict(code=d, name=self.db.value("SELECT name FROM departments WHERE code=%s", (d,)) or d) for d in depts]
        payload = dict(
            format=FORMAT, version=1, batch_uid=uid, batch_no=no, source=APP_NAME, source_version=APP_VERSION,
            company=dict(name=comp.get("name", ""), tax_id=comp.get("tax_id", "")),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"), created_by=self.user["name"] if self.user else "",
            date_from=date(date_from).isoformat(), date_to=date(date_to).isoformat(),
            accounts=[dict(code=a, name=acct_names.get(a, "")) for a in sorted(used)],
            partners=[], departments=dinfo,
            vouchers=[dict(ref=v["ref"], date=v["date"].isoformat(), type=v["type"], memo=v["memo"],
                           lines=[dict(account=x["account"], summary=x["summary"], debit=str(x["debit"]),
                                       credit=str(x["credit"]), partner_kind="", partner="", dept=x["dept"])
                                  for x in v["lines"]]) for v in vouchers])
        total = sum((v["total"] for v in vouchers), D0)
        sc = ",".join(sorted(set(scopes or SCOPES)))
        with self.db.transaction():
            bid = self.db.exec("INSERT INTO gl_batches (batch_no, batch_uid, date_from, date_to, scope, voucher_count, "
                               "total, payload, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                               (no, uid, date(date_from), date(date_to), sc, len(vouchers), total,
                                json.dumps(payload, ensure_ascii=False), self.uid))
            for src in sources:
                for kind, key in src:
                    if kind == "run":
                        self.db.exec("UPDATE payroll_runs SET gl_batch_id=%s WHERE id=%s", (bid, key))
                    elif kind == "pay":
                        self.db.exec("UPDATE payroll_runs SET pay_gl_batch_id=%s WHERE id=%s", (bid, key))
                    elif kind == "sup":
                        self.db.exec("UPDATE nhi_employer_sup SET gl_batch_id=%s WHERE ym=%s", (bid, key))
                    elif kind == "occ":
                        self.db.exec("UPDATE occ_costs SET gl_batch_id=%s WHERE id=%s", (bid, key))
                    elif kind == "acc":
                        self.db.exec("UPDATE leave_accruals SET gl_batch_id=%s WHERE ym=%s", (bid, key))
        self.log("gl_batch", no, "%d 張傳票 %s" % (len(vouchers), total))
        return bid

    def gl_batches(self, limit=200):
        self.need("GL", 1)
        return self.db.rows("SELECT id, batch_no, batch_uid, date_from, date_to, scope, method, status, voucher_count, "
                            "total, result, created_by, created_at FROM gl_batches ORDER BY id DESC LIMIT %s", (limit,))

    def gl_batch(self, bid):
        b = self.db.row("SELECT * FROM gl_batches WHERE id=%s", (bid,))
        if not b:
            raise BizError("拋轉批次不存在")
        b["data"] = json.loads(b["payload"] or "{}")
        return b

    def export_gl_batch(self, bid, path):
        self.need("GL")
        b = self.gl_batch(bid)
        if b["status"] == 9:
            raise BizError("此批次已取消")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(b["data"], f, ensure_ascii=False, indent=1)
        self.db.exec("UPDATE gl_batches SET method='file', result=%s WHERE id=%s",
                     ("已匯出拋轉檔 %s" % time.strftime("%Y-%m-%d %H:%M"), bid))
        self.log("gl_export", b["batch_no"], path)

    def cancel_gl_batch(self, bid, remote=None):
        """取消拋轉：解除鎖定。已直接送到會計系統的批次，會先請會計系統刪除（傳票須仍未審核）。"""
        self.need("GL")
        b = self.gl_batch(bid)
        if b["status"] == 9:
            return
        if b["status"] == 2 and remote:
            remote.call("cancel_gl_import", b["batch_uid"])
        with self.db.transaction():
            self.db.exec("UPDATE payroll_runs SET gl_batch_id=NULL WHERE gl_batch_id=%s", (bid,))
            self.db.exec("UPDATE payroll_runs SET pay_gl_batch_id=NULL WHERE pay_gl_batch_id=%s", (bid,))
            for table in ("occ_costs", "leave_accruals", "nhi_employer_sup"):
                self.db.exec("UPDATE %s SET gl_batch_id=NULL WHERE gl_batch_id=%%s" % table, (bid,))
            self.db.exec("UPDATE gl_batches SET status=9, result=CONCAT(result, ' ／已取消') WHERE id=%s", (bid,))
        self.log("gl_cancel", b["batch_no"])

    def send_gl_batch(self, bid, remote):
        """直接傳送到會計系統（remote＝AcctClient）。"""
        self.need("GL")
        b = self.gl_batch(bid)
        if b["status"] == 9:
            raise BizError("此批次已取消")
        res = remote.call("import_gl_batch", b["data"])
        nos = res.get("voucher_nos") or []
        text = "已送達會計系統：%d 張傳票 %s" % (len(nos), ("%s～%s" % (nos[0], nos[-1])) if nos else "")
        self.db.exec("UPDATE gl_batches SET status=2, method='api', result=%s WHERE id=%s", (text[:500], bid))
        self.log("gl_send", b["batch_no"], text)
        return res


# ================================================================ 會計系統連線（直接傳送）
class AcctClient:
    """連到「資料助秘之一般公司會計」的手機連線服務（http://電腦:8765）。"""

    def __init__(self, url, uid, pw, timeout=20):
        self.url = (url or "").strip().rstrip("/")
        if self.url and not self.url.startswith("http"):
            self.url = "http://" + self.url
        self.uid, self.pw, self.timeout = uid, pw, timeout
        self.token = None

    def _post(self, path, body, token=None):
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error")
            except Exception:
                msg = str(e)
            raise BizError("會計系統回應錯誤：%s" % msg)
        except (urllib.error.URLError, OSError) as e:
            raise BizError("連不到會計系統（%s）：請確認會計系統已開啟，並在「系統管理 → 手機連線」打開連線服務。%s"
                           % (self.url, getattr(e, "reason", e)))

    def ping(self):
        req = urllib.request.Request(self.url + "/api/ping")
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            raise BizError("連不到會計系統（%s）：%s" % (self.url, e))

    def login(self):
        r = self._post("/api/login", dict(uid=self.uid, pw=self.pw))
        if "token" not in r:
            raise BizError("會計系統登入失敗：%s" % r.get("error", ""))
        self.token = r["token"]
        return r

    def call(self, method, *args, **kwargs):
        if not self.token:
            self.login()
        r = self._post("/api/call", dict(obj="books", method=method, args=list(args), kwargs=kwargs), self.token)
        if "biz" in r:
            raise BizError("會計系統：%s" % r["biz"])
        if "error" in r:
            raise BizError("會計系統：%s" % r["error"])
        return _plain(r.get("result"))


def _plain(o):
    """會計系統回傳的 {"$d": "1.00"} 之類還原成一般值。"""
    if isinstance(o, dict):
        if len(o) == 1 and next(iter(o)) in ("$d", "$date", "$dt"):
            k, v = next(iter(o.items()))
            return Decimal(v) if k == "$d" else v
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_plain(x) for x in o]
    return o

