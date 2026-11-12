"""產生使用說明語音：assets/voice/<章節>.mp3（微軟神經語音 臺灣華語 曉臻）。

用法：python tools/make_voice.py   （需要網路；已存在且內容未變的檔案會略過）
"""
import asyncio
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import edge_tts  # noqa: E402

from hr.help_text import GUIDE  # noqa: E402
from hr.voice import VOICE  # noqa: E402

OUT = os.path.join(HERE, "assets", "voice")
MANIFEST = os.path.join(OUT, "manifest.json")


async def main():
    os.makedirs(OUT, exist_ok=True)
    done = json.load(open(MANIFEST, encoding="utf-8")) if os.path.isfile(MANIFEST) else {}
    from hr import adoption
    items = [(s["key"], adoption.spoken(s)) for s in adoption.SECTIONS]
    items += [(key, "%s。%s" % (title, text)) for key, title, text in GUIDE]
    for key, spoken in items:
        h = hashlib.sha1((VOICE + spoken).encode("utf-8")).hexdigest()
        path = os.path.join(OUT, key + ".mp3")
        if done.get(key) == h and os.path.isfile(path):
            continue
        for i in range(6):                  # 語音服務偶爾回 503（忙碌），稍等重試
            try:
                await edge_tts.Communicate(spoken, VOICE, rate="+5%").save(path)
                break
            except Exception as e:
                print("retry", key, i + 1, str(e)[:60])
                await asyncio.sleep(10 * (i + 1))
        else:
            print("FAIL", key)
            continue
        done[key] = h
        json.dump(done, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("ok", key, os.path.getsize(path))
        await asyncio.sleep(1.5)


if __name__ == "__main__":
    asyncio.run(main())
