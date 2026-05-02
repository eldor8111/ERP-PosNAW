import traceback
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)

try:
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_companies (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                role userrole NOT NULL DEFAULT 'cashier',
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_user_company UNIQUE (user_id, company_id)
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_companies_user_id ON user_companies (user_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_companies_company_id ON user_companies (company_id);"))
        conn.execute(text("COMMIT"))
        print("Successfully created user_companies table!")
except Exception as e:
    traceback.print_exc()

