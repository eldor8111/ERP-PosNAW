import { useState, useEffect, useRef } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';
import { useLang } from '../context/LangContext';
import useCompanyFeatures from '../hooks/useCompanyFeatures';

// ── P.2: "Dori qo'shish" / "Dorini tahrirlash" oynasi (faqat dorixona rejimida) ───────────────────
// Oddiy mahsulot formasidan (ProductAddModal) alohida: dori ma'lumotlari, qadoq tuzilmasi, narx hisobi va
// seriya/muddatli boshlang'ich qoldiq shu yerda. Products.jsx ham shu fayldagi yordamchilarni ishlatadi.

const genBarcode = () => Math.floor(10000000 + Math.random() * 90000000).toString();
const BARCODE_FORMATS = [
  { value: 'ean8',  label: 'EAN-8',  len: 8 },
  { value: 'ean13', label: 'EAN-13', len: 13 },
  { value: 'upca',  label: 'UPC-A',  len: 12 },
  { value: 'free',  label: 'Erkin',  len: null },
];
const genBarcodeByFormat = (fmtVal) => {
  const f = BARCODE_FORMATS.find(x => x.value === fmtVal) || BARCODE_FORMATS[0];
  if (!f.len) return genBarcode();
  const min = Math.pow(10, f.len - 1);
  return String(Math.floor(min + Math.random() * (9 * Math.pow(10, f.len - 1))));
};
const genSku = () => 'SKU-' + Math.random().toString(36).substring(2, 8).toUpperCase();
const fmtNum = (v) => { const n = Number(v); return isNaN(n) ? '0' : n.toLocaleString('ru-RU'); };

const inputCls = "w-full px-4 py-3 border border-slate-200 rounded-xl text-base focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent bg-white";
const errCls = "border-red-400 ring-1 ring-red-400";
const packInp = inputCls;

