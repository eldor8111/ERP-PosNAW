#!/usr/bin/env bash
# ============================================================
#  Fon vazifalari ishchisini (scheduler + admin bot) alohida systemd xizmati sifatida o'rnatadi.
#  Loyiha papkasida:  sudo bash deploy/install_worker.sh [asosiy_xizmat=erppos]
#
#  - erppos-worker xizmatini yaratib yoqadi (sozlamalar asosiy xizmatdan olinadi)
#  - ishchi ishga tushgach, asosiy xizmatga RUN_BACKGROUND_JOBS=0 qo'yadi (drop-in) —
#    shundan so'ng scheduler/bot faqat ishchi jarayonida ishlaydi
#  Qayta ishga tushirish xavfsiz. Keyingi deploylarda deploy_erppos.sh ishchini o'zi qayta ishga tushiradi.
# ============================================================
set -euo pipefail

MAIN_UNIT="${1:-erppos}"
WORKER_UNIT="erppos-worker"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ root huquqi kerak: sudo bash deploy/install_worker.sh"
  exit 1
fi
if ! systemctl cat "$MAIN_UNIT" >/dev/null 2>&1; then
  echo "❌ '$MAIN_UNIT' xizmati topilmadi. Nomini bering: sudo bash deploy/install_worker.sh <xizmat>"
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

echo "📋 Sozlamalar:"
echo "   loyiha:   $REPO"
echo "   user:     $RUN_USER"
echo "   python:   $PY"
echo "   env:      ${ENV_FILE:-—}"
echo ""

# ── 1. Ishchi xizmati ─────────────────────────────────────
echo "⚙️  [1/3] $WORKER_UNIT xizmati yaratilmoqda..."
sed -e "s|@MAIN_UNIT@|$MAIN_UNIT|g" \
    -e "s|@USER@|$RUN_USER|g" \
    -e "s|@WORKDIR@|$REPO|g" \
    -e "s|@PYTHON@|$PY|g" \
    -e "s|@ENV_FILE_LINE@|$ENV_FILE_LINE|g" \
    "$REPO/deploy/erppos-worker.service" > "/etc/systemd/system/$WORKER_UNIT.service"
systemctl daemon-reload
systemctl enable "$WORKER_UNIT" >/dev/null 2>&1
systemctl restart "$WORKER_UNIT"
sleep 3
if systemctl is-active --quiet "$WORKER_UNIT"; then
  echo "✅ $WORKER_UNIT ishlayapti"
else
  echo "❌ $WORKER_UNIT ishga tushmadi (web xizmatiga tegilmadi):"
  journalctl -u "$WORKER_UNIT" -n 30 --no-pager
  exit 1
fi

# ── 2. Web xizmatida fon vazifalarini o'chirish ───────────
echo "🔧 [2/3] $MAIN_UNIT: RUN_BACKGROUND_JOBS=0 qo'yilmoqda..."
DROPIN_DIR="/etc/systemd/system/$MAIN_UNIT.service.d"
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN_DIR/background-jobs.conf" <<CONF
[Service]
Environment=RUN_BACKGROUND_JOBS=0
CONF
systemctl daemon-reload
systemctl restart "$MAIN_UNIT"

# ── 3. Natija ─────────────────────────────────────────────
echo "🔍 [3/3] Tekshiruv..."
sleep 5
if systemctl is-active --quiet "$MAIN_UNIT" && systemctl is-active --quiet "$WORKER_UNIT"; then
  echo "✅ $MAIN_UNIT va $WORKER_UNIT ishlayapti"
else
  echo "❌ Xizmatlardan biri ishlamayapti:"
  systemctl --no-pager status "$MAIN_UNIT" "$WORKER_UNIT" | head -30
  exit 1
fi
cat <<EOF

Loglar:  journalctl -u $WORKER_UNIT -f
Qaytarish (fon vazifalarini yana web ichida ishlatish):
    sudo rm $DROPIN_DIR/background-jobs.conf && sudo systemctl daemon-reload && sudo systemctl disable --now $WORKER_UNIT && sudo systemctl restart $MAIN_UNIT
EOF
