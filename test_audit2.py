import traceback
from sqlalchemy import create_engine, text

engine = create_engine('postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres')
with engine.connect() as conn:
    res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'audit_logs'")).fetchall()
    print("audit_logs columns:", res)
