#!/usr/bin/env python3
"""Прогноз погоды на ближайшую пробежку (четверг, 20:00–21:00) у точки сбора.

Источник — Open-Meteo (https://open-meteo.com): бесплатно для некоммерческих сайтов,
без ключа, данные по лицензии CC BY 4.0 (на сайте есть подпись с источником).
Запрос делает GitHub при сборке, посетители сайта к Open-Meteo не обращаются.
Результат — data/weather.json (сборка кладёт его копию в dist/weather.json). Если сервис не ответил
с трёх попыток, берётся прогноз из прошлой сборки, если он на тот же четверг; иначе прогноз не показывается.

Запуск:  python scripts/fetch_weather.py
         python scripts/fetch_weather.py --json f   — разобрать сохранённый ответ (для проверки)
"""
import datetime as dt, json, pathlib, subprocess, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "weather.json"
MSK = dt.timezone(dt.timedelta(hours=3))

# коды погоды WMO → текст
CODES = {
    0: "ясно", 1: "преимущественно ясно", 2: "переменная облачность", 3: "пасмурно",
    45: "туман", 48: "туман с изморозью",
    51: "слабая морось", 53: "морось", 55: "сильная морось", 56: "ледяная морось", 57: "ледяная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь", 66: "ледяной дождь", 67: "ледяной дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа",
    80: "ливень", 81: "ливень", 82: "сильный ливень", 85: "снегопад", 86: "сильный снегопад",
    95: "гроза", 96: "гроза с градом", 99: "гроза с градом",
}


def next_run(now):
    d = now.replace(hour=20, minute=0, second=0, microsecond=0)
    d += dt.timedelta(days=(3 - now.weekday()) % 7)
    if d + dt.timedelta(hours=1) < now:
        d += dt.timedelta(days=7)
    return d


def load(argv):
    if "--json" in argv:
        return json.loads(pathlib.Path(argv[argv.index("--json") + 1]).read_text(encoding="utf-8"))
    q = urllib.parse.urlencode({
        "latitude": CFG["meet"]["lat"], "longitude": CFG["meet"]["lon"],
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,snowfall,wind_speed_10m,weather_code",
        "wind_speed_unit": "ms", "timezone": "Europe/Moscow", "forecast_days": 9,
    })
    req = urllib.request.Request(f"https://api.open-meteo.com/v1/forecast?{q}",
                                 headers={"User-Agent": "zachanku.ru site builder"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def summarize(data, run):
    h = data["hourly"]
    idx = {t: i for i, t in enumerate(h["time"])}
    slots = [idx.get((run + dt.timedelta(hours=k)).strftime("%Y-%m-%dT%H:00")) for k in (0, 1)]
    slots = [i for i in slots if i is not None]
    if not slots:
        return None
    pick = lambda key: [h[key][i] for i in slots if h[key][i] is not None]
    temp, feels = pick("temperature_2m"), pick("apparent_temperature")
    if not temp:
        return None
    prob, prec, snow = pick("precipitation_probability"), pick("precipitation"), pick("snowfall")
    wind, codes = pick("wind_speed_10m"), pick("weather_code")
    code = max(codes) if codes else None  # «худшая» погода за час пробежки
    w = {
        "run": run.strftime("%Y-%m-%dT%H:%M"),
        "temp": round(sum(temp) / len(temp)),
        "feels": round(sum(feels) / len(feels)) if feels else None,
        "precip_prob": max(prob) if prob else None,
        "precip_mm": round(sum(prec), 1) if prec else 0,
        "snow_cm": round(sum(snow), 1) if snow else 0,
        "wind": round(max(wind)) if wind else None,
        "code": code,
        "text": CODES.get(code, ""),
        "updated": dt.datetime.now(MSK).strftime("%Y-%m-%dT%H:%M"),
    }
    tips = []
    if code in (95, 96, 99):
        tips.append("Обещают грозу — следи за каналом, возможна отмена.")
    elif (w["precip_prob"] or 0) >= 60:
        tips.append("Вероятен дождь — пригодится непромокаемая куртка.")
    if w["snow_cm"] >= 1:
        tips.append("Снег — трейловые кроссовки будут кстати.")
    if w["temp"] <= 0:
        tips.append("Около нуля и ниже — на просеке может быть скользко.")
    if (w["wind"] or 0) >= 10:
        tips.append("Сильный ветер — пригодится ветровка.")
    w["tips"] = tips
    return w


def previous():
    """Прогноз из прошлой сборки (ветка site, файл weather.json) — на случай, если Open-Meteo не ответил."""
    try:
        subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", "site"], cwd=ROOT, check=True,
                       capture_output=True, timeout=60)
        out = subprocess.run(["git", "show", "FETCH_HEAD:weather.json"], cwd=ROOT, check=True,
                             capture_output=True, timeout=30).stdout
        return json.loads(out.decode("utf-8"))
    except Exception:
        return {}


def main():
    run = next_run(dt.datetime.now(MSK))
    data, err = None, None
    for attempt, pause in enumerate((0, 10, 30)):  # Open-Meteo иногда отвечает ошибкой или лимитом: три попытки
        time.sleep(pause)
        try:
            data = load(sys.argv)
            break
        except Exception as e:
            err = e
            print(f"[weather] попытка {attempt + 1}: Open-Meteo недоступен: {e}")
    w = summarize(data, run) if data else None
    if not w:
        old = previous()
        if old.get("run") == run.strftime("%Y-%m-%dT%H:%M"):
            w = old  # прошлый прогноз на тот же четверг; на сайте видно, когда он обновлялся
            print(f"[weather] беру прогноз из прошлой сборки (обновлён {old.get('updated')})")
        else:
            print(f"[weather] прогноза не будет: {err}")
            w = {}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[weather] {w.get('run')}: {w.get('temp')}°C, {w.get('text')}, осадки {w.get('precip_prob')}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
