(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var months = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];
  var RUN_MIN = 60; // длительность пробежки, минут

  function plural(n, a, b, c) {
    n = Math.abs(n) % 100; var n1 = n % 10;
    if (n > 10 && n < 20) return c; if (n1 > 1 && n1 < 5) return b; if (n1 === 1) return a; return c;
  }

  // Ближайший четверг 20:00 по Москве (UTC+3 круглый год).
  // Все вычисления в «московских» часах, записанных в UTC-поля даты.
  function nextRun(now) {
    var msk = new Date(now.getTime() + 3 * 3600e3);
    var d = new Date(Date.UTC(msk.getUTCFullYear(), msk.getUTCMonth(), msk.getUTCDate(), 20, 0, 0));
    var add = (4 - msk.getUTCDay() + 7) % 7;
    d.setUTCDate(d.getUTCDate() + add);
    if (add === 0 && msk.getTime() > d.getTime() + RUN_MIN * 60e3) d.setUTCDate(d.getUTCDate() + 7);
    var running = msk.getTime() >= d.getTime() && msk.getTime() <= d.getTime() + RUN_MIN * 60e3;
    return { start: d, running: running, diff: d.getTime() - msk.getTime() };
  }

  // Анонс из Telegram (кладётся в страницу при сборке сайта).
  // Относится к ближайшему четвергу, если опубликован не раньше чем за 6 дней до него.
  function readAnnounce(run) {
    var el = $("announce-data"); if (!el) return null;
    try {
      var a = JSON.parse(el.textContent);
      if (!a || !a.date || !a.status) return null;
      var postedMsk = new Date(new Date(a.date).getTime() + 3 * 3600e3);
      var from = run.start.getTime() - 6 * 86400e3, to = run.start.getTime() + RUN_MIN * 60e3;
      return (postedMsk.getTime() >= from && postedMsk.getTime() <= to) ? a : null;
    } catch (e) { return null; }
  }

  function tick() {
    var dateEl = $("nextDate"); if (!dateEl) return;
    var r = nextRun(new Date()), a = readAnnounce(r);
    var box = $("next"), inEl = $("nextIn"), ann = $("announce");
    dateEl.textContent = "чт, " + r.start.getUTCDate() + " " + months[r.start.getUTCMonth()] + ", 20:00";

    if (a && a.status === "cancel") {
      box.classList.add("cancel");
      inEl.textContent = "в этот четверг не бежим";
    } else if (r.running) {
      inEl.textContent = "бежим прямо сейчас";
    } else {
      var m = Math.floor(r.diff / 60e3), days = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
      inEl.textContent = "через " + (days ? days + " " + plural(days, "день", "дня", "дней") + " " : "") + h + " ч " + mm + " мин";
    }
    if (ann) {
      if (a && a.text) {
        ann.hidden = false;
        ann.className = "announce" + (a.status === "cancel" ? " cancel" : "");
        ann.querySelector("b").textContent = a.status === "cancel" ? "Отмена" : "Анонс из канала";
        ann.querySelector("p").textContent = a.text;
        var link = ann.querySelector("a");
        if (a.url) { link.href = a.url; link.hidden = false; } else link.hidden = true;
      } else ann.hidden = true;
    }
  }
  tick(); setInterval(tick, 30e3);

  // Копирование координат точки сбора
  var cb = $("copyCoords");
  if (cb) cb.addEventListener("click", function () {
    var node = $("coords"), txt = node.textContent;
    function done() { cb.textContent = "Скопировано"; setTimeout(function () { cb.textContent = "Скопировать"; }, 1800); }
    function fallback() {
      var r = document.createRange(); r.selectNodeContents(node);
      var s = getSelection(); s.removeAllRanges(); s.addRange(r);
      cb.textContent = "Выделено, нажмите Ctrl+C";
    }
    try { navigator.clipboard.writeText(txt).then(done, fallback); } catch (e) { fallback(); }
  });

  // Уведомление о данных: отметка «Понятно» хранится только в браузере посетителя
  var KEY = "zachanku_notice_ok", notice = $("notice");
  if (notice) {
    var seen = false; try { seen = localStorage.getItem(KEY) === "1"; } catch (e) {}
    if (!seen) notice.hidden = false;
    $("noticeOk").addEventListener("click", function () {
      notice.hidden = true; try { localStorage.setItem(KEY, "1"); } catch (e) {}
    });
  }

  // Луч налобника и горизонтали на первом экране
  var hero = $("hero");
  if (hero) {
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce) hero.addEventListener("pointermove", function (e) {
      var b = hero.getBoundingClientRect();
      hero.style.setProperty("--x", (e.clientX - b.left) + "px");
      hero.style.setProperty("--y", (e.clientY - b.top) + "px");
    });
    var cv = $("topo"), ctx = cv && cv.getContext("2d");
    var draw = function () {
      if (!ctx) return;
      var w = hero.clientWidth, h = hero.clientHeight, dpr = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h); ctx.lineWidth = 1;
      var cx = w * 0.78, cy = h * 0.42;
      for (var i = 1; i <= 26; i++) {
        var base = i * Math.max(w, h) / 34;
        ctx.beginPath();
        for (var a = 0; a <= 360; a += 3) {
          var t = a * Math.PI / 180;
          var r = base * (1 + 0.16 * Math.sin(3 * t + i * 0.35) + 0.08 * Math.cos(5 * t - i * 0.2));
          var x = cx + r * Math.cos(t) * 1.25, y = cy + r * Math.sin(t);
          if (a === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = i % 5 === 0 ? "rgba(142,161,151,.30)" : "rgba(142,161,151,.13)";
        ctx.stroke();
      }
    };
    draw(); window.addEventListener("resize", draw);
  }
})();
