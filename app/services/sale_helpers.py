from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sale import Sale
import logging
import os
import requests

_logger = logging.getLogger(__name__)


def generate_sale_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"S{today}"
    max_num_str = (
        db.query(func.max(Sale.number))
        .filter(Sale.number.like(f"{prefix}%"))
        .scalar()
    )
    if max_num_str:
        try:
            last_num = int(max_num_str[len(prefix):])
        except (ValueError, IndexError):
            last_num = 0
    else:
        last_num = 0
    return f"{prefix}{last_num + 1:04d}"


def generate_return_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"R{today}"
    max_num_str = (
        db.query(func.max(Sale.number))
        .filter(Sale.number.like(f"{prefix}%"))
        .scalar()
    )
    if max_num_str:
        try:
            last_num = int(max_num_str[len(prefix):])
        except (ValueError, IndexError):
            last_num = 0
    else:
        last_num = 0
    return f"{prefix}{last_num + 1:04d}"


def send_tg_sync(token, chat_id, text, filepath=None):
    try:
        if filepath and os.path.exists(filepath):
            with open(filepath, "rb") as doc:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
                    files={"document": doc},
                    timeout=10
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5
            )
    except Exception as e:
        _logger.error("[TG] Telegram xabarnomasi yuborishda xato: %s", e)


def resolve_price(item_data, product, customer_price, customer=None):
    """Narx prioriteti: frontend > individual narx > price_type > sale_price."""
    price_type = "sale"
    if customer:
        price_type = getattr(customer, "price_type", "sale") or "sale"

    if item_data.unit_price is not None:
        return item_data.unit_price
    if customer_price:
        return customer_price.price
    if price_type == "wholesale":
        return product.wholesale_price or product.sale_price
    if price_type == "cost":
        return product.cost_price or product.sale_price
    return product.sale_price


def resolve_branch_id(db, current_user, warehouse_id=None):
    """Tranzaksiya uchun branch_id topish."""
    tx_branch_id = current_user.branch_id
    if not tx_branch_id and warehouse_id:
        from app.models.warehouse import Warehouse
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if wh and wh.branch_id:
            tx_branch_id = wh.branch_id
    if not tx_branch_id:
        from app.models.branch import Branch
        br = db.query(Branch).filter(Branch.company_id == current_user.company_id).first()
        if br:
            tx_branch_id = br.id
    return tx_branch_id
