from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from cachetools import TTLCache
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.ai_product_service import generate_product_description
from app.core.dependencies import require_roles
from app.models.user import User, UserRole

router = APIRouter(prefix="/ai/products", tags=["AI Products"])

# Kesh (100 ta item, 24 soat davomida saqlaydi) - Byudjetni tejash va tezlik uchun
cache = TTLCache(maxsize=100, ttl=86400)

class DescriptionRequest(BaseModel):
    name: str
    category: str

@router.post("/generate-description")
def generate_desc(
    request: DescriptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """
    Mobil ilova yoki web orqali mahsulot ta'rifini generatsiya qilish.
    """
    # Pullik AI imkoniyati: korxonada AI yordamchi paketi faol bo'lishi kerak
    if current_user.role != UserRole.super_admin:
        from app.services.claude_text import company_has_ai
        if not company_has_ai(db, current_user.company_id):
            raise HTTPException(status_code=402, detail="AI yordamchi paketi faol emas")

    # Kesh kaliti (korxona bo'yicha)
    cache_key = f"{current_user.company_id}_{request.name.strip().lower()}_{request.category.strip().lower()}"
    
    if cache_key in cache:
        return {"description": cache[cache_key], "cached": True}
        
    description = generate_product_description(request.name, request.category)
    
    if not description:
        raise HTTPException(
            status_code=503, 
            detail="Sun'iy intellekt serveri hozircha javob bermadi. Iltimos, o'zingiz yozing yoki birozdan so'ng urinib ko'ring."
        )
        
    # Keshga saqlash
    cache[cache_key] = description
    
    return {"description": description, "cached": False}
