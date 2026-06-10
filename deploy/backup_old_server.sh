#!/bin/bash
# ============================================================
# ERP-PosNAW - Eski Serverdan Backup Olish Skripti
# Agar SSH/Console orqali kirishingiz bo'lsa ishlatilsin
# ============================================================

SERVER_IP="89.39.94.195"
BACKUP_DIR="D:/ERP_Backup_$(date +%Y%m%d_%H%M%S)"

echo "Backup papka: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR" 2>/dev/null || mkdir "ERP_Backup"

echo ""
echo "================================================================"
echo "  Quyidagi buyruqlarni SERVER KONSOLIDA bajaring:"
echo "================================================================"
echo ""
echo "# 1. PostgreSQL database backup"
echo "sudo -u postgres pg_dumpall > /tmp/full_db_backup.sql"
echo ""
echo "# 2. Loyiha fayllarini arxivlash"
echo "tar -czf /tmp/eldor_files.tar.gz /root/eldor/"
echo ""
echo "# 3. Nginx konfiguratsiya"
echo "cp -r /etc/nginx /tmp/nginx_backup"
echo "tar -czf /tmp/nginx_backup.tar.gz /tmp/nginx_backup"
echo ""
echo "================================================================"
echo "  Keyin LOCAL kompyuterda (PowerShell) bu buyruqlarni bajaring:"
echo "================================================================"
echo ""
echo "# Database backup yuklash:"
echo "scp root@$SERVER_IP:/tmp/full_db_backup.sql D:\ERP_Backup\"
echo ""
echo "# Fayllar yuklash:"
echo "scp root@$SERVER_IP:/tmp/eldor_files.tar.gz D:\ERP_Backup\"
echo ""
echo "# Nginx config:"
echo "scp root@$SERVER_IP:/tmp/nginx_backup.tar.gz D:\ERP_Backup\"
