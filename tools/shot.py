"""開發用：用無頭 Edge 開網頁模式並截圖，可依序執行點擊／輸入。

用法：python tools/shot.py out.png [動作…]
動作：click:x,y　type:文字　key:Enter　wait:秒
"""
import sys
import time

from playwright.sync_api import sync_playwright

import os
URL = os.environ.get("SHOT_BASE", "http://127.0.0.1:8570/") + os.environ.get("SHOT_PATH", "")


def snap(pg, path):
    """直接用 CDP 截圖（Playwright 的 screenshot 會等字型載入，Flutter 網頁會卡住）。"""
    import base64
    cdp = pg.context.new_cdp_session(pg)
    data = cdp.send("Page.captureScreenshot", {"format": "png"})["data"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))


def main():
    out = sys.argv[1]
    steps = sys.argv[2:]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        pg = b.new_page(viewport={"width": int(os.environ.get("SHOT_W", 1440)), "height": int(os.environ.get("SHOT_H", 900))})
        pg.goto(URL)
        time.sleep(9)
        n = 0
        for s in steps:
            k, _, v = s.partition(":")
            if k == "click":
                x, y = (float(t) for t in v.split(","))
                pg.mouse.click(x, y)
                time.sleep(1.2)
            elif k == "type":
                pg.keyboard.type(v, delay=30)
            elif k == "key":
                pg.keyboard.press(v)
                time.sleep(0.8)
            elif k == "wait":
                time.sleep(float(v))
            elif k == "shot":
                n += 1
                snap(pg, out.replace(".png", "_%d.png" % n))
        snap(pg, out)
        b.close()


if __name__ == "__main__":
    main()
