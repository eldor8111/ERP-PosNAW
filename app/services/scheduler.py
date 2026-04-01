import asyncio
from datetime import datetime, date
import httpx
from app.database import SessionLocal  # type: ignore
from app.models.sale import Sale, SaleStatus, PaymentType  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.company import Company  # type: ignore

async def send_tg_msg_async(token, chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except:
        pass

async def process_daily_debts():
    db = SessionLocal()
    try:
        today = date.today()
        # Find all active debt sales
        unpaid_sales = db.query(Sale).filter(
            Sale.status == SaleStatus.completed,
            Sale.payment_type == PaymentType.debt,
            Sale.paid_amount < Sale.total_amount,
            Sale.debt_due_date.isnot(None)
        ).all()

        for sale in unpaid_sales:
            debt_amount = sale.total_amount - sale.paid_amount
            if debt_amount <= 0: continue
            
            customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
            if not customer or not customer.tg_chat_id: continue
            
            company = db.query(Company).filter(Company.id == sale.company_id).first()
            if not company or not company.tg_bot_token: continue
            
            due = sale.debt_due_date
            diff_days = (due - today).days
            
            msg = None
            if diff_days == 3:
                msg = f"❗️ <b>Eslatma</b>\n\nSizning <b>{company.name}</b> do'konidan olgan <b>{debt_amount:,.0f} so'm</b> qarzingizni to'lash muddatigacha <b>3 kun</b> qoldi.\nIltimos, vaqtida to'lashni unutmang!"
            elif diff_days == 0:
                msg = f"🚨 <b>Diqqat, To'lov Kuni</b>\n\nSizning <b>{company.name}</b> do'konidan olgan <b>{debt_amount:,.0f} so'm</b> qarzingizni to'lash muddati bugun!\nIltimos, kun davomida to'lovni amalga oshiring."
            elif diff_days < 0:
                overdue = abs(diff_days)
                msg = f"⚠️ <b>Kechiktirilgan To'lov</b>\n\nSizning <b>{company.name}</b> do'konidan olgan qarzingiz to'lov muddati <b>{overdue} kun</b> ga kechikdi.\nQarz miqdori: <b>{debt_amount:,.0f} so'm</b>\nIltimos, zudlik bilan to'lab qo'ying."
                
            if msg:
                await send_tg_msg_async(company.tg_bot_token, customer.tg_chat_id, msg)
                
    except Exception as e:
        print("Scheduler Error:", str(e))
    finally:
        db.close()


async def start_scheduler():
    last_run_date = None
    
    while True:
        try:
            now = datetime.now()
            
            # Har kuni soat 09:xx larda bitta run qiladi
            if now.hour == 9 and last_run_date != now.date():
                await process_daily_debts()
                last_run_date = now.date()
                
        except Exception as e:
            print("Scheduler Loop Error:", str(e))
            
        await asyncio.sleep(60) # har daqiqada tekshiradi
