#!/usr/bin/env python3
"""Сборка сайта бег#заЧанку в папку dist/.

  python build.py              — боевая сборка (черновики draft: true не попадают на сайт)
  python build.py --drafts     — вместе с черновиками, для проверки
  python build.py --artifact   — превью для Claude (dist-artifact/, с черновиками и примером анонса)

Зависимости: pip install markdown beautifulsoup4 pillow
"""
import datetime as dt
import html, json, pathlib, re, shutil, sys
import markdown
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts"))
from mark import mark, tx as trail_x, PALETTES, WEIGHTS  # знак-мост

ROOT = pathlib.Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ARTIFACT = "--artifact" in sys.argv
DRAFTS = "--drafts" in sys.argv or ARTIFACT
OUT = ROOT / ("dist-artifact" if ARTIFACT else "dist")
SITE = CFG["site_url"].rstrip("/")
MSK = dt.timezone(dt.timedelta(hours=3))
NOW = dt.datetime.now(MSK)
TG = f"https://t.me/{CFG['telegram_channel']}"
EMAIL = "beg@zachanku.ru"
COPY_YEARS = "2026" if NOW.year <= 2026 else f"2026–{NOW.year}"
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
e = html.escape


# ---------- утилиты ----------
def ru_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def next_thursday():
    d = NOW.replace(hour=20, minute=0, second=0, microsecond=0)
    d += dt.timedelta(days=(3 - NOW.weekday()) % 7)
    if d + dt.timedelta(hours=1) < NOW:
        d += dt.timedelta(days=7)
    return d


def wordmark():
    """Название с мостом вместо решётки. Для поиска и копирования текста решётка остаётся в aria-label."""
    return ('<span class="wm" aria-label="бег#заЧанку"><span aria-hidden="true">бег</span>'
            + mark("dark", "word", "bold", cls="m", title=False).replace('role="img" aria-label="#"', 'aria-hidden="true" focusable="false"')
            + '<span aria-hidden="true">заЧанку</span></span>')


def href(path, depth):
    """path: '' — главная, 'blog/' — блог, 'blog/slug/' — статья, можно с #якорем."""
    anchor = ""
    if "#" in path:
        path, anchor = path.split("#", 1)
        anchor = "#" + anchor
    if depth == 0 and path == "" and anchor:
        return anchor
    rel = "../" * depth + path
    if ARTIFACT and (path == "" or path.endswith("/")):
        rel += "index.html"
    if rel == "":
        rel = "./"
    return rel + anchor


def asset(name, depth):
    return "../" * depth + name


