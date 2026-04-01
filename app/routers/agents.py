from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from sqlalchemy import func
from app.models.company import Company
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.agent import Agent, generate_agent_code

router = APIRouter(prefix="/agents", tags=["Agents"])


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Faqat Super Admin uchun")
    return current_user


class AgentCreate(BaseModel):
    name: str
    phone: str
    code: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/")
def list_agents(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    agents_with_counts = (
        db.query(Agent, func.count(Company.id).label('companies_count'))
        .outerjoin(Company, Company.agent_id == Agent.id)
        .group_by(Agent.id)
        .order_by(Agent.id.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "code": a.code,
            "name": a.name,
            "phone": a.phone,
            "is_active": a.is_active,
            "companies_count": count,
            "created_at": str(a.created_at),
        }
        for a, count in agents_with_counts
    ]


@router.post("/", status_code=201)
def create_agent(data: AgentCreate, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    existing = db.query(Agent).filter(Agent.phone == data.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon mavjud")

    if data.code:
        code = data.code.strip().upper()
        code_exists = db.query(Agent).filter(Agent.code == code).first()
        if code_exists:
            raise HTTPException(status_code=400, detail=f"'{code}' kodi allaqachon mavjud")
    else:
        code = generate_agent_code(db)

    agent = Agent(name=data.name, phone=data.phone, code=code)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return {
        "id": agent.id,
        "code": agent.code,
        "name": agent.name,
        "phone": agent.phone,
        "is_active": agent.is_active,
        "created_at": str(agent.created_at),
    }


@router.patch("/{agent_id}")
def update_agent(agent_id: int, data: AgentUpdate, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent topilmadi")

    if data.name is not None:
        agent.name = data.name
    if data.phone is not None:
        existing = db.query(Agent).filter(Agent.phone == data.phone, Agent.id != agent_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon mavjud")
        agent.phone = data.phone
    if data.is_active is not None:
        agent.is_active = data.is_active

    db.commit()
    db.refresh(agent)
    return {"id": agent.id, "code": agent.code, "name": agent.name, "phone": agent.phone, "is_active": agent.is_active}


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    db.delete(agent)
    db.commit()
    return {"message": "Agent o'chirildi"}
