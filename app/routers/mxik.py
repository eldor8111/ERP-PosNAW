
from fastapi import APIRouter, Depends, HTTPException, status
from pip._internal.cli import status_codes
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.mxik import MxikReference, MxikPackage
from app.models.tovarlar_catalog import TovarlarCatalog
from app.models.user import User, UserRole
from app.routers.billing import require_super_admin
from app.routers.users import create_user
from app.schemas.mxik import MxikReferenceOut, MxikSyncRequest, MxikReferenceUpdate
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


@router.get("/barcode/{barcode}")
def get_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Shtrix kod bo'yicha tovarlar_catalog jadvalidan mahsulot topadi.
    Qaytaradi: mxik_code, mxik_name, unit_name, group_name, lgota_id
    """
    item = db.query(TovarlarCatalog).filter(TovarlarCatalog.barcode == barcode).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Barcode {barcode} katalogda topilmadi")

    # MxikPackage dan parent_code ni olish (asosiy birlik packageType=1)
    parent_code = None
    if item.mxik_code:
        ref = db.query(MxikReference).filter(MxikReference.mxik_code == item.mxik_code).first()
        if ref:
            unit_pkg = db.query(MxikPackage).filter(
                MxikPackage.mxik_reference_id == ref.id,
                MxikPackage.is_unit_package == 1,
            ).first()
            if unit_pkg:
                parent_code = unit_pkg.code

    return {
        "mxik_code":      item.mxik_code,
        "mxik_name":      item.mxik_name,
        "unit_name":      item.unit_name,
        "group_name":     item.group_name,
        "attribute_name": item.attribute_name,
        "lgota_id":       item.lgota_id,
        "parent_code":    parent_code,
    }


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

@router.delete("/{mxik_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mxik(
        mxik_code: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    ref = db.query(MxikReference).filter(MxikReference.mxik_code == mxik_code).first()
    if not ref:
        raise HTTPException(status_code=404, detail="MXIK topilmadi")
    db.query(MxikPackage).filter(MxikPackage.mxik_reference_id == ref.id).delete()
    db.delete(ref)
    db.commit()
    return None


@router.put("/{mxik_code}", response_model=MxikReferenceUpdate, status_code=status.HTTP_202_ACCEPTED)
def update_mxik(
        mxik_code: str,
        data: MxikReferenceUpdate,
        db: Session = Depends(get_db),
        create_user: User = Depends(require_roles(UserRole.admin, UserRole.super_admin)),
):
    ref = db.query(MxikReferenceUpdate).filter(MxikReferenceUpdate.mxik_code == mxik_code).first()
    if not db:
        raise HTTPException(status_code=404, detail="MXIK topilmadi")
    for field, value in data.model_dump().items():
        setattr(ref, field, value)
    db.commit()
    db.refresh(ref)
    return ref


@router.delete("/{barcode}", status_code=status.HTTP_204_NO_CONTENT)
def delete_by_barcode(
        barcode: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.super_admin)),

):
    ref = db.query()