#!/usr/bin/env bash
# ============================================================
#  Mahsulot rasmlari fonini olib tashlash ishchisini o'rnatadi (bir marta).
#  Loyiha papkasida:  sudo bash deploy/install_bgworker.sh [asosiy_xizmat=erppos]
#
#  - rembg (CPU) kutubxonasini o'rnatadi va modelni (~170 MB) yuklab oladi
#  - erppos-bgworker systemd xizmatini yaratib yoqadi (sozlamalar asosiy xizmatdan olinadi)
#  Qayta ishga tushirish xavfsiz. Keyingi deploylarda hech narsa qilish shart emas:
#  systemctl restart erppos ishchini ham qayta ishga tushiradi.
# ============================================================
set -euo pipefail

MAIN_UNIT="${1:-erppos}"
BG_UNIT="erppos-bgworker"
STATE_DIR="/var/lib/erppos-bg"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ root huquqi kerak: sudo bash deploy/install_bgworker.sh"
  exit 1
fi
if ! systemctl cat "$MAIN_UNIT" >/dev/null 2>&1; then
  echo "❌ '$MAIN_UNIT' xizmati topilmadi. Nomini bering: sudo bash deploy/install_bgworker.sh <xizmat>"
  exit 1
fi

# ── Asosiy xizmat sozlamalari ─────────────────────────────
RUN_USER="$(systemctl show -p User --value "$MAIN_UNIT")"
RUN_USER="${RUN_USER:-root}"
MAIN_WORKDIR="$(systemctl show -p WorkingDirectory --value "$MAIN_UNIT")"
if [ -n "$MAIN_WORKDIR" ] && [ "$(realpath "$MAIN_WORKDIR")" != "$REPO" ]; then
  echo "⚠️  $MAIN_UNIT papkasi ($MAIN_WORKDIR) bu loyihadan ($REPO) farq qiladi — skriptni o'sha papkadan ishga tushiring"
  exit 1
fi

EXEC_PATH="$(systemctl show -p ExecStart --value "$MAIN_UNIT" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
PY=""
for cand in "$(dirname "${EXEC_PATH:-/nonexistent/x}")/python" "$REPO/venv/bin/python" "$REPO/.venv/bin/python"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "❌ Loyiha virtual muhitidagi python topilmadi (venv/bin/python)"
  exit 1
fi

ENV_FILE="$(systemctl show -p EnvironmentFiles --value "$MAIN_UNIT" | awk '{print $1}' | head -1)"
if [ -n "$ENV_FILE" ]; then
  ENV_FILE_LINE="EnvironmentFile=-$ENV_FILE"
else
  ENV_FILE_LINE="# EnvironmentFile yo'q — sozlamalar $REPO/.env dan o'qiladi"
fi

SYSTEMD_VER="$(systemctl --version | awk 'NR==1{print $2}')"
if [ "${SYSTEMD_VER:-0}" -ge 252 ] 2>/dev/null; then CPU_WEIGHT="idle"; else CPU_WEIGHT="1"; fi
CORES="$(nproc)"
if [ "$CORES" -le 1 ]; then CPU_QUOTA="50%"; else CPU_QUOTA="$(( (CORES - 1) * 100 ))%"; fi

echo "📋 Sozlamalar:"
echo "   loyiha:   $REPO"
echo "   user:     $RUN_USER"
echo "   python:   $PY"
echo "   env:      ${ENV_FILE:-—}"
echo "   CPU:      $CORES yadro, ishchiga ko'pi bilan $CPU_QUOTA, ustuvorlik: $CPU_WEIGHT"
echo ""

run_as() {
  if [ "$RUN_USER" = "root" ]; then "$@"; else runuser -u "$RUN_USER" -- "$@"; fi
}

# ── 1. Kutubxona ──────────────────────────────────────────
echo "📦 [1/4] rembg o'rnatilmoqda (bir necha daqiqa)..."
run_as "$PY" -m pip install --quiet "rembg[cpu]==2.0.85"

# ── 2. Model ──────────────────────────────────────────────
echo "🧠 [2/4] Model yuklab olinmoqda va tekshirilmoqda..."
mkdir -p "$STATE_DIR/numba"
chown -R "$RUN_USER" "$STATE_DIR"
( cd "$REPO" && run_as env REMBG_HOME="$STATE_DIR" NUMBA_CACHE_DIR="$STATE_DIR/numba" \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    "$PY" "$REPO/app/services/bg_removal_worker.py" --warmup )

# ── 3. Xizmat ─────────────────────────────────────────────
echo "⚙️  [3/4] $BG_UNIT xizmati yaratilmoqda..."
sed -e "s|@MAIN_UNIT@|$MAIN_UNIT|g" \
    -e "s|@USER@|$RUN_USER|g" \
    -e "s|@WORKDIR@|$REPO|g" \
    -e "s|@PYTHON@|$PY|g" \
    -e "s|@ENV_FILE_LINE@|$ENV_FILE_LINE|g" \
    -e "s|@CPU_WEIGHT@|$CPU_WEIGHT|g" \
    -e "s|@CPU_QUOTA@|$CPU_QUOTA|g" \
    "$REPO/deploy/erppos-bgworker.service" > "/etc/systemd/system/$BG_UNIT.service"
systemctl daemon-reload
systemctl enable "$BG_UNIT" >/dev/null 2>&1
systemctl restart "$BG_UNIT"
sleep 3
if systemctl is-active --quiet "$BG_UNIT"; then
  echo "✅ $BG_UNIT ishlayapti"
else
  echo "❌ $BG_UNIT ishga tushmadi:"
  journalctl -u "$BG_UNIT" -n 30 --no-pager
  exit 1
fi

# ── 4. Server holati ──────────────────────────────────────
echo ""
echo "🖥  [4/4] Server holati:"
echo "   yadrolar: $CORES"
free -h | sed 's/^/   /'
df -h "$REPO" | sed 's/^/   /'
echo ""
echo "🌐 nginx: /static va yuklash hajmi sozlamalari"
NGINX_HITS="$(grep -rnE "location[[:space:]]+/static|client_max_body_size" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ /etc/nginx/nginx.conf 2>/dev/null || true)"
if [ -n "$NGINX_HITS" ]; then echo "$NGINX_HITS" | sed 's/^/   /'; else echo "   (topilmadi)"; fi
cat <<EOF

💡 Tavsiya: rasmlarni Python emas, nginx bersin (server bloki ichiga qo'shing, keyin: nginx -t && systemctl reload nginx):

    client_max_body_size 6m;
    location /static/uploads/ {
        alias $REPO/static/uploads/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

Loglar:  journalctl -u $BG_UNIT -f
EOF
