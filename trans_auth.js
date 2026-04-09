const fs = require('fs');

const authMap = {
    "Korxonani tanlang": "pos.selectEnterprise",
    "Qaysi korxona bilan ishlashni tanlang": "pos.selectEnterpriseSub",
    "← Boshqa hisob bilan kirish": "pos.loginOtherAccount",
    "Kassaga kirish": "pos.loginCashier",
    "Hisob ma'lumotlarini kiriting": "pos.enterCredentials",
    "Telefon raqam": "settings.phone",
    "Parol": "user.password",
    "Kirish...": "common.loggingIn",
    "Kassani ochish": "pos.openCashier",
    "oddiy kirish": "pos.normalLogin",
    "🌐 Server Sozlamalari (IP)": "pos.serverSettingsIP",
    "🌐 Server Sozlamalari": "pos.serverSettings",
    "Backend API manzilini kiriting": "pos.enterApiUrl",
    "Bekor": "common.cancel",
    "Saqlash": "common.save",
    "Muvaffaqiyatli!": "common.success",
    "Korxona ro'yxatdan o'tdi. Tizimga kiring.": "auth.companyRegistered",
    "Korxona nomi": "settings.companyName",
    "Korxona kodi": "settings.orgCode",
    "Ushbu kodni albatta saqlab qo'ying!": "auth.saveThisCode",
    "Balans ochildi": "auth.balanceOpened",
    "Tarif sotib olish uchun balansni to'ldiring": "auth.fillBalance",
    "Tizimga kirish": "land.nav.login",
    "Biznesingizni": "auth.manageYour",
    "boshqaring": "auth.manageBusiness",
    "Ro'yxatdan o'tib, savdo, ombor va moliyani bitta tizimda boshqaring.": "auth.registerDesc",
    "© 2026 E-code ERP": "common.copyright",
    "Ro'yxatdan o'tish": "land.nav.register",
    "Yangi korxona uchun hisob yarating": "auth.createAccount",
    "Keyingi qadam": "common.nextStep",
    "Kiring": "land.nav.login",
    "Ortga": "common.back",
    "Saqlanmoqda...": "common.saving",
    "Foydalanuvchilar": "user.title",
    "Yangi foydalanuvchi": "user.newUser",
    "Tizimga yangi xodim qo'shish": "auth.addNewEmp",
    "To'liq ism": "auth.fullName",
    "Lavozim": "user.role",
    "Imkoniyatlar": "land.features.badge",
    "Modullar": "land.modules",
    "Boshlash": "land.hero.start",
    "Kirish": "land.nav.login",
    "B2B va B2C segmentlari uchun": "land.b2b",
    "Korporativ ERP": "land.erp",
    "Ekosistemasi": "land.eco",
    "Sotuv tarmog'ingizni to'liq raqamlashtiring. Bulutli texnologiyalar, ma'lumotlar xavfsizligi va ilg'or sinxronizatsiya yechimlari bilan ta'minlangan markazlashgan boshqaruv platformasi.": "land.desc1",
    "Tizimni sinash": "land.try",
    "🔒 Bank darajasidagi himoya": "land.sec1",
    "⚡ 99.9% Barqaror ishlash": "land.sec2",
    "☁️ 24/7 Avtomatik zaxira": "land.sec3",
    "Cheksiz imkoniyatlar ekotizimi": "land.ecosystem",
    "Bir-biriga bog'langan modullar arxitekturasi.": "land.arch",
    "Omnichannel POS Terminal": "land.omni",
    "Kassirlar uchun moslashtirilgan tezkor ishlash maydoni. Shtrix-kod, QR-to'lovlar, tarozilar apparati bilan bevosita lokal integratsiya. Offlayn bufer xotira.": "land.omniDesc",
    "BI & Moliyaviy Analitika": "land.bi",
    "Real vaqt rejimida rentabellik dushbordlari. Barcha moliyaviy operatsiyalar, debitor-kreditor qarzlarini chuqur tahlil qilish.": "land.biDesc",
    "Smart CRM Platformasi": "land.crm",
    "Avtomatlashgan keshbek, VIP mijozlar xaritasi (RFM tahlil) va korporativ mijozlar uchun xususiy qarz limitlari marshrutizatsiyasi.": "land.crmDesc",
    "Ko'p Tarmoqli Ombor (WMS)": "land.wms",
    "Murakkab Nomenklaturalar tarmog'ini partiyalar, hisob va xarajat narxlari hamda filiallarga avtomatik xizmat ko'rsatish orqali boshqarish.": "land.wmsDesc",
    "Yagona ma'lumotlar bazasida": "land.singleDb",
    "Qog'ozlar va bir nechta dasyurlarni unuting.": "land.noPaper",
    "Biznesingizni keyingi bosqichga olib chiqing": "land.nextLevel",
    "Hoziroq ro'yxatdan o'ting va platformaning barcha funksiyalaridan foydalaning.": "land.registerNow",
    "Bepul boshlash": "land.hero.start",
    "Bog'lanish": "land.contact",
    "Tizim": "land.system",
    "Parol yangilandi!": "auth.passUpdated",
    "Yangi parolingiz bilan tizimga kiring": "auth.loginWithNewPass",
    "Parolni tiklash": "auth.resetPass",
    "Yangi parol": "auth.newPass",
    "Parolni tasdiqlang": "auth.confirmPass",
    "Daromad": "dashboard.income",
    "Mijozlar": "sidebar.customers",
    "Buyurtma": "purchase.order"
};

