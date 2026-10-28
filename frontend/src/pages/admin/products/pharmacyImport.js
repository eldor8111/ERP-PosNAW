// ── P.4: dorixona rejimida Excel import (faqat modul yoqilgan korxonada ishlatiladi) ─────────────
// Kalitlar backend (app/routers/product_import.py) ustunlari bilan bir xil. Narx, tan narxi va qoldiq — eng katta
// qadoq (quti) bo'yicha; qadoq sonlari bo'sh bo'lsa — 1 dona uchun. Blister va dona narxi serverda hisoblanadi.
import { emptyPack, packLevels, packPrices } from '../../../components/PharmacyProductModal';

const intOk = (v) => { const n = Number(v); return Number.isInteger(n) && n > 1; };
const isFilled = (v) => String(v ?? '').trim() !== '';

// Qator hisobi. "Qutidagi blister soni" berilsa: quti -> blister -> dona, aks holda quti -> dona.
// Ikkala son ham bo'sh bo'lsa — qadoqsiz (donalab sotiladi, narx 1 dona uchun).
export const bulkRowCalc = (row, names, round) => {
  const hasMid = isFilled(row.midQty);
  const hasUnit = isFilled(row.unitQty);
  const single = !hasMid && !hasUnit;
  const pack = {
    ...emptyPack, big_name: names.big, mid_name: names.mid,
    big_qty: hasMid ? row.midQty : row.unitQty, mid_qty: hasMid ? row.unitQty : '',
  };
  const incomplete = (hasMid && !intOk(row.midQty)) || (hasUnit && !intOk(row.unitQty)) || (hasMid && !hasUnit);
  const L = single || incomplete ? packLevels(emptyPack) : packLevels(pack);
  let pr = { mid: null, unit: null };
  if (single) pr = { mid: null, unit: Number(row.price) > 0 ? Number(row.price) : null };
  else if (!incomplete) pr = packPrices(pack, row.price, round);
  const topRatio = single || incomplete ? 1 : L.topRatio;
  return { pack, L, single, incomplete, pr, topRatio, stockTotal: (Number(row.stockBig) || 0) * topRatio };
};

