"""開發用：逐一截圖各畫面（需以 run_web.py 啟動，且設定 HR_DEV_LOGIN）。

用法：python tools/shots_all.py 輸出資料夾 [畫面代號…]
"""
import base64
import os
import sys
import time

from playwright.sync_api import sync_playwright

def screens():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from hr.ui.shell import menu
    return [it[0] for g in menu() for it in g[3]]


def main():
    out = sys.argv[1]
    names = sys.argv[2:] or screens()
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        for n in names:
            pg = b.new_page(viewport={"width": int(os.environ.get("SHOT_W", 1440)), "height": int(os.environ.get("SHOT_H", 900))})
            errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.goto(os.environ.get("SHOT_BASE", "http://127.0.0.1:8570/") + n)
            time.sleep(7)
            cdp = pg.context.new_cdp_session(pg)
            with open(os.path.join(out, n.replace("?", "_").replace(",", "-").replace("=", "-").replace("/", "_") + ".png"), "wb") as f:
                f.write(base64.b64decode(cdp.send("Page.captureScreenshot", {"format": "png"})["data"]))
            print(n, "errors:", errors[:2] if errors else "none", flush=True)
            pg.close()
        b.close()


if __name__ == "__main__":
    main()
