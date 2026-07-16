# app/company_bot/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from aiogram import Bot

from app.database import get_db
from app.admin_tg_bot.models import CompanyBot
from app.admin_tg_bot.bot_schemas import CompanyBotCreate, CompanyBotOut

router = APIRouter(prefix="/companies/{company_id}/bot", tags=["Company Bot"])


@router.post("", response_model=CompanyBotOut)
async def add_company_bot(company_id: int, payload: CompanyBotCreate, db: Session = Depends(get_db)):
    existing = db.query(CompanyBot).filter(CompanyBot.company_id == company_id).first()
    if existing:
        raise HTTPException(400, "Bu kompaniyaga bot allaqachon ulangan")

    bot = Bot(token=payload.bot_token)
    try:
        me = await bot.get_me()
    except Exception:
        raise HTTPException(400, "Bot tokeni noto'g'ri")
    finally:
        await bot.session.close()

    company_bot = CompanyBot(
        company_id=company_id,
        bot_token=payload.bot_token,
        bot_username=me.username,
        bot_type="company",
        is_active=True,
    )
    db.add(company_bot)
    db.commit()
    db.refresh(company_bot)
    return company_bot


admin_router = APIRouter(prefix="/companies/{company_id}/admin-bot", tags=["Admin Bot"])


@admin_router.post("", response_model=CompanyBotOut)
async def add_admin_bot(company_id: int, payload: CompanyBotCreate, db: Session = Depends(get_db)):
    existing = db.query(CompanyBot).filter(
        CompanyBot.company_id == company_id,
        CompanyBot.bot_type == "admin"
    ).first()
    if existing:
        raise HTTPException(400, "Bu kompaniyaga admin bot allaqachon ulangan")

    bot = Bot(token=payload.bot_token)
    try:
        me = await bot.get_me()
    except Exception:
        raise HTTPException(400, "Bot tokeni noto'g'ri")
    finally:
        await bot.session.close()

    admin_bot = CompanyBot(
        company_id=company_id,
        bot_token=payload.bot_token,
        bot_username=me.username,
        bot_type="admin",
        is_active=True,
    )
    db.add(admin_bot)
    db.commit()
    db.refresh(admin_bot)
    return admin_bot


@admin_router.get("", response_model=CompanyBotOut)
async def get_admin_bot(company_id: int, db: Session = Depends(get_db)):
    admin_bot = db.query(CompanyBot).filter(
        CompanyBot.company_id == company_id,
        CompanyBot.bot_type == "admin"
    ).first()
    if not admin_bot:
        raise HTTPException(404, "Bu kompaniyaga admin bot ulanmagan")
    return admin_bot


@admin_router.put("", response_model=CompanyBotOut)
async def update_admin_bot(company_id: int, payload: CompanyBotCreate, db: Session = Depends(get_db)):
    admin_bot = db.query(CompanyBot).filter(
        CompanyBot.company_id == company_id,
        CompanyBot.bot_type == "admin"
    ).first()
    if not admin_bot:
        raise HTTPException(404, "Bu kompaniyaga admin bot ulanmagan")

    # Validate new token
    bot = Bot(token=payload.bot_token)
    try:
        me = await bot.get_me()
    except Exception:
        raise HTTPException(400, "Bot tokeni noto'g'ri")
    finally:
        await bot.session.close()

    admin_bot.bot_token = payload.bot_token
    admin_bot.bot_username = me.username
    db.commit()
    db.refresh(admin_bot)
    return admin_bot


@admin_router.delete("")
async def delete_admin_bot(company_id: int, db: Session = Depends(get_db)):
    admin_bot = db.query(CompanyBot).filter(
        CompanyBot.company_id == company_id,
        CompanyBot.bot_type == "admin"
    ).first()
    if not admin_bot:
        raise HTTPException(404, "Bu kompaniyaga admin bot ulanmagan")

    db.delete(admin_bot)
    db.commit()
    return {"message": "Admin bot o'chirildi"}

