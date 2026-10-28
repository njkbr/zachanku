#!/usr/bin/env python3
"""Автоматические посты недели в Telegram-канал и команды владельца в личке бота.

Что публикуется само (время московское; сборка идёт раз в 15 минут, поэтому пост может выйти на 5–15 минут позже):
  среда, 12:00    — анонс с перекличкой (#анонс) и прогнозом на четверг 20:00;
  четверг, 15:00  — «Сегодня бежим, всё в силе» (#анонс) с прогнозом и строкой про трассу.
Предупреждения владельцу в личку: в среду в 10:00 (за 2 часа до анонса) и в четверг в 13:00.

Пост не публикуется, если:
  — в канале после прошлого четверга последний пост с меткой — #отмена (как и на сайте);
  — ты сам опубликовал #анонс: в среду до 12:00 — бот не публикует анонс, в четверг — «всё в силе»;
  — неделя попала в паузу или анонс пропущен командой «пропуск»;
  — по прогнозу гроза или мороз −20 °C и ниже: тогда «всё в силе» не уходит само, бот спрашивает тебя в личке.

Команды в личке бота (принимаются только от создателя и администраторов канала, можно со слешем или без):
  отмена [причина]   — опубликовать в канале отмену ближайшего четверга (#отмена);
  пропуск            — не публиковать анонс в среду (четверговый пост останется);
  бежим              — опубликовать «всё в силе» сейчас (например, после вопроса о грозе);
  пауза 1.01–10.01   — не публиковать ничего в эти даты; «пауза снять» — отменить паузу;
  статус             — что запланировано на ближайший четверг;
  помощь             — список команд.
Латинские синонимы: /cancel, /skip, /run, /pause, /status, /help.
Чтобы бот мог писать тебе первым, один раз отправь ему /start.

Состояние хранится в data/autopost.json (номера постов бота, пауза, номер последней команды).
Токен — секрет TELEGRAM_BOT_TOKEN. Без токена скрипт ничего не делает.

Проверка без публикации:
  python scripts/autopost.py --dry-run --now 2026-10-28T12:05 [--html страница_канала.html]
"""
import datetime as dt, json, os, pathlib, re, sys, urllib.parse, urllib.request
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STATE_F = ROOT / "data" / "autopost.json"
WEATHER_F = ROOT / "data" / "weather.json"
MSK = dt.timezone(dt.timedelta(hours=3))
CHANNEL = CFG["telegram_channel"]
DRY = "--dry-run" in sys.argv

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]

# расписание: (день недели относительно четверга, час, минута)
WED_REMIND = (-1, 10, 0)
WED_POST = (-1, 12, 0)
THU_REMIND = (0, 13, 0)
THU_POST = (0, 15, 0)
THU_LAST = (0, 19, 30)   # позже «всё в силе» уже не публикуем


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def now_msk():
    s = arg("--now")
    return dt.datetime.fromisoformat(s).replace(tzinfo=MSK) if s else dt.datetime.now(MSK)


def next_thursday(now):
    """Ближайший четверг, пробежка которого (до 21:00) ещё не закончилась."""
    d = now.replace(hour=20, minute=0, second=0, microsecond=0) + dt.timedelta(days=(3 - now.weekday()) % 7)
    if d + dt.timedelta(hours=1) < now:
        d += dt.timedelta(days=7)
    return d


def at(thu, spec):
    day, h, m = spec
    return (thu + dt.timedelta(days=day)).replace(hour=h, minute=m)


def ru_date(d):
    return f"{d.day} {MONTHS[d.month - 1]}"


# ---------- Telegram ----------

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def api(method, **params):
    if DRY and method in ("sendMessage",):
        print(f"[autopost] (dry-run) {method} → {params.get('chat_id')}:\n{params.get('text')}\n")
        return {"ok": True, "result": {"message_id": 0}}
    if not TOKEN:
        return {"ok": False, "description": "нет токена"}
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def send(chat, text):
    try:
        res = api("sendMessage", chat_id=chat, text=text, disable_web_page_preview="true")
    except Exception as e:
        print(f"[autopost] не удалось отправить в {chat}: {e}")
        return None
    if not res.get("ok"):
        print(f"[autopost] Telegram ответил ошибкой ({chat}): {res}")
        return None
    return res["result"]["message_id"]


def admins():
    """Создатель и администраторы канала (люди, не боты): {user_id: is_creator}."""
    if DRY and not TOKEN:
        return {}
    try:
        res = api("getChatAdministrators", chat_id="@" + CHANNEL)
    except Exception as e:
        print(f"[autopost] не удалось получить администраторов канала: {e}")
        return {}
    if not res.get("ok"):
        return {}
    return {m["user"]["id"]: m["status"] == "creator" for m in res["result"] if not m["user"].get("is_bot")}


