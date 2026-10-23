"""Dorixona ma'lumotnomalari (D2.1): ta'sir etuvchi moddalar.

Umumiy moddalar (company_id NULL) hamma dorixonaga ko'rinadi va o'zgarmaydi;
korxona o'z moddalarini qo'shishi, tahrirlashi va o'chirishi mumkin. Boshqa korxona moddasi ko'rinmaydi.
Barcha endpoint'lar faqat dorixona moduli yoqilgan korxonada ishlaydi.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.product_pharma import PharmaSubstance, ProductSubstance
from app.models.user import User, UserRole

router = APIRouter(
    prefix="/pharmacy", tags=["Pharmacy"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


class SubstanceIn(BaseModel):
    name_uz: str = Field(..., max_length=200)
    name_ru: Optional[str] = Field(None, max_length=200)
    name_lat: Optional[str] = Field(None, max_length=200)

    @field_validator("name_uz")
    @classmethod
    def name_required(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Modda nomi (o'zbekcha) majburiy")
        return v

    @field_validator("name_ru", "name_lat")
    @classmethod
    def blank_to_none(cls, v):
        v = (v or "").strip()
        return v or None


class SubstanceOut(BaseModel):
    id: int
    name_uz: str
    name_ru: Optional[str] = None
    name_lat: Optional[str] = None
    company_id: Optional[int] = None
    is_common: bool = False  # True = umumiy ma'lumotnoma yozuvi (o'zgartirib bo'lmaydi)


def _out(s: PharmaSubstance) -> SubstanceOut:
    return SubstanceOut(
        id=s.id, name_uz=s.name_uz, name_ru=s.name_ru, name_lat=s.name_lat,
        company_id=s.company_id, is_common=s.company_id is None,
    )


def _visible(db: Session, company_id):
    """Umumiy + o'z korxonasi moddalari."""
    return db.query(PharmaSubstance).filter(
        or_(PharmaSubstance.company_id.is_(None), PharmaSubstance.company_id == company_id)
    )


def _own_or_error(db: Session, substance_id: int, company_id) -> PharmaSubstance:
    """Faqat o'z korxonasi moddasi: begona/yo'q — 404, umumiy — 403."""
    s = db.query(PharmaSubstance).filter(PharmaSubstance.id == substance_id).first()
    if s is None or (s.company_id is not None and s.company_id != company_id):
        raise HTTPException(status_code=404, detail="Modda topilmadi")
    if s.company_id is None:
        raise HTTPException(status_code=403, detail="Umumiy ma'lumotnoma moddasini o'zgartirib bo'lmaydi")
    return s


def _check_duplicate(db: Session, company_id, name_uz: str, exclude_id: Optional[int] = None) -> None:
    q = _visible(db, company_id).filter(func.lower(PharmaSubstance.name_uz) == name_uz.lower())
    if exclude_id:
        q = q.filter(PharmaSubstance.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=400, detail=f"'{name_uz}' nomli modda allaqachon mavjud")


