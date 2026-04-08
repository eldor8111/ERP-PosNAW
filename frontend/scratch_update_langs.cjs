const fs = require('fs');
const path = require('path');

const uzAdditions = {
  'land.tab1.title': "Tovarlar va Nomenklatura",
  'land.tab1.desc': "Minglab tovar pozitsiyalarini shtrix-kod kataloglari orqali yagona bazaga birlashtiring. O'lchov birliklari, qadoqlar, hamda yaroqlilik muddatlari monitoringini olib boring.",
  'land.tab2.title': "Sotuv va Tranzaksiyalar",
  'land.tab2.desc': "B2B uchun shartnomaviy sotuv, yuridik shaxslarga schyot-fakturalar va B2C uchun umumlashgan tezkor POS darchasi.",
  'land.tab3.title': "Audit va Xavfsizlik",
  'land.tab3.desc': "Xodimlarning barcha harakatlari va tranzaksiya o'zgarishlari tizim loglariga muhrlanadi. To'liq ichki nazorat, Ruxsatlar tizimi (RBAC) va xavfsizlik protokollari.",
  'land.check1': "Qoldiq zaxiralar avto-buyurtmasi",
  'land.check2': "Obyektlar aro ishonchli tranzitlar",
  'land.check3': "Inventarizatsiya va kalkulyatsiya retsepti"
};

const ruAdditions = {
  'land.modules': "Модули",
  'land.b2b': "Для B2B и B2C сегментов",
  'land.erp': "Корпоративный ERP",
  'land.desc1': "Полностью оцифруйте вашу сеть продаж. Централизованная платформа управления с облачными технологиями, безопасностью данных и передовыми решениями синхронизации.",
  'land.try': "Попробовать систему",
  'land.eco': "Экосистема",
  'land.sec1': "🔒 Финансовая защита",
  'land.sec2': "⚡ 99.9% Аптайм",
  'land.sec3': "☁️ 24/7 Резерв",
  'land.ecosystem': "Экосистема бесконечных возможностей",
  'land.arch': "Архитектура взаимосвязанных модулей.",
  'land.omni': "Omnichannel POS Терминал",
  'land.omniDesc': "Адаптированное рабочее пространство для кассиров. Прямая локальная интеграция со сканерами, QR-кодами и весами. Оффлайн буфер.",
  'land.bi': "BI и Финансовая Аналитика",
  'land.biDesc': "Дашборды рентабельности в реальном времени. Глубокий анализ финансовых операций и задолженностей.",
  'land.crm': "Smart CRM Платформа",
  'land.crmDesc': "Автоматизированный кэшбэк, RFM анализ и индивидуальные лимиты долга для корпоративных клиентов.",
  'land.wms': "Многоканальный склад (WMS)",
  'land.wmsDesc': "Управление сложной номенклатурой с учетом партий, себестоимости и автообслуживания филиалов.",
  'land.singleDb': "В единой базе данных",
  'land.noPaper': "Забудьте о бумагах и разрозненных дашбордах.",
  'land.nextLevel': "Выведите бизнес на новый уровень",
  'land.registerNow': "Зарегистрируйтесь сейчас и используйте все возможности.",
  'land.tab1.title': "Товары и Номенклатура",
  'land.tab1.desc': "Объединяйте тысячи позиций в единую базу через каталоги штрих-кодов. Контролируйте единицы измерения, упаковки и сроки годности.",
  'land.tab2.title': "Продажи и Транзакции",
  'land.tab2.desc': "Контрактные продажи для B2B, счета-фактуры для юрлиц и универсальное быстрое окно POS для B2C.",
  'land.tab3.title': "Аудит и Безопасность",
  'land.tab3.desc': "Все действия сотрудников фиксируются в логах. Внутренний контроль, система доступов (RBAC) и протоколы безопасности.",
  'land.check1': "Авто-заказ остатков",
  'land.check2': "Надёжные транзиты",
  'land.check3': "Инвентаризация и калькуляция"
};

const enAdditions = {
  'land.modules': "Modules",
  'land.b2b': "For B2B and B2C segments",
  'land.erp': "Corporate ERP",
  'land.desc1': "Fully digitize your sales network. Centralized management platform with cloud technologies, data security, and advanced synchronization.",
  'land.try': "Try the System",
  'land.eco': "Ecosystem",
  'land.sec1': "🔒 Bank-grade Security",
  'land.sec2': "⚡ 99.9% Uptime",
  'land.sec3': "☁️ 24/7 Backup",
  'land.ecosystem': "Ecosystem of endless possibilities",
  'land.arch': "Interconnected module architecture.",
  'land.omni': "Omnichannel POS Terminal",
  'land.omniDesc': "Fast workspace for cashiers. Local integration with barcode scanners, QR payments, and scales. Offline buffer.",
  'land.bi': "BI & Financial Analytics",
  'land.biDesc': "Real-time profitability dashboards. Deep analysis of all financial operations and debts.",
  'land.crm': "Smart CRM Platform",
  'land.crmDesc': "Automated cashback, VIP customer mapping (RFM), and custom debt limits for corporate accounts.",
  'land.wms': "Multi-channel Warehouse (WMS)",
  'land.wmsDesc': "Manage complex inventories with batches, cost pricing, and automatic branch supply.",
  'land.singleDb': "In a single database",
  'land.noPaper': "Forget paper and disconnected software.",
  'land.nextLevel': "Take your business to the next level",
  'land.registerNow': "Register now and start using all platform features.",
  'land.tab1.title': "Products and Inventory",
  'land.tab1.desc': "Merge thousands of items into a single database via barcode catalogs. Monitor units, packaging, and expirations.",
  'land.tab2.title': "Sales and Transactions",
  'land.tab2.desc': "B2B contract sales, B2B invoices, and a fast integrated POS window for B2C.",
  'land.tab3.title': "Audit and Security",
  'land.tab3.desc': "All employee actions are securely logged. Complete internal control, RBAC permissions, and security protocols.",
  'land.check1': "Auto-reordering",
  'land.check2': "Reliable branch transfers",
  'land.check3': "Inventory counting and formulas"
};

function injectAdditions(filePath, additions) {
  let content = fs.readFileSync(filePath, 'utf8');
  // find the last closing brace
  const lastBraceIndex = content.lastIndexOf('}');
  if (lastBraceIndex !== -1) {
    let toInject = '';
    for (const [key, val] of Object.entries(additions)) {
      toInject += `  '${key}': \`${val.replace(/`/g, '\\`')}\`,\n`;
    }
    const newContent = content.slice(0, lastBraceIndex) + '\n  // Added for Landing\n' + toInject + '};\n';
    fs.writeFileSync(filePath, newContent);
    console.log(`Updated ${filePath}`);
  }
}

const baseDir = path.join('c:/ERPPos_extracted/ERPPos/frontend/src/i18n');
injectAdditions(path.join(baseDir, 'uz.js'), uzAdditions);
injectAdditions(path.join(baseDir, 'ru.js'), ruAdditions);
injectAdditions(path.join(baseDir, 'en.js'), enAdditions);