# ---------- посты ----------
def load_posts():
    posts = []
    for f in sorted((ROOT / "content" / "posts").glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if not m:
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        meta["draft"] = meta.get("draft", "false").lower() == "true"
        if meta["draft"] and not DRAFTS:
            continue
        meta["date"] = dt.date.fromisoformat(meta["date"])
        meta["tags"] = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        body = m.group(2)
        meta["html"] = markdown.markdown(body, extensions=["extra", "sane_lists"])
        words = len(re.sub(r"<[^>]+>", " ", meta["html"]).split())
        meta["minutes"] = max(1, round(words / 180))
        posts.append(meta)
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ---------- общие части страницы ----------
DISCLAIMER_SHORT = ("<b>Не рекомендация.</b> Всё, что написано на сайте, — личный опыт участников. "
                    "Это не медицинский совет и не программа тренировок. Прежде чем начинать бегать "
                    "или увеличивать нагрузку, посоветуйтесь с врачом.")


def head(title, desc, path, depth, og_type="website", jsonld=None, noindex=False):
    url = f"{SITE}/{path}"
    tags = [
        f"<title>{e(title)}</title>",
        f'<meta name="description" content="{e(desc)}">',
        f'<link rel="canonical" href="{e(url)}">',
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:site_name" content="{e(CFG["name"])}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{e(url)}">',
        f'<meta property="og:image" content="{SITE}/og.png">',
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
        '<meta property="og:locale" content="ru_RU">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="theme-color" content="#0C1310">',
        f'<link rel="icon" href="{asset("favicon.svg", depth)}" type="image/svg+xml">',
        f'<link rel="alternate" type="application/rss+xml" title="{e(CFG["name"])} — блог" href="{SITE}/feed.xml">',
        f'<link rel="preload" href="{asset("fonts/tektur-cyrillic-900-normal.woff2", depth)}" as="font" type="font/woff2" crossorigin>',
        f'<link rel="stylesheet" href="{asset("style.css", depth)}">',
    ]
    if noindex:
        tags.append('<meta name="robots" content="noindex">')
    if CFG["verification"].get("yandex"):
        tags.append(f'<meta name="yandex-verification" content="{e(CFG["verification"]["yandex"])}">')
    if CFG["verification"].get("google"):
        tags.append(f'<meta name="google-site-verification" content="{e(CFG["verification"]["google"])}">')
    for block in (jsonld or []):
        tags.append('<script type="application/ld+json">' + json.dumps(block, ensure_ascii=False) + "</script>")
    return "\n".join(tags)



def header(depth, current=""):
    cur = lambda k: ' aria-current="page"' if current == k else ""
    return f"""<header class="top">
  <div class="wrap">
    <a class="logo" href="{href('', depth)}" title="На главную">{wordmark()}</a>
    <nav class="nav" aria-label="Основное меню">
      <a class="l" href="{href('#route', depth)}">Маршрут</a>
      <a class="l" href="{href('#kit', depth)}">Что взять</a>
      <a class="l" href="{href('blog/', depth)}"{cur('blog')}>Блог</a>
      <a class="l" href="{href('#faq', depth)}">Вопросы</a>
    </nav>
    <a class="btn sm tg-top" href="{TG}" target="_blank" rel="noopener">Telegram</a>
  </div>
</header>"""


def footer(depth):
    return f"""<footer>
  <div class="wrap cols">
    <div>
      <h3>Ответственность</h3>
      <p>{wordmark()} — это не организованное спортивное мероприятие, а встреча знакомых, которые бегают вместе. Здесь нет организатора, судей, медицинского сопровождения и страховки.</p>
      <p>Каждый участник бежит добровольно, сам оценивает своё здоровье и подготовку и сам отвечает за свою безопасность и снаряжение. Несовершеннолетние бегут только со взрослыми.</p>
      <p><b style="color:var(--pine)">Не рекомендация.</b> Статьи блога и тексты на сайте — личный опыт, а не медицинский совет и не программа тренировок. Прежде чем начинать бегать, посоветуйтесь с врачом.</p>
    </div>
    <div id="privacy">
      <h3>Данные и cookies</h3>
      <p>Сайт не собирает персональные данные. Здесь нет форм, регистрации, счётчиков посещений и рекламы, сайт не ставит cookies, а шрифты загружаются с этого же сайта.</p>
      <p>В вашем браузере сохраняется только отметка о том, что вы закрыли уведомление внизу экрана. Она никуда не передаётся, её можно удалить, очистив данные сайта.</p>
      <p>Ссылки на Telegram ведут на сторонний сервис со своими правилами обработки данных.</p>
      <p>Если вы напишете нам на почту, адрес и письмо используются только для ответа и никому не передаются.</p>
      <p style="margin-top:18px"><a href="{href('blog/', depth)}">Блог</a> · <a href="{SITE}/feed.xml">RSS</a> · <a href="{TG}" target="_blank" rel="noopener">Telegram</a></p>
    </div>
  </div>
  <div class="wrap foot-bottom">
    <span>© {COPY_YEARS} {wordmark()}. Тексты и изображения — с указанием ссылки на zachanku.ru.</span>
    <span>Обратная связь: <a href="mailto:{EMAIL}">{EMAIL}</a></span>
  </div>
</footer>
<div class="notice" id="notice" role="region" aria-label="Уведомление о данных" hidden>
  <p><b>Здесь нет cookies и слежки.</b> Мы не собираем данные и не ставим счётчики. <a href="#privacy">Подробнее</a></p>
  <button class="btn sm" id="noticeOk" type="button">Понятно</button>
</div>
<script src="{asset('main.js', depth)}" defer></script>"""


def page(title, desc, path, depth, body, current="", og_type="website", jsonld=None, noindex=False, bare=False):
    h = head(title, desc, path, depth, og_type, jsonld, noindex)
    content = f"{header(depth, current)}\n{body}\n{footer(depth)}"
    if bare:  # главная превью-артефакта: без doctype, его добавляет платформа
        return h + "\n" + content
    return (f'<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            f"{h}\n</head>\n<body>\n{content}\n</body>\n</html>\n")


def post_card(p, depth):
    flag = ' <span class="draft-flag">черновик</span>' if p["draft"] else ""
    return (f'<a class="post-card" href="{href("blog/" + p["slug"] + "/", depth)}">'
            f'<span class="meta">{ru_date(p["date"])} · {p["minutes"]} мин чтения{flag}</span>'
            f'<h3>{e(p["title"])}</h3><p>{e(p["description"])}</p><span class="more">Читать →</span></a>')



def _deg(t):
    if t is None:
        return ""
    return ("+" if t > 0 else "−" if t < 0 else "") + str(abs(int(t))) + " °C"


def render_weather(w, run):
    """Блок прогноза для ближайшей пробежки. Пустая строка, если прогноза нет или он не на этот четверг."""
    if not w or not w.get("run") or w["run"] != run.strftime("%Y-%m-%dT%H:%M"):
        return ""
    meet = CFG["meet"]
    ya = f"https://yandex.ru/pogoda/?lat={meet['lat']}&lon={meet['lon']}"
    main = f"<b>{_deg(w.get('temp'))}</b>"
    if w.get("feels") is not None and w.get("feels") != w.get("temp"):
        main += f" <span>ощущается как {_deg(w['feels'])}</span>"
    if w.get("text"):
        main += f" <span>· {e(w['text'])}</span>"
    row = []
    if w.get("precip_prob") is not None:
        row.append(f"осадки {w['precip_prob']}%")
    if w.get("wind") is not None:
        row.append(f"ветер {w['wind']} м/с")
    tips = "".join(f"<li>{e(t)}</li>" for t in w.get("tips", []))
    head = f"Прогноз на четверг, {run.day} {MONTHS[run.month - 1]}, 20:00–21:00"
    return (f'<div class="weather" id="weather" data-run="{e(w["run"])}">'
            f'<div class="w-head">{head}</div>'
            f'<div class="w-main">{main}</div>'
            + (f'<div class="w-row">{" · ".join(row)}</div>' if row else "")
            + (f'<ul class="w-tips">{tips}</ul>' if tips else "")
            + f'<div class="w-src">У точки сбора · данные '
              f'<a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> (CC BY 4.0) · '
              f'<a href="{e(ya)}" target="_blank" rel="noopener">Подробнее на Яндекс Погоде →</a></div></div>')

# ---------- главная ----------
def build_index(posts):
    run = next_thursday()
    meet = CFG["meet"]
    route_svg = (ROOT / "static" / "_routemap.svg.txt").read_text(encoding="utf-8")
    announce_path = ROOT / "data" / "announce.json"
    announce = json.loads(announce_path.read_text(encoding="utf-8")) if announce_path.exists() else {}
    if ARTIFACT and not announce:  # пример анонса только для превью
        announce = {"status": "ok", "date": (run - dt.timedelta(days=1)).replace(hour=12).isoformat(),
                    "text": "Завтра бежим! Прогноз +6 °C, без осадков. У Чанки после дождей мокро, берите обувь с протектором.",
                    "url": TG}
    announce_json = json.dumps(announce, ensure_ascii=False).replace("</", "<\\/")
    weather_path = ROOT / "data" / "weather.json"
    weather = json.loads(weather_path.read_text(encoding="utf-8")) if weather_path.exists() else {}
    if ARTIFACT and not weather:  # пример прогноза только для превью
        weather = {"run": run.strftime("%Y-%m-%dT%H:%M"), "temp": 6, "feels": 3, "precip_prob": 20,
                   "wind": 4, "text": "пасмурно", "tips": []}
    weather_html = render_weather(weather, run)
    yandex = f"https://yandex.ru/maps/?pt={meet['lon']},{meet['lat']}&z=17&l=map"

    event = {
        "@context": "https://schema.org", "@type": "Event",
        "name": f"{CFG['name_plain']} — вечерняя пробежка 10 км по четвергам",
        "description": CFG["description"],
        "startDate": run.isoformat(), "endDate": (run + dt.timedelta(hours=1)).isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "isAccessibleForFree": True,
        "eventSchedule": {"@type": "Schedule", "byDay": "https://schema.org/Thursday", "repeatFrequency": "P1W",
                          "startTime": "20:00", "endTime": "21:00", "scheduleTimezone": "Europe/Moscow",
                          "startDate": run.date().isoformat()},
        "location": {"@type": "Place", "name": f"Мытищинский лесопарк, {meet['label'].lower()}",
                     "address": {"@type": "PostalAddress", "addressLocality": meet["city"],
                                 "addressRegion": meet["region"], "addressCountry": "RU"},
                     "geo": {"@type": "GeoCoordinates", "latitude": meet["lat"], "longitude": meet["lon"]}},
        "organizer": {"@type": "Organization", "name": CFG["name"], "url": SITE + "/"},
        "offers": {"@type": "Offer", "price": 0, "priceCurrency": "RUB", "url": SITE + "/",
                   "availability": "https://schema.org/InStock"},
        "image": SITE + "/og.png",
    }
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": CFG["name"],
               "alternateName": CFG["name_plain"], "url": SITE + "/", "inLanguage": "ru"}

    blog_block = ""
    if posts:
        cards = "".join(post_card(p, 0) for p in posts[:3])
        blog_block = f"""
  <section id="blog">
    <div class="wrap">
      <div class="eyebrow">Блог</div>
      <h2>Наблюдения и опыт</h2>
      <p class="lead">Пишем о том, что замечаем на бегу: про стресс, погоду, снаряжение и про то, как бег меняет неделю.</p>
      <div class="posts">{cards}</div>
      <div class="disclaimer" style="margin-top:22px"><p>{DISCLAIMER_SHORT}</p></div>
    </div>
  </section>"""

    body = f"""<main id="top">
  <section class="hero" id="hero">
    <canvas id="topo" aria-hidden="true"></canvas>
    <div class="hero-mark" aria-hidden="true">{mark("dark", "full", "regular", title=False).replace('role="img" aria-label="#"', 'focusable="false"')}</div>
    <div class="wrap">
      <h1><span class="kicker">Пробежка в Мытищинском лесопарке по четвергам</span>Четверг.<br><span class="lit">20:00.</span><br>10&nbsp;км за&nbsp;Чанку.</h1>
      <p class="tagline">{e(CFG['tagline'])}.</p>
      <p class="sub">Всю неделю организм копит напряжение, которому некуда деться. В четверг вечером даём ему выход: 10&nbsp;км по освещённой просеке за реку Чанку и обратно. Бесплатно, без регистрации, в компании.</p>
      <div class="cta">
        <a class="btn" href="{TG}" target="_blank" rel="noopener">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.4 3.6 2.9 10.7c-1.3.5-1.3 1.2-.2 1.5l4.7 1.5 1.8 5.6c.2.6.1.9.8.9.5 0 .7-.2 1-.5l2.3-2.2 4.8 3.5c.9.5 1.5.2 1.7-.8l3.1-14.7c.3-1.3-.5-1.9-1.5-1.5ZM8.7 13.4l9.6-6c.5-.3.9-.1.5.2l-8 7.3-.3 3.4-1.8-4.9Z"/></svg>
          Вступить в канал
        </a>
        <a class="btn ghost" href="#route">Посмотреть маршрут</a>
      </div>
      <div class="next" id="next" aria-live="polite">
        <span class="eyebrow">Ближайшая пробежка</span>
        <b id="nextDate">чт, {run.day} {MONTHS[run.month - 1]}, 20:00</b>
        <span id="nextIn"></span>
      </div>
      {weather_html}
      <div class="announce" id="announce" hidden><b>Анонс из канала</b><p></p><a href="{TG}" target="_blank" rel="noopener">Открыть пост в Telegram →</a></div>
      <script type="application/json" id="announce-data">{announce_json}</script>
    </div>
  </section>

  <section class="facts-sec">
    <div class="wrap">
      <div class="facts">
        <div class="fact"><div class="eyebrow">Когда</div><div class="v">ЧТ 20:00</div><div class="d">каждую неделю, круглый год</div></div>
        <div class="fact"><div class="eyebrow">Дистанция</div><div class="v">10 км</div><div class="d">туда и обратно, грунт и просека</div></div>
        <div class="fact"><div class="eyebrow">Темп</div><div class="v">6:00 /км</div><div class="d">разговорный, около часа в лесу</div></div>
        <div class="fact"><div class="eyebrow">Стоимость</div><div class="v">0 ₽</div><div class="d">без взносов и регистрации</div></div>
      </div>
    </div>
  </section>

  <section id="route">
    <div class="wrap">
      <div class="eyebrow">Маршрут</div>
      <h2>Три километра по прямой, потом зигзаг за Чанку</h2>
      <p class="lead">Маршрут туда и обратно: убегаем на 5 км, разворачиваемся и возвращаемся тем же путём. Старт и финиш в одной точке. Трасса освещена, заблудиться сложно, поэтому для бега в Мытищах вечером это, пожалуй, самое удобное место. Зимой трассу, как правило, укатывает ратрак, так что бежать можно круглый год.</p>
      <div class="route">
        <div class="map">
          {route_svg}
        </div>
          <ol class="legs">
            <li><div class="km">0,0</div><div><b>Сбор и старт</b><span>{e(meet['label'])}. Собираемся в {CFG['run']['gather']}, стартуем ровно в {CFG['run']['time']}.</span></div></li>
            <li><div class="km">0–3,0</div><div><b>Просека на север</b><span>Три километра по прямой через Мытищинский лесопарк.</span></div></li>
            <li><div class="km">3,0</div><div><b>Налево</b><span>Полкилометра на запад по лесной дороге.</span></div></li>
            <li><div class="km">3,5</div><div><b>Направо, через Чанку {mark("dark", "word", "bold", cls="leg-mark", title=False).replace('role="img" aria-label="#"', 'aria-hidden="true" focusable="false"')}</b><span>Полкилометра на север, по мосту через реку, как на нашем логотипе. После дождей здесь мокро.</span></div></li>
            <li><div class="km">4,0</div><div><b>Налево</b><span>Последний отрезок на запад, к краю посёлка.</span></div></li>
            <li><div class="km">5,0</div><div><b>Разворот</b><span>Ждём последнего и бежим обратно тем же путём.</span></div></li>
            <li><div class="km">10</div><div><b>Финиш</b><span>Там же, где старт. Около 21:00.</span></div></li>
          </ol>
          <div class="meet">
            <div class="meet-info">
            <div class="eyebrow">Точка сбора</div>
            <div class="coords"><code id="coords">{meet['lat']:.6f}, {meet['lon']:.6f}</code><button class="btn sm ghost" id="copyCoords" type="button">Скопировать</button></div>
            <div class="links">
              <a href="{e(yandex)}" target="_blank" rel="noopener">Открыть в Яндекс Картах</a>
              <span class="dl">Скачать трек: <a href="route.gpx" download="zachanku-10km.gpx">GPX</a> · <a href="route.kml" download="zachanku-10km.kml">KML</a> · <a href="route.tcx" download="zachanku-10km.tcx">TCX</a></span>
            </div>
            <div class="park">
              <span class="p-badge" aria-hidden="true">P</span>
              <div><b>Парковка у ТЦ «Июнь»</b>, ул. Мира, 51. До старта около 250 метров, 3–4 минуты пешком: через ул. Мира и Волковское шоссе по двум переходам со светофорами. По данным справочников, первые 3 часа бесплатно, этого хватает на пробежку со сбором. Условия лучше проверить на въезде.
              <a href="https://yandex.ru/maps/org/iyun/30007788202/" target="_blank" rel="noopener">ТЦ «Июнь» на Яндекс Картах</a></div>
            </div>
            </div>
            <svg class="walk" viewBox="0 0 360 230" role="img" aria-label="Как дойти от парковки ТЦ «Июнь» до старта: через ул. Мира и Волковское шоссе по двум переходам со светофорами">
                <rect width="360" height="230" fill="#101915"/>
                <path d="M0 0 H360 V58 L0 66 Z" fill="#17261E"/>
                <text x="12" y="22" fill="#56705F" font-family="Golos Text, sans-serif" font-size="11">Мытищинский лесопарк</text>
                <path d="M0 92 L360 86" stroke="#2F3E36" stroke-width="30"/>
                <path d="M0 92 L360 86" stroke="#4A5A52" stroke-width="1.5" stroke-dasharray="10 8"/>
                <text x="350" y="112" fill="#8EA197" font-family="Golos Text, sans-serif" font-size="11" text-anchor="end">Волковское шоссе</text>
                <path d="M40 118 C120 150 220 196 300 234" fill="none" stroke="#2F3E36" stroke-width="22"/>
                <text x="262" y="196" fill="#8EA197" font-family="Golos Text, sans-serif" font-size="11" transform="rotate(26 262 196)">ул. Мира</text>
                <rect x="0" y="176" width="120" height="54" fill="#1F2D26"/>
                <text x="12" y="220" fill="#E6ECE4" font-family="Golos Text, sans-serif" font-size="12" font-weight="600">Парковка ТЦ «Июнь»</text>
                <path d="M200 52 L201 134 L128 186" fill="none" stroke="#E6ECE4" stroke-width="2.5" stroke-dasharray="3 5" stroke-linecap="round"/>
                <g fill="#E6ECE4" opacity=".55"><rect x="192" y="73" width="18" height="3"/><rect x="192" y="80" width="18" height="3"/><rect x="192" y="87" width="18" height="3"/><rect x="192" y="94" width="18" height="3"/><rect x="192" y="101" width="18" height="3"/></g>
                <g transform="rotate(-36 168 160)" fill="#E6ECE4" opacity=".55"><rect x="158" y="150" width="3" height="18"/><rect x="165" y="150" width="3" height="18"/><rect x="172" y="150" width="3" height="18"/><rect x="179" y="150" width="3" height="18"/></g>
                <g><rect x="214" y="70" width="10" height="22" rx="3" fill="#0C1310" stroke="#8EA197"/><circle cx="219" cy="76" r="2.4" fill="#FF7A6B"/><circle cx="219" cy="85" r="2.4" fill="#5FD08A"/></g>
                <g><rect x="182" y="146" width="10" height="22" rx="3" fill="#0C1310" stroke="#8EA197"/><circle cx="187" cy="152" r="2.4" fill="#FF7A6B"/><circle cx="187" cy="161" r="2.4" fill="#5FD08A"/></g>
                <rect x="112" y="178" width="22" height="22" rx="4" fill="#3E86C8"/>
                <text x="123" y="194" fill="#fff" font-family="Tektur, sans-serif" font-weight="700" font-size="15" text-anchor="middle">P</text>
                <circle cx="200" cy="48" r="10" fill="#FFC247"/>
                <text x="200" y="52" fill="#1A1406" font-family="Tektur, sans-serif" font-weight="700" font-size="10" text-anchor="middle">С</text>
                <text x="216" y="44" fill="#E6ECE4" font-family="Golos Text, sans-serif" font-size="12" font-weight="600">Старт</text>
              </svg>
          </div>
          <p class="note">Схема построена по треку пробежки 1 октября 2026 года: 10 км от точки сбора и обратно. GPX подходит для большинства часов и приложений, KML — для Google Earth и Яндекс Карт, TCX — для Garmin (курс с виртуальным партнёром в темпе 6:00/км).</p>
      </div>
    </div>
  </section>

  <section id="kit">
    <div class="wrap">
      <div class="eyebrow">Что взять</div>
      <h2>Трасса освещена, но в осенне-зимнее время в 20:00 в лесу всё равно ночь</h2>
      <div class="kit">
        <div class="item"><span class="tag must">Обязательно</span><h3>Светоотражатели</h3><p>Жилет, браслет или полосы на одежде. На старте и финише рядом дороги и машины.</p></div>
        <div class="item"><span class="tag must">Обязательно</span><h3>Заряженный телефон</h3><p>С треком маршрута и номером кого-то из группы.</p></div>
        <div class="item"><span class="tag nice">На всякий случай</span><h3>Налобный фонарь</h3><p>Трасса освещена, но фонари вдоль неё могут не работать. С налобником от 200 люмен это не проблема.</p></div>
        <div class="item"><span class="tag nice">Желательно</span><h3>Кроссовки с протектором</h3><p>Грунт, листья, зимой укатанный снег. Трейловых кроссовок достаточно.</p></div>
        <div class="item"><span class="tag nice">Желательно</span><h3>Вода и слой одежды</h3><p>Час в лесу, к концу пробежки становится заметно холоднее.</p></div>
        <div class="item"><span class="tag nice">Желательно</span><h3>Трек в часах</h3><p>Загрузи GPX маршрута в часы или приложение, и разворот не пропустишь.</p></div>
      </div>
    </div>
  </section>

  <section id="how">
    <div class="wrap">
      <div class="eyebrow">Как это устроено</div>
      <h2>От подписки до финиша</h2>
      <ol class="steps">
        <li><div class="t">любой день</div><h3>Подпишись на канал</h3><p>Там анонсы, отмены, погода и трек. Анонс из канала сам появляется на этом сайте.</p></li>
        <li><div class="t">среда</div><h3>Перекличка</h3><p>Пост «кто завтра?». Жмёшь реакцию, чтобы мы знали, сколько ждать.</p></li>
        <li><div class="t">четверг {CFG['run']['gather']}</div><h3>Сбор у старта</h3><p>Знакомимся, разминаемся, назначаем замыкающего.</p></li>
        <li><div class="t">20:00 — ≈21:00</div><h3>Бежим</h3><p>10 км в темпе около 6:00 на км, на поворотах и развороте собираемся вместе.</p></li>
      </ol>
    </div>
  </section>

  <section id="faq">
    <div class="wrap">
      <div class="eyebrow">Правила и вопросы</div>
      <h2>Коротко о главном</h2>
      <div class="two">
        <div>
          <h3 style="font:600 18px/1.3 var(--body);margin-bottom:18px">Пять правил</h3>
          <ul class="rules">
            <li>Никого не бросаем. Последним всегда бежит замыкающий.</li>
            <li>На поворотах ждём, пока соберутся все.</li>
            <li>Светоотражатели обязательны, налобник желателен.</li>
            <li>Плохо себя чувствуешь — скажи, сойдём вместе.</li>
            <li>Мусор уносим с собой. Это наш лес.</li>
          </ul>
          <div class="disclaimer" style="margin-top:28px"><p>{DISCLAIMER_SHORT}</p></div>
        </div>
        <div>
          <details><summary>Почему «бег#заЧанку»?</summary><p>На 3,5 км мы перебегаем реку Чанку, так что бежим за Чанку в прямом смысле. А ещё «за» — как в «ложке за маму» или «стопке за деда»: делаем что-то в честь кого-то. У нас это десятка за Чанку. Туда за Чанку, обратно за себя.</p></details>
          <details><summary>Где бегать в Мытищах вечером, когда темно?</summary><p>Мы бегаем в Мытищинском лесопарке: от входа со стороны Волковского шоссе на север идёт освещённая просека, по ней можно бегать и после заката. Мы бежим 10 км туда и обратно, с разворотом за рекой Чанкой. Трек можно скачать выше и пробежать его в любой день, но в четверг в 20:00 вместе веселее.</p></details>
          <details><summary>Я никогда не бегал 10 км. Мне можно?</summary><p>Если спокойно пробегаешь 5–6 км, приходи. Темп около 6:00 на км, никто не гонится. Для первого раза лучше заранее написать в канал. И сначала посоветуйся с врачом, если давно не было нагрузок.</p></details>
          <details><summary>Это соревнование? Есть протокол и время?</summary><p>Нет. Это дружеская пробежка, без судей, результатов и призов. Время каждый считает на своих часах.</p></details>
          <details><summary>А если дождь или мороз?</summary><p>Бежим почти в любую погоду. Отменяем при грозе, тотальном ливне, сильном гололёде, морозе ниже −20 °C и после сильного снегопада, пока ратрак ещё не укатал трассу. Об отмене пишем в канал до 18:00, и она сразу видна на этом сайте.</p></details>
          <details><summary>Как добраться и где оставить машину?</summary><p>На машине — парковка у ТЦ «Июнь» (ул. Мира, 51), от неё до старта около 250 метров через два перехода со светофорами. На автобусе — до остановки «ТРЦ Июнь». Точка сбора и парковка отмечены на схеме маршрута.</p></details>
          <details><summary>Можно с собакой?</summary><p>Можно, на поводке и если собака выдерживает 10 км.</p></details>
          <details><summary>Сколько стоит?</summary><p>Нисколько. Мы ничего не продаём и не собираем деньги.</p></details>
        </div>
      </div>
    </div>
  </section>
{blog_block}
  <section>
    <div class="wrap">
      <div class="join">
        <div>
          <h2>Следующая пробежка в четверг, 20:00</h2>
          <p>Анонсы, отмены и перекличка — в Telegram. Сайт нужен, чтобы было удобно поделиться ссылкой.</p>
          <div class="handle">@{e(CFG['telegram_channel'])}</div>
        </div>
        <a class="btn" href="{TG}" target="_blank" rel="noopener">Открыть канал в Telegram</a>
      </div>
    </div>
  </section>
</main>"""
    title = f"{CFG['name']} — пробежка в Мытищах по четвергам, 10 км по лесопарку"
    return page(title, CFG["description"], "", 0, body, jsonld=[website, event], bare=ARTIFACT)


# ---------- блог ----------
def build_blog_index(posts):
    cards = "".join(post_card(p, 1) for p in posts) or '<p class="lead">Первая статья скоро появится.</p>'
    body = f"""<main>
  <section class="page-head">
    <div class="wrap">
      <div class="eyebrow">Блог {wordmark()}</div>
      <h1>Наблюдения и опыт</h1>
      <p class="lead">Пишем о том, что замечаем на бегу: про стресс и адреналин, погоду, снаряжение и про то, как десятка по четвергам меняет неделю.</p>
      <div class="disclaimer" style="margin-top:24px"><p>{DISCLAIMER_SHORT}</p></div>
      <div class="posts">{cards}</div>
    </div>
  </section>
</main>"""
    blog = {"@context": "https://schema.org", "@type": "Blog", "name": f"Блог {CFG['name']}",
            "url": f"{SITE}/blog/", "inLanguage": "ru"}
    return page(f"Блог — {CFG['name']}", "Личный опыт о беге, стрессе и вечерних пробежках в Мытищинском лесопарке. Не медицинская рекомендация.",
                "blog/", 1, body, current="blog", jsonld=[blog])


def build_post(p):
    path = f"blog/{p['slug']}/"
    tags = "".join(f"<span>{e(t)}</span>" for t in p["tags"])
    flag = '<span class="draft-flag">черновик, на сайт не публикуется</span> ' if p["draft"] else ""
    body = f"""<main>
  <article class="article">
    <div class="wrap">
      <p style="margin:40px 0 0"><a class="back" href="{href('blog/', 2)}">← Все статьи</a></p>
      <h1>{e(p['title'])}</h1>
      <div class="byline">{flag}<span>{ru_date(p['date'])}</span><span>{p['minutes']} мин чтения</span></div>
      <div class="disclaimer"><p>{DISCLAIMER_SHORT}</p></div>
      <div class="prose">
{p['html']}
      </div>
      <div class="article-end">
        <div class="tags">{tags}</div>
        <div class="disclaimer"><p><b>Ещё раз: это не рекомендация.</b> Мы рассказываем о своём опыте и ощущениях. Если у вас есть вопросы о здоровье или нагрузке, обратитесь к врачу.</p></div>
        <div class="join" style="padding:28px">
          <div><h2 style="font-size:26px">Пробежим вместе?</h2><p>Каждый четверг в 20:00, 10 км за Чанку и обратно.</p></div>
          <a class="btn" href="{href('', 2)}">Подробнее о пробежке</a>
        </div>
      </div>
    </div>
  </article>
</main>"""
    ld = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"],
          "description": p["description"], "datePublished": p["date"].isoformat(),
          "dateModified": p["date"].isoformat(), "inLanguage": "ru",
          "author": {"@type": "Organization", "name": CFG["name"], "url": SITE + "/"},
          "publisher": {"@type": "Organization", "name": CFG["name"], "url": SITE + "/"},
          "mainEntityOfPage": f"{SITE}/{path}", "image": SITE + "/og.png",
          "keywords": ", ".join(p["tags"])}
    return path, page(f"{p['title']} — {CFG['name']}", p["description"], path, 2, body,
                      current="blog", og_type="article", jsonld=[ld], noindex=p["draft"])


