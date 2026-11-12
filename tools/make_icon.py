"""產生程式圖示：assets/icon.png（1024）、packaging/icon.ico、assets/icon.ico。

設計：深藍到青綠的圓角方塊，中間一張員工識別證（人像），右下角時鐘（差勤），右上角金幣寫「薪」。
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shadow(img, shape, box, radius=0, blur=18, alpha=100, off=(10, 20)):
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    x0, y0, x1, y1 = box
    b = [x0 + off[0], y0 + off[1], x1 + off[0], y1 + off[1]]
    if shape == "rr":
        d.rounded_rectangle(b, radius=radius, fill=(0, 0, 0, alpha))
    else:
        d.ellipse(b, fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(blur)))


def font(size):
    try:
        f = ImageFont.truetype(os.path.join(HERE, "assets", "fonts", "NotoSansTC-VF.ttf"), size)
        try:
            f.set_variation_by_name("Black")
        except Exception:
            try:
                f.set_variation_by_axes([900])
            except Exception:
                pass
        return f
    except Exception:
        return ImageFont.load_default()


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    c1, c2 = (20, 50, 110), (15, 140, 130)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(c1, c2, y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)
    gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse([-200, -520, S + 200, 420], fill=(255, 255, 255, 34))
    img = Image.alpha_composite(img, Image.composite(gloss, Image.new("RGBA", (S, S)), mask))
    # 識別證（掛繩＋卡片）
    d = ImageDraw.Draw(img)
    d.polygon([(420, 120), (470, 120), (512, 250), (462, 250)], fill=(230, 180, 60, 255))
    d.polygon([(604, 120), (554, 120), (512, 250), (562, 250)], fill=(210, 160, 45, 255))
    card = (250, 230, 690, 840)
    img = shadow(img, "rr", card, 46)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(card, radius=46, fill=(255, 255, 255, 255))
    d.rounded_rectangle([card[0], card[1], card[2], card[1] + 120], radius=46, fill=(30, 77, 140, 255))
    d.rectangle([card[0], card[1] + 70, card[2], card[1] + 120], fill=(30, 77, 140, 255))
    d.rounded_rectangle([450, 250, 574, 280], radius=14, fill=(255, 255, 255, 200))      # 卡夾孔
    # 人像
    cx = (card[0] + card[2]) // 2
    d.ellipse([cx - 150, 390, cx + 150, 690], fill=(226, 236, 248, 255))
    d.ellipse([cx - 62, 430, cx + 62, 554], fill=(30, 77, 140, 255))                    # 頭
    d.pieslice([cx - 118, 560, cx + 118, 780], 180, 360, fill=(30, 77, 140, 255))        # 肩
    d.rounded_rectangle([cx - 150, 720, cx + 110, 748], radius=12, fill=(203, 213, 225, 255))
    d.rounded_rectangle([cx - 150, 772, cx + 40, 798], radius=12, fill=(226, 232, 240, 255))
    # 時鐘（差勤）
    ccx, ccy, r = 735, 735, 150
    img = shadow(img, "o", (ccx - r, ccy - r, ccx + r, ccy + r))
    d = ImageDraw.Draw(img)
    d.ellipse([ccx - r, ccy - r, ccx + r, ccy + r], fill=(15, 118, 110, 255), outline=(255, 255, 255, 255), width=16)
    d.ellipse([ccx - r + 34, ccy - r + 34, ccx + r - 34, ccy + r - 34], fill=(255, 255, 255, 255))
    for i in range(12):
        import math
        a = math.radians(i * 30)
        x1, y1 = ccx + math.sin(a) * 92, ccy - math.cos(a) * 92
        x2, y2 = ccx + math.sin(a) * (78 if i % 3 else 70), ccy - math.cos(a) * (78 if i % 3 else 70)
        d.line([(x1, y1), (x2, y2)], fill=(15, 118, 110, 255), width=8 if i % 3 == 0 else 5)
    d.line([(ccx, ccy), (ccx, ccy - 66)], fill=(31, 41, 55, 255), width=14)
    d.line([(ccx, ccy), (ccx + 50, ccy + 22)], fill=(31, 41, 55, 255), width=14)
    d.ellipse([ccx - 14, ccy - 14, ccx + 14, ccy + 14], fill=(224, 165, 38, 255))
    # 金幣「薪」
    gx, gy, gr = 790, 250, 135
    img = shadow(img, "o", (gx - gr, gy - gr, gx + gr, gy + gr), blur=16, alpha=110)
    d = ImageDraw.Draw(img)
    d.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=(240, 180, 40, 255), outline=(255, 226, 140, 255), width=14)
    d.ellipse([gx - gr + 28, gy - gr + 28, gx + gr - 28, gy + gr - 28], outline=(201, 138, 20, 255), width=6)
    d.text((gx, gy - 6), "薪", font=font(130), fill=(20, 50, 92, 255), anchor="mm")
    out = os.path.join(HERE, "assets", "icon.png")
    img.save(out)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for p in (os.path.join(HERE, "packaging", "icon.ico"), os.path.join(HERE, "assets", "icon.ico")):
        img.save(p, sizes=sizes)
    print("ok", out)


if __name__ == "__main__":
    main()
