"""E-code AI yordamchi (Claude): kvota va limitlar, tenant izolyatsiyasi, rollar, tasdiqsiz amal bajarilmasligi,
narx hisobi, append-only tarix, busy lock, fayl egaligi, paket sotib olish.

Claude API chaqirilmaydi: soxta mijoz oldindan yozilgan javoblarni qaytaradi va har bir so'rovni saqlaydi.
"""
import copy
import itertools
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from anthropic.types import CacheCreation, Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

from app.config import settings
from app.models.ai_assistant import AiConversation, AiFile, AiMessage
from app.models.billing import BalanceLog, CompanyPackage, FeaturePackage
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.pending_action import PendingAction
from app.models.product import Product
from app.models.user import UserRole
from app.services import ai_assistant as svc
from app.services import ai_packages

_seq = itertools.count(1)


# ─── soxta Claude mijozi ─────────────────────────────────────────────────────

def _usage(inp=100, out=50, read=0, w1h=0, w5m=0):
    return Usage(input_tokens=inp, output_tokens=out, cache_read_input_tokens=read,
                 cache_creation_input_tokens=w1h + w5m,
                 cache_creation=CacheCreation(ephemeral_1h_input_tokens=w1h, ephemeral_5m_input_tokens=w5m))


def reply_text(text, **u):
    return Message(id=f"m{next(_seq)}", type="message", role="assistant", model="claude-sonnet-5-5",
                   content=[ThinkingBlock(type="thinking", thinking="", signature=f"sig{next(_seq)}"),
                            TextBlock(type="text", text=text)],
                   stop_reason="end_turn", stop_sequence=None, usage=_usage(**u))


def reply_tool(name, args, stop="tool_use", **u):
    return Message(id=f"m{next(_seq)}", type="message", role="assistant", model="claude-sonnet-5-5",
                   content=[ThinkingBlock(type="thinking", thinking="", signature=f"sig{next(_seq)}"),
                            ToolUseBlock(type="tool_use", id=f"toolu_{next(_seq)}", name=name, input=args)],
                   stop_reason=stop, stop_sequence=None, usage=_usage(**u))


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for b in self.msg.content:
            if b.type == "text":
                yield SimpleNamespace(type="text", text=b.text)
            else:
                yield SimpleNamespace(type="content_block_start", content_block=b)

    def get_final_message(self):
        return self.msg


class FakeClient:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.files = SimpleNamespace(upload=self._upload)

    def _stream(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        return _Stream(self.script.pop(0))

    def _upload(self, file, expires_in_seconds):
        return SimpleNamespace(id=f"file_{next(_seq)}")


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    def install(*script):
        c = FakeClient(*script)
        monkeypatch.setattr(svc, "_client", c)
        return c
    return install


# ─── ma'lumotlar ─────────────────────────────────────────────────────────────

def _package(db, code="ai_assistant", **kw):
    p = db.query(FeaturePackage).filter(FeaturePackage.code == code).first()
    if not p:
        p = FeaturePackage(code=code, name=kw.pop("name", "AI yordamchi"), price_per_month=kw.pop("price", 100000),
                           is_active=True, sort_order=90)
        db.add(p)
    for k, v in kw.items():
        setattr(p, k, v)
    db.flush()
    return p


def _grant(db, company, code="ai_assistant", days=30, **pkg):
    _package(db, code, **pkg)
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code=code, starts_at=now, ends_at=now + timedelta(days=days),
                          is_active=True))
    db.flush()


def _product(db, company, wh=None, qty=0, name=None, **kw):
    n = next(_seq)
    p = Product(name=name or f"AI Tovar {n}", sku=f"AI-{n}", barcode=kw.pop("barcode", f"AIBC{n:06d}"),
                company_id=company.id, cost_price=Decimal("500"), sale_price=Decimal("1000"), **kw)
    db.add(p)
    db.flush()
    if wh is not None:
        db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
        db.flush()
    return p


def _stock(db, product, wh):
    db.expire_all()
    return sum((s.quantity for s in db.query(StockLevel).filter(StockLevel.product_id == product.id,
                                                                  StockLevel.warehouse_id == wh.id).all()), Decimal("0"))