def build_404():
    body = f"""<main><section class="center404"><div class="wrap">
  <div class="eyebrow">404</div><h1 style="font-size:clamp(36px,7vw,72px);margin-top:12px">Здесь тропинка обрывается</h1>
  <p class="lead">Такой страницы нет. Возвращайтесь на просеку.</p>
  <p style="margin-top:24px"><a class="btn" href="/">На главную</a></p></div></section></main>"""
    return page(f"Страница не найдена — {CFG['name']}", "Страница не найдена", "404.html", 0, body, noindex=True)


# ---------- служебные файлы ----------
def sitemap(posts):
    urls = [("", NOW.date().isoformat(), "weekly", "1.0"), ("blog/", NOW.date().isoformat(), "weekly", "0.8")]
    urls += [(f"blog/{p['slug']}/", p["date"].isoformat(), "monthly", "0.7") for p in posts if not p["draft"]]
    items = "".join(f"<url><loc>{SITE}/{u}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>"
                    for u, m, c, pr in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n'


def rss(posts):
    items = ""
    for p in posts:
        if p["draft"]:
            continue
        d = dt.datetime.combine(p["date"], dt.time(9, 0), MSK).strftime("%a, %d %b %Y %H:%M:%S %z")
        items += (f"<item><title>{e(p['title'])}</title><link>{SITE}/blog/{p['slug']}/</link>"
                  f"<guid>{SITE}/blog/{p['slug']}/</guid><pubDate>{d}</pubDate><description>{e(p['description'])}</description></item>")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{e(CFG["name"])} — блог</title>'
            f"<link>{SITE}/blog/</link><description>Наблюдения и опыт о беге</description><language>ru</language>{items}</channel></rss>\n")


