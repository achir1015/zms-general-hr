"""系統管理：使用者與權限、公司設定、備份還原、版本更新與捷徑、操作紀錄。"""
import os
import threading
import time

import flet as ft

from .. import APP_NAME, APP_VERSION, maintenance, rocdate
from ..seed import FUNCS, ROLES
from ..settings import data_dir
from . import theme as T

FUNC_ICON = {"BAS": (ft.Icons.FOLDER_SPECIAL, "sky"), "EMP": (ft.Icons.BADGE, "violet"),
             "SAL": (ft.Icons.VISIBILITY, "slate"), "ATT": (ft.Icons.SCHEDULE, "teal"),
             "LEV": (ft.Icons.BEACH_ACCESS, "amber"), "INS": (ft.Icons.HEALTH_AND_SAFETY, "sky"),
             "PAY": (ft.Icons.PAYMENTS, "green"), "BON": (ft.Icons.CARD_GIFTCARD, "green"),
             "OCC": (ft.Icons.HEALING, "rose"), "GL": (ft.Icons.SYNC_ALT, "blue"), "RPT": (ft.Icons.INSIGHTS, "violet"),
             "SYS": (ft.Icons.ADMIN_PANEL_SETTINGS, "rose")}
LEVELS = [("0", "無"), ("1", "查詢"), ("2", "維護")]
MAC = __import__("sys").platform == "darwin"


