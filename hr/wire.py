"""手機與電腦之間傳資料的格式：JSON，金額（Decimal）與日期要原樣還原。"""
import datetime as dt
import json
from decimal import Decimal


def _enc(o):
    if isinstance(o, Decimal):
        return {"$d": str(o)}
    if isinstance(o, dt.datetime):
        return {"$dt": o.isoformat()}
    if isinstance(o, dt.date):
        return {"$date": o.isoformat()}
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    raise TypeError("無法傳送的資料型別：%s" % type(o).__name__)


def _dec(d):
    if len(d) == 1:
        if "$d" in d:
            return Decimal(d["$d"])
        if "$date" in d:
            return dt.date.fromisoformat(d["$date"])
        if "$dt" in d:
            return dt.datetime.fromisoformat(d["$dt"])
    return d


def dumps(obj) -> bytes:
    return json.dumps(obj, default=_enc, ensure_ascii=False).encode("utf-8")


def loads(data):
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data, object_hook=_dec)
