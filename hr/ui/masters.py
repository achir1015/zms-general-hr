"""基本資料：商品、客戶、廠商、類別、倉庫、員工、部門、銀行帳戶、異動原因、備註片語（清單＋右側編輯）。"""
from decimal import Decimal

import flet as ft

from ..core import MASTERS
from . import theme as T

MASTER_STYLE = {"departments": (ft.Icons.APARTMENT, "violet"), "shifts": (ft.Icons.SCHEDULE, "teal"),
                "leave_types": (ft.Icons.CATEGORY, "amber"), "pay_items": (ft.Icons.LIST_ALT, "green"),
                "gps_sites": (ft.Icons.LOCATION_ON, "teal"), "calendar": (ft.Icons.EVENT, "rose"),
                "bonus_rules": (ft.Icons.RULE, "green")}
SUBTITLE = {"departments": "費用別決定薪資拋轉的會計科目（管理、推銷、製造、研發）；部門主管可審核部門員工的請假加班",
            "shifts": "上下班時間、休息分鐘與日別；跨夜班（例如 23:00～08:00）下班時間小於上班時間即可",
            "leave_types": "依勞基法、性別平等工作法、勞工請假規則預設；給薪比例 1＝全薪、0.5＝半薪、0＝不給薪",
            "pay_items": "應發與應扣項目；經常性給與計入加班費與投保基數；獎金計入二代健保補充保費",
            "gps_sites": "手機 GPS 打卡的地點與允許半徑；可用地圖查經緯度（Google 地圖按右鍵即可複製座標）",
            "calendar": "國定假日（勞基法第 37 條）、公司休假、補班日；預設已有 115 年國定假日",
            "bonus_rules": "年終獎金（月數）、三節獎金（固定金額）等；在「獎金與年終」依規則產生金額"}
LIST_COLS = {"pay_items": ["code", "name", "kind", "method", "taxable", "regular", "nhi_bonus", "gl_account", "active"],
             "leave_types": ["code", "name", "pay_ratio", "min_hours", "quota_days", "gender", "affects_attend", "balance",
                             "active"],
             "bonus_rules": ["name", "item", "basis", "value", "prorate", "min_months", "active"]}
REF_OPTS = {"dept": "departments", "emp": "employees", "item": "pay_items", "site": "gps_sites"}


def form_header(icon, tone, title, sub=""):
    return ft.Row([T.icon_tile(icon, tone, 40), ft.Column([ft.Text(title, size=17, weight=ft.FontWeight.W_700),
                                                          T.muted(sub, 12)] if sub else
                                                         [ft.Text(title, size=17, weight=ft.FontWeight.W_700)],
                                                         spacing=0, expand=True)], spacing=12)


def sel_options(typ):
    return [tuple(x.split("=")) for x in typ[4:].split(",")]


