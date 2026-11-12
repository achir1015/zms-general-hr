"""手機版（Android／iPhone）：連線設定 → 登入 → 直向版面（上方工具列＋側邊選單）。

資料一律透過電腦版的「手機連線」服務存取（hr.remote），畫面程式與電腦版共用。
"""
import os
import urllib.parse

import flet as ft

from .. import APP_NAME, APP_SHORT, APP_VERSION
from ..core import BizError
from ..help_text import text_for
from ..remote import Client, RemoteBooks
from ..voice import speaker
from . import theme as T

IOS_INSTALL_PAGE = "https://achir1015.github.io/zms-general-hr/ios/"

# 手機不提供的功能（需要直接操作電腦上的資料庫檔案或程式）
DESKTOP_ONLY = {"backup", "update", "mobile_link", "gl_transfer", "gl_batches"}


def is_mobile(page) -> bool:
    return bool(os.environ.get("HR_MOBILE")) or page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)


def link_from_route(route):
    """掃描 QR Code 的深層連結：zmshr://connect?u=<網址> → 頁面路由 /connect?u=…"""
    if not route or "u=" not in route:
        return ""
    q = urllib.parse.urlparse(route).query or route.split("?", 1)[-1]
    return urllib.parse.parse_qs(q).get("u", [""])[0]


def gradient():
    return ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                             colors=[T.SIDEBAR_TOP, "#1E4D8C", "#0F766E"])


# ====================================================================== 連線設定
def install_audio(page):
    """手機播放 MP3：flet_audio（說明語音讀 App 內附檔案；朗讀重點由電腦產生後傳來）。"""
    try:
        import flet_audio as fa
    except Exception:
        return
    st = {"a": None, "playing": False}

    def _stop():
        a = st["a"]
        st["a"], st["playing"] = None, False
        if a is not None:
            try:
                page.services.remove(a)
                page.update()
            except Exception:
                pass

    def _play(data):
        _stop()
        a = fa.Audio(src=data, autoplay=True,
                     on_state_change=lambda e: st.__setitem__("playing", "playing" in str(e.state).lower()))
        st["a"], st["playing"] = a, True
        page.services.append(a)
        page.update()

    speaker.ext_play = lambda data: page.run_thread(_play, data)
    speaker.ext_stop = lambda: page.run_thread(_stop)
    speaker.ext_playing = lambda: st["playing"]


def is_tablet(page) -> bool:
    """iPad（或寬螢幕平板）：用電腦版版面（側邊欄），資料一樣透過電腦的手機連線服務。"""
    if os.environ.get("HR_TABLET"):
        return True
    w = page.width or 0
    return page.platform == ft.PagePlatform.IOS and w >= 900


def start(app):
    p = app.page
    T.MOBILE = not is_tablet(p)
    T.TABLET = not T.MOBILE
    if T.MOBILE:
        T.install_mobile_hooks()
    install_audio(p)

    def on_route(e):
        """App 已開著時又掃了 QR Code：換連到新的公司電腦。"""
        link = link_from_route(p.route)
        if link and link != (app.client.url if app.client else ""):
            remember(app, link)
            if app.books and getattr(app.books, "user", None):
                app.books.logout()
            p.drawer = None
            connect(app, link)
    p.on_route_change = on_route
    url = link_from_route(p.route) or os.environ.get("HR_DEV_SERVER") or app.st.extra.get("server_url", "")
    if link_from_route(p.route):
        remember(app, url)
    if url:
        connect(app, url, quiet=True)
    else:
        connect_screen(app)


def connect_screen(app, msg="", url=""):
    p = app.page
    url_f = T.field("公司電腦的連線網址", url or app.st.extra.get("server_url", ""), hint_text="例：192.168.6.172:8785",
                    prefix_icon=ft.Icons.LINK, keyboard_type=ft.KeyboardType.URL)
    info = ft.Text(msg, color=T.DANGER if msg else T.MUTED, size=13)

    def go(e=None):
        info.value, info.color = "連線中…", T.MUTED
        p.update()
        connect(app, url_f.value)
    url_f.on_submit = go
    p.controls.clear()
    p.add(ft.SafeArea(ft.Container(ft.Column([
        ft.Container(height=20),
        ft.Image(src="icon.png", width=88, height=88),
        ft.Text(APP_SHORT, size=26, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE),
        ft.Text("手機連線設定", size=15, color="#CFE0F7"),
        ft.Container(ft.Column([
            ft.Row([T.icon_tile(ft.Icons.QR_CODE_SCANNER, "teal", 52, radius=16)],
                   alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("連到公司的公司電腦", size=18, weight=ft.FontWeight.W_700),
            T.muted("在電腦版「系統管理 → 手機連線」開啟服務後：用手機相機掃描畫面上的 QR Code 會自動帶入；"
                    "或把畫面上的網址輸入下面。", 13),
            url_f, info,
            ft.FilledButton("連線", icon=ft.Icons.LINK, height=48, on_click=go, bgcolor=T.PRIMARY,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)))],
            spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor=T.CARD, border_radius=20, padding=20, width=None if T.MOBILE else 460),
        T.muted("v%s" % APP_VERSION, 11)],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10, scroll=ft.ScrollMode.AUTO),
        padding=20, expand=True, gradient=gradient()), expand=True))
    p.update()


