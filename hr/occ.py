"""職業災害（公傷）：案件、公傷病假、醫療與補償費用、保險給付抵充。

依勞基法第 59 條與勞工職業災害保險及保護法：
* 醫療期間不能工作：雇主按「原領工資」補償（請「公傷病假」，薪資照發；計薪時以「公傷病假工資補償」免稅項目發給）。
* 職災保險傷病給付（不能工作第 4 日起）：前 2 個月平均月投保薪資 70%、之後 50%，可抵充雇主的工資補償。
* 必需的醫療費用由雇主補償（可抵充保險給付）；失能、死亡依法補償。
* 重大職災（死亡、罹災 3 人以上…）應於 8 小時內通報勞動檢查機構。
公司支付的醫療、失能、死亡補償與其他費用，會計拋轉時：借 職災費用／貸 銀行存款；保險給付（抵充）只做紀錄。
"""
import datetime as dt
from decimal import Decimal

from . import rocdate
from .core import D0, BizError, date, yuan

KIND = {"W": "工作場所", "C": "上下班途中", "D": "職業病", "O": "出差／公出"}
STATUS = {"T": "治療中", "R": "已復工", "C": "結案"}
COST_KIND = {"medical": "醫療費用", "wage": "工資補償", "disab": "失能補償", "death": "死亡補償", "other": "其他費用",
             "ins": "保險給付（抵充）"}


