"""
AI run_sql_readonly uchun ajratilgan xavfsiz PostgreSQL ijrochi moduli.
Faqat ai_sql_ro roli va AI_DB_URL_READONLY ulanishidan foydalanadi.
"""
import time
from decimal import Decimal
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.ai.sql_parser import validate_and_sanitize_sql, SQLSecurityError
from app.models.ai_audit import AIAuditLog

# Read-only engine kesh
_ro_engine = None


def get_ai_readonly_engine():
    global _ro_engine
    if _ro_engine is not None:
        return _ro_engine

    db_url = settings.AI_DB_URL_READONLY
    if not db_url:
        # Standart URL dan ai_sql_ro roli uchun hosil qilish
        base_url = settings.DATABASE_URL
        if "@" in base_url:
            proto, rest = base_url.split("://", 1)
            creds_and_host = rest.split("@", 1)
            db_url = f"{proto}://ai_sql_ro:ai_sql_ro_pass@{creds_and_host[1]}"
        else:
            db_url = "postgresql+psycopg://ai_sql_ro:ai_sql_ro_pass@localhost:5432/erppos"

    _ro_engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={
            "options": f"-c statement_timeout={settings.AI_SQL_TIMEOUT_SEC * 1000} -c default_transaction_read_only=on"
        }
    )
    return _ro_engine


def _json_serializable(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def execute_sql_readonly(
    sql_query: str,
    company_id: int,
    user_id: int,
    db_audit: Optional[Session] = None,
    max_limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Erkin SQL so'rovini tekshiradi va ai_sql_ro roli ostida xavfsiz bajaradi.
    1. AST parser orqali tekshirish (sqlglot).
    2. Rad etilsa AIAuditLog ga yozish va xato qaytarish.
    3. Muvaffaqiyatli bo'lsa ai_sql_ro ulanishida app.company_id o'rnatib SELECT qilish.
    4. Hajmni cheklash va natijani qaytarish.
    """
    limit = max_limit or settings.AI_SQL_MAX_ROWS or 200
    t0 = time.time()

    # 1. SQL ni tekshirish va tozalash
    try:
        sanitized_sql = validate_and_sanitize_sql(sql_query, max_limit=limit)
    except SQLSecurityError as e:
        rejection_reason = str(e)
        duration_ms = (time.time() - t0) * 1000.0
        # Audit log ga rad sababi bilan yozish
        if db_audit is not None:
            try:
                log_entry = AIAuditLog(
                    company_id=company_id,
                    user_id=user_id,
                    tool_name="run_sql_readonly",
                    tool_arguments={"sql": sql_query},
                    risk_level="LOW",
                    status="REJECTED",
                    error=rejection_reason,
                    execution_time_ms=duration_ms
                )
                db_audit.add(log_entry)
                db_audit.commit()
            except Exception:
                db_audit.rollback()

        return {
            "status": "error",
            "error_type": "SecurityRejection",
            "message": f"SQL so'rovi xavfsizlik filtri tomonidan rad etildi: {rejection_reason}"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": "ParserError",
            "message": f"SQL so'rovini tahlil qilishda xatolik: {e}"
        }

    # 2. ai_sql_ro orqali xavfsiz bajarish
    engine = get_ai_readonly_engine()
    try:
        with engine.connect() as conn:
            # Tenant kontekstini o'rnatamiz (SET buyrug'i parametr qabul qilmaydi, int xavfsiz)
            conn.execute(text(f"SET LOCAL app.company_id = '{int(company_id)}';"))
            
            result = conn.execute(text(sanitized_sql))
            columns = list(result.keys())
            
            # Fetch up to limit + 1 to detect truncation
            raw_rows = result.fetchmany(limit + 1)
            
            is_truncated = False
            note = None
            if len(raw_rows) > limit:
                is_truncated = True
                raw_rows = raw_rows[:limit]
                note = f"Natija qisqartirildi: jami so'rovdan dastlabki {limit} ta qator ko'rsatilmoqda."

            formatted_rows: List[Dict[str, Any]] = []
            for row in raw_rows:
                row_dict = {col: _json_serializable(val) for col, val in zip(columns, row)}
                formatted_rows.append(row_dict)

            duration_ms = (time.time() - t0) * 1000.0

            # Audit log
            if db_audit is not None:
                try:
                    log_entry = AIAuditLog(
                        company_id=company_id,
                        user_id=user_id,
                        tool_name="run_sql_readonly",
                        tool_arguments={"sql": sanitized_sql},
                        risk_level="LOW",
                        status="SUCCESS",
                        result_summary=f"{len(formatted_rows)} qator qaytarildi" + (" (qisqartirilgan)" if is_truncated else ""),
                        execution_time_ms=duration_ms
                    )
                    db_audit.add(log_entry)
                    db_audit.commit()
                except Exception:
                    db_audit.rollback()

            return {
                "status": "success",
                "columns": columns,
                "rows": formatted_rows,
                "row_count": len(formatted_rows),
                "is_truncated": is_truncated,
                "note": note,
                "execution_time_ms": round(duration_ms, 2)
            }

    except Exception as e:
        duration_ms = (time.time() - t0) * 1000.0
        err_msg = str(e)
        if db_audit is not None:
            try:
                log_entry = AIAuditLog(
                    company_id=company_id,
                    user_id=user_id,
                    tool_name="run_sql_readonly",
                    tool_arguments={"sql": sanitized_sql},
                    risk_level="LOW",
                    status="ERROR",
                    error=err_msg,
                    execution_time_ms=duration_ms
                )
                db_audit.add(log_entry)
                db_audit.commit()
            except Exception:
                db_audit.rollback()

        return {
            "status": "error",
            "error_type": "ExecutionError",
            "message": f"Bazada so'rovni bajarishda xatolik: {err_msg}"
        }