def remember(app, url):
    """記住連線網址（最多 4 個，最近成功的放最前面）：公司內網址與外出通道網址都記得。"""
    from ..remote import normalize
    url = normalize(url)
    lst = [url] + [u for u in app.st.extra.get("server_urls", []) if u != url]
    app.st.extra["server_urls"] = lst[:4]
    app.st.extra["server_url"] = url
    app.st.save()


def connect(app, url, quiet=False):
    from ..remote import normalize
    saved = [u for u in app.st.extra.get("server_urls", []) if u != normalize(url)]
    c = Client(url, alternates=saved)
    try:
        try:
            info = c.ping()
        except BizError:
            if not c._switch():                  # 這個網址連不上 → 試其他記住的網址
                raise
            info = c.ping()
    except BizError as e:
        connect_screen(app, str(e) if not quiet else "上次的公司電腦目前連不上：%s" % e, url)
        return
    if info.get("app") != APP_NAME:
        connect_screen(app, "這個網址不是人事薪資系統的手機連線服務", url)
        return
    remember(app, c.url)
    c.on_switch = lambda u: remember(app, u)
    app.client = c
    app.books = RemoteBooks(c)
    app.reports = app.books
    app.server_info = info
    app.ctx = T.Ctx(app)
    speaker.remote_tts = c.tts
    from .. import printing
    printing.mobile_saver = lambda name, data: app.page.run_task(app.ctx.save_bytes, name, data)
    c.on_relogin = lambda reason: app.page.run_thread(lambda: login(app, reason))
    login(app)


# ====================================================================== 登入
def login(app, msg=""):
    p = app.page
    info = getattr(app, "server_info", {}) or {}
    uid = T.field("帳號", app.st.last_user, prefix_icon=ft.Icons.PERSON_OUTLINE)
    pw = T.field("密碼", "", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK_OUTLINE,
                 autofocus=bool(app.st.last_user))
    err = ft.Text(msg, color=T.DANGER, size=13)

    def go(e=None):
        try:
            app.books.login(uid.value, pw.value)
        except BizError as ex:
            err.value = str(ex)
            p.update()
            return
        app.st.last_user = app.books.uid
        app.st.save()
        app.main()
    pw.on_submit = go
    dev = os.environ.get("HR_DEV_LOGIN")          # 開發測試：自動登入並開啟網址指定的畫面
    if dev and not msg:
        u, _, w = dev.partition(":")
        app.books.login(u, w)
        route, _, q = (p.route or "").strip("/").partition("?")
        T.MZ_OFF = set(urllib.parse.parse_qs(q).get("off", [""])[0].split(",")) - {""}
        app.main()
        if route and app.find(route):
            app.go(route)
        return
    p.controls.clear()
    p.add(ft.SafeArea(ft.Container(ft.Column([
        ft.Container(height=16),
        ft.Image(src="icon.png", width=80, height=80),
        ft.Text(APP_SHORT, size=26, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE),
        ft.Text(info.get("company") or "", size=15, color="#CFE0F7"),
        ft.Container(ft.Column([
            ft.Text("歡迎回來", size=22, weight=ft.FontWeight.W_800), T.muted("請用您在人事薪資系統的帳號登入", 13),
            uid, pw, err,
            ft.FilledButton("登入", icon=ft.Icons.LOGIN, height=48, on_click=go, bgcolor=T.PRIMARY,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12))),
            ft.Row([T.btn("更換公司電腦", ft.Icons.LINK, lambda e: connect_screen(app), kind="ghost"),
                    T.btn("聽說明", ft.Icons.VOLUME_UP,
                          lambda e: speaker.say_help("quickstart", text_for("quickstart")[1]), kind="ghost")],
                   alignment=ft.MainAxisAlignment.CENTER, wrap=True)],
            spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor=T.CARD, border_radius=20, padding=20, width=None if T.MOBILE else 460),
        T.muted("已連線：%s　v%s" % (app.client.url, APP_VERSION), 11)],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10, scroll=ft.ScrollMode.AUTO),
        padding=20, expand=True, gradient=gradient()), expand=True))
    p.update()


