"""Sodiqlik kartasi raqamlari (T2.12): yagona format va normalizatsiya."""
import random
import re
from typing import Iterable, Optional

# 13 xonali karta: "29" prefiksi tarozi shtrix-kod prefikslari (20/21/22) bilan to'qnashmaydi
CARD_PREFIX = "29"
CARD_LENGTH = 13


def normalize_card(s: Optional[str]) -> str:
    """Faqat raqamlarni qoldiradi ("8888 1234 5678" -> "888812345678")."""
    return re.sub(r"\D", "", s or "")


def generate_card_number(existing: Iterable[Optional[str]] = ()) -> str:
    """13 xonali `29…` karta raqami; `existing` (normallashtirilgan holda) bilan takrorlanmaydi."""
    taken = {normalize_card(x) for x in existing if x}
    while True:
        num = CARD_PREFIX + "".join(str(random.randint(0, 9)) for _ in range(CARD_LENGTH - len(CARD_PREFIX)))
        if num not in taken:
            return num
