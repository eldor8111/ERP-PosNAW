from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.mxik import MxikReference
from app.models.user import User
from app.schemas.mxik import MxikReferenceOut, MxikSyncRequest
from app.services.tasnif_service import sync_mxik
from app.config import settings

router = APIRouter(prefix="/mxik", tags=["MXIK / Tasnif"])


@router.post("/sync", response_model=MxikReferenceOut)
async def sync_mxik_endpoint(
    payload: MxikSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    MXIK kodi bo'yicha tasnif.soliq.uz dan ma'lumot olib DB ga saqlaydi.
    force_refresh=False bo'lsa va DB da mavjud bo'lsa — API chaqirilmaydi.
    """
    terminal_id = payload.terminal_id or settings.DEFAULT_TERMINAL_ID
    if not terminal_id:
        raise HTTPException(status_code=400, detail="terminal_id berilmagan va DEFAULT_TERMINAL_ID sozlanmagan")

    try:
        ref = await sync_mxik(
            db=db,
            mxik_code=payload.mxik_code,
            terminal_id=terminal_id,
            force_refresh=payload.force_refresh,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Tasnif API xatosi: {str(e)}")

    return ref


@router.get("/{mxik_code}", response_model=MxikReferenceOut)
def get_mxik(
    mxik_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DB dagi MXIK ma'lumotini qaytaradi."""
    ref = db.query(MxikReference).filter(MxikReference.mxik_code == mxik_code).first()
    if not ref:
        raise HTTPException(
            status_code=404,
            detail="MXIK topilmadi. Avval POST /mxik/sync chaqiring.",
        )
    return ref
