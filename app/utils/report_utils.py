"""Hisobotlar uchun umumiy vaqt oralig'i yordamchilari."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional


def _today_range():
    today = datetime.now(timezone.utc).date()
    return (
        datetime.combine(today, datetime.min.time()),
        datetime.combine(today + timedelta(days=1), datetime.min.time()),
    )


def _date_range(date_from: Optional[date], date_to: Optional[date]):
    start = datetime.combine(date_from, datetime.min.time()) if date_from else datetime(2000, 1, 1)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) if date_to else datetime(2100, 1, 1)
    return start, end
