from pydantic import BaseModel, ConfigDict, model_validator
from typing import List, Literal, Optional
from datetime import datetime
from decimal import Decimal


def _check_discount(discount_type, discount_value):
    """Chegirma qiymati: foiz uchun 0 < x <= 100, summa uchun x > 0."""
    if discount_value is None:
        return
    if discount_value <= 0:
        raise ValueError("Chegirma qiymati 0 dan katta bo'lishi kerak")
    if discount_type == "percent" and discount_value > 100:
        raise ValueError("Foiz chegirma 100 dan oshmasligi kerak")


def _check_dates(start_date, end_date):
    if start_date is None or end_date is None:
        return
    # aware va naive sanalarni solishtirib bo'lmaydi — tzinfo'siz holga keltiramiz
    s = start_date.replace(tzinfo=None)
    e = end_date.replace(tzinfo=None)
    if e < s:
        raise ValueError("Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas")


class PromotionProductIn(BaseModel):
    product_id: int


class PromotionProductOut(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PromotionBase(BaseModel):
    name: str
    discount_type: str = "percent"  # percent, amount
    discount_value: Decimal
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True


class PromotionCreate(PromotionBase):
    discount_type: Literal["percent", "amount"] = "percent"
    # Berilmasa: `products` bo'sh bo'lmasa "products", aks holda "all" (eski mijozlar bilan mos)
    applies_to: Optional[Literal["all", "products"]] = None
    products: Optional[List[PromotionProductIn]] = []
    # T4.3: aksiya filiallari (bo'sh / berilmagan = hamma filial)
    branch_ids: Optional[List[int]] = None

    @model_validator(mode="after")
    def _validate(self):
        _check_discount(self.discount_type, self.discount_value)
        _check_dates(self.start_date, self.end_date)
        if self.products is None:
            self.products = []
        if self.applies_to is None:
            self.applies_to = "products" if self.products else "all"
        if self.applies_to == "products" and not self.products:
            raise ValueError("Tanlangan mahsulotlar qamrovi uchun kamida bitta mahsulot kerak")
        return self


class PromotionUpdate(BaseModel):
    name: Optional[str] = None
    discount_type: Optional[Literal["percent", "amount"]] = None
    discount_value: Optional[Decimal] = None
    # Sanani aniq `null` bilan bo'shatish mumkin — router `model_fields_set` ni tekshiradi
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    applies_to: Optional[Literal["all", "products"]] = None
    products: Optional[List[PromotionProductIn]] = None
    # T4.3: berilsa filiallar to'liq almashtiriladi; [] — hamma filial; berilmasa o'zgarmaydi
    branch_ids: Optional[List[int]] = None

    @model_validator(mode="after")
    def _validate(self):
        # Faqat ikkalasi ham berilgan bo'lsa to'liq tekshiriladi; qolganini router birlashgan qiymatda tekshiradi
        if self.discount_value is not None:
            _check_discount(self.discount_type, self.discount_value)
        _check_dates(self.start_date, self.end_date)
        if self.applies_to == "products" and self.products is not None and not self.products:
            raise ValueError("Tanlangan mahsulotlar qamrovi uchun kamida bitta mahsulot kerak")
        return self


class PromotionOut(PromotionBase):
    id: int
    company_id: int
    applies_to: str = "all"
    created_at: datetime
    updated_at: datetime
    products: List[PromotionProductOut] = []
    branch_ids: List[int] = []   # T4.3: bo'sh = hamma filial

    model_config = ConfigDict(from_attributes=True)
