#!/usr/bin/env bash
# E-code: nginx'da JS/CSS/JSON/SVG siqish (gzip) va oldindan siqilgan .gz fayllarni berish (gzip_static).
#
#   sudo bash deploy/nginx_speed.sh
#
# Muammo (2026-11-27 o'lchov): /assets/*.js va *.css siqilmasdan berilardi (Content-Encoding yo'q):
# birinchi ochilishda ~1.6 MB. Ubuntu nginx.conf da `gzip on;` bor, lekin `gzip_types` izohda —
# shuning uchun faqat text/html siqilardi.
#
# Xavfsiz: sozlama alohida faylga yoziladi, `nginx -t` o'tmasa fayl o'chiriladi va nginx tegilmaydi.
# Takroriy ishga tushirish xavfsiz (fayl o'zgarmagan bo'lsa reload ham qilinmaydi).
set -uo pipefail

CONF="/etc/nginx/conf.d/e-code-speed.conf"

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx topilmadi — o'tkazildi"
  exit 0
fi
if [ ! -d /etc/nginx/conf.d ]; then
  echo "/etc/nginx/conf.d yo'q — o'tkazildi"
  exit 0
fi
if ! grep -rqs "include[[:space:]]\+/etc/nginx/conf.d/\*\.conf" /etc/nginx/nginx.conf; then
  echo "nginx.conf conf.d ni ulamaydi — o'tkazildi"
  exit 0
fi

read -r -d '' WANT <<'EOF'
# E-code: deploy/nginx_speed.sh yaratgan. Statik JS/CSS va API javoblarini siqish.
# `gzip on;` asosiy nginx.conf da (Ubuntu sukuti) — bu yerda takrorlanmaydi.
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_min_length 1024;
gzip_types text/plain text/css text/xml text/javascript application/javascript application/x-javascript
           application/json application/xml application/rss+xml image/svg+xml font/ttf font/otf
           application/vnd.ms-fontobject;
# deploy_erppos.sh assets/*.js|css uchun .gz nusxalarini oldindan tayyorlaydi — CPU sarflanmaydi
gzip_static on;
EOF

if [ -f "$CONF" ] && [ "$(cat "$CONF")" = "$WANT" ]; then
  echo "nginx siqish sozlamasi allaqachon o'rnatilgan"
  exit 0
fi

BACKUP=""
if [ -f "$CONF" ]; then
  BACKUP="$(mktemp)"
  cp "$CONF" "$BACKUP"
fi
if ! printf '%s\n' "$WANT" > "$CONF" 2>/dev/null; then
  echo "$CONF ga yozib bo'lmadi (root huquqi kerak: sudo bash deploy/nginx_speed.sh) — o'tkazildi"
  [ -n "$BACKUP" ] && rm -f "$BACKUP"
  exit 0
fi

if nginx -t >/dev/null 2>&1; then
  if systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null; then
    echo "OK: nginx siqish yoqildi ($CONF)"
  else
    echo "Diqqat: sozlama yozildi, lekin nginx reload bo'lmadi — qo'lda: systemctl reload nginx"
  fi
  [ -n "$BACKUP" ] && rm -f "$BACKUP"
  exit 0
fi

# Tekshiruv o'tmadi (masalan, gzip_types nginx.conf da allaqachon yoqilgan — takroriy direktiva).
echo "nginx -t xato berdi — sozlama qaytarildi, nginx o'zgarmadi:"
nginx -t 2>&1 | tail -3
if [ -n "$BACKUP" ]; then
  mv "$BACKUP" "$CONF"
else
  rm -f "$CONF"
fi
exit 0
