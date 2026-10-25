"""Dorixona ma'lumotnomalari (D2.1): ta'sir etuvchi moddalar.

Umumiy moddalar (company_id NULL) hamma dorixonaga ko'rinadi va o'zgarmaydi;
korxona o'z moddalarini qo'shishi, tahrirlashi va o'chirishi mumkin. Boshqa korxona moddasi ko'rinmaydi.
Barcha endpoint'lar faqat dorixona moduli yoqilgan korxonada ishlaydi.
"""
import re
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


# ── P.5: tasnif.soliq.uz dan dori topish — "Dori qo'shish" oynalarida nom, MXIK, ATX va boshqalarni avtomatik to'ldirish ──

_ATC_RE = re.compile(r"\b([A-Z]\d{2}[A-Z]{2}\d{2})\b")
_CYR_TO_LAT = str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX")   # ATX kodidagi kirillcha o'xshash harflar
_STRENGTH_RE = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:мкг|мг|г|мл|ме|%|mkg|mcg|mg|g|ml|me|iu)(?:\s*/\s*\d*(?:[.,]\d+)?\s*(?:мл|ml|доза|doza))?)(?![\w])",
    re.IGNORECASE,
)
# Kalit so'z -> dori shakli (matnda eng birinchi uchragani olinadi: "инъекция учун эритма" -> inyeksiya)
_FORM_WORDS = (
    ("таблет", "tablet"), ("tablet", "tablet"), ("драже", "tablet"),
    ("капсул", "capsule"), ("kapsul", "capsule"),
    ("сироп", "syrup"), ("sirop", "syrup"),
    ("томчи", "drops"), ("капли", "drops"), ("tomchi", "drops"),
    ("малҳам", "ointment"), ("малхам", "ointment"), ("мазь", "ointment"), ("malham", "ointment"), ("крем", "ointment"),
    ("инъекц", "injection"), ("ампул", "injection"), ("inyeksiya", "injection"),
    ("эритма", "solution"), ("раствор", "solution"), ("eritma", "solution"),
    ("кукун", "powder"), ("порош", "powder"), ("kukun", "powder"),
    ("суппозитор", "suppository"), ("свеч", "suppository"),
)


def _guess_form(text: str):
    low = (text or "").lower()
    best = None
    for word, key in _FORM_WORDS:
        i = low.find(word)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, key)
    return best[1] if best else None


def _substance_index(db: Session, company_id) -> dict:
    """Ko'rinadigan moddalar: nom (uz/ru/lotin, casefold) -> modda. Kirillcha registr Python'da (SQL lower() ga
    bog'liq emas); umumiy yozuv birinchi."""
    idx: dict = {}
    for s in _visible(db, company_id).order_by(PharmaSubstance.company_id.isnot(None), PharmaSubstance.id).all():
        for nm in (s.name_uz, s.name_ru, s.name_lat):
            if nm:
                idx.setdefault(" ".join(nm.split()).casefold(), s)
    return idx


def _substances_by_names(sub_index: dict, raw: str) -> list:
    """MNN matni ("эналаприл, гидрохлоротиазид") -> mavjud moddalar (nomi aynan mos; yangisi yaratilmaydi)."""
    out: list = []
    for part in re.split(r"[,+;/]", raw or ""):
        s = sub_index.get(" ".join(part.split()).casefold())
        if s is not None and all(x["id"] != s.id for x in out):
            out.append({"id": s.id, "name_uz": s.name_uz})
    return out


_PACK_RE = re.compile(r"№\s*(\d+)")
_MARKS_RE = re.compile(r"[®™©]")
_PARENS_RE = re.compile(r"\([^()]*\)")


def _top_level_head(text: str) -> str:
    """Qavs ichida bo'lmagan birinchi vergulgacha: 'BREND (ООО "X", Россия), Таблеткалар' -> 'BREND (ООО "X", Россия)'."""
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            return text[:i]
    return text


def _nice_case(text: str) -> str:
    """Faqat katta harfli so'zlar (4+ harf) bosh harf bilan: ЦИПРОФЛОКСАЦИН-АДЖИО -> Ципрофлоксацин-Аджио.
    Qisqa (АЦЦ, НО-ШПА), aralash registrli va raqamli qismlar o'zgarmaydi."""
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0)[0] + m.group(0)[1:].lower()
                  if len(m.group(0)) >= 4 and m.group(0).isupper() else m.group(0), text)


def short_drug_name(name, brand=None, attribute=None):
    """Tasnif nomidan qisqa tovar nomi: brend + doza + qadoqdagi soni.
    'Ципрофлоксацин - J01MA02: ЦИПРОФЛОКСАЦИН-АДЖИО (Agio Pharmaceuticals), Таблеткалар, плёнка билан қопланган
    500 мг блистерлар №100(10x10)' -> 'Ципрофлоксацин-Аджио 500 мг №100'.
    Brend ajratilmasa (nom tasnif dori ko'rinishida emas) — None: to'liq nom ishlatiladi."""
    full = " ".join(str(name or "").split())
    base = (brand or "").strip()
    if not base and ":" in full:
        base = _top_level_head(full.split(":", 1)[1])
    base = " ".join(_PARENS_RE.sub(" ", _MARKS_RE.sub("", base)).split()).strip(" -–—:;,")
    if not base:
        return None
    out = _nice_case(base)
    st = _STRENGTH_RE.search(attribute or "") or _STRENGTH_RE.search(full)
    if st:
        dose = " ".join(st.group(1).split())
        num = re.match(r"[\d.,]+", dose).group(0)
        if dose.replace(" ", "").casefold() in out.replace(" ", "").casefold():
            pass
        elif re.search(rf"(?<![\d.,]){re.escape(num)}$", out):   # 'АЦЦ 200' + '200 мг' -> 'АЦЦ 200 мг'
            out += dose[len(num):]
        else:
            out += " " + dose
    pk = _PACK_RE.search(attribute or "") or _PACK_RE.search(full)
    if pk and f"№{pk.group(1)}" not in out.replace(" ", ""):
        out += f" №{pk.group(1)}"
    return out[:200]


