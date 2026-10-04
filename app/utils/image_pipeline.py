"""Mahsulot rasmlari: yuklashda siqish va orqa fonni olib tashlash navbati (image_jobs).

Yengil modul (Pillow + SQLAlchemy Core): alohida ishchi jarayon (app/services/bg_removal_worker.py)
ham shuni ishlatadi, shuning uchun app.models / app.services bu yerda import qilinmaydi.

Fayl nomlari: asl rasm <uuid>.<ext>, foni olib tashlangani <uuid>_<ext>_nobg.jpg (asli o'chirilmaydi).
Mahsulotdagi manzil fayl nomi bo'yicha almashtiriladi — to'liq domenli URL, ?v= va JSON ichidagi
yozuvlar ham to'g'ri almashadi; asl nom natija nomining qismi emas, shuning uchun takror qo'llash
natijani o'zgartirmaydi.
"""
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Table, Text,
    func, insert, or_, select, text, update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import column, table

from app.database import Base

UPLOAD_DIR = "static/uploads/products"
URL_PREFIX = "/static/uploads/products/"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKER_LOCK_FILE = os.path.join(REPO_ROOT, ".bg_worker.lock")

MAX_SIDE = 1280             # mahsulot kartochkasi va Telegram do'kon uchun yetarli
JPEG_QUALITY = 85
MAX_PIXELS = 16_000_000     # dekodlangan rasm (RGBA ~64 MB) — undan kattasi rad etiladi
MAX_JPEG_PIXELS = 89_000_000  # JPEG kichraytirib dekodlanadi (draft), sarlavhadagi o'lcham shu chegaragacha

PENDING, PROCESSING, DONE, FAILED, CANCELLED, REVERTED = (
    "pending", "processing", "done", "failed", "cancelled", "reverted")
ACTIVE = (PENDING, PROCESSING)

_ORIG_NAME = re.compile(r"^([0-9a-f]{32})\.(jpg|jpeg|png|webp|gif)$")
_NOBG_NAME = re.compile(r"^([0-9a-f]{32})_(jpg|jpeg|png|webp|gif)_nobg\.jpg$")


def _now():
    return datetime.now(timezone.utc)


image_jobs = Table(
    "image_jobs", Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("company_id", Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("original_token", String(64), nullable=False),  # <uuid>.<ext>
    Column("status", String(16), nullable=False, default=PENDING),
    Column("error", Text, nullable=True),
    Column("attempts", SmallInteger, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False, default=_now),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Index("ix_image_jobs_status_company", "status", "company_id"),
    Index("ix_image_jobs_company_token", "company_id", "original_token"),
    Index("ix_image_jobs_company_created", "company_id", "created_at"),
    # Bitta rasm bir vaqtda ikki marta navbatga tushmaydi
    Index("uq_image_jobs_active", "company_id", "original_token", unique=True,
          postgresql_where=text("status IN ('pending', 'processing')"),
          sqlite_where=text("status IN ('pending', 'processing')")),
)

# Ishchi jarayon Product modelini (va butun app.models ni) yuklamasligi uchun
_products = table(
    "products",
    column("id", Integer), column("company_id", Integer),
    column("images", Text), column("image_url", Text), column("updated_at", DateTime),
)


class QueueError(Exception):
    """Navbatga qo'yib bo'lmadi — foydalanuvchiga ko'rsatiladigan sabab."""


# ── Fayl nomlari ───────────────────────────────────────────────────────────────

def parse_upload_url(url):
    """URL -> (asl fayl nomi, foni olinganmi). Tizimga yuklanmagan rasm uchun None."""
    if not isinstance(url, str):
        return None
    idx = url.find(URL_PREFIX)
    if idx < 0:
        return None
    name = url[idx + len(URL_PREFIX):].split("?", 1)[0].split("#", 1)[0]
    m = _NOBG_NAME.match(name)
    if m:
        return f"{m.group(1)}.{m.group(2)}", True
    if _ORIG_NAME.match(name):
        return name, False
    return None


def nobg_name(orig: str) -> str:
    stem, ext = orig.rsplit(".", 1)
    return f"{stem}_{ext}_nobg.jpg"


def upload_path(name: str) -> str:
    return os.path.join(UPLOAD_DIR, name)


def result_url(url: str, orig: str) -> str:
    """Mijoz yuborgan manzildagi asl nomni natija nomiga almashtiradi (domen va h.k. saqlanadi)."""
    nobg = nobg_name(orig)
    return url if nobg in url else url.replace(orig, nobg)


def original_url(url: str, orig: str) -> str:
    return url.replace(nobg_name(orig), orig)


# ── Rasmni o'qish va siqish ────────────────────────────────────────────────────

def load_image(data: bytes, max_side: int = MAX_SIDE):
    """Rasmni xavfsiz o'qiydi: o'lcham tekshiruvi load() dan oldin (decompression bomb), JPEG
    kichraytirib dekodlanadi, telefon EXIF burilishi to'g'rilanadi. Natija: max_side gacha kichraytirilgan
    Pillow rasmi. Buzuq yoki juda katta rasmda ValueError."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
    except Exception:
        raise ValueError("Rasm fayli buzilgan yoki noto'g'ri formatda")
    if w * h > (MAX_JPEG_PIXELS if img.format == "JPEG" else MAX_PIXELS):
        raise ValueError("Rasm o'lchami juda katta")
    try:
        if img.format == "JPEG":
            img.draft("RGB", (max_side, max_side))  # DCT darajasida 2–8 baravar kichik dekodlash
        img.thumbnail((max_side, max_side))
        return ImageOps.exif_transpose(img)
    except Exception:
        raise ValueError("Rasm fayli buzilgan yoki noto'g'ri formatda")


def flatten_on_white(img):
    """Shaffof joylarni oq fonga qo'yadi (JPEG da ular qora bo'lib qolardi)."""
    from PIL import Image

    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def to_jpeg(img, quality: int = JPEG_QUALITY) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def compress_upload(data: bytes) -> bytes:
    """Yuklangan rasm -> eng uzun tomoni MAX_SIDE bo'lgan JPEG (telefon surati 3–5 MB -> ~200 KB)."""
    return to_jpeg(flatten_on_white(load_image(data)))


