"""
SQLglot yordamida AI uchun xavfsiz PostgreSQL SELECT so'rovlarini tahlil qilish va tozalash moduli.
Bosqich 4: run_sql_readonly xavfsizlik filtri.
"""
import re
from typing import Set
import sqlglot
from sqlglot import exp

# Ruxsat berilgan semantik ko'rinishlar (faqat ai_v_*)
ALLOWED_VIEWS: Set[str] = {
    "ai_v_sales",
    "ai_v_sale_items",
    "ai_v_stock_balance",
    "ai_v_stock_movements",
    "ai_v_debts",
    "ai_v_customers",
    "ai_v_products",
    "ai_v_purchases",
    "ai_v_returns",
}

# Ruxsat berilgan xavfsiz SQL funksiyalari (oq ro'yxat)
ALLOWED_FUNCTIONS: Set[str] = {
    # Agregatlar
    "sum", "count", "avg", "min", "max",
    # Matn
    "lower", "upper", "trim", "btrim", "ltrim", "rtrim",
    "concat", "concat_ws", "length", "substr", "substring", "replace",
    "left", "right", "like", "ilike", "to_char",
    # Raqamlar va matematika
    "round", "abs", "ceil", "ceiling", "floor", "power", "sqrt",
    "greatest", "least", "sign",
    # Sana va vaqt
    "date_trunc", "timestamp_trunc", "now", "current_date", "current_time", "current_timestamp",
    "extract", "age", "to_date", "to_timestamp",
    # Mantiqiy va shartli
    "coalesce", "nullif", "cast", "try_cast",
}


class SQLSecurityError(ValueError):
    """Xavfli yoki ruxsat berilmagan SQL so'rovi uchun istisno."""
    pass


