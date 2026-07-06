import re
from datetime import datetime

_token: str | None = None
_token_expires_at: datetime | None = None
prefix_list = ["20", "33", "50", "55", "77", "88", "90", "91", "93", "94", "95", "97", "98", "99"]
valid_prefixes = tuple(prefix_list)


def clean_phone(phone: str) -> str:
    if not phone:
        return ""

    digits = re.sub(r'\D', '', phone)

    if len(digits) == 12 and digits.startswith("998"):
        if digits[3:5] in prefix_list:
            return digits

    if len(digits) == 9 and digits.startswith(valid_prefixes):
        return "998" + digits

    return ""


# +998990756341
