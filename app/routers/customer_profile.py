"""
Mijoz profili: rasm, hujjatlar (shartnoma/litsenziya/pasport) va Telegram
orqali joylashuv so'rash.

Rasm ochiq /static da (sahifada ko'rsatiladi). Hujjatlar esa shaxsiy
ma'lumot — uploads_private/ ga saqlanadi va faqat shu kompaniya
xodimiga avtorizatsiyali endpoint orqali beriladi.
"""
import os
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.company import Company
from app.models.customer import Customer
from app.models.customer_document import CustomerDocument
from app.models.user import User

router = APIRouter(prefix="/customers", tags=["customers"])

PHOTO_DIR = "static/uploads/customers"
PRIVATE_ROOT = "uploads_private"
DOC_DIR = os.path.join(PRIVATE_ROOT, "customer_docs")

PHOTO_MAX = 5 * 1024 * 1024
DOC_MAX = 10 * 1024 * 1024
MAX_DOCS_PER_CUSTOMER = 20

# Kengaytma content_type/magic bytes'dan olinadi — foydalanuvchi fayl nomiga ishonilmaydi
IMAGE_SIGNATURES = {
    "jpg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),
}
DOC_TYPES = {
    "application/pdf": ("pdf", (b"%PDF",)),
    "image/jpeg": ("jpg", (b"\xff\xd8\xff",)),
    "image/png": ("png", (b"\x89PNG\r\n\x1a\n",)),
    "image/webp": ("webp", (b"RIFF",)),
    # docx/xlsx — zip konteyner
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("docx", (b"PK\x03\x04",)),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("xlsx", (b"PK\x03\x04",)),
    "application/msword": ("doc", (b"\xd0\xcf\x11\xe0",)),
}


