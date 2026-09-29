"""Знак бег#заЧанку: решётка-мост. Река (синяя) течёт под мостом, тропа (пунктир) идёт по мосту.
Геометрия — по макету Анатолия (координаты макета 800×880)."""
PALETTES = {
    "dark":  {"frame": "#E6ECE4", "river": "#6E9BB5", "trail": "#FFC247"},
    "light": {"frame": "#0C1310", "river": "#2F86C4", "trail": "#B87B1E"},
}
# вес линий: regular — отдельный знак крупно, bold — в слове рядом с Tektur 900 и в иконке
WEIGHTS = {
    "regular": dict(v=30, h=34, river=18, trail=16, dash="40 24"),
    "bold":    dict(v=72, h=70, river=36, trail=32, dash="64 38"),
}
VIEWS = {  # viewBox, концы реки по x, концы тропы по y
    "full": ("20 30 720 850", (43, 713), (50, 855)),
    "word": ("110 120 560 680", (110, 670), (120, 800)),
    "icon": ("0 0 760 760", (-200, 1000), (-200, 1000)),
}

# Варианты реки. Координаты макета: мост стоит в x 220–561, между перекладинами y≈397–515.
RIVERS = {
    "straight": None,  # прямая линия, как в первом макете
    "wave":    "M40 505 C160 535 250 456 390 456 S620 378 720 405",                       # А: плавная волна
    "bend":    "M95 820 C120 640 220 478 390 456 C560 434 655 330 690 110",                  # Б: излучина снизу слева вверх вправо
    "meander": "M60 456 Q115 386 170 456 T280 456 T390 456 T500 456 T610 456 T720 456",  # В: меандр
    "banks":   "M95 820 C120 640 220 478 390 456 C560 434 655 330 690 110",                  # Г: излучина с берегами
}

# в названии река короче, чтобы концы были скруглены, а не обрезаны рамкой
RIVERS_WORD = {"bend": "M175 765 C188 640 242 482 390 456 C545 430 608 352 626 158"}

def tx(y):  # тропа идёт с тем же наклоном, что и стойки решётки
    return 437 - (95 / 805) * (y - 50)

def mark(palette="dark", view="full", weight="regular", cls=None, title=True, bg=None, river="bend"):
    c = PALETTES[palette]
    w = WEIGHTS[weight]
    vb, rx, ty = VIEWS[view]
    g = ""  # для иконки знак сдвигаем в центр квадрата
    dx, dy = (0, 0)
    y1, y2 = ty[0] - dy, ty[1] - dy
    x1r, x2r = rx[0] - dx, rx[1] - dx
    a = f' class="{cls}"' if cls else ""
    t = "<title>бег#заЧанку</title>" if title else ""
    back = f'<rect width="760" height="760" rx="150" fill="{bg}"/>' if bg else ""
    rp = RIVERS_WORD.get(river, RIVERS[river]) if view == "word" else RIVERS[river]
    if rp is None:
        riv = f'<line x1="{x1r}" y1="456" x2="{x2r}" y2="456" stroke="{c["river"]}" stroke-width="{w["river"]}"/>'
    elif river == "banks":
        bgc = bg or ("#0C1310" if palette == "dark" else "#F4F6F2")
        riv = (f'<path d="{rp}" fill="none" stroke="{c["river"]}" stroke-width="{w["river"] * 2.6:.0f}" stroke-linecap="round"/>'
               f'<path d="{rp}" fill="none" stroke="{bgc}" stroke-width="{w["river"] * 1.2:.0f}" stroke-linecap="round"/>')
    else:
        riv = f'<path d="{rp}" fill="none" stroke="{c["river"]}" stroke-width="{w["river"] * 1.15:.0f}" stroke-linecap="round"/>'
    body = (riv +
            f'<g stroke="{c["frame"]}" stroke-width="{w["v"]}">'
            f'<line x1="343" y1="240" x2="285" y2="672"/><line x1="497" y1="240" x2="439" y2="672"/></g>'
            f'<g stroke="{c["frame"]}" stroke-width="{w["h"]}">'
            f'<line x1="241" y1="380" x2="561" y2="380"/><line x1="220" y1="532" x2="540" y2="532"/></g>'
            f'<line x1="{tx(y1):.1f}" y1="{y1}" x2="{tx(y2):.1f}" y2="{y2}" stroke="{c["trail"]}" '
            f'stroke-width="{w["trail"]}" stroke-dasharray="{w["dash"]}"/>')
    if view == "icon":
        body = (f'<clipPath id="r"><rect width="760" height="760" rx="150"/></clipPath><g clip-path="url(#r)">'
                f'<g transform="translate(380 380) scale(1.3) translate(-390 -456)">{body}</g></g>')
    return f'<svg{a} xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="#">{t}{back}{body}</svg>'