def robots():
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n"


def og_image(path):
    """Картинка-превью 1200×630 для ссылок в Telegram и соцсетях."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[og] Pillow не установлен, картинку-превью пропускаю")
        return
    fonts = ROOT / "static" / "og-fonts"
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#0C1310")
    d = ImageDraw.Draw(im)
    for r in range(520, 0, -8):  # мягкое пятно света налобника
        a = int(38 * (1 - r / 520) ** 1.6)
        d.ellipse([260 - r, 300 - r * .75, 260 + r, 300 + r * .75], fill=(12 + a, 19 + int(a * .8), 16))
    import math
    for i in range(1, 22):  # горизонтали
        base = i * 42
        pts = []
        for deg in range(0, 361, 4):
            t = math.radians(deg)
            rr = base * (1 + .16 * math.sin(3 * t + i * .35) + .08 * math.cos(5 * t - i * .2))
            pts.append((940 + rr * math.cos(t) * 1.25, 280 + rr * math.sin(t)))
        d.line(pts, fill=(40, 52, 46) if i % 5 else (58, 72, 64), width=1)
    tk = ImageFont.truetype(str(fonts / "tektur-900.ttf"), 132)
    tk_lat = ImageFont.truetype(str(fonts / "tektur-latin-900.ttf"), 132)
    gl = ImageFont.truetype(str(fonts / "golos-400.ttf"), 38)
    gl_lat = ImageFont.truetype(str(fonts / "golos-latin-400.ttf"), 38)

    def draw_mark(dr, x0, y0, height, view):
        """Рисует знак-мост высотой height; возвращает правый край."""
        from mark import VIEWS
        vb = [float(v) for v in VIEWS[view][0].split()]
        rx, ty = VIEWS[view][1], VIEWS[view][2]
        k = height / vb[3]
        P = lambda X, Y: (x0 + (X - vb[0]) * k, y0 + (Y - vb[1]) * k)
        c, w = PALETTES["dark"], WEIGHTS["bold"]
        from mark import RIVERS_WORD
        rp = RIVERS_WORD["bend"]
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", rp)]
        x0p, y0p, segs = nums[0], nums[1], nums[2:]
        pts = [(x0p, y0p)]
        for i in range(0, len(segs), 6):  # кубические кривые Безье
            (c1x, c1y, c2x, c2y, ex, ey) = segs[i:i + 6]
            sx, sy = pts[-1]
            for t in [j / 24 for j in range(1, 25)]:
                u = 1 - t
                pts.append((u**3*sx + 3*u*u*t*c1x + 3*u*t*t*c2x + t**3*ex, u**3*sy + 3*u*u*t*c1y + 3*u*t*t*c2y + t**3*ey))
        # в слове река обрезается рамкой знака
        vx0, vy0, vw, vh = vb
        pts = [(min(max(X, vx0), vx0 + vw), min(max(Y, vy0), vy0 + vh)) for X, Y in pts]
        dr.line([P(X, Y) for X, Y in pts], fill=c["river"], width=round(w["river"] * 1.15 * k), joint="curve")
        for a, b in (((343, 240), (285, 672)), ((497, 240), (439, 672))):
            dr.line([P(*a), P(*b)], fill=c["frame"], width=round(w["v"] * k))
        for a, b in (((241, 380), (561, 380)), ((220, 532), (540, 532))):
            dr.line([P(*a), P(*b)], fill=c["frame"], width=round(w["h"] * k))
        on, off = (float(v) for v in w["dash"].split())
        y1, y2 = ty
        L = ((trail_x(y2) - trail_x(y1)) ** 2 + (y2 - y1) ** 2) ** .5
        t = 0.0
        while t < L:
            t2 = min(t + on, L)
            ya, yb = y1 + (y2 - y1) * t / L, y1 + (y2 - y1) * t2 / L
            dr.line([P(trail_x(ya), ya), P(trail_x(yb), yb)], fill=c["trail"], width=round(w["trail"] * k))
            t += on + off
        return x0 + vb[2] * k

    def draw_mixed(x, y, text, f_cyr, f_lat, colors):
        for ch, col in zip(text, colors):
            f = f_cyr if re.match(r"[А-Яа-яЁё]", ch) else f_lat
            d.text((x, y), ch, font=f, fill=col)
            x += d.textlength(ch, font=f)
        return x

    # «бег» + мост + «заЧанку»
    x = draw_mixed(72, 150, "бег", tk, tk_lat, ["#E6ECE4"] * 3)
    xt, xb = d.textbbox((0, 150), "е", font=tk)[1::2]  # верх и низ строчных букв
    mh = 132 * 1.3
    from mark import VIEWS
    vb_top, vb_h = (float(v) for v in VIEWS["word"][0].split()[1::2])
    y0 = (xt + xb) / 2 - (456 - vb_top) / vb_h * mh  # река — по центру строчных
    x = draw_mark(d, x - 6, y0, mh, "word") - 6
    draw_mixed(x, 150, "заЧанку", tk, tk_lat, ["#E6ECE4"] * 7)
    line = "Туда за Чанку, обратно за себя."
    draw_mixed(76, 330, line, gl, gl_lat, ["#FFC247"] * len(line))
    info = "Четверг · 20:00 · 10 км · Мытищинский лесопарк"
    draw_mixed(76, 400, info, gl, gl_lat, ["#E6ECE4"] * len(info))
    small = "Бесплатно · без регистрации · темп 6:00 /км"
    gls = ImageFont.truetype(str(fonts / "golos-400.ttf"), 30)
    gls_lat = ImageFont.truetype(str(fonts / "golos-latin-400.ttf"), 30)
    draw_mixed(76, 520, small, gls, gls_lat, ["#8EA197"] * len(small))
    im.save(path, optimize=True)


# ---------- сборка ----------
def main():
    posts = load_posts()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in (ROOT / "static").iterdir():
        if f.name.startswith("_") or f.name == "og-fonts":
            continue
        (shutil.copytree if f.is_dir() else shutil.copy)(f, OUT / f.name)
    (OUT / "index.html").write_text(build_index(posts), encoding="utf-8")
    (OUT / "blog").mkdir()
    (OUT / "blog" / "index.html").write_text(build_blog_index(posts), encoding="utf-8")
    for p in posts:
        path, html_ = build_post(p)
        (OUT / path).mkdir(parents=True, exist_ok=True)
        (OUT / path / "index.html").write_text(html_, encoding="utf-8")
    (OUT / "404.html").write_text(build_404(), encoding="utf-8")
    (OUT / "sitemap.xml").write_text(sitemap(posts), encoding="utf-8")
    (OUT / "feed.xml").write_text(rss(posts), encoding="utf-8")
    (OUT / "robots.txt").write_text(robots(), encoding="utf-8")
    og_image(OUT / "og.png")
    print(f"Готово: {OUT.relative_to(ROOT)}/ — статей {len(posts)}"
          + (" (с черновиками)" if DRAFTS else ""))


if __name__ == "__main__":
    main()
