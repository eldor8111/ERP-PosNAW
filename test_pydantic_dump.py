from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal

class ProductConversionIn(BaseModel):
    source_product_id: int
    ratio: Decimal = Decimal("1.0")

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    product_type: Optional[str] = None
    conversion: Optional[ProductConversionIn] = None

data_dict = {
    "name": "Dumba",
    "product_type": "sell",
    "conversion": {
        "source_product_id": 15,
        "ratio": 1
    }
}

data = ProductUpdate(**data_dict)
update_data = data.model_dump(exclude_none=True, exclude={"conversion"})
print("update_data:", update_data)
