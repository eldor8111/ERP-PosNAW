from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from cachetools import TTLCache
import os

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
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """
    Mobil ilova yoki web orqali mahsulot ta'rifini generatsiya qilish.
    """
    # Kesh kaliti
    cache_key = f"{request.name.strip().lower()}_{request.category.strip().lower()}"
    
    if cache_key in cache:
        return {"description": cache[cache_key], "cached": True}
        
    api_key = os.getenv("BYTEZ_API_KEY", "42444b53b260f17105d68352fe7e9b3f")
    
    description = generate_product_description(request.name, request.category, api_key)
    
    if not description:
        raise HTTPException(
            status_code=503, 
            detail="Sun'iy intellekt serveri hozircha javob bermadi. Iltimos, o'zingiz yozing yoki birozdan so'ng urinib ko'ring."
        )
        
    # Keshga saqlash
    cache[cache_key] = description
    
    return {"description": description, "cached": False}
