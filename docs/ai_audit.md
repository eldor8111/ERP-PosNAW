# AI Copilot — Bosqich 0 auditi

Sana: 2026-10-16. Holat: **faqat o'qish**, kod o'zgartirilmagan.
Asos: `app/services/ai_*.py`, `app/routers/ai_*.py`, `app/models/ai_*.py`, jonli lokal baza (PostgreSQL 16.8, `erppos`).

## 1. Mavjud AI modullari

| Fayl | Vazifasi |
|---|---|
| `app/services/openrouter_copilot_service.py` | OpenRouter orqali LLM chaqiruvi, `FREE_MODELS` zanjiri, tool-calling |
| `app/services/ai_service.py` | Mahalliy tahlil (PostgreSQL'dan hisoblab o'zbekcha xulosa), kunlik hisobot |
| `app/services/ai_tools_registry.py` | `AITool`, `AIToolRegistry`, 11 ta tool, `execute_tool` (risk/audit) |
| `app/services/ai_tools_{customers,products,actions,crud,sales}.py` | Qolgan tool'lar |
| `app/services/openrouter_insights_service.py`, `ai_product_service.py` | Kunlik insight va tovar ta'rifi (OpenRouter, alohida chaqiruv) |
| `app/routers/ai_analytics.py` | `/ai/*` endpointlar (13 ta) |
| `app/routers/ai_products.py`, `ai_reports.py` | `/ai/products/generate-description`, `/ai/reports/daily-insight` |
| `app/models/ai_audit.py`, `ai_chat_history.py` | `ai_audit_logs`, `ai_chat_history` |
| `app/services/scheduler.py` | Kunlik Telegram hisobot (`build_daily_report`) |
| `frontend/src/pages/admin/AICopilot.jsx` | UI |

**Farq (topshiriqdan):** haqiqatda **22 ta** tool bor (hujjatda "~25"). `tests/` da faqat 2 ta fayl, `pytest`, `sqlglot`, `anthropic`, `openai` kutubxonalari `requirements.txt` da **yo'q**.

## 2. Tool'lar

### 2.1 Yozuvchi tool'lar (ma'lumot o'zgartiradi)

| Tool | Nima o'zgartiradi | Hozirgi xavf | Tasdiqlash oqimi | Izoh |
|---|---|---|---|---|
| `create_sale` | `sales`, `sale_items`, `stock_levels`, `stock_movements`, partiyalar, kassa/hamyon, mijoz qarzi | HIGH | bor | `create_sale()` servisini ishlatadi |
| `record_debt_payment` | `customers.debt_balance(s)`, `wallets.balance`, `transactions` | HIGH | bor | `float`, valyuta tekshirilmaydi (R8) |
| `record_new_debt` | `customers.debt_balance(s)`, `debt_edited` | HIGH | bor | hujjat yaratilmaydi, faqat UZS |
| `update_product` | `products.name/sale_price/cost_price` | HIGH | bor | |
| `create_product` | `products` | **MEDIUM** | **yo'q** (darhol `commit`) | topshiriq bo'yicha HIGH bo'lishi kerak |
| `create_customer` | `customers` | **MEDIUM** | **yo'q** | xuddi shunday |
| `update_customer` | `customers.name/phone` | **MEDIUM** | **yo'q** | xuddi shunday |

Endpoint orqali yozuvchi amallar (tool emas):

| Endpoint | Nima qiladi | Muammo |
|---|---|---|
| `POST /ai/confirm` | HIGH tool'ni bajaradi | TTL yo'q, qulf yo'q, kartochka matni umumiy (R5) |
| `POST /ai/actions/purchase-order` | PO yaratadi | argumentlar klientdan, pending yozuvsiz, idempotent emas (R6) |
| `POST /ai/actions/sms-campaign` | Eskiz orqali SMS yuboradi, `sms_logs` | qabul qiluvchilar klientdan, tekshirilmaydi (R4) |

### 2.2 O'qish tool'lari (13 ta, LOW)
`check_customer_debt`, `get_sales_summary`, `get_top_products`, `get_low_stock`, `get_debtors_list`, `get_profit_today`, `find_product_info`, `get_new_customers_stat`, `get_top_customers`, `get_inactive_customers`, `get_churn_risk_customers`, `predict_stock_depletion`, `get_product_profit`.

### 2.3 Qoralama tool'lar (bazaga yozmaydi, lekin `MEDIUM` deb belgilangan)
`draft_purchase_order`, `draft_sms_campaign`. Xavf darajasi noto'g'ri belgilangan (aslida read-only), lekin natijasi keyin klientdan keladigan yozuvchi endpointga (R4, R6) ulanadi.

## 3. Tenant filtri: hozir qanday ishlaydi

