"""Kassa (hamyon) ni tanlash va unga kirish huquqi — yagona qoida (T1.10).

`resolve_wallet` — sotuv, qaytarish, qarz to'lovi, smena yopish va boshqa joylarda
pul tushadigan/chiqadigan kassani BIR XIL tartibda tanlaydi:

  1. so'rovda aniq berilgan kassa (`requested_wallet_id`) — korxona, faollik, filial va
     shaxsiylik tekshiruvi bilan (aks holda 403/404);
  2. foydalanuvchining `user_wallets` dagi (faol, shu korxonaning) kassasi — default birinchi;
  3. filialning default kassasi (`branches.default_wallet_id`, ustun bo'lsa);
  4. `Wallet.branch_id == branch_id`, ochiq, faol, shaxsiy EMAS (eng kichik id);
  5. umumiy kassa (`Wallet.branch_id IS NULL`), ochiq, faol, shaxsiy EMAS (eng kichik id).

6. filial noma'lum (`branch_id is None`) yoki foydalanuvchi admin/director/super_admin (barcha kassalarga
   huquqi bor) bo'lsa: korxonaning birinchi ochiq, faol, shaxsiy bo'lmagan kassasi.

Hech biri topilmasa: korxonada >=2 faol filial va shaxsiy bo'lmagan faol kassalar bor bo'lsa 400
"Bu filial uchun kassa sozlanmagan"; bitta filialli (yoki kassasi umuman yo'q) korxonada `None`
(kassasiz davom etish — eski xatti-harakat).
Shaxsiy ("qo'l kassasi") va boshqa filial kassasi hech qachon "birinchi ochiq kassa" bo'lib tanlanmaydi.

`purpose="refund"`: avval so'ralgan kassa, so'ng asl sotuv kassasi (`sales.wallet_id`, bo'lmasa asl
`KassaMovement`/`Transaction`), so'ng qaytaruvchining o'z kassasi. Asl kassa NOFAOL bo'lsa filial
kassasi tartibi (3-5) ishlaydi. Topilmasa 400 (qaytarishda pul jim hisobsiz ketmaydi).
"""
# pyright: reportMissingImports=false
from typing import List, Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy.orm import Session, object_session  # type: ignore

from app.models.moliya import KassaMovement, Transaction, Wallet
from app.models.user import UserWallet

WALLET_NOT_FOUND = "Kassa (hamyon) topilmadi"
NO_BRANCH_WALLET = "Bu filial uchun kassa sozlanmagan"
REFUND_NO_WALLET = "Qaytarish uchun ochiq kassa topilmadi"
WALLET_OTHER_BRANCH = "Bu kassa boshqa filialga tegishli"
WALLET_PERSONAL = "Bu shaxsiy kassa, undan foydalanib bo'lmaydi"
WALLET_CLOSED = "Kassa yopiq"
NEGATIVE_BALANCE_WARNING = "Kassa balansi manfiyga tushdi"

# Korxonaning istalgan kassasi bilan ishlay oladigan rollar
WALLET_ADMIN_ROLES = ("admin", "director", "super_admin")


def _role(user) -> str:
    return str(getattr(user.role, "value", user.role))


def is_wallet_admin(user) -> bool:
    return _role(user) in WALLET_ADMIN_ROLES


def user_branch_id(db: Optional[Session], user) -> Optional[int]:
    """Foydalanuvchining joriy filiali: filial konteksti (T1.2), bo'lmasa `users.branch_id`."""
    if db is not None:
        from app.core.branch_context import effective_branch_id
        return effective_branch_id(db, user)
    return getattr(user, "branch_id", None)


def user_wallet_ids(db: Session, user) -> List[int]:
    """Foydalanuvchiga biriktirilgan (faol, shu korxonaning) kassalar: default birinchi, so'ng id bo'yicha."""
    rows = (
        db.query(UserWallet.wallet_id)
        .join(Wallet, Wallet.id == UserWallet.wallet_id)
        .filter(
            UserWallet.user_id == user.id,
            Wallet.company_id == user.company_id,
            Wallet.is_active == True,  # noqa: E712
        )
        .order_by(UserWallet.is_default.desc(), UserWallet.wallet_id.asc())
        .all()
    )
    return [r[0] for r in rows]


def _is_attached(db: Session, user, wallet) -> bool:
    return db.query(UserWallet.user_id).filter(
        UserWallet.user_id == user.id, UserWallet.wallet_id == wallet.id,
    ).first() is not None


