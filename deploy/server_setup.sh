#!/bin/bash
# ============================================================
#  BIRINCHI MARTA SETUP — Serverga yangi o'rnatish
#  Faqat bir marta ishlatiladi!
#  bash /home/ubuntu/ERP-PosNAW/deploy/server_setup.sh
# ============================================================

set -e

APP_DIR="/home/ubuntu/ERP-PosNAW"
SERVICE="erp-backend"
LOG_DIR="/var/log/erp-backend"

echo ""
echo "⚙️  Server birinchi marta sozlanmoqda — $(date)"
echo "============================================================"

# 1. Log papkasini yaratish
echo "📁 [1] Log papkasi yaratilmoqda..."
mkdir -p $LOG_DIR
chown ubuntu:ubuntu $LOG_DIR

# 2. Systemd service o'rnatish
echo "🔧 [2] Systemd service o'rnatilmoqda..."
cp $APP_DIR/deploy/erp-backend.service /etc/systemd/system/$SERVICE.service

# Server user nomini avtomatik topish
CURRENT_USER=$(stat -c '%U' $APP_DIR)
echo "   Server user: $CURRENT_USER"
sed -i "s/User=ubuntu/User=$CURRENT_USER/g" /etc/systemd/system/$SERVICE.service
sed -i "s/Group=ubuntu/Group=$CURRENT_USER/g" /etc/systemd/system/$SERVICE.service
sed -i "s|/home/ubuntu|$(dirname $APP_DIR)|g" /etc/systemd/system/$SERVICE.service

echo "   Service fayli: /etc/systemd/system/$SERVICE.service"

# 3. Service yoqish
echo "🚀 [3] Service enable qilinmoqda (server restart bo'lsa ham ishlaydi)..."
systemctl daemon-reload
systemctl enable $SERVICE
systemctl start $SERVICE

sleep 4

# 4. Status tekshirish
echo ""
if systemctl is-active --quiet $SERVICE; then
    echo "✅ Service muvaffaqiyatli ishga tushdi!"
    echo ""
    systemctl status $SERVICE --no-pager
else
    echo "❌ Service ishga tushmadi!"
    journalctl -u $SERVICE -n 50 --no-pager
fi

echo ""
echo "📋 Keyinchalik foydali buyruqlar:"
echo "   sudo systemctl status $SERVICE        # holat"
echo "   sudo systemctl restart $SERVICE       # restart"
echo "   sudo journalctl -u $SERVICE -f        # live loglar"
echo "   sudo tail -f $LOG_DIR/error.log       # xatolar"
echo "   bash $APP_DIR/deploy/deploy.sh        # yangi versiyani deploy"
echo "============================================================"
