"""
Orqaga moslik qatlami (T3.9): tarif limitlarining yagona manbai — `app.services.tariff_guard`.
Bu modul faqat eski importlarni (`app.utils.tariff_check`) ishlatadigan fayllar uchun qoldirilgan;
yangi kodda to'g'ridan-to'g'ri `app.services.tariff_guard` dan import qiling.
"""
from app.services.tariff_guard import (  # noqa: F401
    DEFAULT_MAX_BRANCHES as _DEFAULT_MAX_BRANCHES,
    DEFAULT_MAX_USERS as _DEFAULT_MAX_USERS,
    TariffLimitError,
    check_branch_limit,
    check_user_limit,
    check_warehouse_limit,
    get_company_limits,
)