def assert_wallet_access(user, wallet, db: Optional[Session] = None) -> None:
    """Foydalanuvchi shu kassadan foydalana oladimi (filial doirasi). Aks holda 404/403.

    - `super_admin` — barchasi; `admin/director` — o'z korxonasining barcha kassalari;
    - boshqalar — `user_wallets` da biriktirilgan kassalar, yoki shaxsiy bo'lmagan va
      `wallet.branch_id IN (NULL, user.branch_id)` bo'lgan kassalar (filialsiz xodimda filial
      sharti qo'llanmaydi — ombor tekshiruvidagi kabi).
    Rol cheklovlari (T0.5) bu yerda emas — faqat filial/shaxsiylik doirasi.
    """
    if wallet is None:
        raise HTTPException(status_code=404, detail=WALLET_NOT_FOUND)
    role = _role(user)
    if role == "super_admin":
        return
    if wallet.company_id != user.company_id:
        raise HTTPException(status_code=404, detail=WALLET_NOT_FOUND)
    if role in WALLET_ADMIN_ROLES:
        return
    db = db or object_session(wallet)
    if db is not None and _is_attached(db, user, wallet):
        return
    if getattr(wallet, "is_personal", False):
        raise HTTPException(status_code=403, detail=WALLET_PERSONAL)
    ub = user_branch_id(db, user)
    if ub is not None and wallet.branch_id is not None and wallet.branch_id != ub:
        raise HTTPException(status_code=403, detail=WALLET_OTHER_BRANCH)


def wallet_visible_to(db: Session, user, wallet) -> bool:
    """`assert_wallet_access` ning xatosiz varianti + shaxsiy kassa faqat egasiga ko'rinadi (admin ham)."""
    if getattr(wallet, "is_personal", False) and _role(user) != "super_admin":
        if not _is_attached(db, user, wallet):
            return False
    try:
        assert_wallet_access(user, wallet, db)
    except HTTPException:
        return False
    return True


def _count_active_branches(db: Session, company_id: Optional[int]) -> int:
    from app.models.branch import Branch
    return db.query(Branch.id).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).count()


def _find_by_id(db: Session, user, wallet_id, *, for_update: bool):
    q = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == user.company_id)
    if for_update:
        q = q.with_for_update()
    return q.first()


def _usable_by_id(db: Session, user, wallet_id, *, for_update: bool, require_open: bool = False):
    if not wallet_id:
        return None
    w = _find_by_id(db, user, wallet_id, for_update=for_update)
    if w is None or w.is_active is False:
        return None
    if require_open and w.is_open is False:
        return None
    return w


def _requested(db: Session, user, wallet_id, branch_id, purpose, *, for_update: bool):
    w = _find_by_id(db, user, wallet_id, for_update=for_update)
    if w is None or w.is_active is False:
        raise HTTPException(status_code=404, detail=WALLET_NOT_FOUND)
    assert_wallet_access(user, w, db)
    if purpose == "refund":
        # Qaytarishda kassa ochiq bo'lishi shart (T0.31)
        if w.is_open is False:
            raise HTTPException(status_code=400, detail=WALLET_CLOSED)
    elif branch_id is not None and w.branch_id is not None and w.branch_id != branch_id:
        raise HTTPException(status_code=403, detail=WALLET_OTHER_BRANCH)
    return w


def _branch_default(db: Session, user, branch_id, *, for_update: bool):
    """`branches.default_wallet_id` (T1.4 qo'shgan bo'lsa); ustun yo'q bo'lsa qadam o'tkaziladi."""
    from app.models.branch import Branch
    col = getattr(Branch, "default_wallet_id", None)
    if col is None or branch_id is None:
        return None
    wid = db.query(col).filter(Branch.id == branch_id, Branch.company_id == user.company_id).scalar()
    w = _usable_by_id(db, user, wid, for_update=for_update)
    if w is not None and getattr(w, "is_personal", False):
        return None
    return w


def _branch_open(db: Session, user, branch_id, *, null_branch: bool, for_update: bool):
    q = db.query(Wallet).filter(
        Wallet.company_id == user.company_id,
        Wallet.is_active == True,  # noqa: E712
        Wallet.is_open == True,  # noqa: E712
        Wallet.is_personal == False,  # noqa: E712
    )
    if null_branch:
        q = q.filter(Wallet.branch_id.is_(None))
    else:
        if branch_id is None:
            return None
        q = q.filter(Wallet.branch_id == branch_id)
    q = q.order_by(Wallet.id.asc())
    if for_update:
        q = q.with_for_update()
    return q.first()


def _company_open_wallet(db: Session, user, *, for_update: bool):
    q = db.query(Wallet).filter(
        Wallet.company_id == user.company_id,
        Wallet.is_active == True,  # noqa: E712
        Wallet.is_open == True,  # noqa: E712
        Wallet.is_personal == False,  # noqa: E712
    ).order_by(Wallet.id.asc())
    if for_update:
        q = q.with_for_update()
    return q.first()