function Field({ label, required, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-bold text-slate-700 mb-1.5">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

// ── Dori ma'lumotlari (D2.2 tuzilmasi) ──────────────────────────────────────────────────────
export const DOSAGE_FORMS = [
  ['tablet', 'Tabletka'], ['capsule', 'Kapsula'], ['syrup', 'Sirop'], ['injection', 'Inyeksiya'],
  ['ointment', 'Malham'], ['drops', 'Tomchi'], ['powder', 'Kukun'], ['solution', 'Eritma'],
  ['suppository', 'Sham'], ['other', 'Boshqa'],
];
export const STORAGE_TYPES = [['room', 'Xona harorati'], ['cold_2_8', 'Sovutgich (2-8 °C)'], ['frozen', 'Muzlatilgan']];
export const CONTROL_CLASSES = [
  ['none', "Yo'q"], ['potent', "Kuchli ta'sir etuvchi"], ['psychotropic', 'Psixotrop'],
  ['narcotic', 'Giyohvand'], ['precursor', 'Prekursor'],
];

export const emptyPharma = {
  dosage_form: '', strength: '', pack_qty: '', manufacturer: '', country: '', reg_number: '',
  reg_valid_until: '', atc_code: '', storage: '', is_rx: false, control_class: 'none',
  max_retail_price: '', substances: [],
};

// Serverdagi `pharma` blokidan (yoki null) forma holatiga
export const pharmaToForm = (ph) => (!ph ? { ...emptyPharma, substances: [] } : {
  dosage_form: ph.dosage_form || '', strength: ph.strength || '',
  pack_qty: ph.pack_qty != null ? String(ph.pack_qty) : '',
  manufacturer: ph.manufacturer || '', country: ph.country || '', reg_number: ph.reg_number || '',
  reg_valid_until: ph.reg_valid_until || '', atc_code: ph.atc_code || '', storage: ph.storage || '',
  is_rx: !!ph.is_rx, control_class: ph.control_class || 'none',
  max_retail_price: ph.max_retail_price != null ? String(Number(ph.max_retail_price)) : '',
  substances: Array.isArray(ph.substances) ? ph.substances.map(x => ({ id: x.id, name_uz: x.name_uz })) : [],
});

// Forma holatidan PharmaIn (POST/PUT /products `pharma`) — bo'sh maydonlar null
export const pharmaToPayload = (f) => {
  const str = (v) => (String(v ?? '').trim() || null);
  return {
    dosage_form: f.dosage_form || null, strength: str(f.strength),
    pack_qty: f.pack_qty !== '' && f.pack_qty != null ? Number(f.pack_qty) : null,
    manufacturer: str(f.manufacturer), country: str(f.country), reg_number: str(f.reg_number),
    reg_valid_until: f.reg_valid_until || null, atc_code: str(f.atc_code), storage: f.storage || null,
    is_rx: !!f.is_rx, control_class: f.control_class || 'none',
    max_retail_price: f.max_retail_price !== '' && f.max_retail_price != null ? Number(f.max_retail_price) : null,
    substance_ids: (f.substances || []).map(x => x.id),
  };
};

// ── Qadoq tuzilmasi ───────────────────────────────────────────────────────────────────────────
// Asosiy birlik (dona) <- o'rta qadoq (blister/pachka) <- katta qadoq (quti). Eng katta qadoq narxi kiritiladi,
// qolganlari o'zi hisoblanadi. Products.jsx (ko'p qo'shish, ro'yxat) ham shu yordamchilarni ishlatadi.
export const emptyPack = {
  mid_name: 'blister', mid_qty: '', mid_price: '', mid_auto: true, mid_barcode: '',
  big_name: 'quti', big_qty: '', big_barcode: '',
  unit_price: '', unit_auto: true,
  stock_big: '', stock_mid: '', stock_unit: '',
  lot: '', expiry: '', mfg: '',
  unsupported: false,
};

// PACK-CALC-START
// Narx hisobi (sof funksiya): katta narx / o'rtalar soni = o'rta narx; o'rta narx / donalar soni = dona narxi.
// O'rta qadoq bo'lmasa (midQty 0): dona = katta narx / katta qadoqdagi dona soni (bigQty).
// Bo'linmasa `round` qadamiga YUQORIGA yaxlitlanadi (0 bo'lsa 2 xonali).
export const calcPackPrices = (bigPrice, bigQty, midQty, round) => {
  const price = Number(bigPrice);
  const bq = Number(bigQty);
  const mq = Number(midQty) || 0;
  if (!(price > 0) || !(bq > 1)) return { mid: null, unit: null };
  const step = Number(round) || 0;
  const up = (x) => (step > 0 ? Math.ceil(x / step - 1e-9) * step : Math.ceil(x * 100 - 1e-6) / 100);
  if (mq > 1) {
    const mid = up(price / bq);
    return { mid, unit: up(mid / mq) };
  }
  return { mid: null, unit: up(price / bq) };
};
// PACK-CALC-END

const packInt = (v) => { const n = Number(v); return Number.isInteger(n) && n > 1 ? n : 0; };
const round4 = (x) => Math.round(Number(x) * 10000) / 10000;
const numOrNull = (v) => (v === '' || v == null || isNaN(Number(v)) ? null : Number(v));

// Tuzilma darajalari: top — narx kiritiladigan eng katta daraja ('big' | 'mid' | ''), ratio'lar dona'da
export const packLevels = (pack) => {
  const p = pack || emptyPack;
  const midQty = packInt(p.mid_qty);
  const bigQty = packInt(p.big_qty);
  if (bigQty && midQty) return { top: 'big', midQty, bigQty, midRatio: midQty, bigRatio: midQty * bigQty, topRatio: midQty * bigQty };
  if (bigQty) return { top: 'big', midQty: 0, bigQty, midRatio: 0, bigRatio: bigQty, topRatio: bigQty };
  if (midQty) return { top: 'mid', midQty, bigQty: 0, midRatio: midQty, bigRatio: 0, topRatio: midQty };
  return { top: '', midQty: 0, bigQty: 0, midRatio: 0, bigRatio: 0, topRatio: 1 };
};

// Joriy narxlar: { mid, unit } — qo'lda o'zgartirilgan bo'lsa shu qiymat, aks holda hisoblangan
export const packPrices = (pack, topPrice, round) => {
  const p = pack || emptyPack;
  const L = packLevels(p);
  if (!L.top) return { mid: null, unit: null };
  let autoMid = null;
  let autoUnit = null;
  if (L.top === 'big') {
    const c = calcPackPrices(topPrice, L.bigQty, L.midQty, round);
    autoMid = c.mid; autoUnit = c.unit;
  } else {
    autoUnit = calcPackPrices(topPrice, L.midQty, 0, round).unit;
  }
  const mid = L.top === 'big' && L.midQty ? (p.mid_auto === false ? numOrNull(p.mid_price) : autoMid) : null;
  let unit;
  if (p.unit_auto === false) unit = numOrNull(p.unit_price);
  else if (mid != null && p.mid_auto === false) unit = calcPackPrices(mid, L.midQty, 0, round).unit;
  else unit = autoUnit;
  return { mid, unit };
};

// Serverga yuboriladigan `units` (ratio dona'da)
export const packToUnits = (pack, topPrice, round, mult = 1) => {
  const p = pack || emptyPack;
  const L = packLevels(p);
  if (!L.top || p.unsupported) return [];
  const pr = packPrices(p, topPrice, round);
  const m = (v) => (v == null || v === '' || isNaN(Number(v)) ? null : round4(Number(v) * mult));
  const bc = (v) => (String(v ?? '').trim() || null);
  const units = [];
  if (L.midQty) units.push({ name: String(p.mid_name || '').trim(), ratio: L.midRatio, sale_price: L.top === 'mid' ? m(topPrice) : m(pr.mid), barcode: bc(p.mid_barcode) });
  if (L.bigQty) units.push({ name: String(p.big_name || '').trim(), ratio: L.bigRatio, sale_price: m(topPrice), barcode: bc(p.big_barcode) });
  return units;
};

// Boshlang'ich qoldiq jami dona'da: katta qadoq soni, o'rta qadoq soni va dona soni
export const packStockTotal = (pack) => {
  const p = pack || emptyPack;
  const L = packLevels(p);
  const n = (v) => Number(v) || 0;
  return (L.bigQty ? n(p.stock_big) * L.bigRatio : 0) + (L.midQty ? n(p.stock_mid) * L.midRatio : 0) + n(p.stock_unit);
};

// Tahrirlashda mavjud `units` dan tuzilmani tiklash: katta = eng katta ratio, o'rta = undan kichik.
// Qo'llab bo'lmaydigan tuzilma (2 tadan ko'p birlik, butun bo'linmaydigan ratio) -> unsupported (units yuborilmaydi, tegilmaydi).
export const packRestore = (product, round) => {
  const list = (Array.isArray(product?.units) ? product.units : [])
    .map(u => ({ ...u, ratio: Number(u.ratio) })).sort((a, b) => a.ratio - b.ratio);
  if (!list.length) return { pack: { ...emptyPack }, topRatio: 1, topPrice: '' };
  const bad = { pack: { ...emptyPack, unsupported: true }, topRatio: 1, topPrice: '' };
  if (list.length > 2 || !list.every(u => packInt(u.ratio))) return bad;
  let pack = { ...emptyPack };
  let big;
  let mid = null;
  if (list.length === 2) {
    mid = list[0]; big = list[1];
    if (big.ratio % mid.ratio !== 0) return bad;
    pack = { ...pack, mid_name: mid.name, mid_qty: String(mid.ratio), mid_barcode: mid.barcode || '',
      big_name: big.name, big_qty: String(big.ratio / mid.ratio), big_barcode: big.barcode || '' };
  } else {
    big = list[0];
    pack = { ...pack, big_name: big.name, big_qty: String(big.ratio), big_barcode: big.barcode || '' };
  }
  const unitPrice = Number(product.sale_price) || 0;
  const topPrice = big.sale_price != null ? Number(big.sale_price) : round4(unitPrice * big.ratio);
  const auto = packPrices({ ...pack, mid_auto: true, unit_auto: true }, topPrice, round);
  const same = (a, b) => a != null && b != null && Math.abs(Number(a) - Number(b)) < 1e-6;
  const midStored = mid && mid.sale_price != null ? Number(mid.sale_price) : null;
  pack.mid_price = midStored != null ? String(midStored) : '';
  pack.mid_auto = !mid || midStored == null || same(midStored, auto.mid);
  pack.unit_price = unitPrice ? String(unitPrice) : '';
  pack.unit_auto = !unitPrice || same(unitPrice, auto.unit);
  return { pack, topRatio: big.ratio, topPrice: topPrice ? String(topPrice) : '' };
};

// Ro'yxatdagi ko'rinish: "1 quti = 5 blister = 50 dona"
export const packSummary = (units, unitName = 'dona') => {
  const list = (Array.isArray(units) ? units : []).map(u => ({ name: u.name, ratio: Number(u.ratio) }))
    .filter(u => u.name && u.ratio > 0).sort((a, b) => b.ratio - a.ratio);
  if (!list.length) return '';
  const num = (n) => String(Number(n.toFixed(3)));
  if (list.length === 2 && Number.isInteger(list[0].ratio / list[1].ratio)) {
    return `1 ${list[0].name} = ${num(list[0].ratio / list[1].ratio)} ${list[1].name} = ${num(list[0].ratio)} ${unitName}`;
  }
  return list.map(u => `1 ${u.name} = ${num(u.ratio)} ${unitName}`).join(' · ');
};

// Oyna pastidagi xulosa: "1 quti = 5 blister = 50 dona · quti 100 000 · blister 20 000 · dona 2 000"
export const packLine = (pack, topPrice, round, unitName = 'dona') => {
  const p = pack || emptyPack;
  const L = packLevels(p);
  if (!L.top || p.unsupported) return '';
  const pr = packPrices(p, topPrice, round);
  const head = packSummary(packToUnits(p, 1, 0), unitName);
  const parts = [head];
  if (L.bigQty && Number(topPrice) > 0) parts.push(`${String(p.big_name || '').trim()} ${fmtNum(topPrice)}`);
  if (L.top === 'mid' && Number(topPrice) > 0) parts.push(`${String(p.mid_name || '').trim()} ${fmtNum(topPrice)}`);
  if (L.top === 'big' && L.midQty && pr.mid != null) parts.push(`${String(p.mid_name || '').trim()} ${fmtNum(pr.mid)}`);
  if (pr.unit != null) parts.push(`${unitName} ${fmtNum(pr.unit)}`);
  return parts.join(' · ');
};

// Tuzilma va boshlang'ich qoldiq tekshiruvi: xato matni yoki '' (tf — (kalit, zaxira) tarjimon)
export const validatePack = (pack, { tf, unitName = 'dona', otherBarcodes = [], stockTotal = 0 }) => {
  const p = pack || emptyPack;
  if (p.unsupported) return '';
  const bad = (v) => String(v ?? '').trim() !== '' && !packInt(v);
  if (bad(p.mid_qty) || bad(p.big_qty)) return tf('packStruct.errQty', "Qadoqdagi son butun son va 1 dan katta bo'lishi kerak");
  const L = packLevels(p);
  const names = [];
  if (L.midQty) names.push(String(p.mid_name || '').trim());
  if (L.bigQty) names.push(String(p.big_name || '').trim());
  if (names.some(n => !n)) return tf('packStruct.errName', "Qadoq nomini kiriting (masalan: quti, blister)");
  const low = names.map(n => n.toLowerCase());
  if (new Set(low).size !== low.length || low.includes(String(unitName || '').trim().toLowerCase())) {
    return tf('packStruct.errDupName', "Qadoq nomlari takrorlanmasligi va asosiy birlikdan farq qilishi kerak");
  }
  const seen = new Set((otherBarcodes || []).map(s => String(s ?? '').trim()).filter(Boolean));
  const codes = [L.midQty ? p.mid_barcode : '', L.bigQty ? p.big_barcode : ''].map(s => String(s ?? '').trim()).filter(Boolean);
  for (const c of codes) {
    if (seen.has(c)) return tf('packStruct.errBarcode', "Qadoq shtrix-kodlari takrorlanmasligi kerak");
    seen.add(c);
  }
  if (stockTotal > 0) {
    if (!String(p.lot || '').trim()) return tf('packStruct.errLot', "Boshlang'ich qoldiq uchun seriya raqamini kiriting");
    if (!p.expiry) return tf('packStruct.errExpiry', "Boshlang'ich qoldiq uchun yaroqlilik muddatini kiriting");
    if (p.expiry <= new Date().toISOString().slice(0, 10)) return tf('packStruct.errExpiryPast', "Yaroqlilik muddati bugundan keyin bo'lishi kerak");
  }
  return '';
};

const packName = (tf, key, fallback, name) => tf(key, fallback).replace('{name}', name);

// Dorixonada boshlang'ich qoldiq: katta qadoq soni, o'rta qadoq soni, dona soni -> jami dona; seriya va muddat
export function PackStockFields({ pack, onChange, unitName = 'dona', tf, error }) {
  const p = pack || emptyPack;
  const L = packLevels(p);
  const total = packStockTotal(p);
  const set = (patch) => onChange({ ...p, ...patch });
  const num = (key, intOnly) => (e) => set({ [key]: e.target.value.replace(intOnly ? /[^0-9]/g : /[^0-9.]/g, '') });
  const unitLbl = unitName || 'dona';
  const needLot = total > 0;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {L.bigQty > 0 && (
          <Field label={packName(tf, 'packStruct.stockCount', '{name} soni', String(p.big_name || '').trim() || tf('packStruct.bigDefault', 'katta qadoq'))}>
            <input type="text" inputMode="numeric" className={packInp} value={p.stock_big} onChange={num('stock_big', true)} placeholder="0" />
          </Field>
        )}
        {L.midQty > 0 && (
          <Field label={packName(tf, 'packStruct.stockCount', '{name} soni', String(p.mid_name || '').trim() || tf('packStruct.midDefault', "o'rta qadoq"))}>
            <input type="text" inputMode="numeric" className={packInp} value={p.stock_mid} onChange={num('stock_mid', true)} placeholder="0" />
          </Field>
        )}
        <Field label={L.top ? packName(tf, 'packStruct.stockCount', '{name} soni', unitLbl) : tf('packStruct.stockUnits', "Boshlang'ich qoldiq")}>
          <input type="text" inputMode="decimal" className={packInp} value={p.stock_unit} onChange={num('stock_unit', false)} placeholder="0" />
        </Field>
      </div>
      {(L.top || total > 0) && (
        <p className="text-sm font-bold text-emerald-700">{tf('packStruct.total', 'jami')}: {Number(total.toFixed(3))} {unitLbl}</p>
      )}
      {needLot && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-amber-50/60 border border-amber-200 rounded-xl p-3">
          <Field label={tf('packStruct.lot', 'Seriya raqami')} required hint={tf('pharmacyModal.lotHint', 'Qadoqda yozilgan, masalan: LOT2026A')}>
            <input className={`${packInp} ${error && !String(p.lot || '').trim() ? errCls : ''}`} value={p.lot} maxLength={100} onChange={e => set({ lot: e.target.value })} />
          </Field>
          <Field label={tf('packStruct.expiry', 'Yaroqlilik muddati')} required hint={tf('pharmacyModal.expiryHint', 'Qadoqda "EXP" yoki "Yaroqlilik muddati" deb yozilgan')}>
            <input type="date" className={`${packInp} ${error && !p.expiry ? errCls : ''}`} value={p.expiry} onChange={e => set({ expiry: e.target.value })} />
          </Field>
          <Field label={tf('packStruct.mfg', 'Ishlab chiqarilgan sana')}>
            <input type="date" className={packInp} value={p.mfg} onChange={e => set({ mfg: e.target.value })} />
          </Field>
        </div>
      )}
    </div>
  );
}

