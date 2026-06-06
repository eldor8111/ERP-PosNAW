#!/bin/bash
# ============================================================
# ERP-PosNAW - Yangi Server O'rnatish Skripti
# Ubuntu 22.04 LTS uchun
# ============================================================

set -e  # Xato bo'lsa to'xta

echo "========================================"
echo "  ERP-PosNAW Server O'rnatish Boshlandi"
echo "========================================"

# --- 1. Tizimni yangilash ---
echo "[1/8] Tizim yangilanmoqda..."
apt update && apt upgrade -y

# --- 2. Kerakli dasturlarni o'rnatish ---
echo "[2/8] Dasturlar o'rnatilmoqda..."
apt install -y \
    python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    nginx \
    git \
    curl \
    supervisor \
    certbot python3-certbot-nginx \
    ufw

# --- 3. PostgreSQL sozlash ---
echo "[3/8] PostgreSQL sozlanmoqda..."
systemctl start postgresql
systemctl enable postgresql

# Database va user yaratish
sudo -u postgres psql <<EOF
CREATE USER erp_user WITH PASSWORD 'your_strong_password_here';
CREATE DATABASE erp_db OWNER erp_user;
GRANT ALL PRIVILEGES ON DATABASE erp_db TO erp_user;
EOF

echo "✅ PostgreSQL tayyor"

# --- 4. Loyihani yuklash ---
echo "[4/8] Loyiha yuklanmoqda..."
mkdir -p /root/eldor
cd /root/eldor

# Git orqali yuklash (GitHub/GitLab bo'lsa)
# git clone https://github.com/YOUR_USERNAME/ERP-PosNAW.git .

# YOKI: local kompyuterdan SCP bilan yuklash:
# scp -r D:\ERP-PosNAW root@NEW_SERVER_IP:/root/eldor/

echo "⚠️  Loyiha fayllarini /root/eldor/ ga ko'chiring"

# --- 5. Python virtual environment ---
echo "[5/8] Python muhiti sozlanmoqda..."
cd /root/eldor
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# --- 6. .env fayl yaratish ---
echo "[6/8] .env fayl yaratilmoqda..."
cat > /root/eldor/.env <<EOF
DATABASE_URL=postgresql://erp_user:your_strong_password_here@localhost/erp_db
SECRET_KEY=your_very_secret_key_change_this_immediately
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
EOF

echo "⚠️  .env faylini to'ldiring: /root/eldor/.env"

# --- 7. Database migratsiya ---
echo "[7/8] Database migratsiya..."
cd /root/eldor
source venv/bin/activate
# Eski DB backup restore
# psql -U erp_user -d erp_db < /tmp/backup.sql
alembic upgrade head
echo "✅ Migratsiya tugadi"

# --- 8. Supervisor (process manager) sozlash ---
echo "[8/8] Supervisor sozlanmoqda..."
cat > /etc/supervisor/conf.d/erp-posnaw.conf <<EOF
[program:erp-posnaw]
command=/root/eldor/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
directory=/root/eldor
user=root
autostart=true
autorestart=true
stderr_logfile=/var/log/erp-posnaw.err.log
stdout_logfile=/var/log/erp-posnaw.out.log
environment=PATH="/root/eldor/venv/bin"
EOF

supervisorctl reread
supervisorctl update
supervisorctl start erp-posnaw

echo "✅ Backend ishga tushdi (port 8000)"

# --- Nginx sozlash ---
echo "Nginx sozlanmoqda..."
cat > /etc/nginx/sites-available/erp-posnaw <<EOF
server {
    listen 80;
    server_name e-code.uz savdo.e-code.uz;

    # Frontend (React build)
    location / {
        root /root/eldor/frontend/dist;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/erp-posnaw /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# --- Firewall ---
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw --force enable

echo ""
echo "========================================"
echo "  ✅ O'rnatish TUGADI!"
echo "========================================"
echo ""
echo "Keyingi qadamlar:"
echo "1. DNS sozlang: e-code.uz → $(curl -s ifconfig.me)"
echo "2. SSL sertifikat: certbot --nginx -d e-code.uz -d savdo.e-code.uz"
echo "3. Frontend build: cd /root/eldor/frontend && npm install && npm run build"
echo ""
