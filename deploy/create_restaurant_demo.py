"""Restoran rejimini ko'rsatish uchun test (demo) korxonasi.

    cd ~/eldor/erppos && source venv/bin/activate && python -m deploy.create_restaurant_demo

Yaratadi: "Demo Restoran (test)" korxonasi (restoran, stolli format), asosiy filial, "Asosiy ombor" va
"Oshxona" omborlari, ochiq kassa, sexlar, zal va 10 stol, menyu (taomlar, yarim tayyor, ingredientlar,
ichimliklar) texnologik kartalari bilan, ombor qoldiqlari va uchta xodim (egasi, kassir, ofitsiant).
Takroriy ishga tushirish xavfsiz: egasining telefoni bazada bo'lsa hech narsa yaratilmaydi.

Parol va PIN kodda saqlanmaydi: DEMO_PASSWORD / DEMO_PIN muhit o'zgaruvchilaridan olinadi, berilmasa
tasodifiy yaratiladi va faqat bir marta ekranga chiqariladi.
"""
import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

COMPANY_NAME = "Demo Restoran (test)"


def _password() -> str:
    return os.environ.get("DEMO_PASSWORD") or ("Demo" + secrets.token_hex(4))


def _pin() -> str:
    pin = os.environ.get("DEMO_PIN")
    if pin:
        return pin
    while True:
        pin = f"{secrets.randbelow(10 ** 4):04d}"
        if len(set(pin)) > 1 and pin not in ("1234", "4321"):
            return pin
USERS = [
    # (telefon, ism, rol, restoran ruxsatlari)
    ("998900077001", "Demo Egasi", "admin", None),
    ("998900077002", "Demo Kassir", "cashier", None),
    ("998900077003", "Demo Ofitsiant", "cashier", {"restaurant": {"waiter": True, "take_payment": False,
                                                                 "move_table": False}}),
]

# (nomi, birlik, tannarx so'm, oshxona qoldig'i)
INGREDIENTS = [
    ("Guruch", "kg", 22000, 25), ("Mol go'shti", "kg", 120000, 15), ("Qo'y go'shti", "kg", 130000, 8),
    ("Sabzi", "kg", 6000, 20), ("Piyoz", "kg", 5000, 20), ("O'simlik yog'i", "l", 22000, 10),
    ("Un", "kg", 8000, 25), ("Kartoshka", "kg", 5000, 20), ("Pomidor", "kg", 15000, 8),
    ("Bodring", "kg", 12000, 6), ("Bulg'or qalampiri", "kg", 18000, 4), ("Ko'k choy (quruq)", "kg", 90000, 2),
]
# (nomi, narx, tannarx, asosiy ombor qoldig'i)
GOODS = [("Coca-Cola 0.5", 10000, 6500, 48), ("Suv 0.5", 5000, 2500, 48), ("Non", 4000, 2500, 30)]
# yarim tayyor: (nomi, chiqish kg, [(ingredient, brutto)])
SEMI = [("Qiyma", 5, [("Mol go'shti", 4.5), ("Piyoz", 1)])]
# taomlar: (nomi, kategoriya, narx, porsiya g, tayyorlash daq, [(komponent, brutto 1 porsiya uchun)])
DISHES = [
    ("Osh", "Ikkinchi taomlar", 45000, 400, 15,
     [("Guruch", 0.15), ("Mol go'shti", 0.1), ("Sabzi", 0.1), ("Piyoz", 0.03), ("O'simlik yog'i", 0.04)]),
    ("Lag'mon", "Birinchi taomlar", 38000, 450, 15,
     [("Un", 0.15), ("Mol go'shti", 0.08), ("Bulg'or qalampiri", 0.04), ("Pomidor", 0.05), ("Piyoz", 0.03)]),
    ("Manti (5 dona)", "Ikkinchi taomlar", 40000, 350, 25, [("Qiyma", 0.2), ("Un", 0.1)]),
    ("Shashlik (qo'y)", "Gril", 28000, 150, 15, [("Qo'y go'shti", 0.17), ("Piyoz", 0.03)]),
    ("Fri kartoshka", "Gril", 18000, 200, 10, [("Kartoshka", 0.25), ("O'simlik yog'i", 0.03)]),
    ("Achchiq-chuchuk", "Salatlar", 15000, 250, 5, [("Pomidor", 0.15), ("Bodring", 0.1), ("Piyoz", 0.02)]),
    ("Ko'k choy (choynak)", "Ichimliklar", 8000, 800, 3, [("Ko'k choy (quruq)", 0.005)]),
]
# kategoriya -> sex
CATEGORY_STATION = {"Salatlar": "Sovuq sex", "Ichimliklar": "Bar", "Birinchi taomlar": "Issiq sex",
                    "Ikkinchi taomlar": "Issiq sex", "Gril": "Issiq sex", "Desertlar": "Sovuq sex"}


