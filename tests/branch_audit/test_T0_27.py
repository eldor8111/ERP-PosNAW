"""T0.27 — mijoz hujjatlari (pasport/shartnoma) va shaxsiy ma'lumotlarga rol bo'yicha ruxsat + audit."""
import os

import pytest

import app.routers.customer_profile as cp
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.customer_document import CustomerDocument
from app.models.user import UserRole

PDF = b"%PDF-1.4 test"


@pytest.fixture(autouse=True)
def _doc_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "DOC_DIR", str(tmp_path / "customer_docs"))


def _customer(db, company):
    c = Customer(name="Mijoz", company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _doc(db, company, customer, user, tmp_path=None):
    rel = f"{company.id}/{customer.id}/f.pdf"
    full = os.path.join(cp.DOC_DIR, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(PDF)
    d = CustomerDocument(customer_id=customer.id, company_id=company.id, file_path=rel,
                         original_name="pasport.pdf", content_type="application/pdf",
                         size=len(PDF), uploaded_by=user.id)
    db.add(d)
    db.flush()
    return d


def _audit(db, action):
    return db.query(AuditLog).filter(AuditLog.action == action).all()


def _setup(db, mk, role):
    c, b, w, admin = mk.tenant()
    user = mk.user(c, role=role, branch=b)
    cust = _customer(db, c)
    doc = _doc(db, c, cust, admin)
    return c, b, user, cust, doc


@pytest.mark.parametrize("role", [UserRole.cashier, UserRole.warehouse, UserRole.accountant])
def test_unauthorized_roles_get_403(db, mk, client, role):
    c, b, user, cust, doc = _setup(db, mk, role)
    cl = client.login(user)
    assert cl.get(f"/api/customers/{cust.id}/documents").status_code == 403
    assert cl.get(f"/api/customers/{cust.id}/documents/{doc.id}/file").status_code == 403
    r = cl.post(f"/api/customers/{cust.id}/documents", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert r.status_code == 403
    assert cl.delete(f"/api/customers/{cust.id}/documents/{doc.id}").status_code == 403
    assert _audit(db, "DOC_DOWNLOAD") == []
    assert db.query(CustomerDocument).filter(CustomerDocument.id == doc.id).first() is not None


@pytest.mark.parametrize("role", [UserRole.admin, UserRole.director, UserRole.manager])
def test_view_roles_list_upload_download(db, mk, client, role):
    c, b, user, cust, doc = _setup(db, mk, role)
    cl = client.login(user)
    r = cl.get(f"/api/customers/{cust.id}/documents")
    assert r.status_code == 200 and len(r.json()) == 1

    r = cl.post(f"/api/customers/{cust.id}/documents", files={"file": ("yangi.pdf", PDF, "application/pdf")})
    assert r.status_code == 201
    new_id = r.json()["id"]
    logs = _audit(db, "DOC_UPLOAD")
    assert len(logs) == 1
    assert logs[0].user_id == user.id and logs[0].entity_type == "customer_document" and logs[0].entity_id == new_id
    assert logs[0].new_values["customer_id"] == cust.id
    assert logs[0].new_values["original_name"] == "yangi.pdf"
    assert logs[0].new_values["size"] == len(PDF)

    r = cl.get(f"/api/customers/{cust.id}/documents/{doc.id}/file")
    assert r.status_code == 200 and r.content == PDF
    logs = _audit(db, "DOC_DOWNLOAD")
    assert len(logs) == 1 and logs[0].user_id == user.id and logs[0].entity_id == doc.id


def test_download_audit_is_committed(db, mk, client, monkeypatch):
    c, b, user, cust, doc = _setup(db, mk, UserRole.manager)
    commits = []
    orig = db.commit
    monkeypatch.setattr(db, "commit", lambda: (commits.append(1), orig())[1])
    assert client.login(user).get(f"/api/customers/{cust.id}/documents/{doc.id}/file").status_code == 200
    assert commits, "yuklab olishdan keyin commit chaqirilishi kerak"


def test_manager_cannot_delete(db, mk, client):
    c, b, user, cust, doc = _setup(db, mk, UserRole.manager)
    assert client.login(user).delete(f"/api/customers/{cust.id}/documents/{doc.id}").status_code == 403
    assert db.query(CustomerDocument).filter(CustomerDocument.id == doc.id).first() is not None
    assert _audit(db, "DOC_DELETE") == []


@pytest.mark.parametrize("role", [UserRole.admin, UserRole.director])
def test_admin_director_delete_with_audit(db, mk, client, role):
    c, b, user, cust, doc = _setup(db, mk, role)
    r = client.login(user).delete(f"/api/customers/{cust.id}/documents/{doc.id}")
    assert r.status_code == 204
    assert db.query(CustomerDocument).filter(CustomerDocument.id == doc.id).first() is None
    logs = _audit(db, "DOC_DELETE")
    assert len(logs) == 1 and logs[0].user_id == user.id and logs[0].entity_id == doc.id
    assert logs[0].old_values == {"customer_id": cust.id, "original_name": "pasport.pdf"}


def test_cross_company_isolation_404(db, mk, client):
    ca, ba, wa, admin_a = mk.tenant()
    cb, bb, wb, admin_b = mk.tenant()
    cust_b = _customer(db, cb)
    doc_b = _doc(db, cb, cust_b, admin_b)
    cl = client.login(admin_a)
    assert cl.get(f"/api/customers/{cust_b.id}/documents").status_code == 404
    assert cl.get(f"/api/customers/{cust_b.id}/documents/{doc_b.id}/file").status_code == 404
    assert cl.post(f"/api/customers/{cust_b.id}/documents",
                   files={"file": ("a.pdf", PDF, "application/pdf")}).status_code == 404
    assert cl.delete(f"/api/customers/{cust_b.id}/documents/{doc_b.id}").status_code == 404
    assert db.query(CustomerDocument).filter(CustomerDocument.id == doc_b.id).first() is not None
    # o'z korxonasi ishlaydi
    cust_a = _customer(db, ca)
    assert cl.get(f"/api/customers/{cust_a.id}/documents").status_code == 200


def test_max_docs_counted_per_company(db, mk, client, monkeypatch):
    monkeypatch.setattr(cp, "MAX_DOCS_PER_CUSTOMER", 1)
    c, b, user, cust, doc = _setup(db, mk, UserRole.admin)
    r = client.login(user).post(f"/api/customers/{cust.id}/documents",
                                files={"file": ("a.pdf", PDF, "application/pdf")})
    assert r.status_code == 400


def test_photo_endpoints_not_role_restricted(db, mk, client, tmp_path, monkeypatch):
    """Agent mobil ilovasi upload_customer_photo ni chaqiradi — rasm endpointlari yopilmagan."""
    monkeypatch.setattr(cp, "PHOTO_DIR", str(tmp_path / "photos"))
    c, b, w, cashier = mk.tenant(role=UserRole.cashier)
    cust = _customer(db, c)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    r = client.login(cashier).post(f"/api/customers/{cust.id}/photo", files={"file": ("a.png", png, "image/png")})
    assert r.status_code == 200


def test_delete_customer_files_helper(db, mk):
    c, b, w, admin = mk.tenant()
    cust = _customer(db, c)
    doc = _doc(db, c, cust, admin)
    path = os.path.join(cp.DOC_DIR, doc.file_path)
    assert os.path.isfile(path)
    cp.delete_customer_files(db, cust)
    db.flush()
    assert not os.path.isfile(path)
    assert db.query(CustomerDocument).filter(CustomerDocument.customer_id == cust.id).count() == 0
