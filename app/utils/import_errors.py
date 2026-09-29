from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError  # type: ignore


def row_db_error(exc: SQLAlchemyError) -> str:
    """Excel importida bitta qatorni bazaga yozib bo'lmagani sababini foydalanuvchiga tushunarli qiladi."""
    if isinstance(exc, DataError):
        return "Qiymat juda uzun yoki formati noto'g'ri (masalan, nom, telefon yoki INN ustuni) — o'tkazib yuborildi"
    if isinstance(exc, IntegrityError):
        return "Takroriy yoki ruxsat etilmagan qiymat — o'tkazib yuborildi"
    return "Bazaga yozishda xato — o'tkazib yuborildi"