def owner_ids(adm):
    creators = [u for u, c in adm.items() if c]
    return creators or list(adm)


def tell_owner(adm, text):
    for u in owner_ids(adm):
        send(u, text)


# ---------- канал ----------

def channel_posts():
    """Посты с #анонс и #отмена из публичной ленты канала: [{id, date, status}] от старых к новым."""
    f = arg("--html")
    if f:
        html = pathlib.Path(f).read_text(encoding="utf-8")
    else:
        req = urllib.request.Request(f"https://t.me/s/{CHANNEL}", headers={"User-Agent": "Mozilla/5.0 (zachanku autopost)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        body = msg.select_one(".tgme_widget_message_text")
        t = msg.select_one("a.tgme_widget_message_date time[datetime]") or msg.select_one("time[datetime]")
        if not body or not t:
            continue
        low = body.get_text().lower()
        status = "cancel" if "#отмена" in low else "ok" if "#анонс" in low else None
        if status:
            out.append({"id": int(msg["data-post"].split("/")[-1]),
                        "date": dt.datetime.fromisoformat(t["datetime"]).astimezone(MSK), "status": status})
    return out


# ---------- тексты ----------

def weather_for(thu):
    try:
        w = json.loads(WEATHER_F.read_text(encoding="utf-8"))
    except Exception:
        return None
    return w if w.get("run") == thu.strftime("%Y-%m-%dT%H:%M") and w.get("temp") is not None else None


def deg(t):
    return f"{t:+d}°".replace("-", "−") if t else "0°"


def forecast_line(w):
    if not w:
        return ""
    parts = [deg(w["temp"])]
    code = w.get("code") or 0
    if code >= 45:
        parts.append(w["text"])
    elif (w.get("precip_prob") or 0) >= 40:
        parts.append(f"{w['text']}, вероятность осадков {w['precip_prob']}%" if w.get("text") else f"вероятность осадков {w['precip_prob']}%")
    else:
        parts.append("без осадков" if not w.get("text") else f"{w['text']}, без осадков")
    if (w.get("wind") or 0) >= 8:
        parts.append(f"ветер {w['wind']} м/с")
    return ", ".join(parts)


def track_line(w, thu):
    if not w:
        return ""
    t, code, prob = w["temp"], w.get("code") or 0, w.get("precip_prob") or 0
    if t <= -10:
        return "Холодно: перчатки, шапка, и не стой долго на старте."
    if w.get("snow_cm", 0) >= 1 or code in (71, 73, 75, 77, 85, 86):
        return "Снег — трейловые обязательно, ставь ногу аккуратнее."
    if -3 <= t <= 2:
        return "Местами наледь — трейловые обязательно, у моста аккуратно."
    if prob >= 60 or code in (61, 63, 65, 80, 81, 82):
        return "На просеке лужи, ноги промокнут — возьми сухие носки."
    if thu.month in (9, 10, 11):
        return "Мокро и листва — ставь ногу аккуратнее на спуске к Чанке."
    return ""


def dangerous(w):
    if not w:
        return ""
    if (w.get("code") or 0) in (95, 96, 99):
        return "по прогнозу гроза"
    if w["temp"] <= -20:
        return f"по прогнозу {w['temp']} °C"
    return ""


def text_announce(thu, w):
    f = forecast_line(w)
    return (f"В четверг, {ru_date(thu)}, бежим за Чанку 🏃\n"
            f"Сбор в {CFG['run']['gather']} у входа в лесопарк со стороны Волковского шоссе, старт в {CFG['run']['time']}. "
            f"{CFG['run']['distance_km']} км, темп около {CFG['run']['pace']}/км.\n"
            + (f"Прогноз: {f}.\n" if f else "")
            + "Отметься реакцией: 🫡 — бегу, 🤔 — возможно, 😴 — пропускаю.\n\n#анонс")


def text_thursday(thu, w, own_announce=False):
    """own_announce: на неделе был твой #анонс — время и место в нём могли быть другими, поэтому их не повторяем."""
    f, tr = forecast_line(w), track_line(w, thu)
    line = "" if own_announce else f"Сбор в {CFG['run']['gather']}, старт в {CFG['run']['time']}."
    if f:
        line += f" {f[0].upper() + f[1:]}."
    if tr:
        line += f" {tr}"
    line = line.strip()
    return ("Сегодня бежим, всё в силе ✅\n" + (line + "\n" if line else "") +
            "Не забудь светоотражатели. Кто ещё не отметился — 🫡.\n\n#анонс")


def text_cancel(thu, now, reason):
    when = f"Сегодня, {ru_date(thu)}," if now.date() == thu.date() else f"В четверг, {ru_date(thu)},"
    r = reason.strip().rstrip(".")
    return (f"{when} не бежим ❌\n" + (f"Причина: {r}.\n" if r else "") +
            "Увидимся в следующий четверг. Береги себя.\n\n#отмена")


HELP = ("Команды (можно со слешем или без):\n"
        "отмена [причина] — опубликовать отмену ближайшего четверга\n"
        "пропуск — не публиковать анонс в среду\n"
        "бежим — опубликовать «всё в силе» сейчас\n"
        "пауза 1.01–10.01 — ничего не публиковать в эти даты; «пауза снять» — отменить\n"
        "статус — что запланировано\n"
        "Бот проверяет сообщения раз в 15 минут, поэтому ответ придёт не сразу.")


# ---------- состояние ----------

def load_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def week_state(st, thu):
    key = thu.strftime("%Y-%m-%d")
    if st.get("week") != key:
        st.update({"week": key, "announce_id": None, "thursday_id": None, "cancel_id": None,
                   "skip_announce": False, "reminded": [], "asked_danger": False})
    return st


def parse_pause(arg_text, now):
    m = re.findall(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", arg_text)
    if len(m) != 2:
        return None
    ds = []
    for d, mo, y in m:
        y = int(y) + (2000 if y and len(y) == 2 else 0) if y else now.year
        ds.append(dt.date(y, int(mo), int(d)))
    a, b = ds
    if b < a:
        b = b.replace(year=b.year + 1)
    if b < now.date():
        a, b = a.replace(year=a.year + 1), b.replace(year=b.year + 1)
    return [a.isoformat(), b.isoformat()]


def paused(st, thu):
    p = st.get("pause")
    return bool(p) and p[0] <= thu.date().isoformat() <= p[1]


def status_text(st, thu, now, w, cancelled, manual):
    lines = [f"Ближайший четверг: {ru_date(thu)}."]
    if paused(st, thu):
        lines.append(f"Пауза с {st['pause'][0]} по {st['pause'][1]}: ничего не публикую.")
    elif cancelled:
        lines.append("В канале отмена: больше ничего не публикую.")
    else:
        a = at(thu, WED_POST)
        if st.get("announce_id") or manual["wed"]:
            lines.append("Анонс уже в канале.")
        elif st.get("skip_announce"):
            lines.append("Анонс пропущен командой «пропуск».")
        elif now < at(thu, THU_POST):
            lines.append(f"Анонс: {ru_date(a)} в 12:00.")
        if st.get("thursday_id") or manual["thu"]:
            lines.append("«Всё в силе» уже в канале.")
        else:
            lines.append(f"«Всё в силе»: {ru_date(thu)} в 15:00.")
        d = dangerous(w)
        if d:
            lines.append(f"Внимание: {d}. «Всё в силе» само не уйдёт, напиши «бежим» или «отмена».")
    if st.get("pause") and not paused(st, thu):
        lines.append(f"Пауза запланирована с {st['pause'][0]} по {st['pause'][1]}.")
    return "\n".join(lines)


# ---------- главное ----------

def main():
    if not TOKEN and not DRY:
        print("[autopost] нет TELEGRAM_BOT_TOKEN — пропускаю")
        return 0
    now = now_msk()
    thu = next_thursday(now)
    st = week_state(load_state(), thu)
    w = weather_for(thu)
    adm = admins()
    try:
        posts = channel_posts()
    except Exception as e:
        print(f"[autopost] канал недоступен, ничего не публикую: {e}")
        save(st)
        return 0

    since = (thu - dt.timedelta(days=6)).replace(hour=0, minute=0)
    week = [p for p in posts if p["date"] >= since]
    bot_ids = {st.get("announce_id"), st.get("thursday_id"), st.get("cancel_id")} - {None}

    def cancelled():
        return bool(week) and week[-1]["status"] == "cancel" or bool(st.get("cancel_id") and not week)

    def manual():
        own = [p for p in week if p["status"] == "ok" and p["id"] not in bot_ids]
        return {"wed": bool(own),  # свой #анонс на этой неделе — бот анонс не публикует
                "thu": any(p["date"].date() == thu.date() for p in own)}  # свой #анонс в четверг — без «всё в силе»

    def post_thursday():
        mid = send("@" + CHANNEL, text_thursday(thu, w, manual()["wed"]))
        if mid is not None:
            st["thursday_id"] = mid
            week.append({"id": mid, "date": now, "status": "ok"})
        return mid

    # 1. команды владельца
    try:
        upd = api("getUpdates", offset=st.get("offset", 0), timeout=0,
                  allowed_updates='["message"]') if TOKEN else {"ok": True, "result": []}
    except Exception as e:
        print(f"[autopost] не удалось получить сообщения боту: {e}")
        upd = {"ok": False}
    for u in upd.get("result", []) if upd.get("ok") else []:
        st["offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        chat, uid, text = m.get("chat", {}), m.get("from", {}).get("id"), (m.get("text") or "").strip()
        if chat.get("type") != "private" or not text:
            continue
        if uid not in adm:
            send(chat["id"], "Этот бот публикует посты канала t.me/" + CHANNEL + ". Анонсы — в канале.")
            continue
        cmd, _, rest = text.lstrip("/").partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd in ("start", "help", "помощь"):
            send(uid, "Привет! Буду предупреждать в среду в 10:00 и в четверг в 13:00 перед автопостами.\n\n" + HELP)
        elif cmd in ("отмена", "cancel"):
            if cancelled():
                send(uid, f"Четверг {ru_date(thu)} уже отменён.")
            else:
                mid = send("@" + CHANNEL, text_cancel(thu, now, rest))
                if mid is not None:
                    st["cancel_id"] = mid
                    week.append({"id": mid, "date": now, "status": "cancel"})
                    send(uid, f"Опубликовал отмену на {ru_date(thu)}. Передумаешь — опубликуй в канале пост с #анонс или напиши «бежим».")
        elif cmd in ("пропуск", "skip"):
            st["skip_announce"] = True
            send(uid, f"Анонс в среду не публикую. «Всё в силе» в четверг, {ru_date(thu)}, в 15:00 останется.")
        elif cmd in ("бежим", "run"):
            if st.get("thursday_id"):
                send(uid, "«Всё в силе» уже в канале.")
            elif post_thursday() is not None:
                send(uid, "Опубликовал «всё в силе».")
        elif cmd in ("пауза", "pause"):
            if rest.strip().lower() in ("снять", "off", "стоп"):
                st["pause"] = None
                send(uid, "Пауза снята.")
            else:
                p = parse_pause(rest, now)
                if not p:
                    send(uid, "Не понял даты. Пример: пауза 1.01–10.01")
                else:
                    st["pause"] = p
                    send(uid, f"Пауза с {p[0]} по {p[1]}: в эти даты ничего не публикую. Снять: «пауза снять».")
        elif cmd in ("статус", "status"):
            send(uid, status_text(st, thu, now, w, cancelled(), manual()))
        else:
            send(uid, "Не понял команду.\n\n" + HELP)

    if st.get("pause") and st["pause"][1] < now.date().isoformat():
        st["pause"] = None  # пауза закончилась

    # 2. посты и предупреждения по расписанию
    def remind(key, text):
        if key not in st["reminded"]:
            st["reminded"].append(key)
            tell_owner(adm, text)

    if paused(st, thu) or cancelled():
        print(f"[autopost] {ru_date(thu)}: {'пауза' if paused(st, thu) else 'отмена в канале'}, ничего не публикую")
        save(st)
        return 0

    man = manual()
    need_announce = not st.get("announce_id") and not man["wed"] and not st.get("skip_announce")
    if need_announce and at(thu, WED_REMIND) <= now < at(thu, WED_POST):
        remind("wed", f"В 12:00 опубликую анонс на четверг, {ru_date(thu)}:\n\n{text_announce(thu, w)}\n\n"
                      "Отменить пробежку: «отмена причина». Не публиковать анонс: «пропуск». Все команды: «помощь».")
    if need_announce and at(thu, WED_POST) <= now < at(thu, THU_POST):
        mid = send("@" + CHANNEL, text_announce(thu, w))
        if mid is not None:
            st["announce_id"] = mid
            print(f"[autopost] опубликован анонс на {ru_date(thu)}")

    if not st.get("thursday_id") and not man["thu"]:
        d = dangerous(w)
        if at(thu, THU_REMIND) <= now < at(thu, THU_POST):
            if d:
                remind("thu", f"Сегодня {d}. «Всё в силе» само не уйдёт. Напиши «бежим» или «отмена {d.replace('по прогнозу ', '')}».")
            else:
                remind("thu", f"В 15:00 опубликую:\n\n{text_thursday(thu, w, man['wed'])}\n\nОтменить: «отмена причина».")
        if at(thu, THU_POST) <= now < at(thu, THU_LAST):
            if d:
                if not st.get("asked_danger"):
                    st["asked_danger"] = True
                    tell_owner(adm, f"Сегодня {d}, «всё в силе» не публикую. Напиши «бежим» или «отмена {d.replace('по прогнозу ', '')}».")
            elif post_thursday() is not None:
                print(f"[autopost] опубликовано «всё в силе» на {ru_date(thu)}")
    save(st)
    return 0


def save(st):
    if DRY:
        print("[autopost] (dry-run) состояние:", json.dumps(st, ensure_ascii=False))
        return
    STATE_F.parent.mkdir(exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
