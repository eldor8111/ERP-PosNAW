import os
import re

def safe_replace(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    # Find import
    if 'useLang' not in content:
        import_stmt = "import { useLang } from '../../context/LangContext';\n"
        if "import React" in content:
            content = content.replace("import React", import_stmt + "import React", 1)
        else:
            content = import_stmt + content

    for key, repls in replacements.items():
        # Insert `const { t } = useLang();` inside the component
        match = re.search(f'function {key}\\([^)]*\\) {{\n', content)
        if match and 'useLang' not in content[match.end():match.end()+100]:
            content = content.replace(match.group(0), match.group(0) + "  const { t } = useLang();\n")
            
        match_arrow = re.search(f'const {key} = \\([^)]*\\) => {{\n', content)
        if match_arrow and 'useLang' not in content[match_arrow.end():match_arrow.end()+100]:
            content = content.replace(match_arrow.group(0), match_arrow.group(0) + "  const { t } = useLang();\n")
            
        for orig, new_text in repls.items():
            content = content.replace(orig, new_text)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

# Replacements for SotuvMijozlar.jsx
sotuv_replacements = {
    'SotuvlarTab': {
        '>Yangi sotuv<': ">{t('admin.sales.new') || 'Yangi sotuv'}<",
        '>Jami: 1 ta sotuv<': ">{t('admin.sales.total_1') || 'Jami: 1 ta sotuv'}<",
        "placeholder=\"Jami\"": "placeholder={t('admin.sales.pl_jami') || 'Jami'}",
        "placeholder=\"To'langan\"": "placeholder={t('admin.sales.pl_paid') || \"To'langan\"}",
        "placeholder=\"Boshlanish\"": "placeholder={t('admin.sales.pl_start') || 'Boshlanish'}",
        "placeholder=\"Tugash\"": "placeholder={t('admin.sales.pl_end') || 'Tugash'}",
        ">Status<": ">{t('admin.sales.status') || 'Status'}<",
        ">Xodim<": ">{t('admin.sales.employee') || 'Xodim'}<",
        ">Oldingi<": ">{t('admin.sales.prev') || 'Oldingi'}<",
        ">Keyingi<": ">{t('admin.sales.next') || 'Keyingi'}<",
        ">Excel<": ">{t('admin.sales.excel') || 'Excel'}<",
        ">Limit:<": ">{t('admin.sales.limit') || 'Limit:'}<",
        ">Yakunlandi<": ">{t('admin.sales.completed') || 'Yakunlandi'}<",
        ">Naqd<": ">{t('admin.sales.cash') || 'Naqd'}<",
    },
    'MijozlarTab': {
        ">Jami Mijozlar<": ">{t('admin.sales.total_customers') || 'Jami Mijozlar'}<",
        ">Jami Qarz<": ">{t('admin.sales.total_debt') || 'Jami Qarz'}<",
        ">Qarzdorlar<": ">{t('admin.sales.debtors') || 'Qarzdorlar'}<",
        ">Yangi mijoz<": ">{t('admin.sales.new_customer') || 'Yangi mijoz'}<",
        ">LIMIT<": ">{t('admin.sales.th_limit') || 'LIMIT'}<",
        ">Q/B<": ">{t('admin.sales.th_qb') || 'Q/B'}<",
        ">KESHBEK<": ">{t('admin.sales.th_cashback') || 'KESHBEK'}<",
        ">BALANS<": ">{t('admin.sales.th_balance') || 'BALANS'}<",
        ">JAMI SOTUV<": ">{t('admin.sales.th_totalsales') || 'JAMI SOTUV'}<",
        ">QARZ<": ">{t('admin.sales.th_debt') || 'QARZ'}<",
        ">Mijozlar topilmadi<": ">{t('admin.sales.no_cust') || 'Mijozlar topilmadi'}<",
    },
    'SotuvMijozlar': {
        '>Sotuv va Mijozlar<': ">{t('admin.sales.title') || 'Sotuv va Mijozlar'}<",
        "{ id: 'sotuvlar', label: 'Sotuvlar',": "{ id: 'sotuvlar', label: t('admin.sales.tab_sales') || 'Sotuvlar',",
        "{ id: 'mijozlar', label: 'Mijozlar',": "{ id: 'mijozlar', label: t('admin.sales.tab_cust') || 'Mijozlar',"
    }
}

safe_replace(r'c:\ERPPos_extracted\ERPPos\frontend\src\pages\admin\SotuvMijozlar.jsx', sotuv_replacements)
print("Finished!")
