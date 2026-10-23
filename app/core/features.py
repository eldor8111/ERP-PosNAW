"""Kompaniya darajasidagi ixtiyoriy modullar (Company.*_enabled).

Router'ga dependency sifatida qo'yiladi — modul o'chiq kompaniya uchun API
yopiq bo'ladi (faqat sidebar'da yashirish yetarli emas).
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.company import Company
from app.models.user import User

FEATURES = {
    "manufacturing": ("manufacturing_enabled", "Ishlab chiqarish"),
    "distribution": ("distribution_enabled", "Distribyutorlar va logistika"),
    "marketplace_agents": ("marketplace_agents_enabled", "Marketplace agentlari"),
    "delivery_automation": ("orders_auto_create_sale", "Yetkazib berish avtomatikasi"),
    "pharmacy": ("pharmacy_enabled", "Dorixona"),
}


def company_has_feature(db: Session, company_id, feature: str) -> bool:
    if feature not in FEATURES or not company_id:
        return False
    column, _ = FEATURES[feature]
    try:
        from datetime import datetime, timezone
        from app.models.billing import CompanyPackage
        from app.models.company import Company
        now = datetime.now(timezone.utc)

        comp = db.query(Company).filter(Company.id == company_id).first()
        if not comp:
            return False

        col_val = bool(getattr(comp, column, False))
        if not col_val:
            return False

        if feature == "marketplace_agents":
            return col_val

        # Tarifda kiritilganmi?
        if comp.tariff and getattr(comp.tariff, f"has_{feature}", False):
            return True

        # Paket tekshiruvi (obuna yoki 7 kunlik sinov)
        pkgs = db.query(CompanyPackage).filter(
            CompanyPackage.company_id == company_id,
            CompanyPackage.package_code == feature,
        ).order_by(CompanyPackage.ends_at.desc()).all()

        if pkgs:
            for p in pkgs:
                ends_at = p.ends_at
                if ends_at and ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=timezone.utc)
                if p.is_active and ends_at and ends_at > now:
                    return True
            # Barcha paketlar muddati tugagan va tarifda ham yo'q
            return False

        return col_val
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False


def get_active_features(db: Session, company_id) -> list[str]:
    active = []
    for feat in FEATURES:
        if company_has_feature(db, company_id, feat):
            active.append(feat)
    return active


def require_feature(feature: str):
    _, title = FEATURES[feature]

    def _dep(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
        if not company_has_feature(db, current_user.company_id, feature):
            raise HTTPException(
                status_code=403,
                detail=f"\"{title}\" moduli kompaniyangiz uchun yoqilmagan (Sozlamalar → Umumiy)",
            )
    return _dep