def _events(resp):
    out = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _chat(client, user, message, conversation_id=None, file_ids=None):
    c = client.login(user)
    return c.post("/api/ai/assistant/chat", json={"conversation_id": conversation_id, "message": message,
                                                  "file_ids": file_ids or []})


# ─── kvota va paket ──────────────────────────────────────────────────────────

def test_chat_without_package_is_402(mk, client, fake):
    c, b, w, u = mk.tenant()
    fake(reply_text("salom"))
    r = _chat(client, u, "salom")
    assert r.status_code == 402
    st = client.login(u).get("/api/ai/assistant/status").json()
    assert st["active"] is False and st["can_chat"] is False


def test_monthly_limit_429_and_month_boundary(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c, ai_monthly_limit=2)
    conv = AiConversation(company_id=c.id, user_id=u.id, model="claude-sonnet-5-5", context={"system": [], "tools": []})
    db.add(conv)
    db.flush()
    m0, _ = ai_packages.month_bounds()
    # o'tgan oyning oxirgi daqiqasi — bu oyga sanalmaydi
    db.add(AiMessage(conversation_id=conv.id, company_id=c.id, user_id=u.id, role="user", kind="prompt",
                     content=[], text="eski", created_at=m0 - timedelta(minutes=1)))
    db.add(AiMessage(conversation_id=conv.id, company_id=c.id, user_id=u.id, role="user", kind="prompt",
                     content=[], text="1", created_at=m0 + timedelta(minutes=1)))
    db.flush()
    assert ai_packages.usage(db, c.id, u.id)["month_used"] == 1
    fake(reply_text("javob"))
    assert _chat(client, u, "savol").status_code == 200
    r = _chat(client, u, "yana savol")
    assert r.status_code == 429 and "oy" in r.json()["detail"]


def test_daily_user_limit_429(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c, ai_daily_user_limit=1)
    fake(reply_text("bir"))
    assert _chat(client, u, "savol").status_code == 200
    r = _chat(client, u, "ikkinchi")
    assert r.status_code == 429


def test_expired_package_is_402(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c, days=-1)
    assert _chat(client, u, "salom").status_code == 402


# ─── oqim, narx, append-only ─────────────────────────────────────────────────

def test_cost_calculation():
    u = _usage(inp=1000, out=500, read=2000, w1h=3000, w5m=400)
    # 1000*2 + 2000*0.2 + 3000*4 + 400*2.5 + 500*10 = 2000+400+12000+1000+5000 = 20400 / 1e6
    assert svc.cost_usd("claude-sonnet-5-5", u) == Decimal("0.0204")


