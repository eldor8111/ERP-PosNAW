"""
Bosqich 4: Umumiy AI Semantik Vositalari (ai_v_* ko'rinishlari ustida).
Har bir vosita aniq o'zbekcha tavsif, Pydantic argument tekshiruvi,
qator limiti va RBAC ruxsatlariga ega.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.ai_tools_registry import AITool, AIToolRegistry, _fmt, _sf
from app.ai.sql_executor import execute_sql_readonly
from app.models.user import User


# ─── Pydantic Argument Sxemalari ──────────────────────────────────────────────

class RunSqlArgs(BaseModel):
    sql: str = Field(..., description="PostgreSQL SELECT so'rovi (faqat ai_v_* ko'rinishlari ustida)")


class StockMovementsArgs(BaseModel):
    product: str = Field(..., description="Mahsulot nomi yoki ID'si")
    warehouse: Optional[str] = Field(None, description="Ombor nomi yoki ID'si (ixtiyoriy)")
    date_from: Optional[str] = Field(None, description="Boshlang'ich sana (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Tugash sanasi (YYYY-MM-DD)")
    limit: Optional[int] = Field(50, ge=1, le=200, description="Qatorlar limiti (standart: 50, maks: 200)")


class QuerySalesArgs(BaseModel):
    product: Optional[str] = Field(None, description="Mahsulot nomi yoki ID'si bo'yicha filter")
    customer: Optional[str] = Field(None, description="Mijoz ismi yoki ID'si bo'yicha filter")
    warehouse: Optional[str] = Field(None, description="Ombor nomi bo'yicha filter")
    date_from: Optional[str] = Field(None, description="Boshlang'ich sana (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Tugash sanasi (YYYY-MM-DD)")
    payment_type: Optional[str] = Field(None, description="To'lov turi: cash, card, debt, transfer")
    group_by: Optional[str] = Field(None, description="Guruhlash: 'date', 'customer', 'payment_type'")
    limit: Optional[int] = Field(50, ge=1, le=200, description="Maksimal qatorlar soni (standart: 50)")


class GetDebtsArgs(BaseModel):
    counterparty: Optional[str] = Field(None, description="Mijoz nomi yoki telefoni bo'yicha qidirish")
    currency: Optional[str] = Field(None, description="Valyuta kodi (masalan: 'UZS', 'USD')")
    overdue_only: Optional[bool] = Field(False, description="Faqat muddati o'tgan yoki eng katta qarzdorlar")
    limit: Optional[int] = Field(50, ge=1, le=200, description="Qatorlar limiti (standart: 50)")


class GetPurchasesArgs(BaseModel):
    supplier: Optional[str] = Field(None, description="Yetkazib beruvchi nomi")
    product: Optional[str] = Field(None, description="Mahsulot nomi")
    date_from: Optional[str] = Field(None, description="Boshlang'ich sana (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Tugash sanasi (YYYY-MM-DD)")
    status: Optional[str] = Field(None, description="Holat: completed, pending, cancelled")
    limit: Optional[int] = Field(50, ge=1, le=200, description="Qatorlar limiti (standart: 50)")


class GetReturnsArgs(BaseModel):
    customer: Optional[str] = Field(None, description="Mijoz ismi")
    warehouse: Optional[str] = Field(None, description="Ombor nomi")
    date_from: Optional[str] = Field(None, description="Boshlang'ich sana (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Tugash sanasi (YYYY-MM-DD)")
    limit: Optional[int] = Field(50, ge=1, le=200, description="Qatorlar limiti (standart: 50)")


class GetProductCardArgs(BaseModel):
    query: str = Field(..., description="Mahsulot nomi, shtrixkodi yoki artikuli (SKU)")


class ExplainNegativeStockArgs(BaseModel):
    product: str = Field(..., description="Minusga tushgan mahsulot nomi yoki ID'si")
    warehouse: Optional[str] = Field(None, description="Aniq ombor nomi yoki ID'si (ixtiyoriy)")


# ─── 1. RUN_SQL_READONLY VOSITASI ─────────────────────────────────────────────

@AIToolRegistry.register
class RunSqlReadonlyTool(AITool):
    name = "run_sql_readonly"
    description = (
        "Erkin PostgreSQL SELECT so'rovini xavfsiz va faqat o'qish rejimida bajaradi. "
        "Faqat quyidagi semantik ko'rinishlarga ruxsat berilgan: ai_v_sales, ai_v_sale_items, "
        "ai_v_stock_balance, ai_v_stock_movements, ai_v_debts, ai_v_customers, ai_v_products, "
        "ai_v_purchases, ai_v_returns. Har qanday yozish (INSERT/UPDATE/DELETE/DDL), "
        "tizim sxemalari (pg_catalog) va noqonuniy buyruqlar avtomatik rad etiladi. "
        "LIMIT majburiy tarzda 200 gacha cheklanadi."
    )
    required_permission = "reports.view"
    risk_level = "LOW"
    read_only = True
    parameters = RunSqlArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        validated = RunSqlArgs(**kwargs)
        res = execute_sql_readonly(
            sql_query=validated.sql,
            company_id=company_id,
            user_id=user.id,
            db_audit=db
        )

        if res.get("status") == "error":
            return {
                "reply": f"❌ SQL Xatosi: {res.get('message')}",
                "action": {"type": "error", "error_type": res.get("error_type")}
            }

        rows = res.get("rows", [])
        cnt = res.get("row_count", 0)
        note = res.get("note")

        lines = [f"📊 SQL so'rovi muvaffaqiyatli bajarildi ({cnt} ta qator topildi):"]
        if note:
            lines.append(f"⚠️ {note}")

        # Dastlabki 10 ta qatorni matn ko'rinishida ko'rsatish
        sample = rows[:10]
        if sample:
            lines.append("Namunaviy qatorlar:")
            for i, r in enumerate(sample, 1):
                kv = ", ".join(f"{k}: {v}" for k, v in list(r.items())[:6])
                lines.append(f"  {i}. {kv}")
            if cnt > 10:
                lines.append(f"  ... va yana {cnt - 10} ta qator.")

        return {
            "reply": "\n".join(lines),
            "data": rows,
            "action": {"type": "sql_result", "row_count": cnt, "truncated": res.get("is_truncated", False)}
        }


# ─── 2. GET_STOCK_MOVEMENTS VOSITASI ──────────────────────────────────────────

@AIToolRegistry.register
class GetStockMovementsTool(AITool):
    name = "get_stock_movements"
    description = (
        "Mahsulotning ombordagi harakatlar tarixini (kirim, chiqim, sotuv, inventarizatsiya, ko'chirish) "
        "va har bir harakatdan keyingi qoldig'ini (running_balance) ko'rsatadi. "
        "Ombor bo'yicha yoki sanalar oralig'ida filtrlash mumkin."
    )
    required_permission = "inventory.view"
    risk_level = "LOW"
    read_only = True
    parameters = StockMovementsArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = StockMovementsArgs(**kwargs)
        
        # SQL qurish (ai_v_stock_movements ustida)
        conditions = ["1=1"]
        prod_esc = args.product.strip().replace("'", "''")

        if args.product.isdigit():
            conditions.append(f"(product_id = {int(args.product)} OR product_name ILIKE '%{prod_esc}%')")
        else:
            conditions.append(f"product_name ILIKE '%{prod_esc}%'")

        if args.warehouse:
            wh_esc = args.warehouse.strip().replace("'", "''")
            if args.warehouse.isdigit():
                conditions.append(f"(warehouse_id = {int(args.warehouse)} OR warehouse_name ILIKE '%{wh_esc}%')")
            else:
                conditions.append(f"warehouse_name ILIKE '%{wh_esc}%'")

        if args.date_from:
            date_from_esc = args.date_from.strip().replace("'", "''")
            conditions.append(f"created_at >= '{date_from_esc}'")

        if args.date_to:
            date_to_esc = args.date_to.strip().replace("'", "''")
            conditions.append(f"created_at <= '{date_to_esc} 23:59:59'")

        where_clause = " AND ".join(conditions)
        sql = f"""
        SELECT 
            id AS movement_id, created_at, product_name, warehouse_name, 
            movement_type, quantity, running_balance, document_number AS doc_number, reason
        FROM ai_v_stock_movements
        WHERE {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT {args.limit};
        """

        res = execute_sql_readonly(sql, company_id=company_id, user_id=user.id, db_audit=db)
        if res.get("status") == "error":
            return {"reply": f"❌ Harakatlarni olishda xatolik: {res.get('message')}"}

        rows = res.get("rows", [])
        if not rows:
            return {"reply": f"ℹ️ '{args.product}' mahsuloti bo'yicha ko'rsatilgan shartlarda harakatlar topilmadi."}

        lines = [f"📦 '{args.product}' bo'yicha ombor harakatlari ({len(rows)} ta ko'rsatilmoqda):"]
        for r in rows:
            dt = str(r.get("created_at") or "")[:16].replace("T", " ")
            mtype = r.get("movement_type", "")
            qty = r.get("quantity", 0)
            bal = r.get("running_balance", 0)
            wh = r.get("warehouse_name") or "Asosiy ombor"
            doc = r.get("doc_number") or r.get("reason") or "-"
            sign = "+" if qty > 0 else ""
            lines.append(f"  • {dt} | {wh} | {mtype}: {sign}{qty} ta → Qoldiq: {bal} ta (Hujjat: {doc})")

        return {
            "reply": "\n".join(lines),
            "data": rows,
            "action": {"type": "show_data", "data": rows}
        }


# ─── 3. QUERY_SALES VOSITASI ──────────────────────────────────────────────────

@AIToolRegistry.register
class QuerySalesTool(AITool):
    name = "query_sales"
    description = (
        "Sotuvlarni tahlil qilish va filtrlash vositasi. Mahsulot, mijoz, to'lov turi va sanalar bo'yicha "
        "qidirish hamda kun, mijoz yoki to'lov turi bo'yicha guruhlangan xulosa olish imkonini beradi."
    )
    required_permission = "sales.view"
    risk_level = "LOW"
    read_only = True
    parameters = QuerySalesArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = QuerySalesArgs(**kwargs)
        conditions = ["1=1"]
        params = {"comp_id": str(company_id)}

        if args.customer:
            conditions.append(f"customer_name ILIKE '%{args.customer.strip()}%'")
        if args.warehouse:
            conditions.append(f"warehouse_name ILIKE '%{args.warehouse.strip()}%'")
        if args.payment_type:
            conditions.append(f"payment_type = '{args.payment_type.strip()}'")
        if args.date_from:
            conditions.append(f"created_at >= '{args.date_from}'")
        if args.date_to:
            conditions.append(f"created_at <= '{args.date_to} 23:59:59'")

        where_clause = " AND ".join(conditions)

        if args.group_by == "payment_type":
            sql = f"""
            SELECT payment_type, COUNT(*) as count, SUM(total_amount) as total
            FROM ai_v_sales
            WHERE {where_clause}
            GROUP BY payment_type
            ORDER BY total DESC;
            """
        elif args.group_by == "customer":
            sql = f"""
            SELECT customer_name, COUNT(*) as count, SUM(total_amount) as total
            FROM ai_v_sales
            WHERE {where_clause} AND customer_name IS NOT NULL
            GROUP BY customer_name
            ORDER BY total DESC
            LIMIT {args.limit};
            """
        elif args.group_by == "date":
            sql = f"""
            SELECT DATE_TRUNC('day', created_at) as sale_date, COUNT(*) as count, SUM(total_amount) as total
            FROM ai_v_sales
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY sale_date DESC
            LIMIT {args.limit};
            """
        else:
            sql = f"""
            SELECT id AS sale_id, number AS sale_number, created_at, customer_name, total_amount, payment_type, status
            FROM ai_v_sales
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT {args.limit};
            """

        res = execute_sql_readonly(sql, company_id=company_id, user_id=user.id, db_audit=db)
        if res.get("status") == "error":
            return {"reply": f"❌ Sotuvlarni so'rashda xatolik: {res.get('message')}"}

        rows = res.get("rows", [])
        if not rows:
            return {"reply": "ℹ️ Ko'rsatilgan mezonlarga mos sotuvlar topilmadi."}

        lines = [f"💰 Sotuvlar hisoboti ({len(rows)} ta yozuv):"]
        total_sum = 0.0
        for r in rows:
            if args.group_by == "payment_type":
                pt = r.get("payment_type") or "Noma'lum"
                tot = _sf(r.get("total"))
                cnt = r.get("count", 0)
                total_sum += tot
                lines.append(f"  • {pt.upper()}: {_fmt(tot)} ({cnt} ta sotuv)")
            elif args.group_by in ("customer", "date"):
                label = r.get("customer_name") or str(r.get("sale_date", ""))[:10]
                tot = _sf(r.get("total"))
                cnt = r.get("count", 0)
                total_sum += tot
                lines.append(f"  • {label}: {_fmt(tot)} ({cnt} ta sotuv)")
            else:
                snum = r.get("sale_number", "")
                dt = str(r.get("created_at") or "")[:16].replace("T", " ")
                cname = r.get("customer_name") or "Chakana"
                tot = _sf(r.get("total_amount"))
                total_sum += tot
                lines.append(f"  • #{snum} | {dt} | {cname} | {_fmt(tot)} ({r.get('payment_type', '')})")

        if total_sum > 0:
            lines.append(f"\n💵 Jami summa: {_fmt(total_sum)}")

        return {"reply": "\n".join(lines), "data": rows, "action": {"type": "show_data", "data": rows}}


# ─── 4. GET_DEBTS VOSITASI ────────────────────────────────────────────────────

@AIToolRegistry.register
class GetDebtsTool(AITool):
    name = "get_debts"
    description = (
        "Mijozlarning qarzlarini ko'rsatadi. Har bir valyuta (UZS, USD) alohida qatorda chiqadi, "
        "valyutalar bir-biriga qo'shib yuborilmaydi. Valyuta bo'yicha filter qilish mumkin."
    )
    required_permission = "customers.view"
    risk_level = "LOW"
    read_only = True
    parameters = GetDebtsArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = GetDebtsArgs(**kwargs)
        conditions = ["debt_amount > 0"]

        if args.counterparty:
            conditions.append(f"customer_name ILIKE '%{args.counterparty.strip()}%'")
        if args.currency:
            conditions.append(f"currency = '{args.currency.strip().upper()}'")

        where_clause = " AND ".join(conditions)
        sql = f"""
        SELECT customer_id, customer_name, phone, currency, debt_amount
        FROM ai_v_debts
        WHERE {where_clause}
        ORDER BY debt_amount DESC
        LIMIT {args.limit};
        """

        res = execute_sql_readonly(sql, company_id=company_id, user_id=user.id, db_audit=db)
        if res.get("status") == "error":
            return {"reply": f"❌ Qarzlarni olishda xatolik: {res.get('message')}"}

        rows = res.get("rows", [])
        if not rows:
            return {"reply": "ℹ️ Ko'rsatilgan shartlar bo'yicha qarzdorlar topilmadi."}

        lines = [f"📋 Mijozlar qarzlari ro'yxati ({len(rows)} ta qator):"]
        totals_by_currency: Dict[str, float] = {}

        for r in rows:
            cname = r.get("customer_name") or "Noma'lum"
            curr = r.get("currency") or "UZS"
            amt = _sf(r.get("debt_amount"))
            phone = f" ({r.get('phone')})" if r.get("phone") else ""
            totals_by_currency[curr] = totals_by_currency.get(curr, 0.0) + amt

            amt_str = f"{amt:,.2f} {curr}" if curr != "UZS" else _fmt(amt)
            lines.append(f"  • {cname}{phone}: {amt_str}")

        lines.append("\n📊 Valyutalar kesimida jami qarz:")
        for curr, tot in totals_by_currency.items():
            tot_str = f"{tot:,.2f} {curr}" if curr != "UZS" else _fmt(tot)
            lines.append(f"  • {curr}: {tot_str}")

        return {"reply": "\n".join(lines), "data": rows, "action": {"type": "show_data", "data": rows}}


# ─── 5. GET_PURCHASES VOSITASI ────────────────────────────────────────────────

@AIToolRegistry.register
class GetPurchasesTool(AITool):
    name = "get_purchases"
    description = (
        "Xarid buyurtmalari (ta'minotchilardan qabul qilingan tovarlar) hisobotini ko'rsatadi. "
        "Ta'minotchi, sana va holat bo'yicha filtrlash mumkin."
    )
    required_permission = "purchases.view"
    risk_level = "LOW"
    read_only = True
    parameters = GetPurchasesArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = GetPurchasesArgs(**kwargs)
        conditions = ["1=1"]

        if args.supplier:
            conditions.append(f"supplier_name ILIKE '%{args.supplier.strip()}%'")
        if args.status:
            conditions.append(f"status = '{args.status.strip()}'")
        if args.date_from:
            conditions.append(f"created_at >= '{args.date_from}'")
        if args.date_to:
            conditions.append(f"created_at <= '{args.date_to} 23:59:59'")

        where_clause = " AND ".join(conditions)
        sql = f"""
        SELECT id AS po_id, po_number, created_at, supplier_name, total_amount, status
        FROM ai_v_purchases
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT {args.limit};
        """

        res = execute_sql_readonly(sql, company_id=company_id, user_id=user.id, db_audit=db)
        if res.get("status") == "error":
            return {"reply": f"❌ Xaridlarni olishda xatolik: {res.get('message')}"}

        rows = res.get("rows", [])
        if not rows:
            return {"reply": "ℹ️ Ko'rsatilgan shartlarga mos xaridlar topilmadi."}

        lines = [f"📥 Xaridlar ro'yxati ({len(rows)} ta):"]
        for r in rows:
            pnum = r.get("po_number") or f"PO-{r.get('po_id')}"
            dt = str(r.get("created_at") or "")[:16].replace("T", " ")
            sname = r.get("supplier_name") or "Noma'lum"
            tot = _sf(r.get("total_amount"))
            lines.append(f"  • #{pnum} | {dt} | {sname} | {_fmt(tot)} ({r.get('status', '')})")

        return {"reply": "\n".join(lines), "data": rows, "action": {"type": "show_data", "data": rows}}


# ─── 6. GET_RETURNS VOSITASI ──────────────────────────────────────────────────

@AIToolRegistry.register
class GetReturnsTool(AITool):
    name = "get_returns"
    description = (
        "Mijozlar tomonidan qaytarilgan tovarlar (vazvrat hujjatlari) hisoboti. "
        "Faqat haqiqiy qaytarish hujjatlari (R... raqamli va refunded holatdagi) ko'rsatiladi."
    )
    required_permission = "sales.view"
    risk_level = "LOW"
    read_only = True
    parameters = GetReturnsArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = GetReturnsArgs(**kwargs)
        conditions = ["1=1"]

        if args.customer:
            conditions.append(f"customer_name ILIKE '%{args.customer.strip()}%'")
        if args.warehouse:
            conditions.append(f"warehouse_name ILIKE '%{args.warehouse.strip()}%'")
        if args.date_from:
            conditions.append(f"created_at >= '{args.date_from}'")
        if args.date_to:
            conditions.append(f"created_at <= '{args.date_to} 23:59:59'")

        where_clause = " AND ".join(conditions)
        sql = f"""
        SELECT return_id, return_number, created_at, customer_name, warehouse_name, total_amount, payment_type, note
        FROM ai_v_returns
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT {args.limit};
        """

        res = execute_sql_readonly(sql, company_id=company_id, user_id=user.id, db_audit=db)
        if res.get("status") == "error":
            return {"reply": f"❌ Qaytarishlarni olishda xatolik: {res.get('message')}"}

        rows = res.get("rows", [])
        if not rows:
            return {"reply": "ℹ️ Ko'rsatilgan davrda qaytarish hujjatlari mavjud emas."}

        lines = [f"🔄 Qaytarish hujjatlari ({len(rows)} ta):"]
        total_refunded = 0.0
        for r in rows:
            rnum = r.get("return_number")
            dt = str(r.get("created_at") or "")[:16].replace("T", " ")
            cname = r.get("customer_name") or "Chakana"
            wh = r.get("warehouse_name") or "Ombor"
            tot = _sf(r.get("total_amount"))
            total_refunded += tot
            note = f" — {r.get('note')}" if r.get("note") else ""
            lines.append(f"  • #{rnum} | {dt} | {wh} | {cname} | {_fmt(tot)}{note}")

        lines.append(f"\n💵 Jami qaytarilgan summa: {_fmt(total_refunded)}")
        return {"reply": "\n".join(lines), "data": rows, "action": {"type": "show_data", "data": rows}}


# ─── 7. GET_PRODUCT_CARD VOSITASI ─────────────────────────────────────────────

@AIToolRegistry.register
class GetProductCardTool(AITool):
    name = "get_product_card"
    description = (
        "Mahsulot haqida to'liq kartochka ma'lumotlarini taqdim etadi: "
        "nomi, kategoriya, barcha omborlardagi qoldiqlari, jami qoldiq, narxlari va shtrixkodi."
    )
    required_permission = "products.view"
    risk_level = "LOW"
    read_only = True
    parameters = GetProductCardArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = GetProductCardArgs(**kwargs)
        q = args.query.strip()
        
        # 1. Mahsulotni topamiz
        cond = f"(name ILIKE '%{q}%' OR barcode ILIKE '%{q}%' OR sku ILIKE '%{q}%')"
        if q.isdigit():
            cond = f"(id = {int(q)} OR {cond})"

        prod_sql = f"""
        SELECT id, name, sku, barcode, unit, sale_price, cost_price
        FROM ai_v_products
        WHERE {cond}
        LIMIT 5;
        """
        res_prod = execute_sql_readonly(prod_sql, company_id=company_id, user_id=user.id, db_audit=db)
        products = res_prod.get("rows", [])
        if not products:
            return {"reply": f"❌ '{q}' bo'yicha mahsulot topilmadi."}

        p = products[0]
        pid = p.get("id")

        # 2. Omborlar bo'yicha qoldiqni olamiz
        stock_sql = f"""
        SELECT warehouse_name, quantity, total_quantity
        FROM ai_v_stock_balance
        WHERE product_id = {pid};
        """
        res_stock = execute_sql_readonly(stock_sql, company_id=company_id, user_id=user.id, db_audit=db)
        stocks = res_stock.get("rows", [])

        total_qty = 0.0
        stock_lines = []
        for s in stocks:
            wname = s.get("warehouse_name") or "Asosiy ombor"
            qty = _sf(s.get("quantity"))
            total_qty += qty
            stock_lines.append(f"  🏢 {wname}: {int(qty) if qty.is_integer() else qty} {p.get('unit') or 'dona'}")

        if not stock_lines:
            stock_lines.append("  🏢 Barcha omborlarda: 0 dona")

        p_name = p.get("name")
        sku = p.get("sku") or "-"
        barcode = p.get("barcode") or "-"
        sprice = _fmt(_sf(p.get("sale_price")))
        cprice = _fmt(_sf(p.get("cost_price")))

        lines = [
            f"🏷️ Mahsulot kartochkasi: **{p_name}** (ID: {pid})",
            f"📁 Birlik: {p.get('unit') or 'dona'}",
            f"🔢 SKU: {sku} | Shtrixkod: {barcode}",
            f"💵 Sotuv narxi: {sprice} | Tan narxi: {cprice}",
            f"📊 Jami zaxira: **{int(total_qty) if total_qty.is_integer() else total_qty}** {p.get('unit') or 'dona'}",
            "Omborlar kesimida:",
            *stock_lines
        ]

        return {
            "reply": "\n".join(lines),
            "data": {"product": p, "stocks": stocks, "total_stock": total_qty},
            "action": {"type": "show_data", "data": p}
        }


# ─── 8. EXPLAIN_NEGATIVE_STOCK VOSITASI ───────────────────────────────────────

@AIToolRegistry.register
class ExplainNegativeStockTool(AITool):
    name = "explain_negative_stock"
    description = (
        "Mahsulot nima sababdan minus qoldiqqa tushganini aniq tahlil qilib beradi: "
        "minus boshlangan sana va hujjat, o'sha kungi barcha harakatlar, omborlar kesimida qoldiqlar "
        "va boshqa omborda tovar ortiqcha bo'lsa (omborlararo siljish zarurligi) tavsiyalar beradi."
    )
    required_permission = "inventory.view"
    risk_level = "LOW"
    read_only = True
    parameters = ExplainNegativeStockArgs.model_json_schema()

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        args = ExplainNegativeStockArgs(**kwargs)
        pquery = args.product.strip()

        # 1. Mahsulotni topamiz
        p_cond = f"(name ILIKE '%{pquery}%' OR sku ILIKE '%{pquery}%')"
        if pquery.isdigit():
            p_cond = f"(id = {int(pquery)} OR {p_cond})"

        prod_sql = f"SELECT id, name, unit FROM ai_v_products WHERE {p_cond} LIMIT 1;"
        res_prod = execute_sql_readonly(prod_sql, company_id=company_id, user_id=user.id, db_audit=db)
        prods = res_prod.get("rows", [])
        if not prods:
            return {"reply": f"❌ '{pquery}' bo'yicha mahsulot topilmadi."}

        p = prods[0]
        pid = p.get("id")
        pname = p.get("name")
        unit = p.get("unit") or "dona"

        # 2. Omborlar bo'yicha joriy qoldiqni tekshiramiz
        stock_sql = f"""
        SELECT warehouse_id, warehouse_name, quantity, total_quantity
        FROM ai_v_stock_balance
        WHERE product_id = {pid};
        """
        res_stocks = execute_sql_readonly(stock_sql, company_id=company_id, user_id=user.id, db_audit=db)
        stocks = res_stocks.get("rows", [])

        wh_balances: Dict[str, float] = {}
        total_balance = 0.0
        negative_warehouses = []
        positive_warehouses = []

        for s in stocks:
            wname = s.get("warehouse_name") or f"Ombor #{s.get('warehouse_id')}"
            qty = _sf(s.get("quantity"))
            wh_balances[wname] = qty
            total_balance += qty
            if qty < 0:
                negative_warehouses.append((wname, qty))
            elif qty > 0:
                positive_warehouses.append((wname, qty))

        # 3. Harakatlar tarixidan birinchi minus bo'lgan paytni qidiramiz
        wh_filter = ""
        if args.warehouse:
            wh_filter = f"AND (warehouse_name ILIKE '%{args.warehouse.strip()}%')"

        timeline_sql = f"""
        SELECT 
            id AS movement_id, created_at, warehouse_name, movement_type, 
            quantity, running_balance, document_number AS doc_number, reason
        FROM ai_v_stock_movements
        WHERE product_id = {pid} {wh_filter}
        ORDER BY created_at ASC, id ASC;
        """
        res_timeline = execute_sql_readonly(timeline_sql, company_id=company_id, user_id=user.id, db_audit=db)
        movements = res_timeline.get("rows", [])

        first_negative_mv = None
        for mv in movements:
            if _sf(mv.get("running_balance")) < 0:
                first_negative_mv = mv
                break

        # 4. Tahlil xulosasini tuzamiz
        lines = [f"🔍 **'{pname}'** mahsuloti minus qoldiq tahlili:"]

        if not negative_warehouses and total_balance >= 0:
            lines.append(f"✅ Joriy holatda ushbu mahsulot minusda emas. Jami qoldiq: {total_balance} {unit}.")
            for wname, b in wh_balances.items():
                lines.append(f"  • {wname}: {b} {unit}")
            return {
                "reply": "\n".join(lines),
                "data": {
                    "product_id": pid,
                    "product_name": pname,
                    "total_balance": total_balance,
                    "warehouse_balances": wh_balances,
                    "first_negative_movement": None
                }
            }


        lines.append(f"\n📊 **Joriy qoldiqlar holati:**")
        lines.append(f"  • Korxona bo'yicha jami: **{total_balance} {unit}**")
        for wname, b in wh_balances.items():
            status_icon = "🔴" if b < 0 else "🟢"
            lines.append(f"  {status_icon} {wname}: {b} {unit}")

        if first_negative_mv:
            fn_date_full = str(first_negative_mv.get("created_at") or "")
            fn_day = fn_date_full[:10]
            fn_doc = first_negative_mv.get("doc_number") or first_negative_mv.get("reason") or "Noma'lum"
            fn_wh = first_negative_mv.get("warehouse_name")
            fn_qty = first_negative_mv.get("quantity")
            fn_bal = first_negative_mv.get("running_balance")

            lines.append(f"\n⚠️ **Minus qoldiq qachon va qaysi hujjat bilan boshlangan:**")
            lines.append(f"  • Sana va vaqt: **{fn_date_full[:16].replace('T', ' ')}**")
            lines.append(f"  • Ombor: **{fn_wh}**")
            lines.append(f"  • Sabab bo'lgan harakat: {first_negative_mv.get('movement_type')} ({fn_qty} {unit})")
            lines.append(f"  • Hujjat raqami: **#{fn_doc}**")
            lines.append(f"  • Ushbu harakatdan keyingi qoldiq: **{fn_bal} {unit}**")

            # O'sha kungi barcha harakatlar
            same_day_mvs = [m for m in movements if str(m.get("created_at") or "")[:10] == fn_day]
            if same_day_mvs:
                lines.append(f"\n📅 **{fn_day} sanasidagi barcha harakatlar ({len(same_day_mvs)} ta):**")
                for sm in same_day_mvs:
                    sqty = sm.get("quantity")
                    ssign = "+" if sqty > 0 else ""
                    sdoc = sm.get("doc_number") or sm.get("reason") or "-"
                    lines.append(f"    - {str(sm.get('created_at'))[11:16]} | {sm.get('warehouse_name')} | {sm.get('movement_type')}: {ssign}{sqty} ta → Qoldiq: {sm.get('running_balance')} ta (#{sdoc})")

        # 5. Tavsiyalar va yechim
        lines.append("\n💡 **Xulosa va tavsiya:**")
        if negative_warehouses and positive_warehouses and total_balance >= 0:
            neg_w, neg_amt = negative_warehouses[0]
            pos_w, pos_amt = positive_warehouses[0]
            lines.append(
                f"  👉 Korxona bo'yicha jami qoldiq ijobiy ({total_balance} {unit}), lekin **{neg_w}** omborida minus ({neg_amt} {unit}) "
                f"va **{pos_w}** omborida ortiqcha ({pos_amt} {unit}) mavjud.\n"
                f"  ➡️ Tavsiya: **{pos_w}** dan **{neg_w}** ga {abs(neg_amt)} {unit} mahsulotni "
                f"'Omborlararo ko'chirish' (Transfer) orqali o'tkazish kerak."
            )
        elif total_balance < 0:
            lines.append(
                f"  👉 Korxona bo'yicha jami qoldiq minusda ({total_balance} {unit}). Haqiqatda mavjud bo'lmagan tovar sotilgan "
                f"yoki yetkazib beruvchidan kelgan kirim hujjati tizimga kiritilmagan.\n"
                f"  ➡️ Tavsiya: Kirim (Xarid) hujjatini rasmiylashtiring yoki inventarizatsiya orqali qoldiqni to'g'rilang."
            )

        return {
            "reply": "\n".join(lines),
            "data": {
                "product_id": pid,
                "product_name": pname,
                "total_balance": total_balance,
                "warehouse_balances": wh_balances,
                "first_negative_movement": first_negative_mv
            },
            "action": {"type": "show_data"}
        }
