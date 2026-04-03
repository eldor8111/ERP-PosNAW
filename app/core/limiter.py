"""
Rate limiter singleton — main.py va routerlar buni import qiladi.
Circular import oldini olish uchun alohida modul.
"""
from slowapi import Limiter  # type: ignore
from slowapi.util import get_remote_address  # type: ignore

limiter = Limiter(key_func=get_remote_address)
