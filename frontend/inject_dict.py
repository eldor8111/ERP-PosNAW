import re

DICTIONARY_UZ = {
    'admin.dict.save': 'Saqlash', 'admin.dict.delete': 'O\'chirish', 'admin.dict.edit': 'Tahrirlash',
    'admin.dict.add': 'Qo\'shish', 'admin.dict.cancel': 'Bekor qilish', 'admin.dict.close': 'Yopish',
    'admin.dict.print': 'Chop etish', 'admin.dict.search': 'Izlash', 'admin.dict.filter': 'Filtrlash',
    'admin.dict.confirm': 'Tasdiqlash', 'admin.dict.clear': 'Tozalash', 'admin.dict.excel': 'Excel',
    'admin.dict.pdf': 'PDF', 'admin.dict.prev': 'Oldingi', 'admin.dict.next': 'Keyingi',
    'admin.dict.sale': 'Sotuv', 'admin.dict.income': 'Kirim', 'admin.dict.expense': 'Chiqim',
    'admin.dict.expense2': 'Xarajat', 'admin.dict.balance': 'Qoldiq', 'admin.dict.profit': 'Foyda',
    'admin.dict.loss': 'Zarar', 'admin.dict.debt': 'Qarz', 'admin.dict.payment': 'To\'lov',
    'admin.dict.product': 'Mahsulot', 'admin.dict.category': 'Kategoriya', 'admin.dict.warehouse': 'Ombor',
    'admin.dict.warehouse2': 'Omborxona', 'admin.dict.pos': 'Kassa', 'admin.dict.employee': 'Xodim',
    'admin.dict.customer': 'Mijoz', 'admin.dict.contragent': 'Kontragent', 'admin.dict.user': 'Foydalanuvchi',
    'admin.dict.supplier': 'Ta\'minotchi', 'admin.dict.shift': 'Smena', 'admin.dict.report': 'Hisobot',
    'admin.dict.date': 'Sana', 'admin.dict.status': 'Holat', 'admin.dict.status2': 'Status',
    'admin.dict.qty': 'Miqdor', 'admin.dict.price': 'Narx', 'admin.dict.sale_price': 'Sotuv narxi',
    'admin.dict.cost_price': 'Tan narx', 'admin.dict.total': 'Jami', 'admin.dict.number': 'Raqam',
    'admin.dict.comment': 'Izoh', 'admin.dict.cashier': 'Kassir', 'admin.dict.name': 'Ism',
    'admin.dict.phone': 'Telefon', 'admin.dict.address': 'Manzil', 'admin.dict.all': 'Barcha',
    'admin.dict.all2': 'Barchasi', 'admin.dict.select': 'Tanlang', 'admin.dict.limit': 'Limit',
    'admin.dict.total_colon': 'Jami:', 'admin.dict.yes': 'Ha', 'admin.dict.no': 'Yo\'q',
    'admin.dict.completed': 'Yakunlandi', 'admin.dict.pending': 'Kutish', 'admin.dict.active': 'Faol',
    'admin.dict.inactive': 'Nofaol', 'admin.dict.no_cust': 'Mijoz topilmadi', 'admin.dict.no_data': 'Ma\'lumot topilmadi',
    'admin.dict.th_num': 'RAQAM', 'admin.dict.th_date': 'SANA', 'admin.dict.th_cust': 'MIJOZ',
    'admin.dict.th_emp': 'XODIM', 'admin.dict.th_total': 'JAMI', 'admin.dict.th_paid': 'TO\'LANGAN',
    'admin.dict.th_debt': 'QARZGA', 'admin.dict.th_status': 'HOLAT', 'admin.dict.th_cashier': 'KASSIR',
    'admin.dict.th_prod': 'MAHSULOT', 'admin.dict.th_qty': 'MIQDOR', 'admin.dict.th_price': 'NARX'
}

