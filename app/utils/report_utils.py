"""Hisobotlar uchun umumiy vaqt oralig'i yordamchilari."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional


def _today_range():
    """Bugungi kun boshlanishi va tugashi (UTC timezone-aware)"""
    today = datetime.now(timezone.utc).date()
    return (
        datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc),
        datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc),
    )


def _date_range(date_from: Optional[date], date_to: Optional[date]):
    start = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc) if date_from else datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc) if date_to else datetime(2100, 1, 1, tzinfo=timezone.utc)
    return start, end