def validate_and_sanitize_sql(sql_query: str, max_limit: int = 200) -> str:
    """
    SQL so'rovini tekshiradi, xavfli operator va funksiyalarni rad etadi,
    faqat ai_v_* ko'rinishlariga ruxsat beradi va LIMIT <= max_limit ni majburlaydi.

    Qaytaradi: Tozalangan va qayta formatlangan xavfsiz SQL matni.
    Xatolikda: SQLSecurityError chiqaradi.
    """
    if not sql_query or not sql_query.strip():
        raise SQLSecurityError("So'rov bo'sh bo'lishi mumkin emas")

    cleaned = sql_query.strip()
    raw_lower = cleaned.lower()

    # 1. Matn darajasidagi xavfli kalit so'zlar va buyruqlar
    dangerous_keywords = [
        "reset role", "set role", "set session", "set local", "set_config",
        "current_setting", "pg_sleep", "pg_read_file", "pg_write_file",
        "dblink", "query_to_xml", "pg_catalog", "information_schema",
        "for update", "for share", "for no key update", "select into", "copy "
    ]
    for kw in dangerous_keywords:
        pattern = r'\b' + re.escape(kw).replace(r'\ ', r'\s+') + r'\b'
        if re.search(pattern, raw_lower):
            raise SQLSecurityError(f"Ruxsat berilmagan kalit so'z yoki buyruq aniqlandi: '{kw}'")

    # 2. sqlglot orqali AST tahlil
    try:
        expressions = sqlglot.parse(cleaned, read="postgres")
    except Exception as e:
        raise SQLSecurityError(f"SQL sintaksis xatosi: {e}")

    if not expressions:
        raise SQLSecurityError("So'rov bo'sh")

    # Faqat bitta ifoda (statement) bo'lishi shart
    if len(expressions) > 1:
        raise SQLSecurityError("Faqat bitta SQL so'roviga ruxsat beriladi; ko'p statement rad etildi")

    ast = expressions[0]
    if ast is None:
        raise SQLSecurityError("So'rov tahlil qilinmadi")

    # 3. Asosiy ifoda faqat SELECT yoki UNION bo'lishi shart
    if not isinstance(ast, (exp.Select, exp.Union)):
        raise SQLSecurityError(f"Faqat SELECT so'rovlari ruxsat etiladi (topildi: {type(ast).__name__})")

    # 4. Xavfli ifoda turlarini qidirish (butun daraxt bo'yicha)
    forbidden_types = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
        exp.Create, exp.Command, exp.Set, exp.Into, exp.Lock
    )
    for forbidden in ast.find_all(forbidden_types):
        raise SQLSecurityError(f"Xavfli SQL amali aniqlandi: {type(forbidden).__name__}")

    # 5. CTE (WITH) tahlili
    cte_names: Set[str] = set()
    if hasattr(ast, "ctes") and ast.ctes:
        for cte in ast.ctes:
            alias = (cte.alias_or_name or "").lower()
            cte_names.add(alias)
            # CTE ichi faqat SELECT/UNION bo'lishi shart
            inner_query = cte.this
            if not isinstance(inner_query, (exp.Select, exp.Union)):
                raise SQLSecurityError(f"CTE '{alias}' faqat SELECT bo'lishi kerak")
            for forbidden in inner_query.find_all(forbidden_types):
                raise SQLSecurityError(f"CTE '{alias}' ichida xavfli SQL amali aniqlandi")

    # 6. Jadvallar va ko'rinishlarni tekshirish (faqat ai_v_* va CTE lar)
    for table in ast.find_all(exp.Table):
        tname = (table.name or "").lower().strip('"')
        db_name = (table.db or "").lower().strip('"')

        # Sxema tekshiruvi
        if db_name in ("pg_catalog", "information_schema") or db_name.startswith("pg_"):
            raise SQLSecurityError(f"Tizim sxemasiga murojaat rad etildi: '{db_name}'")
        if db_name and db_name not in ("public", ""):
            raise SQLSecurityError(f"Noma'lum sxemaga murojaat rad etildi: '{db_name}'")

        if tname in cte_names:
            continue

        if tname not in ALLOWED_VIEWS:
            raise SQLSecurityError(
                f"Ruxsat berilmagan jadval yoki ko'rinish: '{tname}'. "
                f"Faqat quyidagi semantik ko'rinishlarga ruxsat bor: {', '.join(sorted(ALLOWED_VIEWS))}"
            )

    # 7. Funksiyalarni tekshirish (faqat oq ro'yxat)
    for func in ast.find_all((exp.Func, exp.Anonymous)):
        # Binary operatorlar, mantiqiy bog'lovchilar (AND, OR) va predikatlarni o'tkazib yuboramiz
        if isinstance(func, (exp.Binary, exp.Connector, exp.Predicate, exp.Operator)):
            continue

        func_name = ""
        if isinstance(func, exp.Anonymous):
            func_name = (func.name or str(func.this or "")).lower()
        elif hasattr(func, "sql_name") and func.sql_name():
            func_name = func.sql_name().lower()
        elif hasattr(func, "name") and func.name:
            func_name = func.name.lower()
        else:
            func_name = (func.key or "").lower()


        func_name = func_name.strip('"')

        if "." in func_name:
            parts = func_name.split(".")
            func_name = parts[-1]
            if parts[0] in ("pg_catalog", "information_schema") or parts[0].startswith("pg_"):
                raise SQLSecurityError(f"Tizim funksiyasiga murojaat rad etildi: '{func_name}'")

        if func_name and func_name not in ALLOWED_FUNCTIONS:
            raise SQLSecurityError(
                f"Ruxsat berilmagan funksiya: '{func_name}'. Faqat oq ro'yxatdagi xavfsiz funksiyalarga ruxsat bor."
            )

    # 8. LIMIT cheklovi (standart max_limit)
    limit_clause = ast.args.get("limit")
    if limit_clause is None:
        ast = ast.limit(max_limit)
    else:
        try:
            curr_val = int(limit_clause.expression.this)
            if curr_val > max_limit or curr_val <= 0:
                ast.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
        except Exception:
            ast.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))

    # 9. Tozalangan va PostgreSQL sintaksisiga normalizatsiya qilingan SQL qaytarish
    sanitized_sql = ast.sql(dialect="postgres")
    return sanitized_sql