class MasterList(ft.Row):
    def __init__(self, ctx, name):
        self.ctx, self.name = ctx, name
        self.m = MASTERS[name]
        b = ctx.books
        self.editable = b.can("BAS", 2)
        icon, tone = MASTER_STYLE.get(name, (ft.Icons.FOLDER, "blue"))
        self.icon, self.tone = icon, tone
        self.search = T.field("搜尋", "", width=220, prefix_icon=ft.Icons.SEARCH, on_change=lambda e: self.filter())
        fields = {f[0]: f for f in self.m["fields"]}
        show = LIST_COLS.get(name) or [f[0] for f in self.m["fields"]]
        cols = []
        for k in show:
            _, t, typ, w = fields[k]
            if k in self.m.get("cost_fields", ()) and False:
                continue
            cols.append((k + "_show" if typ.startswith("sel:") or typ in REF_OPTS else k, t,
                         "n" if typ == "n" else "b" if typ == "b" else "s", min(w, 230)))
        self.grid = T.Grid(cols, on_pick=self.edit)
        self.rows = []
        self.current = None
        self.inputs = {}
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        tools = [self.search, ctx.export_button(self.grid, self.m["title"])]
        if self.editable and name in ("departments",):
            tools.append(ft.PopupMenuButton(
                content=ft.Container(ft.Row([ft.Icon(ft.Icons.UPLOAD_FILE, size=18, color=T.PRIMARY),
                                             ft.Text("匯入 Excel", color=T.PRIMARY, size=14,
                                                     weight=ft.FontWeight.W_500)], spacing=8, tight=True),
                                     border=ft.Border.all(1, "#C7D4E8"), border_radius=10,
                                     padding=ft.Padding.symmetric(horizontal=16, vertical=10)),
                tooltip="下載範本或匯入名冊",
                items=[ft.PopupMenuItem("下載範本（CSV）", icon=ft.Icons.DOWNLOAD, on_click=self.template),
                       ft.PopupMenuItem("選擇檔案匯入", icon=ft.Icons.UPLOAD_FILE, on_click=self.do_import)]))
        left = ft.Column([T.page_header(icon, self.m["title"], SUBTITLE.get(name, ""), tone, tools), self.grid],
                         expand=True, spacing=12)
        super().__init__([left, T.card(self.form, width=420, padding=18)], expand=True, spacing=14, data="split",
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.opts = {}
        self.reload()
        self.edit(None, refresh=False)

    def options(self, typ):
        if typ not in self.opts:
            self.opts[typ] = self.ctx.books.options(REF_OPTS[typ])
        return self.opts[typ]

    def reload(self):
        self.rows = self.ctx.books.master_rows(self.name)
        for k, t, typ, w in self.m["fields"]:
            if typ.startswith("sel:"):
                o = dict(sel_options(typ))
                for r in self.rows:
                    r[k + "_show"] = o.get(str(r.get(k)), r.get(k))
            elif typ in REF_OPTS:
                o = dict(self.options(typ))
                for r in self.rows:
                    r[k + "_show"] = o.get(r.get(k), r.get(k) or "")
        self.filter(refresh=False)

    def filter(self, refresh=True):
        q = (self.search.value or "").strip().lower()
        rows = [r for r in self.rows if not q or any(q in str(v).lower() for v in r.values())]
        self.grid.set_rows(rows)
        if refresh:
            self.update()

    async def template(self, e):
        from .. import csvio
        await self.ctx.save_generated("%s範本.csv" % self.m["title"], lambda p: csvio.master_template(self.name, p))

    async def do_import(self, e):
        from .. import csvio
        path = await self.ctx.pick_csv("選擇%s名冊（CSV）" % self.m["title"])
        if not path:
            return
        r = self.ctx.guard(csvio.import_masters, self.ctx.books, self.name, path)
        if not r:
            return
        ok, errs = r
        self.reload()
        self.update()
        msg = ft.Column([ft.Text("成功匯入（新增或更新）%d 筆。" % ok, size=15, color=T.SUCCESS,
                                 weight=ft.FontWeight.W_600)] +
                        ([ft.Text("以下 %d 列未匯入：" % len(errs), color=T.DANGER)] +
                         [ft.Text(x, size=12, selectable=True) for x in errs[:30]] if errs else []),
                        tight=True, scroll=ft.ScrollMode.AUTO, height=None if len(errs) < 10 else 360)
        self.ctx.dialog("匯入結果", msg, [T.btn("確定", on_click=lambda e: self.ctx.close())],
                        icon=ft.Icons.UPLOAD_FILE, tone="green" if not errs else "amber", width=520)

    def edit(self, r, refresh=True):
        self.current = r
        self.inputs = {}
        b = self.ctx.books
        ctrls = []
        pair = []
        for key, title, typ, w in self.m["fields"]:
            if key in self.m.get("cost_fields", ()) and False:
                continue
            v = (r or {}).get(key)
            ro = key in self.m.get("readonly", ()) or (bool(r) and r.get("sys") and key in self.m.get("readonly_sys", ()))
            if typ == "b":
                c = T.switch(title, (True if key in ("active", "taxable", "exclude_left") else False) if r is None else v)
            elif typ.startswith("sel:"):
                c = T.dropdown(title, sel_options(typ), str(v) if v not in (None, "") else sel_options(typ)[0][0],
                               filterable=False)
            elif typ in REF_OPTS:
                c = T.dropdown(title, self.options(typ), v or "", blank="（無）")
            elif typ in ("n", "i"):
                c = T.field(title, "" if v is None else (T.amt(v) if typ == "n" and key not in ("lat", "lon") else
                                                         str(v)), text_align=ft.TextAlign.RIGHT, read_only=ro)
            elif typ == "d":
                from .. import rocdate
                c = T.field(title, rocdate.show(v) if v else "", hint_text="115/11/13", read_only=bool(r),
                            prefix_icon=ft.Icons.CALENDAR_MONTH)
            else:
                c = T.field(title, v or "", read_only=(bool(r) and key == self.m["key"] and key != "id") or ro,
                            multiline=key == "memo")
            c.disabled = not self.editable or ro
            self.inputs[key] = c
            if typ in ("n", "i", "t") and self.name in ("shifts", "leave_types", "gps_sites", "bonus_rules", "pay_items"):
                c.expand = True
                pair.append(c)
                if len(pair) == 2:
                    ctrls.append(ft.Row(pair, spacing=10))
                    pair = []
                continue
            if pair:
                ctrls.append(ft.Row(pair, spacing=10))
                pair = []
            ctrls.append(c)
        if pair:
            ctrls.append(ft.Row(pair, spacing=10))
        acts = []
        if self.editable:
            acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save()),
                    T.btn("新增", ft.Icons.ADD, lambda e: self.edit(None), kind="outline")]
            if r:
                acts.append(T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger"))
        extra = []
        if self.name == "gps_sites":
            extra = [ft.Row([T.btn("用地址查座標", ft.Icons.TRAVEL_EXPLORE, lambda e: self.geocode(), kind="outline")]
                            if self.editable else [])]
        if r and r.get("sys"):
            extra.append(T.chip("系統內建（代號與類別不能改，可停用）", "slate", ft.Icons.LOCK))
        if r and r.get("law_note"):
            extra.append(T.muted(r["law_note"], 12))
        self.form.controls = [form_header(self.icon, self.tone, "修改%s" % self.m["title"] if r else
                                          "新增%s" % self.m["title"], "" if self.editable else "您只有查詢權限"),
                              *extra, *ctrls, ft.Row(acts, wrap=True, spacing=8)]
        if refresh:
            self.update()

    def save(self):
        row = {k: c.value for k, c in self.inputs.items()}
        if self.current and self.m["key"] == "id":
            row["id"] = self.current["id"]
        for k, t, typ, _ in self.m["fields"]:
            if typ in ("n", "i") and k in row:
                row[k] = str(row[k] or "0").replace(",", "")
        if self.ctx.guard(self.ctx.books.save_master, self.name, row, self.current is None, ok="已儲存"):
            self.reload()
            self.edit(None)

    def delete(self):
        key = self.current[self.m["key"]]
        label = self.current.get("name") or self.current.get("text") or str(key)

        def go():
            if self.ctx.guard(self.ctx.books.delete_master, self.name, key, ok="已刪除"):
                self.reload()
                self.edit(None)
        self.ctx.confirm("刪除%s" % self.m["title"], "確定要刪除「%s」嗎？" % label, go, yes="刪除")


_ = Decimal


def _geocode(addr):
    """地址轉經緯度（參考 gps-arrival-test：ArcGIS 台灣門牌，找不到再用 OpenStreetMap 逐步縮短地址）。"""
    import json
    import re
    import urllib.parse
    import urllib.request
    ua = {"User-Agent": "ZMS-HR/1.0"}
    url = ("https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&forStorage=false"
           "&sourceCountry=TWN&maxLocations=1&SingleLine=" + urllib.parse.quote(addr))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=10) as r:
            c = (json.loads(r.read().decode("utf-8")).get("candidates") or [])
        if c and c[0].get("score", 0) >= 60:
            return float(c[0]["location"]["y"]), float(c[0]["location"]["x"]), "ArcGIS（吻合度 %.0f）" % c[0]["score"]
    except Exception:
        pass
    tries = [addr]
    for pat in (r"之\d+號", r"\d+之?\d*號.*$", r"\d+弄.*$", r"\d+巷.*$", r"\d+段.*$"):
        a = re.sub(pat, "號" if pat.startswith("之") else "", addr).strip()
        if a and a not in tries:
            tries.append(a)
    for q in tries:
        try:
            u = ("https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=tw&q=" +
                 urllib.parse.quote(q + " Taiwan"))
            with urllib.request.urlopen(urllib.request.Request(u, headers=ua), timeout=10) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d:
                return float(d[0]["lat"]), float(d[0]["lon"]), "OpenStreetMap（%s）" % q
        except Exception:
            continue
    return None


def _geocode_method(self):
    addr = (self.inputs["address"].value or "").strip()
    if not addr:
        self.ctx.toast("請先輸入地址", True)
        return
    r = _geocode(addr)
    if not r:
        self.ctx.toast("查不到這個地址的座標，請改用 Google 地圖右鍵複製座標", True)
        return
    self.inputs["lat"].value, self.inputs["lon"].value = "%.6f" % r[0], "%.6f" % r[1]
    self.update()
    self.ctx.toast("已填入座標（來源：%s）" % r[2])


MasterList.geocode = _geocode_method
