import { useState, useEffect, useRef } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';
import { useLang } from '../context/LangContext';
import useCompanyFeatures from '../hooks/useCompanyFeatures';
import TasnifSearch, { lookupDrugByBarcode } from './TasnifSearch';

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
export const genBarcodeByFormat = (fmtVal) => {
  const f = BARCODE_FORMATS.find(x => x.value === fmtVal) || BARCODE_FORMATS[0];
  if (!f.len) return genBarcode();
  const min = Math.pow(10, f.len - 1);
  return String(Math.floor(min + Math.random() * (9 * Math.pow(10, f.len - 1))));
};
export const genSku = () => 'SKU-' + Math.random().toString(36).substring(2, 8).toUpperCase();
const fmtNum = (v) => { const n = Number(v); return isNaN(n) ? '0' : n.toLocaleString('ru-RU'); };

// P.5: ixcham maydonlar — keng oynada uch ustun pastga surmasdan sig'adi
const inputCls = "w-full px-3 py-2 border border-slate-200 rounded-lg text-[15px] focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent bg-white";
const errCls = "border-red-400 ring-1 ring-red-400";

function Field({ label, required, hint, children }) {
  return (
    <div className="min-w-0">
      <label className="block text-sm font-bold text-slate-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-400 mt-0.5">{hint}</p>}
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
  if (stockTotal > 0) {   // P.5: seriya ixtiyoriy, yaroqlilik muddati majburiy
    if (!p.expiry) return tf('packStruct.errExpiry', "Boshlang'ich qoldiq uchun yaroqlilik muddatini kiriting");
    if (p.mfg && p.mfg >= p.expiry) return tf('drugForm.batchMfgBeforeExpiry', "Ishlab chiqarilgan sana yaroqlilik muddatidan oldin bo'lishi kerak");
    if (p.expiry <= new Date().toISOString().slice(0, 10)) return tf('packStruct.errExpiryPast', "Yaroqlilik muddati bugundan keyin bo'lishi kerak");
  }
  return '';
};

const packName = (tf, key, fallback, name) => tf(key, fallback).replace('{name}', name);

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

