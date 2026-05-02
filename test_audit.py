import traceback
from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres')
with engine.connect() as conn:
    res = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'audit_logs')")).fetchone()
    print("Does audit_logs exist?", res)
