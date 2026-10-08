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
}


def company_has_feature(db: Session, company_id, feature: str) -> bool:
    column, _ = FEATURES[feature]
    if not company_id:
        return False
    row = db.query(getattr(Company, column)).filter(Company.id == company_id).first()
    return bool(row and row[0])


def require_feature(feature: str):
    _, title = FEATURES[feature]

    def _dep(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
        if not company_has_feature(db, current_user.company_id, feature):
            raise HTTPException(
                status_code=403,
                detail=f"\"{title}\" moduli kompaniyangiz uchun yoqilmagan (Sozlamalar → Umumiy)",
            )
    return _dep
