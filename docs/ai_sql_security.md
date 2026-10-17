# AI SQL Readonly Xavfsizlik Arxitekturasi (Bosqich 4)

Ushbu hujjat ERP tizimida AI Copilot v2 uchun erkin SQL so'rovlarini (`run_sql_readonly`) xavfsiz, tejamkor va tenant ma'lumotlarini 100% himoyalangan tarzda bajarish arxitekturasini tavsiflaydi.

---

## 1. Asosiy Xavf va Yechim

### Muammo:
Asosiy ilova roli (`ecode_app`) foniy jarayonlar (skeduler, botlar, login) ishlashi uchun "o'tish siyosati"ga ega:
agar `app.company_id` o'rnatilmagan bo'lsa, asosiy ilovaga barcha qatorlarni ko'rishga ruxsat beradi.
Agar AI erkin SQL so'rovlarini `ecode_app` ulanishidan `SET LOCAL ROLE` orqali bajarsa:
1. `RESET ROLE` buyrug'i sessiyani `ecode_app` egasiga qaytaradi va kontekst yo'q bo'lsa, barcha korxonalar ma'lumotlari ochilib ketishi mumkin.
2. `SELECT set_config('app.company_id', '...', false)` orqali cross-tenant hujumi amalga oshirilishi mumkin.

### Yechim:
1. **Alohida LOGIN roli `ai_sql_ro` va alohida ulanish puli (`AI_DB_URL_READONLY`)**:
   - `ai_sql_ro` mustaqil `LOGIN` roli bo'lib, `ecode_app` yoki `postgres` a'zosi emas (`NOINHERIT`).
   - `RESET ROLE` chaqirilganda sessiya `ai_sql_ro` bo'lib qoladi, boshqa rolga qayta olmaydi.
   - `SET ROLE ecode_app` yoki `SET ROLE postgres` urinishlari PostgreSQL darajasida `permission denied` bilan rad etiladi.
2. **`set_config` funksiyasiga huquqni olib tashlash**:
   - `REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;`
   - Faqat `postgres` va `ecode_app` ga ruxsat berilgan. `ai_sql_ro` bu funksiyani chaqira olmaydi.
3. **AST SQL Parser (`sqlglot`)**:
   - So'rov bazaga yetib bormasidan oldin qat'iy tekshiriladi: faqat bitta SELECT, faqat `ai_v_*` ko'rinishlari, faqat ruxsat berilgan funksiyalar (SUM, AVG, COUNT, LOWER, UPPER, DATE_TRUNC, va h.k.).
   - Tizim jadvallari (`pg_catalog`, `information_schema`), xom jadvallar (`sales`, `customers`), va tranzaksiya buyruqlari (`SET`, `RESET`, `BEGIN`, `COMMIT`, `COPY`, `DO`) rad etiladi.

---

## 2. PostgreSQL Roli Sozlamalari (`ai_sql_ro`)

```sql
CREATE ROLE ai_sql_ro WITH
    LOGIN
    PASSWORD '...'
    NOSUPERUSER
    NOBYPASSRLS
    NOINHERIT
    IN ROLE NONE;

ALTER ROLE ai_sql_ro SET default_transaction_read_only = on;
ALTER ROLE ai_sql_ro SET statement_timeout = '10s';
ALTER ROLE ai_sql_ro SET idle_in_transaction_session_timeout = '10s';

-- Faqat 9 ta semantik ko'rinishga o'qish huquqi
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ai_sql_ro;
GRANT USAGE ON SCHEMA public TO ai_sql_ro;
GRANT SELECT ON 
    ai_v_sales,
    ai_v_sale_items,
    ai_v_products,
    ai_v_customers,
    ai_v_debts,
    ai_v_stock_balance,
    ai_v_stock_movements,
    ai_v_purchases,
    ai_v_returns
TO ai_sql_ro;
```

---

## 3. AST Parser Qoidalari (`app/ai/sql_parser.py`)

1. **Faqat bitta Statement**: Bir nechta buyruqlar (`;` bilan ajratilgan) qat'iyan rad etiladi.
2. **Faqat SELECT / UNION**: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `SET`, `RESET`, `COPY`, `LOCK`, `INTO` ifodalari aniqlansa, darhol `SQLSecurityError` tashlanadi.
3. **CTE Xavfsizligi**: `WITH ... SELECT` ruxsat beriladi, lekin CTE ichida yozish amallari bo'lsa rad etiladi.
4. **Jadval Oq Ro'yxati**: Faqat `ai_v_*` semantik ko'rinishlari va joriy CTE aliaslariga murojaat qilish mumkin. Har qanday xom jadval (`sales`, `users`, `tenants`) va tizim sxemalari (`pg_catalog`, `information_schema`) rad etiladi.
5. **Funksiya Oq Ro'yxati**:
   - Agregatlar: `count`, `sum`, `avg`, `min`, `max`
   - Sanalar: `date_trunc`, `now`, `current_date`, `extract`, `age`
   - Matnlar: `lower`, `upper`, `trim`, `coalesce`, `nullif`, `concat`, `substr`, `substring`, `length`, `replace`
   - Matematik: `round`, `abs`, `ceil`, `floor`
   - Xavfli funksiyalar (`set_config`, `current_setting`, `pg_sleep`, `pg_read_file`, `dblink`, `query_to_xml`) qat'iy taqiqlangan.
6. **LIMIT Majburiyligi**: Agar so'rovda `LIMIT` bo'lmasa, avtomatik `LIMIT 200` qo'shiladi; agar ko'rsatilgan limit 200 dan oshsa, 200 ga qisqartiriladi.

---

## 4. Tenant Izolyatsiyasi va Tranzaksiya Bajarilishi (`app/ai/sql_executor.py`)

```python
with readonly_engine.connect() as conn:
    # 1. Tranzaksiya darajasida tenant kontekstini o'rnatish
    conn.execute(text(f"SET LOCAL app.company_id = '{int(company_id)}';"))
    
    # 2. Xavfsiz parserdan o'tgan SQL ni bajarish
    result = conn.execute(text(validated_sql))
```

- Agar `app.company_id` o'rnatilmasa yoki bo'sh bo'lsa, barcha `ai_v_*` ko'rinishlari `WHERE company_id = NULLIF(current_setting('app.company_id', true), '')::integer` sharti tufayli **0 ta qator** qaytaradi (Fail-Closed).
- Har qanday rad etilgan so'rov yoki xavfsizlik buzilishi darhol `AIAuditLog` jadvaliga yozib boriladi.

---

## 5. Startup Xavfsizlik Tekshiruvi (`app/main.py`)

Ilova ishga tushganda (`lifespan`), ma'lumotlar bazasi ulanish foydalanuvchisi tekshiriladi:
- Agar ulanish roli `SUPERUSER` yoki `BYPASSRLS` huquqiga ega bo'lsa:
  - `PRODUCTION` rejimida (`ENVIRONMENT=production` yoki `STRICT_RLS_CHECK=true`) ilova ishga tushmaydi (`RuntimeError`).
  - `DEVELOPMENT` rejimida xavfsizlik bo'yicha jiddiy ogohlantirish (`logger.warning`) chiqariladi.