# ====================================================================== 使用者與權限
class Users(ft.Row):
    def __init__(self, ctx):
        self.ctx = ctx
        self.list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        super().__init__([
            ft.Column([T.page_header(ft.Icons.ADMIN_PANEL_SETTINGS, "使用者與權限", "角色範本＋逐項權限", "rose",
                                     [T.btn("新增", ft.Icons.PERSON_ADD, lambda e: self.edit(None))]),
                       T.card(self.list, expand=True, padding=12)], width=400, spacing=12),
            T.card(self.form, expand=True, padding=20)], expand=True, spacing=14, data="split",
            vertical_alignment=ft.CrossAxisAlignment.START)
        self.reload()
        self.edit(None, refresh=False)

    def reload(self):
        self.users = self.ctx.books.users()
        palette = ["#0FA294", "#1E4D8C", "#B45309", "#6D28D9", "#BE123C", "#0369A1"]
        self.list.controls = [ft.Container(ft.Row([
            ft.Container(ft.Text(u["name"][:1], color=ft.Colors.WHITE, weight=ft.FontWeight.W_700), width=40,
                         height=40, border_radius=20, alignment=ft.Alignment.CENTER, bgcolor=palette[i % 6]),
            ft.Column([ft.Text("%s（%s）" % (u["name"], u["uid"]), size=14, weight=ft.FontWeight.W_600),
                       T.muted("最近登入 %s" % T.show(u["last_login"]) if u["last_login"] else "尚未登入", 11)],
                      spacing=0, expand=True),
            T.chip("管理員" if u["is_admin"] else (u["role"] or "自訂"), "rose" if u["is_admin"] else "blue"),
            *([T.chip(u["emp_code"], "teal", ft.Icons.BADGE)] if u.get("emp_code") else []),
            *([T.chip("停用", "slate")] if not u["active"] else [])], spacing=10),
            padding=10, border_radius=12, bgcolor="#F7F9FC", ink=True, on_click=lambda e, u=u: self.edit(u))
            for i, u in enumerate(self.users)]

    def edit(self, u, refresh=True):
        self.cur = u
        new = u is None
        u = u or {"uid": "", "name": "", "role": "員工", "is_admin": 0, "active": 1, "emp_code": "",
                  "perms": ROLES["員工"]}
        self.f_uid = T.field("帳號", u["uid"], read_only=not new, width=200)
        self.f_name = T.field("姓名", u["name"], width=200)
        self.f_role = T.dropdown("角色範本", [(k, k) for k in ROLES], u["role"] if u["role"] in ROLES else None,
                                 width=200, filterable=False, on_select=self.apply_role, blank="自訂")
        self.f_admin = T.switch("系統管理員（擁有全部權限）", u["is_admin"], on_change=lambda e: self.render_perms())
        self.f_active = T.switch("帳號啟用", u["active"])
        self.f_emp = T.dropdown("對應員工（打卡、請假、看自己的薪資單）", self.ctx.books.options("emp_all"),
                                u.get("emp_code") or "", width=320, blank="（不對應員工）")
        self.f_pw = T.field("密碼" if new else "重設密碼（不改請留空）", "", password=True, can_reveal_password=True,
                            width=260)
        self.perm_ctl = {}
        self.perm_box = ft.Column(spacing=6)
        for f, name, desc in FUNCS:
            seg = ft.SegmentedButton(segments=[ft.Segment(value=k, label=t) for k, t in LEVELS],
                                     selected=[str(u["perms"].get(f, 0))], show_selected_icon=False)
            self.perm_ctl[f] = seg
        self.render_perms(refresh=False)
        acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save(new))]
        if not new:
            acts.append(T.btn("刪除帳號", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger"))
        self.form.controls = [
            ft.Row([T.icon_tile(ft.Icons.PERSON_ADD if new else ft.Icons.PERSON, "rose", 44),
                    ft.Text("新增使用者" if new else "修改 %s" % u["name"], size=18, weight=ft.FontWeight.W_700)]),
            ft.Row([self.f_uid, self.f_name, self.f_role], wrap=True), ft.Row([self.f_pw, self.f_emp], wrap=True),
            T.muted("「員工」角色沒有任何管理權限，只能使用「員工自助」（電腦打卡、請假加班、自己的薪資單）與手機 GPS 打卡網頁。"
                    "部門主管可以審核自己部門員工的請假與加班（在「部門」設定主管）。", 12),
            ft.Row([self.f_admin, self.f_active], spacing=24),
            ft.Text("功能權限", size=15, weight=ft.FontWeight.W_700), self.perm_box, ft.Row(acts, spacing=8)]
        if refresh:
            self.update()

    def render_perms(self, refresh=True):
        admin = self.f_admin.value
        self.perm_box.controls = [ft.Container(ft.Row([
            T.icon_tile(*FUNC_ICON[f], 36),
            ft.Column([ft.Text(name, size=14, weight=ft.FontWeight.W_600), T.muted(desc, 11)], spacing=0,
                      expand=True),
            T.chip("全部", "rose") if admin else self.perm_ctl[f]], spacing=12),
            padding=8, border_radius=12, bgcolor="#F7F9FC") for f, name, desc in FUNCS]
        if refresh:
            self.update()

    def apply_role(self, e):
        perms = ROLES.get(self.f_role.value)
        if perms:
            for f, seg in self.perm_ctl.items():
                seg.selected = [str(perms.get(f, 0))]
            self.f_admin.value = self.f_role.value == "系統管理員"
            self.render_perms()

    def save(self, new):
        perms = {f: int((seg.selected or ["0"])[0]) for f, seg in self.perm_ctl.items()}
        if self.ctx.guard(self.ctx.books.save_user, self.f_uid.value, self.f_name.value, self.f_role.value or "",
                          self.f_admin.value, self.f_active.value, perms, self.f_pw.value or None, new,
                          self.f_emp.value or "", ok="已儲存"):
            self.reload()
            self.edit(next((u for u in self.users if u["uid"] == self.f_uid.value.strip()), None))

    def delete(self):
        u = self.cur
        self.ctx.confirm("刪除帳號", "確定刪除 %s（%s）？有作業紀錄的帳號請改為停用。" % (u["name"], u["uid"]),
                         lambda: self.ctx.guard(self.ctx.books.delete_user, u["uid"], ok="已刪除")
                         and (self.reload(), self.edit(None)), yes="刪除")


# ====================================================================== 公司設定
class Company(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        c = ctx.books.company()
        self.f = {}

        def F(k, label, width, **kw):
            self.f[k] = T.field(label, c.get(k), width=width, **kw)
            return self.f[k]
        self.leave_sys = ft.RadioGroup(value=c.get("leave_system") or "A", content=ft.Column([
            ft.Radio(value="A", label="週年制：依每位員工到職週年給特休（勞基法原則）"),
            ft.Radio(value="C", label="曆年制：每年 1/1 統一給特休，依比例折算（須勞雇協商，不得少於週年制）")], spacing=0))
        self.attend = ft.RadioGroup(value=c.get("attend_rule") or "R", content=ft.Column([
            ft.Radio(value="R", label="全勤獎金依請假時數比例扣發（建議）"),
            ft.Radio(value="A", label="請影響全勤的假、遲到早退、曠職，當月全勤獎金不發")], spacing=0))
        self.late = T.switch("遲到早退按分鐘比例扣薪", c.get("late_deduct"))
        self.absent = T.switch("曠職按時數扣薪", c.get("absent_deduct"))
        super().__init__([
            T.page_header(ft.Icons.BUSINESS, "公司設定", "公司基本資料、投保單位、發薪與差勤規則", "rose"),
            T.card(ft.Column([
                ft.Row([T.icon_tile(ft.Icons.APARTMENT, "blue", 36), ft.Text("基本資料", size=16,
                                                                           weight=ft.FontWeight.W_700)]),
                ft.Row([F("name", "公司名稱", 360), F("short_name", "簡稱", 160), F("tax_id", "統一編號", 150),
                        F("owner", "負責人", 140)], wrap=True),
                ft.Row([F("phone", "電話", 180), F("email", "電子郵件", 260)], wrap=True),
                F("address", "地址", 560),
                ft.Divider(),
                ft.Row([T.icon_tile(ft.Icons.HEALTH_AND_SAFETY, "sky", 36), ft.Text("投保單位", size=16,
                                                                                   weight=ft.FontWeight.W_700)]),
                ft.Row([F("labor_ins_no", "勞保保險證號", 180), F("nhi_no", "健保投保單位代號", 180),
                        F("tax_unit_no", "扣繳單位統一編號", 180), F("occ_rate", "職災保險費率 %（行業別＋上下班 0.07）", 300)],
                       wrap=True),
                T.muted("職災保險費率請依勞保局「勞工職業災害保險適用行業別及費率表」查公司行業別費率，再加上下班災害費率 0.07%。", 12),
                ft.Divider(),
                ft.Row([T.icon_tile(ft.Icons.SCHEDULE, "teal", 36), ft.Text("發薪與差勤規則", size=16,
                                                                          weight=ft.FontWeight.W_700)]),
                ft.Row([F("pay_day", "每月發薪日（次月幾日）", 200), F("late_grace", "遲到寬限（分鐘）", 160),
                        F("ot_round_min", "加班計算單位（分鐘）", 180)], wrap=True),
                ft.Row([ft.Container(self.late, width=260), ft.Container(self.absent, width=220)], wrap=True),
                T.muted("特休制度", 13), self.leave_sys, T.muted("全勤獎金", 13), self.attend,
                F("slip_footer", "薪資單頁尾文字（例如：薪資有疑問請洽人資 分機 101）", 560),
                ft.Row([T.btn("儲存", ft.Icons.SAVE, lambda e: self.save())])], spacing=14), padding=22)],
            spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)

    def save(self):
        v = {k: x.value for k, x in self.f.items()}
        try:
            for k in ("pay_day", "late_grace", "ot_round_min"):
                v[k] = int(v[k] or 0)
        except ValueError:
            self.ctx.toast("發薪日、分鐘數要是整數", True)
            return
        self.ctx.guard(self.ctx.books.save_company, leave_system=self.leave_sys.value, attend_rule=self.attend.value,
                       late_deduct=int(self.late.value), absent_deduct=int(self.absent.value), ok="公司設定已儲存", **v)


# ====================================================================== 備份與還原
class Backup(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        st = ctx.app.st
        self.msg = T.muted("", 13)
        self.busy = ft.ProgressRing(width=22, height=22, visible=False)
        info = [("資料庫", "本機內建 MariaDB（連接埠 %s）" % st.port if st.mode == "embedded" else
                 "%s:%s" % (st.host, st.port)), ("資料庫名稱", st.database), ("資料夾", data_dir())]
        super().__init__([
            T.page_header(ft.Icons.BACKUP, "備份與還原", "建議每週備份，並另存到隨身碟或雲端硬碟", "rose"),
            ft.Row([
                action_card(ft.Icons.CLOUD_DOWNLOAD, "teal", "立即備份", "把全部人事薪資差勤資料壓縮成 .sql.gz 檔",
                            T.btn("選擇位置並備份", ft.Icons.BACKUP, self.backup, kind="accent")),
                action_card(ft.Icons.RESTORE, "rose", "從備份還原", "用備份檔覆蓋目前所有資料（無法復原）",
                            T.btn("選擇備份檔", ft.Icons.UPLOAD_FILE, self.restore, kind="danger")),
                action_card(ft.Icons.FOLDER_OPEN, "sky", "資料資料夾", "設定檔、資料庫與紀錄檔所在位置",
                            T.btn("開啟資料夾", ft.Icons.FOLDER_OPEN, lambda e: T.open_file(data_dir()),
                                  kind="outline"))], spacing=14, data="split"),
            ft.Row([self.busy, self.msg]),
            T.card(ft.Column([ft.Row([T.muted(k, 13, width=90), ft.Text(v, size=13, selectable=True)])
                              for k, v in info], spacing=8), padding=18)], spacing=14, expand=True)

    async def backup(self, e):
        name = "人事薪資備份_%s.sql.gz" % time.strftime("%Y%m%d_%H%M")
        path = await self.ctx.save_as(name, "gz")
        if not path:
            return
        if path.endswith(".gz") and not path.endswith(".sql.gz"):
            path = path[:-3] + ".sql.gz"
        self.busy.visible, self.msg.value = True, "備份中…"
        self.update()
        try:
            size = maintenance.backup(self.ctx.app.st, path)
            self.ctx.books.log("backup", os.path.basename(path))
            self.msg.value = "備份完成：%s（%.1f KB）" % (path, size / 1024)
            self.ctx.toast("備份完成")
        except Exception as ex:
            self.msg.value = str(ex)
            self.ctx.toast(str(ex), True)
        self.busy.visible = False
        self.update()

    async def restore(self, e):
        files = await ft.FilePicker().pick_files(dialog_title="選擇備份檔", allowed_extensions=["gz", "sql"])
        if not files:
            return
        path = files[0].path

        def go():
            self.busy.visible, self.msg.value = True, "還原中，請勿關閉程式…"
            self.update()
            try:
                maintenance.restore(self.ctx.app.st, path)
                self.ctx.books.log("restore", os.path.basename(path))
                self.ctx.toast("還原完成，請重新登入")
                self.ctx.app.logout()
            except Exception as ex:
                self.msg.value = str(ex)
                self.ctx.toast(str(ex), True)
                self.busy.visible = False
                self.update()
        self.ctx.confirm("從備份還原", "目前所有資料將被「%s」覆蓋，確定嗎？建議先備份目前資料。" % os.path.basename(path),
                         go, yes="還原")


def action_card(icon, tone, title, desc, button):
    return T.card(ft.Column([T.icon_tile(icon, tone, 52, radius=16), ft.Text(title, size=17,
                                                                         weight=ft.FontWeight.W_700),
                             T.muted(desc, 12), ft.Container(height=4), button], spacing=8), expand=True,
                  padding=20)


# ====================================================================== 版本更新與捷徑
class Update(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.status = ft.Column(spacing=10)
        self.bar = ft.ProgressBar(value=0, visible=False, color=T.ACCENT, bgcolor="#E6F4F1", bar_height=8,
                                  border_radius=4)
        super().__init__([
            T.page_header(ft.Icons.SYSTEM_UPDATE, "版本更新與捷徑", "程式開啟時會自動檢查新版本", "rose"),
            ft.Row([
                T.card(ft.Column([
                    ft.Row([ft.Image(src="icon.png", width=64, height=64),
                            ft.Column([ft.Text(APP_NAME, size=18, weight=ft.FontWeight.W_800),
                                       T.chip("目前版本 v%s" % APP_VERSION, "blue", ft.Icons.VERIFIED)], spacing=6)],
                           spacing=14),
                    self.status, self.bar,
                    ft.Row([T.btn("檢查更新", ft.Icons.REFRESH, lambda e: self.check())])], spacing=14),
                    expand=True, padding=22),
                T.card(ft.Column([
                    T.icon_tile(ft.Icons.SHORTCUT, "teal", 52, radius=16),
                    ft.Text("桌面捷徑", size=17, weight=ft.FontWeight.W_700),
                    T.muted("App 在「應用程式」資料夾，可拖到 Dock 常駐；也可以在桌面建立替身。" if MAC else
                            "安裝時已建立桌面與開始功能表捷徑；如果不見了，按下面按鈕重建。", 12),
                    T.btn("在桌面建立替身" if MAC else "重建桌面捷徑",
                          ft.Icons.DESKTOP_MAC if MAC else ft.Icons.DESKTOP_WINDOWS, lambda e: self.shortcut(),
                          kind="accent")],
                    spacing=10), width=340, padding=22)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.START, data="split"),
            T.card(ft.Column([ft.Text("系統資訊", size=15, weight=ft.FontWeight.W_700),
                              T.muted("系統開發：吳玉柱 先生 與 Claude AI Opus 5.5", 13),
                              T.muted("資料庫：MariaDB　介面：Flet　語音：微軟神經語音／Windows 內建語音", 13)],
                             spacing=6), padding=18)], spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)
        info = ctx.app.update_info
        if info:
            self.show_info(info, refresh=False)
        else:
            self.status.controls = [T.muted("按「檢查更新」查詢是否有新版本。", 13)]

    def check(self):
        self.status.controls = [ft.Row([ft.ProgressRing(width=18, height=18), T.muted("檢查中…")])]
        self.update()

        def work():
            try:
                info = maintenance.check_update()
            except Exception as ex:
                self.status.controls = [ft.Row([ft.Icon(ft.Icons.WIFI_OFF, color=T.WARN),
                                                ft.Text("無法連線更新伺服器：%s" % ex, size=13, color=T.WARN)])]
                self.update()
                return
            if not info:
                self.status.controls = [ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=T.SUCCESS),
                                                ft.Text("已是最新版本", size=14, color=T.SUCCESS)])]
                self.update()
                return
            self.ctx.app.update_info = info
            self.show_info(info)
        self.ctx.page.run_thread(work)

    def show_info(self, info, refresh=True):
        notes = (info["notes"] or "").strip()[:900]
        self.status.controls = [
            ft.Row([T.icon_tile(ft.Icons.NEW_RELEASES, "green", 36),
                    ft.Text("有新版本 v%s" % info["version"], size=16, weight=ft.FontWeight.W_700, color=T.SUCCESS)]),
            ft.Container(ft.Text(notes or "（無更新說明）", size=13, selectable=True), bgcolor="#F7F9FC",
                         border_radius=10, padding=12),
            ft.Row([T.btn("下載並安裝", ft.Icons.DOWNLOAD, lambda e: self.install(info), kind="accent"),
                    T.btn("略過此版本", ft.Icons.SKIP_NEXT, lambda e: self.skip(info), kind="ghost")])]
        if refresh:
            self.update()

    def skip(self, info):
        self.ctx.app.st.skipped_version = info["version"]
        self.ctx.app.st.save()
        self.ctx.app.update_banner.visible = False
        self.ctx.toast("已略過 v%s" % info["version"])
        self.ctx.page.update()

    def install(self, info):
        if not info.get("name"):
            T.open_file(info["page"] or info["url"])
            return
        self.bar.visible, self.bar.value = True, 0
        self.update()

        def work():
            try:
                def prog(x):
                    self.bar.value = x
                    self.bar.update()
                path = maintenance.download(info["url"], prog)
            except Exception as ex:
                self.ctx.toast("下載失敗：%s" % ex, True)
                return
            self.ctx.books.log("update", info["version"])
            self.ctx.toast("下載完成，即將關閉程式並安裝新版…")
            time.sleep(1.2)
            maintenance.launch_installer(path)
            self.ctx.app.shutdown()
            self.ctx.page.run_task(self.ctx.page.window.destroy)
        self.ctx.page.run_thread(work)

    def shortcut(self):
        self.ctx.guard(maintenance.create_desktop_shortcut, ok="桌面替身已建立" if MAC else "桌面捷徑已建立")


# ====================================================================== 手機連線
def qr_png(text, box=6):
    import io

    import qrcode
    q = qrcode.QRCode(border=2, box_size=box, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(text)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(fill_color="#14325C", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def deep_link(url):
    import urllib.parse
    return "zmshr://connect?u=" + urllib.parse.quote(url, safe="")


class MobileLink(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.app = ctx.app
        st = self.app.st
        self.port = T.field("連接埠", str(st.extra.get("api_port") or 8785), width=110)
        self.sw = T.switch("啟用手機連線服務", bool(self.app.api and self.app.api.running), on_change=self.toggle)
        self.status = ft.Container()
        self.urls = ft.Row(wrap=True, spacing=14, run_spacing=14)
        # 外出連線（Cloudflare 通道）
        x = st.extra
        self.t_mode = ft.RadioGroup(value=x.get("tunnel_mode") or "quick", on_change=lambda e: self.render_tunnel(),
                                    content=ft.Column([
                                        ft.Radio(value="quick", label="快速通道（免帳號；網址每次啟動會改變，手機要重新掃描）"),
                                        ft.Radio(value="token", label="固定網址（需要 Cloudflare 帳號與自己的網域）")],
                                        spacing=0))
        self.t_token = T.field("Cloudflare 通道權杖（Tunnel token）", x.get("tunnel_token", ""), password=True,
                               can_reveal_password=True, width=520)
        self.t_url = T.field("公開網址", x.get("tunnel_url", ""), width=520, hint_text="例：https://hr.mycompany.com")
        self.t_fixed = ft.Column([self.t_token, self.t_url,
                                  T.muted("在 Cloudflare 網站 Zero Trust → Networks → Tunnels 建立通道，"
                                          "Public Hostname 的服務填 http://localhost:" +
                                          str(x.get("api_port") or 8785) + "，再把權杖與網址貼在這裡。", 12)],
                                 spacing=10)
        self.t_sw = T.switch("啟用外出連線", bool(getattr(self.app, "tunnel", None) and self.app.tunnel.running),
                             on_change=self.toggle_tunnel)
        self.t_bar = ft.ProgressBar(visible=False, color=T.ACCENT, bgcolor="#E6F4F1", bar_height=6, border_radius=3)
        self.t_status = ft.Container()
        self.t_qr = ft.Container()
        outside = T.card(ft.Column([
            ft.Row([T.icon_tile(ft.Icons.PUBLIC, "violet", 44),
                    ft.Column([ft.Text("外出連線（Cloudflare 加密通道）", size=15, weight=ft.FontWeight.W_700),
                               T.muted("手機在外面用行動網路也能連回這台電腦；全程 HTTPS 加密，不需要設定路由器。"
                                       "第一次啟用會自動下載 Cloudflare 官方的 cloudflared 程式。", 12)],
                              spacing=2, expand=True)], spacing=12),
            self.t_mode, self.t_fixed, ft.Row([self.t_sw, self.t_status], spacing=16, wrap=True), self.t_bar,
            self.t_qr], spacing=12), padding=18)
        super().__init__([
            T.page_header(ft.Icons.PHONE_ANDROID, "手機打卡與連線", "員工用手機瀏覽器 GPS 打卡、請假；手機 App 也透過這台電腦連線", "rose"),
            T.card(ft.Column([ft.Row([T.icon_tile(ft.Icons.FINGERPRINT, "teal", 44), ft.Column([
                ft.Text("員工手機 GPS 打卡網頁", size=15, weight=ft.FontWeight.W_700),
                T.muted("員工用手機的 Chrome／Safari 打開打卡網址，以自己的員工帳號登入，按「上班打卡」「下班打卡」。"
                        "手機瀏覽器只允許在 HTTPS 加密網址取得 GPS 定位，所以請打開下方的「外出連線」，"
                        "再把顯示的「打卡網址」QR Code 印出來貼在公司，或傳到員工的 LINE 群組。", 12)], spacing=2,
                expand=True)], spacing=12),
                T.muted("員工帳號：到「員工資料 → 更多 → 建立員工帳號」一次建立；GPS 地點在「差勤管理 → GPS 打卡地點」設定。"
                        "距離超出允許半徑或 GPS 精確度不足的打卡會列為「待確認」，由人資在「打卡紀錄」確認。", 12)],
                spacing=10), padding=18),
            T.card(ft.Column([
                ft.Row([self.sw, self.port, self.status], spacing=18,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
                T.muted("手機用自己的帳號密碼登入，權限與電腦版相同；手機不會直接連資料庫。"
                        "這台電腦要保持開機並開著人事薪資系統，手機才連得到。", 12),
                T.muted("第一次啟用時，Windows 會詢問是否允許網路存取，請勾選「私人網路」後按「允許」。", 12)],
                spacing=10), padding=18),
            ft.Text("公司內（同一個 Wi-Fi）", size=16, weight=ft.FontWeight.W_700),
            self.urls, outside],
            spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)
        self.render(refresh=False)
        self.render_tunnel(refresh=False)

    def render_tunnel(self, refresh=True):
        t = getattr(self.app, "tunnel", None)
        on = bool(t and t.running and t.url)
        self.t_fixed.visible = self.t_mode.value == "token"
        self.t_status.content = T.chip("已連線：%s" % t.url if on else "已關閉", "green" if on else "slate",
                                       ft.Icons.PUBLIC if on else ft.Icons.PUBLIC_OFF)
        if on:
            punch = t.url.rstrip("/") + "/punch"
            self.t_qr.content = ft.Column([ft.Row([
                ft.Image(src=qr_png(punch), width=200, height=200),
                ft.Column([ft.Text("📍 員工打卡網址", size=14, weight=ft.FontWeight.W_700),
                           ft.Text(punch, size=15, weight=ft.FontWeight.W_700, color=T.ACCENT, selectable=True),
                           T.muted("手機相機掃描就能打開打卡頁（可「加入主畫面」當成 App 使用）。", 12),
                           T.btn("在這台電腦開啟", ft.Icons.OPEN_IN_BROWSER, lambda e, u=punch: self.ctx.page.launch_url(u),
                                 kind="outline")], spacing=6, expand=True)],
                spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER), ft.Row([
                ft.Image(src=qr_png(deep_link(t.url)), width=160, height=160),
                ft.Column([ft.Text(t.url, size=15, weight=ft.FontWeight.W_700, color=T.PRIMARY, selectable=True),
                           T.muted("在公司時先掃這個 QR Code；手機會記住，外出時自動改用這個網址。", 12),
                           T.muted("快速通道每次重新啟動網址都會改變，屆時請重新掃描並重新公告打卡網址；"
                                   "長期使用建議改「固定網址」。" if t.mode == "quick" else "固定網址不會改變，掃描一次即可。", 12)],
                          spacing=6, expand=True)],
                spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)], spacing=14)
        else:
            self.t_qr.content = None
        if refresh:
            self.update()

    def toggle_tunnel(self, e):
        x = self.app.st.extra
        x["tunnel_mode"] = self.t_mode.value
        x["tunnel_token"] = (self.t_token.value or "").strip()
        x["tunnel_url"] = (self.t_url.value or "").strip()
        if not self.t_sw.value:
            self.app.stop_tunnel()
            x["tunnel_enabled"] = False
            self.app.st.save()
            self.ctx.books.log("tunnel", "off")
            self.render_tunnel()
            return
        self.t_bar.visible, self.t_bar.value = True, None
        self.t_status.content = T.chip("連線中（第一次會先下載 cloudflared）…", "amber", ft.Icons.HOURGLASS_TOP)
        self.update()

        def work():
            def prog(v):
                self.t_bar.value = v
                self.t_bar.update()
            try:
                url = self.app.start_tunnel(progress=prog)
                x["tunnel_enabled"], x["api_enabled"] = True, True
                self.app.st.save()
                self.ctx.books.log("tunnel", "on", url)
                self.sw.value = True
            except Exception as ex:
                self.t_sw.value = False
                self.ctx.toast("外出連線失敗：%s" % ex, True)
            self.t_bar.visible = False
            self.render(refresh=False)
            self.render_tunnel()
        self.ctx.page.run_thread(work)

    def toggle(self, e):
        st = self.app.st
        try:
            st.extra["api_port"] = int(self.port.value or 8785)
        except ValueError:
            self.ctx.toast("連接埠要是數字", True)
            return
        if self.sw.value:
            self.app.stop_api()
            if not self.ctx.guard(self.app.start_api):
                self.sw.value = False
        else:
            self.app.stop_api()
        st.extra["api_enabled"] = bool(self.sw.value)
        st.save()
        self.ctx.books.log("mobile_service", "on" if self.sw.value else "off", str(st.extra["api_port"]))
        if not self.sw.value:
            self.t_sw.value = False                 # 關掉手機連線，外出通道也一起停止
        self.render_tunnel(refresh=False)
        self.render()

    def render(self, refresh=True):
        from ..api import lan_addresses
        on = bool(self.app.api and self.app.api.running)
        self.status.content = T.chip("服務執行中（%d 個手機登入中）" % len(self.app.api.sessions) if on else "已關閉",
                                     "green" if on else "slate", ft.Icons.WIFI_TETHERING if on else ft.Icons.WIFI_OFF)
        cards = []
        if on:
            port = self.app.api.port
            for ip in lan_addresses() or ["127.0.0.1"]:
                url = "http://%s:%d" % (ip, port)
                cards.append(T.card(ft.Column([
                    ft.Image(src=qr_png(deep_link(url)), width=200, height=200),
                    ft.Text(url, size=16, weight=ft.FontWeight.W_700, color=T.PRIMARY, selectable=True),
                    T.muted("手機 App 連線用（打卡請用外出連線的 HTTPS 打卡網址）", 11)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=16, width=260))
        else:
            cards.append(T.empty_state(ft.Icons.PHONELINK_OFF, "手機連線服務已關閉", "打開上方開關後，這裡會顯示 QR Code"))
        self.urls.controls = cards
        if refresh:
            self.update()



ACTIONS = {"login": "登入", "logout": "登出", "login_fail": "登入失敗", "password": "變更密碼",
           "doc_new": "新增單據", "doc_edit": "修改單據", "doc_void": "作廢單據", "doc_close": "結案",
           "doc_reopen": "取消結案", "receipt_new": "新增收付款", "receipt_void": "作廢收付款",
           "note_collect": "票據託收", "note_clear": "票據兌現", "note_bounce": "退票", "note_withdraw": "撤票",
           "note_pay": "應付票據兌現", "note_cancel": "應付票據作廢", "note_undo": "還原票據異動",
           "cost_close": "成本月結", "cost_reopen": "取消月結", "count_adjust": "盤差轉調整", "count_done": "盤點完成",
           "gl_batch": "產生拋轉", "gl_export": "匯出拋轉檔", "gl_send": "傳送會計", "gl_cancel": "取消拋轉",
           "gl_map": "科目對照", "master_new": "新增基本資料", "master_edit": "修改基本資料",
           "stock_rebuild": "重算庫存", "mobile_login": "手機登入", "mobile_logout": "手機登出",
           "mobile_service": "手機連線服務", "tunnel": "外出連線",
           "voucher_new": "新增傳票", "voucher_edit": "修改傳票", "voucher_delete": "刪除傳票",
           "voucher_approve": "審核", "voucher_return": "退回", "voucher_post": "過帳", "voucher_unpost": "取消過帳",
           "voucher_void": "作廢", "period_close": "關帳", "period_reopen": "重新開帳", "year_close": "年度結帳",
           "year_reopen": "取消年度結帳", "user_save": "儲存使用者", "user_delete": "刪除使用者", "company": "公司設定",
           "account_save": "儲存科目", "account_delete": "刪除科目", "master_save": "儲存基本資料",
           "master_delete": "刪除基本資料", "template_save": "儲存常用分錄", "template_delete": "刪除常用分錄",
           "backup": "備份", "restore": "還原", "update": "版本更新", "budget_save": "儲存預算",
           "mobile_login": "手機登入", "mobile_logout": "手機登出", "mobile_service": "手機連線服務",
           "ratio_save": "儲存比率公式", "ratio_delete": "刪除比率公式", "import": "匯入", "tunnel": "外出連線",
           "emp_new": "新增員工", "emp_edit": "修改員工", "emp_delete": "刪除員工", "emp_resign": "離職",
           "emp_items": "固定薪資項目", "emp_accounts": "建立員工帳號", "roster_fill": "循環排班", "roster_xml": "匯入月班表",
           "xk_export": "匯出小柯班表", "disaster": "災害停班", "punch_fix": "補登打卡", "punch_set": "確認／作廢打卡",
           "leave_new": "請假", "leave_ok": "核准請假", "leave_reject": "駁回請假", "leave_cancel": "撤銷請假",
           "ot_new": "加班", "ot_ok": "核准加班", "ot_reject": "駁回加班", "grant_annual": "產生特休", "grant_add": "新增額度",
           "settle_A": "特休結算", "settle_C": "補休結算", "occ_case": "職災案件", "pay_input": "變動輸入",
           "bonus_gen": "產生獎金", "run_new": "新增薪資批次", "run_calc": "計算薪資", "run_confirm": "確認薪資",
           "run_unconfirm": "取消確認", "run_paid": "標示發放", "run_unpaid": "取消發放", "run_delete": "刪除批次",
           "close_month": "關帳", "reopen_month": "取消關帳", "bank_file": "銀行轉帳檔", "law": "法令參數",
           "grades": "投保分級表", "leave_accrue": "特休估列"}


class Audit(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.user = T.dropdown("使用者", [(u["uid"], u["name"]) for u in ctx.books.users()], "", width=180,
                               blank="全部", filterable=False, on_select=lambda e: self.load())
        self.grid = T.Grid([("at", "時間", "s", 150), ("uid", "使用者", "s", 90), ("act", "動作", "s", 110),
                            ("target", "對象", "s", 140), ("detail", "內容", "s", 380)])
        super().__init__([T.page_header(ft.Icons.HISTORY, "操作紀錄", "最近 1000 筆，供內部稽核", "rose",
                                        [self.user, ctx.export_button(self.grid, "操作紀錄")]),
                          self.grid], spacing=12, expand=True)
        self.load(refresh=False)

    def load(self, refresh=True):
        rows = self.ctx.books.audit(1000, self.user.value or "")
        for r in rows:
            r["act"] = ACTIONS.get(r["action"], r["action"])
            r["at"] = rocdate.show(r["at"].date()) + r["at"].strftime(" %H:%M:%S")
        self.grid.set_rows(rows)
        if refresh:
            self.update()


_ = threading
