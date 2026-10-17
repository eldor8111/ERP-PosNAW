"""Yagona Foyda va Zarar (P&L) hisobi (T2.2).

`/finance/profit-loss`, `/reports/profit-loss` va `/reports/pnl-compare` bir xil davr va filial uchun
BIR XIL natija berishi uchun hammasi shu servisdan foydalanadi.

Filial qoidasi (hammasi bir xil):
- Tushum, qaytarish, tannarx — sotuv filiali (`Sale.branch_id`; snapshot yo'q eski sotuvlarda ombor filiali).
  Qator darajasida (`SaleItem.warehouse_id`) taqsimlanmaydi — ma'lum cheklov: ulgurji chekning barcha
  qatorlari sarlavha filialiga yoziladi (T1.9 chekni bir filialga majburlaydi).
- Xarajat — `Expense.branch_id` (yaratishda: kassa filiali -> xodim filiali -> asosiy filial).
- Boshqa kirim — `Transaction.branch_id`, xuddi shu qoida bilan.
- Filialsiz guruh — `branch_id = UNASSIGNED_BRANCH` (-1): ombori/filiali yo'q sotuvlar, korxonaning
  hech bir filialiga tegishli bo'lmagan xarajat va tranzaksiyalar. Shunda
  sigma(filiallar) + filialsiz = butun korxona.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.moliya import Expense, ExpenseCategory, Transaction
from app.models.sale import Sale, SaleItem
from app.utils.report_utils import (
    currency_rate_map, doc_sign, item_cost_uzs, return_doc_filter, sale_branch_filter,
    sale_doc_filter, sale_or_return_filter, tx_cash_flow_filter,
)

UNASSIGNED_BRANCH = -1

# "Boshqa kirim" ga kiradigan `Transaction.reference_type` qiymatlari (oq ro'yxat) — `reference_type IS NULL`
# dan tashqari. Boshqa kirimlar sotuv/qarz/smena/ta'minotchi qaytimi va h.k. bo'lib, tushum yoki pul
# ko'chishi hisoblanadi, daromad emas:
#   delivery_fee   — yetkazib berish haqi (alohida tranzaksiya, Sale.total_amount ga kirmaydi);
#   other_income   — /finance/transactions orqali qo'lda kiritilgan boshqa kirim.
OTHER_INCOME_REFS = ("delivery_fee", "other_income")

UNCATEGORIZED_EXPENSE = "Boshqa xarajatlar"
OTHER_INCOME_NOTE = (
    "Boshqa kirim valyutalari joriy kurs bilan UZS ga o'girilgan (tranzaksiyada kurs saqlanmaydi), "
    "shuning uchun eski kirimlar uchun taxminiy"
)


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole > 0 else 0.0


def _company_branch_ids(cid: int):
    return select(Branch.id).where(Branch.company_id == cid)


def branch_condition(column, cid: int, branch_id: Optional[int]):
    """`Expense.branch_id` / `Transaction.branch_id` filtri. None/0 — filtrsiz; -1 — filialsiz
    (NULL yoki korxonaning hech bir filialiga tegishli bo'lmagan, masalan 0 yoki begona filial)."""
    if not branch_id:
        return None
    if branch_id == UNASSIGNED_BRANCH:
        return or_(column.is_(None), column.notin_(_company_branch_ids(cid)))
    return column == branch_id


def _other_income(db: Session, cid: int, start: datetime, end: datetime, branch_id: Optional[int]):
    """Boshqa kirim (UZS) va izoh. Valyutalar `Transaction.currency_code` bo'yicha guruhlanadi."""
    flt = [
        Transaction.company_id == cid,
        Transaction.created_at >= start,
        Transaction.created_at < end,
        Transaction.type == "income",
        Transaction.voided_at.is_(None),
        or_(Transaction.reference_type.is_(None), Transaction.reference_type.in_(OTHER_INCOME_REFS)),
        tx_cash_flow_filter(),
    ]
    cond = branch_condition(Transaction.branch_id, cid, branch_id)
    if cond is not None:
        flt.append(cond)
    rows = (
        db.query(Transaction.currency_code, func.coalesce(func.sum(Transaction.amount), 0))
        .filter(*flt)
        .group_by(Transaction.currency_code)
        .all()
    )
    rates = currency_rate_map(db, cid)
    total = 0.0
    converted = False
    for code, amount in rows:
        code = (code or "UZS").upper()
        value = float(amount or 0)
        if code != "UZS":
            rate = rates.get(code)
            if rate:
                value *= rate
                converted = True
        total += value
    return round(total, 2), (OTHER_INCOME_NOTE if converted else None)


def compute_pnl(db: Session, cid: int, start: datetime, end: datetime, branch_id: Optional[int] = None) -> dict:
    """Davr (`start <= created_at < end`) va filial uchun P&L (UZS).

    `branch_id`: None/0 — butun korxona; `UNASSIGNED_BRANCH` (-1) — filialsiz guruh; boshqasi — shu filial.
    `net_profit = gross_profit + other_income - expenses.total`.
    """
    sale_filters = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    if branch_id:
        sale_filters.append(sale_branch_filter(branch_id, db, cid))

    def _sum_sales(doc_filter) -> float:
        return float(
            db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(*sale_filters, doc_filter).scalar() or 0
        )

    def _sum_cost(doc_filter) -> float:
        return float(
            db.query(func.coalesce(func.sum(item_cost_uzs()), 0))
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(*sale_filters, doc_filter)
            .scalar() or 0
        )

    gross_revenue = _sum_sales(sale_doc_filter())
    returns = _sum_sales(return_doc_filter())
    net_revenue = gross_revenue - returns

    cogs = _sum_cost(sale_doc_filter())
    returns_cost = _sum_cost(return_doc_filter())
    net_cogs = cogs - returns_cost
    gross_profit = net_revenue - net_cogs

    other_income, other_income_note = _other_income(db, cid, start, end, branch_id)

    # Xarajatlar: nom bo'yicha SQL guruhlash (bir xil nomli kategoriyalar bir qatorga qo'shiladi),
    # jami esa alohida SUM — dict to'qnashuvi yo'q
    exp_flt = [
        Expense.company_id == cid,
        Expense.created_at >= start,
        Expense.created_at < end,
        Expense.voided_at.is_(None),
    ]
    cond = branch_condition(Expense.branch_id, cid, branch_id)
    if cond is not None:
        exp_flt.append(cond)
    # T2.7: USD va boshqa valyutadagi xarajat UZS ekvivalenti (amount_uzs) bilan; eski yozuvlarda NULL -> amount
    exp_uzs = func.coalesce(Expense.amount_uzs, Expense.amount)
    total_expenses = float(
        db.query(func.coalesce(func.sum(exp_uzs), 0)).filter(*exp_flt).scalar() or 0
    )
    cat_name = func.coalesce(ExpenseCategory.name, UNCATEGORIZED_EXPENSE)
    by_category = [
        {"name": name, "total": round(float(total or 0), 2)}
        for name, total in (
            db.query(cat_name, func.coalesce(func.sum(exp_uzs), 0))
            .select_from(Expense)
            .outerjoin(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
            .filter(*exp_flt)
            .group_by(cat_name)
            .all()
        )
    ]
    by_category.sort(key=lambda c: c["total"], reverse=True)

    net_profit = gross_profit + other_income - total_expenses

    return {
        "gross_revenue": round(gross_revenue, 2),
        "returns": round(returns, 2),
        "net_revenue": round(net_revenue, 2),
        "cogs": round(cogs, 2),
        "returns_cost": round(returns_cost, 2),
        "net_cogs": round(net_cogs, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin_pct": _pct(gross_profit, net_revenue),
        "other_income": other_income,
        "other_income_note": other_income_note,
        "expenses": {"total": round(total_expenses, 2), "by_category": by_category},
        "net_profit": round(net_profit, 2),
        "net_margin_pct": _pct(net_profit, net_revenue),
    }


def _check_count(db: Session, cid: int, start: datetime, end: datetime, branch_id: Optional[int]) -> int:
    """Davrdagi sotuv cheklari soni (qaytarish hujjatlari hisobga olinmaydi) — `compute_pnl` bilan bir xil filtr."""
    flt = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end, sale_doc_filter()]
    if branch_id:
        flt.append(sale_branch_filter(branch_id, db, cid))
    return int(db.query(func.count(Sale.id)).filter(*flt).scalar() or 0)


def compute_pnl_by_branch(
    db: Session, cid: int, start: datetime, end: datetime, allowed_branch_ids=None,
) -> list:
    """Korxonaning har bir filiali (nofaollari ham) va filialsiz guruh (-1) uchun P&L.

    Qaytaradi: [{"branch_id", "branch_name", "is_active", "check_count", "avg_check", **compute_pnl(...)}];
    oxirgi qator — filialsiz guruh (T2.5). `allowed_branch_ids` berilsa (cheklangan foydalanuvchi, T2.1) —
    faqat shu filiallar; filialsiz guruh qaytmaydi (korxona jami ochilib qolmasligi uchun)."""
    q = db.query(Branch.id, Branch.name, Branch.is_active).filter(Branch.company_id == cid)
    if allowed_branch_ids is not None:
        q = q.filter(Branch.id.in_(list(allowed_branch_ids)))
    entries = [(bid, name, active) for bid, name, active in q.order_by(Branch.id).all()]
    if allowed_branch_ids is None:
        entries.append((UNASSIGNED_BRANCH, None, None))
    result = []
    for bid, name, active in entries:
        checks = _check_count(db, cid, start, end, bid)
        pnl = compute_pnl(db, cid, start, end, bid)
        result.append({
            "branch_id": bid, "branch_name": name, "is_active": active,
            "check_count": checks,
            "avg_check": round(pnl["gross_revenue"] / checks, 2) if checks else 0.0,
            **pnl,
        })
    return result


_SUM_KEYS = ("gross_revenue", "returns", "net_revenue", "check_count", "cogs", "gross_profit",
             "expenses", "other_income", "net_profit")


def _summary_row(part: dict) -> dict:
    """`compute_pnl_by_branch` qatori -> tekis qator (xarajat — son)."""
    return {
        "branch_id": part["branch_id"],
        "branch_name": part["branch_name"],
        "is_active": part["is_active"],
        "gross_revenue": part["gross_revenue"],
        "returns": part["returns"],
        "net_revenue": part["net_revenue"],
        "check_count": part["check_count"],
        "avg_check": part["avg_check"],
        "cogs": part["net_cogs"],
        "gross_profit": part["gross_profit"],
        "gross_margin_pct": part["gross_margin_pct"],
        "expenses": part["expenses"]["total"],
        "other_income": part["other_income"],
        "net_profit": part["net_profit"],
        "net_margin_pct": part["net_margin_pct"],
    }


def build_branch_summary(
    db: Session, cid: int, start: datetime, end: datetime, allowed_branch_ids=None,
) -> dict:
    """Filiallar kesimidagi jamlanma (T2.5): `rows` (filiallar), `unassigned`, `total`, `reconciled`.

    `total` — qatorlar (filiallar + filialsiz) yig'indisi; `reconciled` — shu yig'indining
    `compute_pnl(branch_id=None)` (butun korxona) bilan mosligi (`abs(diff) < 0.01`).
    Cheklangan foydalanuvchida (`allowed_branch_ids` is not None) faqat o'z filiallari qatori qaytadi;
    `unassigned`, `total`, `reconciled` — None."""
    parts = compute_pnl_by_branch(db, cid, start, end, allowed_branch_ids)
    flat = [_summary_row(x) for x in parts]
    if allowed_branch_ids is not None:
        return {"rows": flat, "unassigned": None, "total": None, "reconciled": None}
    rows = [r for r in flat if r["branch_id"] != UNASSIGNED_BRANCH]
    unassigned = next(r for r in flat if r["branch_id"] == UNASSIGNED_BRANCH)

    total = {k: round(sum(r[k] for r in flat), 2) for k in _SUM_KEYS}
    total["check_count"] = int(total["check_count"])
    total["avg_check"] = round(total["gross_revenue"] / total["check_count"], 2) if total["check_count"] else 0.0
    total["gross_margin_pct"] = _pct(total["gross_profit"], total["net_revenue"])
    total["net_margin_pct"] = _pct(total["net_profit"], total["net_revenue"])
    total.update({"branch_id": None, "branch_name": None, "is_active": None})

    company = compute_pnl(db, cid, start, end, None)
    company_vals = {
        "gross_revenue": company["gross_revenue"], "returns": company["returns"],
        "net_revenue": company["net_revenue"], "cogs": company["net_cogs"],
        "gross_profit": company["gross_profit"], "expenses": company["expenses"]["total"],
        "other_income": company["other_income"], "net_profit": company["net_profit"],
    }
    reconciled = all(abs(total[k] - v) < 0.01 for k, v in company_vals.items())
    return {"rows": rows, "unassigned": unassigned, "total": total, "reconciled": reconciled}
