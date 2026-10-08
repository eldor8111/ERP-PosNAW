"""Marketplace (mir-maza.uz) integratsiyasi: kategoriyalar sinxronizatsiyasi.

Manba URL .env dagi MARKETPLACE_CATEGORIES_URL orqali beriladi. Javob
[{id, name, parent_id}, ...] yoki {"results"|"data"|"categories": [...]}
ko'rinishida bo'lishi mumkin. Manba ishlamasa — oxirgi muvaffaqiyatli kesh
qaytariladi (marketplace vaqtincha o'chiq bo'lsa ham agentlar ishlayveradi).
"""
import logging
import threading
import time
from typing import Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Dict[str, object] = {"items": [], "ts": 0.0}


def _normalize(raw) -> List[dict]:
    if isinstance(raw, dict):
        for key in ("results", "data", "categories", "items"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        return []
    out = []
    for c in raw:
        if not isinstance(c, dict) or c.get("id") is None:
            continue
        try:
            cid = int(c["id"])
        except (TypeError, ValueError):
            continue
        parent = c.get("parent_id", c.get("parent"))
        if isinstance(parent, dict):
            parent = parent.get("id")
        try:
            parent = int(parent) if parent not in (None, "", 0) else None
        except (TypeError, ValueError):
            parent = None
        name = c.get("name") or c.get("title") or c.get("name_uz") or f"#{cid}"
        out.append({"id": cid, "name": str(name)[:200], "parent_id": parent})
    return out


def fetch_categories(force: bool = False) -> List[dict]:
    """Kategoriyalar ro'yxati (kesh TTL — MARKETPLACE_CATEGORIES_TTL)."""
    now = time.time()
    with _lock:
        fresh = _cache["items"] and (now - float(_cache["ts"])) < settings.MARKETPLACE_CATEGORIES_TTL
        if fresh and not force:
            return list(_cache["items"])  # type: ignore[arg-type]

    url = settings.MARKETPLACE_CATEGORIES_URL
    if not url:
        return list(_cache["items"])  # type: ignore[arg-type]
    headers = {"Accept": "application/json"}
    if settings.MARKETPLACE_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.MARKETPLACE_API_TOKEN}"
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        items = _normalize(resp.json())
        if items:
            with _lock:
                _cache["items"], _cache["ts"] = items, now
            return list(items)
    except Exception as e:  # noqa: BLE001 — tashqi tizim xatosi agentlarni to'xtatmasin
        logger.warning("mir-maza kategoriyalarini olib bo'lmadi: %s", e)
    return list(_cache["items"])  # type: ignore[arg-type]


def category_ids() -> set:
    return {c["id"] for c in fetch_categories()}


def category_name_map() -> Dict[int, str]:
    return {c["id"]: c["name"] for c in fetch_categories()}


def normalize_phone(phone: str) -> str:
    return phone.strip().replace("+", "").replace(" ", "").replace("-", "")


def clamp_images(images: Optional[list], limit: int = 8) -> list:
    return [str(i)[:500] for i in (images or []) if i][:limit]
