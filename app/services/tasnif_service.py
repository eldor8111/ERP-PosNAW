from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.mxik import MxikReference, MxikPackage, VatRateType

TASNIF_BASE_URL = "https://tasnif.soliq.uz/api/cl-api"


async def fetch_mxik_info(mxik_code: str, terminal_id: str, lang: str = "uz") -> dict:
    """tasnif.soliq.uz dan MXIK ma'lumotini olish (API 1)."""
    url = f"{TASNIF_BASE_URL}/integration-mxik/get/information"
    params = {
        "mxikCode":   mxik_code,
        "terminalId": terminal_id,
        "lang":       lang,
        "page":       0,
        "size":       25,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def fetch_vat_lgota(mxik_codes: list[str]) -> dict:
    """
    tasnif.soliq.uz API 2 — QQS lgota ma'lumotlari.
    POST /integration-mxik/references/set/lgotaxtasnif/vat
    Qaytaradi: {mxik_code: {withoutVat: [...], zeroVat: [...], ...}}
    """
    url = f"{TASNIF_BASE_URL}/integration-mxik/references/set/lgotaxtasnif/vat"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"tasnifCodes": mxik_codes})
        if resp.status_code == 400:
            return {}
        resp.raise_for_status()
        return resp.json()


def _parse_vat_rate_type_from_lgota(vat_info: Optional[dict]) -> Optional[VatRateType]:
    """
    API 2 javobidan QQS turini aniqlash.
    zeroVat bo'sh emas → zero (0% QQS)
    withoutVat bo'sh emas → exempt (lgota)
    ikkalasi bo'sh → None (API 1 lgotaId ga qarab aniqlanadi)
    """
    if not vat_info:
        return None
    if vat_info.get("zeroVat"):
        return VatRateType.zero
    if vat_info.get("withoutVat"):
        return VatRateType.exempt
    return VatRateType.standard


def _parse_vat_rate_type(lgota_id: Optional[int]) -> VatRateType:
    """API 1 lgotaId bo'yicha QQS turini aniqlash (fallback)."""
    if lgota_id is None:
        return VatRateType.standard
    return VatRateType.exempt


def upsert_mxik_reference(db: Session, data: dict, vat_info: Optional[dict] = None) -> MxikReference:
    """
    API 1 + API 2 javobini DB ga saqlash yoki yangilash.
    data     — API 1 javobidagi bitta mahsulot dict i
    vat_info — API 2 javobidan ushbu mxik_code uchun {withoutVat, zeroVat, ...}
    """
    mxik_code = data.get("mxikCode") or data.get("mxik")

    ref = db.query(MxikReference).filter(MxikReference.mxik_code == mxik_code).first()
    if not ref:
        ref = MxikReference(mxik_code=mxik_code)
        db.add(ref)

    ref.mxik_name          = data.get("mxikName") or data.get("name")
    ref.short_name         = data.get("shortName")
    ref.group_code         = data.get("groupCode")
    ref.group_name         = data.get("groupName")
    ref.class_code         = data.get("classCode")
    ref.class_name         = data.get("className")
    ref.position_code      = data.get("positionCode")
    ref.position_name      = data.get("positionName")
    ref.sub_position_code  = data.get("subPositionCode")
    ref.sub_position_name  = data.get("subPositionName")
    ref.brand_code         = data.get("brandCode")
    ref.brand_name         = data.get("brandName")
    ref.attribute_name     = data.get("attributeName")
    ref.international_code = data.get("internationalCode") or data.get("internalCode")
    ref.label              = int(data.get("label") or 0)
    ref.use_card           = int(data.get("useCard") or 0)

    # QQS: avval API 2 dan, bo'lmasa API 1 lgotaId dan
    vat_type_from_api2 = _parse_vat_rate_type_from_lgota(vat_info)
    if vat_type_from_api2 is not None:
        ref.vat_rate_type = vat_type_from_api2
        # lgota ma'lumotlarini API 2 dan olamiz
        without_vat = (vat_info or {}).get("withoutVat") or []
        if without_vat:
            ref.lgota_id   = without_vat[0].get("lgotaId")
            ref.lgota_name = without_vat[0].get("lgotaName")
        else:
            ref.lgota_id   = data.get("lgotaId")
            ref.lgota_name = data.get("lgotaName")
    else:
        ref.lgota_id      = data.get("lgotaId")
        ref.lgota_name    = data.get("lgotaName")
        ref.vat_rate_type = _parse_vat_rate_type(data.get("lgotaId"))

    ref.last_synced_at = datetime.now(timezone.utc)

    db.flush()

    # Paketlarni qayta yozish
    db.query(MxikPackage).filter(MxikPackage.mxik_reference_id == ref.id).delete()
    for pkg in data.get("packages") or []:
        db.add(MxikPackage(
            mxik_reference_id = ref.id,
            code              = pkg.get("code"),
            parent_code       = pkg.get("parentCode"),
            container_code    = pkg.get("containerCode"),
            container_name    = pkg.get("containerName"),
            unit_id           = pkg.get("unitId"),
            unit_name         = pkg.get("unitName"),
            parent_value      = pkg.get("parentValue"),
            name              = pkg.get("name"),
            type              = int(pkg["type"]) if pkg.get("type") else None,
            is_unit_package   = int(pkg["isUnitPackage"]) if pkg.get("isUnitPackage") else None,
        ))

    db.commit()
    db.refresh(ref)
    return ref


async def sync_mxik(
    db: Session,
    mxik_code: str,
    terminal_id: str,
    force_refresh: bool = False,
) -> MxikReference:
    """
    MXIK ma'lumotini DB dan qaytaradi.
    DB da yo'q bo'lsa yoki force_refresh=True bo'lsa, API 1 + API 2 dan oladi.
    """
    if not force_refresh:
        existing = db.query(MxikReference).filter(
            MxikReference.mxik_code == mxik_code
        ).first()
        if existing:
            return existing

    # API 1: asosiy ma'lumotlar
    response = await fetch_mxik_info(mxik_code, terminal_id)

    if response.get("data"):
        items = response["data"]
    elif response.get("content"):
        items = response["content"]
    else:
        items = [response]

    if not items:
        raise ValueError(f"MXIK {mxik_code} topilmadi")

    # API 2: QQS lgota ma'lumotlari (xato bo'lsa o'tkazib yuboramiz)
    vat_data: dict = {}
    try:
        vat_response = await fetch_vat_lgota([mxik_code])
        vat_data = vat_response.get(mxik_code) or {}
    except Exception:
        pass

    return upsert_mxik_reference(db, items[0], vat_info=vat_data or None)
