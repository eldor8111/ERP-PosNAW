"""
Korxonani barcha ma'lumotlari bilan butunlay o'chirish (Super Admin).

Bog'lanishlar bazaning o'zidan o'qiladi (FK reflection) — modelga kiritilmagan jadvallar ham qamraladi.
Hammasi bitta tranzaksiyada: biror qadam xato bo'lsa, hech narsa o'chmaydi.

Qoidalar:
  * Korxonaga to'g'ridan-to'g'ri bog'langan qatorlar (company_id = X) — o'chiriladi.
  * O'chiriladigan qatorga NOT NULL FK bilan bog'langan qatorlar — o'chiriladi (sale_items va h.k.).
  * Nullable FK: qator boshqa korxonaniki bo'lsa (company_id != X) — faqat bog'lanish NULL qilinadi;
    korxonasi yo'q (company_id ustuni yo'q yoki NULL) bo'lsa — o'chiriladi.
  * Foydalanuvchilar: superadmin, boshqa korxonaga ham a'zo yoki boshqa korxona ma'lumotlarida ishtirok
    etgan foydalanuvchi o'chirilmaydi — faqat shu korxonadan uziladi (company_id/branch_id/role_id → NULL).
  * Boshqa korxonalar (companies jadvali) hech qachon o'chirilmaydi — faqat bog'lanish NULL qilinadi.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

PROTECTED = {"companies", "users"}
TMP = "_purge_"


@dataclass
class Edge:
    child: str        # bog'langan (ishora qiluvchi) jadval
    col: str          # child'dagi FK ustun
    parent: str       # ishora qilinadigan jadval
    pcol: str         # parent'dagi ustun (odatda id)
    nullable: bool


class PurgeError(Exception):
    pass


class _Purger:
    def __init__(self, db: Session, company_id: int):
        self.db = db
        self.cid = company_id
        self.conn = db.connection()
        self.q = self.conn.dialect.identifier_preparer.quote
        self.pg = self.conn.dialect.name == "postgresql"
        self._reflect()
        self.sets: set[str] = set()          # o'chirish to'plami (temp jadval) bor jadvallar
        self.set_null: list[Edge] = []       # saqlanadigan qatorlarda NULL qilinadigan bog'lanishlar
        self.leaf_delete: list[Edge] = []    # bitta PK'si yo'q jadvallar — shart bo'yicha o'chiriladi

    # ── Bazani o'qish ─────────────────────────────────────
    def _reflect(self):
        insp = inspect(self.conn)
        cols = insp.get_multi_columns()
        pks = insp.get_multi_pk_constraint()
        fks = insp.get_multi_foreign_keys()
        self.columns = {k[1]: {c["name"]: c for c in v} for k, v in cols.items()}
        self.pk = {}
        for (_, t), pkc in pks.items():
            cc = pkc.get("constrained_columns") or []
            self.pk[t] = cc[0] if len(cc) == 1 else None
        self.rev: dict[str, list[Edge]] = defaultdict(list)
        for (_, t), lst in fks.items():
            for fk in lst:
                if len(fk["constrained_columns"]) != 1 or len(fk["referred_columns"]) != 1:
                    continue
                if fk.get("referred_schema") not in (None, insp.default_schema_name):
                    continue   # masalan Supabase auth.users — bizning jadvallar emas
                col = fk["constrained_columns"][0]
                self.rev[fk["referred_table"]].append(Edge(
                    child=t, col=col, parent=fk["referred_table"], pcol=fk["referred_columns"][0],
                    nullable=bool(self.columns.get(t, {}).get(col, {}).get("nullable", True)),
                ))

    def has_cid(self, t: str) -> bool:
        return "company_id" in self.columns.get(t, {})

    # ── Temp jadvallar ────────────────────────────────────
    def tmp(self, t: str) -> str:
        return self.q(TMP + t)

    def ensure_set(self, t: str):
        if t in self.sets:
            return
        self.conn.execute(text(f"DROP TABLE IF EXISTS {self.tmp(t)}"))
        self.conn.execute(text(f"CREATE TEMPORARY TABLE {self.tmp(t)} (id BIGINT PRIMARY KEY)"))
        self.sets.add(t)

    def parent_vals(self, e: Edge) -> str:
        """Parent'ning o'chiriladigan qatorlaridagi e.pcol qiymatlari (subquery)."""
        P, ppk = self.q(e.parent), self.q(self.pk[e.parent])
        if e.pcol == self.pk[e.parent]:
            return f"SELECT id FROM {self.tmp(e.parent)}"
        return f"SELECT p.{self.q(e.pcol)} FROM {P} p JOIN {self.tmp(e.parent)} d ON p.{ppk} = d.id"

    def add_rows(self, t: str, where: str, params=None) -> int:
        """t jadvalidan where shartiga mos qatorlarni o'chirish to'plamiga qo'shadi. Yangi qo'shilganlar soni."""
        self.ensure_set(t)
        T, pk = self.q(t), self.q(self.pk[t])
        r = self.conn.execute(text(
            f"INSERT INTO {self.tmp(t)} (id) SELECT r.{pk} FROM {T} r WHERE ({where}) "
            f"AND NOT EXISTS (SELECT 1 FROM {self.tmp(t)} d WHERE d.id = r.{pk})"), params or {})
        return r.rowcount or 0

    # ── Tarqatish ─────────────────────────────────────────
    def propagate(self, start: set[str]):
        changed = set(start)
        while changed:
            nxt = set()
            for parent in sorted(changed):
                for e in self.rev.get(parent, []):
                    if self._edge(e):
                        nxt.add(e.child)
            changed = nxt

    def _edge(self, e: Edge) -> int:
        """Bitta bog'lanish bo'yicha qaror. Yangi o'chiriladigan qatorlar soni (tarqatish davom etishi uchun)."""
        c = f"r.{self.q(e.col)} IN ({self.parent_vals(e)})"
        if e.child in PROTECTED:
            if e.child == "companies" and not e.nullable:
                raise PurgeError(f"Boshqa korxona '{e.parent}' jadvaliga majburiy bog'langan — o'chirib bo'lmaydi")
            if e.nullable:
                self._remember_null(e)
            return 0     # users — alohida hisoblanadi (_users)
        if self.pk.get(e.child) is None:
            self.leaf_delete.append(e)
            return 0
        if not e.nullable:
            return self.add_rows(e.child, c)
        if self.has_cid(e.child):
            n = self.add_rows(e.child, f"{c} AND (r.company_id = :cid OR r.company_id IS NULL)", {"cid": self.cid})
            self._remember_null(e)
            return n
        return self.add_rows(e.child, c)

    def _remember_null(self, e: Edge):
        if e not in self.set_null:
            self.set_null.append(e)

    # ── Foydalanuvchilar ──────────────────────────────────
    def users(self) -> int:
        if "users" not in self.columns:
            return 0
        conds = ["r.company_id = :cid"]
        if "branches" in self.sets:
            conds.append(f"r.branch_id IN (SELECT id FROM {self.tmp('branches')})")
        if "user_companies" in self.columns:
            conds.append("r.id IN (SELECT user_id FROM user_companies WHERE company_id = :cid)")
        keep = ["(r.role IS NULL OR r.role <> 'super_admin')",
                "(r.company_id IS NULL OR r.company_id = :cid)"]
        if "user_companies" in self.columns:
            keep.append("NOT EXISTS (SELECT 1 FROM user_companies uc WHERE uc.user_id = r.id AND uc.company_id <> :cid)")
        # Boshqa korxona ma'lumotlarida ishtirok etgan foydalanuvchi saqlanadi
        for e in self.rev.get("users", []):
            if e.pcol != "id" or not self.has_cid(e.child) or e.child in PROTECTED:
                continue
            keep.append(f"NOT EXISTS (SELECT 1 FROM {self.q(e.child)} x WHERE x.{self.q(e.col)} = r.id "
                        f"AND x.company_id IS NOT NULL AND x.company_id <> :cid)")
        where = f"({' OR '.join(conds)}) AND {' AND '.join(keep)}"
        return self.add_rows("users", where, {"cid": self.cid})

    # ── Bajarish ──────────────────────────────────────────
    def plan(self):
        if self.pg:
            self.conn.execute(text("SET LOCAL statement_timeout = 0"))
        self.ensure_set("companies")
        self.conn.execute(text(f"INSERT INTO {self.tmp('companies')} (id) VALUES (:cid)"), {"cid": self.cid})
        self.propagate({"companies"})
        if self.users():
            self.propagate({"users"})

    def counts(self) -> dict[str, int]:
        out = {}
        for t in sorted(self.sets):
            n = self.conn.execute(text(f"SELECT COUNT(*) FROM {self.tmp(t)}")).scalar() or 0
            if n:
                out[t] = int(n)
        for e in self.leaf_delete:
            n = self.conn.execute(text(
                f"SELECT COUNT(*) FROM {self.q(e.child)} r WHERE r.{self.q(e.col)} IN ({self.parent_vals(e)})")).scalar() or 0
            if n:
                out[e.child] = out.get(e.child, 0) + int(n)
        return out

    def execute(self):
        # 1) Saqlanadigan qatorlardagi bog'lanishlarni uzish
        for e in self.set_null:
            if e.parent not in self.sets:
                continue
            cond = f"{self.q(e.col)} IN ({self.parent_vals(e)})"
            keep = ""
            if e.child in self.sets and self.pk.get(e.child):
                keep = f" AND {self.q(self.pk[e.child])} NOT IN (SELECT id FROM {self.tmp(e.child)})"
            self.conn.execute(text(f"UPDATE {self.q(e.child)} SET {self.q(e.col)} = NULL WHERE {cond}{keep}"))
        # 2) PK'siz jadvallar
        for e in self.leaf_delete:
            self.conn.execute(text(
                f"DELETE FROM {self.q(e.child)} WHERE {self.q(e.col)} IN ({self.parent_vals(e)})"))
        # 3) Asosiy o'chirish: bolalardan ota tomonga; tartib noma'lum bo'lsa — qayta urinish
        pending = [t for t in self.sets]
        stuck_round = False
        while pending:
            progressed = []
            for t in list(pending):
                sp = self.conn.begin_nested()
                try:
                    self.conn.execute(text(
                        f"DELETE FROM {self.q(t)} WHERE {self.q(self.pk[t])} IN (SELECT id FROM {self.tmp(t)})"))
                    sp.commit()
                    progressed.append(t)
                except DBAPIError:
                    sp.rollback()
            for t in progressed:
                pending.remove(t)
            if progressed:
                stuck_round = False
                continue
            if stuck_round:
                raise PurgeError("O'chirib bo'lmadi (bog'lanish halqasi): " + ", ".join(sorted(pending)))
            # Halqani uzish: qolgan jadvallar orasidagi nullable bog'lanishlarni NULL qilish
            self._break_cycles(set(pending))
            stuck_round = True

    def _break_cycles(self, pending: set[str]):
        for parent in pending:
            for e in self.rev.get(parent, []):
                if e.child in pending and e.nullable and self.pk.get(e.child):
                    self.conn.execute(text(
                        f"UPDATE {self.q(e.child)} SET {self.q(e.col)} = NULL "
                        f"WHERE {self.q(self.pk[e.child])} IN (SELECT id FROM {self.tmp(e.child)})"))

    def cleanup(self):
        for t in self.sets:
            try:
                self.conn.execute(text(f"DROP TABLE IF EXISTS {self.tmp(t)}"))
            except DBAPIError:
                pass


def preview_company_purge(db: Session, company_id: int) -> dict[str, int]:
    """Nima o'chishini sanaydi; hech narsa o'zgartirmaydi."""
    p = _Purger(db, company_id)
    try:
        p.plan()
        return p.counts()
    finally:
        db.rollback()


def purge_company(db: Session, company_id: int) -> dict[str, int]:
    """Korxonani barcha ma'lumotlari bilan o'chiradi. Xato bo'lsa — rollback, PurgeError."""
    p = _Purger(db, company_id)
    try:
        p.plan()
        counts = p.counts()
        p.execute()
        p.cleanup()
        db.commit()
        return counts
    except Exception:
        db.rollback()
        raise
