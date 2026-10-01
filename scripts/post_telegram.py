#!/usr/bin/env python3
"""Публикует в Telegram-канал новые статьи блога: картинка-превью, заголовок, описание, ссылка, #блог.

Работает после выкладки сайта. Какие статьи уже опубликованы, хранится в data/posted.json,
поэтому каждая статья уходит в канал один раз. Черновики (draft: true) не публикуются.
Токен бота берётся из секрета GitHub TELEGRAM_BOT_TOKEN; без токена скрипт ничего не делает.
Бот должен быть администратором канала с правом «Публикация сообщений».

Запуск:  python scripts/post_telegram.py            — опубликовать новые статьи
         python scripts/post_telegram.py --dry-run  — только показать, что будет опубликовано
"""
import html, json, os, pathlib, re, sys, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SITE = CFG["site_url"].rstrip("/")
POSTED = ROOT / "data" / "posted.json"
PHOTO = ROOT / "dist" / "og.png"
DRY = "--dry-run" in sys.argv


def posts():
    out = []
    for f in sorted((ROOT / "content" / "posts").glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S)
        if not m:
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        if meta.get("draft", "false").lower() == "true":
            continue
        out.append(meta)
    return sorted(out, key=lambda p: p["date"])


def send_photo(token, chat, caption):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat), ("caption", caption), ("parse_mode", "HTML")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="og.png"\r\n'
                 f"Content-Type: image/png\r\n\r\n".encode() + PHOTO.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and not DRY:
        print("[telegram] нет TELEGRAM_BOT_TOKEN — пропускаю")
        return 0
    done = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else []
    new = [p for p in posts() if p["slug"] not in done]
    if not new:
        print("[telegram] новых статей нет")
        return 0
    chat = "@" + CFG["telegram_channel"]
    for p in new:
        url = f"{SITE}/blog/{p['slug']}/"
        caption = (f"<b>{html.escape(p['title'])}</b>\n\n{html.escape(p.get('description', ''))}\n\n"
                   f"Читать: {url}\n\n#блог")[:1024]
        if DRY:
            print(f"[telegram] опубликую: {p['slug']}\n{caption}\n")
            continue
        try:
            res = send_photo(token, chat, caption)
        except Exception as e:
            print(f"[telegram] не удалось опубликовать {p['slug']}: {e}")
            return 0  # не роняем сборку; попробуем при следующем запуске
        if res.get("ok"):
            done.append(p["slug"])
            POSTED.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[telegram] опубликовано: {p['slug']}")
        else:
            print(f"[telegram] Telegram ответил ошибкой для {p['slug']}: {res}")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
