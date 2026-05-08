"""
Uzbek Kirill ↔ Lotin transliteratsiya yordamchi moduli.
Barcha routerlarda (products, customers, suppliers, ...) qidiruv uchun ishlatiladi.
"""
from __future__ import annotations

# ── Kirill → Lotin ─────────────────────────────────────────────────────────
_CYR_TO_LAT: dict[str, str] = {
    'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',
    'е': 'e',  'ё': 'yo', 'ж': 'j',  'з': 'z',  'и': 'i',
    'й': 'y',  'к': 'k',  'л': 'l',  'м': 'm',  'н': 'n',
    'о': 'o',  'п': 'p',  'р': 'r',  'с': 's',  'т': 't',
    'у': 'u',  'ф': 'f',  'х': 'x',  'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'sh', 'ъ': "'",  'ы': 'i',  'ь': '',
    'э': 'e',  'ю': 'yu', 'я': 'ya',
    'қ': 'q',  'ғ': "g'", 'ҳ': 'h',  'ў': "o'",
}

# ── Lotin → Kirill (uzun bigramlar birinchi bo'lishi SHART) ────────────────
_LAT_TO_CYR: list[tuple[str, str]] = [
    ("o'", 'ў'), ("g'", 'ғ'),
    ('ch', 'ч'), ('sh', 'ш'),
    ('yo', 'ё'), ('yu', 'ю'), ('ya', 'я'), ('ts', 'ц'),
    ('a', 'а'), ('b', 'б'), ('d', 'д'), ('e', 'е'), ('f', 'ф'),
    ('g', 'г'), ('h', 'х'), ('i', 'и'), ('j', 'ж'), ('k', 'к'),
    ('l', 'л'), ('m', 'м'), ('n', 'н'), ('o', 'о'), ('p', 'п'),
    ('q', 'қ'), ('r', 'р'), ('s', 'с'), ('t', 'т'), ('u', 'у'),
    ('v', 'в'), ('x', 'х'), ('y', 'й'), ('z', 'з'),
]


def translit_variants(text: str) -> list[str]:
    """
    Kirill yoki Lotin so'zni ikki yo'nalishda o'girib,
    barcha variantlarni (takrorlarsiz) ro'yxat sifatida qaytaradi.

    Misol:
        'магазин'  → ['магазин', 'magazin']
        'magazin'  → ['magazin', 'магазин']
        'Туроn un' → ['туроn un', 'turon un', 'туроn ун']  (har so'z alohida)
    """
    tl = text.lower().strip()
    variants: list[str] = [tl]

    # Kirill harflari bor → Lotinga o'gir
    if any(c in _CYR_TO_LAT for c in tl):
        lat = ''.join(_CYR_TO_LAT.get(c, c) for c in tl)
        variants.append(lat)

    # Lotin harflari bor → Kirillga o'gir
    if any(c.isascii() and c.isalpha() for c in tl):
        cyr = tl
        for fr, to in _LAT_TO_CYR:
            cyr = cyr.replace(fr, to)
        if cyr != tl:
            variants.append(cyr)

    # Takrorlanmasin
    return list(dict.fromkeys(variants))


def name_search_filter(column, search: str):
    """
    Ko'p so'zli, transliteratsiya-aware SQLAlchemy filter.

    Har bir so'z alohida AND sharti bilan qidiriladi:
      'ali vali' → column HAS 'ali' AND column HAS 'vali'
    Har bir so'z uchun Kirill + Lotin variantlari OR bilan birlashtiriladi.

    Parametrlar:
        column  — SQLAlchemy ustun yoki ustunlar OR birikmasi
        search  — foydalanuvchi kiritgan matn
    """
    from sqlalchemy import and_, or_

    words = [w for w in search.strip().split() if w]
    if not words:
        from sqlalchemy import true
        return true()

    word_conditions = []
    for word in words:
        variants = translit_variants(word)
        word_conditions.append(
            or_(*[column.ilike(f"%{v}%") for v in variants])
        )
    return and_(*word_conditions)


def name_phone_search_filter(name_col, phone_col, search: str):
    """
    Ism + telefon ustunlari bo'yicha transliteratsiya-aware qidiruv.
    Ism uchun translit, telefon uchun oddiy ilike ishlatiladi.
    """
    from sqlalchemy import or_

    variants = translit_variants(search)
    name_conds = [name_col.ilike(f"%{v}%") for v in variants]
    phone_cond = phone_col.ilike(f"%{search}%")
    return or_(*name_conds, phone_cond)
