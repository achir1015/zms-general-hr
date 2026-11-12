"""會計拋轉：薪資、公司負擔保費、發放、職災費用、特休估列產生傳票（預覽），匯出拋轉檔或直接傳送到會計系統。"""
import os
import time

import flet as ft

from .. import rocdate
from ..gl import SCOPES, AcctClient
from . import theme as T

CAT_TONE = {"payroll": "green", "paid": "sky", "occ": "rose", "accrual": "amber"}


def acct_login_dialog(ctx, title, on_ok):
    """輸入會計系統網址與帳號密碼（網址、帳號會記住；密碼不存）。"""
    st = ctx.app.st
    url = T.field("會計系統網址", st.extra.get("acct_url") or "http://127.0.0.1:8765", width=320,
                  hint_text="同一台電腦：http://127.0.0.1:8765")
    uid = T.field("會計系統帳號", st.extra.get("acct_user", ""), width=200)
    pw = T.field("密碼", "", width=200, password=True, can_reveal_password=True)
    msg = T.muted("會計系統要開著，並在「系統管理 → 手機連線」打開連線服務。帳號需要「傳票登錄」維護權限。", 12)

    def test(e):
        try:
            info = AcctClient(url.value, uid.value, pw.value).ping()
            msg.value, msg.color = "連線成功：%s v%s（%s）" % (info.get("app"), info.get("version"),
                                                         info.get("company")), T.SUCCESS
        except Exception as ex:
            msg.value, msg.color = str(ex), T.DANGER
        msg.update()

    def ok(e):
        st.extra["acct_url"], st.extra["acct_user"] = url.value.strip(), uid.value.strip()
        st.save()
        ctx.close()
        on_ok(AcctClient(url.value, uid.value, pw.value))
    pw.on_submit = ok
    ctx.dialog(title, ft.Column([url, ft.Row([uid, pw]), msg], tight=True, spacing=12),
               [T.btn("取消", kind="ghost", on_click=lambda e: ctx.close()),
                T.btn("測試連線", ft.Icons.WIFI_TETHERING, test, kind="outline"),
                T.btn("登入並傳送", ft.Icons.SEND, ok)], icon=ft.Icons.SYNC_ALT, tone="blue", width=560)


def batch_actions(ctx, bid, after):
    """批次產生後或在拋轉紀錄點選時：匯出、傳送、取消。"""
    b = ctx.books
    bt = b.gl_batch(bid)

    async def export(e):
        name = "人事薪資拋轉_%s.zmsgl" % bt["batch_no"]
        path = await ctx.save_as(name, "zmsgl")
        if path and ctx.guard(b.export_gl_batch, bid, path):
            ctx.close()
            ctx.toast("已匯出：%s，請到會計系統「傳票作業 → 進銷存拋轉」匯入（人事薪資與進銷存共用同一個匯入功能）" % os.path.basename(path))
            after()

    def send(e):
        ctx.close()

        def go(client):
            res = ctx.guard(b.send_gl_batch, bid, client)
            if res:
                nos = res.get("voucher_nos") or []
                ctx.toast("已送達會計系統：%d 張傳票 %s" % (len(nos), ("%s～%s" % (nos[0], nos[-1])) if nos else ""))
                after()
        acct_login_dialog(ctx, "直接傳送到會計系統", go)

    def cancel(e):
        ctx.close()

        def do(client=None):
            if ctx.guard(b.cancel_gl_batch, bid, client, ok="已取消拋轉，薪資批次已解除鎖定"):
                after()
        if bt["status"] == 2:
            ctx.confirm("取消拋轉", "這批傳票已送到會計系統，會先請會計系統刪除這批傳票（必須都還沒審核）。",
                        lambda: acct_login_dialog(ctx, "登入會計系統以取消匯入", do), yes="繼續", danger=True)
        else:
            ctx.confirm("取消拋轉", "如果已經把拋轉檔匯入會計系統，請先在會計系統「進銷存拋轉」畫面取消匯入，再取消這裡，"
                        "否則兩邊會不一致。確定取消？", do, yes="取消拋轉")
    st = {1: "已產生", 2: "已送達會計", 9: "已取消"}[bt["status"]]
    info = ft.Column([
        T.muted("期間 %s～%s　%d 張傳票　借貸合計 %s" % (rocdate.show(bt["date_from"]), rocdate.show(bt["date_to"]),
                                                  bt["voucher_count"], T.amt(bt["total"])), 13),
        T.muted("狀態：%s　%s" % (st, bt["result"] or ""), 13)], tight=True, spacing=6)
    acts = [T.btn("關閉", kind="ghost", on_click=lambda e: ctx.close())]
    if bt["status"] != 9 and b.can("GL", 2):
        acts += [T.btn("取消拋轉", ft.Icons.UNDO, cancel, kind="danger"),
                 T.btn("匯出拋轉檔", ft.Icons.DOWNLOAD, export, kind="outline"),
                 T.btn("直接傳送會計系統", ft.Icons.SEND, send)]
    ctx.dialog("拋轉批次 %s" % bt["batch_no"], info, acts, icon=ft.Icons.SYNC_ALT, tone="blue", width=640)


