"""deploy/create_restaurant_demo.py: demo restoran yaratiladi, takroriy chaqiruv xavfsiz va to'liq oqim ishlaydi
(chek ochish, oshxonaga yuborish, to'lov, ingredient yechilishi)."""
from decimal import Decimal

from app.models.company import Company
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.restaurant import Hall, RestaurantTable
from app.models.user import User
from app.services.restaurant import get_kitchen_warehouse
from deploy.create_restaurant_demo import USERS, create_demo


def test_demo_created_once_and_full_flow(db, client):
    res = create_demo(db)
    assert res["created"] is True
    c = db.query(Company).filter(Company.org_code == res["org_code"]).one()
    assert c.business_type == "restaurant"
    owner = db.query(User).filter(User.phone == USERS[0][0]).one()
    cashier = db.query(User).filter(User.phone == USERS[1][0]).one()
    assert owner.pin_hash
    dishes = {p.name: p for p in db.query(Product).filter(Product.company_id == c.id, Product.item_kind == "dish")}
    assert len(dishes) == 7
    menu = client.login(owner).get("/api/restaurant/menu/items", params={"kind": "dish"}).json()
    assert all(m["has_card"] for m in menu) and all(m["food_cost_pct"] for m in menu)

    again = create_demo(db)
    assert again["created"] is False and again["org_code"] == res["org_code"]

    # kassir: stol -> osh x2 + cola -> oshxona -> to'lov
    hall = db.query(Hall).filter(Hall.company_id == c.id).one()
    table = db.query(RestaurantTable).filter(RestaurantTable.hall_id == hall.id).first()
    cl = client.login(cashier)
    oid = cl.post("/api/restaurant/orders", json={"table_id": table.id, "guests": 2}).json()["id"]
    cola = db.query(Product).filter(Product.company_id == c.id, Product.name == "Coca-Cola 0.5").one()
    cl.post(f"/api/restaurant/orders/{oid}/items", json={"items": [
        {"product_id": dishes["Osh"].id, "quantity": 2}, {"product_id": cola.id}]})
    assert cl.post(f"/api/restaurant/orders/{oid}/send", json={}).status_code == 200
    r = cl.post(f"/api/restaurant/orders/{oid}/pay", json={"payments": [{"type": "cash", "amount": 200000}]})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 110000          # 2*45000 + 10000 + 10% xizmat
    rice = db.query(Product).filter(Product.company_id == c.id, Product.name == "Guruch").one()
    kitchen = get_kitchen_warehouse(db, c.id, owner.branch_id)
    q = db.query(StockLevel.quantity).filter(StockLevel.product_id == rice.id, StockLevel.warehouse_id == kitchen.id).scalar()
    assert Decimal(str(q)) == Decimal("24.700")
