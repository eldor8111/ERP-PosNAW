#!/usr/bin/env bash
# E-code ERP — serverda to'xtovsiz yangilash.
#
#   cd ~/eldor/erppos && bash deploy/deploy.sh
#
# Nima qiladi:
#  1. git pull
#  2. pip install (faqat requirements.txt o'zgargan bo'lsa)
#  3. alembic upgrade head — backend qayta yuklanishidan OLDIN (yangi kod
#     bazada yo'q ustunlarni kutib 500 bermasligi uchun)
#  4. frontend'ni dist_new/ ga yig'adi va bir zumda almashtiradi; eski
#     /assets fayllari saqlanadi — ochiq tablar eski JS bo'laklarini so'rasa
#     ham 404 olmaydi
#  5. gunicorn'ga HUP: yangi worker tayyor bo'lgach eskisi yopiladi (restart
#     kabi 8 soniyalik to'xtash yo'q)
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="${SERVICE:-erppos}"
cd "$APP_DIR"

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }

step "1/5 git pull"
OLD_HEAD=$(git rev-parse HEAD)
git pull --ff-only origin main
NEW_HEAD=$(git rev-parse HEAD)
if [ "$OLD_HEAD" = "$NEW_HEAD" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "Yangi o'zgarish yo'q (majburan: FORCE=1 bash deploy/deploy.sh)"
  exit 0
fi
changed() { git diff --name-only "$OLD_HEAD" "$NEW_HEAD" | grep -qE "$1"; }

# shellcheck disable=SC1091
source venv/bin/activate

step "2/5 Python kutubxonalari"
if changed '^requirements\.txt$' || [ "${FORCE:-0}" = "1" ]; then
  pip install -q -r requirements.txt
else
  echo "requirements.txt o'zgarmagan — o'tkazildi"
fi

step "3/5 Migratsiyalar"
alembic upgrade head
alembic current | tail -1

step "4/5 Frontend"
if changed '^frontend/' || [ "${FORCE:-0}" = "1" ]; then
  cd frontend
  if changed '^frontend/package(-lock)?\.json$' || [ ! -d node_modules ]; then
    npm install --no-audit --no-fund
  fi
  rm -rf dist_new
  npx vite build --outDir dist_new --emptyOutDir --logLevel warn
  # Eski bo'laklarni saqlaymiz (hash'li nomlar to'qnashmaydi)
  if [ -d dist/assets ]; then
    cp -n dist/assets/* dist_new/assets/ 2>/dev/null || true
    # 14 kundan eski bo'laklarni tozalash
    find dist_new/assets -type f -mtime +14 -delete 2>/dev/null || true
  fi
  rm -rf dist_old
  [ -d dist ] && mv dist dist_old
  mv dist_new dist
  rm -rf dist_old
  cd "$APP_DIR"
else
  echo "frontend o'zgarmagan — o'tkazildi"
fi

step "5/5 Backend (to'xtovsiz qayta yuklash)"
MAIN_PID=$(systemctl show -p MainPID --value "$SERVICE")
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
  kill -HUP "$MAIN_PID"
  echo "HUP yuborildi (gunicorn PID $MAIN_PID) — yangi worker ishga tushmoqda"
else
  systemctl restart "$SERVICE"
  echo "Servis ishlamayotgan edi — restart qilindi"
fi

sleep 12
if journalctl -u "$SERVICE" --since '30 sec ago' --no-pager | grep -q "Application startup complete"; then
  echo "✅ Backend yangi kod bilan ishlayapti"
else
  echo "⚠️  'startup complete' ko'rinmadi — tekshiring: journalctl -u $SERVICE -n 50 --no-pager"
fi
curl -s -o /dev/null -w "API: %{http_code} %{time_total}s\n" http://127.0.0.1:8015/api/mobile/version || true
echo "Tayyor: $(git log --oneline -1)"