DICTIONARY_RU = {
    'admin.dict.save': 'Сохранить', 'admin.dict.delete': 'Удалить', 'admin.dict.edit': 'Редактировать',
    'admin.dict.add': 'Добавить', 'admin.dict.cancel': 'Отмена', 'admin.dict.close': 'Закрыть',
    'admin.dict.print': 'Печать', 'admin.dict.search': 'Поиск', 'admin.dict.filter': 'Фильтр',
    'admin.dict.confirm': 'Подтвердить', 'admin.dict.clear': 'Очистить', 'admin.dict.excel': 'Excel',
    'admin.dict.pdf': 'PDF', 'admin.dict.prev': 'Назад', 'admin.dict.next': 'Вперед',
    'admin.dict.sale': 'Продажа', 'admin.dict.income': 'Приход', 'admin.dict.expense': 'Расход',
    'admin.dict.expense2': 'Расход', 'admin.dict.balance': 'Остаток', 'admin.dict.profit': 'Прибыль',
    'admin.dict.loss': 'Убыток', 'admin.dict.debt': 'Долг', 'admin.dict.payment': 'Оплата',
    'admin.dict.product': 'Товар', 'admin.dict.category': 'Категория', 'admin.dict.warehouse': 'Склад',
    'admin.dict.warehouse2': 'Склад', 'admin.dict.pos': 'Касса', 'admin.dict.employee': 'Сотрудник',
    'admin.dict.customer': 'Клиент', 'admin.dict.contragent': 'Контрагент', 'admin.dict.user': 'Пользователь',
    'admin.dict.supplier': 'Поставщик', 'admin.dict.shift': 'Смена', 'admin.dict.report': 'Отчет',
    'admin.dict.date': 'Дата', 'admin.dict.status': 'Статус', 'admin.dict.status2': 'Статус',
    'admin.dict.qty': 'Кол-во', 'admin.dict.price': 'Цена', 'admin.dict.sale_price': 'Цена продажи',
    'admin.dict.cost_price': 'Себестоимость', 'admin.dict.total': 'Итого', 'admin.dict.number': 'Номер',
    'admin.dict.comment': 'Комментарий', 'admin.dict.cashier': 'Кассир', 'admin.dict.name': 'Имя',
    'admin.dict.phone': 'Телефон', 'admin.dict.address': 'Адрес', 'admin.dict.all': 'Все',
    'admin.dict.all2': 'Все', 'admin.dict.select': 'Выберите', 'admin.dict.limit': 'Лимит',
    'admin.dict.total_colon': 'Итого:', 'admin.dict.yes': 'Да', 'admin.dict.no': 'Нет',
    'admin.dict.completed': 'Завершено', 'admin.dict.pending': 'Ожидание', 'admin.dict.active': 'Активен',
    'admin.dict.inactive': 'Не активен', 'admin.dict.no_cust': 'Клиент не найден', 'admin.dict.no_data': 'Нет данных',
    'admin.dict.th_num': 'НОМЕР', 'admin.dict.th_date': 'ДАТА', 'admin.dict.th_cust': 'КЛИЕНТ',
    'admin.dict.th_emp': 'СОТРУДНИК', 'admin.dict.th_total': 'ИТОГО', 'admin.dict.th_paid': 'ОПЛАЧЕНО',
    'admin.dict.th_debt': 'В ДОЛГ', 'admin.dict.th_status': 'СТАТУС', 'admin.dict.th_cashier': 'КАССИР',
    'admin.dict.th_prod': 'ТОВАР', 'admin.dict.th_qty': 'КОЛ-ВО', 'admin.dict.th_price': 'ЦЕНА'
}