// [kalit, tarjima kaliti, zaxira yorliq]
export const PHARMA_IMPORT_FIELDS = [
  ['Nomi', 'pharmacyImport.f.name', 'Dori nomi'],
  ['Barkod', 'pharmacyImport.f.barcode', 'Shtrix-kod'],
  ['MXIK', 'pharmacyImport.f.mxik', 'MXIK kodi'],
  // P.6: "Ko'p mahsulot qo'shish" yashil qatoridagi nomlar va tartib
  ['Katta qadoq narxi', 'pharmacyImport.f.bigPrice', '1 quti narxi'],
  ["Katta qadoqdagi o'rta qadoq soni", 'pharmacyImport.f.midCount', 'Qutidagi blister soni'],
  ["O'rta qadoqdagi dona soni", 'pharmacyImport.f.unitCount', 'Blisterdagi dona soni'],
  ['Qoldiq (katta qadoq)', 'pharmacyImport.f.bigStock', 'Quti soni (qoldiq)'],
  ['Seriya', 'pharmacyImport.f.lot', 'Seriya'],
  ['Yaroqlilik muddati', 'pharmacyImport.f.expiry', 'Yaroqlilik muddati'],
  ['Shakl', 'pharmacyImport.f.form', 'Dori shakli'],
  ['Ishlab chiqarilgan sana', 'pharmacyImport.f.mfg', 'Ishlab chiqarilgan sana (ixtiyoriy)'],
  ['Katta qadoq tan narxi', 'pharmacyImport.f.bigCost', '1 quti tan narxi'],
  ['Modda', 'pharmacyImport.f.substance', "Ta'sir etuvchi modda (vergul bilan)"],
  ['Doza', 'pharmacyImport.f.strength', 'Doza'],
  ['Ishlab chiqaruvchi', 'pharmacyImport.f.manufacturer', 'Ishlab chiqaruvchi'],
  ['Retseptli', 'pharmacyImport.f.rx', "Retseptli (ha/yo'q)"],
  ['Kategoriya', 'pharmacyImport.f.category', 'Kategoriya'],
  ['Ombor', 'pharmacyImport.f.warehouse', 'Ombor'],
  ['Mamlakat', 'pharmacyImport.f.country', 'Mamlakat'],
  ["Ro'yxat raqami", 'pharmacyImport.f.regNumber', "Ro'yxat raqami"],
  ['Nazorat toifasi', 'pharmacyImport.f.control', 'Nazorat toifasi'],
  ['ATX kodi', 'pharmacyImport.f.atc', 'ATX kodi'],
  ['Katta qadoq nomi', 'pharmacyImport.f.bigName', "Katta qadoq nomi (bo'sh: quti)"],
  ["O'rta qadoq nomi", 'pharmacyImport.f.midName', "O'rta qadoq nomi (bo'sh: blister)"],
  ['Qadoqdagi soni', 'pharmacyImport.f.packQty', 'Qadoqdagi soni (eski ustun)'],
  // donalab (ixtiyoriy): berilsa quti bo'yicha hisobdan ustun
  ['Chakana narxi', 'pharmacyImport.f.unitPrice', '1 dona narxi (qo\'lda)'],
  ['Tan narxi', 'pharmacyImport.f.unitCost', '1 dona tan narxi'],
  ['Qoldiq', 'pharmacyImport.f.unitStock', 'Qoldiq (dona)'],
  ['Ulgurji narxi', 'pharmacyImport.f.wholesale', 'Ulgurji narxi (dona)'],
  ['Min. qoldiq', 'pharmacyImport.f.minStock', 'Min. qoldiq (dona)'],
  ['SKU', 'pharmacyImport.f.sku', 'SKU'],
  ['Kod', 'pharmacyImport.f.code', 'Kod'],
  ['Holat', 'pharmacyImport.f.status', 'Holat'],
];

// Sonli ustunlar (dorixona rejimida tozalanadi: "100 000", "100,000", "12,5")
export const PHARMA_NUM_KEYS = [
  'Katta qadoq narxi', "Katta qadoqdagi o'rta qadoq soni", "O'rta qadoqdagi dona soni", 'Katta qadoq tan narxi',
  'Qoldiq (katta qadoq)', 'Chakana narxi', 'Tan narxi', 'Ulgurji narxi', 'Qoldiq', 'Min. qoldiq',
];

// P.6: Excel sana yacheykalari (raqam + sana formati) -> "YYYY-MM-DD". Yacheyka formatidan (m/d/yy, dd.mm.yyyy ...),
// kompyuter tili va vaqt mintaqasidan qat'i nazar aniq sana olinadi (yaroqlilik muddati, ishlab chiqarilgan sana).
// Faqat dorixona importida: XLSX.read({ cellNF: true }) bilan o'qilgan varaqqa qo'llanadi.
export const isoDateCells = (XLSX, ws) => {
  const SSF = XLSX && XLSX.SSF;
  if (!ws || !SSF || typeof SSF.parse_date_code !== 'function' || typeof SSF.is_date !== 'function') return;
  Object.keys(ws).forEach((addr) => {
    if (addr[0] === '!') return;
    const c = ws[addr];
    if (!c || c.t !== 'n' || !c.z || !SSF.is_date(c.z)) return;
    const d = SSF.parse_date_code(c.v);
    if (!d || !d.y) return;
    c.w = `${d.y}-${String(d.m).padStart(2, '0')}-${String(d.d).padStart(2, '0')}`;
  });
};

export const cleanPharmaNum = (v) => {
  let s = String(v ?? '').replace(/[\s ]/g, '');
  if (s.includes(',') && s.includes('.')) s = s.replace(/,/g, '');          // 100,000.50
  else if (/^\d{1,3}(,\d{3})+$/.test(s)) s = s.replace(/,/g, '');            // 100,000
  else s = s.replace(',', '.');                                              // 12,5
  return s.replace(/[^0-9.]/g, '');
};

