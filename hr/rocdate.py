"""民國日期：畫面顯示 115/11/12，資料庫存西元 DATE。"""
import datetime as dt
import re


def today() -> dt.date:
    return dt.date.today()


def show(d) -> str:
    if not d:
        return ""
    if isinstance(d, dt.datetime):
        d = d.date()
    if isinstance(d, str):
        d = read(d)
    return "%03d/%02d/%02d" % (d.year - 1911, d.month, d.day)


def read(text) -> dt.date:
    """可輸入 115/11/12、1151112、115.11.12、2026-11-12、20261112、11/12（今年）。"""
    if isinstance(text, dt.datetime):
        return text.date()
    if isinstance(text, dt.date):
        return text
    s = (text or "").strip()
    if not s:
        raise ValueError("請輸入日期")
    parts = [p for p in re.split(r"[/\-.\s]+", s) if p]
    try:
        if len(parts) == 3:
            y, m, d = (int(p) for p in parts)
        elif len(parts) == 2:
            y, (m, d) = today().year, (int(p) for p in parts)
        elif s.isdigit() and len(s) == 8:
            y, m, d = int(s[:4]), int(s[4:6]), int(s[6:])
        elif s.isdigit() and len(s) in (6, 7):
            y, m, d = int(s[:-4]), int(s[-4:-2]), int(s[-2:])
        else:
            raise ValueError
        if y < 1000:
            y += 1911
        return dt.date(y, m, d)
    except ValueError:
        raise ValueError("日期格式不正確：%s（例如 115/11/12）" % s)


def compact(d: dt.date) -> str:
    return "%03d%02d%02d" % (d.year - 1911, d.month, d.day)


def month_first(d: dt.date) -> dt.date:
    return d.replace(day=1)


def month_last(d: dt.date) -> dt.date:
    nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def ym(d: dt.date) -> str:
    return "%04d%02d" % (d.year, d.month)


def ym_show(s: str) -> str:
    return "%03d 年 %d 月" % (int(s[:4]) - 1911, int(s[4:]))


def fiscal_year_range(year: int, start_month: int = 1):
    """會計年度（以年度開始的西元年表示）的起訖日。"""
    start = dt.date(year, start_month, 1)
    end_y, end_m = (year, 12) if start_month == 1 else (year + 1, start_month - 1)
    return start, month_last(dt.date(end_y, end_m, 1))