@router.get("/substances", response_model=List[SubstanceOut])
def list_substances(
        search: Optional[str] = Query(None, description="Nomi (uz/ru/lotin) bo'yicha qidiruv"),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    q = _visible(db, current_user.company_id)
    term = (search or "").strip()
    if term:
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        q = q.filter(or_(
            PharmaSubstance.name_uz.ilike(like, escape="\\"),
            PharmaSubstance.name_ru.ilike(like, escape="\\"),
            PharmaSubstance.name_lat.ilike(like, escape="\\"),
        ))
    rows = q.order_by(PharmaSubstance.name_uz, PharmaSubstance.id).offset(skip).limit(limit).all()
    return [_out(s) for s in rows]


@router.post("/substances", response_model=SubstanceOut, status_code=status.HTTP_201_CREATED)
def create_substance(
        data: SubstanceIn,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    _check_duplicate(db, current_user.company_id, data.name_uz)
    s = PharmaSubstance(
        company_id=current_user.company_id,
        name_uz=data.name_uz, name_ru=data.name_ru, name_lat=data.name_lat,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _out(s)


@router.put("/substances/{substance_id}", response_model=SubstanceOut)
def update_substance(
        substance_id: int,
        data: SubstanceIn,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    s = _own_or_error(db, substance_id, current_user.company_id)
    _check_duplicate(db, current_user.company_id, data.name_uz, exclude_id=s.id)
    s.name_uz, s.name_ru, s.name_lat = data.name_uz, data.name_ru, data.name_lat
    db.commit()
    db.refresh(s)
    return _out(s)


@router.delete("/substances/{substance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_substance(
        substance_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    s = _own_or_error(db, substance_id, current_user.company_id)
    used = db.query(func.count(ProductSubstance.id)).filter(ProductSubstance.substance_id == s.id).scalar() or 0
    if used:
        raise HTTPException(status_code=409, detail=f"Modda {used} ta mahsulotda ishlatilmoqda — avval bog'lanishni olib tashlang")
    db.delete(s)
    db.commit()


# Eng ko'p uchraydigan 50 ta ta'sir etuvchi modda: (o'zbekcha, ruscha, lotincha)
COMMON_SUBSTANCES = [
    ("Paratsetamol", "Парацетамол", "Paracetamolum"),
    ("Ibuprofen", "Ибупрофен", "Ibuprofenum"),
    ("Amoksitsillin", "Амоксициллин", "Amoxicillinum"),
    ("Aspirin (atsetilsalitsil kislota)", "Ацетилсалициловая кислота", "Acidum acetylsalicylicum"),
    ("Diklofenak", "Диклофенак", "Diclofenacum"),
    ("Nimesulid", "Нимесулид", "Nimesulidum"),
    ("Ketorolak", "Кеторолак", "Ketorolacum"),
    ("Analgin (metamizol natriy)", "Метамизол натрия", "Metamizolum natrium"),
    ("Drotaverin", "Дротаверин", "Drotaverinum"),
    ("Azitromitsin", "Азитромицин", "Azithromycinum"),
    ("Siprofloksasin", "Ципрофлоксацин", "Ciprofloxacinum"),
    ("Seftriakson", "Цефтриаксон", "Ceftriaxonum"),
    ("Sefaleksin", "Цефалексин", "Cefalexinum"),
    ("Doksitsiklin", "Доксициклин", "Doxycyclinum"),
    ("Metronidazol", "Метронидазол", "Metronidazolum"),
    ("Flukonazol", "Флуконазол", "Fluconazolum"),
    ("Omeprazol", "Омепразол", "Omeprazolum"),
    ("Pantoprazol", "Пантопразол", "Pantoprazolum"),
    ("Ranitidin", "Ранитидин", "Ranitidinum"),
    ("Loperamid", "Лоперамид", "Loperamidum"),
    ("Aktivlangan ko'mir", "Активированный уголь", "Carbo activatus"),
    ("Metoklopramid", "Метоклопрамид", "Metoclopramidum"),
    ("Loratadin", "Лоратадин", "Loratadinum"),
    ("Setirizin", "Цетиризин", "Cetirizinum"),
    ("Xlorpiramin", "Хлоропирамин", "Chloropyraminum"),
    ("Deksametazon", "Дексаметазон", "Dexamethasonum"),
    ("Prednizolon", "Преднизолон", "Prednisolonum"),
    ("Salbutamol", "Сальбутамол", "Salbutamolum"),
    ("Ambroksol", "Амброксол", "Ambroxolum"),
    ("Asetilsistein", "Ацетилцистеин", "Acetylcysteinum"),
    ("Bromgeksin", "Бромгексин", "Bromhexinum"),
    ("Ksilometazolin", "Ксилометазолин", "Xylometazolinum"),
    ("Enalapril", "Эналаприл", "Enalaprilum"),
    ("Lizinopril", "Лизиноприл", "Lisinoprilum"),
    ("Amlodipin", "Амлодипин", "Amlodipinum"),
    ("Metoprolol", "Метопролол", "Metoprololum"),
    ("Bisoprolol", "Бисопролол", "Bisoprololum"),
    ("Losartan", "Лозартан", "Losartanum"),
    ("Furosemid", "Фуросемид", "Furosemidum"),
    ("Atorvastatin", "Аторвастатин", "Atorvastatinum"),
    ("Klopidogrel", "Клопидогрел", "Clopidogrelum"),
    ("Metformin", "Метформин", "Metforminum"),
    ("Glibenklamid", "Глибенкламид", "Glibenclamidum"),
    ("Levotiroksin natriy", "Левотироксин натрия", "Levothyroxinum natrium"),
    ("Askorbin kislota (vitamin C)", "Аскорбиновая кислота", "Acidum ascorbicum"),
    ("Kolekalsiferol (vitamin D3)", "Колекальциферол", "Colecalciferolum"),
    ("Folat kislota", "Фолиевая кислота", "Acidum folicum"),
    ("Temir sulfat", "Железа сульфат", "Ferrosi sulfas"),
    ("Kalsiy glyukonat", "Кальция глюконат", "Calcii gluconas"),
    ("Magniy sulfat", "Магния сульфат", "Magnesii sulfas"),
]


def seed_pharma_substances() -> int:
    """Boshlang'ich umumiy moddalarni qo'shadi (idempotent: lotincha nomi bo'yicha bor bo'lsa tegmaydi).
    Startup'da chaqiriladi; xato bo'lsa ishga tushishni to'xtatmaydi. Qo'shilganlar sonini qaytaradi."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        existing = {
            (lat or "").lower()
            for (lat,) in db.query(PharmaSubstance.name_lat).filter(PharmaSubstance.company_id.is_(None)).all()
        }
        added = 0
        for uz, ru, lat in COMMON_SUBSTANCES:
            if lat.lower() in existing:
                continue
            db.add(PharmaSubstance(company_id=None, name_uz=uz, name_ru=ru, name_lat=lat))
            added += 1
        if added:
            db.commit()
        return added
    except Exception as e:  # jadval hali yo'q yoki parallel worker allaqachon qo'shgan bo'lishi mumkin
        db.rollback()
        print(f"[PHARMACY-SEED] skip: {e}")
        return 0
    finally:
        db.close()
