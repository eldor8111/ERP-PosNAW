#!/bin/bash
# ============================================================
#  TEZKOR TUZATISh — Backend o'chib qolsa shu skriptni ishlat
#  SSH orqali serverga kiring va: bash /home/ubuntu/ERP-PosNAW/deploy/fix_now.sh
# ============================================================

APP_DIR="/home/ubuntu/ERP-PosNAW"
VENV="$APP_DIR/venv/bin"
SERVICE="erp-backend"
LOG_DIR="/var/log/erp-backend"

echo ""
echo "🔧 Tezkor tuzatish boshlandi — $(date)"
echo "============================================================"

# 1. Hozir qanday holat?
echo "📊 [1] Joriy holat:"
systemctl status $SERVICE --no-pager 2>/dev/null || echo "Service topilmadi!"
echo ""

# 2. Port 8010 da nima ishlayapti?
echo "🔍 [2] Port 8010 tekshiruvi:"
ss -tlnp | grep 8010 || echo "8010 portda hech narsa ishlamayapti!"
echo ""

# 3. So'nggi xatolar
echo "📋 [3] So'nggi xatolar (20 ta):"
journalctl -u $SERVICE -n 20 --no-pager 2>/dev/null || echo "Loglar topilmadi"
echo ""

# 4. Agar service mavjud bo'lsa — restart
if systemctl list-units --type=service | grep -q "$SERVICE"; then
    echo "🔄 [4] Service restart qilinmoqda..."
    systemctl restart $SERVICE
    sleep 4
    
    if systemctl is-active --quiet $SERVICE; then
        echo "✅ Backend ishga tushdi!"
    else
        echo "❌ Restart muvaffaqiyatsiz. Loglar:"
        journalctl -u $SERVICE -n 30 --no-pager
    fi
else
    echo "⚠️  [4] Service topilmadi! Qo'lda ishga tushirilmoqda..."
    
    # Log papkasini yaratish
    mkdir -p $LOG_DIR
    
    # Qo'lda gunicorn ishga tushirish (fon rejimida)
    cd $APP_DIR
    
    # Eski jarayonlarni o'ldirish
    pkill -f "gunicorn.*app.main" 2>/dev/null || true
    pkill -f "uvicorn.*app.main" 2>/dev/null || true
    sleep 2
    
    # Yangi jarayon ishga tushirish
    nohup $VENV/gunicorn \
        app.main:app \
        -w 4 \
        -k uvicorn.workers.UvicornWorker \
        --bind 127.0.0.1:8010 \
        --timeout 120 \
        --keepalive 5 \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --log-level warning \
        --error-logfile $LOG_DIR/error.log \
        --access-logfile $LOG_DIR/access.log \
        > $LOG_DIR/stdout.log 2>&1 &
    
    GUNICORN_PID=$!
    echo "Gunicorn PID: $GUNICORN_PID"
    sleep 5
    
    if kill -0 $GUNICORN_PID 2>/dev/null; then
        echo "✅ Gunicorn ishga tushdi (PID: $GUNICORN_PID)"
    else
        echo "❌ Gunicorn ishga tushmadi! Xatolar:"
        cat $LOG_DIR/error.log | tail -30
        cat $LOG_DIR/stdout.log | tail -30
    fi
fi

# 5. Health check
echo ""
echo "🏥 [5] Health check..."
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/api/health 2>/dev/null || echo "000")
echo "HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Backend muvaffaqiyatli ishlayapti!"
else
    echo "❌ Backend javob bermayapti!"
    echo ""
    echo "Loglarni ko'ring:"
    echo "  tail -50 $LOG_DIR/error.log"
    echo "  tail -50 $LOG_DIR/stdout.log"
fi

echo "============================================================"
