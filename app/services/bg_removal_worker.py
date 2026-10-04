"""Orqa fonni olib tashlash ishchisi — alohida jarayon (systemd: deploy/erppos-bgworker.service).

image_jobs navbatidan ish oladi, rembg bilan fonni olib tashlaydi va mahsulotlardagi rasm manzilini
almashtiradi. API uni hech qachon kutmaydi — yuklash darhol qaytadi, natija keyin paydo bo'ladi.
- bo'sh paytda yengil (~40 MB): faqat navbatni tekshiradi, model ish kelgandagina yuklanadi;
- navbat BG_REMOVAL_IDLE_SEC bo'sh tursa o'zini qayta yuklaydi (os.execv) — model xotirasi bo'shaydi;
- do'konlar navbatma-navbat: eng uzoq kutgani birinchi, do'kon ichida — kelish tartibida;
- CPU (faqat bo'sh yadrolar) va xotira cheklovlari systemd unit'da — ERP sekinlashmaydi.

Paket importisiz ishlaydi:
  python app/services/bg_removal_worker.py           — ishga tushirish
  python app/services/bg_removal_worker.py --warmup  — modelni yuklab olib tayyorlash (o'rnatishda bir marta)
"""
import itertools
import os
import sys
import threading
import time
import traceback
from datetime import timedelta

# numpy/onnxruntime import qilinishidan oldin: kutubxonalar ortiqcha oqim ochmasin
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

SCRIPT = os.path.abspath(__file__)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import delete, func, select, update  # noqa: E402

from app.utils import image_pipeline as ip  # noqa: E402

MODEL = os.getenv("BG_REMOVAL_MODEL", "isnet-general-use")  # rembg standarti (bria-rmbg) tijoriy emas
THREADS = int(os.getenv("BG_REMOVAL_THREADS", str(min(2, max(1, (os.cpu_count() or 2) - 1)))))
IDLE_SEC = int(os.getenv("BG_REMOVAL_IDLE_SEC", "600"))
POLL_SEC = float(os.getenv("BG_REMOVAL_POLL_SEC", "2"))
MIN_FREE_MB = int(os.getenv("BG_REMOVAL_MIN_FREE_MB", "700"))  # model ~600 MB — swap'ga tushmaslik uchun
JOB_TIMEOUT = int(os.getenv("BG_REMOVAL_JOB_TIMEOUT", "300"))
MAX_ATTEMPTS = 3
KEEP_DAYS = 30

_session = None
_job_started = None  # watchdog uchun
_serve_seq = itertools.count(1)  # adolatli navbat: vaqt emas, tartib raqami (soat aniqligiga bog'liq emas)


def log(msg):
    print(f"[bg-worker] {msg}", flush=True)


# ── Model ──────────────────────────────────────────────────────────────────────

def _get_session():
    global _session
    if _session is None:
        import onnxruntime as ort
        from rembg import new_session

        opts = ort.SessionOptions()
        opts.enable_cpu_mem_arena = False
        opts.intra_op_num_threads = THREADS
        opts.inter_op_num_threads = 1
        opts.add_session_config_entry("session.intra_op.allow_spinning", "0")  # kutayotgan oqim CPU yemasin
        t = time.time()
        _session = new_session(MODEL, sess_opts=opts)
        log(f"model yuklandi: {MODEL}, {THREADS} oqim, {time.time() - t:.1f}s")
    return _session


def remove_background(data: bytes) -> bytes:
    """Rasm baytlari -> oq fonli JPEG. Foydalanuvchi xatosida (buzuq rasm, mahsulot yo'q) ValueError."""
    from PIL import Image
    from rembg import remove

    src = ip.flatten_on_white(ip.load_image(data))
    # post_process_mask: maskadagi xira "arvoh" dog'larni tozalaydi, chetlar tiniq
    cut = remove(src, session=_get_session(), post_process_mask=True)
    alpha = cut.getchannel("A")
    if alpha.getbbox() is None:
        raise ValueError("Rasmda mahsulot aniqlanmadi")
    out = Image.new("RGB", cut.size, (255, 255, 255))
    out.paste(cut.convert("RGB"), mask=alpha)
    return ip.to_jpeg(out, quality=90)


