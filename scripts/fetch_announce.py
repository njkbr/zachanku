#!/usr/bin/env python3
"""Берёт последний пост с #анонс или #отмена из публичного Telegram-канала
и сохраняет его в data/announce.json. Сборка сайта кладёт этот файл в главную.

Источник — публичная веб-версия канала https://t.me/s/<канал>, без бота и токенов.
Если пост с меткой удалили, а других постов с метками нет, анонс с сайта убирается.
Если канал недоступен (сбой сети), файл не трогаем: на сайте останется прошлый анонс.
Устаревший анонс страница сама перестаёт показывать после окончания пробежки в четверг (21:00).

Запуск:  python scripts/fetch_announce.py            — канал из config.json
         python scripts/fetch_announce.py --html f   — разобрать сохранённую страницу (для проверки)
"""
import json, re, sys, pathlib, urllib.request
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "announce.json"

TAGS = {"#анонс": "ok", "#отмена": "cancel"}


def load_html(argv):
    if "--html" in argv:
        return pathlib.Path(argv[argv.index("--html") + 1]).read_text(encoding="utf-8")
    url = f"https://t.me/s/{CFG['telegram_channel']}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (zachanku site builder)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    found = None
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        body = msg.select_one(".tgme_widget_message_text")
        t = msg.select_one("a.tgme_widget_message_date time[datetime]") or msg.select_one("time[datetime]")
        if not body or not t:
            continue
        for br in body.find_all("br"):
            br.replace_with("\n")
        raw = body.get_text()
        low = raw.lower()
        status = None
        for tag, st in TAGS.items():
            if tag in low:
                status = st  # #отмена проверяется последней и важнее
        if not status:
            continue
        text = re.sub(r"#(анонс|отмена)\b", "", raw, flags=re.I)
        # строка со ссылкой на сам сайт (её добавляют автопосты) на сайте не нужна
        site = CFG["site_url"].replace("https://", "").rstrip("/")
        text = "\n".join(l for l in text.split("\n") if l.strip().lower() not in (site, "https://" + site, "https://" + site + "/"))
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        post = msg["data-post"]  # вида "zachanku/123"
        found = {  # страница канала идёт от старых постов к новым: берём последний подходящий
            "status": status,
            "text": text[:600],
            "date": t["datetime"],
            "url": f"https://t.me/{post}",
        }
    return found


def main():
    try:
        html = load_html(sys.argv)
    except Exception as e:  # сеть, блокировка, канал не найден
        print(f"[announce] канал недоступен, оставляю прежний анонс: {e}")
        return 0
    a = parse(html)
    if not a:
        # в канале нет постов с метками (например, анонс удалили) — убираем анонс с сайта
        if OUT.exists() and OUT.read_text(encoding="utf-8").strip() not in ("", "{}"):
            OUT.write_text("{}\n", encoding="utf-8")
            print("[announce] постов с #анонс или #отмена нет, анонс на сайте убран")
        else:
            print("[announce] постов с #анонс или #отмена нет")
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[announce] {a['status']}: {a['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