def _company_has_wallets(db: Session, company_id) -> bool:
    return db.query(Wallet.id).filter(
        Wallet.company_id == company_id,
        Wallet.is_active == True,  # noqa: E712
        Wallet.is_personal == False,  # noqa: E712
    ).first() is not None


def _branch_chain(db: Session, user, branch_id, *, for_update: bool):
    w = _branch_default(db, user, branch_id, for_update=for_update)
    if w is not None:
        return w
    w = _branch_open(db, user, branch_id, null_branch=False, for_update=for_update)
    if w is not None:
        return w
    return _branch_open(db, user, branch_id, null_branch=True, for_update=for_update)


def original_sale_wallet_id(db: Session, original_sale) -> Optional[int]:
    """Asl sotuv kassasi: `sales.wallet_id`, bo'lmasa asl `KassaMovement`/`Transaction` (eski sotuvlar)."""
    if original_sale is None:
        return None
    wid = getattr(original_sale, "wallet_id", None)
    if wid:
        return wid
    cid = original_sale.company_id
    row = db.query(KassaMovement.wallet_id).filter(
        KassaMovement.company_id == cid,
        KassaMovement.reference_type == "sale",
        KassaMovement.reference_id == original_sale.id,
        KassaMovement.wallet_id.isnot(None),
    ).order_by(KassaMovement.id.asc()).first()
    if row:
        return row[0]
    row = db.query(Transaction.wallet_id).filter(
        Transaction.company_id == cid,
        Transaction.reference_type == "sale",
        Transaction.reference_id == original_sale.id,
        Transaction.wallet_id.isnot(None),
    ).order_by(Transaction.id.asc()).first()
    return row[0] if row else None


def resolve_wallet(
    db: Session,
    user,
    *,
    branch_id: Optional[int],
    purpose: str = "sale",
    requested_wallet_id: Optional[int] = None,
    original_sale=None,
    for_update: bool = False,
):
    """Kassani tanlaydi (modul docstring'ida tartib). `Wallet` yoki (>=2 filialsiz holatda) `None` qaytaradi.

    `purpose`: 'sale' | 'refund' | 'debt_payment' | 'shift_close' | 'expense'.
    `for_update=True` — balans o'zgartiriladigan joylarda qator qulflanadi.
    """
    if requested_wallet_id:
        return _requested(db, user, requested_wallet_id, branch_id, purpose, for_update=for_update)

    if purpose == "refund":
        orig_inactive = False
        wid = original_sale_wallet_id(db, original_sale)
        if wid:
            ow = _find_by_id(db, user, wid, for_update=False)
            if ow is not None and ow.is_active is False:
                orig_inactive = True
            else:
                w = _usable_by_id(db, user, wid, for_update=for_update, require_open=True)
                if w is not None:
                    return w
        for uwid in user_wallet_ids(db, user):
            w = _usable_by_id(db, user, uwid, for_update=for_update, require_open=True)
            if w is not None:
                return w
        if orig_inactive:
            bid = branch_id if branch_id is not None else getattr(original_sale, "branch_id", None)
            w = _branch_chain(db, user, bid, for_update=for_update)
            if w is not None:
                return w
        if _count_active_branches(db, user.company_id) >= 2 and _company_has_wallets(db, user.company_id):
            raise HTTPException(status_code=400, detail=NO_BRANCH_WALLET)
        raise HTTPException(status_code=400, detail=REFUND_NO_WALLET)

    for uwid in user_wallet_ids(db, user):
        w = _usable_by_id(db, user, uwid, for_update=for_update)
        if w is not None:
            return w

    w = _branch_chain(db, user, branch_id, for_update=for_update)
    if w is not None:
        return w

    # Filial noma'lum yoki foydalanuvchi barcha kassalarga huquqli (admin/director): korxonaning birinchi ochiq kassasi
    if branch_id is None or is_wallet_admin(user):
        w = _company_open_wallet(db, user, for_update=for_update)
        if w is not None:
            return w

    if _count_active_branches(db, user.company_id) >= 2 and _company_has_wallets(db, user.company_id):
        raise HTTPException(status_code=400, detail=NO_BRANCH_WALLET)
    return None


# ─── Ro'yxat doirasi (GET /kassa va GET /finance/wallets uchun bir xil to'plam) ─────────────