// Bo'lim: komponent TASHQARISIDA (aks holda har renderda qayta yaratilib, kiritish fokusi yo'qoladi)
const Section = ({ n, title, hint, children }) => (
  <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3">
    <div>
      <h4 className="text-base md:text-lg font-black text-slate-800"><span className="text-emerald-600">{n}.</span> {title}</h4>
      {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
    </div>
    {children}
  </div>
);


// ── Oyna holati ───────────────────────────────────────────────────────────────────────────────
// P.6: "Ko'p mahsulot qo'shish" yashil qatoridagidek: bigPrice — 1 quti narxi, blisters — qutidagi blister soni
// (bo'sh — blistersiz), pieces — blisterdagi (blister bo'lmasa — qutidagi) dona soni, stockBoxes — quti soni (qoldiq).
// Ikkala son bo'sh — qadoqsiz dori: narx va qoldiq 1 dona bo'yicha. cost — 1 quti (qadoqsizda 1 dona) tan narxi.
export const pharmacyFormFromProduct = (product, round) => {
  const base = {
    name: '', barcode: '', category_id: '', requires_marking: false, mxik: '',
    bigPrice: '', blisters: '', pieces: '', cost: '', stockBoxes: '',
  };
  // P.5: yangi dorida shtrix-kod bo'sh (qutini skanerlash uchun); bo'sh qolsa saqlashda avtomatik yaratiladi
  if (!product) return { form: { ...base }, pack: { ...emptyPack }, pharma: pharmaToForm(null) };
  const r = packRestore(product, round);
  const form = {
    ...base,
    name: product.name || '', barcode: product.barcode || '', category_id: product.category_id ? String(product.category_id) : '',
    requires_marking: !!product.requires_marking, mxik: product.mxik_code || '',
  };
  const costUnit = Number(product.cost_price) || 0;
  const units = Array.isArray(product.units) ? product.units : [];
  if (r.pack.unsupported || units.length === 0) {
    form.bigPrice = product.sale_price != null ? String(Number(product.sale_price)) : '';
    form.cost = costUnit ? String(costUnit) : '';
  } else {
    const two = units.length === 2;
    form.blisters = two ? r.pack.big_qty : '';
    form.pieces = two ? r.pack.mid_qty : r.pack.big_qty;
    form.bigPrice = r.topPrice;
    form.cost = costUnit ? String(round4(costUnit * r.topRatio)) : '';
  }
  return { form, pack: r.pack, pharma: pharmaToForm(product.pharma) };
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
  const [showTasnif, setShowTasnif] = useState(false);
  const [bcInfo, setBcInfo] = useState(null);   // P.5: shtrix-kod holati { status, text }
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const bodyRef = useRef(null);
  const bcTimer = useRef(null);
  const lookupSeq = useRef(0);

  // P.5: tahrirlashda partiyalar (seriya, yaroqlilik muddati, ishlab chiqarilgan sana) — shu oynada to'g'rilanadi
  const [batches, setBatches] = useState([]);
  const [batchNote, setBatchNote] = useState('');

  useEffect(() => {
    api.get('/categories/all').then(r => setCategories(Array.isArray(r.data) ? r.data : [])).catch(() => {});
    if (isEdit) {
      api.get('/pharmacy/batches', { params: { product_id: product.id, limit: 200 }, _suppressToast: true })
        .then(({ data }) => setBatches((Array.isArray(data) ? data : []).map(b => {
          const v = { lot_number: b.lot_number || '', expiry_date: b.expiry_date || '', manufacture_date: b.manufacture_date || '' };
          return { ...b, ...v, _orig: v };
        })))
        .catch(e => setBatchNote(e.response?.status === 403
          ? tf('drugForm.batchesNoAccess', "Partiyalarni ko'rishga ruxsat yo'q")
          : tf('drugForm.batchesLoadError', "Partiyalarni yuklab bo'lmadi")));
    }
    return () => clearTimeout(bcTimer.current);
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const setB = (id, patch) => setBatches(bs => bs.map(b => (b.batch_id === id ? { ...b, ...patch } : b)));
  const dirtyBatches = batches.filter(b => ['lot_number', 'expiry_date', 'manufacture_date'].some(k => b[k] !== b._orig[k]));

  const setF = (patch) => setForm(f => ({ ...f, ...patch }));
  const setP = (patch) => setPack(p => ({ ...p, ...patch }));
  // P.6: blister soni berilsa quti -> blister -> dona, aks holda quti -> dona; ikkalasi bo'sh — qadoqsiz (1 dona)
  const hasA = String(form.blisters ?? '').trim() !== '';
  const hasB = String(form.pieces ?? '').trim() !== '';
  const single = pack.unsupported || (!hasA && !hasB);
  const incomplete = !single && hasA && !hasB;
  const eff = {
    ...pack, mid_auto: true, unit_auto: true,
    big_qty: single || incomplete ? '' : (hasA ? form.blisters : form.pieces),
    mid_qty: single || incomplete || !hasA ? '' : form.pieces,
  };
  const L = packLevels(eff);
  const topPrice = single ? '' : form.bigPrice;
  const pr = single ? { mid: null, unit: numOrNull(form.bigPrice) } : packPrices(eff, topPrice, round);
  const topRatio = single || !L.top ? 1 : L.topRatio;
  const stockTotal = isEdit ? 0 : (Number(form.stockBoxes) || 0) * topRatio;
  const bigName = String(pack.big_name || '').trim() || tf('packStruct.bigDefault', 'katta qadoq');
  const line = single ? '' : packLine(eff, topPrice, round, baseUnit);
  const maxRetail = pharma.max_retail_price;
  const overMax = maxRetail !== '' && pr.unit != null && Number(pr.unit) > Number(maxRetail);

  // P.5: tasnif/katalogdan topilgan dori. explicit — foydalanuvchi ro'yxatdan tanladi (nom va MXIK almashtiriladi),
  // aks holda (shtrix-kod skanerlandi) faqat bo'sh maydonlar to'ldiriladi
  const applyDrug = (d, explicit) => {
    setForm(f => ({
      ...f,
      name: explicit || !f.name.trim() ? (d.name || f.name) : f.name,
      mxik: explicit || !f.mxik.trim() ? (d.mxik_code || f.mxik) : f.mxik,
      barcode: f.barcode.trim() ? f.barcode : (d.barcode || ''),
    }));
    setPharma(p => ({
      ...p,
      atc_code: p.atc_code || d.atc_code || '',
      manufacturer: p.manufacturer || d.manufacturer || '',
      dosage_form: p.dosage_form || d.dosage_form || '',
      strength: p.strength || d.strength || '',
      substances: (p.substances || []).length ? p.substances : (d.substances || []),
    }));
  };

  // Shtrix-kod: bazada bormi? Yo'q bo'lsa — katalog/tasnifdan nom va MXIK
  const checkBarcode = async (raw) => {
    const code = String(raw || '').trim();
    if (code.length < 8 || (isEdit && code === String(product.barcode || ''))) return;
    const seq = ++lookupSeq.current;
    setBcInfo({ status: 'checking' });
    try {
      const { data } = await api.get(`/products/barcode/${encodeURIComponent(code)}`, { _suppressToast: true });
      if (seq !== lookupSeq.current) return;
      if (data && (!isEdit || data.id !== product.id)) { setBcInfo({ status: 'exists', text: data.name }); return; }
    } catch { /* bazada yo'q — yangi dori */ }
    const res = await lookupDrugByBarcode(code);
    if (seq !== lookupSeq.current) return;
    if (res.status === 'found') {
      applyDrug(res.drug, false);
      setBcInfo({ status: 'found', text: res.drug.name });
    } else if (res.status === 'notfound') {
      setBcInfo({ status: 'notfound' });
      setShowTasnif(true);
    } else {
      setBcInfo({ status: 'error', text: res.message });
    }
  };

  const onBarcodeInput = (value) => {
    setF({ barcode: value });
    setBcInfo(null);
    clearTimeout(bcTimer.current);
    if (value.trim().length >= 8) bcTimer.current = setTimeout(() => checkBarcode(value), 500);
  };

  const fail = (msg, openMore = false) => {
    setError(msg);
    if (openMore) setShowMore(true);
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return fail(tf('pharmacyModal.errName', 'Dori nomini kiriting'));
    if (!form.mxik.trim()) return fail(tf('pharmaProduct.mxikRequired', 'Dorixona rejimida MXIK kodi majburiy'));
    if (!(Number(form.bigPrice) > 0)) {
      return fail(single ? tf('pharmacyModal.errUnitPrice', 'Dona narxini kiriting')
        : packName(tf, 'pharmacyModal.errBigPrice', '1 {name} narxini kiriting', bigName));
    }
    if (incomplete || (!single && !L.top)) return fail(tf('pharmacyModal.errCounts', "Qadoqdagi sonlarni kiriting (1 dan katta butun son)"));
    if (pr.unit == null) return fail(tf('pharmacyModal.errUnitPrice', 'Dona narxini kiriting'));
    const barcode = form.barcode.trim() || genBarcodeByFormat('ean13');
    const pErr = validatePack(eff, { tf, unitName: baseUnit, otherBarcodes: [barcode], stockTotal });
    if (pErr) return fail(pErr);
    for (const b of dirtyBatches) {
      if (!b.expiry_date) return fail(tf('drugForm.batchExpiryRequired', 'Partiyaning yaroqlilik muddatini kiriting'));
      if (b.manufacture_date && b.manufacture_date >= b.expiry_date) {
        return fail(tf('drugForm.batchMfgBeforeExpiry', "Ishlab chiqarilgan sana yaroqlilik muddatidan oldin bo'lishi kerak"));
      }
    }

    const payload = {
      name: form.name.trim(),
      barcode,
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
        payload.initial_expiry_date = pack.expiry;
        if (pack.lot.trim()) payload.initial_lot_number = pack.lot.trim();   // P.5: seriya ixtiyoriy
        if (pack.mfg) payload.initial_manufacture_date = pack.mfg;           // P.5: ixtiyoriy
      }
    }

    setSaving(true); setError('');
    try {
      const res = isEdit ? await api.put(`/products/${product.id}`, payload) : await api.post('/products', payload);
      // P.5: o'zgargan partiyalar (faqat o'zgargan maydonlar yuboriladi)
      for (const b of dirtyBatches) {
        const body = {};
        if (b.lot_number !== b._orig.lot_number) body.lot_number = b.lot_number;
        if (b.expiry_date !== b._orig.expiry_date) body.expiry_date = b.expiry_date;
        if (b.manufacture_date !== b._orig.manufacture_date) body.manufacture_date = b.manufacture_date || null;
        await api.put(`/pharmacy/batches/${b.batch_id}`, body, { _suppressToast: true });
      }
      toast.success(isEdit ? tf('pharmacyModal.updated', 'Dori yangilandi') : tf('pharmacyModal.created', "Dori qo'shildi"));
      onSaved?.(res.data);
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      fail(Array.isArray(detail) ? detail.map(d => d.msg).join(' | ') : String(detail || err.message || tf('pharmacyModal.saveError', 'Xatolik yuz berdi')));
    } finally { setSaving(false); }
  };

  const BC_STYLE = {
    checking: 'text-slate-500', exists: 'text-red-600', found: 'text-emerald-700', picked: 'text-emerald-700',
    notfound: 'text-amber-700', error: 'text-red-600',
  };
  const bcText = !bcInfo ? '' : ({
    checking: tf('drugForm.bcChecking', 'Tekshirilmoqda...'),
    exists: `${tf('drugForm.bcExists', 'Bu shtrix-kod bazada bor')}: ${bcInfo.text || ''}`,
    found: `✓ ${tf('drugForm.bcFound', "Topildi — nomi va MXIK to'ldirildi")}`,
    picked: `✓ ${tf('drugForm.bcPicked', "Tasnifdan tanlandi — nomi va MXIK to'ldirildi")}`,
    notfound: tf('drugForm.bcNotFound', "Bu shtrix-kod tasnifda yo'q — dori nomi bo'yicha toping"),
    error: `${tf('drugForm.bcError', "Tasnif bilan bog'lanib bo'lmadi")} ${bcInfo.text || ''}`,
  })[bcInfo.status];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-3 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-slate-50 rounded-2xl shadow-2xl w-full max-w-[1500px] h-[96vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 md:px-6 py-3 border-b border-slate-200 bg-white rounded-t-2xl shrink-0">
          <h3 className="text-lg md:text-xl font-bold text-slate-800">
            {isEdit ? tf('pharmacyModal.titleEdit', 'Dorini tahrirlash') : tf('pharmacyModal.titleAdd', "Dori qo'shish")}
          </h3>
          <button type="button" onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400" aria-label="close">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <form onSubmit={handleSave} className="flex flex-col min-h-0 flex-1">
          <div ref={bodyRef} className="overflow-y-auto flex-1 p-3 md:p-4">
            {error && (
              <div className="mb-3 px-4 py-2.5 bg-red-50 border border-red-200 text-red-700 text-sm font-semibold rounded-xl">{error}</div>
            )}

            {/* P.5: keng oyna — uch ustun: 1. Asosiy | 2. Qadoq va narx | 3. Qoldiq + Batafsil */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
              {/* 1. Asosiy */}
              <Section n={1} title={tf('pharmacyModal.s1', 'Asosiy')}>
                <Field label={tf('pharmacyModal.barcode', 'Shtrix-kod')}
                  hint={tf('drugForm.barcodeHint', "Qutini skanerlang — nomi va MXIK o'zi to'ladi. Bo'sh qolsa avtomatik yaratiladi")}>
                  <div className="flex gap-2">
                    <input className={`${inputCls} font-mono`} value={form.barcode} autoFocus={!isEdit}
                      onChange={e => onBarcodeInput(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); clearTimeout(bcTimer.current); checkBarcode(form.barcode); } }} />
                    <button type="button" onClick={() => { setF({ barcode: genBarcodeByFormat('ean13') }); setBcInfo(null); }}
                      className="px-3 rounded-lg bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-sm font-bold whitespace-nowrap">
                      {tf('pharmacyModal.generate', 'Yaratish')}
                    </button>
                  </div>
                  {bcText && <p className={`text-xs font-semibold mt-1 ${BC_STYLE[bcInfo.status]}`}>{bcText}</p>}
                </Field>
                <Field label={tf('pharmacyModal.name', 'Dori nomi')} required>
                  <input className={`${inputCls} ${error && !form.name.trim() ? errCls : ''}`} value={form.name} maxLength={255}
                    placeholder={tf('pharmacyModal.nameHint', 'Masalan: Paratsetamol 500 mg')}
                    onChange={e => setF({ name: e.target.value })} />
                </Field>
                <Field label={tf('pharmaProduct.mxik', 'MXIK kodi')} required>
                  <div className="flex gap-2">
                    <input type="text" inputMode="numeric" value={form.mxik} onChange={e => setF({ mxik: e.target.value.replace(/[^0-9]/g, '') })}
                      className={`${inputCls} font-mono ${error && !form.mxik.trim() ? errCls : ''}`} />
                    <button type="button" onClick={() => setShowTasnif(v => !v)}
                      className="px-3 rounded-lg bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-700 text-sm font-bold whitespace-nowrap">
                      {tf('drugForm.findTasnif', 'Tasnifdan topish')}
                    </button>
                  </div>
                </Field>
                {showTasnif && (
                  <TasnifSearch initialQuery={form.name} tf={tf} onClose={() => setShowTasnif(false)}
                    onPick={(d) => { applyDrug(d, true); setShowTasnif(false); setBcInfo({ status: 'picked' }); }} />
                )}
                <Field label={tf('pharmaProduct.substances', "Ta'sir etuvchi moddalar")}>
                  <SubstancePicker value={pharma.substances} onChange={(subs) => setPharma(p => ({ ...p, substances: subs }))} tf={tf} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={tf('pharmaProduct.dosageForm', 'Dori shakli')}>
                    <select className={inputCls} value={pharma.dosage_form} onChange={e => setPharma(p => ({ ...p, dosage_form: e.target.value }))}>
                      <option value="">—</option>
                      {DOSAGE_FORMS.map(([k, label]) => <option key={k} value={k}>{tf(`pharmaProduct.form.${k}`, label)}</option>)}
                    </select>
                  </Field>
                  <Field label={tf('pharmaProduct.strength', 'Doza')}>
                    <input className={inputCls} value={pharma.strength} maxLength={100} placeholder="500 mg" onChange={e => setPharma(p => ({ ...p, strength: e.target.value }))} />
                  </Field>
                  <Field label={tf('pharmacyModal.category', 'Kategoriya (ixtiyoriy)')}>
                    <select className={inputCls} value={form.category_id} onChange={e => setF({ category_id: e.target.value })}>
                      <option value="">—</option>
                      {categories.map(c => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
                    </select>
                  </Field>
                  <label className="flex items-center gap-2 cursor-pointer select-none self-end pb-2">
                    <input type="checkbox" checked={!!pharma.is_rx} onChange={e => setPharma(p => ({ ...p, is_rx: e.target.checked }))}
                      className="w-5 h-5 text-emerald-600 rounded border-slate-300 cursor-pointer" />
                    <span className="text-sm font-bold text-slate-700">{tf('pharmaProduct.isRx', 'Retseptli dori')}</span>
                  </label>
                </div>
              </Section>

              {/* 2. Qadoq, narx va qoldiq — "Ko'p mahsulot qo'shish" yashil qatoridagi tartibda (P.6) */}
              <Section n={2} title={tf('drugForm.packTitle', 'Qadoq, narx va qoldiq')}
                hint={tf('drugForm.packHint', "1 quti narxini kiriting — blister va dona narxi, jami qoldiq o'zi hisoblanadi. Qadoqsiz dori uchun sonlarni bo'sh qoldiring")}>
                {pack.unsupported && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800">
                    {tf('packStruct.unsupported', "Bu mahsulotning qadoq tuzilmasi murakkab (2 tadan ko'p birlik): shu oynada o'zgartirilmaydi va saqlanganda tegilmaydi.")}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3 bg-emerald-50/60 border border-emerald-200 rounded-xl p-3">
                  <Field label={single ? tf('drugForm.unitPrice', '1 dona narxi') : packName(tf, 'pharmacyModal.bigPrice', '1 {name} narxi', bigName)} required>
                    <input type="text" inputMode="decimal" className={`${inputCls} ${error && !(Number(form.bigPrice) > 0) ? errCls : ''}`} value={form.bigPrice}
                      placeholder="100000" onChange={e => setF({ bigPrice: e.target.value.replace(/[^0-9.]/g, '') })} />
                  </Field>
                  {!pack.unsupported && (
                    <Field label={tf('packStruct.bulkMidCount', 'Qutidagi blister soni')}>
                      <input type="text" inputMode="numeric" className={inputCls} value={form.blisters} placeholder="5"
                        onChange={e => setF({ blisters: e.target.value.replace(/[^0-9]/g, '') })} />
                    </Field>
                  )}
                  {!pack.unsupported && (
                    <Field label={hasA ? tf('packStruct.bulkUnitCount', 'Blisterdagi dona soni') : tf('drugForm.piecesInBox', 'Qutidagi dona soni')}
                      required={hasA}>
                      <input type="text" inputMode="numeric" className={`${inputCls} ${error && incomplete ? errCls : ''}`} value={form.pieces} placeholder="10"
                        onChange={e => setF({ pieces: e.target.value.replace(/[^0-9]/g, '') })} />
                    </Field>
                  )}
                  {!isEdit && (
                    <Field label={single ? tf('drugForm.stockUnits', 'Qoldiq (dona soni)') : tf('packStruct.bulkStockBig', 'Quti soni (qoldiq)')}>
                      <input type="text" inputMode="numeric" className={inputCls} value={form.stockBoxes} placeholder="0"
                        onChange={e => setF({ stockBoxes: e.target.value.replace(/[^0-9]/g, '') })} />
                    </Field>
                  )}
                  {!isEdit && (
                    <Field label={tf('packStruct.lot', 'Seriya raqami')}>
                      <input className={inputCls} value={pack.lot} maxLength={100} placeholder="LOT2026A" onChange={e => setP({ lot: e.target.value })} />
                    </Field>
                  )}
                  {!isEdit && (
                    <Field label={tf('packStruct.expiry', 'Yaroqlilik muddati')} required={stockTotal > 0}>
                      <input type="date" className={`${inputCls} ${error && stockTotal > 0 && !pack.expiry ? errCls : ''}`} value={pack.expiry}
                        onChange={e => setP({ expiry: e.target.value })} />
                    </Field>
                  )}
                  {!isEdit && (
                    <Field label={tf('drugForm.mfgOptional', 'Ishlab chiqarilgan sana (ixtiyoriy)')}>
                      <input type="date" className={inputCls} value={pack.mfg} onChange={e => setP({ mfg: e.target.value })} />
                    </Field>
                  )}
                  <Field label={packName(tf, 'pharmacyModal.costPer', '1 {name} tan narxi (ixtiyoriy)', single ? baseUnit : bigName)}>
                    <input type="text" inputMode="decimal" className={inputCls} value={form.cost}
                      onChange={e => setF({ cost: e.target.value.replace(/[^0-9.]/g, '') })} />
                  </Field>
                </div>

                {/* avtomatik hisob: qadoq, blister va dona narxi, jami qoldiq */}
                {(line || (single && pr.unit != null) || stockTotal > 0) && (
                  <div className="px-4 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-bold break-words">
                    {single && pr.unit != null ? `${tf('drugForm.singleLine', 'Qadoqsiz')}: 1 ${baseUnit} = ${fmtNum(pr.unit)}` : line}
                    {stockTotal > 0 && ` · ${tf('packStruct.total', 'jami')}: ${fmtNum(stockTotal)} ${baseUnit}`}
                  </div>
                )}
                {overMax && (
                  <p className="text-xs font-semibold text-red-600">{tf('pharmaProduct.maxPriceWarn', 'Chakana narx maksimal chakana narxdan yuqori')}</p>
                )}
                {!isEdit && warehouses.length > 0 && (
                  <Field label={tf('pharmacyModal.warehouse', 'Ombor')}>
                    <select className={inputCls} value={whId} onChange={e => setWhId(e.target.value)}>
                      <option value="">—</option>
                      {warehouses.filter(w => w.is_active !== false).map(w => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
                    </select>
                  </Field>
                )}
              </Section>

              {/* 3. Partiyalar (tahrirda) + Batafsil */}
              <div className="space-y-4">
                {isEdit && (
                <Section n={3} title={tf('drugForm.batchesTitle', 'Partiyalar: seriya va muddatlar')}
                  hint={tf('drugForm.batchesHint', "Qoldiq kirim orqali o'zgaradi. Seriya va sanalarni shu yerda to'g'rilang")}>
                  {/* P.5: tahrirlashda partiyalarni to'g'rilash */}
                  {isEdit && (batchNote ? (
                    <p className="text-sm text-slate-500">{batchNote}</p>
                  ) : batches.length === 0 ? (
                    <p className="text-sm text-slate-500">{tf('drugForm.noBatches', "Hozir qoldiq yo'q — kirim qilinganda partiyalar shu yerda ko'rinadi")}</p>
                  ) : (
                    <div className="space-y-2 max-h-[48vh] overflow-y-auto pr-1">
                      {batches.map(b => (
                        <div key={b.batch_id} className={`border rounded-xl p-3 space-y-2 ${dirtyBatches.includes(b) ? 'border-emerald-400 bg-emerald-50/40' : 'border-slate-200'}`}>
                          <div className="flex justify-between gap-2 text-xs font-semibold text-slate-600">
                            <span className="truncate">{b.warehouse_name || '—'}</span>
                            <span className="whitespace-nowrap">{tf('drugForm.batchQty', 'qoldiq')}: {fmtNum(b.quantity)} {baseUnit}</span>
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <Field label={tf('packStruct.lot', 'Seriya raqami')}>
                              <input className={inputCls} value={b.lot_number} maxLength={100} onChange={e => setB(b.batch_id, { lot_number: e.target.value })} />
                            </Field>
                            <Field label={tf('packStruct.expiry', 'Yaroqlilik muddati')} required>
                              <input type="date" className={`${inputCls} ${!b.expiry_date ? errCls : ''}`} value={b.expiry_date}
                                onChange={e => setB(b.batch_id, { expiry_date: e.target.value })} />
                            </Field>
                            <Field label={tf('packStruct.mfg', 'Ishlab chiqarilgan sana')}>
                              <input type="date" className={inputCls} value={b.manufacture_date}
                                onChange={e => setB(b.batch_id, { manufacture_date: e.target.value })} />
                            </Field>
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </Section>
                )}

                <div className="bg-white border border-slate-200 rounded-2xl">
                  <button type="button" onClick={() => setShowMore(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left">
                    <span className="text-base md:text-lg font-black text-slate-800"><span className="text-emerald-600">{isEdit ? 4 : 3}.</span> {tf('pharmacyModal.details', 'Batafsil')}
                      <span className="ml-2 text-xs font-normal text-slate-500">{tf('drugForm.detailsHint', "ishlab chiqaruvchi, ATX va boshqalar")}</span>
                    </span>
                    <span className="text-slate-400 text-xl">{showMore ? '−' : '+'}</span>
                  </button>
                  {showMore && (
                    <div className="px-4 pb-4 grid grid-cols-2 gap-3">
                      <Field label={tf('pharmaProduct.manufacturer', 'Ishlab chiqaruvchi')}>
                        <input className={inputCls} value={pharma.manufacturer} maxLength={200} onChange={e => setPharma(p => ({ ...p, manufacturer: e.target.value }))} />
                      </Field>
                      <Field label={tf('pharmaProduct.country', 'Ishlab chiqarilgan mamlakat')}>
                        <input className={inputCls} value={pharma.country} maxLength={100} onChange={e => setPharma(p => ({ ...p, country: e.target.value }))} />
                      </Field>
                      <Field label={tf('pharmaProduct.atc', 'ATX kodi')} hint={tf('pharmacyModal.atcHint', "JSST xalqaro tasnif kodi, yo'riqnomada yoziladi")}>
                        <input className={inputCls} value={pharma.atc_code} maxLength={20} placeholder={tf('pharmacyModal.atcPlaceholder', 'masalan N02BE01')}
                          onChange={e => setPharma(p => ({ ...p, atc_code: e.target.value }))} />
                      </Field>
                      <Field label={tf('pharmaProduct.regNumber', "Ro'yxat raqami")}>
                        <input className={inputCls} value={pharma.reg_number} maxLength={100} onChange={e => setPharma(p => ({ ...p, reg_number: e.target.value }))} />
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
                      <label className="flex items-center gap-2 cursor-pointer select-none self-end pb-2">
                        <input type="checkbox" checked={!!form.requires_marking} onChange={e => setF({ requires_marking: e.target.checked })}
                          className="w-5 h-5 text-emerald-600 rounded border-slate-300 cursor-pointer" />
                        <span className="text-sm font-bold text-slate-700">{tf('pharmacyModal.requiresMarking', 'Markirovka talab qilinadi')}</span>
                      </label>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="flex gap-3 px-4 md:px-6 py-3 border-t border-slate-200 bg-white rounded-b-2xl shrink-0">
            <button type="button" onClick={onClose} className="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-semibold hover:bg-slate-50">
              {tf('pharmacyModal.cancel', 'Bekor qilish')}
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-base">
              {saving ? tf('pharmacyModal.saving', 'Saqlanmoqda...') : (isEdit ? tf('pharmacyModal.save', 'Saqlash') : tf('pharmacyModal.add', "Dorini qo'shish"))}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
