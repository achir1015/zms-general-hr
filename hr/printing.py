"""列印：把傳票或報表輸出成排版好的 HTML，用瀏覽器開啟後列印（可另存 PDF）。"""
import html
import os
import tempfile
import time

from . import APP_NAME, rocdate

CSS = """
@page { size: A4; margin: 14mm 12mm; }
body { font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", sans-serif; color: #1f2937; margin: 0;
       font-size: 12.5px; }
.wrap { max-width: 1000px; margin: 0 auto; padding: 18px; }
.head { text-align: center; margin-bottom: 10px; }
.head .co { font-size: 20px; font-weight: 700; letter-spacing: 2px; }
.head .title { font-size: 17px; font-weight: 700; color: #1e4d8c; margin-top: 4px; letter-spacing: 4px; }
.head .sub { color: #6b7280; margin-top: 3px; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th { background: #eef3fa; color: #334155; font-weight: 700; padding: 6px 8px; border: 1px solid #cbd5e1; }
td { padding: 5px 8px; border: 1px solid #dfe5ee; }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.head td { background: #f6f8fc; font-weight: 700; }
tr.sub td { font-weight: 700; border-top: 1.5px solid #94a3b8; }
tr.total td { font-weight: 800; background: #eaf2ff; border-top: 2px solid #1e4d8c; }
.meta { display: flex; justify-content: space-between; margin-top: 6px; color: #374151; }
.sign { display: flex; justify-content: space-around; margin-top: 28px; }
.sign div { width: 22%; border-top: 1px solid #94a3b8; text-align: center; padding-top: 4px; color: #4b5563; }
.foot { margin-top: 14px; color: #9ca3af; font-size: 10.5px; text-align: right; }
.bar { position: sticky; top: 0; background: #1e4d8c; padding: 8px; text-align: center; }
.bar button { font-size: 14px; padding: 6px 18px; border-radius: 8px; border: 0; background: #fff; color: #1e4d8c;
              cursor: pointer; font-weight: 700; }
@media print { .bar { display: none; } .wrap { padding: 0; } }
"""


def esc(v):
    return html.escape("" if v is None else str(v))


def page(company, title, subtitle, body):
    return ("<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><title>%s</title><style>%s</style></head>"
            "<body><div class='bar'><button onclick='window.print()'>🖨 列印／另存 PDF</button></div><div class='wrap'>"
            "<div class='head'><div class='co'>%s</div><div class='title'>%s</div><div class='sub'>%s</div></div>%s"
            "<div class='foot'>%s　列印時間 %s</div></div></body></html>"
            % (esc(title), CSS, esc(company), esc(title), esc(subtitle), body, esc(APP_NAME),
               rocdate.show(rocdate.today()) + time.strftime(" %H:%M")))


def table(columns, rows, row_class=None):
    """columns=[(key, 標題, 是否數字)]"""
    h = "<table><tr>%s</tr>" % "".join("<th>%s</th>" % esc(c[1]) for c in columns)
    for r in rows:
        cls = row_class(r) if row_class else ""
        h += "<tr class='%s'>%s</tr>" % (cls, "".join(
            "<td class='%s'>%s</td>" % ("n" if c[2] else "", esc(r.get(c[0], ""))) for c in columns))
    return h + "</table>"


mobile_saver = None     # 手機版：(檔名, bytes) → 另存到手機（由 mobile.py 設定）


def write_and_open(html_text, name):
    if mobile_saver:
        mobile_saver("%s_%s.html" % (name, time.strftime("%Y%m%d%H%M")), html_text.encode("utf-8"))
        return ""
    d = os.path.join(tempfile.gettempdir(), "ZMSGeneralHR")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "%s_%s.html" % (name, time.strftime("%Y%m%d%H%M%S")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)
    from .ui.theme import open_file
    open_file(path)
    return path


SLIP_CSS = """
.slip { border: 1.5px solid #94a3b8; border-radius: 8px; padding: 12px 14px; margin: 0 0 14px; page-break-inside: avoid; }
.slip h3 { margin: 0 0 4px; font-size: 15px; color: #1e4d8c; }
.slip .info { display: flex; flex-wrap: wrap; gap: 4px 18px; color: #374151; margin-bottom: 6px; }
.cols { display: flex; gap: 10px; }
.cols > div { flex: 1; }
.cols table { margin-top: 2px; }
.net { text-align: right; font-size: 16px; font-weight: 800; color: #1e4d8c; margin-top: 6px; }
.note { color: #6b7280; font-size: 11px; margin-top: 4px; }
.cut { border-top: 1px dashed #cbd5e1; margin: 10px 0 14px; }
"""


def _amt(v):
    try:
        return "{:,.0f}".format(float(v))
    except (TypeError, ValueError):
        return ""


def payslips_page(company, slips):
    """薪資單（一張 A4 約可印 2 位員工；每人：應發、應扣、實發、公司負擔、說明）。"""
    co = company.get("name") or ""
    body = ""
    for s in slips:
        earn = [ln for ln in s["lines"] if ln["kind"] == "E"]
        ded = [ln for ln in s["lines"] if ln["kind"] == "D"]

        def rows(ls):
            return "".join("<tr><td>%s<div class='note'>%s</div></td><td class='n'>%s</td></tr>"
                           % (esc(x["name"]), esc(x["note"]), _amt(x["amount"])) for x in ls)
        er = sum(float(s.get(k) or 0) for k in ("labor_er", "occ_er", "fund_er", "nhi_er", "pension_er"))
        body += (
            "<div class='slip'><h3>%s　%s</h3><div class='info'><span>員工：%s %s</span><span>部門：%s</span>"
            "<span>發薪日：%s</span><span>投保：勞保 %s／健保 %s／勞退 %s</span></div>"
            "<div class='cols'><div><table><tr><th>應發項目</th><th>金額</th></tr>%s"
            "<tr class='total'><td>應發合計</td><td class='n'>%s</td></tr></table></div>"
            "<div><table><tr><th>應扣項目</th><th>金額</th></tr>%s"
            "<tr class='total'><td>應扣合計</td><td class='n'>%s</td></tr></table></div></div>"
            "<div class='net'>實發金額 NT$ %s</div>"
            "<div class='note'>公司另為您負擔：勞保 %s、職災 %s、墊償 %s、健保 %s、勞退 6%% %s（合計 %s）。%s</div>"
            "<div class='note'>%s</div></div>"
            % (esc(co), esc(s.get("title", "")), esc(s["emp"]), esc(s["name"]), esc(s.get("dept", "")),
               rocdate.show(s.get("pay_date")), _amt(s.get("labor_wage")), _amt(s.get("nhi_wage")),
               _amt(s.get("pension_wage")), rows(earn), _amt(s["gross"]), rows(ded), _amt(s["deduct"]), _amt(s["net"]),
               _amt(s.get("labor_er")), _amt(s.get("occ_er")), _amt(s.get("fund_er")), _amt(s.get("nhi_er")),
               _amt(s.get("pension_er")), _amt(er), esc(company.get("slip_footer") or ""),
               esc("；".join(s.get("notes") or []))))
    html_text = page(co, "薪資明細單", "%d 位員工" % len(slips), body)
    return html_text.replace("</style>", SLIP_CSS + "</style>", 1)