def test_chat_stream_saves_tokens_and_cost(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    f = fake(reply_text("Bugun savdo yo'q.", inp=1000, out=500, read=2000, w1h=3000))
    r = _chat(client, u, "Bugun savdo qancha?")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = _events(r)
    assert [e["type"] for e in ev][0] == "start"
    assert "".join(e["text"] for e in ev if e["type"] == "delta") == "Bugun savdo yo'q."
    done = [e for e in ev if e["type"] == "done"][0]
    assert done["cost_usd"] == pytest.approx(0.0194)
    db.expire_all()
    conv = db.query(AiConversation).filter(AiConversation.user_id == u.id).one()
    rows = db.query(AiMessage).filter(AiMessage.conversation_id == conv.id).order_by(AiMessage.id).all()
    assert [(x.role, x.kind) for x in rows] == [("user", "prompt"), ("assistant", "response")]
    assert rows[1].input_tokens == 1000 and rows[1].cache_read_tokens == 2000 and rows[1].cache_write_tokens == 3000
    assert Decimal(str(rows[1].cost_usd)) == Decimal("0.0194")
    assert conv.busy_until is None and conv.turns == 1
    call = f.calls[0]
    assert call["model"] == "claude-sonnet-5-5" and call["output_config"] == {"effort": "medium"}
    assert call["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert call["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in call and "temperature" not in call
    assert all(t.get("eager_input_streaming") for t in call["tools"])
    assert [t["name"] for t in call["tools"]] == sorted(t["name"] for t in call["tools"])


def test_history_is_append_only_and_thinking_preserved(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    p = _product(db, c, w, qty=7, name="Paracetamol 500 mg")
    f = fake(reply_tool("match_products", {"query": "Paracetamol"}), reply_text("Qoldiq: 7 dona."),
             reply_text("Yana nima kerak?"))
    r = _chat(client, u, "Paracetamol qancha qoldi?")
    ev = _events(r)
    assert any(e["type"] == "tool" and e["name"] == "match_products" for e in ev)
    conv_id = ev[0]["conversation_id"]
    _chat(client, u, "rahmat", conversation_id=conv_id)
    first, second, third = f.calls
    # har bir keyingi so'rov oldingisining davomi: oldingi xabarlar aynan o'zgarishsiz
    assert second["messages"][:len(first["messages"])] == first["messages"]
    assert third["messages"][:len(second["messages"])] == second["messages"]
    assert third["system"] == first["system"] and third["tools"] == first["tools"]
    asst = second["messages"][1]
    assert asst["role"] == "assistant" and asst["content"][0]["type"] == "thinking"
    assert asst["content"][0]["signature"].startswith("sig")
    tool_result = second["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result" and "Paracetamol 500 mg" in tool_result["content"]
    assert f"id={p.id}" in tool_result["content"]


def test_busy_conversation_is_409(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    fake(reply_text("bir"))
    ev = _events(_chat(client, u, "salom"))
    conv = db.get(AiConversation, ev[0]["conversation_id"])
    conv.busy_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=60)
    db.flush()
    r = _chat(client, u, "yana", conversation_id=conv.id)
    assert r.status_code == 409


def test_invalid_tool_input_is_not_executed(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    p = _product(db, c, w, qty=5)
    f = fake(reply_tool("receive_goods", {"items": [{"product_id": p.id}]}), reply_text("Miqdorni ayting."))
    _chat(client, u, "kirim qil")
    res = f.calls[1]["messages"][-1]["content"][0]
    assert res.get("is_error") is True and "quantity" in res["content"]
    assert db.query(PendingAction).filter(PendingAction.company_id == c.id).count() == 0


def test_max_tokens_tool_use_is_not_executed(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    p = _product(db, c, w, qty=5)
    f = fake(reply_tool("receive_goods", {"items": [{"product_id": p.id, "quantity": 3}]}, stop="max_tokens"),
             reply_text("Qisqaroq qilib yozing."))
    _chat(client, u, "kirim")
    assert f.calls[1]["messages"][-1]["content"][0]["is_error"] is True
    assert db.query(PendingAction).filter(PendingAction.company_id == c.id).count() == 0


# ─── amallar: tasdiqsiz bajarilmaydi ─────────────────────────────────────────

def test_action_runs_only_after_confirm(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    p = _product(db, c, w, qty=10)
    f = fake(reply_tool("receive_goods", {"items": [{"product_id": p.id, "quantity": 5, "purchase_price": 600}],
                                          "warehouse_id": w.id}),
             reply_text("Tasdiqlash tugmasini bosing."), reply_text("Kirim saqlandi."))
    ev = _events(_chat(client, u, "5 ta kirim qil"))
    cards = [e["action"] for e in ev if e["type"] == "action"]
    assert len(cards) == 1 and cards[0]["type"] == "confirm" and cards[0]["total"].startswith("3 000")
    assert _stock(db, p, w) == Decimal("10")          # hali bajarilmagan
    tr = f.calls[1]["messages"][-1]["content"][0]["content"]
    assert "HALI BAJARILMADI" in tr
    cid = cards[0]["confirmation_id"]
    r = client.login(u).post(f"/api/ai/assistant/actions/{cid}/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert _stock(db, p, w) == Decimal("15")
    # ikkinchi marta tasdiqlab bo'lmaydi
    assert client.login(u).post(f"/api/ai/assistant/actions/{cid}/confirm").status_code == 409
    # natija keyingi savolda tizim eslatmasi bo'lib boradi; ekran ko'rinishida karta holati "executed"
    conv_id = ev[0]["conversation_id"]
    _chat(client, u, "bo'ldimi?", conversation_id=conv_id)
    head = f.calls[2]["messages"][-1]["content"][0]["text"]
    assert "TASDIQLADI" in head
    view = client.login(u).get(f"/api/ai/assistant/conversations/{conv_id}").json()
    acts = [a for m in view["messages"] for a in m.get("actions", [])]
    assert acts and acts[0]["status"] == "executed"


def test_cancel_does_not_execute(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    p = _product(db, c, w, qty=10)
    fake(reply_tool("stock_out", {"items": [{"product_id": p.id, "quantity": 4}], "type": "brak",
                                  "warehouse_id": w.id}), reply_text("Tasdiqlang."))
    ev = _events(_chat(client, u, "4 ta brak"))
    cid = [e["action"] for e in ev if e["type"] == "action"][0]["confirmation_id"]
    r = client.login(u).post(f"/api/ai/assistant/actions/{cid}/cancel")
    assert r.status_code == 200
    assert _stock(db, p, w) == Decimal("10")
    assert db.get(PendingAction, cid).status == "cancelled"
    assert "BEKOR" in (db.get(AiConversation, ev[0]["conversation_id"]).pending_note or "")


def test_debt_adjust_via_ui_service(db, mk, client, fake):
    c, b, w, u = mk.tenant(role=UserRole.director)
    _grant(db, c)
    cust = Customer(name="Ali Valiyev", phone="998901112233", company_id=c.id, debt_balance=Decimal("0"),
                    debt_balances={})
    db.add(cust)
    db.flush()
    fake(reply_tool("adjust_customer_debt", {"customer_id": cust.id, "delta": 50000, "reason": "nasiya"}),
         reply_text("Tasdiqlang."))
    ev = _events(_chat(client, u, "Aliga 50 ming nasiya yoz"))
    cid = [e["action"] for e in ev if e["type"] == "action"][0]["confirmation_id"]
    db.expire_all()
    assert Decimal(str(db.get(Customer, cust.id).debt_balance or 0)) == 0
    assert client.login(u).post(f"/api/ai/assistant/actions/{cid}/confirm").json()["ok"] is True
    db.expire_all()
    assert Decimal(str(db.get(Customer, cust.id).debt_balance)) == Decimal("50000")


# ─── rollar ──────────────────────────────────────────────────────────────────

def _names(user, allow=True):
    return {t["name"] for t in svc.tools_for(user, allow)}


def test_role_tool_sets(mk):
    c = mk.company()
    admin = mk.user(c, role=UserRole.admin)
    manager = mk.user(c, role=UserRole.manager)
    cashier = mk.user(c, role=UserRole.cashier)
    keeper = mk.user(c, role=UserRole.warehouse)
    acct = mk.user(c, role=UserRole.accountant)
    actions = {"receive_goods", "stock_out", "adjust_customer_debt", "accept_debt_payment", "add_product"}
    sensitive = {"get_profit_today", "get_product_profit"}
    assert actions | sensitive <= _names(admin)
    assert {"receive_goods", "stock_out", "add_product"} <= _names(manager)
    assert not {"adjust_customer_debt", "accept_debt_payment"} & _names(manager)
    for ro in (cashier, keeper):
        n = _names(ro)
        assert not (actions | sensitive) & n and "match_products" in n and "get_sales_summary" in n
    assert sensitive <= _names(acct) and not actions & _names(acct)
    assert not actions & _names(admin, allow=False)


def test_cashier_sees_no_cost_and_cannot_chat_tools(db, mk, client, fake):
    c, b, w, cashier = mk.tenant(role=UserRole.cashier)
    _grant(db, c)
    _product(db, c, w, qty=3, name="Aspirin")
    f = fake(reply_tool("match_products", {"query": "Aspirin"}),
             reply_tool("get_profit_today", {"period": "today"}), reply_text("Ruxsat yo'q."))
    _chat(client, cashier, "aspirin")
    tr = f.calls[1]["messages"][-1]["content"][0]["content"]
    assert "Aspirin" in tr and "tannarx" not in tr
    denied = f.calls[2]["messages"][-1]["content"][0]
    assert denied["is_error"] is True and "ruxsat" in denied["content"]


def test_courier_cannot_chat(mk, client, fake):
    c = mk.company()
    courier = mk.user(c, role=UserRole.courier)
    assert _chat(client, courier, "salom").status_code == 403


def test_role_downgrade_blocks_confirm(db, mk, client, fake):
    c, b, w, u = mk.tenant(role=UserRole.admin)
    _grant(db, c)
    p = _product(db, c, w, qty=1)
    fake(reply_tool("receive_goods", {"items": [{"product_id": p.id, "quantity": 2}], "warehouse_id": w.id}),
         reply_text("Tasdiqlang."))
    ev = _events(_chat(client, u, "kirim"))
    cid = [e["action"] for e in ev if e["type"] == "action"][0]["confirmation_id"]
    u.role = UserRole.cashier
    db.flush()
    assert client.login(u).post(f"/api/ai/assistant/actions/{cid}/confirm").status_code == 403
    assert _stock(db, p, w) == Decimal("1")


# ─── tenant izolyatsiyasi ────────────────────────────────────────────────────

def test_tenant_isolation(db, mk, client, fake):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    _grant(db, ca)
    _grant(db, cb)
    pa = _product(db, ca, wa, qty=9, name="Maxfiy Tovar A")
    fake(reply_tool("receive_goods", {"items": [{"product_id": pa.id, "quantity": 1}], "warehouse_id": wa.id}),
         reply_text("Tasdiqlang."))
    ev = _events(_chat(client, ua, "kirim"))
    conv_a = ev[0]["conversation_id"]
    cid = [e["action"] for e in ev if e["type"] == "action"][0]["confirmation_id"]
    cb_client = client.login(ub)
    assert cb_client.get(f"/api/ai/assistant/conversations/{conv_a}").status_code == 404
    assert cb_client.post(f"/api/ai/assistant/actions/{cid}/confirm").status_code == 404
    assert all(x["id"] != conv_a for x in cb_client.get("/api/ai/assistant/conversations").json())
    # B korxonasi qidiruvi A mahsulotini ko'rmaydi; A mahsulotiga kirim tayyorlab bo'lmaydi
    f = fake(reply_tool("match_products", {"query": "Maxfiy Tovar"}),
             reply_tool("receive_goods", {"items": [{"product_id": pa.id, "quantity": 1}]}), reply_text("Topilmadi."))
    _chat(client, ub, "Maxfiy tovar")
    assert "topilmadi" in f.calls[1]["messages"][-1]["content"][0]["content"]
    bad = f.calls[2]["messages"][-1]["content"][0]
    assert bad["is_error"] is True
    assert db.query(PendingAction).filter(PendingAction.company_id == cb.id).count() == 0
    assert _stock(db, pa, wa) == Decimal("9")


def test_file_ownership(db, mk):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    db.add(AiFile(file_id="file_A", company_id=ca.id, user_id=ua.id, media_type="image/jpeg",
                  expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)))
    db.add(AiFile(file_id="file_old", company_id=ca.id, user_id=ua.id, media_type="image/jpeg",
                  expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)))
    db.flush()
    assert svc.own_files(db, ua, ["file_A"]) == ["file_A"]
    with pytest.raises(svc.AssistantError):
        svc.own_files(db, ub, ["file_A"])
    with pytest.raises(svc.AssistantError):
        svc.own_files(db, ua, ["file_old"])
    with pytest.raises(svc.AssistantError):
        svc.own_files(db, ua, ["a", "b", "c", "d", "e"])


def test_image_upload_and_chat_with_image(db, mk, client, fake):
    import io
    from PIL import Image
    c, b, w, u = mk.tenant()
    _grant(db, c)
    f = fake(reply_text("Nakladnoyda 2 qator bor."))
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), "white").save(buf, format="PNG")
    r = client.login(u).post("/api/ai/assistant/upload", files={"file": ("n.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    meta = r.json()
    assert max(meta["width"], meta["height"]) <= 1568
    _chat(client, u, "o'qi", file_ids=[meta["file_id"]])
    blocks = f.calls[0]["messages"][-1]["content"]
    assert {"type": "image", "source": {"type": "file", "file_id": meta["file_id"]}} in blocks


# ─── paket sotib olish ───────────────────────────────────────────────────────

def test_ai_package_purchase(db, mk, client):
    c, b, w, admin = mk.tenant()
    c.balance = Decimal("1000000")
    _package(db, "ai_assistant", price=100000)
    _package(db, "ai_assistant_pro", name="AI Pro", price=200000)
    db.flush()
    cl = client.login(admin)
    assert cl.post("/api/billing/my-company/packages/subscribe",
                   json={"package_code": "ai_assistant", "months": 2}).status_code == 400
    r = cl.post("/api/billing/my-company/packages/subscribe", json={"package_code": "ai_assistant", "months": 3})
    assert r.status_code == 200, r.text
    log = db.query(BalanceLog).filter(BalanceLog.company_id == c.id).order_by(BalanceLog.id.desc()).first()
    assert log.log_type == "ai_subscription" and Decimal(str(log.amount)) == Decimal("-300000")
    assert ai_packages.access_for(db, c.id).active
    # boshqa daraja faol paket tugaguncha sotib olinmaydi
    assert cl.post("/api/billing/my-company/packages/subscribe",
                   json={"package_code": "ai_assistant_pro", "months": 1}).status_code == 409
    cashier = mk.user(c, role=UserRole.cashier)
    assert client.login(cashier).post("/api/billing/my-company/packages/subscribe",
                                      json={"package_code": "ai_assistant", "months": 1}).status_code == 403


def test_super_admin_packages_and_usage(db, mk, client):
    sa = mk.user(None, role=UserRole.super_admin)
    cl = client.login(sa)
    r = cl.post("/api/ai/assistant/admin/packages", json={"code": "pro", "name": "AI Pro", "price_per_month": 250000,
                                                          "ai_monthly_limit": 3000, "is_active": True})
    assert r.status_code == 200 and r.json()["code"] == "ai_assistant_pro"
    assert any(p["code"] == "ai_assistant_pro" for p in cl.get("/api/ai/assistant/admin/packages").json())
    rep = cl.get("/api/ai/assistant/admin/usage").json()
    assert "items" in rep and "total_cost_usd" in rep
    c, b, w, admin = mk.tenant()
    assert client.login(admin).get("/api/ai/assistant/admin/usage").status_code == 403


def reply_text_tool(text, name, args):
    return Message(id=f"m{next(_seq)}", type="message", role="assistant", model="claude-sonnet-5-5",
                   content=[TextBlock(type="text", text=text),
                            ToolUseBlock(type="tool_use", id=f"toolu_{next(_seq)}", name=name, input=args)],
                   stop_reason="tool_use", stop_sequence=None, usage=_usage())


def test_text_rounds_are_separated(db, mk, client, fake):
    c, b, w, u = mk.tenant()
    _grant(db, c)
    fake(reply_text_tool("Qidiryapman.", "match_products", {"query": "Aspirin"}), reply_text("Topilmadi."))
    ev = _events(_chat(client, u, "aspirin bormi"))
    assert "".join(e["text"] for e in ev if e["type"] == "delta") == "Qidiryapman.\n\nTopilmadi."


def test_match_products_spelling_variants(db, mk):
    from app.services.ai_assistant_tools import MatchProductsTool
    c, b, w, u = mk.tenant()
    _product(db, c, w, qty=5, name="Paracetamol 500 mg")
    _product(db, c, w, qty=5, name="Nazol ксилометазолин 0,1%")   # SQLite: kirillda faqat kichik harf
    r = MatchProductsTool().execute(db, c.id, u, query="Paratsetamol")["reply"]
    assert "Paracetamol 500 mg" in r
    r = MatchProductsTool().execute(db, c.id, u, query="Ksilometazolin")["reply"]
    assert "ксилометазолин" in r