# ====================================================================== 主畫面
def main(app):
    p = app.page
    u = app.books.user
    app.title = ft.Text("", size=17, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE, expand=True,
                        no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
    app.sidebar = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)

    async def open_menu(e):
        await p.show_drawer()

    top = ft.Container(ft.Row([
        ft.IconButton(ft.Icons.MENU, icon_color=ft.Colors.WHITE, on_click=open_menu, tooltip="選單"),
        app.title,
        ft.IconButton(ft.Icons.VOLUME_UP, icon_color=ft.Colors.WHITE, tooltip="本頁說明",
                      on_click=lambda e: app.speak_page()),
        ft.IconButton(ft.Icons.HOME_ROUNDED, icon_color=ft.Colors.WHITE, tooltip="首頁",
                      on_click=lambda e: app.go("home"))], spacing=0),
        gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT,
                                   colors=[T.SIDEBAR_TOP, T.PRIMARY]),
        padding=ft.Padding.only(left=4, right=4, top=4, bottom=4))
    avatar = ft.Container(ft.Text(u["name"][:1], color=ft.Colors.WHITE, weight=ft.FontWeight.W_700), width=40,
                          height=40, border_radius=20, bgcolor=T.ACCENT, alignment=ft.Alignment.CENTER)
    p.drawer = ft.NavigationDrawer(bgcolor=T.SIDEBAR_TOP, controls=[
        ft.Container(ft.Column([
            ft.Row([ft.Image(src="icon.png", width=40, height=40),
                    ft.Column([ft.Text("資料助秘", size=11, color="#9FB6D8"),
                               ft.Text(APP_SHORT, size=17, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE)],
                              spacing=0)], spacing=10),
            ft.Row([avatar, ft.Column([ft.Text(u["name"], color=ft.Colors.WHITE, size=14, weight=ft.FontWeight.W_600),
                                       ft.Text((app.server_info or {}).get("company", ""), color="#9FB6D8",
                                               size=11)], spacing=0, expand=True)], spacing=10)], spacing=14),
            padding=ft.Padding.only(left=18, right=12, top=20, bottom=10)),
        ft.Divider(color="#2A4A78", height=1),
        ft.Container(app.sidebar, padding=ft.Padding.symmetric(horizontal=8, vertical=6), height=None),
        ft.Divider(color="#2A4A78", height=1),
        ft.Container(ft.Column([
            ft.TextButton("變更密碼", icon=ft.Icons.KEY, on_click=lambda e: app.change_password(),
                          style=ft.ButtonStyle(color="#D5E0F0")),
            ft.TextButton("登出", icon=ft.Icons.LOGOUT, on_click=lambda e: app.logout(),
                          style=ft.ButtonStyle(color="#D5E0F0")),
            ft.TextButton("更換公司電腦", icon=ft.Icons.LINK, on_click=lambda e: switch_server(app),
                          style=ft.ButtonStyle(color="#D5E0F0")),
            ft.Text("v%s　已連線 %s" % (APP_VERSION, app.client.url), size=10, color="#7F98BF")], spacing=0),
            padding=ft.Padding.only(left=12, bottom=16))])
    app.body = ft.Container(expand=True, padding=ft.Padding.only(left=12, right=12, top=12, bottom=8))
    app.crumb = ft.Row()                      # 電腦版用，手機不顯示
    app.update_banner = ft.Container(visible=False)
    p.controls.clear()
    p.add(ft.SafeArea(ft.Column([top, app.body], expand=True, spacing=0), expand=True))
    app.go("home")
    p.run_thread(check_update, app)


def check_update(app):
    """手機版：有新版時在選單最上方顯示提示，點一下用瀏覽器下載新的安裝檔。"""
    from .. import maintenance
    try:
        info = maintenance.check_update(platform="ios" if app.page.platform == ft.PagePlatform.IOS else "android")
    except Exception:
        return
    if not info:
        return
    if app.page.platform == ft.PagePlatform.IOS:      # iPhone／iPad：開 GitHub Pages 安裝頁
        info["url"] = IOS_INSTALL_PAGE

    async def open_dl(e):
        await ft.UrlLauncher().launch_url(info["url"] or info["page"])
    banner = ft.Container(ft.Row([ft.Icon(ft.Icons.SYSTEM_UPDATE, color=ft.Colors.WHITE),
                                  ft.Text("有新版本 v%s，點這裡下載" % info["version"], color=ft.Colors.WHITE,
                                          weight=ft.FontWeight.W_600, expand=True)]),
                          bgcolor=T.ACCENT, border_radius=12, padding=12, margin=ft.Margin.symmetric(horizontal=10),
                          on_click=open_dl, ink=True)
    try:
        if app.page.drawer is not None:               # 手機：放在側邊選單最上面
            app.page.drawer.controls.insert(1, banner)
        else:                                         # iPad：電腦版版面上方的提示
            app.update_banner.content = ft.Container(
                ft.Text("有新版本 v%s，點這裡下載" % info["version"], color=ft.Colors.WHITE, size=13,
                        weight=ft.FontWeight.W_600), bgcolor=T.ACCENT, border_radius=20, on_click=open_dl,
                padding=ft.Padding.symmetric(horizontal=12, vertical=6))
            app.update_banner.visible = True
        app.ctx.toast("有新版本 v%s，請下載更新" % info["version"])
        app.page.update()
    except Exception:
        pass


def switch_server(app):
    app.books.logout()
    app.st.extra.pop("server_url", None)
    app.st.extra.pop("server_urls", None)       # 換一台公司電腦：舊的網址都不要了
    app.st.save()
    connect_screen(app)


async def close_drawer(page):
    try:
        await page.close_drawer()
    except Exception:
        pass
