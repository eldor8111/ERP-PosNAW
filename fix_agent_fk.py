"""
Agent FK constraint ni ON DELETE SET NULL ga o'zgartiradi.
Run: python fix_agent_fk.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Mavjud FK constraint nomini topamiz
    result = conn.execute(text("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = 'companies'
          AND constraint_type = 'FOREIGN KEY'
          AND constraint_name LIKE '%agent%';
    """))
    rows = result.fetchall()
    print("Topilgan constraint lar:", rows)

    for row in rows:
        fk_name = row[0]
        print(f"Dropping: {fk_name}")
        conn.execute(text(f'ALTER TABLE companies DROP CONSTRAINT IF EXISTS "{fk_name}";'))

    # Yangi constraint qo'shamiz — ON DELETE SET NULL
    conn.execute(text("""
        ALTER TABLE companies
        ADD CONSTRAINT companies_agent_id_fkey
        FOREIGN KEY (agent_id)
        REFERENCES agents(id)
        ON DELETE SET NULL;
    """))
    conn.commit()
    print("OK FK constraint muvaffaqiyatli yangilandi (ON DELETE SET NULL).")