def _org_code(db: Session) -> str:
    from app.models.company import Company
    while True:
        code = str(random.randint(10000000, 99999999))
        if not db.query(Company.id).filter(Company.org_code == code).first():
            return code


def create_demo(db: Session, password: str = None, pin: str = None) -> dict:
    from app.core.security import hash_password
    from app.models.billing import Tariff
    from app.models.branch import Branch
    from app.models.category import Category
    from app.models.company import Company
    from app.models.currency import Currency
    from app.models.moliya import KassaSession, Wallet
    from app.models.restaurant import KitchenStation
    from app.models.user import User, UserRole, UserStatus, UserWallet
    from app.models.user_company import UserCompany
    from app.services.branch_provisioning import get_default_warehouse, provision_branch
    from app.services.inventory_service import receive_stock
    from app.services.restaurant import get_kitchen_warehouse, settings_for_format
    from app.services.restaurant_menu import create_item, save_card
    from app.services.restaurant_orders import set_pin

    owner_phone = USERS[0][0]
    existing = db.query(User).filter(User.phone == owner_phone).first()
    if existing is not None:
        c = db.get(Company, existing.company_id)
        return {"created": False, "company": c.name if c else None, "org_code": c.org_code if c else None}
    taken = [p for p, *_ in USERS if db.query(User.id).filter(User.phone == p).first()]
    if taken:
        raise RuntimeError(f"Telefon raqamlar band: {taken}")

    password = password or _password()
    pin = pin or _pin()
    now = datetime.now(timezone.utc)
    trial = (db.query(Tariff).filter(Tariff.is_active == True, Tariff.price_per_month <= 0,  # noqa: E712
                                     Tariff.business_type == "restaurant").order_by(Tariff.id).first()
             or db.query(Tariff).filter(Tariff.is_active == True, Tariff.price_per_month <= 0)  # noqa: E712
             .order_by(Tariff.id).first())
    company = Company(name=COMPANY_NAME, org_code=_org_code(db), region="Toshkent shahri", district="Chilonzor",
                      phone=owner_phone, is_active=True, is_trial=True, business_type="restaurant",
                      restaurant_settings=settings_for_format("full_service"),
                      tariff_id=trial.id if trial else None,
                      subscription_starts_at=now, subscription_ends_at=now + timedelta(days=30))
    db.add(company)
    db.flush()
    branch = Branch(name=f"{COMPANY_NAME} (Asosiy)", company_id=company.id, is_active=True, is_main=True)
    db.add(branch)
    db.flush()
    provision_branch(db, branch, create_warehouse=True, create_wallet=True)   # + oshxona, sexlar, zal, stollar
    db.add(Currency(name="O'zbek so'mi", code="UZS", rate=1, is_default=True, is_active=True, company_id=company.id))

    users = {}
    for phone, name, role, perms in USERS:
        u = User(name=name, phone=phone, hashed_password=hash_password(password), role=UserRole(role),
                 branch_id=branch.id, company_id=company.id, status=UserStatus.active, permissions=perms or {})
        db.add(u)
        db.flush()
        db.add(UserCompany(user_id=u.id, company_id=company.id, role=UserRole(role), is_active=True,
                           branch_id=branch.id, permissions=perms or {}))
        users[role if not perms else "waiter"] = u
    set_pin(users["admin"], pin)

    # Kassa: ochiq sessiya bilan, egasi va kassirga biriktirilgan
    wallet = db.query(Wallet).filter(Wallet.company_id == company.id, Wallet.branch_id == branch.id).first()
    wallet.is_open, wallet.opened_at, wallet.opened_by, wallet.closed_at = True, now, users["admin"].id, None
    db.add(KassaSession(wallet_id=wallet.id, company_id=company.id, branch_id=branch.id,
                        opened_by=users["admin"].id, opening_balance=0, status="open"))
    for key in ("admin", "cashier"):
        db.add(UserWallet(user_id=users[key].id, wallet_id=wallet.id, is_default=True, company_id=company.id))

    # Kategoriyalar sexlarga
    stations = {s.name: s.id for s in db.query(KitchenStation).filter(KitchenStation.company_id == company.id)}
    cats = {c.name: c for c in db.query(Category).filter(Category.company_id == company.id)}
    for cname, sname in CATEGORY_STATION.items():
        if cname in cats and sname in stations:
            cats[cname].station_id = stations[sname]

    kitchen = get_kitchen_warehouse(db, company.id, branch.id)
    main_wh = get_default_warehouse(db, company.id, branch.id)
    owner = users["admin"]
    items = {}
    for name, unit, cost, qty in INGREDIENTS:
        p = create_item(db, company.id, {"name": name, "kind": "ingredient", "unit": unit, "cost_price": cost})
        items[name] = p
        receive_stock(db, p.id, Decimal(str(qty)), owner.id, reason="Demo: boshlang'ich qoldiq",
                      reference_type="demo", warehouse_id=kitchen.id, purchase_price=Decimal(str(cost)),
                      company_id=company.id)
    for name, price, cost, qty in GOODS:
        p = create_item(db, company.id, {"name": name, "kind": "goods", "unit": "dona", "sale_price": price,
                                         "cost_price": cost, "category_id": cats["Ichimliklar"].id
                                         if name != "Non" else cats.get("Non", cats["Ichimliklar"]).id})
        items[name] = p
        receive_stock(db, p.id, Decimal(str(qty)), owner.id, reason="Demo: boshlang'ich qoldiq",
                      reference_type="demo", warehouse_id=main_wh.id, purchase_price=Decimal(str(cost)),
                      company_id=company.id)
    for name, out_qty, rows in SEMI:
        p = create_item(db, company.id, {"name": name, "kind": "semi", "unit": "kg"})
        items[name] = p
        save_card(db, company.id, p, {"output_qty": out_qty, "items": [
            {"component_product_id": items[c].id, "gross_qty": q} for c, q in rows]}, owner.id)
    for name, cat, price, weight, minutes, rows in DISHES:
        p = create_item(db, company.id, {"name": name, "kind": "dish", "sale_price": price,
                                         "category_id": cats[cat].id})
        items[name] = p
        save_card(db, company.id, p, {"output_weight_g": weight, "cooking_time_min": minutes, "items": [
            {"component_product_id": items[c].id, "gross_qty": q} for c, q in rows]}, owner.id)
    db.commit()
    return {"created": True, "company": company.name, "org_code": company.org_code,
            "users": [(p, n, "ofitsiant" if perms else r) for p, n, r, perms in USERS],
            "password": password, "owner_pin": pin}


def main():
    from app.database import SessionLocal
    import app.main  # noqa: F401 — barcha modellar ro'yxatdan o'tadi
    db = SessionLocal()
    try:
        res = create_demo(db)
    finally:
        db.close()
    if not res["created"]:
        print(f"Demo allaqachon bor: {res['company']} (korxona kodi {res['org_code']})")
        return
    print(f"Yaratildi: {res['company']}, korxona kodi {res['org_code']}")
    for phone, name, role in res["users"]:
        print(f"  {role:10s} {name:16s} +{phone}  parol: {res['password']}")
    print(f"  Egasining PIN kodi (tasdiqlar uchun): {res['owner_pin']}")


if __name__ == "__main__":
    main()