def list_visible_wallets(
    db: Session,
    user,
    *,
    branch_id: Optional[int] = None,
    include_inactive: bool = False,
    usable: bool = False,
    company_scoped: bool = True,
) -> List[Wallet]:
    """Foydalanuvchiga ko'rinadigan kassalar (id bo'yicha).

    - standart holatda faqat faol kassalar (`include_inactive=True` — nofaollar ham);
    - shaxsiy ("qo'l kassasi") kassalar faqat egasiga ko'rinadi (`user_wallets`);
    - admin/director/super_admin — korxonaning barcha (shaxsiy bo'lmagan) kassalari; boshqalar —
      o'ziga biriktirilganlar va `branch_id IN (NULL, o'z filiali)` kassalar;
    - `branch_id` berilsa: aniq shu filial kassalari; `usable=True` bilan shu filial va umumiy
      (filialsiz) kassalar (smena yopish, to'lov formalari uchun).
    """
    from sqlalchemy import or_

    q = db.query(Wallet)
    if company_scoped or _role(user) != "super_admin":
        q = q.filter(Wallet.company_id == user.company_id)
    if not include_inactive or usable:
        q = q.filter(Wallet.is_active == True)  # noqa: E712

    attached_ids = [r[0] for r in db.query(UserWallet.wallet_id).filter(UserWallet.user_id == user.id).all()]
    if attached_ids:
        q = q.filter(or_(Wallet.is_personal == False, Wallet.id.in_(attached_ids)))  # noqa: E712
    else:
        q = q.filter(Wallet.is_personal == False)  # noqa: E712

    if not is_wallet_admin(user):
        ub = user_branch_id(db, user)
        scope = []
        if attached_ids:
            scope.append(Wallet.id.in_(attached_ids))
        if ub is not None:
            scope.append(or_(Wallet.branch_id.is_(None), Wallet.branch_id == ub))
        elif not attached_ids:
            scope = None  # filialsiz va biriktirilmagan xodim: filial sharti yo'q (assert_wallet_access bilan mos)
        if scope:
            q = q.filter(or_(*scope))
        elif scope is not None:
            q = q.filter(Wallet.id == -1)

    if branch_id is not None:
        if usable:
            q = q.filter(or_(Wallet.branch_id == branch_id, Wallet.branch_id.is_(None)))
        else:
            q = q.filter(Wallet.branch_id == branch_id)
    return q.order_by(Wallet.id.asc()).all()


def wallet_meta(db: Session, user, wallets) -> dict:
    """Ro'yxat javobi uchun qo'shimcha maydonlar: {wallet_id: {branch_name, is_personal, is_default_for_me}}."""
    from app.models.branch import Branch
    branch_ids = {w.branch_id for w in wallets if w.branch_id}
    names = {}
    if branch_ids:
        names = dict(db.query(Branch.id, Branch.name).filter(Branch.id.in_(branch_ids)).all())
    defaults = {
        r[0] for r in db.query(UserWallet.wallet_id).filter(
            UserWallet.user_id == user.id, UserWallet.is_default == True,  # noqa: E712
        ).all()
    }
    return {
        w.id: {
            "branch_name": names.get(w.branch_id),
            "is_personal": bool(getattr(w, "is_personal", False)),
            "is_default_for_me": w.id in defaults and w.is_active is not False,
        }
        for w in wallets
    }


def validate_wallet_branch(db: Session, branch_id: Optional[int], company_id: Optional[int]) -> Optional[int]:
    """Kassa filiali (tahrirlashda): bo'sh bo'lsa `None` (umumiy kassa); boshqa korxona yoki mavjud
    bo'lmagan filial -> 404 "Filial topilmadi" (mavjudligi oshkor bo'lmaydi); nofaol filial -> 400."""
    if not branch_id:
        return None
    from app.models.branch import Branch
    from app.services.tenant_guards import BRANCH_INVALID
    b = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    if b.is_active is False:
        raise HTTPException(status_code=400, detail=BRANCH_INVALID)
    return b.id


def clear_wallet_assignments(db: Session, wallet_id: int) -> int:
    """Kassa o'chirilganda (nofaol qilinganda) `user_wallets` qatorlarini ham o'chiradi."""
    return db.query(UserWallet).filter(UserWallet.wallet_id == wallet_id).delete(synchronize_session=False)


WALLET_BRANCH_MISMATCH_WARNING = "Kassa xodimning filialiga tegishli emas"


def wallet_branch_warning(db: Session, target_user, wallet) -> Optional[str]:
    """Kassa biriktirishda ogohlantirish: kassa filiali xodim filialiga mos kelmasa matn (aks holda `None`).
    Biriktirish baribir bajariladi (xodim ikki filialda ishlashi mumkin) — ogohlantirish `{ok, warning}` da qaytadi."""
    ub = getattr(target_user, "branch_id", None)
    if ub is None or wallet.branch_id is None or wallet.branch_id == ub:
        return None
    return WALLET_BRANCH_MISMATCH_WARNING