export const normHeader = (h) => String(h ?? '').toLowerCase()
  .replace(/[ʻʼ`’‘]/g, "'").replace(/[*:]+$/g, '').replace(/\s+/g, ' ').trim();

// Excel sarlavhasi (o'zbekcha / ruscha / shablon) -> kalit
const ALIASES = {
  'Nomi': ['dori nomi', 'nomi', 'nomlanishi', 'mahsulot nomi', 'наименование', 'название', 'препарат', 'товар', 'name'],
  'Barkod': ['shtrix-kod', 'shtrix kod', 'shtrixkod', 'barkod', 'barcode', 'штрихкод', 'штрих-код', 'штрих код', 'ean',
    // P.12: eksportdagi "barcha shtrix-kodlar" ustuni (bir nechta kod vergul bilan)
    'barcha barkodlar', 'barkodlar', 'shtrix-kodlar', 'shtrix kodlar', 'все штрих-коды', 'штрих-коды', 'штрихкоды',
    'all barcodes', 'barcodes'],
  'MXIK': ['mxik', 'mxik kodi', 'ikpu', 'икпу', 'код икпу', 'мхик'],
  'Modda': ["ta'sir etuvchi modda", "ta'sir etuvchi modda (vergul bilan)", 'modda', 'mnn', 'мнн', 'действующее вещество'],
  'Shakl': ['dori shakli', 'shakl', 'shakli', 'форма', 'лекарственная форма', 'форма выпуска'],
  'Doza': ['doza', 'dozasi', 'дозировка', 'доза'],
  'Ishlab chiqaruvchi': ['ishlab chiqaruvchi', 'производитель', 'manufacturer'],
  'Retseptli': ['retseptli', "retseptli (ha/yo'q)", 'по рецепту', 'рецептурный', 'rx'],
  'Katta qadoq narxi': ['1 quti narxi', 'quti narxi', 'katta qadoq narxi', 'narxi', 'narx', 'sotuv narxi', 'цена',
    'цена продажи', 'розничная цена', 'цена за упаковку', 'цена упаковки'],
  "Katta qadoqdagi o'rta qadoq soni": ['qutidagi blister soni', "katta qadoqdagi o'rta qadoq soni", 'blister soni',
    'блистеров в упаковке', 'кол-во блистеров'],
  "O'rta qadoqdagi dona soni": ['dona soni', 'dona soni (blisterda yoki qutida)', 'blisterdagi dona soni',
    '1 blisterdagi dona soni',
    "o'rta qadoqdagi dona soni", 'qutidagi dona soni', 'штук в блистере', 'штук в упаковке', 'шт. в упаковке'],
  'Katta qadoq tan narxi': ['1 quti tan narxi', 'quti tan narxi', 'tan narxi (1 quti)', 'katta qadoq tan narxi',
    'kelish narxi', 'закупочная цена', 'цена закупки', 'цена прихода', 'себестоимость'],
  'Qoldiq (katta qadoq)': ['quti soni (qoldiq)', 'qoldiq (quti soni)', 'qoldiq (quti)', 'quti soni', 'qoldiq (katta qadoq)',
    'miqdori', 'soni',
    'количество', 'кол-во', 'остаток'],
  'Seriya': ['seriya', 'seriya raqami', 'серия', 'партия', 'lot'],
  'Yaroqlilik muddati': ['yaroqlilik muddati', 'muddati', 'amal qilish muddati', 'срок годности', 'годен до', 'exp', 'expiry'],
  'Ishlab chiqarilgan sana': ['ishlab chiqarilgan sana', 'ishlab chiqarilgan sana (ixtiyoriy)', 'ishlab chiqarilgan',
    'дата производства', 'дата изготовления', 'mfg'],
  'Kategoriya': ['kategoriya', 'категория', 'группа'],
  'Ombor': ['ombor', 'склад'],
  'Mamlakat': ['mamlakat', 'страна', 'страна производитель'],
  "Ro'yxat raqami": ["ro'yxat raqami", 'рег. номер', 'регистрационный номер', 'рег номер', 'рег. удостоверение'],
  'Nazorat toifasi': ['nazorat toifasi'],
  'ATX kodi': ['atx kodi', 'atx', 'атх', 'atc'],
  'Katta qadoq nomi': ['katta qadoq nomi', "katta qadoq nomi (bo'sh: quti)"],
  "O'rta qadoq nomi": ["o'rta qadoq nomi", "o'rta qadoq nomi (bo'sh: blister)"],
  'Qadoqdagi soni': ['qadoqdagi soni'],
  'Chakana narxi': ['1 dona narxi', "1 dona narxi (qo'lda)", 'dona narxi', 'chakana narxi'],
  'Tan narxi': ['1 dona tan narxi', 'tan narxi (dona)', 'tan narxi'],
  'Qoldiq': ['qoldiq (dona)', 'qoldiq dona', 'qoldiq'],
  'Ulgurji narxi': ['ulgurji narxi', 'ulgurji narxi (dona)', 'оптовая цена'],
  'Min. qoldiq': ['min. qoldiq', 'min. qoldiq (dona)', 'min qoldiq'],
  'SKU': ['sku', 'artikul', 'артикул'],
  'Kod': ['kod'],
  'Holat': ['holat', 'статус'],
};
const ALIAS_INDEX = (() => {
  const m = new Map();
  Object.entries(ALIASES).forEach(([key, list]) => list.forEach(a => { const n = normHeader(a); if (!m.has(n)) m.set(n, key); }));
  return m;
})();

// Ustunni tanish: avval taxallus, keyin aynan kalit / yorliq; topilmasa '' (foydalanuvchi o'zi tanlaydi)
export const pharmaMapHeader = (header, fields) => {
  const n = normHeader(header);
  if (!n) return '';
  if (ALIAS_INDEX.has(n)) return ALIAS_INDEX.get(n);
  const f = fields.find(x => x.key && x.key !== '__SKIP__' && (normHeader(x.key) === n || normHeader(x.label) === n));
  return f ? f.key : '';
};

const filled = (v) => String(v ?? '').trim() !== '';

// ── P.12: bitta dori bir necha qatorda — har qator alohida partiya (seriya, muddat, ishlab chiqarilgan sana, qoldiq) ──
// Kalit server (`_group_key`) bilan bir xil: nomi; nomsiz bo'lsa birinchi shtrix-kodi.
export const pharmaRowKey = (r) => {
  const name = String(r['Nomi'] ?? '').trim();
  if (name) return `n:${name}`;
  const code = String(r['Barkod'] ?? '').split(/[,;\r\n]+/).map(s => s.trim()).find(Boolean);
  return code ? `b:${code}` : null;
};

// Import bo'laklari: bir xil dori qatorlari birga (birinchi uchragan tartibda), bo'lak guruh chegarasida kesiladi —
// bitta dorining partiyalari ikki so'rovga bo'linmaydi (server ularni bitta mahsulotga birlashtiradi)
export const pharmaChunks = (rows, size) => {
  const groups = new Map();
  const order = [];
  rows.forEach((r) => {
    const k = pharmaRowKey(r);
    if (k != null && groups.has(k)) { groups.get(k).push(r); return; }
    const g = [r];
    order.push(g);
    if (k != null) groups.set(k, g);
  });
  const chunks = [];
  let cur = [];
  order.forEach((g) => {
    if (cur.length && cur.length + g.length > size) { chunks.push(cur); cur = []; }
    cur = cur.concat(g);
  });
  if (cur.length) chunks.push(cur);
  return chunks;
};

// Import ko'rinishida: yuqoridagi dorining partiya qatorlari (importRows indekslari)
export const pharmaLotRows = (rows, colMap, skipRows) => {
  const col = (key) => Object.keys(colMap).find(c => colMap[c] === key);
  const nameCol = col('Nomi');
  const codeCol = col('Barkod');
  const seen = new Set();
  const out = new Set();
  rows.forEach((row, i) => {
    if (i < skipRows - 1) return;
    const k = pharmaRowKey({ Nomi: nameCol ? row[nameCol] : '', Barkod: codeCol ? row[codeCol] : '' });
    if (k == null) return;
    if (seen.has(k)) out.add(i);
    else seen.add(k);
  });
  return out;
};

// Qator hisobi (ko'rinish uchun; asl hisob serverda): { line, warnings }. lotRow — yuqoridagi dorining partiyasi
// (narx, qadoq va MXIK birinchi qatordan olinadi, shu sababli faqat partiya ma'lumoti ko'rsatiladi)
export const pharmaImportPreview = (m, round, fmtNum, lotRow = false) => {
  if (lotRow) {
    const box = filled(m['Qoldiq (katta qadoq)']) ? Number(cleanPharmaNum(m['Qoldiq (katta qadoq)'])) : 0;
    const pcs = filled(m['Qoldiq']) ? Number(cleanPharmaNum(m['Qoldiq'])) : 0;
    const parts = [m['Seriya'], m['Yaroqlilik muddati']].map(v => String(v ?? '').trim()).filter(Boolean);
    if (pcs > 0) parts.push(`qoldiq ${fmtNum(pcs)} dona`);
    else if (box > 0) parts.push(`qoldiq ${fmtNum(box)} ${String(m['Katta qadoq nomi'] ?? '').trim() || 'quti'}`);
    const warnings = (pcs > 0 || box > 0) && !filled(m['Yaroqlilik muddati']) ? ['lot'] : [];
    return { line: parts.join(' · '), warnings, lotRow: true };
  }
  const mid = filled(m["Katta qadoqdagi o'rta qadoq soni"]) ? cleanPharmaNum(m["Katta qadoqdagi o'rta qadoq soni"]) : '';
  const pcs = filled(m["O'rta qadoqdagi dona soni"]) ? cleanPharmaNum(m["O'rta qadoqdagi dona soni"]) : '';
  const both = mid !== '' && pcs !== '';
  const names = {
    big: String(m['Katta qadoq nomi'] ?? '').trim() || 'quti',
    mid: String(m["O'rta qadoq nomi"] ?? '').trim() || 'blister',
  };
  const row = {
    price: filled(m['Katta qadoq narxi']) ? cleanPharmaNum(m['Katta qadoq narxi']) : '',
    midQty: both ? mid : '',
    unitQty: both ? pcs : (mid || pcs),
    stockBig: filled(m['Qoldiq (katta qadoq)']) ? cleanPharmaNum(m['Qoldiq (katta qadoq)']) : '',
  };
  const calc = bulkRowCalc(row, names, round);
  const manualUnit = filled(m['Chakana narxi']) ? Number(cleanPharmaNum(m['Chakana narxi'])) : null;
  const unitPrice = manualUnit != null ? manualUnit : calc.pr.unit;
  const stock = filled(m['Qoldiq']) ? Number(cleanPharmaNum(m['Qoldiq'])) : calc.stockTotal;
  const parts = [];
  if (!calc.single && calc.L.top) {
    parts.push(calc.L.midQty
      ? `1 ${names.big} = ${calc.L.bigQty} ${names.mid} = ${calc.L.topRatio} dona`
      : `1 ${names.big} = ${calc.L.topRatio} dona`);
  }
  if (calc.pr.mid != null) parts.push(`${names.mid} ${fmtNum(calc.pr.mid)}`);
  if (unitPrice != null) parts.push(`dona ${fmtNum(unitPrice)}`);
  if (stock > 0) parts.push(`qoldiq ${fmtNum(stock)} dona`);
  const warnings = [];
  if (calc.incomplete) warnings.push('qty');
  if (unitPrice == null) warnings.push('price');
  if (stock > 0 && !filled(m['Yaroqlilik muddati'])) warnings.push('lot');   // P.5: seriya ixtiyoriy
  if (!filled(m['MXIK'])) warnings.push('mxik');
  return { line: parts.join(' · '), warnings };
};

// Dorixona shabloni: "Dorilar" (namunalar) + "Yo'riqnoma"
export const PHARMA_TEMPLATE_HEADERS = [
  'Dori nomi', 'Shtrix-kod', 'MXIK kodi',
  '1 quti narxi', 'Qutidagi blister soni', 'Blisterdagi dona soni', 'Quti soni (qoldiq)',
  'Seriya', 'Yaroqlilik muddati', 'Dori shakli', 'Ishlab chiqarilgan sana',
  '1 quti tan narxi', "Ta'sir etuvchi modda", 'Doza', 'Ishlab chiqaruvchi', "Retseptli (ha/yo'q)",
  'Kategoriya', 'Mamlakat', "Ro'yxat raqami", 'ATX kodi',
];

const TEMPLATE_ROWS = [
  ['Paratsetamol 500 mg', '4780012345678', '', 100000, 5, 10, 3, 'LOT2026A', '2027-12-31', 'tabletka', '2025-12-01',
    70000, 'Paratsetamol', '500 mg', 'Nika Pharm', "yo'q", 'Dorilar', "O'zbekiston", '', 'N02BE01'],
  ['Ambroksol sirop 100 ml', '4780012345685', '', 25000, '', '', 10, '', '2027-06-30', 'sirop', '',
    18000, 'Ambroksol', '15 mg/5 ml', '', "yo'q", 'Dorilar', '', '', ''],
];

const GUIDE = [
  ['Ustun', 'Majburiy', 'Izoh'],
  ['Dori nomi', 'ha', 'Masalan: Paratsetamol 500 mg'],
  ['Shtrix-kod', "yo'q", "Bo'sh bo'lsa avtomatik yaratiladi"],
  ['MXIK kodi', 'tavsiya', "17 xonali kod. Bo'sh bo'lsa shtrix-kod bo'yicha katalogdan olinadi. Ustunni 'Matn' formatida saqlang"],
  ["Ta'sir etuvchi modda", "yo'q", "Bir nechta bo'lsa vergul bilan: Paratsetamol, Kofein"],
  ['Dori shakli', "yo'q", 'tabletka, kapsula, sirop, inyeksiya, malham, tomchi, kukun, eritma, sham, boshqa'],
  ["Retseptli (ha/yo'q)", "yo'q", "ha yoki yo'q"],
  ['1 quti narxi', 'ha', "Eng katta qadoq narxi. Blister va dona narxi o'zi hisoblanadi"],
  ['Qutidagi blister soni', "yo'q", "Blister bo'lmasa bo'sh qoldiring"],
  ['Blisterdagi dona soni', "yo'q", "Blister bo'lsa — 1 blisterdagi, bo'lmasa — 1 qutidagi dona soni. Qadoqsiz dori (sirop) uchun bo'sh: narx 1 dona uchun"],
  ['1 quti tan narxi', "yo'q", "Kelish narxi; donaga bo'linib saqlanadi"],
  ['Quti soni (qoldiq)', "yo'q", "Hozir omborda nechta quti bor. Donaga o'zi aylantiriladi"],
  ['Seriya', "yo'q", 'Qadoqda yozilgan seriya (LOT), ixtiyoriy'],
  ['Yaroqlilik muddati', 'qoldiq bo\'lsa', 'YYYY-MM-DD yoki DD.MM.YYYY yoki MM.YYYY'],
  ['Ishlab chiqarilgan sana', "yo'q", 'Ixtiyoriy; yaroqlilik muddatidan oldin bo\'lishi kerak'],
  ['Kategoriya', "yo'q", "Yo'q bo'lsa yangisi ochiladi"],
  ['Bir nechta partiya', "yo'q", "Har partiya alohida qatorda: nomi bir xil, seriya, muddat, ishlab chiqarilgan sana va quti soni o'ziniki. Narx va qadoq birinchi qatordan olinadi"],
  ['Bir nechta shtrix-kod', "yo'q", 'Bitta katakda vergul bilan: 4780012345678, 4780012345685. Birinchisi asosiy'],
];

export const downloadPharmacyTemplate = (XLSX, saveAs) => {
  const ws = XLSX.utils.aoa_to_sheet([PHARMA_TEMPLATE_HEADERS, ...TEMPLATE_ROWS]);
  ws['!cols'] = PHARMA_TEMPLATE_HEADERS.map(h => ({ wch: Math.max(12, h.length + 2) }));
  const guide = XLSX.utils.aoa_to_sheet(GUIDE);
  guide['!cols'] = [{ wch: 22 }, { wch: 14 }, { wch: 90 }];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Dorilar');
  XLSX.utils.book_append_sheet(wb, guide, "Yo'riqnoma");
  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), 'dorilar_shablon.xlsx');
};

// ── P.6: Excel'ga yuklab olish (faqat dorixonada) — mavjud jadval oxiriga qo'shiladigan ustunlar ───────
// Sarlavhalar import shablonidagidek: yuklab olingan faylni tahrirlab qayta import qilish mumkin.
export const PHARMA_EXPORT_HEADERS = [
  'MXIK kodi', '1 quti narxi', 'Qutidagi blister soni', 'Blisterdagi dona soni', 'Quti soni (qoldiq)',
  'Seriya', 'Yaroqlilik muddati', 'Dori shakli', 'Ishlab chiqarilgan sana',   // P.8: eng yaqin muddatli partiya
  'Ombor',   // P.12: partiya ombori (faqat 2+ partiyali dori qatorlarida)
];

// P.12: eksport qatorlari — 2+ partiyali dori: har partiya alohida qator (ro'yxat `with_batches` bilan olinadi),
// aks holda bitta qator (umumiy qoldiq va eng yaqin muddatli partiya, avvalgidek)
export const pharmaExportLines = (p) => (Array.isArray(p.batches) && p.batches.length > 1
  ? p.batches.map((b, k) => ({ b, lotOnly: k > 0 }))
  : [{ b: null, lotOnly: false }]);

// Mahsulot (ro'yxat javobi: units, stock_quantity, pharma, nearest_batch) -> PHARMA_EXPORT_HEADERS tartibidagi qiymatlar.
// Qadoqsiz (yoki murakkab tuzilmali) dori: narx va qoldiq 1 dona bo'yicha, sonlar bo'sh — importdagi qoida bilan bir xil.
// b — partiya (qoldig'i shu partiyaniki, ombori bilan); lotOnly — dorining keyingi partiya qatori: MXIK, narx, qadoq
// sonlari va shakl bo'sh (importda birinchi qatordan olinadi)
export const pharmaExportRow = (p, formLabel, b = null, lotOnly = false) => {
  const qty = b ? Number(b.quantity || 0) : Number(p.stock_quantity || 0);
  const r3 = (x) => Math.round(x * 1000) / 1000;
  const form = p.pharma?.dosage_form && !lotOnly ? formLabel(p.pharma.dosage_form) : '';
  const nb = b || p.nearest_batch || {};
  const tail = [nb.lot_number || '', nb.expiry_date || '', form, nb.manufacture_date || '', b ? (b.warehouse || '') : ''];
  const us = (Array.isArray(p.units) ? p.units : [])
    .map(u => ({ ratio: Number(u.ratio), price: u.sale_price != null ? u.sale_price : u.price }))
    .filter(u => u.ratio > 1).sort((a, b) => a.ratio - b.ratio);
  const simple = us.length === 1 || (us.length === 2 && Number.isInteger(us[1].ratio / us[0].ratio));
  const head = (row) => (lotOnly ? ['', '', '', '', row[4]] : row);
  if (!simple) return [...head([p.mxik_code || '', Number(p.sale_price || 0), '', '', r3(qty)]), ...tail];
  const big = us[us.length - 1];
  const boxPrice = big.price != null ? Number(big.price) : Number(p.sale_price || 0) * big.ratio;
  return us.length === 2
    ? [...head([p.mxik_code || '', boxPrice, big.ratio / us[0].ratio, us[0].ratio, r3(qty / big.ratio)]), ...tail]
    : [...head([p.mxik_code || '', boxPrice, '', big.ratio, r3(qty / big.ratio)]), ...tail];
};
