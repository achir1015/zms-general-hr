"""職業災害（公傷）：案件清單、案件內容、公傷病假、醫療與補償費用、保險給付抵充、職災給付試算。"""
import flet as ft

from .. import rocdate
from ..occ import COST_KIND, KIND, STATUS
from . import common as C
from . import theme as T


class Occ(ft.Row):
    def __init__(self, ctx):
        self.ctx = ctx
        self.editable = ctx.books.can("OCC", 2)
        self.status = T.dropdown("狀態", [("", "全部")] + list(STATUS.items()), "", width=130, filterable=False,
                                 on_select=lambda e: self.load())
        self.grid = T.Grid([("case_no", "案號", "s", 100), ("emp", "編號", "s", 60), ("name", "姓名", "s", 70),
                            ("injury_at", "受傷時間", "s", 120), ("kind_name", "類別", "s", 80), ("status_name", "狀態", "s", 60),
                            ("leave_days", "公傷假(日)", "s", 70), ("total_cost", "公司成本", "n", 90)],
                           on_pick=lambda r: self.edit(r["id"]))
        tools = [self.status, ctx.export_button(self.grid, "職災案件")]
        if self.editable:
            tools.insert(0, T.btn("新增案件", ft.Icons.ADD, lambda e: self.edit(None)))
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        left = ft.Column([T.page_header(ft.Icons.HEALING, "公傷案件", "職業災害：公傷病假、原領工資補償、醫療費用與保險給付",
                                        "rose", tools), self.grid], expand=True, spacing=12)
        super().__init__([left, T.card(self.form, width=520)], expand=True, spacing=14, data="split",
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.load(False)
        self.edit(None, False)

    def load(self, upd=True):
        rows = self.ctx.guard(self.ctx.books.occ_cases, self.status.value or "") or []
        for r in rows:
            r["injury_at"] = C.dt_text(r["injury_at"])
            r["leave_days"] = C.hours(r["leave_days"])
        self.grid.set_rows(rows)
        if upd:
            self.update()

    def edit(self, cid, upd=True):
        b = self.ctx.books
        self.cid = cid
        c = self.ctx.guard(b.occ_case, cid) if cid else {}
        if c is None:
            return
        c = c or {}
        self.f_emp = C.emp_dropdown(self.ctx, c.get("emp") or "", width=230, blank=None, include_left=True)
        self.f_at = T.field("受傷日期時間", C.dt_text(c["injury_at"]) if c.get("injury_at") else
                            rocdate.show(rocdate.today()) + " 09:00", width=200)
        self.f_kind = T.dropdown("類別", list(KIND.items()), c.get("kind") or "W", width=160, filterable=False)
        self.f_status = T.dropdown("狀態", list(STATUS.items()), c.get("status") or "T", width=130, filterable=False)
        self.f_place = T.field("地點", c.get("place") or "")
        self.f_desc = T.field("經過", c.get("description") or "", multiline=True, min_lines=2)
        self.f_injury = T.field("傷害部位與程度", c.get("injury") or "")
        self.f_hosp = T.field("就醫院所", c.get("hospital") or "", width=230)
        self.f_rep = T.field("職災通報日", rocdate.show(c["reported_at"]) if c.get("reported_at") else "", width=150)
        self.f_claim = T.field("申請職災給付日", rocdate.show(c["claim_at"]) if c.get("claim_at") else "", width=150)
        self.f_ret = T.field("復工日", rocdate.show(c["return_date"]) if c.get("return_date") else "", width=150)
        self.f_avg = T.money_field("原領工資（月，空白＝目前經常性薪資）", c.get("avg_wage") or "", width=300)
        self.f_memo = T.field("備註", c.get("memo") or "", multiline=True)
        ctl = [self.f_emp, ft.Row([self.f_at, self.f_kind, self.f_status], wrap=True), self.f_place, self.f_desc,
               self.f_injury, ft.Row([self.f_hosp, self.f_rep], wrap=True), ft.Row([self.f_claim, self.f_ret], wrap=True),
               self.f_avg, self.f_memo]
        for x in ctl:
            for y in (x.controls if isinstance(x, ft.Row) else [x]):
                y.disabled = not self.editable
        acts = []
        if self.editable:
            acts = [T.btn("儲存案件", ft.Icons.SAVE, lambda e: self.save())]
            if cid:
                acts += [T.btn("登錄公傷病假", ft.Icons.EVENT_BUSY, lambda e: self.leave(), kind="outline"),
                         T.btn("新增費用", ft.Icons.ADD_CARD, lambda e: self.cost(), kind="outline"),
                         T.btn("職災給付試算", ft.Icons.CALCULATE, lambda e: self.estimate(), kind="ghost")]
        extra = []
        if cid:
            g = T.Grid([("d", "日期", "d", 90), ("kind_name", "類別", "s", 110), ("amount", "金額", "n", 90),
                        ("memo", "說明", "s", 160)], height=200, on_pick=self.del_cost)
            g.set_rows(c["costs"])
            lv = T.Grid([("lname", "假別", "s", 80), ("s", "期間", "s", 220), ("h", "時數", "s", 60)], height=150)
            lv.set_rows([dict(lname=x["lname"], s="%s～%s" % (C.dt_text(x["start_at"]), C.dt_text(x["end_at"])),
                              h=C.hours(x["hours"])) for x in c["leaves"]])
            extra = [ft.Row([T.chip("公司支付 %s" % T.amt(c["cost_company"]), "rose"),
                             T.chip("工資補償（已發薪）%s" % T.amt(c["wage_comp"]), "amber"),
                             T.chip("保險給付 %s" % T.amt(c["cost_ins"]), "green")], wrap=True, spacing=6),
                     T.muted("費用（點選可刪除）", 13), g, T.muted("公傷病假", 13), lv]
        self.form.controls = [ft.Row([T.icon_tile(ft.Icons.HEALING, "rose", 40),
                                      ft.Text(("案件 %s" % c["case_no"]) if cid else "新增職災案件", size=17,
                                              weight=ft.FontWeight.W_700)], spacing=12),
                              *ctl, ft.Row(acts, wrap=True, spacing=8), *extra,
                              C.info_box("勞基法第 59 條：醫療期間不能工作，雇主按原領工資補償（可抵充職災保險給付）；"
                                         "公傷病假期間薪資照發，系統以「公傷病假工資補償」免稅項目發給。必需的醫療費用由雇主補償。"
                                         "重大職災應於 8 小時內通報勞動檢查機構；職災保險傷病給付自不能工作第 4 日起，"
                                         "前 2 個月發給平均月投保薪資 70%、之後 50%。", "rose", ft.Icons.GAVEL)]
        if upd:
            self.update()

    def save(self):
        row = dict(emp=self.f_emp.value, injury_at=self.f_at.value, kind=self.f_kind.value, status=self.f_status.value,
                   place=self.f_place.value, description=self.f_desc.value, injury=self.f_injury.value,
                   hospital=self.f_hosp.value, reported_at=self.f_rep.value, claim_at=self.f_claim.value,
                   return_date=self.f_ret.value, avg_wage=(self.f_avg.value or "0").replace(",", ""), memo=self.f_memo.value)
        cid = self.ctx.guard(self.ctx.books.save_occ_case, row, self.cid, ok="案件已儲存")
        if cid:
            self.load(False)
            self.edit(cid)

    def leave(self):
        s = T.field("開始（日期 時間）", rocdate.show(rocdate.today()) + " 09:00", width=200)
        e_ = T.field("結束（日期 時間）", rocdate.show(rocdate.today()) + " 18:00", width=200)

        def go(ev):
            if self.ctx.guard(self.ctx.books.occ_leave, self.cid, s.value, e_.value, ok="已登錄公傷病假"):
                self.ctx.close()
                self.load(False)
                self.edit(self.cid)
        self.ctx.dialog("登錄公傷病假", ft.Column([ft.Row([s, e_], wrap=True), T.muted("依班表計算時數；薪資照發、不影響全勤。")],
                                              tight=True, spacing=12),
                        [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("登錄", ft.Icons.SAVE, go)],
                        icon=ft.Icons.EVENT_BUSY, tone="rose")

    def cost(self):
        d = T.date_field("日期", rocdate.today(), width=160)
        kind = T.dropdown("類別", list(COST_KIND.items()), "medical", width=200, filterable=False)
        amt = T.money_field("金額", "", width=150)
        memo = T.field("說明", "", width=300)

        def go(ev):
            if self.ctx.guard(self.ctx.books.add_occ_cost, self.cid, d.value, kind.value, (amt.value or "0").replace(",", ""),
                              memo.value, ok="已新增"):
                self.ctx.close()
                self.load(False)
                self.edit(self.cid)
        self.ctx.dialog("新增職災費用", ft.Column([ft.Row([d, kind], wrap=True), amt, memo, T.muted(
            "公司支付的醫療、補償等費用會拋轉會計（借 職災費用／貸 銀行存款）；保險給付（抵充）只做紀錄。"
            "工資補償若已由薪資發放（公傷病假），不必在這裡重複登錄。", 12)], tight=True, spacing=12),
            [T.btn("取消", kind="ghost", on_click=lambda e: self.ctx.close()), T.btn("新增", ft.Icons.ADD, go)],
            icon=ft.Icons.ADD_CARD, tone="rose")

    def del_cost(self, r):
        if not self.editable:
            return
        self.ctx.confirm("刪除費用", "刪除 %s %s？" % (r["kind_name"], T.amt(r["amount"])),
                         lambda: self.ctx.guard(self.ctx.books.delete_occ_cost, r["id"], ok="已刪除") and self.edit(self.cid),
                         yes="刪除")

    def estimate(self):
        days = T.field("不能工作日數", "30", width=140)
        out = ft.Text("", size=15, weight=ft.FontWeight.W_700, color=T.PRIMARY)

        def go(ev):
            v = self.ctx.guard(self.ctx.books.occ_benefit_estimate, self.cid, int(days.value or 0))
            if v is not None:
                out.value = "職災保險傷病給付約 %s 元（可抵充雇主工資補償）" % T.amt(v)
                out.update()
        self.ctx.dialog("職災給付試算", ft.Column([days, out, T.muted("以職災保險投保薪資 ÷ 30 為日額；第 4 日起，前 60 日 70%、之後 50%。", 12)],
                                              tight=True, spacing=12),
                        [T.btn("試算", ft.Icons.CALCULATE, go), T.btn("關閉", kind="ghost", on_click=lambda e: self.ctx.close())],
                        icon=ft.Icons.CALCULATE, tone="rose")