**Yaxshi:**
- `company_id` modeldan **kelmaydi**. `execute_tool` uni `user.company_id` dan oladi; hech bir tool sxemasida `company_id` parametri yo'q (tekshirildi, 22/22).
- Barcha tool so'rovlarida `Sale.company_id` / `Product.company_id` / `Customer.company_id` filtri qo'lda yozilgan.
- `/confirm` `AIAuditLog` ni `company_id` va `user_id` bo'yicha qidiradi.

**Zaif joylar:**
1. Himoya **faqat ilova kodidagi qo'lda yozilgan filtrlarga** tayanadi. Bazada **RLS yo'q** (`relrowsecurity` = 0 ta jadvalda).
2. Ilova bazaga **`postgres` superuser** (`rolsuper=t`, `rolbypassrls=t`) sifatida ulanadi: bu rol bilan RLS umuman ishlamaydi. Faqat policy yozish yetarli emas.
3. 91 ta jadvalning **40 tasida `company_id` yo'q**, shu jumladan `stock_movements`, `stock_levels`, `sale_items`, `sale_payments`, `po_items`, `stock_transfers`, `inventory_counts`. Ular tenantga faqat ota-jadval (`products`, `warehouses`, `sales`) orqali bog'langan.
4. `draft_purchase_order`: `SupplierProduct` so'rovi `company_id` bo'yicha emas, faqat `product_id` bo'yicha (ID'lar o'z kompaniyasi tovarlaridan olingan, shuning uchun bilvosita xavfsiz; to'g'ridan-to'g'ri himoya yo'q).
5. `_FORBIDDEN_WORDS` himoya emas: `"admin"`, `"unut"` kabi oddiy so'zlarni to'sib qo'yadi, aylanib o'tish oson.

## 4. Topilgan xavflar

| ID | Daraja | Xavf | Joyi |
|---|---|---|---|
| R1 | **Kritik** | Izolyatsiya faqat qo'lda filtrlarga tayanadi; DB roli superuser, RLS yo'q | `database.py`, butun baza |
| R2 | Yuqori | 40 jadvalda `company_id` yo'q, RLS/view uchun ota-jadval orqali bog'lash kerak | baza sxemasi |
| R3 | Yuqori | `create_product`, `create_customer`, `update_customer` tasdiqlashsiz yoziladi | `ai_tools_crud.py`, `execute_tool` |
| R4 | Yuqori | `/actions/sms-campaign` ixtiyoriy telefon va matnni qabul qiladi; kompaniya Eskiz hisobidan spam yuborish mumkin; chastota limiti yo'q | `ai_analytics.py:584` |
| R5 | Yuqori | `/confirm`: qulf va TTL yo'q (parallel ikki so'rov qarzni ikki marta yozishi mumkin); foydalanuvchi aniq nimani tasdiqlayotganini ko'rmaydi (kartochka matni umumiy) | `ai_analytics.py:443` |
| R6 | Yuqori | `/actions/purchase-order` miqdor/narxni klientdan oladi, pending yozuvi va idempotentlik yo'q (egalik servis ichida tekshiriladi: `_company_supplier`, `_company_warehouse`) | `ai_analytics.py:516` |
| R7 | O'rta | `required_permission` hech qayerda tekshirilmaydi; faqat `risk_level` bo'yicha rol ro'yxati. Maxsus rollar/`users.permissions` e'tiborga olinmaydi | `execute_tool` |
| R8 | O'rta | Pul `float` bilan (`_sf`); `record_debt_payment` valyutadan qat'i nazar UZS qarzdan ayiradi va **birinchi ochiq hamyonga** (valyutasi tekshirilmay) qo'shadi; `get_debtors_list` valyutalarni aralashtirib solishtiradi | `ai_tools_registry.py` |
| R9 | O'rta | Ichki xato matni foydalanuvchiga chiqadi: `execute_tool` (`str(e)`), `/voice` (`detail=str(e)`, shuningdek 400 ni 500 ga aylantiradi) | `ai_tools_registry.py:131`, `ai_analytics.py:438` |
| R10 | O'rta | Xato: barcha modellar 402/403 qaytarsa `last_error` aniqlanmagan, `NameError` 500; faqat birinchi `tool_calls[0]` ishlatiladi | `openrouter_copilot_service.py` |
| R11 | O'rta | Mijoz ismi/qarzi tashqi **bepul** modellarga yuboriladi (`summarize_tool_result_with_llm`, kunlik kontekst). Bepul modellar loglashi/o'qitishi mumkin | `openrouter_copilot_service.py` |
| R12 | O'rta | `/ai/voice` kassirga ruxsat beradi: kassir chat'da yopiq `get_profit_today`, `get_debtors_list` kabi LOW tool'larni ovoz orqali ko'ra oladi (chat va voice rol ro'yxati mos emas) | `ai_analytics.py:367` |
| R13 | O'rta | `config.py` da Eskiz login/paroli **git'da kuzatiladigan kodda** (`ESKIZ_EMAIL`, `ESKIZ_PASSWORD` default). Qoida 5 buzilgan | `app/config.py:30-31` |
| R14 | Past | `GET /ai/status` autentifikatsiyasiz | `ai_analytics.py:27` |
| R15 | Past | `FREE_MODELS` eskirgan; `OPENROUTER_MODEL` `.env` da yo'q, shuning uchun `FREE_MODELS[0]` (qwen) ishlatiladi va `404` beradi. Ishlaydigan model (`cohere/north-mini-code:free`) faqat `config.py` defaultida, uni `os.getenv` o'qimaydi | `openrouter_copilot_service.py:29` |
| R16 | Past | `get_low_stock`, `find_product_info` o'chirilgan (`is_deleted`) tovarlarni ham ko'rsatadi; `get_top_customers.limit`/`days` yuqori chegarasiz | tool'lar |
| R17 | Past | `ai_chat_history` saqlash muddati yo'q; `*.bak.*` zaxira fayllar `app/` ichida | |

## 5. Dizayn uchun muhim aniqlashlar

### 5.1 PostgreSQL versiyasi va view qarori
Lokal baza **PG 16.8**, ya'ni `security_invoker` mavjud. Lekin topshiriqdagi ikki talab bir-biriga zid:

- `security_invoker=true` bo'lsa view bazaviy jadvallarni **chaqiruvchi (`ai_readonly`)** huquqi bilan o'qiydi, demak `ai_readonly` ga xom jadvallarga `SELECT` berish shart bo'ladi.
- Talab esa: `ai_readonly` xom jadvallarga **umuman** kira olmasin.

**Taklif etilgan qaror (tasdiqlash kerak):** view'lar `security_invoker=off`, egasi alohida `ai_view_owner` roli (`NOLOGIN`, `BYPASSRLS` yo'q, jadval egasi emas). Bazaviy jadvallarga RLS policy `TO ai_view_owner` bilan, `company_id = current_setting('app.company_id', true)::int` ga tayanadi. `ai_readonly` faqat `ai_v_*` ga `SELECT` oladi. `app.company_id` o'rnatilmasa `NULL` qaytadi va **hech qanday qator ko'rinmaydi** (fail-closed). Bu PG versiyasidan mustaqil.
`company_id` yo'q jadvallar (`stock_movements` va h.k.) view ichida `products`/`warehouses` ga JOIN qilinadi, ota-jadval RLS bilan filtrlangani uchun bola qatorlar ham filtrlanadi.

