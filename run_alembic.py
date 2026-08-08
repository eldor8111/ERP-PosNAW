import os
from dotenv import load_dotenv
load_dotenv()
os.system('alembic revision --autogenerate -m "add debt_amounts to sales"')