DICTIONARY_EN = {
    'admin.dict.save': 'Save', 'admin.dict.delete': 'Delete', 'admin.dict.edit': 'Edit',
    'admin.dict.add': 'Add', 'admin.dict.cancel': 'Cancel', 'admin.dict.close': 'Close',
    'admin.dict.print': 'Print', 'admin.dict.search': 'Search', 'admin.dict.filter': 'Filter',
    'admin.dict.confirm': 'Confirm', 'admin.dict.clear': 'Clear', 'admin.dict.excel': 'Excel',
    'admin.dict.pdf': 'PDF', 'admin.dict.prev': 'Prev', 'admin.dict.next': 'Next',
    'admin.dict.sale': 'Sale', 'admin.dict.income': 'Income', 'admin.dict.expense': 'Expense',
    'admin.dict.expense2': 'Expense', 'admin.dict.balance': 'Balance', 'admin.dict.profit': 'Profit',
    'admin.dict.loss': 'Loss', 'admin.dict.debt': 'Debt', 'admin.dict.payment': 'Payment',
    'admin.dict.product': 'Product', 'admin.dict.category': 'Category', 'admin.dict.warehouse': 'Warehouse',
    'admin.dict.warehouse2': 'Warehouse', 'admin.dict.pos': 'POS', 'admin.dict.employee': 'Employee',
    'admin.dict.customer': 'Customer', 'admin.dict.contragent': 'Contragent', 'admin.dict.user': 'User',
    'admin.dict.supplier': 'Supplier', 'admin.dict.shift': 'Shift', 'admin.dict.report': 'Report',
    'admin.dict.date': 'Date', 'admin.dict.status': 'State', 'admin.dict.status2': 'Status',
    'admin.dict.qty': 'Qty', 'admin.dict.price': 'Price', 'admin.dict.sale_price': 'Sale Price',
    'admin.dict.cost_price': 'Cost Price', 'admin.dict.total': 'Total', 'admin.dict.number': 'Number',
    'admin.dict.comment': 'Comment', 'admin.dict.cashier': 'Cashier', 'admin.dict.name': 'Name',
    'admin.dict.phone': 'Phone', 'admin.dict.address': 'Address', 'admin.dict.all': 'All',
    'admin.dict.all2': 'All', 'admin.dict.select': 'Select', 'admin.dict.limit': 'Limit',
    'admin.dict.total_colon': 'Total:', 'admin.dict.yes': 'Yes', 'admin.dict.no': 'No',
    'admin.dict.completed': 'Completed', 'admin.dict.pending': 'Pending', 'admin.dict.active': 'Active',
    'admin.dict.inactive': 'Inactive', 'admin.dict.no_cust': 'Customer not found', 'admin.dict.no_data': 'No data',
    'admin.dict.th_num': 'NUMBER', 'admin.dict.th_date': 'DATE', 'admin.dict.th_cust': 'CUSTOMER',
    'admin.dict.th_emp': 'EMPLOYEE', 'admin.dict.th_total': 'TOTAL', 'admin.dict.th_paid': 'PAID',
    'admin.dict.th_debt': 'DEBT', 'admin.dict.th_status': 'STATUS', 'admin.dict.th_cashier': 'CASHIER',
    'admin.dict.th_prod': 'PRODUCT', 'admin.dict.th_qty': 'QTY', 'admin.dict.th_price': 'PRICE'
}

def inject_dict(filepath, new_dict):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    idx = content.rfind('};')
    if idx == -1: 
        print('Error parsing', filepath)
        return
    
    items = []
    for k, v in new_dict.items():
        val = v.replace("'", "\\'")
        items.append(f"  '{k}': '{val}'")
        
    inject_str = ",\n" + ",\n".join(items) + "\n"
    content = content[:idx] + inject_str + content[idx:]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

inject_dict(r'c:\ERPPos_extracted\ERPPos\frontend\src\i18n\uz.js', DICTIONARY_UZ)
inject_dict(r'c:\ERPPos_extracted\ERPPos\frontend\src\i18n\ru.js', DICTIONARY_RU)
inject_dict(r'c:\ERPPos_extracted\ERPPos\frontend\src\i18n\en.js', DICTIONARY_EN)
print('Dictionaries injected successfully!')
