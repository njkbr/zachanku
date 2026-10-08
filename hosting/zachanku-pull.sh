#!/bin/bash
# Забирает свежую сборку сайта zachanku.ru с GitHub и раскладывает её в папку сайта.
#
# Зачем: с 06.10.2026 REG.RU закрыл FTP/SFTP для зарубежных адресов, и GitHub не может
# выложить сайт сам. Поэтому GitHub складывает готовый сайт в ветку «site» репозитория,
# а хостинг раз в 5 минут запускает этот скрипт из Планировщика CRON и забирает обновление.
#
# Лежит на хостинге в корне: /zachanku-pull.sh
# Задание CRON (каждые 5 минут):
#   bash $HOME/zachanku-pull.sh
# Журнал скрипт пишет сам в $HOME/zachanku-pull.log: строка появляется только при обновлении сайта
# или при ошибке. (ISPmanager с галочкой «Не отправлять отчет по e-mail» отправляет вывод команды
# в /dev/null, поэтому перенаправление в самой команде CRON не работает.)
#
# Раз в 15 минут скрипт сам запускает сборку на GitHub (токен в $HOME/.zachanku-dispatch-token).
# Если репозиторий приватный, положите токен GitHub (только чтение) в файл $HOME/.zachanku-github-token.

set -eu
export LC_ALL=C
exec >>"$HOME/zachanku-pull.log" 2>&1

REPO="njkbr/zachanku"
BRANCH="site"
SITE="$HOME/www/zachanku.ru"
WORK="$HOME/.zachanku-pull"
TOKEN_FILE="$HOME/.zachanku-github-token"

mkdir -p "$WORK"
cd "$WORK"

# Не запускаемся дважды одновременно
exec 9>"$WORK/lock"
flock -n 9 || exit 0

if [ -s "$TOKEN_FILE" ]; then
    # Приватный репозиторий: через API с токеном
    AUTH="Authorization: Bearer $(tr -d ' \r\n' < "$TOKEN_FILE")"
    HASH_URL="https://api.github.com/repos/$REPO/contents/build-hash.txt?ref=$BRANCH"
    ARCHIVE_URL="https://api.github.com/repos/$REPO/tarball/$BRANCH"
    ACCEPT="Accept: application/vnd.github.raw"
else
    # Публичный репозиторий: без токена
    AUTH="X-No-Auth: 1"
    HASH_URL="${HASH_URL:-https://raw.githubusercontent.com/$REPO/$BRANCH/build-hash.txt}"
    ARCHIVE_URL="${ARCHIVE_URL:-https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH}"
    ACCEPT="Accept: */*"
fi

# 0. Раз в 15 минут просим GitHub пересобрать сайт (подхватить анонс из канала и свежую погоду).
#    Запуски GitHub «по расписанию» часто опаздывают на часы, а запуск по запросу идёт сразу.
#    Нужен токен GitHub с правом Actions: Read and write в файле $HOME/.zachanku-dispatch-token.
DISPATCH_TOKEN_FILE="$HOME/.zachanku-dispatch-token"
DISPATCH_STAMP="$WORK/last-dispatch"
DISPATCH_EVERY=900   # секунд
if [ -s "$DISPATCH_TOKEN_FILE" ]; then
    LAST=$(cat "$DISPATCH_STAMP" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [ $((NOW - LAST)) -ge $DISPATCH_EVERY ]; then
        echo "$NOW" > "$DISPATCH_STAMP"
        CODE=$(curl -sS -o "$WORK/dispatch.out" -w '%{http_code}' --max-time 30 -X POST \
            -H "Authorization: Bearer $(tr -d ' \r\n' < "$DISPATCH_TOKEN_FILE")" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/$REPO/actions/workflows/site.yml/dispatches" \
            -d '{"ref":"main"}' 2>"$WORK/dispatch.err" || true)
        if [ "$CODE" != "204" ]; then
            echo "$(date '+%F %T') не удалось запустить сборку на GitHub (код $CODE): $(tr '\n' ' ' < "$WORK/dispatch.out" 2>/dev/null | cut -c1-200) $(tr '\n' ' ' < "$WORK/dispatch.err" 2>/dev/null)"
        fi
    fi
fi

# 1. Есть ли новая сборка? Сравниваем отпечаток на GitHub и на сайте.
if ! REMOTE=$(curl -fsSL --max-time 30 -H "$AUTH" -H "$ACCEPT" "$HASH_URL" 2>"$WORK/curl.err"); then
    echo "$(date '+%F %T') не удалось получить отпечаток с GitHub: $(tr '\n' ' ' < "$WORK/curl.err")"
    exit 0
fi
REMOTE=$(printf '%s' "$REMOTE" | tr -d ' \r\n')
LOCAL=$( { tr -d ' \r\n' < "$SITE/build-hash.txt"; } 2>/dev/null || true)
[ -n "$REMOTE" ] || exit 0
[ "$REMOTE" = "$LOCAL" ] && exit 0

# 2. Скачиваем и распаковываем во временную папку
rm -rf new site.tar.gz
mkdir new
curl -fsSL --max-time 120 -H "$AUTH" -o site.tar.gz "$ARCHIVE_URL"
tar -xzf site.tar.gz -C new --strip-components=1
if [ ! -f new/index.html ]; then
    echo "$(date '+%F %T') в архиве нет index.html, пропускаю"
    exit 1
fi

# 3. Копируем в папку сайта (build-hash.txt последним — он отмечает, что выкладка завершена)
mkdir -p "$SITE"
(cd new && find . -type f ! -name build-hash.txt | sort) > manifest.new
(cd new && tar -cf - --exclude=./build-hash.txt .) | (cd "$SITE" && tar -xf -)

# 4. Удаляем файлы, которые были в прошлой сборке, а в этой исчезли
if [ -f manifest ]; then
    comm -23 manifest manifest.new | while IFS= read -r f; do
        case "$f" in
            ./*) rm -f -- "$SITE/${f#./}" ;;
        esac
    done
fi
mv manifest.new manifest
cp new/build-hash.txt "$SITE/build-hash.txt"

rm -rf new site.tar.gz
echo "$(date '+%F %T') сайт обновлён: $LOCAL -> $REMOTE"