### 5.2 `SET LOCAL` va `commit()`
Tool'lar (`create_product`, `create_sale` va boshqalar) so'rov ichida `db.commit()` chaqiradi. `SET LOCAL app.company_id` tranzaksiya tugashi bilan yo'qoladi. Yechim: SQLAlchemy `after_begin` hodisasida har yangi tranzaksiya boshida qiymatni qayta o'rnatish.

### 5.3 RLS asosiy ilova ulanishiga qo'yilsa nima bo'ladi
Skeduler, Telegram botlar, ochiq do'kon (`shop`), login va super-admin ham xuddi shu `engine` dan foydalanadi va `company_id` kontekstiga ega emas. Asosiy ilova rolini RLS ostiga o'tkazish ularni sindiradi ("mavjud endpointlarni buzmang" qoidasiga zid). Shuning uchun RLS policy'larini **faqat AI rollariga** (`ai_view_owner`, kerak bo'lsa `ai_writer`) qo'llash taklif etiladi; asosiy ilova roli o'zgarmaydi.

### 5.4 Test bazasi
Izolyatsiya va RLS testlari rol/policy yaratishni talab qiladi. Ishlab chiqish bazasiga tegmaslik uchun alohida `erppos_test` bazasi kerak. Dev bazada hozir 2 kompaniya, 11 sotuv, 3 mijoz, 12 tovar, 25 tovar harakati bor (seed uchun asos).

### 5.5 Valyuta/pul
Modelda `numeric` ishlatilgan (DB to'g'ri), lekin AI kodi `float` ga o'tkazadi. Bosqich 4 va 6 da `Decimal` va valyuta bo'yicha ajratish talab qilinadi.

## 6. Keyingi bosqich uchun xavflar
- Bosqich 2 asosiy ilova rolini o'zgartirmasa ham, `ai_view_owner` va policy migratsiyasi superuser huquqini talab qiladi (ishlab chiqarish DB'sida shunday huquq borligi noma'lum).
- Bosqich 3 dagi `running_balance` mavjud ombor hisobotlari bilan mos kelishi kerak; `stock_movements` da `qty_before/qty_after` bor, lekin tarixiy yozuvlarda nomuvofiqlik bo'lishi mumkin (tekshiruv testi shart).
- Alembic tarixida ko'p `merge_heads` bor; yangi migratsiyalar yagona `head` dan davom etishi kerak (hozirgi head: `b18a5d60c340`).
