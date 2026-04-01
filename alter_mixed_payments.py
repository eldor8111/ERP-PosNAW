from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg://postgres:postgres@localhost:5432/erppos')

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE sales ADD COLUMN paid_cash NUMERIC(14,2) DEFAULT 0;"))
        print("added paid_cash column")
    except Exception as e:
        print(f"Error adding paid_cash: {e}")

    try:
        conn.execute(text("ALTER TABLE sales ADD COLUMN paid_card NUMERIC(14,2) DEFAULT 0;"))
        print("added paid_card column")
    except Exception as e:
        print(f"Error adding paid_card: {e}")

    conn.commit()

print("DB ALTERED SUCCESSFULLY")
