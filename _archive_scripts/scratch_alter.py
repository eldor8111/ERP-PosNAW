from sqlalchemy import create_engine, text

def alter():
    engine = create_engine("postgresql+psycopg://postgres:postgres@localhost:5432/erppos")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE company_bots ADD COLUMN notify_expired_products BOOLEAN DEFAULT true"))
            print("Added notify_expired_products")
        except Exception as e:
            print(e)
            
        try:
            conn.execute(text("ALTER TABLE company_bots ADD COLUMN expired_days_before INTEGER DEFAULT 7"))
            print("Added expired_days_before")
        except Exception as e:
            print(e)
        conn.commit()

if __name__ == "__main__":
    alter()
