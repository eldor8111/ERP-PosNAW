from pydantic import BaseModel
from typing import Optional

class ProductUpdate(BaseModel):
    product_type: Optional[str] = None
    name: Optional[str] = None

data = ProductUpdate(product_type="sell", name="Dumba")
print("exclude_none=True:", data.model_dump(exclude_none=True))
