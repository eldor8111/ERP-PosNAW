# ERP/POS Tizimi — Backend

## Ishga tushirish

### 1. Virtual muhit yaratish
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# yoki
source venv/bin/activate     # Linux/Mac
```

### 2. Paketlarni o'rnatish
```bash
pip install -r requirements.txt
```

### 3. .env faylini sozlash
```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/erppos
SECRET_KEY=your-secret-key-min-32-characters-long
```

### 4. PostgreSQL da database yaratish
```sql
CREATE DATABASE erppos;
```

### 5. Migratsiyani ishlatish
```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 6. Seed ma'lumotlarni yuklash
```bash
python seed.py
```

### 7. Serverni ishga tushirish
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Dokumentatsiya

- Swagger UI: http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc

## Test Login

| Rol        | Telefon        | Parol        |
|------------|----------------|--------------|
| Admin      | 998901234567   | admin123     |
| Direktor   | 998901234568   | director123  |
| Kassir     | 998901234569   | cashier123   |
| Omborchi   | 998901234570   | warehouse123 |
| Buxgalter  | 998901234571   | accountant123|
| Menejer    | 998901234572   | manager123   |

## API Endpointlar

| Modul      | Prefix              |
|------------|---------------------|
| Auth       | /api/auth           |
| Users      | /api/users          |
| Categories | /api/categories     |
| Products   | /api/products       |
| Inventory  | /api/inventory      |
| Sales      | /api/sales          |
| Reports    | /api/reports        |