# ── Navbat ─────────────────────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def bg_enabled() -> bool:
    return os.getenv("BG_REMOVAL_ENABLED", "1").lower() not in ("0", "false", "no", "off")


def worker_alive() -> bool:
    """Ishchi jarayon lock faylni ushlab turadimi (u bitta nusxada ishlaydi)."""
    try:
        fd = os.open(WORKER_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return False
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return False
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def is_available() -> bool:
    return bg_enabled() and worker_alive()


def _latest(conn, company_id: int, orig: str):
    j = image_jobs
    return conn.execute(
        select(j.c.id, j.c.status, j.c.error)
        .where(j.c.company_id == company_id, j.c.original_token == orig)
        .order_by(j.c.id.desc()).limit(1)
    ).first()


def latest_jobs(bind, company_id: int, origs) -> dict:
    """{asl nom: so'nggi ish (id, status, error, original_token)} — faqat shu kompaniya."""
    origs = list(origs)
    if not origs:
        return {}
    j = image_jobs
    with bind.connect() as conn:
        rows = conn.execute(
            select(j.c.id, j.c.status, j.c.error, j.c.original_token)
            .where(j.c.company_id == company_id, j.c.original_token.in_(origs))
            .order_by(j.c.id)
        ).all()
    return {r.original_token: r for r in rows}


def _check_limits(conn, company_id: int):
    j = image_jobs
    daily = _env_int("BG_REMOVAL_DAILY_LIMIT", 500)
    per_company = _env_int("BG_REMOVAL_MAX_PENDING", 200)
    total = _env_int("BG_REMOVAL_MAX_PENDING_TOTAL", 2000)
    count = select(func.count()).select_from(j)
    if conn.scalar(count.where(j.c.company_id == company_id, j.c.created_at >= _now() - timedelta(hours=24))) >= daily:
        raise QueueError(f"Kunlik limit tugadi ({daily} ta rasm). Ertaga davom ettirish mumkin")
    if conn.scalar(count.where(j.c.company_id == company_id, j.c.status.in_(ACTIVE))) >= per_company:
        raise QueueError(f"Navbatda {per_company} ta rasm turibdi — ular tugashini kuting")
    if conn.scalar(count.where(j.c.status.in_(ACTIVE))) >= total:
        raise QueueError("Navbat to'lgan — birozdan keyin qayta urinib ko'ring")


def enqueue(bind, company_id: int, user_id, orig: str) -> dict:
    """Rasmni navbatga qo'yadi yoki mavjud holatini qaytaradi: {"id", "status"}.
    Avval ishlangan rasm darhol "done" (limitga sanalmaydi). Limit oshsa QueueError."""
    j = image_jobs
    try:
        with bind.begin() as conn:
            last = _latest(conn, company_id, orig)
            if last is not None and last.status in ACTIVE:
                return {"id": last.id, "status": last.status}
            if (last is not None and last.status in (DONE, REVERTED)
                    and os.path.isfile(upload_path(nobg_name(orig)))):
                if last.status == DONE:
                    return {"id": last.id, "status": DONE}
                conn.execute(update(j).where(j.c.id == last.id).values(status=DONE, finished_at=_now()))
                reenabled = last.id
            else:
                _check_limits(conn, company_id)
                new_id = conn.execute(insert(j).values(
                    company_id=company_id, user_id=user_id, original_token=orig,
                    status=PENDING, attempts=0, created_at=_now(),
                )).inserted_primary_key[0]
                return {"id": new_id, "status": PENDING}
    except IntegrityError:  # parallel so'rov xuddi shu rasmni navbatga qo'yib ulgurdi
        with bind.connect() as conn:
            last = _latest(conn, company_id, orig)
        return {"id": last.id, "status": last.status} if last else {"id": None, "status": PENDING}
    apply(bind, reenabled)  # asliga qaytarilgan natija yana yoqildi — mahsulotlarda ham
    return {"id": reenabled, "status": DONE}


def cancel(bind, company_id: int, orig: str):
    """Navbatdagi/ishlanayotgan ish -> cancelled, tayyor natija -> reverted (asl rasmga qaytarish).
    Yangi holatni qaytaradi (ish bo'lmasa None)."""
    j = image_jobs
    for _ in range(3):  # ishchi aynan shu payt holatni o'zgartirgan bo'lsa — qayta o'qiladi
        with bind.begin() as conn:
            last = _latest(conn, company_id, orig)
            if last is None:
                return None
            if last.status in ACTIVE:
                new = CANCELLED
            elif last.status == DONE:
                new = REVERTED
            else:
                return last.status
            changed = conn.execute(
                update(j).where(j.c.id == last.id, j.c.status == last.status)
                .values(status=new, finished_at=_now())
            ).rowcount
        if changed:
            apply(bind, last.id)
            return new
    return None


def apply(bind, job_id) -> int:
    """Ish holatini mahsulotlarga qo'llaydi: done — natija rasmi, reverted/cancelled — asl rasm.
    FOR SHARE: bekor qilish bilan bir vaqtda ishlasa ham natija holatga mos bo'lib qoladi.
    O'zgargan mahsulotlar sonini qaytaradi."""
    if job_id is None:
        return 0
    j, p = image_jobs, _products
    with bind.begin() as conn:
        row = conn.execute(
            select(j.c.status, j.c.company_id, j.c.original_token)
            .where(j.c.id == job_id).with_for_update(read=True)
        ).first()
        if row is None:
            return 0
        orig, nobg = row.original_token, nobg_name(row.original_token)
        if row.status == DONE:
            src, dst = orig, nobg
        elif row.status in (REVERTED, CANCELLED):
            src, dst = nobg, orig
        else:
            return 0
        return conn.execute(
            update(p)
            .where(p.c.company_id == row.company_id,
                   or_(p.c.images.contains(src, autoescape=True), p.c.image_url.contains(src, autoescape=True)))
            .values(images=func.replace(p.c.images, src, dst),
                    image_url=func.replace(p.c.image_url, src, dst),
                    updated_at=_now())
        ).rowcount


def reconcile_product(bind, product) -> bool:
    """Mahsulot saqlangandan keyin rasmlarini navbat holatiga moslaydi. Ishchi natijani mahsulot hali
    bazada yo'q paytda tayyorlagan bo'lsa ham u yo'qolmaydi. Hech qachon xato tashlamaydi —
    mahsulotni saqlash bu funksiyaga bog'liq emas. O'zgarish bo'lsa True."""
    try:
        values = [product.image_url]
        try:
            imgs = json.loads(product.images or "[]")
        except (TypeError, ValueError):
            imgs = []
        if isinstance(imgs, list):
            values += imgs
        forms = {}  # asl nom -> {False: asl rasm bor, True: natija bor}
        for v in values:
            parsed = parse_upload_url(v)
            if parsed:
                forms.setdefault(parsed[0], set()).add(parsed[1])
        if not forms or not product.company_id:
            return False
        changed = 0
        for orig, job in latest_jobs(bind, product.company_id, forms).items():
            if (job.status == DONE and False in forms[orig]) or \
                    (job.status in (REVERTED, CANCELLED) and True in forms[orig]):
                changed += apply(bind, job.id)
        return changed > 0
    except Exception as e:  # noqa: BLE001
        print(f"[image-jobs] mahsulot rasmlarini moslashda xato: {e!r}", flush=True)
        return False
