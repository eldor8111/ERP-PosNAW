"""Telegram (parse_mode=HTML) xabarlari uchun yordamchilar (T2.10).

- esc(v): dinamik qiymatlarni (mahsulot/mijoz/korxona nomi, xato matni) HTML-escape qiladi.
  Telegram HTML faqat `& < >` ni talab qiladi, shuning uchun quote=False.
- split_html_message(text, limit): 4096 belgilik chegaradan oshgan xabarni qator chegaralarida bo'laklaydi.
- strip_tags(text): "can't parse entities" xatosida teglarsiz qayta yuborish uchun.
"""
import html
import re

TG_MAX_LEN = 4096
DEFAULT_CHUNK = 3800

# Telegram qo'llab-quvvatlaydigan teglar (strip_tags faqat shularni olib tashlaydi —
# qiymat ichidagi "<USB-C>" kabi matn yo'qolmasin)
_TG_TAGS = r"b|strong|i|em|u|ins|s|strike|del|a|code|pre|tg-spoiler|tg-emoji|span|blockquote"
_TAG_RE = re.compile(rf"</?(?:{_TG_TAGS})(?:\s[^<>]*)?/?>", re.IGNORECASE)
_TAG_PARTS_RE = re.compile(rf"<(/?)({_TG_TAGS})(\s[^<>]*)?>", re.IGNORECASE)


def esc(v) -> str:
    """HTML-escape (& < >). None bo'sh qator bo'ladi."""
    return html.escape("" if v is None else str(v), quote=False)


def strip_tags(text: str) -> str:
    """Telegram teglarini olib tashlaydi va escape'larni (&lt; ...) oddiy belgilarga qaytaradi."""
    return html.unescape(_TAG_RE.sub("", text or ""))


def _open_tags(segment: str, stack: list) -> list:
    """segment oxirida ochiq qolgan teglar ro'yxati (boshlang'ich stack bilan)."""
    stack = list(stack)
    for m in _TAG_PARTS_RE.finditer(segment):
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        else:
            stack.append((name, f"<{name}{attrs}>"))
    return stack


def _safe_cut(s: str, size: int) -> int:
    """s[:cut] teg (<...>) yoki entity (&...;) o'rtasida uzilmasligi uchun cut ni topadi."""
    cut = min(size, len(s))
    if cut >= len(s):
        return cut
    head = s[:cut]
    lt, gt = head.rfind("<"), head.rfind(">")
    if lt > gt:
        cut = lt
    else:
        amp, semi = head.rfind("&"), head.rfind(";")
        if amp > semi and cut - amp <= 10:
            cut = amp
    return cut if cut > 0 else min(size, len(s))


def _hard_split(line: str, limit: int) -> list:
    """Bitta juda uzun qatorni limitdan oshmaydigan bo'laklarga bo'ladi (teglar muvozanatlanadi)."""
    parts = []
    stack: list = []
    rest = line
    while rest:
        prefix = "".join(t[1] for t in stack)
        closers_now = "".join(f"</{t[0]}>" for t in reversed(stack))
        # yangi ochiladigan teglar uchun zaxira
        reserve = 40 if ("<" in rest or stack) else 0
        budget = max(limit - len(prefix) - len(closers_now) - reserve, 1)
        if len(prefix) + len(rest) + len(closers_now) <= limit:
            parts.append(prefix + rest)
            break
        cut = _safe_cut(rest, budget)
        seg, rest = rest[:cut], rest[cut:]
        new_stack = _open_tags(seg, stack)
        closers = "".join(f"</{t[0]}>" for t in reversed(new_stack))
        parts.append(prefix + seg + closers)
        stack = new_stack
    return parts


def split_html_message(text: str, limit: int = DEFAULT_CHUNK) -> list:
    """Xabarni qator chegaralarida <= limit belgilik bo'laklarga bo'ladi.

    Teglar bir qator ichida bo'lishi shart. Bitta qator limitdan uzun bo'lsa qattiq bo'linadi
    (teg/entity o'rtasida uzilmaydi). Bo'sh matn uchun bo'sh ro'yxat qaytadi.
    """
    limit = max(1, min(int(limit or DEFAULT_CHUNK), TG_MAX_LEN))
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list = []
    cur = ""
    for line in text.split("\n"):
        pieces = [line] if len(line) <= limit else _hard_split(line, limit)
        for piece in pieces:
            if not cur:
                cur = piece
            elif len(cur) + 1 + len(piece) <= limit:
                cur += "\n" + piece
            else:
                chunks.append(cur)
                cur = piece
    if cur:
        chunks.append(cur)
    # faqat bo'sh joydan iborat bo'laklarni yubormaymiz
    return [c for c in chunks if c.strip()]
