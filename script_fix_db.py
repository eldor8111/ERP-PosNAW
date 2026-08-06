from sqlalchemy import create_engine, text
from app.config import settings

# Construct the exact database URL from settings
db_url = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
engine = create_engine(db_url)

with engine.begin() as conn:
    # Update alembic_version to the base revision before our changes
    conn.execute(text("UPDATE alembic_version SET version_num = 'u6v7w8x9y0z1'"))
    print("Alembic version forcefully updated to u6v7w8x9y0z1")
