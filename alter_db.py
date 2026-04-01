from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg://postgres:postgres@localhost:5432/erppos')

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE purchase_orders ADD COLUMN paid_amount NUMERIC(14,2) DEFAULT 0;"))
    conn.execute(text("ALTER TABLE purchase_orders ADD COLUMN discount_amount NUMERIC(14,2) DEFAULT 0;"))
    conn.execute(text("ALTER TABLE purchase_orders ADD COLUMN payment_type VARCHAR(20) DEFAULT 'cash';"))
    conn.commit()

print("DB ALTERED SUCCESSFULLY")