class Transfer(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        today = rocdate.today()
        first = b.gl_first_pending() or today.replace(day=1)
        self.start = T.date_field("起", first, width=150)
        self.end = T.date_field("迄", today, width=150)
        self.checks = {k: ft.Checkbox(label=v, value=True) for k, v in SCOPES.items()}
        self.pending = ft.Row([], wrap=True, spacing=8)
        self.summary = ft.Row([], spacing=10)
        self.grid = T.Grid([("date", "日期", "d", 90), ("ref", "來源", "s", 100),
                            ("memo", "摘要", "s", 380), ("total", "借貸金額", "n", 120)], on_pick=self.lines,
                           totals=("total",), empty="按「預覽傳票」查看要拋轉的分錄")
        self.grid.set_rows([])
        self.vouchers = []
        super().__init__([
            T.page_header(ft.Icons.SYNC_ALT, "會計拋轉", "把薪資、保費、職災費用轉成「資料助秘之一般公司會計」的傳票（薪資批次要先確認）",
                          "blue", [T.btn("拋轉紀錄", ft.Icons.HISTORY_EDU, lambda e: ctx.app.go("gl_batches"),
                                         kind="outline"),
                                   T.btn("科目對照", ft.Icons.ACCOUNT_TREE, lambda e: ctx.app.go("gl_map"),
                                         kind="outline")]),
            T.card(ft.Column([
                ft.Row([self.start, self.end, T.btn("預覽傳票", ft.Icons.PREVIEW, lambda e: self.preview()),
                        T.btn("產生拋轉批次", ft.Icons.PLAYLIST_ADD_CHECK, lambda e: self.create(), kind="accent")],
                       wrap=True, spacing=10),
                ft.Row([ft.Container(c, width=190) for c in self.checks.values()], wrap=True, spacing=4),
                self.pending], spacing=10), padding=14),
            self.summary, self.grid], spacing=12, expand=True)
        self.show_pending(refresh=False)

    def scopes(self):
        return [k for k, c in self.checks.items() if c.value]

    def show_pending(self, refresh=True):
        p = self.ctx.guard(self.ctx.books.gl_pending, self.start.value, self.end.value) or {}
        self.pending.controls = [T.muted("期間內尚未拋轉：", 12)] + [
            T.chip("%s %d" % (SCOPES[k], v), CAT_TONE[k]) for k, v in p.items() if v] if any(
            p.values()) else [T.muted("期間內沒有尚未拋轉的交易", 12)]
        if refresh:
            self.update()

    def preview(self):
        r = self.ctx.guard(self.ctx.books.gl_preview, self.start.value, self.end.value, self.scopes())
        if not r:
            return
        self.vouchers = r[0]
        self.grid.set_rows(self.vouchers)
        total = sum(v["total"] for v in self.vouchers)
        self.summary.controls = [T.chip("%d 張傳票" % len(self.vouchers), "blue"),
                                 T.chip("借貸合計 %s" % T.amt(total), "teal"),
                                 T.muted("點選傳票可看分錄明細", 12)]
        self.show_pending(refresh=False)
        self.update()

    def lines(self, v):
        g = T.Grid([("account", "科目", "s", 70), ("summary", "摘要", "s", 300), ("dept", "部門", "s", 60),
                    ("debit", "借方", "nz", 110), ("credit", "貸方", "nz", 110)], height=300, totals=("debit", "credit"))
        g.set_rows(v["lines"])
        self.ctx.dialog("%s　%s" % (v["ref"], rocdate.show(v["date"])), g,
                        [T.btn("關閉", kind="ghost", on_click=lambda e: self.ctx.close())], icon=ft.Icons.RECEIPT_LONG,
                        width=760)

    def create(self):
        c = self.ctx

        def go():
            bid = c.guard(c.books.create_gl_batch, self.start.value, self.end.value, self.scopes())
            if bid:
                self.grid.set_rows([])
                self.summary.controls = []
                self.show_pending(refresh=False)
                self.update()
                batch_actions(c, bid, lambda: c.app.go("gl_batches"))
        c.confirm("產生拋轉批次", "會把期間內勾選類別、尚未拋轉的資料產生一批傳票，薪資批次之後要先取消拋轉才能取消確認。"
                  "接著可以匯出拋轉檔或直接傳送到會計系統。", go, yes="產生", danger=False)


class Batches(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.grid = T.Grid([("batch_no", "批次", "s", 130), ("period", "交易期間", "s", 170), ("scope_s", "類別", "s", 220),
                            ("voucher_count", "傳票", "s", 60), ("total", "借貸金額", "n", 120), ("st", "狀態", "s", 90),
                            ("result", "結果", "s", 260), ("created_by", "產生人", "s", 80), ("at", "產生時間", "s", 130)],
                           on_pick=lambda r: batch_actions(ctx, r["id"], self.load), empty="尚未拋轉")
        super().__init__([T.page_header(ft.Icons.HISTORY_EDU, "拋轉紀錄", "點選批次可再匯出、直接傳送或取消拋轉", "blue",
                                        [T.btn("會計拋轉", ft.Icons.SYNC_ALT, lambda e: ctx.app.go("gl_transfer"))]),
                          self.grid], spacing=12, expand=True)
        self.load(refresh=False)

    def load(self, refresh=True):
        rows = self.ctx.books.gl_batches()
        for r in rows:
            r["period"] = "%s～%s" % (rocdate.show(r["date_from"]), rocdate.show(r["date_to"]))
            r["scope_s"] = "、".join(SCOPES.get(x, x) for x in (r["scope"] or "").split(",") if x)
            r["st"] = {1: "已產生", 2: "已送達會計", 9: "已取消"}[r["status"]]
            r["voucher_count"] = str(r["voucher_count"])
            r["at"] = T.show(r["created_at"])
        self.grid.set_rows(rows)
        if refresh:
            self.update()


class MapEdit(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b = ctx.books
        self.rows = b.gl_map()
        self.inputs = {}
        editable = b.can("GL", 2)
        items = []
        for r in self.rows:
            a = T.field("", r["account"], width=90, disabled=not editable, height=42)
            n = T.field("", r["name"], width=200, disabled=not editable, height=42)
            self.inputs[r["k"]] = (a, n)
            items.append(ft.Container(ft.Row([a, n, T.muted(r["desc"], 12, expand=True),
                                              T.muted("預設 %s" % r["default"], 11)], spacing=10),
                                      padding=ft.Padding.symmetric(vertical=2, horizontal=6)))
        acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save())] if editable else []
        super().__init__([T.page_header(ft.Icons.ACCOUNT_TREE, "會計科目對照",
                                        "拋轉時每類交易記到哪個會計科目（四碼明細科目，與會計系統一致）", "blue", acts),
                          T.card(ft.Column([T.muted("預設值與「資料助秘之一般公司會計」的科目表相同。2145 應付休假給付、2175 代扣自提勞退 "
                                                    "會計系統匯入時若沒有會自動建立。個別薪資科目（加班費、伙食費、借支…）"
                                                    "的會計科目在「薪資作業 → 薪資科目」設定；空白者依部門費用別記到上面的薪資支出科目。", 12),
                                            ft.Column(items, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)],
                                           spacing=10, expand=True), padding=14, expand=True)],
                         spacing=12, expand=True)

    def save(self):
        items = [dict(k=k, account=a.value, name=n.value) for k, (a, n) in self.inputs.items()]
        self.ctx.guard(self.ctx.books.save_gl_map, items, ok="科目對照已儲存")


_ = time