// Ta'sir etuvchi moddalarni qidirib tanlash (+ yangi modda qo'shish): GET/POST /api/pharmacy/substances
export function SubstancePicker({ value, onChange, tf, allowCreate = true }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef(null);
  const term = q.trim();

  useEffect(() => {
    const close = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get('/pharmacy/substances', { params: { search: term || undefined, limit: 20 }, _suppressToast: true });
        setResults(Array.isArray(data) ? data : []);
      } catch { setResults([]); }
    }, 250);
    return () => clearTimeout(timer);
  }, [term, open]);

  const add = (sub) => {
    if (!(value || []).some(x => x.id === sub.id)) onChange([...(value || []), { id: sub.id, name_uz: sub.name_uz }]);
    setQ(''); setOpen(false);
  };
  const remove = (id) => onChange((value || []).filter(x => x.id !== id));

  const createNew = async () => {
    if (!term || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post('/pharmacy/substances', { name_uz: term }, { _suppressToast: true });
      add(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || tf('pharmaProduct.substanceCreateError', "Moddani qo'shib bo'lmadi"));
    } finally { setBusy(false); }
  };

  const exact = results.some(r => (r.name_uz || '').toLowerCase() === term.toLowerCase());
  const shown = results.filter(r => !(value || []).some(x => x.id === r.id));
  return (
    <div ref={wrapRef} className="relative">
      <div className="flex flex-wrap gap-1.5 mb-2">
        {(value || []).map(x => (
          <span key={x.id} className="inline-flex items-center gap-1 px-2.5 py-1 bg-emerald-100 text-emerald-800 text-xs font-semibold rounded-lg">
            {x.name_uz}
            <button type="button" onClick={() => remove(x.id)} className="text-emerald-600 hover:text-red-500" aria-label="remove">×</button>
          </span>
        ))}
      </div>
      <input className={inputCls} value={q} placeholder={tf('pharmaProduct.substanceSearch', 'Moddani qidiring (masalan: paratsetamol)')}
        onChange={e => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} />
      {open && (shown.length > 0 || (allowCreate && term && !exact)) && (
        <div className="absolute z-[200] left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-56 overflow-y-auto">
          {shown.map(r => (
            <div key={r.id} onClick={() => add(r)} className="px-4 py-2.5 hover:bg-emerald-50 cursor-pointer text-sm text-slate-700 border-b border-slate-50 last:border-0">
              {r.name_uz}{r.name_lat ? <span className="text-xs text-slate-400"> · {r.name_lat}</span> : null}
            </div>
          ))}
          {allowCreate && term && !exact && (
            <button type="button" disabled={busy} onClick={createNew}
              className="w-full text-left px-4 py-2.5 text-sm font-semibold text-blue-600 hover:bg-blue-50 disabled:opacity-50">
              + {tf('pharmaProduct.addSubstance', "Yangi modda qo'shish")}: {term}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Bo'lim va avto-belgi: komponent TASHQARISIDA (aks holda har renderda qayta yaratilib, kiritish fokusi yo'qoladi)
const Section = ({ n, title, hint, children }) => (
  <div className="bg-white border border-slate-200 rounded-2xl p-4 md:p-5 space-y-4">
    <div>
      <h4 className="text-base md:text-lg font-black text-slate-800"><span className="text-emerald-600">{n}.</span> {title}</h4>
      {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
    </div>
    {children}
  </div>
);
const AutoTag = ({ auto, has, onReset, tf }) => (auto
  ? (has ? <span className="ml-1 text-[10px] font-bold text-emerald-600">{tf('packStruct.auto', 'avto')}</span> : null)
  : <button type="button" onClick={onReset} className="ml-1 text-[10px] font-bold text-blue-600 hover:underline">{'↺ ' + tf('packStruct.resetAuto', 'avto hisob')}</button>);


// ── Oyna holati ───────────────────────────────────────────────────────────────────────────────
// Mavjud mahsulotdan (yoki bo'sh) boshlang'ich forma holati. pack — qadoq tuzilmasi, bigPrice — "1 katta qadoq" narxi,
// mode: 'pack' (qadoqli) | 'single' (faqat donalab). cost — qadoq rejimida "1 katta qadoq" uchun, aks holda dona uchun.
export const pharmacyFormFromProduct = (product, round) => {
  const base = {
    name: '', barcode: '', barcode_format: 'ean13', category_id: '', requires_marking: false, mxik: '',
    mode: 'pack', hasMid: false, bigPrice: '', singlePrice: '', cost: '', wh: '',
  };
  if (!product) return { form: { ...base, barcode: genBarcodeByFormat('ean13') }, pack: { ...emptyPack }, pharma: pharmaToForm(null) };
  const r = packRestore(product, round);
  const form = {
    ...base,
    name: product.name || '', barcode: product.barcode || '', category_id: product.category_id ? String(product.category_id) : '',
    requires_marking: !!product.requires_marking, mxik: product.mxik_code || '',
  };
  const costUnit = Number(product.cost_price) || 0;
  if (r.pack.unsupported || !Array.isArray(product.units) || product.units.length === 0) {
    form.mode = 'single';
    form.singlePrice = product.sale_price != null ? String(Number(product.sale_price)) : '';
    form.cost = costUnit ? String(costUnit) : '';
  } else {
    form.mode = 'pack';
    form.hasMid = product.units.length === 2;
    form.bigPrice = r.topPrice;
    form.cost = costUnit ? String(round4(costUnit * r.topRatio)) : '';
  }
  return { form, pack: r.pack, pharma: pharmaToForm(product.pharma) };
};

// Effektiv tuzilma: donalab rejimida qadoq sonlari e'tiborsiz; "ichida blister bor" belgisisiz o'rta son e'tiborsiz;
// belgi bor-u, qutidagi blister soni yo'q (tugallanmagan) bo'lsa — tuzilma hali yo'q hisoblanadi
const effectivePack = (pack, mode, hasMid) => {
  if (mode === 'single') return { ...pack, big_qty: '', mid_qty: '' };
  if (!hasMid) return { ...pack, mid_qty: '' };
  if (!packInt(pack.big_qty)) return { ...pack, big_qty: '', mid_qty: '' };
  return pack;
};

export default function PharmacyProductModal({ product = null, onClose, onSaved, warehouses = [], defaultWarehouseId = '' }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();
  const round = Number(features?.pharmacy_settings?.price_round) || 0;
  const isEdit = !!product;
  const baseUnit = (isEdit && product.unit) ? product.unit : 'dona';

  const [init] = useState(() => pharmacyFormFromProduct(product, round));
  const [form, setForm] = useState(init.form);
  const [pack, setPack] = useState(init.pack);
  const [pharma, setPharma] = useState(init.pharma);
  const [whId, setWhId] = useState(defaultWarehouseId ? String(defaultWarehouseId) : '');
  const [showMore, setShowMore] = useState(false);
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const bodyRef = useRef(null);

  useEffect(() => {
    api.get('/categories/all').then(r => setCategories(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  }, []);

  const setF = (patch) => setForm(f => ({ ...f, ...patch }));
  const setP = (patch) => setPack(p => ({ ...p, ...patch }));
  const single = form.mode === 'single';
  const eff = effectivePack(pack, form.mode, form.hasMid);
  const L = packLevels(eff);
  const topPrice = single ? '' : form.bigPrice;
  const pr = single ? { mid: null, unit: numOrNull(form.singlePrice) } : packPrices(eff, topPrice, round);
  const stockTotal = isEdit ? 0 : packStockTotal(eff);
  const bigName = String(pack.big_name || '').trim() || tf('packStruct.bigDefault', 'katta qadoq');
  const midName = String(pack.mid_name || '').trim() || tf('packStruct.midDefault', "o'rta qadoq");
  const line = single ? '' : packLine(eff, topPrice, round, baseUnit);
  const maxRetail = pharma.max_retail_price;
  const overMax = maxRetail !== '' && pr.unit != null && Number(pr.unit) > Number(maxRetail);

  const fail = (msg, openMore = false) => {
    setError(msg);
    if (openMore) setShowMore(true);
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return fail(tf('pharmacyModal.errName', 'Dori nomini kiriting'));
    if (!form.barcode.trim()) return fail(tf('pharmacyModal.errBarcode', 'Shtrix-kodni kiriting'));
    if (!form.mxik.trim()) return fail(tf('pharmaProduct.mxikRequired', 'Dorixona rejimida MXIK kodi majburiy'), true);
    if (single) {
      if (!(Number(form.singlePrice) > 0)) return fail(tf('pharmacyModal.errUnitPrice', 'Dona narxini kiriting'));
    } else {
      if (!L.top || (form.hasMid && !(L.bigQty && L.midQty)) || (!form.hasMid && !L.bigQty)) {
        return fail(tf('pharmacyModal.errCounts', "Qadoqdagi sonlarni kiriting (1 dan katta butun son)"));
      }
      if (!(Number(form.bigPrice) > 0)) return fail(packName(tf, 'pharmacyModal.errBigPrice', '1 {name} narxini kiriting', bigName));
      if (pr.unit == null) return fail(tf('pharmacyModal.errUnitPrice', 'Dona narxini kiriting'));
    }
    const pErr = validatePack(eff, { tf, unitName: baseUnit, otherBarcodes: [form.barcode], stockTotal });
    if (pErr) return fail(pErr);

    const topRatio = single ? 1 : L.topRatio;
    const payload = {
      name: form.name.trim(),
      barcode: form.barcode.trim(),
      category_id: form.category_id ? Number(form.category_id) : null,
      cost_price: round4((Number(form.cost) || 0) / topRatio),
      sale_price: round4(pr.unit ?? 0),
      mxik_code: form.mxik.trim(),
      requires_marking: !!form.requires_marking,
      pharma: pharmaToPayload(pharma),
    };
    // units: to'liq almashtiriladi ([] = o'chirish); tushunarsiz (murakkab) tuzilmada tegilmaydi
    if (!pack.unsupported) payload.units = single ? [] : packToUnits(eff, topPrice, round, 1);
    if (!isEdit) {
      payload.sku = genSku();
      payload.unit = 'dona';
      payload.product_type = 'stock';
      if (stockTotal > 0) {
        payload.initial_stock = stockTotal;
        payload.initial_warehouse_id = whId ? Number(whId) : undefined;
        payload.initial_lot_number = pack.lot.trim();
        payload.initial_expiry_date = pack.expiry;
        if (pack.mfg) payload.initial_manufacture_date = pack.mfg;
      }
    }

    setSaving(true); setError('');
    try {
      const res = isEdit ? await api.put(`/products/${product.id}`, payload) : await api.post('/products', payload);
      toast.success(isEdit ? tf('pharmacyModal.updated', 'Dori yangilandi') : tf('pharmacyModal.created', "Dori qo'shildi"));
      onSaved?.(res.data);
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      fail(Array.isArray(detail) ? detail.map(d => d.msg).join(' | ') : String(detail || err.message || tf('pharmacyModal.saveError', 'Xatolik yuz berdi')));
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-slate-50 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[96vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 md:px-6 py-4 border-b border-slate-200 bg-white rounded-t-2xl shrink-0">
          <h3 className="text-lg md:text-xl font-bold text-slate-800">
            {isEdit ? tf('pharmacyModal.titleEdit', 'Dorini tahrirlash') : tf('pharmacyModal.titleAdd', "Dori qo'shish")}
          </h3>
          <button type="button" onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400" aria-label="close">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <form onSubmit={handleSave} className="flex flex-col min-h-0 flex-1">
          <div ref={bodyRef} className="overflow-y-auto flex-1 p-3 md:p-5 space-y-4">
            {error && (
              <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">{error}</div>
            )}

            {/* 1. Asosiy */}
            <Section n={1} title={tf('pharmacyModal.s1', 'Asosiy')}>
              <Field label={tf('pharmacyModal.name', 'Dori nomi')} required hint={tf('pharmacyModal.nameHint', 'Masalan: Paratsetamol 500 mg')}>
                <input className={`${inputCls} ${error && !form.name.trim() ? errCls : ''}`} value={form.name} maxLength={255}
                  onChange={e => setF({ name: e.target.value })} autoFocus={!isEdit} />
              </Field>
              <Field label={tf('pharmacyModal.barcode', 'Shtrix-kod')} required hint={tf('pharmacyModal.barcodeHint', 'Skaner bilan o\'qing yoki "Yaratish" tugmasini bosing')}>
                <div className="flex gap-2">
                  <input className={`${inputCls} font-mono ${error && !form.barcode.trim() ? errCls : ''}`} value={form.barcode}
                    onChange={e => setF({ barcode: e.target.value })} />
                  {!isEdit && (
                    <select className="px-2 border border-slate-200 rounded-xl text-sm bg-white" value={form.barcode_format}
                      onChange={e => setF({ barcode_format: e.target.value, barcode: genBarcodeByFormat(e.target.value) })}>
                      {BARCODE_FORMATS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                    </select>
                  )}
                  <button type="button" onClick={() => setF({ barcode: genBarcodeByFormat(form.barcode_format) })}
                    className="px-4 rounded-xl bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-sm font-bold whitespace-nowrap">
                    {tf('pharmacyModal.generate', 'Yaratish')}
                  </button>
                </div>
              </Field>
              <Field label={tf('pharmaProduct.substances', "Ta'sir etuvchi moddalar")} hint={tf('pharmacyModal.substanceHint', 'Masalan: paratsetamol. Topilmasa — yangisini qo\'shing')}>
                <SubstancePicker value={pharma.substances} onChange={(subs) => setPharma(p => ({ ...p, substances: subs }))} tf={tf} />
              </Field>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label={tf('pharmaProduct.dosageForm', 'Dori shakli')}>
                  <select className={inputCls} value={pharma.dosage_form} onChange={e => setPharma(p => ({ ...p, dosage_form: e.target.value }))}>
                    <option value="">—</option>
                    {DOSAGE_FORMS.map(([k, label]) => <option key={k} value={k}>{tf(`pharmaProduct.form.${k}`, label)}</option>)}
                  </select>
                </Field>
                <Field label={tf('pharmaProduct.strength', 'Doza')} hint={tf('pharmacyModal.strengthHint', 'Masalan: 500 mg')}>
                  <input className={inputCls} value={pharma.strength} maxLength={100} placeholder="500 mg" onChange={e => setPharma(p => ({ ...p, strength: e.target.value }))} />
                </Field>
                <Field label={tf('pharmacyModal.category', 'Kategoriya (ixtiyoriy)')}>
                  <select className={inputCls} value={form.category_id} onChange={e => setF({ category_id: e.target.value })}>
                    <option value="">—</option>
                    {categories.map(c => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
                  </select>
                </Field>
                <label className="flex items-center gap-3 cursor-pointer select-none self-end pb-3">
                  <input type="checkbox" checked={!!pharma.is_rx} onChange={e => setPharma(p => ({ ...p, is_rx: e.target.checked }))}
                    className="w-5 h-5 text-emerald-600 rounded border-slate-300 cursor-pointer" />
                  <span className="text-base font-bold text-slate-700">{tf('pharmaProduct.isRx', 'Retseptli dori')}</span>
                </label>
              </div>
            </Section>

            {/* 2. Qadoq va narx */}
            <Section n={2} title={tf('pharmacyModal.s2', 'Qadoq va narx')}
              hint={single ? undefined : tf('pharmacyModal.s2Hint', "Eng katta qadoq narxini kiriting — blister va dona narxi o'zi hisoblanadi")}>
              {!pack.unsupported && (
                <label className="flex items-center gap-3 cursor-pointer select-none">
                  <input type="checkbox" checked={single} onChange={e => setF({ mode: e.target.checked ? 'single' : 'pack' })}
                    className="w-5 h-5 text-emerald-600 rounded border-slate-300 cursor-pointer" />
                  <span className="text-sm font-semibold text-slate-700">{tf('pharmacyModal.singleOnly', 'Faqat donalab sotiladi (qadoqsiz)')}</span>
                </label>
              )}
              {pack.unsupported && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800">
                  {tf('packStruct.unsupported', "Bu mahsulotning qadoq tuzilmasi murakkab (2 tadan ko'p birlik): shu oynada o'zgartirilmaydi va saqlanganda tegilmaydi.")}
                </div>
              )}

              {single ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field label={packName(tf, 'packStruct.price', '{name} narxi', baseUnit)} required hint={tf('pharmacyModal.unitPriceHint', 'Masalan: 2 000')}>
                    <input type="text" inputMode="decimal" className={`${inputCls} ${error && !(Number(form.singlePrice) > 0) ? errCls : ''}`} value={form.singlePrice}
                      onChange={e => setF({ singlePrice: e.target.value.replace(/[^0-9.]/g, '') })} />
                  </Field>
                  <Field label={packName(tf, 'pharmacyModal.costPer', '1 {name} tan narxi (ixtiyoriy)', baseUnit)}>
                    <input type="text" inputMode="decimal" className={inputCls} value={form.cost}
                      onChange={e => setF({ cost: e.target.value.replace(/[^0-9.]/g, '') })} />
                  </Field>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Field label={tf('packStruct.bigName', 'Katta qadoq nomi')} hint={tf('pharmacyModal.bigNameHint', 'Masalan: quti')}>
                      <input className={inputCls} value={pack.big_name} maxLength={50} placeholder="quti" onChange={e => setP({ big_name: e.target.value })} />
                    </Field>
                    <Field label={packName(tf, 'pharmacyModal.bigPrice', '1 {name} narxi', bigName)} required hint={tf('pharmacyModal.bigPriceHint', 'Masalan: 100 000')}>
                      <input type="text" inputMode="decimal" className={`${inputCls} ${error && !(Number(form.bigPrice) > 0) ? errCls : ''}`} value={form.bigPrice}
                        onChange={e => setF({ bigPrice: e.target.value.replace(/[^0-9.]/g, '') })} />
                    </Field>
                  </div>

                  <label className="flex items-center gap-3 cursor-pointer select-none">
                    <input type="checkbox" checked={form.hasMid}
                      onChange={e => { setF({ hasMid: e.target.checked }); setP({ big_qty: '', mid_qty: '', mid_auto: true }); }}
                      className="w-5 h-5 text-emerald-600 rounded border-slate-300 cursor-pointer" />
                    <span className="text-sm font-semibold text-slate-700">{tf('pharmacyModal.hasMid', 'Ichida blister/pachka bor')}</span>
                  </label>

                  {form.hasMid && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <Field label={tf('packStruct.midName', "O'rta qadoq nomi")} hint={tf('pharmacyModal.midNameHint', 'Masalan: blister')}>
                        <input className={inputCls} value={pack.mid_name} maxLength={50} placeholder="blister" onChange={e => setP({ mid_name: e.target.value })} />
                      </Field>
                      <Field label={packName(tf, 'pharmacyModal.midCount', '1 {name} ichida nechta {inner}', bigName).replace('{inner}', midName)} required hint={tf('pharmacyModal.midCountHint', 'Masalan: 5')}>
                        <input type="text" inputMode="numeric" className={inputCls} value={pack.big_qty} placeholder="5"
                          onChange={e => setP({ big_qty: e.target.value.replace(/[^0-9]/g, '') })} />
                      </Field>
                    </div>
                  )}

                  <Field label={packName(tf, 'pharmacyModal.unitCount', '1 {name} ichida nechta dona', form.hasMid ? midName : bigName)} required
                    hint={tf('pharmacyModal.unitCountHint', 'Masalan: 10')}>
                    <input type="text" inputMode="numeric" className={inputCls} placeholder="10"
                      value={form.hasMid ? pack.mid_qty : pack.big_qty}
                      onChange={e => setP({ [form.hasMid ? 'mid_qty' : 'big_qty']: e.target.value.replace(/[^0-9]/g, '') })} />
                  </Field>

                  {L.top && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-emerald-50/60 border border-emerald-200 rounded-xl p-3">
                      {form.hasMid && L.midQty > 0 && (
                        <Field label={<>{packName(tf, 'packStruct.price', '{name} narxi', midName)}<AutoTag tf={tf} auto={pack.mid_auto !== false} has={pr.mid != null} onReset={() => setP({ mid_auto: true })} /></>}>
                          <input type="number" min="0" step="any" className={inputCls}
                            value={pack.mid_auto === false ? pack.mid_price : (pr.mid ?? '')}
                            onChange={e => setP({ mid_price: e.target.value, mid_auto: false })} />
                        </Field>
                      )}
                      <Field label={<>{packName(tf, 'packStruct.price', '{name} narxi', baseUnit)}<AutoTag tf={tf} auto={pack.unit_auto !== false} has={pr.unit != null} onReset={() => setP({ unit_auto: true })} /></>}
                        hint={tf('pharmacyModal.autoHint', "Avtomatik hisoblanadi, kerak bo'lsa o'zgartiring")}>
                        <input type="number" min="0" step="any" className={inputCls}
                          value={pack.unit_auto === false ? pack.unit_price : (pr.unit ?? '')}
                          onChange={e => setP({ unit_price: e.target.value, unit_auto: false })} />
                      </Field>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Field label={packName(tf, 'pharmacyModal.costPer', '1 {name} tan narxi (ixtiyoriy)', L.top === 'mid' ? midName : bigName)}
                      hint={tf('pharmacyModal.costHint', "Saqlashda donaga bo'linadi")}>
                      <input type="text" inputMode="decimal" className={inputCls} value={form.cost}
                        onChange={e => setF({ cost: e.target.value.replace(/[^0-9.]/g, '') })} />
                    </Field>
                    {L.bigQty > 0 && (
                      <Field label={packName(tf, 'pharmacyModal.packBarcode', '{name} shtrix-kodi (ixtiyoriy)', bigName)}>
                        <input className={`${inputCls} font-mono`} value={pack.big_barcode} maxLength={100} onChange={e => setP({ big_barcode: e.target.value })} />
                      </Field>
                    )}
                    {form.hasMid && L.midQty > 0 && (
                      <Field label={packName(tf, 'pharmacyModal.packBarcode', '{name} shtrix-kodi (ixtiyoriy)', midName)}>
                        <input className={`${inputCls} font-mono`} value={pack.mid_barcode} maxLength={100} onChange={e => setP({ mid_barcode: e.target.value })} />
                      </Field>
                    )}
                  </div>

                </>
              )}

              {overMax && (
                <p className="text-xs font-semibold text-red-600">{tf('pharmaProduct.maxPriceWarn', 'Chakana narx maksimal chakana narxdan yuqori')}</p>
              )}
              {line && (
                <div className="px-4 py-3 bg-emerald-600 text-white rounded-xl text-sm font-bold break-words">{line}</div>
              )}
            </Section>

            {/* 3. Boshlang'ich qoldiq */}
            <Section n={3} title={tf('pharmacyModal.s3', "Boshlang'ich qoldiq (ixtiyoriy)")}
              hint={isEdit ? tf('pharmacyModal.stockEditHint', "Qoldiq kirim (xarid) orqali o'zgartiriladi") : tf('pharmacyModal.s3Hint', 'Hozir omborda bor dori miqdori. Bo\'sh qoldirsangiz — keyin kirim qilasiz')}>
              {!isEdit && (
                <>
                  {warehouses.length > 0 && (
                    <Field label={tf('pharmacyModal.warehouse', 'Ombor')}>
                      <select className={inputCls} value={whId} onChange={e => setWhId(e.target.value)}>
                        <option value="">—</option>
                        {warehouses.filter(w => w.is_active !== false).map(w => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
                      </select>
                    </Field>
                  )}
                  <PackStockFields pack={eff} onChange={(next) => setPack(p => ({ ...p, stock_big: next.stock_big, stock_mid: next.stock_mid, stock_unit: next.stock_unit, lot: next.lot, expiry: next.expiry, mfg: next.mfg }))}
                    unitName={baseUnit} tf={tf} error={!!error} />
                </>
              )}
            </Section>

            {/* 4. Qo'shimcha (yig'ilgan) */}
            <div className="bg-white border border-slate-200 rounded-2xl">
              <button type="button" onClick={() => setShowMore(v => !v)}
                className="w-full flex items-center justify-between px-4 md:px-5 py-4 text-left">
                <span className="text-base md:text-lg font-black text-slate-800"><span className="text-emerald-600">4.</span> {tf('pharmacyModal.details', 'Batafsil')}
                  <span className="ml-2 text-xs font-normal text-slate-500">{tf('pharmacyModal.detailsHint', "ishlab chiqaruvchi, ATX, MXIK va boshqalar")}</span>
                </span>
                <span className="text-slate-400 text-xl">{showMore ? '−' : '+'}</span>
              </button>
              {showMore && (
                <div className="px-4 md:px-5 pb-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field label={tf('pharmaProduct.mxik', 'MXIK kodi')} required hint={tf('pharmaProduct.mxikHint', 'Dorixona rejimida MXIK kodi majburiy')}>
                    <input type="text" inputMode="numeric" value={form.mxik} onChange={e => setF({ mxik: e.target.value.replace(/[^0-9]/g, '') })}
                      className={`${inputCls} ${error && !form.mxik.trim() ? errCls : ''}`} />
                  </Field>
                  <Field label={tf('pharmaProduct.manufacturer', 'Ishlab chiqaruvchi')}>
                    <input className={inputCls} value={pharma.manufacturer} maxLength={200} onChange={e => setPharma(p => ({ ...p, manufacturer: e.target.value }))} />
                  </Field>
                  <Field label={tf('pharmaProduct.country', 'Ishlab chiqarilgan mamlakat')}>
                    <input className={inputCls} value={pharma.country} maxLength={100} onChange={e => setPharma(p => ({ ...p, country: e.target.value }))} />
                  </Field>
                  <Field label={tf('pharmaProduct.regNumber', "Ro'yxat raqami")}>
                    <input className={inputCls} value={pharma.reg_number} maxLength={100} onChange={e => setPharma(p => ({ ...p, reg_number: e.target.value }))} />
                  </Field>
                  <Field label={tf('pharmaProduct.regValidUntil', "Ro'yxat amal qilish muddati")}>
                    <input type="date" className={inputCls} value={pharma.reg_valid_until} onChange={e => setPharma(p => ({ ...p, reg_valid_until: e.target.value }))} />
                  </Field>
                  <Field label={tf('pharmaProduct.atc', 'ATX kodi')} hint={tf('pharmacyModal.atcHint', "JSST xalqaro tasnif kodi, yo'riqnomada yoziladi")}>
                    <input className={inputCls} value={pharma.atc_code} maxLength={20} placeholder={tf('pharmacyModal.atcPlaceholder', 'masalan N02BE01')}
                      onChange={e => setPharma(p => ({ ...p, atc_code: e.target.value }))} />
                  </Field>
                  <Field label={tf('pharmaProduct.storage', 'Saqlash sharti')}>
                    <select className={inputCls} value={pharma.storage} onChange={e => setPharma(p => ({ ...p, storage: e.target.value }))}>
                      <option value="">—</option>
                      {STORAGE_TYPES.map(([k, label]) => <option key={k} value={k}>{tf(`pharmaProduct.storageType.${k}`, label)}</option>)}
                    </select>
                  </Field>
                  <Field label={tf('pharmaProduct.controlClass', 'Nazorat toifasi')}>
                    <select className={inputCls} value={pharma.control_class} onChange={e => setPharma(p => ({ ...p, control_class: e.target.value }))}>
                      {CONTROL_CLASSES.map(([k, label]) => <option key={k} value={k}>{tf(`pharmaProduct.control.${k}`, label)}</option>)}
                    </select>
                  </Field>
                  <Field label={tf('pharmaProduct.maxRetailPrice', 'Maksimal chakana narx')} hint={tf('pharmacyModal.maxRetailHint', '1 dona uchun')}>
                    <input type="number" min="0" step="any" className={`${inputCls} ${overMax ? errCls : ''}`} value={pharma.max_retail_price}
                      onChange={e => setPharma(p => ({ ...p, max_retail_price: e.target.value }))} />
                  </Field>
                  <label className="flex items-center gap-3 cursor-pointer select-none self-end pb-3">
                    <input type="checkbox" checked={!!form.requires_marking} onChange={e => setF({ requires_marking: e.target.checked })}
                      className="w-5 h-5 text-emerald-600 rounded border-slate-300 cursor-pointer" />
                    <span className="text-base font-bold text-slate-700">{tf('pharmacyModal.requiresMarking', 'Markirovka talab qilinadi')}</span>
                  </label>
                </div>
              )}
            </div>
          </div>

          <div className="flex gap-3 px-4 md:px-6 py-4 border-t border-slate-200 bg-white rounded-b-2xl shrink-0">
            <button type="button" onClick={onClose} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-semibold hover:bg-slate-50">
              {tf('pharmacyModal.cancel', 'Bekor qilish')}
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 px-5 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-base">
              {saving ? tf('pharmacyModal.saving', 'Saqlanmoqda...') : (isEdit ? tf('pharmacyModal.save', 'Saqlash') : tf('pharmacyModal.add', "Dorini qo'shish"))}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
