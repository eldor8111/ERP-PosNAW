import os
import uuid

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.database import engine
from app.utils import image_pipeline as ip

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB

router = APIRouter(prefix="/uploads", tags=["Uploads"])

# Rasmni qayta kodlash CPU va xotira oladi: har worker'da bir vaqtda bittadan
# (umumiy threadpool band bo'lmaydi, ko'p rasm kelsa ham boshqa so'rovlar kutmaydi)
_image_limiter = None


def _limiter():
    global _image_limiter
    if _image_limiter is None:
        _image_limiter = anyio.CapacityLimiter(1)
    return _image_limiter


def _bind():
    return engine


def _store(content: bytes) -> str:
    """Rasmni siqib saqlaydi (har doim JPEG), fayl nomini qaytaradi. Buzuq rasmda ValueError."""
    data = ip.compress_upload(content)
    os.makedirs(ip.UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    with open(ip.upload_path(name), "wb") as f:
        f.write(data)
    return name


def _company_id(user):
    cid = getattr(user, "company_id", None)
    if not cid:
        raise ip.QueueError("Kompaniya tanlanmagan")
    return cid


def _enqueue(user, orig: str) -> dict:
    if not ip.bg_enabled():
        raise ip.QueueError("Orqa fonni olib tashlash serverda yoqilmagan")
    return ip.enqueue(_bind(), _company_id(user), getattr(user, "id", None), orig)


def _parse_or_400(url: str):
    parsed = ip.parse_upload_url(url)
    if not parsed:
        raise HTTPException(status_code=400, detail="Faqat tizimga yuklangan rasmlarning fonini olib tashlash mumkin")
    return parsed[0]


@router.get("/capabilities")
def upload_capabilities(current_user=Depends(get_current_user)):
    """Frontend "Orqa fonni olib tashlash" katagini faqat ishchi xizmat ishlayotgan bo'lsa ko'rsatadi."""
    return {"remove_background": ip.is_available()}


@router.post("/product-image")
async def upload_product_image(
    file: UploadFile = File(...),
    remove_bg: bool = Query(False, description="Orqa fonni olib tashlash uchun navbatga qo'yish"),
    current_user=Depends(get_current_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Faqat JPG, PNG, WEBP, GIF rasm formatlari qabul qilinadi",
        )

    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Fayl hajmi 5 MB dan oshmasligi kerak",
        )

    # Har bir rasm siqiladi (eng uzun tomoni 1280 px, JPEG) — fayl nomi bizniki, kengaytma doim .jpg
    try:
        filename = await anyio.to_thread.run_sync(_store, content, limiter=_limiter())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    url = ip.URL_PREFIX + filename
    if not remove_bg:
        return {"url": url}
    # Fon keyin, alohida ishchida olib tashlanadi — yuklash hech qachon kutmaydi
    try:
        bg = await run_in_threadpool(_enqueue, current_user, filename)
    except ip.QueueError as e:
        return {"url": url, "bg_error": str(e)}
    return {"url": url, "bg": bg}


class UrlRequest(BaseModel):
    url: str


class StatusRequest(BaseModel):
    urls: list[str] = []


@router.post("/remove-background")
def remove_background(data: UrlRequest, current_user=Depends(get_current_user)):
    """Avval yuklangan rasmni navbatga qo'yadi (har doim asl rasmdan). Tayyor bo'lsa — darhol natija."""
    orig = _parse_or_400(data.url)
    if not os.path.isfile(ip.upload_path(orig)):
        raise HTTPException(status_code=404, detail="Rasm topilmadi")
    try:
        bg = _enqueue(current_user, orig)
    except ip.QueueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = {"url": data.url, **bg}
    if bg["status"] == ip.DONE:
        res["result_url"] = ip.result_url(data.url, orig)
    return res


@router.post("/bg-jobs/status")
def bg_jobs_status(data: StatusRequest, current_user=Depends(get_current_user)):
    """Rasmlar navbatdagi holati. URL mijoz yuborganidek qaytadi — frontend o'z ro'yxatidan topadi."""
    cid = getattr(current_user, "company_id", None)
    parsed = {u: ip.parse_upload_url(u) for u in data.urls[:50]}
    origs = {p[0] for p in parsed.values() if p}
    if not cid or not origs:
        return {"items": []}
    jobs = ip.latest_jobs(_bind(), cid, origs)
    items = []
    for url, p in parsed.items():
        job = jobs.get(p[0]) if p else None
        if job is None:
            continue
        item = {"url": url, "status": job.status}
        if job.status == ip.DONE:
            item["result_url"] = ip.result_url(url, p[0])
        elif job.status == ip.FAILED and job.error:
            item["error"] = job.error
        items.append(item)
    return {"items": items}


@router.post("/bg-jobs/cancel")
def bg_jobs_cancel(data: UrlRequest, current_user=Depends(get_current_user)):
    """Navbatdagi ishni bekor qiladi yoki tayyor natijani asl rasmga qaytaradi (mahsulotlarda ham)."""
    orig = _parse_or_400(data.url)
    try:
        cid = _company_id(current_user)
    except ip.QueueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    status = ip.cancel(_bind(), cid, orig)
    return {"status": status, "original_url": ip.original_url(data.url, orig)}
