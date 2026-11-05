from typing import Optional, List


def generate_daily_insight(
    company_name: str,
    total_sales: float,
    sales_count: int,
    cash: float,
    card: float,
    debt_added: float,
    growth_pct: float,
    low_stock_count: int,
    overdue_count: int,
    top_products: List[str],
    api_key: str = "",
    db=None,
    company_id: Optional[int] = None,
) -> Optional[str]:
    """Kunlik savdo bo'yicha qisqa AI xulosa (Claude). Shaxsiy ma'lumotlar yuborilmaydi.

    Faqat korxonada AI yordamchi paketi faol bo'lsa chaqiriladi (db va company_id berilganda);
    aks holda yoki xato bo'lsa None — chaqiruvchi statik hisobotni ko'rsatadi. `api_key` eski
    chaqiruvlar uchun qoldirilgan, ishlatilmaydi (kalit faqat .env da)."""
    from app.services import claude_text
    if db is not None and not claude_text.company_has_ai(db, company_id):
        return None

    system_prompt = (
        "Siz korxona rahbarlari uchun kunlik savdo xulosasini yozuvchi moliyaviy tahlilchisiz. "
        "Berilgan raqamlarga qarab 3-5 gapdan iborat qisqa xulosa va 1-2 ta amaliy maslahat yozing. "
        "Faqat berilgan raqamlarni ishlating, yangi raqam to'qimang. O'zbek tilida, lotin yozuvida, "
        "emoji va sarlavhalarsiz, oddiy matn bilan yozing."
    )

    def fmt(x):
        return f"{x:,.0f}".replace(",", " ") + " so'm"

    trend = f"+{growth_pct:.1f}% o'sish" if growth_pct >= 0 else f"{growth_pct:.1f}% pasayish"
    top = ", ".join(top_products) if top_products else "yo'q"
    user_prompt = (
        f"Korxona: {company_name}\n"
        f"Bugungi cheklar: {sales_count} ta\n"
        f"Sof tushum: {fmt(total_sales)}\n"
        f"Naqd: {fmt(cash)} | Karta: {fmt(card)} | Nasiya: {fmt(debt_added)}\n"
        f"Kechagiga nisbatan: {trend}\n"
        f"Top mahsulotlar: {top}\n"
        f"Kam qolgan tovarlar: {low_stock_count} ta\n"
        f"Muddati o'tgan qarzdorlar: {overdue_count} ta"
    )
    return claude_text.complete(system_prompt, user_prompt, max_tokens=800)