def _drug_out(sub_index: dict, *, name, mxik_code, barcode, brand=None, attribute=None, mnn=None,
              source="tasnif") -> dict:
    name = " ".join(str(name or "").split())
    text = f"{name} {attribute or ''}"
    atc = _ATC_RE.search(name.upper().translate(_CYR_TO_LAT))
    # Ishlab chiqaruvchi: brend oxiridagi qavs ichida ("СУЛЬФАЦИЛ (Фармак)"); brend bo'lmasa — nomdagi "...: BREND (X)," qismi
    brand_part = (brand or "").strip() or (name.split(":", 1)[1].split(",", 1)[0] if ":" in name else "")
    m_brand = re.search(r"\(([^()]+)\)\s*$", brand_part.strip())
    strength = _STRENGTH_RE.search(attribute or "") or _STRENGTH_RE.search(name)
    return {
        "name": name,
        "short_name": short_drug_name(name, brand, attribute),   # kassa va ro'yxat uchun qisqa nom
        "mxik_code": str(mxik_code or "").strip() or None,
        "barcode": str(barcode or "").strip() or None,
        "atc_code": atc.group(1) if atc else None,
        "manufacturer": m_brand.group(1).strip() if m_brand else None,
        "dosage_form": _guess_form(text),
        "strength": " ".join(strength.group(1).split()) if strength else None,
        "substance_name": (mnn or "").strip() or None,
        "substances": _substances_by_names(sub_index, mnn or ""),
        "source": source,
    }


def _from_tasnif_item(sub_index: dict, it: dict) -> dict:
    return _drug_out(sub_index, name=it.get("name"), mxik_code=it.get("mxikCode"),
                     barcode=it.get("internationalCode"), brand=it.get("brandName"),
                     attribute=it.get("attributeName"), mnn=it.get("mnnName"))


def _tasnif_search(text: str, size: int) -> list:
    from app.services import tasnif_service
    try:
        return tasnif_service.tasnif_search_sync(text, size=size)
    except Exception:
        raise HTTPException(status_code=502, detail="Tasnif (soliq.uz) bilan bog'lanib bo'lmadi — keyinroq urinib ko'ring")


@router.get("/tasnif/search")
def tasnif_search(
        q: str = Query(..., min_length=2, max_length=100, description="Dori nomi yoki shtrix-kod"),
        limit: int = Query(10, ge=1, le=20),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Dorini tasnif.soliq.uz dan nom (yoki shtrix-kod) bo'yicha qidirish: nom, MXIK, ATX, ishlab chiqaruvchi, shakl, doza."""
    items = _tasnif_search(q.strip(), limit)
    idx = _substance_index(db, current_user.company_id)
    return [_from_tasnif_item(idx, it) for it in items[:limit] if it.get("mxikCode")]


@router.get("/tasnif/barcode/{barcode}")
def tasnif_by_barcode(
        barcode: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Shtrix-kod bo'yicha: avval mahalliy katalog, keyin tasnif (faqat aynan mos shtrix-kod). Topilsa katalogga yoziladi."""
    from app.models.tovarlar_catalog import TovarlarCatalog
    code = barcode.strip()
    if not code or len(code) > 30:
        raise HTTPException(status_code=400, detail="Shtrix-kod noto'g'ri")
    cat = db.query(TovarlarCatalog).filter(TovarlarCatalog.barcode == code).first()
    if cat is not None and cat.mxik_code:
        return _drug_out(_substance_index(db, current_user.company_id), name=cat.mxik_name, mxik_code=cat.mxik_code, barcode=code,
                         attribute=cat.attribute_name, source="catalog")
    hit = next((it for it in _tasnif_search(code, 20)
                if str(it.get("internationalCode") or "").strip() == code and it.get("mxikCode")), None)
    if hit is None:
        raise HTTPException(status_code=404, detail="Shtrix-kod tasnifda topilmadi — dori nomi bo'yicha qidiring")
    sp = db.begin_nested()   # keyingi safar (va Excel importida) mahalliy katalogdan topilsin
    try:
        if cat is None:
            db.add(TovarlarCatalog(
                barcode=code, mxik_code=str(hit["mxikCode"])[:30], mxik_name=hit.get("name"),
                unit_name=(hit.get("unitsName") or None) and str(hit.get("unitsName"))[:200],
                group_name=hit.get("groupName"), attribute_name=hit.get("attributeName"),
            ))
            db.flush()
        sp.commit()
        db.commit()
    except Exception:
        sp.rollback()
    return _from_tasnif_item(_substance_index(db, current_user.company_id), hit)


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