class OccMixin:
    def occ_cases(self, status=""):
        self.need("OCC", 1)
        rows = self.db.rows("SELECT c.*, e.name, e.dept FROM occ_cases c JOIN employees e ON e.code=c.emp" +
                            (" WHERE c.status=%s" if status else "") + " ORDER BY c.injury_at DESC",
                            (status,) if status else ())
        for r in rows:
            r["kind_name"] = KIND.get(r["kind"], "")
            r["status_name"] = STATUS.get(r["status"], "")
            s = self.occ_summary(r["id"])
            r.update(s)
        return rows

    def occ_case(self, cid):
        self.need("OCC", 1)
        c = self.db.row("SELECT c.*, e.name FROM occ_cases c JOIN employees e ON e.code=c.emp WHERE c.id=%s", (cid,))
        if not c:
            raise BizError("職災案件不存在")
        c["costs"] = self.db.rows("SELECT * FROM occ_costs WHERE case_id=%s ORDER BY d, id", (cid,))
        for x in c["costs"]:
            x["kind_name"] = COST_KIND.get(x["kind"], x["kind"])
        c["leaves"] = self.db.rows("SELECT r.*, t.name AS lname FROM leave_requests r JOIN leave_types t ON t.code=r.ltype "
                                   "WHERE r.occ_case=%s AND r.status IN (0,1) ORDER BY r.start_at", (cid,))
        c.update(self.occ_summary(cid))
        return c

    def occ_summary(self, cid):
        tot = {r["kind"]: Decimal(r["s"] or 0) for r in self.db.rows(
            "SELECT kind, SUM(amount) s FROM occ_costs WHERE case_id=%s GROUP BY kind", (cid,))}
        leave_h = Decimal(self.db.value("SELECT COALESCE(SUM(hours), 0) FROM leave_requests WHERE occ_case=%s AND status=1",
                                        (cid,)) or 0)
        wage_paid = Decimal(self.db.value(
            "SELECT COALESCE(SUM(l.amount), 0) FROM payslip_lines l JOIN payslips s ON s.id=l.slip_id JOIN payroll_runs r ON "
            "r.id=s.run_id JOIN occ_cases c ON c.emp=s.emp WHERE c.id=%s AND l.item='OCC_WAGE' AND r.status>=1", (cid,)) or 0)
        company = sum((v for k, v in tot.items() if k != "ins"), D0)
        return dict(cost_company=company, cost_ins=tot.get("ins", D0), leave_hours=leave_h, leave_days=leave_h / 8,
                    wage_comp=wage_paid, total_cost=company + wage_paid)

    def next_case_no(self, d):
        prefix = "OC" + rocdate.compact(d)[:5]
        last = self.db.value("SELECT MAX(case_no) FROM occ_cases WHERE case_no LIKE %s", (prefix + "%",))
        return "%s%03d" % (prefix, int(last[len(prefix):]) + 1 if last else 1)

    def save_occ_case(self, row, cid=None):
        self.need("OCC")
        emp = row.get("emp")
        e = self.employee(emp)
        at = row.get("injury_at")
        if isinstance(at, str):
            parts = at.split()
            d = date(parts[0])
            h, m = (int(x) for x in (parts[1] if len(parts) > 1 else "09:00").split(":"))
            at = dt.datetime(d.year, d.month, d.day, h, m)
        if not isinstance(at, dt.datetime):
            raise BizError("請輸入受傷日期時間")
        kind = row.get("kind") or "W"
        if kind not in KIND:
            raise BizError("職災類別不正確")
        st = row.get("status") or "T"
        if st not in STATUS:
            raise BizError("案件狀態不正確")
        avg = yuan(row.get("avg_wage") or 0) or self.wage_basis(e)
        vals = dict(emp=emp, injury_at=at, kind=kind, place=(row.get("place") or "")[:100],
                    description=(row.get("description") or "")[:500], injury=(row.get("injury") or "")[:200],
                    hospital=(row.get("hospital") or "")[:60], reported_at=_od(row.get("reported_at")),
                    claim_at=_od(row.get("claim_at")), status=st, return_date=_od(row.get("return_date")), avg_wage=avg,
                    memo=(row.get("memo") or "")[:300])
        if cid:
            self.db.exec("UPDATE occ_cases SET %s WHERE id=%%s" % ", ".join("%s=%%s" % k for k in vals),
                         tuple(vals.values()) + (cid,))
        else:
            vals["case_no"] = self.next_case_no(at.date())
            vals["created_by"] = self.uid
            cid = self.db.exec("INSERT INTO occ_cases (%s) VALUES (%s)" % (", ".join(vals), ", ".join(["%s"] * len(vals))),
                               tuple(vals.values()))
        self.log("occ_case", str(cid), "%s %s" % (emp, at))
        return cid

    def add_occ_cost(self, cid, d, kind, amount, memo=""):
        self.need("OCC")
        c = self.db.row("SELECT id FROM occ_cases WHERE id=%s", (cid,))
        if not c:
            raise BizError("職災案件不存在")
        if kind not in COST_KIND:
            raise BizError("費用類別不正確")
        a = yuan(amount)
        if a <= 0:
            raise BizError("金額要大於 0")
        payer = "I" if kind == "ins" else "C"
        return self.db.exec("INSERT INTO occ_costs (case_id, d, kind, amount, payer, memo, created_by) VALUES "
                            "(%s, %s, %s, %s, %s, %s, %s)", (cid, date(d), kind, a, payer, (memo or "")[:200], self.uid))

    def delete_occ_cost(self, xid):
        self.need("OCC")
        x = self.db.row("SELECT * FROM occ_costs WHERE id=%s", (xid,))
        if x and x["gl_batch_id"]:
            raise BizError("已拋轉會計的費用不能刪除，請先取消拋轉")
        self.db.exec("DELETE FROM occ_costs WHERE id=%s", (xid,))

    def occ_leave(self, cid, start, end, reason="公傷病假"):
        """登錄公傷病假（核准）。"""
        c = self.db.row("SELECT * FROM occ_cases WHERE id=%s", (cid,))
        if not c:
            raise BizError("職災案件不存在")
        return self.request_leave(c["emp"], "OCC", start, end, reason, approve=True, occ_case=cid)

    def occ_benefit_estimate(self, cid, days_off):
        """職災保險傷病給付試算：不能工作第 4 日起，前 2 個月 70%、之後 50%（平均月投保薪資 ÷ 30）。"""
        c = self.db.row("SELECT * FROM occ_cases WHERE id=%s", (cid,))
        e = self.employee(c["emp"])
        _, occ, _, _ = self.insured_wages(e, self.wage_basis(e), c["injury_at"].date())
        daily = Decimal(occ) / 30
        n = max(int(days_off) - 3, 0)
        first = min(n, 60)
        rest = max(n - 60, 0)
        return yuan(daily * Decimal("0.7") * first + daily * Decimal("0.5") * rest)


def _od(v):
    if v in (None, ""):
        return None
    return date(v)