['PosLogin.jsx', 'RegisterCompany.jsx', 'Register.jsx', 'Landing.jsx', 'Login.jsx'].forEach(file => {
  let filepath = 'c:/ERPPos_extracted/ERPPos/frontend/src/pages/' + file;
  if (!fs.existsSync(filepath)) return;
  
  let original = fs.readFileSync(filepath, 'utf8');
  let content = original;

  // Add the useLang hook if it doesn't exist
  if (!content.includes('useLang')) {
     const importMatch = content.match(/import .*?;?[\r\n]+/);
     if (importMatch) {
         content = content.slice(0, importMatch.index + importMatch[0].length) + 
           "import { useLang } from '../context/LangContext';\n" + 
           content.slice(importMatch.index + importMatch[0].length);
     }
  }

  // Inject useLang safely into ALL React components
  content = content.replace(/(function\s+[A-Z][A-Za-z0-9_]*\s*\([^)]*\)\s*\{)/g, (m, p1) => {
      if (m.includes('t, ') || m.includes('{ t }')) return m;
      return p1 + '\n  const { t } = useLang();\n';
  });
  content = content.replace(/(const\s+[A-Z][A-Za-z0-9_]*\s*=\s*\([^)]*\)\s*=>\s*\{)/g, (m, p1) => {
      if (m.includes('t, ') || m.includes('{ t }')) return m;
      return p1 + '\n  const { t } = useLang();\n';
  });
  content = content.replace(/(\n\s*const\s*\{\s*t\s*\}\s*=\s*useLang\(\);\s*){2,}/g, '\n  const { t } = useLang();\n');

  // Replace exact occurrences
  Object.keys(authMap).forEach(key => {
      const val = authMap[key];
      content = content.split('>' + key + '<').join('>{t(\'' + val + '\')}<');
      content = content.split('placeholder="' + key + '"').join('placeholder={t(\'' + val + '\')}');
  });

  if (content !== original) {
      fs.writeFileSync(filepath, content, 'utf8');
      console.log('Fixed ' + file);
  }
});

// Finally, rewrite uz.js and add the missing authMap translations if they aren't there!
const uzPath = 'c:/ERPPos_extracted/ERPPos/frontend/src/i18n/uz.js';
let uzContent = fs.readFileSync(uzPath, 'utf8');

let newKeys = [];
let keysMap = {};
Object.keys(authMap).forEach(k => {
    let key = authMap[k];
    if (!uzContent.includes("'" + key + "':") && !keysMap[key]) {
        newKeys.push("  '" + key + "': '" + k.replace(/'/g, "\\'") + "',");
        keysMap[key] = true;
    }
});

if (newKeys.length > 0) {
    let toAppend = '\n  // AUTOMATED AUTH TRANSLATIONS\n' + newKeys.join('\n') + '\n};\n';
    uzContent = uzContent.replace(/};\s*$/, toAppend);
    fs.writeFileSync(uzPath, uzContent, 'utf8');
    console.log('Added ' + newKeys.length + ' new translation keys to uz.js');
}
