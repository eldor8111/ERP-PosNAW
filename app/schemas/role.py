from pydantic import BaseModel
from typing import Optional, Any, Dict

class RoleBase(BaseModel):
    name: str
    permissions: Dict[str, Any] = {}

class RoleCreate(RoleBase):
    pass

class RoleUpdate(RoleBase):
    pass

class RoleResponse(RoleBase):
    id: int
    company_id: Optional[int] = None
    is_system: bool = False

    class Config:
        from_attributes = True