def _get_customer(db: Session, customer_id: int, user: User) -> Customer:
    c = db.query(Customer).filter(Customer.id == customer_id, Customer.company_id == user.company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    return c


def _image_ext(content: bytes) -> str:
    for ext, sigs in IMAGE_SIGNATURES.items():
        if any(content.startswith(s) for s in sigs):
            if ext == "webp" and content[8:12] != b"WEBP":
                continue
            return ext
    raise HTTPException(status_code=400, detail="Faqat JPG, PNG yoki WEBP rasm qabul qilinadi")


def _remove_static_photo(url: str) -> None:
    if url and url.startswith("/static/uploads/customers/"):
        path = url.lstrip("/")
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


# ── Rasm ────────────────────────────────────────────────────────────────────

@router.post("/{customer_id}/photo")
async def upload_customer_photo(customer_id: int, file: UploadFile = File(...),
                                db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cust = _get_customer(db, customer_id, current_user)
    content = await file.read(PHOTO_MAX + 1)
    if len(content) > PHOTO_MAX:
        raise HTTPException(status_code=400, detail="Rasm hajmi 5 MB dan oshmasligi kerak")
    ext = _image_ext(content)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(PHOTO_DIR, filename), "wb") as f:
        f.write(content)
    _remove_static_photo(cust.photo_url)
    cust.photo_url = f"/static/uploads/customers/{filename}"
    db.commit()
    return {"photo_url": cust.photo_url}


@router.delete("/{customer_id}/photo")
def delete_customer_photo(customer_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    cust = _get_customer(db, customer_id, current_user)
    _remove_static_photo(cust.photo_url)
    cust.photo_url = None
    db.commit()
    return {"ok": True}


# ── Hujjatlar ───────────────────────────────────────────────────────────────

def _doc_out(d: CustomerDocument) -> dict:
    return {
        "id": d.id,
        "original_name": d.original_name,
        "content_type": d.content_type,
        "size": d.size,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@router.get("/{customer_id}/documents")
def list_customer_documents(customer_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    _get_customer(db, customer_id, current_user)
    docs = db.query(CustomerDocument).filter(
        CustomerDocument.customer_id == customer_id,
        CustomerDocument.company_id == current_user.company_id,
    ).order_by(CustomerDocument.created_at.desc()).all()
    return [_doc_out(d) for d in docs]


@router.post("/{customer_id}/documents", status_code=201)
async def upload_customer_document(customer_id: int, file: UploadFile = File(...),
                                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _get_customer(db, customer_id, current_user)
    count = db.query(CustomerDocument).filter(CustomerDocument.customer_id == customer_id).count()
    if count >= MAX_DOCS_PER_CUSTOMER:
        raise HTTPException(status_code=400, detail=f"Bitta mijozga ko'pi bilan {MAX_DOCS_PER_CUSTOMER} ta hujjat")

    spec = DOC_TYPES.get(file.content_type or "")
    if not spec:
        raise HTTPException(status_code=400, detail="Faqat PDF, rasm (JPG/PNG/WEBP) yoki Word/Excel hujjat qabul qilinadi")
    content = await file.read(DOC_MAX + 1)
    if len(content) > DOC_MAX:
        raise HTTPException(status_code=400, detail="Hujjat hajmi 10 MB dan oshmasligi kerak")
    ext, sigs = spec
    if not any(content.startswith(s) for s in sigs):
        raise HTTPException(status_code=400, detail="Fayl mazmuni turiga mos emas")

    rel_dir = os.path.join(str(current_user.company_id), str(customer_id))
    os.makedirs(os.path.join(DOC_DIR, rel_dir), exist_ok=True)
    rel_path = os.path.join(rel_dir, f"{uuid.uuid4().hex}.{ext}")
    with open(os.path.join(DOC_DIR, rel_path), "wb") as f:
        f.write(content)

    original = os.path.basename(file.filename or f"hujjat.{ext}")[:255]
    doc = CustomerDocument(
        customer_id=customer_id,
        company_id=current_user.company_id,
        file_path=rel_path.replace("\\", "/"),
        original_name=original,
        content_type=file.content_type,
        size=len(content),
        uploaded_by=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


def _get_doc(db: Session, customer_id: int, doc_id: int, user: User) -> CustomerDocument:
    doc = db.query(CustomerDocument).filter(
        CustomerDocument.id == doc_id,
        CustomerDocument.customer_id == customer_id,
        CustomerDocument.company_id == user.company_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Hujjat topilmadi")
    return doc


def _safe_doc_path(rel_path: str) -> str:
    base = os.path.realpath(DOC_DIR)
    full = os.path.realpath(os.path.join(base, rel_path))
    if not full.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Noto'g'ri fayl yo'li")
    return full


@router.get("/{customer_id}/documents/{doc_id}/file")
def download_customer_document(customer_id: int, doc_id: int, db: Session = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    doc = _get_doc(db, customer_id, doc_id, current_user)
    path = _safe_doc_path(doc.file_path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Fayl topilmadi")
    # attachment — brauzer faylni sahifa sifatida bajarmasligi uchun
    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.original_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{customer_id}/documents/{doc_id}", status_code=204)
def delete_customer_document(customer_id: int, doc_id: int, db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    doc = _get_doc(db, customer_id, doc_id, current_user)
    path = _safe_doc_path(doc.file_path)
    db.delete(doc)
    db.commit()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ── Telegram orqali joylashuv so'rash ───────────────────────────────────────

@router.post("/{customer_id}/request-location")
def request_customer_location(customer_id: int, db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Mijozga botdan "📍 Joylashuvni yuborish" tugmali xabar yuboradi.
    Mijoz tugmani bossa, webhook (telegram.py) lat/lng ni saqlaydi."""
    import requests

    cust = _get_customer(db, customer_id, current_user)
    if not cust.tg_chat_id:
        raise HTTPException(status_code=400, detail="Mijoz Telegram botga ulanmagan")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company or not company.tg_bot_token:
        raise HTTPException(status_code=400, detail="Kompaniyaning Telegram boti sozlanmagan")

    text = (
        f"📍 <b>{company.name}</b> yetkazib berish uchun joylashuvingizni so'ramoqda.\n\n"
        "Pastdagi tugmani bosing yoki 📎 → Joylashuv orqali kerakli nuqtani yuboring."
    )
    markup = {
        "keyboard": [[{"text": "📍 Joylashuvni yuborish", "request_location": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{company.tg_bot_token}/sendMessage",
            json={"chat_id": cust.tg_chat_id, "text": text, "parse_mode": "HTML", "reply_markup": markup},
            timeout=10,
        )
        ok = r.ok and r.json().get("ok")
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=502, detail="Telegramga xabar yuborib bo'lmadi (mijoz botni bloklagan bo'lishi mumkin)")
    return {"message": "So'rov yuborildi. Mijoz joylashuvni yuborgach, u avtomatik saqlanadi."}
