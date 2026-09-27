#!/bin/bash
# ============================================================
#  ERP-POS Deploy Script
#  Ishlatish: bash deploy.sh
#  Yoki: bash deploy.sh --no-migrate  (migratsiyasiz)
# ============================================================

set -e  # Xato bo'lsa to'xta

APP_DIR="/home/ubuntu/ERP-PosNAW"
VENV="$APP_DIR/venv/bin"
SERVICE="erp-backend"
LOG_DIR="/var/log/erp-backend"

echo ""
echo "🚀 [$SERVICE] Deploy boshlandi — $(date)"
echo "============================================================"

# Log papkasini yaratish
mkdir -p $LOG_DIR

# 1. Kodni yangilash
echo "📦 [1/6] Git pull..."
cd $APP_DIR
git pull origin main

# 2. Virtual environment va dependencies
echo "📚 [2/6] Dependencies yangilanmoqda..."
$VENV/pip install -r requirements.txt --quiet

# 3. Frontend build
echo "🏗️  [3/6] Frontend build..."
cd $APP_DIR/frontend
npm install
npm run build

# 4. Migratsiya (--no-migrate argumenti bo'lmasa)
if [[ "$1" != "--no-migrate" ]]; then
    echo "🗄️  [4/6] Alembic migratsiya..."
    cd $APP_DIR
    $VENV/alembic upgrade head
else
    echo "⏭️  [4/6] Migratsiya o'tkazib yuborildi."
fi

# 5. Nginx konfiguratsiyani tekshirish
echo "🔍 [5/6] Nginx konfiguratsiya tekshiruvi..."
nginx -t 2>&1 || echo "⚠️  Nginx config xato bor, lekin davom etamiz..."

# 6. Serviceni qayta ishlatish
echo "🔄 [6/6] Backend qayta ishlanmoqda..."
systemctl daemon-reload
systemctl restart $SERVICE
sleep 3

# Status tekshirish
if systemctl is-active --quiet $SERVICE; then
    echo ""
    echo "✅ Deploy muvaffaqiyatli! Backend ishlayapti."
    echo ""
    # Health check
    sleep 2
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/api/health || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Health check: OK (HTTP $HTTP_CODE)"
    else
        echo "⚠️  Health check: HTTP $HTTP_CODE — loglarni tekshiring"
        echo "   sudo journalctl -u $SERVICE -n 50 --no-pager"
    fi
else
    echo ""
    echo "❌ Backend ishga tushmadi! Loglar:"
    echo ""
    journalctl -u $SERVICE -n 30 --no-pager
    exit 1
fi

echo ""
echo "📋 Foydali buyruqlar:"
echo "   sudo systemctl status $SERVICE"
echo "   sudo journalctl -u $SERVICE -f"
echo "   sudo tail -f $LOG_DIR/error.log"
echo "============================================================"