def _free_mb():
    """Bo'sh xotira (MB): xostdagi MemAvailable va cgroup (systemd MemoryMax) qoldig'ining kichigi.
    Aniqlab bo'lmasa (Windows) — None."""
    values = []
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    values.append(int(line.split()[1]) // 1024)
                    break
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open("/proc/self/cgroup") as f:
            rel = next(line.strip()[3:] for line in f if line.startswith("0::"))
        base = "/sys/fs/cgroup" + rel
        with open(base + "/memory.max") as f:
            limit = f.read().strip()
        if limit != "max":
            with open(base + "/memory.current") as f:
                current = int(f.read())
            inactive = 0
            with open(base + "/memory.stat") as f:
                for line in f:
                    if line.startswith("inactive_file "):
                        inactive = int(line.split()[1])
                        break
            values.append((int(limit) - (current - inactive)) // (1024 * 1024))
    except (OSError, ValueError, StopIteration):
        pass
    return min(values) if values else None


# ── Navbat ─────────────────────────────────────────────────────────────────────

def recover(bind):
    """Ishga tushganda: uzilib qolgan ishlar navbatga qaytadi (ko'p marta yiqitgan rasm — failed),
    eski yakunlangan yozuvlar tozalanadi (fayllarga tegilmaydi)."""
    j = ip.image_jobs
    now = ip._now()
    with bind.begin() as conn:
        conn.execute(update(j).where(j.c.status == ip.PROCESSING, j.c.attempts >= MAX_ATTEMPTS)
                     .values(status=ip.FAILED, error="Rasmni ishlab bo'lmadi", finished_at=now))
        back = conn.execute(update(j).where(j.c.status == ip.PROCESSING).values(status=ip.PENDING)).rowcount
        conn.execute(delete(j).where(j.c.status.notin_(ip.ACTIVE),
                                     j.c.created_at < now - timedelta(days=KEEP_DAYS)))
    if back:
        log(f"{back} ta uzilib qolgan ish navbatga qaytarildi")


def pending_heads(bind) -> dict:
    """{company_id: eng eski kutayotgan ish id}."""
    j = ip.image_jobs
    with bind.connect() as conn:
        rows = conn.execute(
            select(j.c.company_id, func.min(j.c.id)).where(j.c.status == ip.PENDING).group_by(j.c.company_id)
        ).all()
    return {cid: jid for cid, jid in rows}


def pick(heads: dict, last_served: dict):
    """Adolatli tanlov: eng uzoq xizmat ko'rmagan do'kon, teng bo'lsa — eng eski ish."""
    cid = min(heads, key=lambda c: (last_served.get(c, 0), heads[c]))
    return cid, heads[cid]


def claim(bind, job_id):
    """Ishni o'ziga oladi (urinishlar soni shu yerda oshadi — rasm jarayonni yiqitsa ham sanaladi)."""
    j = ip.image_jobs
    with bind.begin() as conn:
        got = conn.execute(
            update(j).where(j.c.id == job_id, j.c.status == ip.PENDING)
            .values(status=ip.PROCESSING, attempts=j.c.attempts + 1, started_at=ip._now(), error=None)
        ).rowcount
        if not got:
            return None
        return conn.execute(
            select(j.c.id, j.c.company_id, j.c.original_token, j.c.attempts).where(j.c.id == job_id)
        ).first()


def _finish(bind, job, status, error=None) -> bool:
    j = ip.image_jobs
    with bind.begin() as conn:
        return bool(conn.execute(
            update(j).where(j.c.id == job.id, j.c.status == ip.PROCESSING)
            .values(status=status, error=error, finished_at=ip._now())
        ).rowcount)


def retry_later(bind, job, error: str):
    j = ip.image_jobs
    if job.attempts >= MAX_ATTEMPTS:
        _finish(bind, job, ip.FAILED, error)
        return
    with bind.begin() as conn:
        conn.execute(update(j).where(j.c.id == job.id, j.c.status == ip.PROCESSING)
                     .values(status=ip.PENDING, error=error))


def run_job(bind, job, remove=None):
    """Bitta ish. Foydalanuvchi xatosi — darhol failed; boshqa xatolar chaqiruvchiga (qayta urinish)."""
    remove = remove or remove_background
    orig = job.original_token
    src, dst = ip.upload_path(orig), ip.upload_path(ip.nobg_name(orig))
    if not os.path.isfile(src):
        _finish(bind, job, ip.FAILED, "Rasm topilmadi")
        return
    if not os.path.isfile(dst):  # avval ishlangan bo'lsa model ishlatilmaydi
        with open(src, "rb") as f:
            data = f.read()
        try:
            out = remove(data)
        except ValueError as e:
            _finish(bind, job, ip.FAILED, str(e))
            return
        tmp = f"{dst}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, dst)  # yarim yozilgan fayl hech qachon ko'rinmaydi
    # 1) holat (bekor qilingan bo'lsa — o'tkazib yuboriladi), 2) mahsulotlar — alohida, qisqa tranzaksiyalar
    if _finish(bind, job, ip.DONE):
        ip.apply(bind, job.id)


def step(bind, last_served: dict, remove=None, memory_ok=None) -> bool:
    """Navbatdan bitta ishni bajaradi. Ish bo'lmasa (yoki xotira yetmasa) False."""
    global _job_started
    heads = pending_heads(bind)
    if not heads:
        return False
    if memory_ok is not None and not memory_ok():
        return False
    cid, job_id = pick(heads, last_served)
    last_served[cid] = next(_serve_seq)
    job = claim(bind, job_id)
    if job is None:
        return True  # boshqa holat o'zgardi (bekor qilindi) — keyingisiga
    _job_started = time.monotonic()
    try:
        run_job(bind, job, remove)
    except Exception as e:  # noqa: BLE001
        log(f"ish #{job.id} xatosi ({job.attempts}-urinish): {e!r}")
        traceback.print_exc()
        retry_later(bind, job, "Fonni olib tashlashda xato")
        raise
    finally:
        _job_started = None
    return True


# ── Jarayon ────────────────────────────────────────────────────────────────────

def _acquire_lock(wait_sec: float = 10.0):
    """Bitta nusxa: lock faylni ushlab turadi (API shu orqali ishchi tirikligini biladi)."""
    fd = os.open(ip.WORKER_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + wait_sec
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError:
            if time.monotonic() > deadline:
                os.close(fd)
                return None
            time.sleep(0.5)  # API tekshiruvi lock'ni bir lahzaga ushlagan bo'lishi mumkin


def _watchdog():
    while True:
        time.sleep(10)
        started = _job_started
        if started is not None and time.monotonic() - started > JOB_TIMEOUT:
            log(f"ish {JOB_TIMEOUT}s dan oshdi — jarayon qayta ishga tushiriladi")
            os._exit(3)  # systemd qayta ishga tushiradi, ish navbatga qaytadi (urinish sanalgan)


def _memory_ok_factory():
    state = {"warned": False}

    def ok():
        if _session is not None:
            return True
        free = _free_mb()
        if free is None or free >= MIN_FREE_MB:
            state["warned"] = False
            return True
        if not state["warned"]:
            log(f"bo'sh xotira {free} MB < {MIN_FREE_MB} MB — model yuklanmaydi, kutilmoqda")
            state["warned"] = True
        return False
    return ok


def warmup():
    from PIL import Image

    t = time.time()
    _get_session()
    img = Image.new("RGB", (64, 64), (200, 30, 30))
    try:
        remove_background(ip.to_jpeg(img))
    except ValueError:
        pass
    log(f"tayyor: model={MODEL}, {time.time() - t:.1f}s")


def main():
    os.chdir(ROOT)  # UPLOAD_DIR va .env loyiha papkasiga nisbatan
    if "--warmup" in sys.argv:
        warmup()
        return
    lock = _acquire_lock()
    if lock is None:
        log("boshqa nusxa ishlayapti — chiqildi")
        return
    from app.database import engine

    threading.Thread(target=_watchdog, daemon=True).start()
    recover(engine)
    log(f"ishga tushdi (pid {os.getpid()}), navbat kuzatilmoqda")
    last_served, memory_ok = {}, _memory_ok_factory()
    idle_since, errors = time.monotonic(), 0
    while True:
        try:
            worked = step(engine, last_served, memory_ok=memory_ok)
            errors = 0
        except Exception as e:  # noqa: BLE001  (baza uzilishi yoki model xatosi)
            errors += 1
            if errors >= 5:
                log(f"ketma-ket {errors} ta xato — jarayon qayta ishga tushiriladi: {e!r}")
                sys.exit(1)
            time.sleep(min(30 * errors, 120))
            continue
        if worked:
            idle_since = time.monotonic()
            continue
        if _session is not None and time.monotonic() - idle_since > IDLE_SEC:
            log("navbat bo'sh — model xotiradan bo'shatiladi")
            sys.stdout.flush()
            os.execv(sys.executable, [sys.executable, SCRIPT])
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
