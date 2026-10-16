# RLS va Ma'lumotlar Bazasi Rollarini Jonli Muhitga Chiqarish Rejasi (Rollout Plan)

Ushbu hujjat PostgreSQL darajasida Row-Level Security (RLS) va maxsus rollarni (`ecode_app`, `ai_view_owner`, `ai_readonly`) ishlab chiqarish (production) muhitiga xavfsiz tatbiq etish tartibini belgilaydi.

---

## 1. Rollar Arxitekturasi va Vazifalari

| Rol nomi | Turi | Xususiyatlari | Vazifasi va Huquqlari |
| :--- | :--- | :--- | :--- |
| **`postgres`** | Superuser | `SUPERUSER`, `BYPASSRLS` | DDL, Alembic migratsiyalari va server ma'muriyatchiligi. Jonli ilova so'rovlari bu roldan ishlamasligi kerak. |
| **`ecode_app`** | Ilova roli | `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS` | FastAPI asosiy backendining barcha operatsiyalari (savdo, kassa, tovar, ombor). RLS qoidalariga bo'ysunadi. |
| **`ai_view_owner`**| View egasi | `NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS` | Semantik ko'rinishlar (`ai_v_*`) egasi. Asosiy jadvallardan faqat SELECT huquqi bor. Yozish huquqi yo'q. |
| **`ai_readonly`** | AI agent roli| `NOLOGIN`, `read_only=on`, `timeout='10s'` | AI sessiyalari ushbu rolga o'tadi (`SET LOCAL ROLE ai_readonly`). Faqat `ai_v_*` ko'rinishlarini o'qiydi. |

---

## 2. Fail-Closed Xavfsizlik va Tranzit Siyosatlari

1. **AI yo'llari (`ai_readonly`, `ai_view_owner`):**
   * Qat'iy **Fail-Closed** rejimida ishlaydi:
     ```sql
     USING (NULLIF(current_setting('app.company_id', true), '')::integer = company_id);
     ```
   * Agar `app.company_id` o'rnatilmagan bo'lsa yoki bo'sh bo'lsa, natija `NULL` bo'ladi va **0 ta qator** qaytadi.

2. **Asosiy ilova yo'llari (`ecode_app`):**
   * Mavjud ilova kodining to'liq to'xtovsiz ishlashini ta'minlash uchun tranzit siyosati:
     ```sql
     USING (
         NULLIF(current_setting('app.company_id', true), '') IS NULL
         OR company_id = NULLIF(current_setting('app.company_id', true), '')::integer
     )
     WITH CHECK (
         NULLIF(current_setting('app.company_id', true), '') IS NULL
         OR company_id = NULLIF(current_setting('app.company_id', true), '')::integer
     );
     ```
   * Bu siyosat ilovaning mavjud ORM darajasidagi `.filter(company_id == current_user.company_id)` mantiqini buzmaydi, lekin `app.company_id` o'rnatilganda avtomatik ravishda DB darajasida ham cheklaydi.

---

## 3. Ishlab Chiqarish Muhitiga Chiqarish Bosqichlari (Rollout Steps)

### 0-qadam: Zaxira nusxa olish (Backup)
Har qanday o'zgarishdan oldin to'liq ma'lumotlar bazasi zaxira nusxasi olinadi:
```bash
pg_dump -h localhost -U postgres -d erppos -F c -b -v -f "/backup/erppos_pre_rls_$(date +%Y%m%d_%H%M%S).dump"
```

### 1-qadam: Rollar va Dastlabki Huquqlarni Yaratish
PostgreSQL superuser (`postgres`) orqali bajariladi:
```sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ecode_app') THEN
        CREATE ROLE ecode_app WITH LOGIN PASSWORD 'STRONG_PRODUCTION_PASSWORD' NOSUPERUSER NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_view_owner') THEN
        CREATE ROLE ai_view_owner WITH NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_readonly') THEN
        CREATE ROLE ai_readonly WITH NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;

ALTER ROLE ai_readonly SET default_transaction_read_only = on;
ALTER ROLE ai_readonly SET statement_timeout = '10s';

GRANT ai_readonly TO ecode_app, postgres;
GRANT ai_view_owner TO ecode_app, postgres;
```

### 2-qadam: Alembic Migratsiyasini Qo'llash
```bash
alembic upgrade head
```
Ushbu migratsiya:
* `sales`, `products`, `customers`, `purchase_orders`, `warehouses`, `suppliers`, `sale_items`, `stock_levels`, `stock_movements` jadvallarida FORCE RLS yoqadi.
* 9 ta semantik ko'rinishni yaratadi va egaligini `ai_view_owner` ga beradi.
* O'zbek tilidagi `COMMENT ON` izohlarini yozadi.

### 3-qadam: Ilovaning `.env` Konfiguratsiyasini Yangilash
Backend serverdagi `.env` faylida ulanish satri yangi `ecode_app` roliga o'tkaziladi:
```env
# Ilgari: postgres://postgres:password@localhost:5432/erppos
DATABASE_URL=postgresql://ecode_app:STRONG_PRODUCTION_PASSWORD@localhost:5432/erppos
```

### 4-qadam: Salomatlik Tekshiruvi (Smoke Testing)
Quyidagi asosiy biznes jarayonlari tekshiriladi:
1. Yangi sotuv (chek) yaratish (POS).
2. Yangi tovar va mijoz qo'shish.
3. Ombor hisoboti va qoldiqlarni ko'rish.
4. AI Copilot savoli: "Bugungi sotuvlar qancha bo'ldi?"
5. AI orqali tasdiqlash bilan tovar/sotuv yaratish (`/ai/confirm`).

---

## 4. Orqaga Qaytarish Rejasi (Rollback Plan)

Agar kutilmagan nosozlik yoki ulanish xatoligi yuz bersa, quyidagi orqaga qaytarish bosqichlari amalga oshiriladi:

### Variant A: Tezkor Favqulodda RLS ni O'chirish (Tezkor 1 daqiqalik yechim)
Barcha jadvallarda RLS zudlik bilan to'xtatiladi, ilova avvalgi holatda ishlashda davom etadi:
```sql
ALTER TABLE sales NO FORCE ROW LEVEL SECURITY;
ALTER TABLE sales DISABLE ROW LEVEL SECURITY;
ALTER TABLE products NO FORCE ROW LEVEL SECURITY;
ALTER TABLE products DISABLE ROW LEVEL SECURITY;
ALTER TABLE customers NO FORCE ROW LEVEL SECURITY;
ALTER TABLE customers DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders NO FORCE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders DISABLE ROW LEVEL SECURITY;
ALTER TABLE warehouses NO FORCE ROW LEVEL SECURITY;
ALTER TABLE warehouses DISABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers NO FORCE ROW LEVEL SECURITY;
ALTER TABLE suppliers DISABLE ROW LEVEL SECURITY;
ALTER TABLE sale_items NO FORCE ROW LEVEL SECURITY;
ALTER TABLE sale_items DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_levels NO FORCE ROW LEVEL SECURITY;
ALTER TABLE stock_levels DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_movements NO FORCE ROW LEVEL SECURITY;
ALTER TABLE stock_movements DISABLE ROW LEVEL SECURITY;
```

### Variant B: Alembic Orqali To'liq Orqaga Qaytarish (Clean Downgrade)
```bash
alembic downgrade -1
```

### Variant C: Zaxira Nusxadan Qayta Tiklash (Worst Case Scenario)
```bash
pg_restore -h localhost -U postgres -d erppos --clean --if-exists -v "/backup/erppos_pre_rls_YYYYMMDD_HHMMSS.dump"
```
