/**
 * UlgurjiSotuv — Ulgurji (wholesale) sotuv sahifasi
 */
import { useState, useEffect, useRef, useCallback, useMemo, memo, forwardRef, useImperativeHandle } from 'react';
import api from '../../api/axios';
import { buildReceiptHtml, printReceiptHtml, getReceiptSettings, saveReceiptSettings } from '../../utils/receiptBuilder';
import { toast } from '../../utils/toast';
import { useActiveShift } from '../../hooks/useActiveShift';
import ShiftOpenModal from '../../components/ShiftOpenModal';
import ShiftCloseModal from '../../components/ShiftCloseModal';
import { matchesSearch } from '../../utils/translit';
import { GS, parseGs1Scan, gtinVariants, productMatchesGtin, createGsDetector } from '../../utils/gs1';
import ProductAddModal from '../../components/ProductAddModal';
import PartialReturnModal from './PartialReturnModal';
import { getDebtEntries, hasAnyDebt } from '../../utils/debt';
import { fiscalizeAndPrint } from '../../api/hippoLocal';
import { useLang } from '../../context/LangContext';
import { useBranch } from '../../context/BranchContext';
import SaleDeliveryBlock from '../../components/sale/SaleDeliveryBlock';
import CustomerPicker from '../../components/CustomerPicker';
import useCompanyFeatures from '../../hooks/useCompanyFeatures';
import {
  describeRejection, fmtExpiry, todayLocalIso, rxProductsOf, isControlled, validateRx, buildRxPayload, unitLinePrice, wholeBoxMax,
  parseWholeBoxError,
} from '../../utils/posQueue';
import { EMPTY_DELIVERY, deliveryFromSale, deliveryPayload } from '../../components/sale/saleDelivery';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';
import { filenameFromDisposition, blobErrorMessage } from '../../utils/downloadBlob';


const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);
const parseN = (s) => parseFloat(String(s || '').replace(/\s/g, '')) || 0;

// D2.6: dorixona savat qatorining qo'shimcha maydonlari (muddat, retsept, birliklar); faqat dorixona rejimida chaqiriladi
// D2.6: skanerda birlik o'zi tanlanadi — quti (omborda butun quti bo'lsa) -> blister -> dona (null)
const defaultScanUnit = (p) => (Array.isArray(p.units) ? p.units : [])
  .filter(u => (Number(u.ratio) || 1) > 1)
  .sort((a, b) => Number(b.ratio) - Number(a.ratio))
  .find(u => !(p.pack_ratio != null && p.full_boxes != null && Number(u.ratio) >= Number(p.pack_ratio) && Number(p.full_boxes) < 1)) || null;

const pharmaFieldsOf = (p, unit) => ({
  nearest_expiry: p.nearest_expiry || null,
  expiry_warn: !!p.expiry_warn,
  is_rx: !!p.is_rx,
  control_class: p.control_class || 'none',
  units: Array.isArray(p.units) ? p.units : [],
  pack_ratio: p.pack_ratio != null ? Number(p.pack_ratio) : null,
  full_boxes: p.full_boxes != null ? Number(p.full_boxes) : null,
  loose_units: p.loose_units != null ? Number(p.loose_units) : null,
  stock_display: p.stock_display || null,
  unit_id: unit ? unit.id : null,
  unit_name: unit ? unit.name : null,
  unit_ratio: unit ? Number(unit.ratio) || 1 : 1,
  base_unit_name: p.unit || 'dona',
});

// D2.6: birlik (quti/blister) qatorining ASOSIY birlikdagi narxi. Qator narxi qo'lda o'zgartirilmagan bo'lsa
// qo'shilganda saqlangan base_price (aks holda narx/nisbat). Birlik bo'lmasa — qator narxining o'zi.
const lineBasePrice = (it) => {
  if (!it.unit_id) return it.price;
  const un = (it.units || []).find(u => u.id === it.unit_id);
  if (un && it.base_price != null && Number(it.price) === unitLinePrice(it.base_price, it.sale_price, un)) return Number(it.base_price);
  return (Number(it.price) || 0) / (Number(it.unit_ratio) || 1);
};
// Qayta narxlashda (mijoz/narx turi) yangi ASOSIY narxni qatorga qo'llaydi: birlik qatorida narx birlik narxiga aylantiriladi
const repriceLine = (it, newBase) => {
  if (!it.unit_id) return { ...it, price: newBase };
  const un = (it.units || []).find(u => u.id === it.unit_id);
  return { ...it, price: un ? unitLinePrice(newBase, it.sale_price, un) : newBase * (Number(it.unit_ratio) || 1), base_price: newBase };
};

const fmtPrice = (v) => {
  if (v === '' || v === null || v === undefined) return '';
  let s = String(v).replace(/\s/g, '').replace(',', '.');
  if (s === '.' || s === ',') return '.';
  if (s.endsWith('.')) {
    const intPart = s.slice(0, -1);
    const formattedInt = intPart === '' ? '' : (Number(intPart) || 0).toLocaleString('ru-RU');
    return formattedInt + '.';
  }
  const n = Number(s);
  if (isNaN(n)) return s;
  const parts = s.split('.');
  const formattedInt = Number(parts[0]).toLocaleString('ru-RU');
  if (parts.length > 1) {
    return formattedInt + '.' + parts[1];
  }
  return formattedInt;
};
const parsePrice = (v) => {
  let s = String(v).replace(/\s/g, '').replace(',', '.').replace(/[^0-9.]/g, '');
  const parts = s.split('.');
  if (parts.length > 2) {
    return parts[0] + '.' + parts.slice(1).join('');
  }
  return s;
};

// Kasrli birliklar (kg, litr, metr...) — bunday tovarni "jami summa" bo'yicha sotish mumkin
const FRACTIONAL_UNITS = new Set(['kg', 'g', 'gr', 'gramm', 'litr', 'l', 'ml', 'metr', 'm', 'sm', 'm2', 'm3']);
const isFractionalUnit = (unit) => FRACTIONAL_UNITS.has(String(unit || '').trim().toLowerCase());
const round3 = (n) => Math.round(n * 1000) / 1000;

const PAY_ICONS = {
  cash: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="6" width="20" height="13" rx="2" /><circle cx="12" cy="12.5" r="2.5" /><path d="M6 9.5h.01M18 9.5h.01M6 15.5h.01M18 15.5h.01" /></svg>),
  card: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /><path d="M6 15h4" /></svg>),
  uzcard: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /><circle cx="17" cy="15" r="1.5" /><circle cx="14" cy="15" r="1.5" /></svg>),
  humo: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /><path d="M6 15h3M15 15h3" /></svg>),
  bank: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18M3 10h18M5 10V21M19 10V21M10 10V21M14 10V21M12 3L2 10h20L12 3z" /></svg>),
  click: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="7" y="2" width="10" height="20" rx="2" /><path d="M11 18h2" /></svg>),
  payme: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><rect x="7" y="2" width="10" height="20" rx="2" /><path d="M10 7h4M10 11h4M10 15h2" /></svg>),
  uzum: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z" /><path d="M8 12h8M12 8v8" /></svg>),
  debt: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" /><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></svg>),
  mixed: (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M16 3h5v5M4 20L21 3" /><path d="M21 16v5h-5" /><path d="M15 15l6 6" /><path d="M4 4l5 5" /></svg>),
};

const PAY_TYPES = [
  { id: 'cash', labelKey: 'pay.cash', accent: 'emerald' },
  { id: 'card', labelKey: 'pay.card', accent: 'blue' },
  { id: 'uzcard', labelKey: 'pay.uzcard', accent: 'blue' },
  { id: 'humo', labelKey: 'pay.humo', accent: 'violet' },
  { id: 'bank', labelKey: 'pay.bank', accent: 'cyan' },
  { id: 'click', labelKey: 'pay.click', accent: 'indigo' },
  { id: 'payme', labelKey: 'pay.payme', accent: 'sky' },
  { id: 'uzum', labelKey: 'pay.uzum', accent: 'orange' },
  { id: 'debt', labelKey: 'pay.debt', accent: 'amber' },
  { id: 'mixed', labelKey: 'pay.mixed', accent: 'purple' },
];

const ACCENT_CLS = {
  emerald: { active: 'border-emerald-500 bg-emerald-500 text-white shadow-emerald-200', idle: 'border-slate-200 text-emerald-600 hover:border-emerald-300 hover:bg-emerald-50' },
  blue: { active: 'border-blue-500 bg-blue-500 text-white shadow-blue-200', idle: 'border-slate-200 text-blue-600 hover:border-blue-300 hover:bg-blue-50' },
  violet: { active: 'border-violet-500 bg-violet-500 text-white shadow-violet-200', idle: 'border-slate-200 text-violet-600 hover:border-violet-300 hover:bg-violet-50' },
  cyan: { active: 'border-blue-500 bg-blue-500 text-white shadow-blue-200', idle: 'border-slate-200 text-blue-600 hover:border-blue-300 hover:bg-blue-50' },
  indigo: { active: 'border-blue-500 bg-blue-500 text-white shadow-blue-200', idle: 'border-slate-200 text-blue-600 hover:border-blue-300 hover:bg-blue-50' },
  sky: { active: 'border-sky-500 bg-sky-500 text-white shadow-sky-200', idle: 'border-slate-200 text-sky-600 hover:border-sky-300 hover:bg-sky-50' },
  orange: { active: 'border-orange-500 bg-orange-500 text-white shadow-orange-200', idle: 'border-slate-200 text-orange-600 hover:border-orange-300 hover:bg-orange-50' },
  amber: { active: 'border-amber-500 bg-amber-500 text-white shadow-amber-200', idle: 'border-slate-200 text-amber-600 hover:border-amber-300 hover:bg-amber-50' },
  purple: { active: 'border-blue-500 bg-blue-500 text-white shadow-blue-200', idle: 'border-slate-200 text-blue-600 hover:border-blue-300 hover:bg-blue-50' },
};

const STATUS_META = {
  completed: { lKey: 'sale.statusCompleted', c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { lKey: 'sale.statusCancelled', c: 'bg-red-100 text-red-600' },
  pending: { lKey: 'wholesale.statusPendingApproval', c: 'bg-amber-100 text-amber-700 ring-1 ring-amber-300' },
  partial_refund: { lKey: 'sale.statusPartialRefund', c: 'bg-orange-100 text-orange-700' },
};
const PAY_META_KEYS = {
  cash: 'pay.cash', card: 'pay.card', uzcard: 'pay.uzcard', humo: 'pay.humo', bank: 'pay.bank',
  click: 'pay.click', payme: 'pay.payme', visa: 'pay.visa', uzum: 'pay.uzum', debt: 'pay.debt', mixed: 'pay.mixed',
};

function Ic({ d, cls = 'w-4 h-4' }) {
  return (
    <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
    </svg>
  );
} const CustomerSearch = memo(forwardRef(function CustomerSearch({ customers, value, onChange, onNew, onFetch, onCustomerSelected }, fwdRef) {
  const { t } = useLang();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', debt_limit: '' });
  const [activeIdx, setActiveIdx] = useState(0);
  const [saving, setSaving] = useState(false);
  const ref = useRef(null);
  const inputRef = useRef(null);

  useImperativeHandle(fwdRef, () => ({
    openForm: () => { setShowForm(true); setOpen(false); },
    focus: () => inputRef.current?.focus(),
  }));

  const selected = useMemo(() => customers.find(c => String(c.id) === String(value)), [customers, value]);
  const filtered = useMemo(() => (q.trim()
    ? customers.filter(c => matchesSearch(c.name, q) || (c.phone || '').includes(q))
    : customers
  ).slice(0, 30), [customers, q]);

  // Tashqariga bosilganda yopish
  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) { setOpen(false); } };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  // Mijoz qidiruvi (debounced)
  useEffect(() => {
    if (q.trim().length >= 2) {
      const timer = setTimeout(async () => {
        try {
          const res = await api.get('/customers/', { params: { search: q.trim(), limit: 30 } });
          const items = Array.isArray(res.data) ? res.data : (res.data?.items || []);
          if (items.length > 0 && onFetch) onFetch(items);
        } catch (err) { console.error('Fetch customers error:', err); }
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [q, onFetch]);

  const saveNew = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error(t('wholesale.enterName'));
    setSaving(true);
    try {
      const res = await api.post('/customers', {
        name: form.name.trim(),
        phone: form.phone.trim() || undefined,
        debt_limit: form.debt_limit ? Number(form.debt_limit) : 0,
      });
      toast.success(t('wholesale.customerAdded'));
      onNew?.(res.data);
      onChange(String(res.data.id));
      setShowForm(false);
      setForm({ name: '', phone: '', debt_limit: '' });
      setOpen(false);
      onCustomerSelected?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('common.error'));
    } finally { setSaving(false); }
  };

  const handleKey = (e) => {
    if (!open || !filtered.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx(i => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = filtered[activeIdx];
      if (item) {
        onChange(String(item.id));
        setQ('');
        setOpen(false);
        onCustomerSelected?.();
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const selectCustomer = useCallback((c) => {
    onChange(String(c.id));
    setQ('');
    setOpen(false);
    onCustomerSelected?.();
  }, [onChange, onCustomerSelected]);

  return (
    <div ref={ref} className="relative">
      <div className={`flex items-center gap-2 border rounded-lg px-2.5 py-1.5 bg-white transition-all ${open ? 'border-blue-500 ring-2 ring-blue-100' : 'border-slate-200 hover:border-slate-300'}`}>
        <Ic d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" cls="w-4 h-4 text-slate-400 shrink-0" />
        <input
          ref={inputRef}
          value={open ? q : (selected ? `${selected.name}${selected.phone ? ' · ' + selected.phone : ''}` : '')}
          onChange={e => { setQ(e.target.value); setOpen(true); setActiveIdx(0); if (!e.target.value) onChange(''); }}
          onKeyDown={handleKey}
          onFocus={() => { setOpen(true); setActiveIdx(0); }}
          onBlur={() => { /* relying on mousedown handler */ }}
          placeholder={t('wholesale.selectOrSearchCustomer')}
          className="flex-1 text-xs md:text-sm font-semibold text-slate-800 outline-none bg-transparent placeholder:font-normal placeholder:text-slate-400"
        />
        {selected && <button onMouseDown={() => { onChange(''); setQ(''); }} className="text-slate-300 hover:text-red-400"><Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" /></button>}
      </div>

      {selected && !open && (
        <div className="mt-1 px-2.5 py-1 bg-blue-50/70 border border-blue-100 rounded-lg flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 min-w-0">
            <div className="w-5 h-5 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-[10px] font-black shrink-0">{selected.name?.[0]?.toUpperCase()}</div>
            <span className="font-bold text-blue-900 truncate">{selected.name}</span>
            {selected.phone && <span className="text-[11px] text-blue-600 shrink-0">· {selected.phone}</span>}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {hasAnyDebt(selected) ? (
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-slate-400 font-bold uppercase">{t('customer.debtBalance')}:</span>
                <div className="flex items-center gap-1">
                  {getDebtEntries(selected).map(({ currency, amount }) => (
                    <span key={currency} className="text-xs font-black text-red-600 bg-red-50 px-1 py-0.5 rounded border border-red-100">
                      {fmt(amount)} {currency === 'USD' ? '$' : currency}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100">Qarzsiz</span>
            )}
            {Number(selected.loyalty_points) > 0 && <span className="text-[10px] text-emerald-700 font-bold bg-emerald-100 px-1 py-0.5 rounded">🏆 {fmt(selected.loyalty_points)} b</span>}
          </div>
        </div>
      )}

      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-lg shadow-2xl z-50 overflow-hidden max-h-72 overflow-y-auto">
          {filtered.length === 0
            ? <div className="px-4 py-4 text-center text-sm text-slate-400">"{q}" — {t('wholesale.notFound')}</div>
            : filtered.map((c, i) => (
              <button key={c.id} onMouseDown={() => selectCustomer(c)}
                className={`w-full flex cursor-pointer items-center justify-between px-4 py-3 border-b border-slate-50 last:border-0 transition-colors ${i === activeIdx ? 'bg-blue-100' : 'hover:bg-blue-50'}`}>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold">{c.name?.[0]?.toUpperCase()}</div>
                  <div className="text-left">
                    <div className="text-sm font-bold text-slate-800">{c.name}</div>
                    <div className="text-xs text-slate-400">{c.phone || '—'}</div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {hasAnyDebt(c) && (
                    <div className="flex flex-col items-end gap-1">
                      {getDebtEntries(c).map(({ currency, amount }) => (
                        <span key={currency} className="text-xs font-black text-red-600">
                          {fmt(amount)} {currency === 'USD' ? '$' : currency}
                        </span>
                      ))}
                    </div>
                  )}
                  {Number(c.debt_limit) > 0 && <div className="text-[10px] text-slate-400 font-medium tracking-tight mt-0.5">{t('common.limit')}: {fmt(c.debt_limit)}</div>}
                </div>
              </button>
            ))
          }
          {/* + Yangi mijoz */}
          <button onMouseDown={() => { setShowForm(true); setOpen(false); }}
            className="w-full flex cursor-pointer items-center gap-2 px-4 py-3 text-blue-600 hover:bg-blue-50 font-bold text-sm border-t border-slate-100 transition-colors">
            <span className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center text-base leading-none">+</span>
            {t('wholesale.addNewCustomer')}
          </button>
        </div>
      )}

      {/* Yangi mijoz modal */}
      {showForm && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <span className="font-black text-slate-800">{t('customer.newCustomer')}</span>
              <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-red-400"><Ic d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" /></button>
            </div>
            <form onSubmit={saveNew} className="p-5 space-y-3">
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase mb-1 block">{t('common.name')} *</label>
                <input autoFocus value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder={t('wholesale.fullNamePlaceholder')}
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase mb-1 block">{t('common.phone')}</label>
                <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}
                  placeholder="+998 90 123 45 67"
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase mb-1 block">{t('wholesale.debtLimitSom')}</label>
                <input type="number" value={form.debt_limit} onChange={e => setForm({ ...form, debt_limit: e.target.value })}
                  placeholder="0"
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setShowForm(false)}
                  className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm">{t('common.cancel')}</button>
                <button type="submit" disabled={saving}
                  className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm disabled:opacity-50">
                  {saving ? t('common.saving') : t('common.add')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}));

const ProductSearch = memo(forwardRef(function ProductSearch({ onSelect, placeholder, onOpenAdd, warehouseId, disabled, customerPriceType }, fwdRef) {
  const { t } = useLang();
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const timerRef = useRef(null);
  const listRef = useRef(null);
  // D2.6: dorixona rejimida qidiruv /products/pos-list orqali (nearest_expiry, is_rx, units, stock_display)
  const searchFeatures = useCompanyFeatures();
  const searchEndpoint = searchFeatures?.pharmacy ? '/products/pos-list' : '/products';
  // true — oxirgi tanlovdan keyingi natijalar ushlab turiladi (maydon bo'sh bo'lsa ham)
  const keepResultsRef = useRef(false);

  useImperativeHandle(fwdRef, () => ({
    openForm: () => onOpenAdd?.(),
    focus: () => { inputRef.current?.focus(); }
  }));

  // q o'zgarganda qidirish
  useEffect(() => {
    if (!q.trim()) { if (!keepResultsRef.current) setResults([]); return; }
    clearTimeout(timerRef.current);
    const abortCtrl = new AbortController();
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.get(searchEndpoint, {
          params: { search: q.trim(), limit: 50, warehouse_id: warehouseId || undefined },
          signal: abortCtrl.signal,
          _silent: true,
        });
        if (abortCtrl.signal.aborted) return;
        const items = Array.isArray(res.data) ? res.data : (res.data?.items || []);
        // Aqlli tartiblash: qidirilgan so'z bilan boshlangan mahsulotlar tepaga
        const sq = q.trim().toLowerCase();
        const scored = items.map(p => {
          const n = (p.name || '').toLowerCase();
          let score = 0;
          if (n === sq) score = 4;                                    // to'liq mos
          else if (n.startsWith(sq + ' ') || n.startsWith(sq + '-') || n === sq) score = 3; // boshidan mos
          else if (new RegExp('(?:^|[\\s\\-])' + sq.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(n)) score = 2; // so'z boshidan
          else score = 1;                                              // ichida uchraydi
          return { ...p, _score: score };
        });
        scored.sort((a, b) => b._score - a._score || (a.name || '').localeCompare(b.name || ''));
        setResults(scored.slice(0, 20));
      } catch (err) {
        if (err?.code !== 'ERR_CANCELED') setResults([]);
      } finally {
        if (!abortCtrl.signal.aborted) setLoading(false);
      }
    }, 280);
    return () => { clearTimeout(timerRef.current); abortCtrl.abort(); };
  }, [q, warehouseId, searchEndpoint]);

  // Tanlangandan keyin qidiruv maydoni tozalanadi, lekin natijalar ro'yxati saqlanadi — bir xil
  // turdagi keyingi mahsulotni (masalan, boshqa rangini) qayta yozmasdan tanlash uchun.
  const select = useCallback((p, idx) => {
    onSelect(p);
    keepResultsRef.current = true;
    setQ('');
    setActiveIdx(idx ?? 0);
    setOpen(false);
  }, [onSelect]);
  const clearSearch = () => { keepResultsRef.current = false; setQ(''); setResults([]); setActiveIdx(0); };

  // Ro'yxat ochilganda belgilangan (oxirgi tanlangan) mahsulot ko'rinib tursin
  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector(`[data-idx="${activeIdx}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [open, activeIdx, results]);

  const handleKey = (e) => {
    if (!results.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, results.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
    if (e.key === 'Enter' && results[activeIdx]) { e.preventDefault(); select(results[activeIdx], activeIdx); }
    if (e.key === 'Escape') { clearSearch(); setOpen(false); }
  };

  const handleFocus = useCallback(async () => {
    if (disabled) return;
    setOpen(true);
    // Saqlangan natijalar bo'lsa — ularni ko'rsatamiz, standart ro'yxatni yuklamaymiz
    if (!q.trim() && !(keepResultsRef.current && results.length)) {
      setLoading(true);
      try {
        const res = await api.get(searchEndpoint, { params: { limit: 30, warehouse_id: warehouseId || undefined }, _silent: true });
        const items = Array.isArray(res.data) ? res.data : (res.data?.items || []);
        setResults(items.slice(0, 30));
      } catch { /* ignore */ }
      finally { setLoading(false); }
    }
  }, [disabled, q, warehouseId, results.length, searchEndpoint]);

  const handleBlur = useCallback(() => {
    // kichik delay — mouseDown evenidan keyin blur ishlaydi
    setTimeout(() => { setOpen(false); }, 150);
  }, []);

  return (
    <div className="relative">
      <div className={`flex items-center gap-2 border rounded-lg px-2.5 py-1.5 bg-white transition-all ${disabled ? 'border-slate-100 bg-slate-50 opacity-60' :
        open || q ? 'border-blue-500 ring-2 ring-blue-100' : 'border-slate-200 hover:border-slate-300'
        }`}>
        {loading
          ? <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
          : <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-4 h-4 text-slate-400 shrink-0" />
        }
        <input ref={inputRef} value={q}
          disabled={disabled}
          onChange={e => { keepResultsRef.current = false; setQ(e.target.value); setActiveIdx(0); }}
          onKeyDown={handleKey}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder={placeholder || t('wholesale.productSearchPlaceholder')}
          className="flex-1 text-xs md:text-sm outline-none bg-transparent placeholder:text-slate-400 disabled:cursor-not-allowed"
        />
        {(q || (keepResultsRef.current && results.length > 0)) && <button onMouseDown={(e) => { e.preventDefault(); clearSearch(); inputRef.current?.focus(); }} className="text-slate-300 hover:text-red-400"><Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" /></button>}
      </div>

      {open && !disabled && (
        <div ref={listRef} className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-2xl z-50 overflow-hidden max-h-[380px] overflow-y-auto">
          {loading && results.length === 0 && (
            <div className="px-4 py-8 text-center">
              <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <div className="text-xs font-bold text-slate-400">{t('pos.productsLoading')}</div>
            </div>
          )}
          {!loading && results.length === 0 && q.trim() && (
            <div className="px-4 py-4 text-center text-sm text-slate-400">"{q}" — {t('wholesale.notFound')}</div>
          )}
          {results.length > 0 && results.map((p, i) => (
            <button key={p.id} data-idx={i} onMouseDown={() => select(p, i)}
              className={`w-full cursor-pointer flex items-center gap-3 px-4 py-3 border-b border-slate-50 last:border-0 transition-colors text-left ${i === activeIdx ? 'bg-blue-50' : 'hover:bg-slate-50'}`}>
              <div className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 overflow-hidden">
                {p.image_url ? <img src={p.image_url} alt="" className="w-full h-full object-cover" /> : <Ic d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" cls="w-4 h-4 text-slate-400" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-slate-800 truncate">{p.name}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  {p.sku && <span className="text-xs text-slate-400 font-mono">{p.sku}</span>}
                  {p.barcode && <><span className="text-xs text-slate-300">|</span><span className="text-xs text-slate-400 font-mono">{p.barcode}</span></>}
                  {searchFeatures?.pharmacy && p.nearest_expiry && (
                    <span className={`text-[10px] font-bold px-1 rounded ${p.expiry_warn ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
                      {p.expiry_warn ? '⚠ ' : ''}{fmtExpiry(p.nearest_expiry)}
                    </span>
                  )}
                  {searchFeatures?.pharmacy && ((p.control_class && p.control_class !== 'none') || p.is_rx) && (
                    <span className="text-[10px] font-bold px-1 rounded bg-violet-100 text-violet-700">Rx</span>
                  )}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-sm font-black text-blue-700">
                  {(() => {
                    let displayPrice = p.sale_price;
                    let displayCur = p.sale_currency || 'UZS';
                    if (customerPriceType === 'wholesale' && p.wholesale_price) {
                      displayPrice = p.wholesale_price;
                      displayCur = p.wholesale_currency || p.sale_currency || 'UZS';
                    } else if (customerPriceType === 'cost' && p.cost_price) {
                      displayPrice = p.cost_price;
                      displayCur = p.cost_currency || 'UZS';
                    }
                    return `${fmt(displayPrice)} ${displayCur === 'USD' ? '$' : displayCur === 'UZS' ? 's' : displayCur}`;
                  })()}
                </div>
                {p.wholesale_price && p.sale_price !== p.wholesale_price && customerPriceType !== 'wholesale' && customerPriceType !== 'cost' && (
                  <div className="text-xs text-slate-400 line-through">
                    {fmt(p.wholesale_price)} {p.wholesale_currency === 'USD' ? '$' : (p.wholesale_currency || 's')} ({t('wholesale.wholesaleShort')})
                  </div>
                )}
                <div className={`text-xs font-semibold mt-0.5 ${Number(p.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>{(searchFeatures?.pharmacy && p.stock_display && Number(p.stock_quantity) > 0) ? p.stock_display : `${fmt(p.stock_quantity)} ${p.unit || t('common.piece')}`}</div>
              </div>
            </button>
          ))}
          {/* + Yangi mahsulot */}
          <button onMouseDown={() => { clearSearch(); setOpen(false); onOpenAdd?.(); }}
            className="w-full flex cursor-pointer items-center gap-2 px-4 py-3 text-emerald-600 hover:bg-emerald-50 font-bold text-sm border-t border-slate-100 transition-colors">
            <span className="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center text-base leading-none">+</span>
            {t('wholesale.addNewProduct')}
          </button>
        </div>
      )}
    </div>
  );
}));

/* ─── Asosiy komponent ──────────────────────────────────── */
export default function UlgurjiSotuv() {
  const { t } = useLang();
  const [customers, setCustomers] = useState([]);
  // T3.19: tanlangan mijozning individual narxlari { [product_id]: price }
  const [custPrices, setCustPrices] = useState({});
  const custPricesRef = useRef({});
  const [warehouses, setWarehouses] = useState([]);

  const handleNewFetchedCustomers = useCallback((newCusts) => {
    setCustomers(prev => {
      const map = new Map(prev.map(c => [c.id, c]));
      let changed = false;
      newCusts.forEach(c => {
        if (!map.has(c.id)) { map.set(c.id, c); changed = true; }
      });
      return changed ? Array.from(map.values()) : prev;
    });
  }, []);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [autoPrint, setAutoPrint] = useState(localStorage.getItem('ulgurji_autoPrint') !== 'false');
  const [onlySom, setOnlySom] = useState(localStorage.getItem('ulgurji_onlySom') === 'true');
  const [receiptWidth, setReceiptWidth] = useState(localStorage.getItem('ulgurji_receiptWidth') || '80');
  const [defaultCustomerId, setDefaultCustomerId] = useState(localStorage.getItem('ulgurji_defaultCustomer') || '');

  const [custId, setCustId] = useState(() => sessionStorage.getItem('ulgurji_customer') || localStorage.getItem('ulgurji_defaultCustomer') || '');
  const [isWholesaleMode, setIsWholesaleMode] = useState(localStorage.getItem('ulgurji_isWholesale') === 'true');
  const [warehouseId, setWarehouseId] = useState('');
  const { defaultWarehouseId: branchDefaultWarehouseId } = useBranch();   // T1.5: ProductAddModal uchun filial default ombori

  // Promotions
  const [promotions, setPromotions] = useState([]);
  // T4.3: amaldagi aksiyalar serverdan — tanlangan ombor filiali bo'yicha (ombor tanlanmasa xodim filiali)
  useEffect(() => {
    const wh = warehouses.find(w => String(w.id) === String(warehouseId));
    const params = wh?.branch_id ? { branch_id: wh.branch_id } : {};
    api.get('/promotions/active', { params, _suppressToast: true })
      .then(r => setPromotions(Array.isArray(r.data) ? r.data.filter(p => p.is_active) : []))
      .catch(() => setPromotions([]));
  }, [warehouseId, warehouses]);

  // SessionStorage dan savatni tiklash (sahifa yangilanganda ham saqlanadi)
  const [cart, setCart] = useState(() => {
    try {
      const saved = sessionStorage.getItem('ulgurji_cart');
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });
  const [note, setNote] = useState('');
  const [delivery, setDelivery] = useState(EMPTY_DELIVERY);
  const features = useCompanyFeatures();
  // D2.6: dorixona rejimi — faqat modul yoqilgan korxonada retsept/analog/birlik elementlari ko'rinadi
  const pharmacy = !!features?.pharmacy;
  const rxMode = features?.pharmacy_settings?.rx_mode === 'block' ? 'block' : 'warn';
  const [rxModal, setRxModal] = useState(null);         // { proceed?, message? }
  const [rxData, setRxData] = useState({});
  const [rxReason, setRxReason] = useState('');
  const [rxError, setRxError] = useState('');
  const [analogModal, setAnalogModal] = useState(null);
  const [saleError, setSaleError] = useState(null);
  const [showPayment, setShowPayment] = useState(false);
  const [saving, setSaving] = useState(false);
  const { shift: activeShift, hasShift, reload: reloadShift } = useActiveShift();
  const [showShiftModal, setShowShiftModal] = useState(false);
  const [showShiftClose, setShowShiftClose] = useState(false);   // T3.1: sotuv ekranidan smenani yopish

  // Product entry form
  const [formProduct, setFormProduct] = useState(null);
  const [formPrice, setFormPrice] = useState('');
  const [formCurrency, setFormCurrency] = useState('');
  const [formQty, setFormQty] = useState('1');
  const [formDiscType, setFormDiscType] = useState('pct');
  const [formDiscVal, setFormDiscVal] = useState('');
  const [formPromoId, setFormPromoId] = useState(null);   // T4.3: formadagi mahsulotga qo'llangan aksiya
  // Qo'lda kiritilgan jami summa; miqdor/narx/chegirma o'zgarsa (key mos kelmasa) hisoblangan summa ko'rsatiladi
  const [formTotalEdit, setFormTotalEdit] = useState(null); // { key, text }
  const [currencies, setCurrencies] = useState([]);
  const formQtyRef = useRef(null);
  const custSearchRef = useRef(null);
  const prodSearchRef = useRef(null);
  const [showProdAddModal, setShowProdAddModal] = useState(false);
  const [variantPickerProduct, setVariantPickerProduct] = useState(null); // parent mahsulot tanlanganda
  const formPriceRef = useRef(null);
  const formDiscRef = useRef(null);

  // Mobile tab: 'form' | 'cart'
  const [mobileTab, setMobileTab] = useState('form');

  // Clock
  const [currentTime, setCurrentTime] = useState(new Date());
  const selected = useMemo(() => customers.find(c => String(c.id) === String(custId)), [customers, custId]);
  useEffect(() => {
    const t = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Mijoz narx turini o'zgartirish (Chakana ↔ Ulgurji ↔ Tannarx)
  const changePriceType = useCallback(() => {
    if (!custId) return;
    const ORDER = ['sale', 'wholesale', 'cost'];
    setCustomers(prev => prev.map(c => {
      if (String(c.id) !== String(custId)) return c;
      const cur = c.price_type || 'sale';
      const next = ORDER[(ORDER.indexOf(cur) + 1) % ORDER.length];
      return { ...c, price_type: next };
    }));
    // Savatni ham yangilash (useEffect custId+customers ga bog'liq emas, shuning uchun manual)
    setCart(prev => {
      const cust = customers.find(c => String(c.id) === String(custId));
      if (!cust) return prev;
      const cur = cust.price_type || 'sale';
      const ORDER2 = ['sale', 'wholesale', 'cost'];
      const next = ORDER2[(ORDER2.indexOf(cur) + 1) % ORDER2.length];
      return prev.map(it => {
        if (it.price_manual) return it;
        let newPrice = lineBasePrice(it);
        if (next === 'wholesale' && it.wholesale_price > 0) newPrice = it.wholesale_price;
        else if (next === 'cost' && it.cost_price > 0) newPrice = it.cost_price;
        else if (it.sale_price > 0) newPrice = it.sale_price;
        // T3.19: individual narx narx turidan ustun
        const cp = custPricesRef.current[it.product_id];
        if (cp != null && Number(cp) > 0 && (it.currency || 'UZS') === 'UZS') newPrice = Number(cp);
        return repriceLine(it, newPrice);
      });
    });
  }, [custId, customers]);

  // Cart o'zgargan har bir holda sessionStorage ga saqlash
  useEffect(() => {
    try {
      if (cart.length > 0) {
        sessionStorage.setItem('ulgurji_cart', JSON.stringify(cart));
      } else {
        sessionStorage.removeItem('ulgurji_cart');
      }
    } catch { /* ignore */ }
  }, [cart]);

  // Mijoz o'zgarganda sessionStorage ga saqlash va savat narxlarini yangilash
  useEffect(() => {
    if (custId) {
      sessionStorage.setItem('ulgurji_customer', custId);
      // Savatdagi mahsulot narxlarini yangi mijoz narx turiga qarab yangilash
      const cust = customers.find(c => String(c.id) === String(custId));
      if (cust && cart.length > 0) {
        const pt = cust.price_type || 'sale';
        setCart(prev => prev.map(it => {
          if (it.price_manual) return it;   // saqlangan buyurtma narxi o'zgarmaydi
          let newPrice = lineBasePrice(it);
          if (pt === 'wholesale' && it.wholesale_price > 0) newPrice = it.wholesale_price;
          else if (pt === 'cost' && it.cost_price > 0) newPrice = it.cost_price;
          else if (pt === 'sale' && it.sale_price > 0) newPrice = it.sale_price;
          // T3.19: individual narx narx turidan ustun
          const cp = custPrices[it.product_id];
          if (cp != null && Number(cp) > 0 && (it.currency || 'UZS') === 'UZS') newPrice = Number(cp);
          return repriceLine(it, newPrice);
        }));
      }
    } else {
      sessionStorage.removeItem('ulgurji_customer');
    }
  }, [custId, customers, custPrices]); // eslint-disable-line react-hooks/exhaustive-deps

  // T3.19: mijoz tanlanganda uning individual narxlarini yuklash
  useEffect(() => {
    custPricesRef.current = {};
    setCustPrices({});
    if (!custId) return undefined;
    let cancelled = false;
    api.get(`/customers/${custId}/prices`, { _silent: true, _suppressToast: true })
      .then(r => {
        if (cancelled) return;
        const map = {};
        (Array.isArray(r.data) ? r.data : []).forEach(row => { map[row.product_id] = Number(row.price); });
        custPricesRef.current = map;
        setCustPrices(map);
      })
      .catch(() => { });
    return () => { cancelled = true; };
  }, [custId]);

  // T3.19: qator narxi serverning ro'yxat narxidan (individual narx > narx turi) farq qilsa — qo'lda deb belgilanadi
  const isPriceManual = (it) => {
    if (it.price_manual) return true;
    const price = Number(it.price) || 0;
    if ((it.currency || 'UZS') !== 'UZS') return true;
    // D2.6: birlik (quti/blister) qatori — narx shu birlikning ro'yxat narxiga (unit.price yo'q bo'lsa asosiy narx * nisbat) teng bo'lsa qo'lda emas
    const un = it.unit_id ? (it.units || []).find(u => u.id === it.unit_id) : null;
    if (it.unit_id && !un) return true;
    const lineList = (base) => (un ? unitLinePrice(base, it.sale_price, un) : base);
    const cp = custPrices[it.product_id];
    if (cp != null && Number(cp) > 0) return price !== lineList(Number(cp));
    const pt = selected?.price_type || 'sale';
    let list = Number(it.sale_price) || 0;
    if (pt === 'wholesale') list = Number(it.wholesale_price) || list;
    else if (pt === 'cost') list = Number(it.cost_price) || list;
    return price !== lineList(list);
  };

  const saveSettings = () => {
    localStorage.setItem('ulgurji_autoPrint', autoPrint);
    localStorage.setItem('ulgurji_receiptWidth', receiptWidth);
    localStorage.setItem('ulgurji_defaultCustomer', defaultCustomerId);
    localStorage.setItem('ulgurji_onlySom', String(onlySom)); // Persist the onlySom setting
    setSettingsOpen(false);
    if (!cart.length && defaultCustomerId) setCustId(defaultCustomerId);
    toast.success(t('wholesale.settingsSaved'));
  };

  const [payments, setPayments] = useState([]);
  const [discType, setDiscType] = useState('pct');
  const [discVal, setDiscVal] = useState('');
  const [payNote, setPayNote] = useState('');
  const [debtDate, setDebtDate] = useState('');
  const [showDebtDate, setShowDebtDate] = useState(false);
  const [editingSale, setEditingSale] = useState(() => {
    try {
      const s = sessionStorage.getItem('ulgurji_editing_sale');
      return s ? JSON.parse(s) : null;
    } catch { return null; }
  });
  useEffect(() => {
    if (editingSale) {
      sessionStorage.setItem('ulgurji_editing_sale', JSON.stringify(editingSale));
    } else {
      sessionStorage.removeItem('ulgurji_editing_sale');
    }
  }, [editingSale]);
  const [pendingSaving, setPendingSaving] = useState(false);

  // Fiskal tasdiqlash modal
  const [fiskalPending, setFiskalPending] = useState(null); // null | { factoryId, cart, payments, discount, saleId }
  const [isFiskalizing, setIsFiskalizing] = useState(false);

  // T3.18: filial to'lov terminallari (serverdan; xato bo'lsa bo'sh = tranzaksiya raqami ixtiyoriy)
  const [terminals, setTerminals] = useState([]);
  useEffect(() => {
    api.get('/payment-terminals/mine', { _silent: true, _suppressToast: true })
      .then(r => setTerminals(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  }, []);
  const REF_PROVIDERS = ['click', 'payme', 'uzum'];
  const tfb = (key, fallback, vars) => {
    let v = t(key);
    if (v === key) v = fallback;
    return vars ? Object.keys(vars).reduce((acc, k) => acc.replace(`{${k}}`, vars[k]), v) : v;
  };
  const tfRef = useRef(tfb);
  tfRef.current = tfb;
  const saleBranchId = warehouses.find(w => String(w.id) === String(warehouseId))?.branch_id || null;
  // Joriy filial terminallari (filial aniqlangan bo'lsa); butun korxona terminallari (branch_id yo'q) hammada
  const providerTerminals = (type) => terminals.filter(x =>
    x.provider === type && x.is_active !== false && (!saleBranchId || !x.branch_id || x.branch_id === saleBranchId));
  const referenceRequired = (p) => {
    if (!REF_PROVIDERS.includes(p.type)) return false;
    const sel = p.terminal_id ? terminals.find(x => String(x.id) === String(p.terminal_id)) : null;
    if (sel) return !!sel.require_reference;
    return providerTerminals(p.type).some(x => x.require_reference);
  };



  const [tab, setTab] = useState('new');
  const [sales, setSales] = useState([]);
  const [loadingSales, setLoadingSales] = useState(false);
  const [filters, setFilters] = useState({ date_from: new Date().toISOString().split('T')[0], date_to: new Date().toISOString().split('T')[0], status: '', search: '' });
  const [selectedSale, setSelectedSale] = useState(null);
  const [page, setPage] = useState(0);
  const LIMIT = 25;
  const [openMenuId, setOpenMenuId] = useState(null);
  const [returnSale, setReturnSale] = useState(null);
  const [assignModalSale, setAssignModalSale] = useState(null);
  const [assignCustId, setAssignCustId] = useState('');
  const [savingAssignCustomer, setSavingAssignCustomer] = useState(false);

  const scanBufRef = useRef('');
  const scanTimeRef = useRef(0);
  const customersRef = useRef([]);
  const setCustIdRef = useRef(setCustId);
  const addToCartRef = useRef(null);
  const pharmaRef = useRef({ pharmacy: false, warehouseId: '' });   // D2.6: skaner effekti ([] deps) uchun
  // custIdRef: addToCart closuresi uchun — har doim yangi qiymatni o'qiydi
  const custIdRef = useRef(custId);

  const [draftsList, setDraftsList] = useState([]);
  useEffect(() => {
    if (tab === 'drafts') {
      try { setDraftsList(JSON.parse(localStorage.getItem('ulgurji_drafts') || '[]')); } catch (err) { console.error('Load drafts error:', err); setDraftsList([]); }
    }
  }, [tab]);

  const loadDraft = (idx) => {
    const d = draftsList[idx];
    if (!d) return;
    if (cart.length > 0 && !window.confirm(t('wholesale.confirmDiscardCurrentCart'))) return;
    setCart(d.cart || []); setCustId(d.custId || ''); setNote(d.note || '');
    if (d.discType) setDiscType(d.discType); setDiscVal(d.discVal || '');
    setTab('new');
    const nd = draftsList.filter((_, i) => i !== idx);
    setDraftsList(nd); localStorage.setItem('ulgurji_drafts', JSON.stringify(nd));
    toast.success(t('wholesale.archiveLoadedToCart'));
  };

  const removeDraft = (idx) => {
    if (!window.confirm(t('wholesale.confirmDeleteArchive'))) return;
    const nd = draftsList.filter((_, i) => i !== idx);
    setDraftsList(nd); localStorage.setItem('ulgurji_drafts', JSON.stringify(nd));
  };

  useEffect(() => {
    api.get('/customers/?limit=200').then(r => setCustomers(Array.isArray(r.data) ? r.data : (r.data?.items || []))).catch(() => { });
    api.get('/warehouses/').then(r => setWarehouses(Array.isArray(r.data) ? r.data : [])).catch(() => { });
    api.get('/currencies/').then(r => setCurrencies(Array.isArray(r.data) ? r.data : [])).catch(() => { });
    api.get('/companies/me/receipt_templates').then(r => {
      const d = r.data?.receipt_templates || {};
      if (Object.keys(d).length) {
        const stored = {};
        if (d.r58) stored.r58 = d.r58;
        if (d.r80) stored.r80 = d.r80;
        if (d.nak) stored.nak = d.nak;
        if (Object.keys(stored).length) saveReceiptSettings(stored);
      }
    }).catch(() => { });
  }, []);

  const loadSales = useCallback(() => {
    setLoadingSales(true);
    const params = { skip: page * LIMIT, limit: LIMIT, ...filters };
    if (!params.status) delete params.status;
    if (!params.search) delete params.search;
    api.get('/sales/', { params })
      .then(r => setSales(Array.isArray(r.data) ? r.data : []))
      .catch(() => { })
      .finally(() => setLoadingSales(false));
  }, [filters, page]);

  useEffect(() => { if (tab === 'list') loadSales(); }, [tab, loadSales]);

  // Qaytarish bilan bog'liq sotuv (R... hujjat, qaytarilgan/qisman qaytarilgan) —
  // tahrirlash/o'chirish backend'da 400 (qoldiq va pul ikki marta hisoblanmasin)
  const isReturnLinked = (s) => ['refunded', 'partial_refund'].includes(s?.status)
    || String(s?.number || '').startsWith('R') || !!s?.original_sale_id;

  const loadEditSale = async (s) => {
    try {
      if (isReturnLinked(s)) { toast.error(t('sale.cannotEditReturned')); return; }
      if (cart.length > 0 && !window.confirm(t('wholesale.confirmDiscardCartSimple'))) return;
      const r = await api.get(`/sales/${s.id}`);
      const sale = r.data;
      setCart((sale.items || []).map(it => ({
        product_id: it.product_id, name: it.product_name,
        unit: it.unit || 'dona',            // ← SaleItem dan haqiqiy unit
        qty: Number(it.quantity), price: Number(it.unit_price),
        currency: it.currency_code || 'UZS',
        rate: it.exchange_rate ? Number(it.exchange_rate) : 1,
        discount_type: 'sum', discount_val: it.discount > 0 ? String(it.discount) : '',
        wholesale_price: Number(it.unit_price), sale_price: Number(it.unit_price), stock_quantity: 9999,
        price_manual: true,   // T3.19: saqlangan (buyurtma/sotuv) narxi qayta hisoblanmasin
        variant_id: it.variant_id || null,     // ← variant tahrirda yo'qolmasin
        warehouse_id: it.warehouse_id || null, // ← per-item sklad (Desktop POS dan)
        warehouse_name: it.warehouse_name || null,
      })));
      setCustId(sale.customer_id ? String(sale.customer_id) : '');
      setNote(sale.note || ''); setDelivery(deliveryFromSale(sale.delivery)); setDiscType('sum');
      setDiscVal(sale.discount_amount > 0 ? String(sale.discount_amount) : '');

      // Load existing payments to prevent wipeout on save
      if (sale.payments && sale.payments.length > 0) {
        setPayments(sale.payments.map(p => ({ id: p.id || Math.random(), type: p.payment_type, amt: String(p.amount) })));
      } else if (sale.paid_amount > 0) {
        setPayments([{ id: Math.random(), type: sale.payment_type || 'cash', amt: String(sale.paid_amount) }]);
      } else {
        setPayments([]);
      }
      if (sale.debt_due_date) {
        setDebtDate(sale.debt_due_date);
        setShowDebtDate(true);
      }

      setEditingSale({ id: sale.id, number: sale.number, warehouse_id: sale.warehouse_id, created_at: sale.created_at, status: sale.status });
      if (sale.warehouse_id) setWarehouseId(String(sale.warehouse_id));
      else setWarehouseId('');
      // MUHIM: tahrirlash rejimida session_sale_id YOZMAYMIZ
      // Aks holda useEffect (pending tiklash) cartni yana bir marta to'ldiradi → dublikat!
      sessionStorage.removeItem('ulgurji_session_sale_id');
      setTab('new'); setOpenMenuId(null);
      toast.success(t('wholesale.saleLoadedForEdit', { number: sale.number }));
    } catch (e) { toast.error(e?.response?.data?.detail || t('wholesale.loadSaleError')); }
  };

  const deleteSale = async (id) => {
    if (!window.confirm(t('wholesale.confirmDeleteSale'))) return;
    try { await api.delete(`/sales/${id}`); toast.success(t('wholesale.saleDeleted')); loadSales(); }
    catch (e) { toast.error(e.response?.data?.detail || t('wholesale.deleteError')); }
  };

  // T3.8: tanlangan mijoz 200 talik oflayn zaxira ro'yxatda bo'lmasa (masalan sessiyadan tiklangan) — alohida olinadi
  useEffect(() => {
    if (customers.length === 0) return undefined;
    const missing = [custId, assignCustId, defaultCustomerId].filter(id => id && !customers.some(c => String(c.id) === String(id)));
    if (!missing.length) return undefined;
    let alive = true;
    missing.forEach(id => {
      api.post(`/customers/${id}`, null, { _silent: true, _suppressToast: true })   // yagona mijoz: POST /customers/{id}
        .then(r => { if (alive && r.data?.id) handleNewFetchedCustomers([r.data]); })
        .catch(() => { /* topilmasa nom ko'rinmaydi, id saqlanadi */ });
    });
    return () => { alive = false; };
  }, [custId, assignCustId, defaultCustomerId, customers, handleNewFetchedCustomers]);

  const openAssignCustomerModal = (sale) => {
    setAssignModalSale(sale);
    setAssignCustId(sale.customer_id ? String(sale.customer_id) : '');
  };

  const handleSaveAssignCustomer = async () => {
    if (!assignModalSale) return;
    if (!assignCustId) {
      toast.error(t('wholesale.selectCustomerPrompt') || 'Iltimos, mijozni tanlang');
      return;
    }
    try {
      setSavingAssignCustomer(true);
      const res = await api.put(`/sales/${assignModalSale.id}/assign-customer`, {
        customer_id: Number(assignCustId)
      });
      toast.success(t('wholesale.assignCustomerSuccess') || 'Mijoz muvaffaqiyatli biriktirildi');
      const updatedSale = res.data;
      setSales(prev => prev.map(s => s.id === updatedSale.id ? { ...s, customer_id: updatedSale.customer_id, customer_name: updatedSale.customer_name } : s));
      if (selectedSale?.id === updatedSale.id) {
        setSelectedSale(prev => ({ ...prev, customer_id: updatedSale.customer_id, customer_name: updatedSale.customer_name }));
      }
      setAssignModalSale(null);
      setAssignCustId('');
      loadSales();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSavingAssignCustomer(false);
    }
  };

  const printSale = async (s, size) => {
    try {
      let data = s;
      if (!s.items) { const r = await api.get(`/sales/${s.id}`); data = r.data; }
      const clientName = data.contractor_name || data.customer_name || s.customer_name || s.contractor_name || (data.customer && data.customer.name);
      
      const selectedCust = customers.find(c => String(c.id) === String(data.customer_id || s.customer_id));
      
      // Chek chop etilganda mijozning HOZIRGI (sotuv keyingi) balansi emas,
      // OLDINGI (sotuv yaratilishidan avval) balansi ko'rsatilishi kerak.
      // Agar sotuv allaqachon bajarilgan bo'lsa, mijoz balansi yangilangan —
      // shuning uchun `debt_amounts`ni hisobga olib, avvalgi holatni tiklashga harakat qilamiz.
      let prevBalances = null;
      let rawBeforeDebtBalances = data.before_debt_balances || s.before_debt_balances;
      if (typeof rawBeforeDebtBalances === 'string') {
        try { rawBeforeDebtBalances = JSON.parse(rawBeforeDebtBalances); } catch (e) { rawBeforeDebtBalances = null; }
      }

      if (rawBeforeDebtBalances && Object.keys(rawBeforeDebtBalances).length > 0) {
        prevBalances = rawBeforeDebtBalances;
      } else if (selectedCust) {
        const currBalances = selectedCust.debt_balances || { UZS: Number(selectedCust.debt_balance || 0) };
        let saleDebtAmounts = data.debt_amounts || {};
        if (typeof saleDebtAmounts === 'string') {
          try { saleDebtAmounts = JSON.parse(saleDebtAmounts); } catch (e) { saleDebtAmounts = {}; }
        }

        // Eskiroq sotuvlar uchun fallback (qachonki backend debt_amounts saqlamagan bo'lsa)
        if (Object.keys(saleDebtAmounts).length === 0) {
          const residByCurr = {};
          if (data.items) {
            data.items.forEach(it => {
              const c = String(it.currency_code || 'UZS').toUpperCase();
              residByCurr[c] = (residByCurr[c] || 0) + Number(it.subtotal || 0);
            });
          }
          
          let pAmtUZS = Number(data.paid_amount || 0);
          if (pAmtUZS > 0) {
             if (residByCurr['UZS'] !== undefined && residByCurr['UZS'] >= pAmtUZS) {
                 residByCurr['UZS'] -= pAmtUZS;
             } else {
                 let rem = pAmtUZS - (residByCurr['UZS'] || 0);
                 residByCurr['UZS'] = 0;
                 for (const c of Object.keys(residByCurr)) {
                    if (c !== 'UZS' && residByCurr[c] > 0) {
                        const rate = Number(data.exchange_rate || 1);
                        if (rate > 1) {
                            const inVal = rem / rate;
                            if (residByCurr[c] >= inVal) {
                                residByCurr[c] -= inVal;
                                rem = 0;
                                break;
                            } else {
                                rem -= residByCurr[c] * rate;
                                residByCurr[c] = 0;
                            }
                        }
                    }
                 }
             }
          }

          for (const [c, a] of Object.entries(residByCurr)) {
            if (a > 0.001) saleDebtAmounts[c] = Number(a.toFixed(2));
          }
          data.debt_amounts = saleDebtAmounts;
        }

        // Fallback: Avvalgi balans = hozirgi balans - joriy sotuv qarzi
        // (Bu faqatgina eng so'nggi sotuv uchun aniq ishlaydi, eski sotuvlar uchun noaniq)
        if (Object.keys(saleDebtAmounts).length > 0) {
          prevBalances = { ...currBalances };
          for (const [curr, amt] of Object.entries(saleDebtAmounts)) {
            const c = String(curr).toUpperCase();
            prevBalances[c] = (Number(prevBalances[c] || 0)) - Number(amt);
          }
        } else {
          prevBalances = currBalances;
        }
      }

      data = {
        ...data,
        contractor_name: clientName,
        customer_name: clientName,
        before_debt_balances: prevBalances,
        before_debt: 0, // before_debt_balances ishlatilganda bu e'tiborga olinmaydi
      };
      const tpl = size === 'nak' ? 'nak' : size === '58' ? '58' : '80';
      const rSettings = getReceiptSettings();
      const cfgRaw = tpl === 'nak' ? (rSettings.nak || {}) : (rSettings['r' + tpl] || {});
      const _r58 = rSettings.r58 || {};
      const _r80 = rSettings.r80 || {};
      const _rN = rSettings.nak || {};
      const _CF = ['company', 'address', 'phone', 'inn', 'logo', 'logo_size', 'footer'];
      const tmplCfg = { ...cfgRaw };
      for (const f of _CF) {
        if (tmplCfg[f] === undefined) {
          tmplCfg[f] = _r58[f] !== undefined ? _r58[f] : (_r80[f] !== undefined ? _r80[f] : (_rN[f] || ''));
        }
      }
      printReceiptHtml(buildReceiptHtml(data, tpl, tmplCfg));
    } catch (err) { console.error('Print error:', err); toast.error(t('wholesale.printError')); }
  };

  // ── Bitta sotuvni PDF formatida yuklab olish (Namuna asosida) ────────────
  const downloadSalePdf = async (s) => {
    toast.info("PDF tayyorlanmoqda...");
    try {
      const res = await api.get(`/sales/${s.id}/pdf`, { responseType: 'blob' });
      const cust = s.customer_name || s.contractor_name || 'Mijoz';
      const datePart = (s.created_at || '').replace(/[- :]/g, '_').slice(0, 19);
      const fallbackName = `Sotuv_${cust.replace(/[^\w\s-]/g, '').trim().replace(/[-\s]+/g, '_')}_${datePart}.pdf`;
      const filename = filenameFromDisposition(res.headers && (res.headers['content-disposition'] || res.headers['Content-Disposition']), fallbackName);
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const saveAs = await loadSaveAs();
      saveAs(blob, filename);
      toast.success("PDF muvaffaqiyatli yuklab olindi");
    } catch (err) {
      const msg = await blobErrorMessage(err);
      console.error('Sotuv PDF xatosi:', err, msg);
      toast.error(`PDF yuklanmadi: ${msg}`);
    }
  };

  // ── Sotuvlar ro'yxatini Excel (.xlsx) formatida eksport qilish ──────────
  const exportToExcel = async () => {
    if (!sales || sales.length === 0) {
      toast.error(t('common.noData') || "Eksport qilish uchun sotuvlar mavjud emas");
      return;
    }
    try {
      const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
      const rows = sales.map((s, idx) => {
        const total = Number(s.total_amount || 0);
        const paid = Number(s.paid_amount || 0);
        const debt = Math.max(0, total - paid);
        const pType = (PAY_META_KEYS[s.payment_type] && t(PAY_META_KEYS[s.payment_type])) || s.payment_type || '—';
        const st = (STATUS_META[s.status]?.lKey && t(STATUS_META[s.status].lKey)) || s.status || '—';
        const dStr = s.created_at
          ? new Date(s.created_at).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
          : '—';
        return {
          "№": idx + 1,
          "Hujjat raqami": s.number || `#${s.id}`,
          "Mijoz": s.customer_name || '—',
          "Jami summa (so'm)": total,
          "To'langan (so'm)": paid,
          "Qarz (so'm)": debt,
          "To'lov turi": pType,
          "Holati": st,
          "Kassir": s.cashier_name || '—',
          "Sana": dStr,
        };
      });

      const ws = XLSX.utils.json_to_sheet(rows);
      ws['!cols'] = [
        { wch: 6 },
        { wch: 18 },
        { wch: 24 },
        { wch: 18 },
        { wch: 18 },
        { wch: 18 },
        { wch: 16 },
        { wch: 20 },
        { wch: 18 },
        { wch: 20 },
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Sotuvlar');
      const filename = `sotuvlar_${filters.date_from || today()}_${filters.date_to || today()}.xlsx`;
      saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), filename);
      toast.success(t('wholesale.excelExportSuccess') || "Excel fayl muvaffaqiyatli yuklab olindi");
    } catch (err) {
      console.error('Excel export error:', err);
      toast.error(t('wholesale.exportError') || "Excel yuklab olishda xatolik yuz berdi");
    }
  };

  // ── Sotuvlar ro'yxatini PDF formatida yuklab olish / eksport qilish ──────
  const exportToPdf = async () => {
    if (!sales || sales.length === 0) {
      toast.error(t('common.noData') || "Eksport qilish uchun sotuvlar mavjud emas");
      return;
    }
    toast.info("PDF hisobot tayyorlanmoqda...");
    try {
      const params = {
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
        status: filters.status || undefined,
        search: filters.search || undefined,
      };
      const res = await api.get('/sales/export/pdf', { params, responseType: 'blob' });
      const fallbackName = `sotuvlar_hisoboti_${filters.date_from || today()}_${filters.date_to || today()}.pdf`;
      const filename = filenameFromDisposition(res.headers && (res.headers['content-disposition'] || res.headers['Content-Disposition']), fallbackName);
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const saveAs = await loadSaveAs();
      saveAs(blob, filename);
      toast.success("Sotuvlar hisoboti PDF muvaffaqiyatli yuklab olindi");
    } catch (err) {
      const errMsg = await blobErrorMessage(err);
      console.error('Sotuvlar PDF xatosi:', err, errMsg);
      toast.error(`PDF yuklanmadi: ${errMsg}`);
      console.warn('Backend export pdf error, falling back to browser print view:', err);
      try {
        const rSettings = getReceiptSettings();
        const compName = rSettings?.nak?.company || rSettings?.r80?.company || rSettings?.company || "E-Code ERP";
        const dateFrom = filters.date_from || today();
        const dateTo = filters.date_to || today();

        let sumTotal = 0;
        let sumPaid = 0;
        let sumDebt = 0;

        const rowsHtml = sales.map((s, idx) => {
          const total = Number(s.total_amount || 0);
          const paid = Number(s.paid_amount || 0);
          const debt = Math.max(0, total - paid);
          sumTotal += total;
          sumPaid += paid;
          sumDebt += debt;

          const pType = (PAY_META_KEYS[s.payment_type] && t(PAY_META_KEYS[s.payment_type])) || s.payment_type || '—';
          const st = (STATUS_META[s.status]?.lKey && t(STATUS_META[s.status].lKey)) || s.status || '—';
          const dStr = s.created_at
            ? new Date(s.created_at).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
            : '—';

          return `<tr>
            <td style="text-align:center;">${idx + 1}</td>
            <td style="font-weight:600;">${s.number || `#${s.id}`}</td>
            <td>${s.customer_name || '—'}</td>
            <td style="text-align:right;font-weight:600;">${fmt(total)} s</td>
            <td style="text-align:right;color:#059669;">${fmt(paid)} s</td>
            <td style="text-align:right;color:#dc2626;font-weight:600;">${debt > 0 ? fmt(debt) + ' s' : '—'}</td>
            <td style="text-align:center;">${pType}</td>
            <td style="text-align:center;">${st}</td>
            <td>${s.cashier_name || '—'}</td>
            <td style="text-align:center;font-size:10px;">${dStr}</td>
          </tr>`;
        }).join('');

        const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Sotuvlar hisoboti (${dateFrom} - ${dateTo})</title>
  <style>
    @media print {
      @page { size: landscape; margin: 8mm; }
      body { margin: 0; padding: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 11px; color: #1e293b; padding: 12px; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 8px; margin-bottom: 12px; }
    .title { font-size: 18px; font-weight: 800; color: #0f172a; }
    .subtitle { font-size: 12px; color: #64748b; margin-top: 2px; }
    .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
    .summary-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 12px; }
    .summary-card .label { font-size: 10px; color: #64748b; font-weight: 600; text-transform: uppercase; }
    .summary-card .val { font-size: 14px; font-weight: 800; margin-top: 2px; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    th { background: #f1f5f9; border: 1px solid #cbd5e1; padding: 6px 8px; font-weight: 700; text-align: left; }
    td { border: 1px solid #e2e8f0; padding: 5px 8px; }
    tr:nth-child(even) { background: #fafafa; }
    .footer-total { background: #f8fafc; font-weight: 800; border-top: 2px solid #0f172a; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="title">${compName} — Sotuvlar hisoboti</div>
      <div class="subtitle">Sana oralig'i: <b>${dateFrom}</b> dan <b>${dateTo}</b> gacha &bull; Jami sotuvlar soni: <b>${sales.length} ta</b></div>
    </div>
    <div style="text-align:right;font-size:10px;color:#64748b;">
      Chop etilgan vaqt: ${new Date().toLocaleString('uz-UZ')}<br>
      E-Code ERP tizimi
    </div>
  </div>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="label">Jami sotuvlar</div>
      <div class="val" style="color:#0f172a;">${sales.length} ta</div>
    </div>
    <div class="summary-card">
      <div class="label">Umumiy summa</div>
      <div class="val" style="color:#2563eb;">${fmt(sumTotal)} so'm</div>
    </div>
    <div class="summary-card">
      <div class="label">Jami to'langan</div>
      <div class="val" style="color:#059669;">${fmt(sumPaid)} so'm</div>
    </div>
    <div class="summary-card">
      <div class="label">Jami qarz</div>
      <div class="val" style="color:#dc2626;">${fmt(sumDebt)} so'm</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:30px;text-align:center;">#</th>
        <th style="width:110px;">Raqam</th>
        <th>Mijoz</th>
        <th style="text-align:right;width:110px;">Jami</th>
        <th style="text-align:right;width:100px;">To'langan</th>
        <th style="text-align:right;width:100px;">Qarz</th>
        <th style="text-align:center;width:90px;">To'lov turi</th>
        <th style="text-align:center;width:100px;">Holati</th>
        <th style="width:100px;">Kassir</th>
        <th style="text-align:center;width:110px;">Sana</th>
      </tr>
    </thead>
    <tbody>
      ${rowsHtml}
    </tbody>
    <tfoot>
      <tr class="footer-total">
        <td colspan="3" style="text-align:right;padding:8px;">JAMI:</td>
        <td style="text-align:right;color:#2563eb;padding:8px;">${fmt(sumTotal)} s</td>
        <td style="text-align:right;color:#059669;padding:8px;">${fmt(sumPaid)} s</td>
        <td style="text-align:right;color:#dc2626;padding:8px;">${fmt(sumDebt)} s</td>
        <td colspan="4"></td>
      </tr>
    </tfoot>
  </table>
</body>
</html>`;

        const win = window.open('', '_blank');
        if (win) {
          win.document.open();
          win.document.write(html);
          win.document.close();
          setTimeout(() => { try { win.focus(); win.print(); } catch (e) { console.warn(e); } }, 400);
          toast.success("Hisobot chop etish oynasi ochildi");
        } else {
          printReceiptHtml(html);
        }
      } catch (fallbackErr) {
        console.error('Fallback error:', fallbackErr);
        toast.error("PDF yaratishda xatolik yuz berdi");
      }
    }
  };

  // ── Bitta sotuv tovarlarini Excel (.xlsx) ga eksport qilish ─────────────
  const exportSingleSaleToExcel = async (s) => {
    try {
      let data = s;
      if (!s.items) {
        const r = await api.get(`/sales/${s.id}`);
        data = r.data;
      }
      const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
      const items = data.items || [];
      const rows = items.map((it, idx) => ({
        "№": idx + 1,
        "Mahsulot": it.product_name || '—',
        "Miqdor": Number(it.quantity || 0),
        "Birlik": it.unit || 'dona',
        "Narx (so'm)": Number(it.unit_price || 0),
        "Chegirma (so'm)": Number(it.discount || 0),
        "Jami summa (so'm)": Number(it.subtotal || 0),
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      ws['!cols'] = [
        { wch: 6 },
        { wch: 30 },
        { wch: 12 },
        { wch: 10 },
        { wch: 16 },
        { wch: 16 },
        { wch: 18 },
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Tovarlar');
      saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `nakladnoy_${data.number || data.id}.xlsx`);
      toast.success(t('wholesale.excelExportSuccess') || "Excel fayl muvaffaqiyatli yuklab olindi");
    } catch (e) {
      console.error(e);
      toast.error("Excel yuklab olishda xatolik");
    }
  };

  // ── Savatchadagi tovarlarni Excel ga eksport qilish ────────────────────
  const exportCartToExcel = async () => {
    if (!cart.length) return;
    try {
      const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
      const rows = cart.map((it, idx) => ({
        "№": idx + 1,
        "Mahsulot": it.name || '—',
        "Miqdor": Number(it.qty || 0),
        "Birlik": it.unit || 'dona',
        "Narx (so'm)": Number(it.price || 0),
        "Chegirma (so'm)": it.discount_type === 'pct' ? Number(it.price * it.qty * (parseN(it.discount_val) / 100)) : Number(parseN(it.discount_val)),
        "Jami (so'm)": Number(itemNet(it) || 0),
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Savatcha');
      saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `sotuv_savatcha_${today()}.xlsx`);
      toast.success(t('wholesale.excelExportSuccess') || "Excel fayl yuklab olindi");
    } catch (e) {
      console.error(e);
      toast.error("Excel yuklab olishda xatolik");
    }
  };

  // Valyuta kursi olish yordamchisi
  const getRate = useCallback((code) => {
    if (!code || String(code).toUpperCase() === 'UZS') return 1;
    const cur = currencies.find(c => String(c.code).toUpperCase() === String(code).toUpperCase());
    return cur ? (parseFloat(cur.rate) || 1) : 1;
  }, [currencies]);

  // Mijoz narx turiga qarab mahsulot narxini olish
  const getProductPrice = useCallback((p, custOverride) => {
    // T3.19: mijozning individual narxi (customer_prices) — eng yuqori ustuvorlik
    const cp = custPricesRef.current[p.id];
    if (cp != null && Number(cp) > 0) return { price: Number(cp), currency: 'UZS' };
    if (isWholesaleMode && p.wholesale_price) {
      return { price: Number(p.wholesale_price), currency: p.wholesale_currency || p.sale_currency || 'UZS' };
    }
    // Default: sale (chakana)
    return { price: Number(p.sale_price || 0), currency: p.sale_currency || 'UZS' };
  }, [isWholesaleMode]);

  // Aksiya chegirmasini topish (product_id bo'yicha)
  const getPromoDiscount = useCallback((productId, basePrice) => {
    const now = new Date();
    const activePrs = promotions.filter(pr => {
      if (!pr.is_active) return false;
      if (pr.start_date && new Date(pr.start_date) > now) return false;
      if (pr.end_date) {
        // T4.3: sana ko'rinishidagi (00:00) tugash kuni kun oxirigacha amal qiladi (server bilan bir xil)
        const end = new Date(pr.end_date);
        if (end.getHours() === 0 && end.getMinutes() === 0 && end.getSeconds() === 0) end.setDate(end.getDate() + 1);
        if (end < now) return false;
      }
      // T3.19: qamrov aniq — "all" (yoki applies_to yo'q eski javobda mahsulotsiz) universal;
      // aks holda faqat tanlangan mahsulotlar. PromotionProduct.id (pp.id) mahsulot ID'si emas.
      if (pr.applies_to === 'all') return true;
      if (!pr.applies_to && (!pr.products || pr.products.length === 0)) return true;
      return (pr.products || []).some(pp => pp.product_id === productId);
    });
    if (!activePrs.length) return { discount: 0, promo: null };
    // Eng katta chegirmani olish
    let bestDiscount = 0;
    let bestPromo = null;
    for (const pr of activePrs) {
      let disc = pr.discount_type === 'percent'
        ? basePrice * (Number(pr.discount_value) / 100)
        : Number(pr.discount_value);
      // Summa turidagi chegirma asos narxdan oshib ketmasin
      disc = Math.min(disc, basePrice);
      if (disc > bestDiscount) { bestDiscount = disc; bestPromo = pr; }
    }
    return { discount: bestDiscount, promo: bestPromo };
  }, [promotions]);

  // T3.19: mijozning doimiy chegirma foizi (aksiya chegirmasi bo'lmaganda qatorga oldindan qo'yiladi)
  const custDiscountPct = () => {
    const c = customersRef.current.find(x => String(x.id) === String(custIdRef.current));
    const v = Number(c?.discount_percent) || 0;
    return v > 0 ? v : 0;
  };

  // D2.6: analoglar (GET /products/{id}/analogs); `auto` — qoldiq 0 bo'lganda o'zi ochiladi (analog topilmasa jim yopiladi)
  const openAnalogs = useCallback((p, auto = false) => {
    const pid = p.id ?? p.product_id;
    const name = p.name ?? p.product_name;
    setAnalogModal({ product_id: pid, name, loading: true, items: [], auto });
    api.get(`/products/${pid}/analogs`, { _silent: true, _suppressToast: true })
      .then(r => {
        const items = Array.isArray(r.data) ? r.data : [];
        setAnalogModal(m => (m && m.product_id === pid ? (auto && !items.length ? null : { ...m, loading: false, items }) : m));
      })
      .catch(() => setAnalogModal(m => (m && m.product_id === pid ? (auto ? null : { ...m, loading: false, items: [], error: true }) : m)));
  }, []);

  const addToCart = useCallback((p) => {
    // Parent mahsulot (variantli) bo'lsa — variant picker modal ochiladi
    if (p.product_type === 'parent') {
      setVariantPickerProduct(p);
      return;
    }
    const currentCustId = custIdRef.current;
    if (!currentCustId && !pharmaRef.current.pharmacy) {   // dorixonada mijoz ixtiyoriy
      toast.error(t('sale.mustSelectCustomer'));
      return;
    }
    // D2.6: dorixona — birlik shtrix-kodi skanerlansa birlik o'zi tanlanadi; qoldiq 0 bo'lsa analoglar taklif qilinadi
    const isPharma = pharmaRef.current.pharmacy;
    let scanUnit = isPharma && p._scanUnit && (Number(p._scanUnit.ratio) || 1) !== 1 ? p._scanUnit : null;
    if (scanUnit && p.pack_ratio != null && Number(scanUnit.ratio) >= Number(p.pack_ratio) && p.full_boxes != null && Number(p.full_boxes) < 1) {
      toast.warn(tfRef.current('pos.wholeBoxNone', "Omborda butun quti yo'q (ochilgan qutida {loose} dona). Dona qilib soting.", { loose: p.loose_units ?? 0 }));
      scanUnit = null;
    }
    if (isPharma && !p._noAnalogs && Number(p.stock_quantity) <= 0 && (p.product_type || 'stock') === 'stock') openAnalogs(p, true);
    // Mijoz narx turiga qarab narxni olish
    let { price, currency } = getProductPrice(p);
    let rate = getRate(currency);
    let basePrice = price;   // D2.6: asosiy birlikdagi narx (birlik almashtirganda asos)
    if (scanUnit) price = currency === 'UZS' ? unitLinePrice(price, p.sale_price, scanUnit) : price * (Number(scanUnit.ratio) || 1);

    if (onlySom && currency !== 'UZS') {
      basePrice = basePrice * rate;
      price = price * rate;
      currency = 'UZS';
      rate = 1;
    }

    // Aksiya chegirmasini tekshirish
    const { discount: promoDisc, promo } = getPromoDiscount(p.id, price);

    setCart(prev => {
      const unitKey = scanUnit ? scanUnit.id : null;
      const ex = prev.find(i => i.product_id === p.id && (i.unit_id || null) === unitKey);
      if (ex) {
        return prev.map(i => i === ex
          ? { ...i, qty: i.qty + 1 }
          : i);
      }
      return [...prev, {
        ...(isPharma ? { ...pharmaFieldsOf(p, scanUnit), base_price: basePrice } : {}),
        product_id: p.id, name: p.name, sku: p.sku || '', unit: p.unit || 'dona', qty: 1, price,
        currency, rate,
        discount_type: promoDisc > 0 ? 'sum' : 'pct',
        discount_val: promoDisc > 0 ? promoDisc : custDiscountPct(),
        promo_name: promo?.name || null,
        promo_id: promo?.id || null,
        wholesale_price: (onlySom && p.sale_currency !== 'UZS') ? Number(p.wholesale_price || 0) * getRate(p.sale_currency) : Number(p.wholesale_price || 0),
        sale_price: (onlySom && p.sale_currency !== 'UZS') ? Number(p.sale_price || 0) * getRate(p.sale_currency) : Number(p.sale_price || 0),
        cost_price: Number(p.cost_price || 0),
        stock_quantity: Number(p.stock_quantity || 0), image_url: p.image_url,
        mxik_code:    p.mxik_code    || '',
        package_code: p.parent_code || p.package_code || '',
        barcode:      p.barcode      || '',
        labels:       p.labels       || [],
        requires_marking: !!p.requires_marking,
        marking_codes: [],
        vat_rate_type: p.vat_rate_type || 'nds_12',
        addedAt: Date.now(),
      }];
    });
    if (promo) toast.success(t('wholesale.promoAppliedName', { name: promo.name }), { duration: 2000 });
  }, [getProductPrice, getPromoDiscount, getRate, onlySom, openAnalogs]);

  const updateItem = useCallback((idx, field, val) => setCart(prev => prev.map((it, i) => {
    if (i !== idx) return it;
    const next = { ...it, [field]: val };
    // Miqdor kamaytirilganda ortiqcha skanerlangan markirovka kodlarini kesib tashlaymiz
    if (field === 'qty' && next.requires_marking && (next.marking_codes || []).length > Number(val)) {
      next.marking_codes = next.marking_codes.slice(0, Math.floor(Number(val)) || 0);
    }
    // D2.6: butun quti sotuvida miqdor ombordagi butun qutilar sonidan oshmasin (server ham 400 qaytaradi)
    if (field === 'qty') {
      const wbMax = wholeBoxMax(next);
      if (wbMax != null && Number(val) > wbMax) {
        next.qty = Math.max(wbMax, 1);
        toast.warn(tfRef.current('pos.wholeBoxMax', "Omborda butun quti {boxes} ta (ochilgan qutida {loose} dona). Ko'proq kerak bo'lsa dona qilib soting.", {
          boxes: next.full_boxes, loose: next.loose_units ?? 0,
        }));
      }
    }
    // Chegirma [0, narx x miqdor] (pct uchun [0, 100]) oralig'ida bo'lishi
    // shart - aks holda manfiy summali sotuv bazaga yozilishi mumkin edi.
    if (field === 'discount_val' || field === 'qty' || field === 'price' || field === 'discount_type') {
      const maxDisc = next.discount_type === 'pct' ? 100 : (Number(next.price) || 0) * (Number(next.qty) || 0);
      next.discount_val = Math.min(maxDisc, Math.max(0, Number(next.discount_val) || 0));
    }
    return next;
  })), []);
  const removeItem = useCallback((idx) => setCart(prev => prev.filter((_, i) => i !== idx)), []);

  // D2.6: savat qatorida birlikni almashtirish (quti <-> blister <-> dona) — narx qayta hisoblanadi, miqdor imkon bo'lsa saqlanadi
  const switchUnit = useCallback((idx, unitIdRaw) => setCart(prev => {
    const it = prev[idx];
    if (!it) return prev;
    const unit = unitIdRaw ? (it.units || []).find(u => String(u.id) === String(unitIdRaw)) || null : null;
    if ((it.unit_id || null) === (unit ? unit.id : null)) return prev;
    const oldRatio = it.unit_ratio || 1;
    const newRatio = unit ? Number(unit.ratio) || 1 : 1;
    const basePrice = Number(lineBasePrice(it)) || 0;
    const q = (it.qty * oldRatio) / newRatio;
    const nextItem = {
      ...it,
      unit_id: unit ? unit.id : null,
      unit_name: unit ? unit.name : null,
      unit_ratio: newRatio,
      price: unitLinePrice(basePrice, it.sale_price, unit),
      base_price: basePrice,
      qty: Number.isInteger(q) && q >= 1 ? q : 1,
    };
    const wbMax = wholeBoxMax(nextItem);
    if (wbMax === 0) {
      toast.warn(tfRef.current('pos.wholeBoxNone', "Omborda butun quti yo'q (ochilgan qutida {loose} dona). Dona qilib soting.", { loose: it.loose_units ?? 0 }));
      return prev;
    }
    if (wbMax != null && nextItem.qty > wbMax) nextItem.qty = wbMax;
    if (nextItem.discount_type !== 'pct') nextItem.discount_val = Math.min(parseN(nextItem.discount_val), nextItem.price * nextItem.qty);
    if (nextItem.requires_marking && (nextItem.marking_codes || []).length > nextItem.qty) {
      nextItem.marking_codes = nextItem.marking_codes.slice(0, Math.floor(nextItem.qty) || 0);
    }
    return prev.map((x, i) => (i === idx ? nextItem : x));
  }), []);

  const addAnalogToCart = (a) => {
    addToCart({
      id: a.id, name: a.name, barcode: a.barcode, unit: a.unit, sale_price: a.sale_price, sale_currency: a.sale_currency || 'UZS',
      stock_quantity: a.stock_quantity, nearest_expiry: a.nearest_expiry, expiry_warn: a.expiry_warn,
      is_rx: a.is_rx, control_class: a.control_class, _noAnalogs: true,
    });
    setAnalogModal(null);
  };

  // Markirovka (Data Matrix) kod skanerlash — savat qatoriga kod qo'shish/o'chirish
  const [markingModal, setMarkingModal] = useState(null); // { idx }

  const addMarkingCode = useCallback((idx, code) => {
    const trimmed = (code || '').trim();
    if (!trimmed) return;
    setCart(prev => {
      const item = prev[idx];
      if (!item) return prev;
      const codes = [...(item.marking_codes || [])];
      if (codes.includes(trimmed)) {
        toast.error(t('wholesale.markingCodeAlreadyScanned'));
        return prev;
      }
      if (codes.length >= item.qty) {
        toast.error(t('wholesale.enoughCodesForQty', { qty: item.qty }));
        return prev;
      }
      codes.push(trimmed);
      return prev.map((it, i) => i === idx ? { ...it, marking_codes: codes } : it);
    });
  }, []);

  const removeMarkingCode = useCallback((idx, codeIdx) => {
    setCart(prev => prev.map((it, i) => i === idx
      ? { ...it, marking_codes: (it.marking_codes || []).filter((_, ci) => ci !== codeIdx) }
      : it));
  }, []);

  // Select product into form — mijoz narx turiga qarab narxni ko'rsatadi
  const selectFormProduct = useCallback((p) => {
    // Parent mahsulot bo'lsa — variant picker ochiladi
    if (p.product_type === 'parent') {
      setVariantPickerProduct(p);
      return;
    }
    setFormProduct(p);
    let { price, currency } = getProductPrice(p);

    if (onlySom && currency !== 'UZS') {
      const rate = getRate(currency);
      price = price * rate;
      currency = 'UZS';
    }

    // Aksiya chegirmasini avtomatik qo'llash
    const { discount: promoDisc, promo } = getPromoDiscount(p.id, price);
    setFormPromoId(promoDisc > 0 && promo ? promo.id : null);
    if (promoDisc > 0) {
      setFormDiscType('sum');
      setFormDiscVal(String(Math.round(promoDisc)));
      toast.success(t('wholesale.promoApplied', { name: promo.name, amount: Math.round(promoDisc).toLocaleString() }), { duration: 2500 });
    } else {
      const cpct = custDiscountPct();
      setFormDiscType('pct');
      setFormDiscVal(cpct > 0 ? String(cpct) : '');
    }

    setFormPrice(String(price));
    setFormCurrency(currency);
    setFormQty('1');
    setFormTotalEdit(null);
    setTimeout(() => {
      if (formQtyRef.current) {
        formQtyRef.current.focus();
        formQtyRef.current.select();
      }
    }, 100);
  }, [getProductPrice, getPromoDiscount, onlySom, getRate]);


  // Mijoz o'zgarganda form narxini yangilash
  useEffect(() => {
    if (formProduct) {
      const { price } = getProductPrice(formProduct);
      setFormPrice(String(price));
    }
  }, [custId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Savatdagi qator summasi bilan bir xil formula: narx × miqdor − chegirma
  const formTotalKey = `${formQty}|${formPrice}|${formDiscType}|${formDiscVal}`;
  const formComputedTotal = (() => {
    const gross = (parseFloat(formPrice) || 0) * (parseFloat(formQty) || 0);
    const disc = formDiscType === 'pct' ? gross * ((parseFloat(formDiscVal) || 0) / 100) : (parseFloat(formDiscVal) || 0);
    return Math.max(0, Math.round((gross - disc) * 100) / 100);
  })();
  const formTotalText = formTotalEdit && formTotalEdit.key === formTotalKey ? formTotalEdit.text : String(formComputedTotal || '');

  // Jami summa kiritilsa — miqdor = summa / narx (chegirma hisobga olinadi), 3 xonagacha
  const onFormTotalChange = (raw) => {
    const text = parsePrice(raw);
    const total = parseFloat(text) || 0;
    const price = parseFloat(formPrice) || 0;
    const discVal = parseFloat(formDiscVal) || 0;
    let qty = formQty;
    if (price > 0 && total > 0) {
      const q = formDiscType === 'pct'
        ? total / (price * Math.max(0.0001, 1 - discVal / 100))
        : (total + discVal) / price;
      qty = String(round3(q));
    }
    setFormQty(qty);
    setFormTotalEdit({ key: `${qty}|${formPrice}|${formDiscType}|${formDiscVal}`, text });
  };

  const addFormToCart = () => {
    if (!custId && !pharmacy) return toast.error(t('sale.mustSelectCustomer'));
    if (!formProduct) return toast.error(t('wholesale.productNotSelected'));
    const price = parseFloat(formPrice) || 0;
    const qty = parseFloat(formQty) || 1;
    if (qty <= 0) return toast.error(t('wholesale.qtyMustBePositive'));

    const currency = formCurrency || 'UZS';
    const rate = getRate(currency);

    // D2.6: qoldiq 0 bo'lgan dorida analoglar avtomatik taklif qilinadi
    if (pharmacy && Number(formProduct.stock_quantity) <= 0 && (formProduct.product_type || 'stock') === 'stock') openAnalogs(formProduct, true);
    setCart(prev => {
      const ex = prev.find(i => i.product_id === formProduct.id && !i.unit_id);
      if (ex) return prev.map(i => i === ex
        ? { ...i, qty: i.qty + qty, price, currency, rate, discount_type: formDiscType, discount_val: parseFloat(formDiscVal) || 0 }
        : i);
      return [...prev, {
        ...(pharmacy ? pharmaFieldsOf(formProduct, null) : {}),
        product_id: formProduct.id, name: formProduct.name, unit: formProduct.unit || 'dona',
        qty, price, currency, rate, discount_type: formDiscType, discount_val: parseFloat(formDiscVal) || 0,
        promo_id: formPromoId || null,
        wholesale_price: (onlySom && formProduct.sale_currency !== 'UZS') ? Number(formProduct.wholesale_price || 0) * getRate(formProduct.sale_currency) : Number(formProduct.wholesale_price || 0),
        sale_price: (onlySom && formProduct.sale_currency !== 'UZS') ? Number(formProduct.sale_price || 0) * getRate(formProduct.sale_currency) : Number(formProduct.sale_price || 0),
        stock_quantity: Number(formProduct.stock_quantity || 0), image_url: formProduct.image_url,
        // Fiskal maydonlar
        mxik_code:    formProduct.mxik_code    || '',
        package_code: formProduct.parent_code || formProduct.package_code || '',
        barcode:      formProduct.barcode      || '',
        labels:       formProduct.labels       || [],
        requires_marking: !!formProduct.requires_marking,
        marking_codes: [],
        vat_rate_type: formProduct.vat_rate_type || 'nds_12',
        addedAt: Date.now(),
      }];
    });
    setFormProduct(null); setFormPrice(''); setFormQty('1'); setFormDiscVal(''); setFormCurrency('UZS'); setFormTotalEdit(null); setFormPromoId(null);
    prodSearchRef.current?.focus();
    // switch to cart tab on mobile to show the result
    setMobileTab('cart');
    setTimeout(() => setMobileTab('form'), 300); // bounce back after brief show
  };

  // Refs update every render
  customersRef.current = customers;
  setCustIdRef.current = setCustId;
  addToCartRef.current = addToCart;

  // D2.6: dorixona — QR (Data Matrix) kodi skanerlandi: dori GTIN bo'yicha topiladi (pos-list, shtrix-kod).
  // Seriyali kod (markirovka): bitta kod = bitta quti (omborda butun quti bo'lsa), kod shu qatorga yoziladi
  const addByGs1 = async (gs1) => {
    let prod = null;
    for (const code of gtinVariants(gs1.gtin)) {
      try {
        const pr = await api.get('/products/pos-list', {
          params: { search: code, limit: 5, warehouse_id: pharmaRef.current.warehouseId || undefined },
          _silent: true, _suppressToast: true,
        });
        const rows = Array.isArray(pr.data) ? pr.data : (pr.data?.items || []);
        prod = rows.find(x => productMatchesGtin(x, gs1.gtin)) || null;
      } catch { /* shtrix-kod bo'yicha urinamiz */ }
      if (!prod) {
        try {
          const r = await api.get(`/products/barcode/${encodeURIComponent(code)}`, { _silent: true, _suppressToast: true });
          if (r.data?.id) prod = r.data;
        } catch { /* keyingi variant */ }
      }
      if (prod) break;
    }
    if (!prod) { toast.error(t('wholesale.productNotFoundCode', { code: gs1.gtin })); return; }
    if (!gs1.serial) { addToCartRef.current({ ...prod, _scanUnit: defaultScanUnit(prod) }); return; }
    if (cartRef.current.some(it => (it.marking_codes || []).includes(gs1.code))) { toast.error(t('wholesale.markingCodeAlreadyScanned')); return; }
    const box = (Array.isArray(prod.units) ? prod.units : [])
      .filter(u => (Number(u.ratio) || 1) > 1).sort((a, b) => Number(b.ratio) - Number(a.ratio))[0] || null;
    const unit = box && !(prod.pack_ratio != null && prod.full_boxes != null && Number(prod.full_boxes) < 1) ? box : null;
    const same = (it) => it.product_id === prod.id && (it.unit_id || null) === (unit ? unit.id : null);
    const open = (it) => same(it) && (it.marking_codes || []).length < it.qty;
    if (!cartRef.current.some(open)) addToCartRef.current({ ...prod, _scanUnit: unit });
    setCart(prev => {
      const idx = prev.findIndex(open);
      return idx < 0 ? prev : prev.map((it, i) => (i === idx ? { ...it, marking_codes: [...(it.marking_codes || []), gs1.code] } : it));
    });
  };
  const addByGs1Ref = useRef(null);
  addByGs1Ref.current = addByGs1;
  pharmaRef.current = { pharmacy, warehouseId };

  // Global barcode scanner
  useEffect(() => {
    const gsKey = createGsDetector();
    const handle = (e) => {
      // Dorixona: Data Matrix ajratgichi (GS) buferda saqlanadi, Alt+raqamlar kodga yozilmaydi
      const gsAct = pharmaRef.current.pharmacy ? gsKey(e) : null;
      if (gsAct === 'gs') { scanBufRef.current += GS; return; }
      if (gsAct === 'skip' || e.type === 'keyup') return;
      const now = Date.now(); const gap = now - scanTimeRef.current; scanTimeRef.current = now;
      // Raqam maydonlari (miqdor, narx, jami summa, chegirma, to'lov) — tez yozilgan raqam + Enter
      // skaner deb ushlanib, maydon tozalanib qolmasin
      if (e.target?.closest?.('[data-no-scan]')) { scanBufRef.current = ''; return; }
      if (e.key === 'Enter') {
        const buf = scanBufRef.current.trim(); scanBufRef.current = '';
        if (buf.length < 3) return;
        e.preventDefault();
        e.stopPropagation();
        const active = document.activeElement;
        if (active && active.tagName === 'INPUT') { active.value = ''; active.dispatchEvent(new Event('input', { bubbles: true })); }

        toast.info(t('wholesale.scanned', { code: buf }), { autoClose: 1500 });

        const cust = customersRef.current.find(c => c.phone && (c.phone === buf || c.phone.replace(/\D/g, '') === buf.replace(/\D/g, '')));
        if (cust) { setCustIdRef.current(String(cust.id)); toast.success(t('wholesale.customerSelected', { name: cust.name })); return; }

        const gs1 = pharmaRef.current.pharmacy ? parseGs1Scan(buf) : null;
        if (gs1) { addByGs1Ref.current(gs1); return; }

        let searchCode = buf;
        let weightQty = 1;

        if (buf.length === 13 && (buf.startsWith('20') || buf.startsWith('21') || buf.startsWith('22'))) {
          searchCode = buf.substring(2, 7);
          const weightGram = parseInt(buf.substring(7, 12), 10) || 0;
          weightQty = weightGram / 1000;
        }

        const fetchProduct = async () => {
           // D2.6: dorixona — pos-list (birlik shtrix-kodi `scanned_unit_id`, muddat, retsept maydonlari bilan)
           if (pharmaRef.current.pharmacy) {
             try {
               const pr = await api.get('/products/pos-list', {
                 params: { search: searchCode, limit: 5, warehouse_id: pharmaRef.current.warehouseId || undefined },
                 _silent: true, _suppressToast: true,
               });
               const rows = Array.isArray(pr.data) ? pr.data : (pr.data?.items || []);
               const hit = rows.find(x => x.scanned_unit_id != null) || rows.find(x => x.barcode === searchCode || x.sku === searchCode);
               if (hit) {
                 if (hit.scanned_unit_id != null) hit._scanUnit = (hit.units || []).find(u => u.id === hit.scanned_unit_id) || null;
                 return hit;
               }
             } catch { /* oddiy oqimga o'tamiz */ }
           }
           try {
             // 1-urinish: shtrixkod bo'yicha qidirish
             const r = await api.get(`/products/barcode/${encodeURIComponent(searchCode)}`);
             if (r.data?.id) return r.data;
           } catch (e) {
             // 2-urinish: Agar barkoddan topilmasa, SKU yoki ismidan qidirib ko'rish (umumiy qidiruv)
             try {
                const res = await api.get('/products', { params: { search: searchCode, limit: 1 } });
                if (res.data && res.data.length > 0) {
                   const p = res.data[0];
                   if (p.barcode === searchCode || p.sku === searchCode || String(p.id) === searchCode) {
                       return p;
                   }
                }
             } catch (err) {
                // Hech qayerdan topilmadi
             }
             
             // 3-urinish: Tarozi barkodi bo'lsa va ID ga teng bo'lishi ehtimoli bo'lsa
             if (weightQty !== 1 && searchCode.match(/^\d+$/)) {
               try {
                  const searchId = parseInt(searchCode, 10);
                  const res = await api.get(`/products/${searchId}`);
                  if (res.data?.id) return res.data;
               } catch (err) { }
             }
           }
           return null;
        };

        fetchProduct().then(prod => {
          if (prod) {
            if (weightQty !== 1) prod.qty_ordered = weightQty;
            // D2.6: dorixona — asosiy shtrix-kod skanerlansa eng katta mavjud birlik (quti -> blister -> dona)
            if (pharmaRef.current.pharmacy && !prod._scanUnit && weightQty === 1) prod._scanUnit = defaultScanUnit(prod);
            addToCartRef.current(prod);
          } else {
            const el = document.activeElement;
            if (el?.tagName === 'INPUT' && el.value.includes(buf)) {
              el.value = el.value.replace(buf, '').trim();
            }
            toast.error(t('wholesale.productNotFoundCode', { code: searchCode }));
          }
        });
      } else if (e.key.length === 1) {
        if (gap > 500) scanBufRef.current = e.key; else scanBufRef.current += e.key;
      }
    };
    window.addEventListener('keydown', handle, true);
    window.addEventListener('keyup', handle, true);
    return () => { window.removeEventListener('keydown', handle, true); window.removeEventListener('keyup', handle, true); };
  }, []);

  const itemNet = useCallback((it) => {
    const gross = it.price * it.qty;
    const disc = it.discount_type === 'pct' ? gross * (parseN(it.discount_val) / 100) : parseN(it.discount_val);
    return Math.max(0, gross - disc);
  }, []);
  const itemNetUZS = useCallback((it) => itemNet(it) * (it.rate || 1), [itemNet]);

  const subtotal = useMemo(() => cart.reduce((s, it) => s + itemNetUZS(it), 0), [cart, itemNetUZS]);

  // Valyuta bo'yicha jami summalarni hisoblash
  const totalsByCurrency = useMemo(() => cart.reduce((acc, it) => {
    const cur = it.currency || 'UZS';
    acc[cur] = (acc[cur] || 0) + itemNet(it);
    return acc;
  }, {}), [cart, itemNet]);

  const saleDisc = useMemo(() => discType === 'pct' ? subtotal * (parseN(discVal) / 100) : parseN(discVal), [discType, discVal, subtotal]);
  const total = useMemo(() => Math.max(0, subtotal - saleDisc), [subtotal, saleDisc]);

  const getPaidUZS = (paymentList) => {
    return paymentList.reduce((s, p) => {
      const rate = getRate(p.currency || 'UZS');
      return s + (parseN(p.amt) * rate);
    }, 0);
  };

  const paid = getPaidUZS(payments);
  const debt = Math.max(0, total - paid);

  const submitSale = async (overridePayType, pPaid = 0, pCash = 0, pCard = 0) => {
    if (!cart.length) return toast.error(t('sale.emptyCart'));
    // Dorixonada mijozsiz sotiladi, lekin qarzga emas (server ham qarz uchun mijoz talab qiladi)
    if (!custId && (!pharmacy || pPaid + 0.01 < total)) return toast.error(t(pharmacy ? 'wholesale.selectCustomerForDebtSale' : 'wholesale.customerNotSelectedFull'));
    // Dorixonada markirovka majburiy emas: skanerlangan kodlar yuboriladi, kodsiz ham sotiladi
    const incompleteMarking = !pharmacy && cart.find(it => it.requires_marking && (it.marking_codes || []).length < it.qty);
    if (incompleteMarking) {
      toast.error(t('wholesale.markingIncomplete', { name: incompleteMarking.name, done: (incompleteMarking.marking_codes || []).length, qty: incompleteMarking.qty }));
      setMarkingModal({ idx: cart.indexOf(incompleteMarking) });
      return;
    }
    // D2.6: retseptli / nazoratdagi dori — retsept ma'lumoti kiritilmaguncha sotuv yuborilmaydi (server D2.5 ham tekshiradi)
    if (pharmacy && rxProductsOf(cart).length && validateRx(cart, rxData, rxReason, rxMode)) {
      setShowPayment(false);
      setRxModal({ proceed: false });
      return;
    }
    // T3.18: click/payme/uzum to'lovida terminal talab qilsa tranzaksiya raqami majburiy
    const missingRef = payments.find(p => parseN(p.amt) > 0 && referenceRequired(p) && !String(p.reference || '').trim());
    if (missingRef) return toast.error(tfb('pos.referenceRequired', 'Tranzaksiya raqamini kiriting'));
    setSaving(true);
    try {
      const items = cart.map(it => {
        const disc = it.discount_type === 'pct'
          ? it.price * it.qty * (parseN(it.discount_val) / 100)
          : parseN(it.discount_val);
        return {
          product_id: it.product_id, quantity: it.qty, unit_price: it.price,
          price_manual: isPriceManual(it),
          discount: disc,
          promotion_id: (it.promo_id && disc > 0) ? it.promo_id : undefined,   // T4.3: server tekshiradi, qo'shimcha chegirma qo'shmaydi
          variant_id: it.variant_id || undefined,
          warehouse_id: it.warehouse_id || undefined,
          currency_code: it.currency || 'UZS',
          exchange_rate: it.rate || 1,
          marking_codes: it.marking_codes && it.marking_codes.length ? it.marking_codes : undefined,
          // D2.6: qadoq birligi (quti/blister) — miqdor shu birlikda; asosiy birlik uchun yuborilmaydi
          unit_id: pharmacy && it.unit_id ? it.unit_id : undefined,
        };
      });
      // To'lovlarni ham valyutasi bilan yuboramiz
      const paymentsList = payments.filter(p => parseN(p.amt) > 0).map(p => ({
        type: p.type,
        amount: parseN(p.amt),
        currency: p.currency || 'UZS',
        rate: getRate(p.currency),
        // T3.18: provayder tranzaksiya raqami va terminal (faqat click/payme/uzum)
        ...(REF_PROVIDERS.includes(p.type) && String(p.reference || '').trim() ? { reference: String(p.reference).trim() } : {}),
        ...(REF_PROVIDERS.includes(p.type) && p.terminal_id ? { terminal_id: Number(p.terminal_id) } : {}),
      }));
      // Haqiqiy qarzni valyutalar kesimida hisoblash
      const actualDebts = {};

      if (overridePayType === 'debt' && pPaid === 0) {
        // To'liq qarzga berilsa (qarz tugmasi orqali)
        Object.assign(actualDebts, totalsByCurrency);
      } else {
        const remain = { ...totalsByCurrency };
        let overpaidUZS = 0;

        // 1. To'lovlarni mos valyutadan ayiramiz
        for (const p of payments) {
          const a = parseN(p.amt);
          if (a <= 0 || p.type === 'debt') continue; // Qarz line bo'lsa hisoblanmaydi
          const c = p.currency || 'UZS';
          if (!remain[c]) remain[c] = 0;
          remain[c] -= a;
        }

        // 2. Ortib qolgan (manfiy) to'lovlarni UZS ga o'tkazib yig'amiz
        for (const c in remain) {
          if (remain[c] < -0.001) {
            overpaidUZS += Math.abs(remain[c]) * getRate(c);
            delete remain[c];
          }
        }

        // 3. Qolgan (musbat) qarzlarni overpaid UZS dan uzamiz
        for (const c in remain) {
          if (remain[c] > 0.001 && overpaidUZS > 0.001) {
            const needUZS = remain[c] * getRate(c);
            if (overpaidUZS >= needUZS) {
              overpaidUZS -= needUZS;
              delete remain[c];
            } else {
              remain[c] -= overpaidUZS / getRate(c);
              overpaidUZS = 0;
            }
          }
        }

        // 4. Haqiqatan ham qarz bo'lib qolgan summalarni kiritamiz
        for (const c in remain) {
          if (remain[c] > 0.01) actualDebts[c] = Number(remain[c].toFixed(2));
        }
      }

      // Find the primary currency of the sale
      const primaryItem = cart.find(it => it.currency && it.currency !== 'UZS');
      const primaryPayment = payments.find(p => p.currency && p.currency !== 'UZS');
      const primaryCurrencyCode = primaryItem ? primaryItem.currency : (primaryPayment ? primaryPayment.currency : 'UZS');

      const primaryCurrencyObj = currencies.find(c => String(c.code).toUpperCase() === String(primaryCurrencyCode).toUpperCase());
      const currencyId = primaryCurrencyObj ? primaryCurrencyObj.id : undefined;

      const payload = {
        items, payment_type: overridePayType, paid_amount: pPaid, paid_cash: pCash, paid_card: pCard,
        status: 'completed',
        discount_amount: saleDisc, note: note || payNote || undefined,
        customer_id: custId ? Number(custId) : undefined,
        warehouse_id: warehouseId ? Number(warehouseId) : undefined,
        debt_due_date: overridePayType === 'debt' && debtDate ? debtDate : undefined,
        payments: paymentsList.length > 0 ? paymentsList : undefined,
        currency_totals: Object.keys(actualDebts).length > 0 ? actualDebts : undefined,
        currency_id: currencyId,
        currency_code: primaryCurrencyCode || 'UZS',
        delivery: deliveryPayload(delivery),
        // D2.6: retsept(lar) yoki retseptsiz sotish sababi (D2.5) — faqat dorixona rejimida
        ...(pharmacy ? buildRxPayload(cart, rxData, rxReason, rxMode) : {}),
      };

      let res;
      if (editingSale) {
        // Faqat aniq tahrirlangan sotuvni yangilaymiz (sessionStorage dan EMAS)
        res = await api.put(`/sales/${editingSale.id}`, { ...payload, warehouse_id: editingSale.warehouse_id || (warehouseId ? Number(warehouseId) : undefined) });
        toast.success(t('wholesale.saleUpdated', { number: editingSale.number }));
        setEditingSale(null);
        setTab('list');
        sessionStorage.removeItem('ulgurji_session_sale_id'); // ← sessiyani tozalash
      } else {
        // Yangi sotuv — hech qachon sessionStorage dagi pending ID ishlatilmaydi!
        res = await api.post('/sales/', payload, pharmacy ? { _suppressToast: true } : undefined);
        sessionStorage.removeItem('ulgurji_session_sale_id'); // ← old pending session clear
        toast.success(t('wholesale.saleSavedSuccess'));
      }
      if (pharmacy) { setRxData({}); setRxReason(''); }

      if (autoPrint) {
        try {
          const rSettings = getReceiptSettings();
          const tpl = receiptWidth === 'A4' ? 'nak' : receiptWidth;
          const cfgRaw = tpl === 'nak' ? (rSettings.nak || {}) : (rSettings['r' + tpl] || {});
          // Company ma'lumotlari fallback: agar tanlangan shablonda bo'sh bo'lsa,
          // boshqa shablonlardan olamiz (58mm da kiritilgan bo'lsa — 80mm uchun ham ishlaydi)
          const r58 = rSettings.r58 || {};
          const r80 = rSettings.r80 || {};
          const rNak = rSettings.nak || {};
          const COMPANY_FIELDS = ['company', 'address', 'phone', 'inn', 'logo', 'logo_size', 'footer'];
          const merged = {};
          for (const f of COMPANY_FIELDS) {
            merged[f] = cfgRaw[f] || r58[f] || r80[f] || rNak[f] || '';
          }
          const cfg = { ...cfgRaw, ...merged };
          // Tanlangan mijozni aniqlaymiz
          const selectedCust = customers.find(c => String(c.id) === String(custId));
          // UZS ekvivalentida ko'rsatish uchun (chekda to'lov qatorlari)
          const payTypesArr = payments.filter(p => parseN(p.amt) > 0).map(p => ({
            type: p.type, amount: parseN(p.amt) * (getRate(p.currency || 'UZS'))
          }));
          // Native valyutada (joriy qarz fallback uchun)
          const paymentCurrencies = payments.filter(p => parseN(p.amt) > 0).map(p => ({
            type: p.type,
            amount: parseN(p.amt),
            currency: p.currency || 'UZS',
            rate: getRate(p.currency || 'UZS'),
          }));
          const currentCurrencyCode = res.data.currency_code || primaryCurrencyCode || "UZS";
          const currentExchangeRate = res.data.exchange_rate || getRate(primaryCurrencyCode) || 1.0;

          printReceiptHtml(buildReceiptHtml({
            number: res.data.number, id: res.data.id, created_at: res.data.created_at,
            cashier_name: res.data.cashier_name,
            total_amount: res.data.total_amount,
            paid_amount: res.data.paid_amount,
            discount_amount: saleDisc,
            currency_code: currentCurrencyCode,
            exchange_rate: currentExchangeRate,
            // Mijoz ma'lumotlari
            contractor_name: selectedCust ? selectedCust.name : (res.data.customer_name || undefined),
            contractor_contacts: selectedCust?.phone ? [{ value: selectedCust.phone }] : [],
            // To'lov turlari ro'yxati (UZS ekvivalentida, ko'rsatish uchun)
            payment_types_array: payTypesArr.length > 0 ? payTypesArr : undefined,
            // Izoh
            note: note || payNote || undefined,
            // Joriy sotuv qarzi — backenddan (har valyuta alohida)
            debt_amounts: (() => {
              let d = res.data.debt_amounts || null;
              if (typeof d === 'string') { try { d = JSON.parse(d); } catch (e) { d = null; } }
              return d;
            })(),
            // Qarz ma'lumotlari — auto-print: before_debt_balances = backend dan to'g'ridan to'g'ri olinadi
            before_debt: 0,
            before_debt_balances: (() => {
              let raw = res.data.before_debt_balances;
              if (typeof raw === 'string') { try { raw = JSON.parse(raw); } catch (e) { raw = null; } }
              if (raw && Object.keys(raw).length > 0) return raw;

              // Fallback (eskiroq sotuvlar uchun, amalda bu yerda kerak bo'lmaydi chunki auto-print yangi sotuvda ishlaydi)
              if (!selectedCust) return null;
              const currBalances = selectedCust.debt_balances || { UZS: Number(selectedCust.debt_balance || 0) };
              let saleDebtAmounts = res.data.debt_amounts || {};
              if (typeof saleDebtAmounts === 'string') {
                try { saleDebtAmounts = JSON.parse(saleDebtAmounts); } catch (e) { saleDebtAmounts = {}; }
              }
              if (Object.keys(saleDebtAmounts).length > 0) {
                const prev = { ...currBalances };
                for (const [curr, amt] of Object.entries(saleDebtAmounts)) {
                  const c = String(curr).toUpperCase();
                  prev[c] = (Number(prev[c] || 0)) - Number(amt);
                }
                return prev;
              }
              return currBalances;
            })(),
            // To'lov valyuta ma'lumotlari (fallback uchun)
            payment_currencies: paymentCurrencies,
            items: cart.map(it => ({
              product_name: it.name,
              quantity: it.qty,
              unit_price: it.price,
              discount: it.discount_type === 'pct'
                ? it.price * it.qty * (parseN(it.discount_val) / 100)
                : parseN(it.discount_val),
              subtotal: itemNet(it),
              unit: it.unit,
              currency_code: it.currency || 'UZS',
              exchange_rate: it.rate || 1.0,
            })),
          }, tpl, cfg));
        } catch (err) { console.error('Auto-print error:', err); }
      }

      // Snapshot: cart tozalanishidan oldin saqlaymiz
      const cartSnap     = [...cart];
      const paymentsSnap = payments.filter(p => parseN(p.amt) > 0).map(p => ({
        type: p.type, amount: String(parseN(p.amt) * getRate(p.currency || 'UZS')),
      }));
      const discSnap = saleDisc;

      setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDelivery(EMPTY_DELIVERY); setDiscVal('');
      setPayNote(''); setDebtDate('');
      setShowPayment(false); setShowDebtDate(false); setPayments([]);
      setFormProduct(null); setFormPrice(''); setFormQty('1'); setFormDiscVal('');
      sessionStorage.removeItem('ulgurji_cart');
      sessionStorage.removeItem('ulgurji_customer');

      // Fiskalizatsiya yoqilgan bo'lsa — tasdiqlash modalini ko'rsatamiz.
      // Yangi sotuv YOKI avval "pending" bo'lib, hozir to'lov bilan yakunlanayotgan
      // sotuv uchun so'raladi. Allaqachon "completed" bo'lgan sotuvni shunchaki
      // tahrirlashda (masalan izoh o'zgartirish) qayta fiskal so'ralmaydi.
      const fiskalEnabled = JSON.parse(localStorage.getItem('fiskalSend') || 'false');
      const factoryId     = JSON.parse(localStorage.getItem('fiskalId')   || 'null');
      const wasPendingBeforeEdit = editingSale && editingSale.status === 'pending';
      if (fiskalEnabled && factoryId && (!editingSale || wasPendingBeforeEdit)) {
        // T3.18: saleId — fiskallangach natijani PATCH /sales/{id}/fiscal bilan serverga yozish uchun
        setFiskalPending({ factoryId, cartSnap, paymentsSnap, discount: discSnap, saleId: res?.data?.id ?? null });
      }


    } catch (e) {
      // T2.12: PUT /sales/{id} endi kredit limitdan oshganda 400 "Kredit limitidan oshadi: ..." qaytaradi —
      // server matni (limit, joriy qarz, yangi qarz) ko'rsatiladi; sotuv tahrir holatida qoladi.
      const detail = e?.response?.data?.detail;
      // D2.6: dorixona 400 xatolari (muddat D1.2, butun quti D2.4, retsept D2.5, markirovka D3.2) — aniq oynada
      if (pharmacy && e?.response?.status === 400) {
        const info = describeRejection(detail);
        setShowPayment(false);
        if (info.category === 'rx' && detail && typeof detail === 'object') {
          setRxError(info.text);
          setRxModal({ proceed: false, message: info.text });
        } else {
          setSaleError({ category: info.category, message: info.text, boxFix: parseWholeBoxError(detail) });
        }
        return;
      }
      toast.error((typeof detail === 'string' && detail) || t('wholesale.saveError'));
    }
    finally { setSaving(false); }
  };

  const handlePay = async () => {
    if (!cart.length) return toast.error(t('sale.emptyCart'));
    if (!hasShift) { setShowShiftModal(true); return; }
    if (!custId && (!pharmacy || debt > 0)) return toast.error(t(pharmacy ? 'wholesale.selectCustomerForDebtSale' : 'wholesale.customerNotSelectedFull'));
    if (debt > 0 && !debtDate && showDebtDate) return toast.error(t('wholesale.enterDebtDueDate'));
    if (debt > 0 && !showDebtDate) { setShowDebtDate(true); return; }
    const totalPaidUZS = getPaidUZS(payments); // Haqiqiy to'langan hamma pulni so'mdagi qiymati
    const types = [...new Set(payments.map(p => p.type))];
    let finalPayType;
    if (totalPaidUZS === 0) finalPayType = 'debt';
    else if (types.length === 1 && debt === 0) finalPayType = types[0];
    else finalPayType = 'mixed';
    // Backend ga yuborish uchun faqat so'mdagi yig'indilar
    const pCashUZS = payments.filter(p => p.type === 'cash' || p.type === 'uzcard' || p.type === 'humo' || p.type === 'click' || p.type === 'payme' || p.type === 'transfer' ? p.type === 'cash' : false).reduce((s, p) => s + (parseN(p.amt) * getRate(p.currency)), 0);
    const pCardUZS = payments.filter(p => p.type !== 'cash' && p.type !== 'debt').reduce((s, p) => s + (parseN(p.amt) * getRate(p.currency)), 0);
    await submitSale(finalPayType, totalPaidUZS, pCashUZS, pCardUZS);
  };

  const handleDirectAction = async (actionType) => {
    if (!cart.length) return toast.error(t('sale.emptyCart'));
    if (actionType === 'draft') {
      const existing = JSON.parse(localStorage.getItem('ulgurji_drafts') || '[]');
      localStorage.setItem('ulgurji_drafts', JSON.stringify([{ id: Date.now(), date: new Date().toISOString(), cart, custId, note, discType, discVal, total }, ...existing]));
      toast.success(t('wholesale.saleArchived'));
      setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDelivery(EMPTY_DELIVERY); setDiscVal('');
      sessionStorage.removeItem('ulgurji_cart');
      sessionStorage.removeItem('ulgurji_customer');
      return;
    }
    if (actionType === 'debt') {
      if (!custId) return toast.error(t('wholesale.selectCustomerForDebtSale'));
      await submitSale('debt', 0, 0, 0);
    }
  };

  // D2.6: retsept ma'lumotini tasdiqlash (to'lov oynasidan oldin)
  const setRxField = (pid, field, val) => setRxData(prev => ({ ...prev, [pid]: { ...(prev[pid] || {}), [field]: val } }));
  const confirmRx = () => {
    const err = validateRx(cart, rxData, rxReason, rxMode);
    if (err) { setRxError(err); return; }
    setRxError('');
    const proceed = !!rxModal?.proceed;
    setRxModal(null);
    if (proceed) openPayModal();
  };
  const applyBoxFix = () => {
    const name = saleError?.boxFix?.name;
    const idx = cart.findIndex(c => c.name === name && wholeBoxMax(c) != null);
    if (idx >= 0) switchUnit(idx, '');
    setSaleError(null);
  };

  const openPayModal = () => {
    if (!cart.length) return;
    if (!custId && !pharmacy) return toast.error(t('wholesale.customerNotSelected'));
    if (!hasShift) { setShowShiftModal(true); return; }
    if (pharmacy && rxProductsOf(cart).length && validateRx(cart, rxData, rxReason, rxMode)) {
      setRxModal({ proceed: true });
      return;
    }
    
    const uniqueCurrencies = [...new Set(cart.map(item => item.currency || 'UZS'))];
    
    if (uniqueCurrencies.length > 0) {
      setPayments(uniqueCurrencies.map((curr, idx) => ({ 
        id: Date.now() + idx, 
        type: 'cash', 
        amt: '', 
        currency: curr 
      })));
    } else {
      setPayments([{ id: Date.now(), type: 'cash', amt: '', currency: 'UZS' }]);
    }
    
    setShowPayment(true);
  };

  // ── Pending (to'lovsiz) saqlash ──────────────────────────────────────────
  const savePendingSale = async (silently = false) => {
    if (!cart.length || !custId) return;
    setPendingSaving(true);
    try {
      const items = cart.map(it => {
        const disc = it.discount_type === 'pct'
          ? it.price * it.qty * (parseN(it.discount_val) / 100)
          : parseN(it.discount_val);
        // D2.6: pending sotuv unit_id ni qabul qilmaydi — birlik (quti/blister) qatori asosiy birlikka (dona) o'tkaziladi
        // (miqdor * nisbat, narx / nisbat; summa o'zgarmaydi). Oddiy korxonada unit_id yo'q — ratio 1.
        const unitRatio = pharmacy && it.unit_id ? (Number(it.unit_ratio) || 1) : 1;
        return {
          product_id: it.product_id, quantity: it.qty * unitRatio, unit_price: it.price / unitRatio,
          price_manual: isPriceManual(it),
          discount: disc,
          promotion_id: (it.promo_id && disc > 0) ? it.promo_id : undefined,   // T4.3: server tekshiradi, qo'shimcha chegirma qo'shmaydi
          variant_id: it.variant_id || undefined,
          warehouse_id: it.warehouse_id || undefined,
          currency: it.currency || 'UZS',
          currency_code: it.currency || 'UZS',
          rate: it.rate || 1,
          exchange_rate: it.rate || 1,
        };
      });
      const uniqueCurrs = [...new Set(cart.map(it => it.currency || 'UZS'))];
      const primaryCurr = uniqueCurrs.length === 1 ? uniqueCurrs[0] : 'UZS';
      const payload = {
        items,
        status: 'pending',
        payment_type: 'cash',
        currency_code: primaryCurr,
        // Tahrirlashda paid_amount yuborilmaydi — backend eski to'lovni saqlaydi
        ...(editingSale ? {} : { paid_amount: 0 }),
        discount_amount: saleDisc,
        note: note || undefined,
        customer_id: custId ? Number(custId) : undefined,
        warehouse_id: warehouseId ? Number(warehouseId) : undefined,
        delivery: deliveryPayload(delivery),
      };

      // MUHIM: faqat aniq tahrirlayotgan savoni yangilaymiz
      // sessionStorage dan kelgan ID — YANGI mijoz uchun HECH QACHON ishlatilmaydi!
      const activeSaleId = editingSale?.id || null;

      if (activeSaleId) {
        const wid = editingSale?.warehouse_id || payload.warehouse_id;
        await api.put(`/sales/${activeSaleId}`, { ...payload, warehouse_id: wid });
        sessionStorage.removeItem('ulgurji_session_sale_id');
        if (editingSale) {
          setEditingSale(null);
          setTab('list');
        }
        if (!silently) toast.success(t('wholesale.saleUpdatedShort'));
      } else {
        const res = await api.post('/sales/pending', payload);
        sessionStorage.removeItem('ulgurji_session_sale_id');
        if (!silently) toast.success(t('wholesale.saleSavedPending'));
      }

      setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDelivery(EMPTY_DELIVERY); setDiscVal('');
      setFormProduct(null); setFormPrice(''); setFormQty('1'); setFormDiscVal('');
      sessionStorage.removeItem('ulgurji_cart');
      sessionStorage.removeItem('ulgurji_customer');
    } catch (e) {
      if (!silently) toast.error(e?.response?.data?.detail || t('wholesale.saveError'));
    } finally {
      setPendingSaving(false);
    }
  };

  // Auto-save: boshqa bo'limga o'tganda yoki sahifa yopilganda pending saqlash
  const cartRef = useRef(cart);
  cartRef.current = cart;
  custIdRef.current = custId;  // har render da yangilanadi (addToCart uchun ham)

  // Unmount vaqtida kerak bo'lgan barcha ma'lumotlarni ref da saqlaymiz
  const pendingSaveDataRef = useRef(null);
  pendingSaveDataRef.current = { cart, custId, saleDisc, warehouseId, editingSale };

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (cartRef.current.length > 0 && custIdRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  // Tab ochilganda shu sessiyaga tegishli pending sotuvni tiklash
  useEffect(() => {
    const sessionSaleId = sessionStorage.getItem('ulgurji_session_sale_id');
    if (!sessionSaleId) return;
    api.get(`/sales/${sessionSaleId}`).then(r => {
      const sale = r.data;
      if (sale.status !== 'pending') { sessionStorage.removeItem('ulgurji_session_sale_id'); return; }
      setCart((sale.items || []).map(it => ({
        product_id: it.product_id, name: it.product_name,
        unit: it.unit || 'dona',            // ← haqiqiy unit
        qty: Number(it.quantity), price: Number(it.unit_price),
        currency: it.currency_code || 'UZS',
        rate: it.exchange_rate ? Number(it.exchange_rate) : 1,
        discount_type: 'sum', discount_val: it.discount > 0 ? String(it.discount) : '',
        wholesale_price: Number(it.unit_price), sale_price: Number(it.unit_price), stock_quantity: 9999,
        price_manual: true,   // T3.19: saqlangan (buyurtma/sotuv) narxi qayta hisoblanmasin
        addedAt: Date.now(),
        warehouse_id: it.warehouse_id || null, // ← per-item sklad
        warehouse_name: it.warehouse_name || null,
      })));
      setCustId(sale.customer_id ? String(sale.customer_id) : '');
      setNote(sale.note || '');
      setDelivery(deliveryFromSale(sale.delivery));
      setDiscType('sum');
      setDiscVal(sale.discount_amount > 0 ? String(sale.discount_amount) : '');
      setEditingSale({ id: sale.id, number: sale.number, warehouse_id: sale.warehouse_id, status: sale.status });
    }).catch(() => {
      sessionStorage.removeItem('ulgurji_session_sale_id');
    });
  }, []);

  // XAVFSIZ: Unmount vaqtida avtomatik saqlash O'CHIRILDI!
  // Sabab: bu bug ning asosiy manbai edi — unmount da sessionStorage dagi
  // BOSHQA mijoz uchun yaratilgan pending sale ID ustiga yangi mijoz ma'lumotlari
  // yozilib ketardi. Foydalanuvchi "Saqlash" tugmasini o'zi bosishi kerak.
  // useEffect(() => { return () => { ... } }, []);  ← o'chirildi (BUG FIX)

  // Tab o'zgarganda (Tarixi yoki Arxiv ga o'tganda) auto-pending saqlash
  const handleTabChange = async (newTab) => {
    if (newTab !== 'new' && tab === 'new' && cartRef.current.length > 0 && custIdRef.current) {
      await savePendingSale(true);
      toast.info(t('wholesale.cartSavedPending'));
    }
    setTab(newTab);
  };

  /* ══════════════════════════════════════════════════
     RENDER
  ══════════════════════════════════════════════════ */
  return (
    <div className="absolute inset-0 flex flex-col bg-slate-100 overflow-hidden">
      {showShiftModal && <ShiftOpenModal onOpened={() => { reloadShift(); setShowShiftModal(false); }} onCancel={() => setShowShiftModal(false)} />}
      {showShiftClose && activeShift && <ShiftCloseModal shift={activeShift} onClosed={() => { setShowShiftClose(false); reloadShift(); }} onCancel={() => setShowShiftClose(false)} />}
      {showProdAddModal && <ProductAddModal warehouses={warehouses} defaultWarehouseId={warehouseId || branchDefaultWarehouseId || ''} onClose={() => setShowProdAddModal(false)} onSaved={p => { selectFormProduct(p); setShowProdAddModal(false); }} />}
      {returnSale && <PartialReturnModal sale={returnSale} onClose={() => setReturnSale(null)} onSuccess={() => { setReturnSale(null); loadSales(); }} />}

      {/* ── FISKAL TASDIQLASH MODAL ─────────────────────────────────────── */}
      {fiskalPending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-[360px] overflow-hidden">
            <div className="bg-slate-900 px-5 py-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <div>
                <div className="text-white font-bold text-sm">{t('wholesale.saleSavedCheck')}</div>
                <div className="text-slate-400 text-xs">{t('wholesale.decideFiscalReceipt')}</div>
              </div>
            </div>
            <div className="px-5 py-5 text-center">
              <div className="text-2xl mb-1">🧾</div>
              <div className="font-bold text-slate-800 text-base mb-1">{t('wholesale.issueFiscalReceipt')}</div>
              <div className="text-slate-500 text-xs">{t('wholesale.fiscalReceiptHint')}</div>
            </div>
            <div className="px-5 pb-5 flex gap-3">
              <button
                disabled={isFiskalizing}
                onClick={() => setFiskalPending(null)}
                className="flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50 transition-colors disabled:opacity-40"
              >
                {t('wholesale.noSkip')}
              </button>
              <button
                disabled={isFiskalizing}
                onClick={async () => {
                  setIsFiskalizing(true);
                  try {
                    const { factoryId, cartSnap, paymentsSnap, discount, saleId } = fiskalPending;
                    const { fiscal } = await fiscalizeAndPrint({ factoryId, cart: cartSnap, payments: paymentsSnap, discountAmount: discount });
                    toast.success(t('wholesale.fiscalReceiptSent'));
                    // T3.18: natijani serverga yozish (xato bo'lsa sotuv bekor qilinmaydi, faqat ogohlantirish)
                    const sign = fiscal?.fiscal_sign ?? fiscal?.FiscalSign;
                    if (saleId && sign) {
                      const seq = Number(fiscal?.receipt_seq ?? fiscal?.receipt_number ?? fiscal?.ReceiptSeq);
                      const txId = fiscal?.transaction_id ?? fiscal?.TransactionID;
                      const body = {
                        fiscal_sign: String(sign),
                        fiscal_qr_url: fiscal?.qr_code_url ?? fiscal?.QRCodeURL ?? undefined,
                        fiscal_receipt_seq: Number.isFinite(seq) && seq >= 0 ? seq : undefined,
                        fiscal_transaction_id: txId != null ? String(txId) : undefined,
                        fiscal_at: new Date().toISOString().slice(0, 19),
                        fiscal_factory_id: factoryId,
                      };
                      try {
                        await api.patch(`/sales/${saleId}/fiscal`, body, { _suppressToast: true });
                      } catch (patchErr) {
                        toast.warning(tfb('pos.fiscalSaveFailed', 'Fiskal chek berildi, lekin natija serverga yozilmadi: {message}', {
                          message: patchErr?.response?.data?.detail || patchErr?.message || t('wholesale.unknown'),
                        }));
                      }
                    }
                  } catch (err) {
                    toast.error(t('wholesale.fiscalError', { msg: err?.message || t('wholesale.unknown') }));
                  } finally {
                    setIsFiskalizing(false);
                    setFiskalPending(null);
                  }
                }}
                className="flex-1 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isFiskalizing
                  ? <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg> {t('wholesale.sending')}</>
                  : <>✓ {t('wholesale.yesFiscalize')}</>
                }
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── HEADER ── */}
      <div className="shrink-0 bg-white border-b border-slate-200 px-3 md:px-5 py-2.5 flex items-center justify-between shadow-sm gap-2">
        <div className="hidden lg:flex items-center gap-1.5 text-slate-500 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-100">
          <Ic d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4" />
          <span className="text-sm font-bold font-mono tracking-tight">{currentTime.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })}</span>
        </div>

        {/* Mijoz narx turi badge — bosib o'zgartirish mumkin */}
        {selected && (() => {
          const pt = selected.price_type || 'sale';
          const cfg = {
            sale: { label: `🔵 ${t('wholesale.retail')}`, cls: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100' },
            wholesale: { label: `🟢 ${t('wholesale.wholesaleShort')}`, cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100' },
            cost: { label: `🟠 ${t('wholesale.costPrice')}`, cls: 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100' },
          }[pt] || { label: `🔵 ${t('wholesale.retail')}`, cls: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100' };
          return (
            <button
              onClick={changePriceType}
              title={t('wholesale.priceTypeToggleHint')}
              className={`hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold cursor-pointer transition-colors ${cfg.cls}`}
            >
              {cfg.label} {t('wholesale.priceLower')}
              <svg className="w-3 h-3 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </button>
          );
        })()}

        {/* Faol aksiyalar */}
        {promotions.length > 0 && (
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-violet-200 bg-violet-50 text-violet-700 text-xs font-bold">
            🎁 {t('wholesale.activePromotions', { count: promotions.length })}
          </div>
        )}

        <div className="flex items-center gap-1.5 md:gap-3">
          {[
            { id: 'new', label: t('common.new'), icon: 'M12 4v16m8-8H4' },
            { id: 'list', label: t('sale.title'), icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
            { id: 'drafts', label: t('wholesale.archive'), icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' },
          ].map(tabItem => (
            <button key={tabItem.id} onClick={() => handleTabChange(tabItem.id)}
              className={`flex items-center gap-0.5 md:gap-1 px-2 md:px-3.5 py-2 rounded-lg font-semibold transition-all ${tab === tabItem.id ? 'bg-blue-600 text-white shadow-md shadow-blue-200' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              <Ic d={tabItem.icon} cls="w-3.5 h-3.5" />
              <span className="text-[10px] md:text-sm">{tabItem.label}</span>
            </button>
          ))}

          {tab === 'new' && (
            <button onClick={() => {
              if (cart.length > 0) {
                exportCartToExcel();
              } else {
                toast.info(t('wholesale.excelUploadComingSoon') || "Excel yuklash tez kunda");
              }
            }}
              className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors text-sm font-bold border border-emerald-100"
              title={cart.length > 0 ? "Savatchadagi mahsulotlarni Excel formatida yuklab olish" : "Excel"}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
              Excel
            </button>
          )}

          <div className="w-px h-5 bg-slate-200 mx-1 hidden md:block" />

          {activeShift && (
            <button onClick={() => setShowShiftClose(true)}
              className="shrink-0 px-2.5 md:px-3 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 border border-red-100 text-[10px] md:text-sm font-bold transition-colors">
              {(() => { const v = t('shift.closeAction'); return v === 'shift.closeAction' ? 'Smenani yopish' : v; })()}
            </button>
          )}

          <button onClick={() => setSettingsOpen(true)}
            className="shrink-0 rounded-xl text-slate-500 hover:text-blue-600 hover:bg-blue-50 flex items-center justify-center transition-colors">
            <Ic d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </button>
        </div>
      </div>

      {/* ══ YANGI SOTUV ══ */}
      {tab === 'new' && (
        <>
          {editingSale && (
            <div className="shrink-0 bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-700 text-sm font-semibold">
                <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-4 h-4" />
                {t('wholesale.editMode')}: <span className="font-black font-mono">{editingSale.number}</span>
              </div>
              <button onClick={() => { setEditingSale(null); setCart([]); setCustId(defaultCustomerId || ''); setNote(''); setDelivery(EMPTY_DELIVERY); setDiscVal(''); sessionStorage.removeItem('ulgurji_session_sale_id'); }}
                className="text-amber-500 hover:text-amber-700 font-bold text-sm">{t('common.cancel')}</button>
            </div>
          )}

          {/* Main two-panel area */}
          <div className="flex-1 flex flex-col md:flex-row overflow-hidden min-h-0">

            {/* ── LEFT PANEL: Forma ── */}
            <div className={`md:w-[380px] lg:w-[410px] md:shrink-0 md:flex md:flex-col md:bg-white md:border-r md:border-slate-200 md:overflow-y-auto
              ${mobileTab === 'form' ? 'flex flex-col flex-1 overflow-y-auto bg-white' : 'hidden md:flex md:flex-col'}`}>
              <div className="p-3 space-y-2.5">

                {/* Mijoz */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wide">{t('sale.customer')}{pharmacy ? '' : ' *'}</label>
                    <div className="flex items-center gap-1.5">
                      {!custId && !pharmacy && <span className="text-xs text-red-400 font-semibold">{t('common.notSelected')}</span>}
                      <button onClick={() => custSearchRef.current?.openForm()}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 hover:bg-blue-100 text-blue-600 text-xs font-bold border border-blue-200 transition-colors">
                        <span className="text-sm leading-none">+</span> {t('common.new')}
                      </button>
                    </div>
                  </div>
                  <CustomerSearch onCustomerSelected={() => setTimeout(() => prodSearchRef.current?.focus(), 50)} ref={custSearchRef} customers={customers} value={custId}
                    onChange={(newId) => {
                      setCustId(newId);
                    }}
                    onNew={c => setCustomers(prev => [...prev, c])} onFetch={handleNewFetchedCustomers} />
                </div>

                <div className="border-t border-slate-100" />

                {/* Mahsulot qo'shish */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wide">{t('wholesale.product')}</label>
                    <div className="flex items-center gap-1.5">
                      {/* Yangi mahsulot */}
                      <button onClick={() => setShowProdAddModal(true)}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-600 text-xs font-bold border border-emerald-200 transition-colors">
                        <span className="text-sm leading-none">+</span> {t('common.new')}
                      </button>
                      {/* Mijoz narx turi ko'rsatgichi / o'zgartirgichi */}
                      <button
                        onClick={() => {
                          setIsWholesaleMode(prev => {
                            const next = !prev;
                            localStorage.setItem('ulgurji_isWholesale', next ? 'true' : 'false');
                            return next;
                          });
                        }}
                        className={`flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-bold border transition-colors cursor-pointer select-none ${isWholesaleMode ? 'bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-700' : 'bg-blue-600 border-blue-600 text-white hover:bg-blue-700'}`}
                      >
                        <Ic d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a2 2 0 012-2z" cls="w-3 h-3" />
                        {isWholesaleMode ? t('wholesale.wholesaleShort') : t('wholesale.retail')}
                      </button>
                      {/* Ombor */}
                      {warehouses.length > 0 && (
                        <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
                          className="border border-slate-200 rounded-lg px-1.5 py-0.5 text-xs font-semibold text-slate-700 focus:outline-none bg-white">
                          <option value="">{t('common.all')}</option>
                          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                      )}
                    </div>
                  </div>

                  <ProductSearch customerPriceType={isWholesaleMode ? 'wholesale' : 'sale'} disabled={!custId && !pharmacy} ref={prodSearchRef} onSelect={selectFormProduct} placeholder={t('wholesale.productSearchPlaceholder')} onOpenAdd={() => setShowProdAddModal(true)} warehouseId={warehouseId} />

                  {/* Mijoz tanlanmagan ogohlantirish (dorixonada mijoz ixtiyoriy) */}
                  {!custId && !pharmacy && (
                    <div className="mt-2 flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5">
                      <svg className="w-4 h-4 text-amber-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                      <span className="text-xs font-semibold text-amber-700">{t('wholesale.selectCustomerFirstToAddProduct')}</span>
                    </div>
                  )}

                  {/* Selected product card */}
                  {formProduct ? (
                    <div className="mt-2 bg-blue-50/70 border border-blue-100 rounded-lg p-2.5">
                      {/* Product info */}
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-lg bg-white border border-blue-100 flex items-center justify-center shrink-0 overflow-hidden">
                          {formProduct.image_url
                            ? <img src={formProduct.image_url} alt="" className="w-full h-full object-cover" />
                            : <span className="font-black text-blue-500 text-xs">{formProduct.name?.[0]}</span>}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-bold text-slate-800 text-xs truncate">{formProduct.name}</div>
                          <div className="text-[11px] text-slate-500 flex items-center justify-between gap-1 mt-0.5">
                            <div className="flex items-center gap-1.5">
                              <span className="font-semibold text-slate-600">{formProduct.unit || t('common.piece')}</span>
                              <span className={`font-semibold ${Number(formProduct.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                                {t('wholesale.warehouseShort')}: {fmt(formProduct.stock_quantity)}
                              </span>
                            </div>
                            <span className="text-slate-400">
                              {t('wholesale.originalPrice')}: {fmt(isWholesaleMode ? (formProduct.wholesale_price || formProduct.sale_price) : formProduct.sale_price)}
                            </span>
                          </div>
                        </div>
                        <button onClick={() => setFormProduct(null)} className="text-slate-300 hover:text-red-400 shrink-0 p-1">
                          <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Inputs Grid: 2 columns */}
                      <div className="grid grid-cols-2 gap-2 mb-2">

                        {/* 1. Narx */}
                        <div>
                          <div className="flex justify-between items-center mb-0.5">
                            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">{t('common.price')}</label>
                            <div className="flex gap-1">
                              {formProduct.wholesale_price > 0 && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    let p = Number(formProduct.wholesale_price);
                                    let c = formProduct.sale_currency || 'UZS';
                                    if (onlySom && c !== 'UZS') {
                                      p = p * getRate(c);
                                      c = 'UZS';
                                    }
                                    setFormPrice(String(p));
                                    setFormCurrency(c);
                                  }}
                                  className="text-[9px] font-bold px-1 py-0.5 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded transition-colors" title={t('wholesale.wholesalePrice')}>U</button>
                              )}
                              {formProduct.sale_price > 0 && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    let p = Number(formProduct.sale_price);
                                    let c = formProduct.sale_currency || 'UZS';
                                    if (onlySom && c !== 'UZS') {
                                      p = p * getRate(c);
                                      c = 'UZS';
                                    }
                                    setFormPrice(String(p));
                                    setFormCurrency(c);
                                  }}
                                  className="text-[9px] font-bold px-1 py-0.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded transition-colors" title={t('wholesale.retailPrice')}>C</button>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="relative flex-1">
                              <input data-no-scan
                                ref={formPriceRef}
                                type="text"
                                value={fmtPrice(formPrice)}
                                onChange={e => {
                                  setFormPrice(parsePrice(e.target.value));
                                }}
                                onFocus={e => e.target.select()}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') {
                                    e.preventDefault();
                                    formQtyRef.current?.focus();
                                  }
                                }}
                                className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-black text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
                              />
                            </div>
                            <select
                              value={formCurrency}
                              onChange={e => {
                                const newCode = e.target.value;
                                if (!newCode || newCode === formCurrency) return;

                                const oldRate = getRate(formCurrency);
                                const newRate = getRate(newCode);
                                const currentPrice = parseFloat(formPrice) || 0;

                                if (currentPrice > 0) {
                                  const priceInUZS = currentPrice * oldRate;
                                  const converted = priceInUZS / newRate;
                                  const formatted = converted < 0.01 ? converted.toFixed(4) : converted.toFixed(2);
                                  setFormPrice(String(parseFloat(formatted)));
                                }
                                setFormCurrency(newCode);
                              }}
                              className="cursor-pointer border border-slate-200 rounded-lg px-1 py-1.5 text-xs font-black text-blue-600 focus:outline-none bg-white">
                              <option value="UZS">UZS</option>
                              {currencies.filter(c => String(c.code).toUpperCase() !== 'UZS').map((item) => (
                                <option key={item.id} value={item.code}>{item.code}</option>
                              ))}
                            </select>
                          </div>
                        </div>

                        {/* 2. Miqdor */}
                        <div>
                          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-0.5 block">{t('common.quantity')} ({formProduct.unit || t('common.piece')})</label>
                          <div className="flex items-center gap-1">
                            <button onClick={() => setFormQty(q => String(Math.max(0, (parseFloat(q) || 1) - 1)))}
                              className="w-8 h-8 shrink-0 rounded-lg bg-white flex items-center justify-center font-black text-slate-600 text-base active:bg-slate-100 border border-slate-200">−</button>
                            <input data-no-scan ref={formQtyRef} type="number" step="any" value={formQty}
                              onChange={e => setFormQty(e.target.value)}
                              onFocus={e => e.target.select()}
                              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addFormToCart(); } }}
                              className="flex-1 min-w-0 border border-slate-200 rounded-lg py-1.5 text-center text-xs font-black text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white" />
                            <button onClick={() => setFormQty(q => String((parseFloat(q) || 1) + 1))}
                              className="w-8 h-8 shrink-0 rounded-lg bg-blue-600 flex items-center justify-center font-black text-white text-base active:bg-blue-700">+</button>
                          </div>
                        </div>

                        {/* 3. JAMI SUMMA — Barcha o'lchov birliklari uchun (dona, kg, metr va b.) */}
                        <div>
                          <label className="text-[10px] font-bold text-emerald-700 uppercase tracking-wide mb-0.5 block">
                            {t('wholesale.totalSum')} ({formCurrency || 'UZS'})
                          </label>
                          <div className="flex items-center gap-1">
                            <input data-no-scan type="text" inputMode="decimal"
                              value={fmtPrice(formTotalText)}
                              onChange={e => onFormTotalChange(e.target.value)}
                              onFocus={e => e.target.select()}
                              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addFormToCart(); } }}
                              placeholder="0"
                              title={t('wholesale.totalSumHint', { unit: formProduct.unit || t('common.piece') })}
                              className="w-full border border-emerald-300 rounded-lg px-2 py-1.5 text-xs font-black text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white" />
                          </div>
                        </div>

                        {/* 4. Chegirma */}
                        <div>
                          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-0.5 block">{t('common.discount')}</label>
                          <div className="flex gap-1">
                            <button onClick={() => setFormDiscType(dt => dt === 'pct' ? 'amt' : 'pct')}
                              className="w-8 h-8 shrink-0 rounded-lg bg-white border border-amber-200 text-amber-600 font-black text-xs hover:bg-amber-50 active:bg-amber-100 transition-colors">
                              {formDiscType === 'pct' ? '%' : "S"}
                            </button>
                            <input data-no-scan ref={formDiscRef} type="number" value={formDiscVal}
                              onChange={e => setFormDiscVal(e.target.value)}
                              onFocus={e => e.target.select()}
                              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addFormToCart(); } }}
                              placeholder="0"
                              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white" />
                          </div>
                        </div>

                      </div>

                      {/* 5. Savatga qo'shish */}
                      <button onClick={addFormToCart}
                        className="w-full h-8 bg-blue-600 cursor-pointer hover:bg-blue-700 active:bg-blue-800 text-white font-bold text-xs rounded-lg flex items-center justify-center gap-1.5 shadow-sm shadow-blue-200 transition-all">
                        <Ic d="M12 4v16m8-8H4" cls="w-3.5 h-3.5" />
                        {t('sale.addToCart')}
                      </button>
                    </div>
                  ) : (
                    <div className="mt-2 flex flex-col items-center justify-center py-4 text-slate-300 gap-1.5 bg-slate-50/50 rounded-lg border border-dashed border-slate-200">
                      <Ic d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" cls="w-7 h-7" />
                      <p className="text-xs text-slate-400 text-center">{t('wholesale.searchProductOrScan')}</p>
                    </div>
                  )}
                </div>

                <div className="border-t border-slate-100" />

                {/* Izoh */}
                <div>
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1 block">{t('common.note')}</label>
                  <textarea value={note} onChange={e => setNote(e.target.value)}
                    placeholder={t('wholesale.contractNumberNotePlaceholder')} rows={1}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none bg-white" />
                </div>

                {/* Yetkazib berish */}
                {(features?.distribution || delivery.existing) && (
                  <SaleDeliveryBlock value={delivery} onChange={setDelivery} customerId={custId} />
                )}

                {/* Sotuv chegirmasi */}
                <div>
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-1 block">{t('wholesale.saleDiscount')}</label>
                  <div className="flex gap-1.5">
                    <div className="flex rounded-lg border border-slate-200 overflow-hidden shrink-0">
                      {['pct', 'amt'].map(dt => (
                        <button key={dt} onClick={() => setDiscType(dt)}
                          className={`px-2 py-1 text-xs cursor-pointer font-bold transition-colors ${discType === dt ? 'bg-amber-500 text-white' : 'bg-white text-slate-500'}`}>
                          {dt === 'pct' ? '%' : t('common.sum')}
                        </button>
                      ))}
                    </div>
                    <input data-no-scan type="number" value={discVal} onChange={e => setDiscVal(e.target.value)}
                      placeholder="0"
                      className="flex-1 border border-slate-200 rounded-lg px-2.5 py-1 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white" />
                  </div>
                  {saleDisc > 0 && <p className="text-[11px] text-amber-600 font-semibold mt-0.5">− {fmt(saleDisc)} {t('common.sum')} {t('common.discount').toLowerCase()}</p>}
                </div>

                {/* Spacer for mobile scroll */}
                <div className="h-1" />
              </div>
            </div>

            {/* ── RIGHT PANEL: Savat ── */}
            <div className={`flex-1 flex flex-col overflow-hidden bg-white
              ${mobileTab === 'cart' ? 'flex' : 'hidden md:flex md:flex-col'}`}>

              {/* Cart header */}
              <div className="shrink-0 px-4 py-2.5 border-b border-slate-100 flex items-center justify-between bg-slate-50">
                <span className="text-sm font-bold text-slate-600">
                  {cart.length > 0 ? t('wholesale.cartSummary', { types: cart.length, units: cart.reduce((s, i) => s + i.qty, 0).toFixed(1) }) : t('sale.emptyCart')}
                </span>
                {cart.length > 0 && (
                  <button onClick={() => { if (window.confirm(t('wholesale.confirmClearCart'))) { setCart([]); sessionStorage.removeItem('ulgurji_cart'); sessionStorage.removeItem('ulgurji_customer'); } }}
                    className="text-xs text-red-400 hover:text-red-600 font-semibold px-2 py-1 rounded-lg hover:bg-red-50 transition-colors">
                    {t('wholesale.clearAll')}
                  </button>
                )}
              </div>

              {/* Cart body */}
              <div className="flex-1 overflow-y-auto">
                {cart.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-300 gap-3 p-8">
                    <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center">
                      <Ic d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" cls="w-7 h-7" />
                    </div>
                    <div className="text-center">
                      <p className="font-bold text-slate-400">{t('sale.emptyCart')}</p>
                      <p className="text-xs text-slate-300 mt-1">{t('wholesale.addProductFromLeftOrScan')}</p>
                    </div>
                  </div>
                ) : (
                  <table className="w-full text-sm border-collapse">
                    <thead className="sticky top-0 z-10 bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="text-left px-2 py-1.5 text-xs font-bold text-slate-500 w-7">#</th>
                        <th className="text-left px-2 py-1.5 text-xs font-bold text-slate-500">{t('common.name')}</th>
                        <th className="text-center px-1.5 py-1.5 text-xs font-bold text-slate-500 w-[110px]">{t('common.quantity')}</th>
                        <th className="text-right px-1.5 py-1.5 text-xs font-bold text-slate-500 w-[100px]">{t('common.price')}</th>
                        <th className="text-center px-1.5 py-1.5 text-xs font-bold text-slate-500 w-[100px]">{t('common.discount')}</th>
                        <th className="text-right px-2 py-1.5 text-xs font-bold text-slate-500 w-[95px]">{t('common.total')}</th>
                        <th className="w-7" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {cart.map((it, idx) => {
                        const net = itemNet(it);
                        const hasDisc = parseN(it.discount_val) > 0;
                        const curSym = it.currency === 'USD' ? '$' : (it.currency === 'UZS' ? 's' : it.currency);
                        return (
                          <tr key={idx} className="hover:bg-slate-50/80 group transition-colors">
                            <td className="px-2 py-1.5 text-xs text-slate-400 font-mono">{idx + 1}</td>
                            <td className="px-2 py-1.5">
                              <div className="font-semibold text-slate-800 text-xs md:text-sm leading-tight">{it.name}</div>
                              <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                                <span className="text-[11px] text-slate-400">{it.unit}</span>
                                {pharmacy && (
                                  <>
                                    {it.nearest_expiry && (
                                      <span className={`text-[9px] font-bold px-1 rounded ${it.expiry_warn ? 'bg-amber-100 text-amber-700 border border-amber-300' : 'bg-slate-100 text-slate-500'}`}
                                        title={it.expiry_warn ? tfb('pos.expiryWarnTitle', 'Muddati yaqin — eng yaqin yaroqlilik muddati') : tfb('pos.expiryNearest', 'Eng yaqin muddat')}>
                                        {it.expiry_warn ? '⚠ ' : ''}{tfb('pos.expiryShort', 'Muddat')}: {fmtExpiry(it.nearest_expiry)}
                                      </span>
                                    )}
                                    {(isControlled(it) || it.is_rx) && (
                                      <button type="button" onClick={() => setRxModal({})}
                                        className={`text-[9px] font-bold px-1 rounded ${isControlled(it) ? 'bg-red-100 text-red-700' : 'bg-violet-100 text-violet-700'}`}>
                                        {isControlled(it) ? tfb('pos.rxControlled', 'Nazoratda') : 'Rx'}
                                      </button>
                                    )}
                                    {Array.isArray(it.units) && it.units.some(u => (Number(u.ratio) || 1) !== 1) && (
                                      <select value={it.unit_id || ''} onChange={e => switchUnit(idx, e.target.value)}
                                        className="border border-slate-200 rounded px-0.5 text-[10px] font-bold text-slate-700 bg-white outline-none"
                                        title={tfb('pos.unitSelect', 'Birlik')}>
                                        <option value="">{it.base_unit_name || 'dona'}</option>
                                        {it.units.filter(u => (Number(u.ratio) || 1) !== 1).map(u => (
                                          <option key={u.id} value={u.id}>{u.name}</option>
                                        ))}
                                      </select>
                                    )}
                                    {wholeBoxMax(it) != null && (
                                      <>
                                        <span className="text-[9px] font-bold text-slate-400">{tfb('pos.wholeBoxMaxShort', 'max {n} quti', { n: wholeBoxMax(it) })}</span>
                                        <button type="button" onClick={() => switchUnit(idx, '')}
                                          className="text-[9px] font-bold px-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100">
                                          {tfb('pos.sellByPiece', 'Dona qilib sotish')}
                                        </button>
                                      </>
                                    )}
                                    <button type="button" onClick={() => openAnalogs(it)}
                                      className="text-[9px] font-bold px-1 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100">
                                      {tfb('pos.analogs', 'Analoglar')}
                                    </button>
                                  </>
                                )}
                                {it.warehouse_name && (
                                  <span className="bg-emerald-50 text-emerald-600 border border-emerald-100 text-[9px] font-bold px-1 py-0.2 rounded flex items-center gap-0.5">
                                    <Ic d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" cls="w-2.5 h-2.5" />
                                    {it.warehouse_name}
                                  </span>
                                )}
                                {it.currency && it.currency !== 'UZS' && (
                                  <span className="text-[9px] font-black text-blue-500 bg-blue-50 px-1 py-0.2 rounded uppercase">{it.currency}</span>
                                )}
                                {it.promo_name && (
                                  <span className="bg-violet-50 text-violet-600 border border-violet-200 text-[9px] font-bold px-1 py-0.2 rounded flex items-center gap-0.5">
                                    🎁 {it.promo_name}
                                  </span>
                                )}
                                {it.requires_marking && (
                                  <button
                                    type="button"
                                    onClick={() => setMarkingModal({ idx })}
                                    className={`text-[9px] font-bold px-1 py-0.2 rounded flex items-center gap-0.5 border ${
                                      (it.marking_codes || []).length >= it.qty
                                        ? 'bg-emerald-50 text-emerald-600 border-emerald-200'
                                        : 'bg-red-50 text-red-600 border-red-200 animate-pulse'
                                    }`}
                                  >
                                    📷 {(it.marking_codes || []).length}/{it.qty}
                                  </button>
                                )}
                              </div>
                            </td>
                            <td className="px-1.5 py-1.5">
                              <div className="flex items-center gap-0.5 justify-center">
                                <button onClick={() => updateItem(idx, 'qty', Math.max(0, it.qty - 1))}
                                  className="w-6 h-6 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center font-bold text-slate-600 text-xs">−</button>
                                <input data-no-scan type="number" value={it.qty}
                                  onChange={e => updateItem(idx, 'qty', Math.max(0, parseFloat(e.target.value) ?? 0))}
                                  className="w-12 text-center font-black text-slate-800 border border-slate-200 rounded py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-300" />
                                <button onClick={() => updateItem(idx, 'qty', it.qty + 1)}
                                  className="w-6 h-6 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center font-bold text-slate-600 text-xs">+</button>
                              </div>
                            </td>
                            <td className="px-1.5 py-1.5">
                              <div className="relative">
                                <input data-no-scan type="text"
                                  value={fmtPrice(it.price)}
                                  onChange={e => {
                                    updateItem(idx, 'price', parsePrice(e.target.value));
                                  }}
                                  className="w-full min-w-16 text-right font-bold text-slate-800 border border-slate-200 rounded py-0.5 pr-5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-300" />
                                <span className={`absolute right-1.5 top-1/2 -translate-y-1/2 text-[11px] font-bold ${it.currency === 'USD' ? 'text-green-600' : 'text-slate-400'}`}>{curSym}</span>
                              </div>
                            </td>
                            <td className="px-1.5 py-1.5">
                              <div className="flex items-center gap-0.5 justify-center">
                                <button onClick={() => updateItem(idx, 'discount_type', it.discount_type === 'pct' ? 'amt' : 'pct')}
                                  className="w-6 h-6 rounded bg-amber-50 text-amber-600 text-[10px] font-black border border-amber-200 shrink-0">
                                  {it.discount_type === 'pct' ? '%' : curSym}
                                </button>
                                <input data-no-scan type="number" value={it.discount_val || ''}
                                  onChange={e => updateItem(idx, 'discount_val', parseFloat(e.target.value) || 0)}
                                  placeholder="0"
                                  className="w-12 text-center text-xs border border-slate-200 rounded py-0.5 focus:outline-none focus:ring-1 focus:ring-amber-300" />
                              </div>
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              <div className="font-black text-slate-800 text-xs md:text-sm whitespace-nowrap">{fmt(net)} {curSym}</div>
                              {hasDisc && <div className="text-[10px] text-slate-400 line-through whitespace-nowrap">{fmt(it.price * it.qty)} {curSym}</div>}
                              {it.currency !== 'UZS' && <div className="text-[10px] text-blue-500 font-bold">≈ {fmt(Math.round(net * it.rate))} s</div>}
                            </td>
                            <td className="pr-1.5 py-1.5">
                              <button onClick={() => removeItem(idx)}
                                className="w-6 h-6 rounded text-slate-400 hover:bg-red-50 hover:text-red-500 flex items-center justify-center transition-colors">
                                <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Cart totals */}
              {cart.length > 0 && (
                <div className="shrink-0 bg-slate-50 border-t border-slate-200 px-3 py-2 space-y-1">
                  <div>
                    {Object.entries(totalsByCurrency).map(([cur, amt]) => (
                      <div key={cur} className="flex justify-between items-center group">
                        <span className="text-xs font-black text-slate-600 uppercase tracking-wider leading-none">{cur === 'UZS' ? t('product.title') : cur} {t('common.total').toLowerCase()}:</span>
                        <span className="text-base font-black text-blue-600">
                          {fmt(amt)} {cur === 'USD' ? '$' : (cur === 'UZS' ? t('common.sum') : cur)}
                        </span>
                      </div>
                    ))}
                  </div>

                  {saleDisc > 0 && (
                    <div className="flex justify-between items-center py-1 border-y border-dashed border-slate-200">
                      <span className="text-[10px] font-black text-amber-600 uppercase tracking-wider">{t('common.discount')}:</span>
                      <span className="text-xs font-black text-amber-600">− {fmt(saleDisc)} s</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ── MOBILE TABS ── */}
          <div className="md:hidden shrink-0 flex border-t border-slate-200 bg-white">
            <button onClick={() => setMobileTab('form')}
              className={`flex-1 py-2 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors
                ${mobileTab === 'form' ? 'text-blue-600 border-t-2 border-blue-600 -mt-px' : 'text-slate-500 border-t-2 border-transparent -mt-px'}`}>
              <Ic d="M12 4v16m8-8H4" cls="w-3.5 h-3.5" />
              {t('common.add')}
            </button>
            <button onClick={() => setMobileTab('cart')}
              className={`flex-1 py-2 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors
                ${mobileTab === 'cart' ? 'text-blue-600 border-t-2 border-blue-600 -mt-px' : 'text-slate-500 border-t-2 border-transparent -mt-px'}`}>
              <Ic d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" cls="w-3.5 h-3.5" />
              {t('sale.cart')}
              {cart.length > 0 && (
                <span className="bg-blue-600 text-white text-[10px] font-black rounded-full min-w-[16px] h-[16px] flex items-center justify-center px-1">{cart.length}</span>
              )}
            </button>
          </div>

          {/* ── BOTTOM ACTION BAR ── */}
          <div className="shrink-0 bg-white border-t border-slate-200 shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">

            {/* Mobile: 2-row layout */}
            <div className="md:hidden">
              {/* Row 1: 4 secondary action buttons */}
              <div className="flex gap-1 px-2 pt-1.5 pb-1">
                <button onClick={() => { if (!cart.length) return; if (window.confirm(t('wholesale.confirmClearCart'))) { setCart([]); setFormProduct(null); } }}
                  disabled={cart.length === 0}
                  className="flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-lg bg-red-600 text-white active:bg-red-700 disabled:opacity-40 font-bold transition-all shadow-sm">
                  <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-3.5 h-3.5" />
                  <span className="text-[9px]">{t('common.delete')}</span>
                </button>

                <button onClick={() => savePendingSale(false)}
                  disabled={cart.length === 0 || !custId || pendingSaving}
                  className="flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-lg bg-amber-600 text-white active:bg-amber-700 disabled:opacity-40 font-bold transition-all shadow-sm">
                  <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M12 12v4m0 0l-2-2m2 2l2-2" cls="w-3.5 h-3.5" />
                  <span className="text-[9px]">{pendingSaving ? t('common.saving') : t('wholesale.withoutPayment')}</span>
                </button>

                <button onClick={() => handleDirectAction('debt')}
                  disabled={cart.length === 0 || saving}
                  className="flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-lg bg-blue-600 text-white active:bg-blue-700 disabled:opacity-40 font-bold transition-all shadow-sm">
                  <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-3.5 h-3.5" />
                  <span className="text-[9px]">{t('pay.debt')}</span>
                </button>

                <button disabled={cart.length === 0}
                  onClick={() => { if (!cart.length) return; openPayModal(); }}
                  className="flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-lg bg-slate-700 text-white active:bg-slate-800 disabled:opacity-40 font-bold transition-all shadow-sm">
                  <Ic d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" cls="w-3.5 h-3.5" />
                  <span className="text-[9px]">{t('sale.receipt')}</span>
                </button>
              </div>

              {totalsByCurrency && Object.keys(totalsByCurrency).length > 1 && (
                <div className="px-2 py-1.5 bg-blue-50/50 border-y border-blue-100 flex flex-wrap gap-x-3 gap-y-0.5">
                  {Object.entries(totalsByCurrency).map(([cur, amt]) => (
                    <div key={cur} className="flex items-center gap-1">
                      <span className="text-[9px] font-bold text-slate-400 uppercase">{cur}:</span>
                      <span className="text-xs font-black text-blue-700">{fmt(amt)} {cur === 'USD' ? '$' : (cur === 'UZS' ? 's' : cur)}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Row 2: full-width Pay button */}
              <div className="px-2 pb-1.5 mt-1">
                <button onClick={openPayModal}
                  disabled={cart.length === 0 || saving}
                  className={`w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg font-black text-xs shadow-sm transition-all disabled:opacity-40
                    ${!custId && !pharmacy && cart.length > 0 ? 'bg-amber-500 hover:bg-amber-600 text-white' : 'bg-emerald-600 hover:bg-emerald-700 text-white'}`}>
                  <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-3.5 h-3.5" />
                  <span>{!custId && !pharmacy && cart.length > 0 ? t('sale.selectCustomer') : editingSale ? t('common.update') : t('sale.checkout')}</span>
                  {cart.length > 0 && <span className="font-black">{fmt(total)} s</span>}
                </button>
              </div>
            </div>

            {/* Desktop: single row */}
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5">
              <button onClick={() => { if (!cart.length) return; if (window.confirm(t('wholesale.confirmClearCart'))) { setCart([]); setFormProduct(null); } }}
                disabled={cart.length === 0}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 active:bg-red-800 disabled:opacity-40 text-white text-xs md:text-sm font-bold shadow-sm transition-all cursor-pointer disabled:cursor-not-allowed">
                <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-3.5 h-3.5" />
                <span>{t('common.delete')}</span>
              </button>

              <button onClick={() => savePendingSale(false)}
                disabled={cart.length === 0 || !custId || pendingSaving}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 active:bg-amber-800 disabled:opacity-40 text-white text-xs md:text-sm font-bold shadow-sm transition-all cursor-pointer disabled:cursor-not-allowed">
                <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2M12 12v4m0 0l-2-2m2 2l2-2" cls="w-3.5 h-3.5" />
                <span>{pendingSaving ? t('common.saving') : t('wholesale.saveWithoutPayment')}</span>
              </button>

              <button onClick={() => handleDirectAction('debt')}
                disabled={cart.length === 0 || saving}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-40 text-white text-xs md:text-sm font-bold shadow-sm transition-all cursor-pointer disabled:cursor-not-allowed">
                <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-3.5 h-3.5" />
                <span>{t('pay.debt')}</span>
              </button>

              <button disabled={cart.length === 0}
                onClick={() => { if (!cart.length) return; openPayModal(); }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-slate-700 hover:bg-slate-800 active:bg-slate-900 disabled:opacity-40 text-white text-xs md:text-sm font-bold shadow-sm transition-all cursor-pointer disabled:cursor-not-allowed">
                <Ic d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" cls="w-3.5 h-3.5" />
                <span>{t('sale.receipt')}</span>
              </button>

              <div className="flex-1" />

              <button onClick={openPayModal}
                disabled={cart.length === 0 || saving}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg font-black text-xs md:text-sm shadow-sm transition-all disabled:opacity-40
                  ${!custId && !pharmacy && cart.length > 0 ? 'bg-amber-500 hover:bg-amber-600 text-white' : 'bg-emerald-600 hover:bg-emerald-700 text-white'}`}>
                <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-3.5 h-3.5" />
                <span>{!custId && !pharmacy && cart.length > 0 ? t('sale.selectCustomer') : editingSale ? t('common.update') : t('sale.checkout')}</span>
              </button>
            </div>
          </div>
        </>
      )}

      {/* ══ SOTUVLAR TARIXI ══ */}
      {tab === 'list' && (
        <div className="flex-1 overflow-hidden flex flex-col p-3 md:p-4 gap-3">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-3 md:p-4 flex flex-wrap gap-2 items-center">
            <input type="date" value={filters.date_from} onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))}
              className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            <input type="date" value={filters.date_to} onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))}
              className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
              className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white">
              <option value="">{t('wholesale.allStatuses')}</option>
              <option value="completed">{t('sale.statusCompleted')}</option>
              <option value="pending">{t('wholesale.statusPendingApproval')}</option>
              <option value="cancelled">{t('wholesale.statusCancelledShort')}</option>
            </select>
            <input value={filters.search} onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
              placeholder={t('wholesale.saleNumberOrCustomerPlaceholder')} className="border-2 border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 w-full max-w-100" />
            <button onClick={loadSales} className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5">
              <Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-3.5 h-3.5" />{t('common.search')}
            </button>
            <div className="flex-1" />
            <div className="flex items-center gap-2">
              <button onClick={exportToExcel} disabled={!sales || sales.length === 0}
                className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 disabled:opacity-40 text-white text-sm font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                title="Sotuvlar ro'yxatini Excel (.xlsx) formatida yuklab olish">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                <span>Excel</span>
              </button>
              <button onClick={exportToPdf} disabled={!sales || sales.length === 0}
                className="px-3 py-2 bg-rose-600 hover:bg-rose-700 active:bg-rose-800 disabled:opacity-40 text-white text-sm font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                title="Sotuvlar ro'yxatini PDF formatida chop etish yoki saqlash">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" /></svg>
                <span>PDF</span>
              </button>
            </div>
          </div>

          <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-auto">
            {loadingSales ? (
              <div className="flex justify-center items-center h-64"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                  <tr>
                    {['#', t('sale.number'), t('sale.customer'), t('common.total'), t('common.paid'), t('common.debt'), t('sale.paymentType'), t('common.status'), t('sale.cashier'), t('common.date'), ''].map((h, hi) => (
                      <th key={hi} className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {sales.length === 0 && <tr><td colSpan={11} className="text-center py-16 text-slate-400">{t('sale.noSales')}</td></tr>}
                  {sales.filter((s) => s?.status !== 'refunded').map((s, i) => {
                    const dbt = Number(s?.total_amount) - Number(s?.paid_amount);
                    return (
                      <tr key={s.id} onClick={() => { setSelectedSale(s); setOpenMenuId(null); }}
                        className="hover:bg-blue-50/40 cursor-pointer transition-colors">
                        <td className="px-4 py-3 text-xs text-slate-400">{i + 1 + page * LIMIT}</td>
                        <td className="px-4 py-3">
                          <span className="font-mono font-black text-blue-700 text-xs bg-blue-50 px-2.5 py-1 rounded-lg border border-blue-100">{s.number}</span>
                          {s.delivery_status && s.delivery_status !== 'cancelled' && (
                            <span title={t(`logistics.orderStatus.${s.delivery_status}`)}
                              className={`ml-1.5 text-[10px] font-bold px-1.5 py-0.5 rounded-md ${s.delivery_status === 'delivered' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                              🚚 {t(`logistics.orderStatus.${s.delivery_status}`)}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {s.customer_name ? (
                            <div className="flex items-center justify-between gap-1.5 group/cust">
                              <div className="flex items-center gap-2">
                                <div className="w-7 h-7 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-xs font-bold">{s.customer_name[0]}</div>
                                <span className="font-semibold text-slate-700">{s.customer_name}</span>
                              </div>
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); openAssignCustomerModal(s); }}
                                className="opacity-0 group-hover/cust:opacity-100 text-[11px] text-blue-600 hover:text-blue-800 px-1.5 py-0.5 rounded bg-blue-50 hover:bg-blue-100 transition-all font-semibold"
                                title={t('wholesale.changeCustomer')}
                              >
                                ✏️
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); openAssignCustomerModal(s); }}
                              className="inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded-lg border border-blue-200 transition-all"
                            >
                              <span className="text-sm font-black">+</span> {t('wholesale.assignCustomer')}
                            </button>
                          )}
                        </td>
                        <td className="px-4 py-3 font-black text-slate-800 text-right whitespace-nowrap">
                          {s.currency_code === 'USD' ? `${fmt(s.total_amount)} $` : `${fmt(s.total_amount)} s`}
                        </td>
                        <td className="px-4 py-3 font-bold text-emerald-700 text-right whitespace-nowrap">
                          {s.currency_code === 'USD' ? `${fmt(s.paid_amount)} $` : `${fmt(s.paid_amount)} s`}
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {dbt > 0 ? (
                            <span className="font-bold text-red-600">
                              {s.currency_code === 'USD' ? `${fmt(dbt)} $` : `${fmt(dbt)} s`}
                            </span>
                          ) : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-3"><span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{(PAY_META_KEYS[s.payment_type] && t(PAY_META_KEYS[s.payment_type])) || s.payment_type}</span></td>
                        <td className="px-4 py-3"><span className={`text-xs font-bold px-2 py-0.5 rounded-full ${STATUS_META[s.status]?.c || 'bg-slate-100 text-slate-500'}`}>{(STATUS_META[s.status]?.lKey && t(STATUS_META[s.status].lKey)) || s.status}</span></td>
                        <td className="px-4 py-3 text-sm text-slate-500">{s.cashier_name}</td>
                        <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{s.created_at ? new Date(s.created_at).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                        <td className="px-3 py-3 relative text-right whitespace-nowrap" onClick={e => e.stopPropagation()}>
                          <div className="inline-flex items-center gap-1.5 justify-end">
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); downloadSalePdf(s); }}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 active:bg-rose-200 text-rose-600 hover:text-rose-700 font-bold text-xs border border-rose-200 transition-all shadow-xs cursor-pointer"
                              title="Ushbu sotuvni PDF formatida yuklab olish"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              <span>PDF</span>
                            </button>
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); exportSingleSaleToExcel(s); }}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 active:bg-emerald-200 text-emerald-600 hover:text-emerald-700 font-bold text-xs border border-emerald-200 transition-all shadow-xs cursor-pointer"
                              title="Ushbu sotuv tovarlarini Excel formatida yuklab olish"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              <span>Excel</span>
                            </button>
                            <button
                              onClick={e => { e.stopPropagation(); setOpenMenuId(openMenuId === s.id ? null : s.id); }}
                              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
                              title="Boshqa amallar"
                            >
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" /></svg>
                            </button>
                          </div>
                          {openMenuId === s.id && (
                            <div className="absolute right-0 top-8 z-50 bg-white border border-slate-200 rounded-xl shadow-2xl py-1 min-w-[170px]" onMouseLeave={() => setOpenMenuId(null)}>
                              {s.status === 'pending' && !isReturnLinked(s) && (
                                <button onClick={async () => {
                                  setOpenMenuId(null);
                                  await loadEditSale(s);
                                  setTimeout(() => openPayModal(), 150);
                                }} className="w-full text-left px-4 py-2.5 text-sm text-emerald-700 bg-emerald-50 hover:bg-emerald-100 font-bold flex items-center gap-2.5 border-b border-emerald-100">
                                  <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                  To'lovni tasdiqlash
                                </button>
                              )}
                              {!isReturnLinked(s) && (
                                <button onClick={() => loadEditSale(s)} className="w-full text-left px-4 py-2.5 text-sm text-slate-700 hover:bg-blue-50 flex items-center gap-2.5">
                                  <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                                  {t('common.edit')}
                                </button>
                              )}
                              <button onClick={() => { openAssignCustomerModal(s); setOpenMenuId(null); }}
                                className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-blue-50 flex items-center gap-2.5">
                                <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                                {s.customer_name ? t('wholesale.changeCustomer') : t('wholesale.assignCustomer')}
                              </button>
                              <div className="border-t border-slate-100 my-1" />
                              <div className="px-4 py-1 text-xs font-semibold text-slate-400 uppercase tracking-wide">{t('common.print')}</div>
                              {[{ size: '58', label: '58mm' }, { size: '80', label: '80mm' }, { size: 'nak', label: 'A4 Nakladnoy' }].map(opt => (
                                <button key={opt.size} onClick={() => { printSale(s, opt.size); setOpenMenuId(null); }}
                                  className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-blue-50 flex items-center gap-2.5">
                                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" /></svg>
                                  {opt.label}
                                </button>
                              ))}
                              <button onClick={() => { downloadSalePdf(s); setOpenMenuId(null); }}
                                className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-rose-50 hover:text-rose-700 flex items-center gap-2.5">
                                <svg className="w-4 h-4 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                PDF yuklab olish
                              </button>
                              <button onClick={() => { exportSingleSaleToExcel(s); setOpenMenuId(null); }}
                                className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-emerald-50 hover:text-emerald-700 flex items-center gap-2.5">
                                <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                                Excel (Tovarlar)
                              </button>
                              <div className="border-t border-slate-100 my-1" />
                              <button onClick={() => { setReturnSale(s); setOpenMenuId(null); }}
                                className="w-full text-left px-4 py-2 text-sm text-orange-600 hover:bg-orange-50 flex items-center gap-2.5">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
                                {t('sale.return')}
                              </button>
                              <div className="border-t border-slate-100 my-1" />
                              <button onClick={() => { if (isReturnLinked(s)) toast.error(t('sale.cannotDeleteReturned')); else deleteSale(s.id); setOpenMenuId(null); }}
                                className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2.5">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                {t('common.delete')}
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {sales.length > 0 && (
                  <tfoot>
                    <tr className="bg-blue-50 border-t-2 border-blue-100">
                      <td colSpan={3} className="px-4 py-3 text-xs font-bold text-blue-700">{t('wholesale.salesCount', { count: sales.length })}</td>
                      <td className="px-4 py-3 text-right font-black text-blue-800 whitespace-nowrap">{fmt(sales.reduce((s, x) => s + Number(x.total_amount), 0))} s</td>
                      <td className="px-4 py-3 text-right font-black text-emerald-700 whitespace-nowrap">{fmt(sales.reduce((s, x) => s + Number(x.paid_amount), 0))} s</td>
                      <td className="px-4 py-3 text-right font-black text-red-600 whitespace-nowrap">{fmt(sales.reduce((s, x) => s + Math.max(0, Number(x.total_amount) - Number(x.paid_amount)), 0))} s</td>
                      <td colSpan={5} />
                    </tr>
                  </tfoot>
                )}
              </table>
            )}
          </div>

          <div className="flex items-center justify-between">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">← {t('common.prev')}</button>
            <span className="text-sm text-slate-500 font-semibold">{t('wholesale.pageNumber', { page: page + 1 })}</span>
            <button disabled={sales.length < LIMIT} onClick={() => setPage(p => p + 1)} className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-all">{t('common.next')} →</button>
          </div>
        </div>
      )}

      {/* ══ ARXIVLAR ══ */}
      {tab === 'drafts' && (
        <div className="flex-1 overflow-auto p-4 md:p-6 bg-slate-50">
          <div className="max-w-4xl mx-auto space-y-4">
            {draftsList.length === 0 && (
              <div className="text-center py-20 bg-white rounded-3xl border border-slate-200">
                <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4 text-slate-300">
                  <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-8 h-8" />
                </div>
                <h3 className="text-lg font-bold text-slate-700">{t('wholesale.noArchivedSales')}</h3>
                <p className="text-sm text-slate-400 mt-1">{t('wholesale.archiveHint')}</p>
              </div>
            )}
            {draftsList.map((d, i) => (
              <div key={d.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="bg-amber-100 text-amber-700 text-[10px] font-black uppercase px-2 py-0.5 rounded-full tracking-wide">
                      {new Date(d.date).toLocaleString('uz-UZ', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className="text-sm font-bold text-slate-800">{t('wholesale.productTypesCount', { count: d.cart.length })}</span>
                  </div>
                  <h4 className="text-2xl font-black text-blue-700">{fmt(d.total)} {t('common.sum')}</h4>
                  {d.note && <p className="text-xs text-slate-500 mt-1">📝 {d.note}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => removeDraft(i)} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm">{t('common.delete')}</button>
                  <button onClick={() => loadDraft(i)} className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-sm shadow-md shadow-blue-200">{t('wholesale.loadIntoCart')}</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ══ TO'LOV MODALI ══ */}
      {showPayment && (() => {
        const closeModal = () => { setShowPayment(false); setShowDebtDate(false); setPayments([]); };
        const remaining = Math.max(0, total - paid);
        const updateLine = (id, fieldOrObj, val) => {
          setPayments(prev => prev.map(p => {
            if (p.id === id) {
              if (typeof fieldOrObj === 'object') {
                return { ...p, ...fieldOrObj };
              }
              return { ...p, [fieldOrObj]: val };
            }
            return p;
          }));
        };
        const removeLine = (id) => { if (payments.length > 1) setPayments(prev => prev.filter(p => p.id !== id)); };
        const addLine = () => setPayments(prev => [...prev, { id: Date.now(), type: 'cash', amt: '', currency: 'UZS' }]);
        const fillLine = (id) => {
          const line = payments.find(p => p.id === id);
          if (!line) return;
          
          const lineCurr = line.currency || 'UZS';
          
          const itemsCostInCurr = cart.filter(it => (it.currency || 'UZS') === lineCurr).reduce((sum, it) => sum + itemNet(it), 0);
          
          let formattedAmt = '0';

          if (itemsCostInCurr > 0) {
            const otherPaidInCurr = payments.filter(p => p.id !== id && (p.currency || 'UZS') === lineCurr).reduce((sum, p) => sum + (parseFloat(p.amt) || 0), 0);
            const neededInLineCurrency = Math.max(0, itemsCostInCurr - otherPaidInCurr);
            formattedAmt = lineCurr === 'UZS' || !lineCurr
              ? String(Math.round(neededInLineCurrency))
              : String(Number(neededInLineCurrency.toFixed(4)));
          } else {
            const totalOtherPaidUZS = getPaidUZS(payments.filter(p => p.id !== id));
            const stillNeededUZS = Math.max(0, total - totalOtherPaidUZS);
            const lineRate = getRate(lineCurr);
            const neededInLineCurrency = stillNeededUZS / lineRate;
            formattedAmt = lineCurr === 'UZS' || !lineCurr
              ? String(Math.round(neededInLineCurrency))
              : String(Number(neededInLineCurrency.toFixed(4)));
          }
          
          updateLine(id, 'amt', formattedAmt);
        };
        const now = new Date();
        return (
          <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/50 backdrop-blur-sm p-0 md:p-4">
            <div className="bg-white w-full md:max-w-lg rounded-t-3xl md:rounded-2xl shadow-2xl overflow-hidden flex flex-col" style={{ maxHeight: '95vh' }}>
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center">
                    <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-4 h-4 text-white" />
                  </div>
                  <div>
                    <h2 className="text-base font-black text-slate-800">{t('wholesale.payToCashier')}</h2>
                    <p className="text-xs text-blue-500 font-mono">{now.toLocaleString('ru-RU').replace(',', '')}</p>
                  </div>
                </div>
                <button onClick={closeModal} className="w-8 h-8 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-500">
                  <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                {selected && (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-0.5">{t('sale.customer')}</div>
                      <div className="text-sm font-black text-blue-700">{selected.name}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t('wholesale.currentDebt')}</div>
                      <div className="text-sm font-black text-red-600">{fmt(selected.debt_balance)} s</div>
                      {selected.debt_balances && typeof selected.debt_balances === 'object' && Object.keys(selected.debt_balances).some(k => k !== 'UZS' && Number(selected.debt_balances[k]) !== 0) && (
                        <div className="flex flex-wrap gap-1 justify-end mt-1">
                          {Object.entries(selected.debt_balances).map(([curr, amt]) => (curr !== 'UZS' && Number(amt) !== 0) && (
                            <span key={curr} className="inline-flex items-center text-[9px] font-black text-white bg-red-500 px-1.5 py-0.5 rounded shadow-sm">
                              {fmt(amt)} {curr}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">{t('customer.payment')}</span>
                    <button onClick={addLine} className="w-7 h-7 rounded-lg bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center shadow-sm">
                      <Ic d="M12 4v16m8-8H4" cls="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="space-y-2">
                    {payments.map((line, idx) => {
                      const isDebt = line.type === 'debt';
                      const lineRate = getRate(line.currency);
                      const amtInUZS = (parseN(line.amt) || 0) * lineRate;

                      return (
                        <div key={line.id} className="bg-slate-50/50 border border-slate-100 rounded-xl p-2 space-y-2">
                          <div className="flex items-center gap-2">
                            <div className="relative flex-1">
                              <select value={line.type} onChange={e => updateLine(line.id, { type: e.target.value, reference: '', terminal_id: '' })}
                                className="w-full h-10 pl-3 pr-8 border border-slate-200 rounded-lg text-sm font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white appearance-none cursor-pointer">
                                {PAY_TYPES.map(p => <option key={p.id} value={p.id}>{t(p.labelKey)}</option>)}
                              </select>
                              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                <Ic d="M19 9l-7 7-7-7" cls="w-4 h-4" />
                              </div>
                            </div>

                            <div className="relative w-32">
                              <select value={line.currency || 'UZS'} onChange={e => {
                                const newCode = e.target.value;
                                const oldCode = line.currency || 'UZS';
                                const oldRate = getRate(oldCode);
                                const newRate = getRate(newCode);
                                const currentAmt = parseFloat(line.amt) || 0;
                                if (currentAmt > 0) {
                                  const amtInUZS = currentAmt * oldRate;
                                  const converted = amtInUZS / newRate;
                                  const formatted = newCode === 'UZS'
                                    ? String(Math.round(converted))
                                    : String(Number(converted.toFixed(4)));
                                  updateLine(line.id, { currency: newCode, amt: formatted });
                                } else {
                                  updateLine(line.id, 'currency', newCode);
                                }
                              }}
                                className="w-full h-10 pl-3 pr-8 border border-slate-200 rounded-lg text-sm font-black text-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white appearance-none cursor-pointer">
                                <option value="UZS">UZS</option>
                                {currencies.filter(c => c.code !== 'UZS').map(c => <option key={c.id} value={c.code}>{c.code}</option>)}
                              </select>
                              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                <Ic d="M12 8c-1.657 0-3 1.343-3 3s1.343 3 3 3 3-1.343 3-3-1.343-3-3-3zM12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2z" cls="w-4 h-4" />
                              </div>
                            </div>

                            <button onClick={() => removeLine(line.id)} className={`shrink-0 w-8 h-10 rounded-lg flex items-center justify-center ${payments.length > 1 ? 'text-slate-300 hover:text-red-500 hover:bg-red-50' : 'text-slate-200 cursor-not-allowed'}`}>
                              <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                            </button>
                          </div>

                          <div className="flex items-center gap-2">
                            {isDebt
                              ? <div className="flex-1 h-10 px-3 bg-amber-50 border border-amber-100 rounded-lg flex items-center"><span className="text-sm font-black text-amber-700">{t('wholesale.willBeRecordedAsDebt')}</span></div>
                              : <div className="flex-1 relative">
                                <input data-no-scan type="number" value={line.amt} onChange={e => updateLine(line.id, 'amt', e.target.value)}
                                  placeholder="0" autoFocus={idx === payments.length - 1}
                                  className="w-full h-10 pl-3 pr-10 border border-slate-200 rounded-lg text-lg font-black text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-400 min-w-0" />
                                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-400 capitalize">{line.currency || 'UZS'}</span>
                              </div>
                            }
                            {!isDebt && (
                              <button onClick={() => fillLine(line.id)}
                                className="shrink-0 h-10 px-4 bg-slate-800 text-white text-xs font-black rounded-lg hover:bg-slate-700 transition-colors shadow-sm">
                                {t('wholesale.fillRemaining')}
                              </button>
                            )}
                          </div>

                          {/* T3.18: provayder to'lovi — terminal (bir nechta bo'lsa) va tranzaksiya raqami */}
                          {REF_PROVIDERS.includes(line.type) && (providerTerminals(line.type).length > 0 || line.type !== 'uzum') && (
                            <div className="flex items-center gap-2">
                              {providerTerminals(line.type).length > 1 && (
                                <select value={line.terminal_id || ''} onChange={e => updateLine(line.id, 'terminal_id', e.target.value)}
                                  className="h-10 px-2 border border-slate-200 rounded-lg text-sm font-semibold text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-300">
                                  <option value="">—</option>
                                  {providerTerminals(line.type).map(x => (
                                    <option key={x.id} value={x.id}>{x.label || x.terminal_id || x.merchant_id || `#${x.id}`}</option>
                                  ))}
                                </select>
                              )}
                              <input
                                data-no-scan
                                value={line.reference || ''}
                                onChange={e => updateLine(line.id, 'reference', e.target.value)}
                                placeholder={tfb('pos.referencePlaceholder', 'Tranzaksiya raqami') + (referenceRequired(line) ? ' *' : '')}
                                className={`flex-1 min-w-0 h-10 px-3 bg-white border rounded-lg text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-blue-300 ${referenceRequired(line) && !String(line.reference || '').trim() ? 'border-amber-400' : 'border-slate-200'}`}
                              />
                            </div>
                          )}

                          {line.currency && line.currency !== 'UZS' && amtInUZS > 0 && (
                            <div className="text-[10px] font-bold text-blue-500 pl-1">
                              ≈ {fmt(amtInUZS)} {t('common.sum')} ({t('common.rate')}: {fmt(lineRate)})
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1.5 block">{t('common.note')} ({t('common.optional').toLowerCase()})</label>
                  <textarea value={payNote} onChange={e => setPayNote(e.target.value)} placeholder={t('wholesale.contractNumberNotePlaceholder')} rows={2}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none" />
                </div>

                {showDebtDate && remaining > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-3">
                    <Ic d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" cls="w-4 h-4 text-amber-600 shrink-0" />
                    <div className="flex-1">
                      <p className="text-xs font-bold text-amber-700 mb-1">{t('sale.debtDueDate')} ({t('common.optional').toLowerCase()})</p>
                      <input type="date" min={today()} value={debtDate} onChange={e => setDebtDate(e.target.value)}
                        className="w-full border border-amber-300 bg-white rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400" />
                    </div>
                  </div>
                )}

                <div className="bg-slate-50 rounded-xl border border-slate-100 divide-y divide-slate-100">
                  <div className="px-4 py-2 bg-blue-50/50 flex justify-between items-center border-b border-blue-100">
                    <span className="text-[10px] font-black text-blue-500 uppercase">{t('wholesale.totalByCurrency')}</span>
                    <div className="flex gap-3">
                      {Object.entries(totalsByCurrency).map(([cur, amt]) => (
                        <span key={cur} className="text-xs font-black text-slate-700">{fmt(amt)} {cur === 'USD' ? '$' : (cur === 'UZS' ? 's' : cur)}</span>
                      ))}
                    </div>
                  </div>
                  {(() => {
                    const activeCurrencies = Array.from(new Set([
                      ...Object.keys(totalsByCurrency),
                      ...payments.map(p => p.currency || 'UZS')
                    ])).filter(Boolean);

                    const remain = { ...totalsByCurrency };
                    for (const p of payments) {
                      const a = parseN(p.amt);
                      if (a <= 0 || p.type === 'debt') continue;
                      const c = p.currency || 'UZS';
                      if (!remain[c]) remain[c] = 0;
                      remain[c] -= a;
                    }

                    let overpaidUZS = 0;
                    for (const c in remain) {
                      if (remain[c] < -0.001) {
                        overpaidUZS += Math.abs(remain[c]) * getRate(c);
                        delete remain[c];
                      }
                    }

                    for (const c in remain) {
                      if (remain[c] > 0.001 && overpaidUZS > 0.001) {
                        const needUZS = remain[c] * getRate(c);
                        if (overpaidUZS >= needUZS) {
                          overpaidUZS -= needUZS;
                          delete remain[c];
                        } else {
                          remain[c] -= overpaidUZS / getRate(c);
                          overpaidUZS = 0;
                        }
                      }
                    }

                    const debts = {};
                    for (const c in remain) {
                      if (remain[c] > 0.001) {
                        debts[c] = remain[c];
                      }
                    }

                    const rows = [];

                    rows.push({
                      label: t('wholesale.totalAmountCur', { cur: 'UZS' }),
                      val: fmt(total) + ' s',
                      cls: 'text-slate-800 font-bold'
                    });
                    if (saleDisc > 0) {
                      rows.push({
                        label: t('wholesale.discountCur', { cur: 'UZS' }),
                        val: '−' + fmt(saleDisc) + ' s',
                        cls: 'text-amber-600 font-semibold'
                      });
                    }
                    rows.push({
                      label: t('wholesale.totalPaidCur', { cur: 'UZS' }),
                      val: fmt(paid) + ' s',
                      cls: 'text-emerald-600 font-black'
                    });

                    activeCurrencies.forEach(c => {
                      if (c === 'UZS') return;
                      const rate = getRate(c);
                      const totalInC = total / rate;
                      const paidInC = payments.filter(p => (p.currency || 'UZS') === c).reduce((sum, p) => sum + (parseFloat(p.amt) || 0), 0);
                      const sym = c === 'USD' ? '$' : (c === 'RUB' ? '₽' : c);

                      rows.push({
                        label: t('wholesale.totalAmountCur', { cur: c }),
                        val: sym + ' ' + Number(totalInC.toFixed(4)),
                        cls: 'text-slate-700 font-bold border-t border-slate-100 pt-1.5'
                      });
                      rows.push({
                        label: t('wholesale.totalPaidCur', { cur: c }),
                        val: sym + ' ' + Number(paidInC.toFixed(4)),
                        cls: 'text-emerald-600 font-black'
                      });
                    });

                    const allDebtCurrs = Array.from(new Set(['UZS', ...Object.keys(debts)]));
                    let listedDebt = false;
                    allDebtCurrs.forEach(c => {
                      const dVal = debts[c] || 0;
                      if (dVal > 0.009) {
                        listedDebt = true;
                        const sym = c === 'USD' ? '$' : (c === 'RUB' ? '₽' : (c === 'UZS' ? ' s' : ' ' + c));
                        const formattedVal = c === 'UZS'
                          ? fmt(dVal) + sym
                          : sym + ' ' + (dVal < 0.01 ? dVal.toFixed(4) : dVal.toFixed(2));
                        rows.push({
                          label: t('wholesale.remainsAsDebtCur', { cur: c }),
                          val: formattedVal,
                          cls: 'text-red-600 font-black'
                        });
                      }
                    });

                    const remainingUZS = Math.max(0, total - paid);
                    if (remainingUZS > 0 && !listedDebt) {
                      rows.push({
                        label: t('wholesale.remainsAsDebtCur', { cur: 'UZS' }),
                        val: fmt(remainingUZS) + ' s',
                        cls: 'text-red-600 font-black'
                      });
                    }

                    const changeUZS = Math.max(0, paid - total);
                    if (changeUZS > 0) {
                      rows.push({
                        label: t('wholesale.changeCur', { cur: 'UZS' }),
                        val: fmt(changeUZS) + ' s',
                        cls: 'text-blue-600 font-black'
                      });
                    }

                    return rows.map((r, i) => (
                      <div key={i} className="flex justify-between items-center px-4 py-2.5 text-sm">
                        <span className="text-slate-500">{r.label}</span>
                        <span className={r.cls}>{r.val}</span>
                      </div>
                    ));
                  })()}
                </div>
              </div>

              <div className="shrink-0 px-5 py-3.5 border-t border-slate-100 flex gap-2.5">
                <button onClick={closeModal} className="px-5 py-2.5 border border-slate-200 hover:bg-slate-50 text-slate-600 font-semibold rounded-xl text-sm">{t('common.cancel')}</button>
                <button onClick={handlePay} disabled={saving}
                  className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-black rounded-xl text-sm shadow-md shadow-emerald-200 transition-all flex items-center justify-center gap-2">
                  {saving ? <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />{t('common.saving')}</> : <><Ic d="M5 13l4 4L19 7" cls="w-4 h-4" />{t('common.save')}</>}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ══ SOTUV TAFSILOTI MODALI ══ */}
      {selectedSale && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5 text-white flex items-center justify-between shrink-0">
              <div>
                <h2 className="font-black text-lg font-mono">{selectedSale.number}</h2>
                <p className="text-sm text-white/60 mt-0.5">{selectedSale.cashier_name} · {new Date(selectedSale.created_at).toLocaleDateString('uz-UZ')}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold px-3 py-1.5 rounded-full ${STATUS_META[selectedSale.status]?.c || 'bg-white/20 text-white'}`}>{STATUS_META[selectedSale.status]?.lKey ? t(STATUS_META[selectedSale.status].lKey) : ''}</span>
                <button onClick={() => downloadSalePdf(selectedSale)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                  PDF
                </button>
                <button onClick={() => exportSingleSaleToExcel(selectedSale)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                  Excel
                </button>
                <button onClick={() => { openAssignCustomerModal(selectedSale); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                  {selectedSale.customer_name ? t('wholesale.changeCustomer') : t('wholesale.assignCustomer')}
                </button>
                <button onClick={() => { setReturnSale(selectedSale); setSelectedSale(null); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-xs font-bold transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>
                  {t('sale.return')}
                </button>
                <button onClick={() => setSelectedSale(null)} className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center"><Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" /></button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              <SaleDetailContent saleId={selectedSale.id} />
            </div>
          </div>
        </div>
      )}

      {/* ══ MIJOZ BIRIKTIRISH MODALI ══ */}
      {assignModalSale && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={() => setAssignModalSale(null)}>
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-blue-700 to-indigo-700 px-6 py-4 text-white flex items-center justify-between shrink-0">
              <div>
                <h3 className="font-black text-base">
                  {assignModalSale.customer_name ? t('wholesale.changeCustomer') : t('wholesale.assignCustomer')}
                </h3>
                <p className="text-xs text-white/70 font-mono mt-0.5">#{assignModalSale.number} · {assignModalSale.created_at ? new Date(assignModalSale.created_at).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</p>
              </div>
              <button onClick={() => setAssignModalSale(null)} className="w-8 h-8 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center">
                <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="bg-blue-50/60 border border-blue-100 rounded-2xl p-3 text-xs space-y-1.5 text-slate-700">
                <div className="flex justify-between">
                  <span className="text-slate-500">{t('common.total')}:</span>
                  <span className="font-bold text-slate-900">{fmt(assignModalSale.total_amount)} s</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">{t('common.paid')}:</span>
                  <span className="font-bold text-emerald-700">{fmt(assignModalSale.paid_amount)} s</span>
                </div>
                {Number(assignModalSale.total_amount) - Number(assignModalSale.paid_amount) > 0 && (
                  <div className="flex justify-between border-t border-blue-200/60 pt-1.5 font-bold">
                    <span className="text-red-600">{t('common.debt')}:</span>
                    <span className="text-red-600">{fmt(Number(assignModalSale.total_amount) - Number(assignModalSale.paid_amount))} s</span>
                  </div>
                )}
                <p className="text-[11px] text-blue-700 pt-1 border-t border-blue-200/40">
                  ℹ️ {t('wholesale.assignCustomerHint')}
                </p>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">{t('sale.customer')} *</label>
                <CustomerSearch
                  customers={customers}
                  value={assignCustId}
                  onChange={setAssignCustId}
                  onNew={c => { setCustomers(prev => [...prev, c]); setAssignCustId(String(c.id)); }}
                  onFetch={handleNewFetchedCustomers}
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setAssignModalSale(null)}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50 transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="button"
                  disabled={savingAssignCustomer || !assignCustId}
                  onClick={handleSaveAssignCustomer}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm shadow-md shadow-blue-200 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
                >
                  {savingAssignCustomer ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    t('common.save')
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ SOZLAMALAR MODALI ══ */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm overflow-hidden flex flex-col">
            <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-5 text-white flex items-center justify-between shrink-0">
              <h2 className="text-lg font-black">{t('wholesale.saleSettings')}</h2>
              <button onClick={() => setSettingsOpen(false)} className="w-9 h-9 rounded-xl bg-white/20 hover:bg-white/30 flex items-center justify-center"><Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" /></button>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">{t('wholesale.defaultCustomer')}</label>
                <CustomerPicker
                  customers={customers}
                  value={defaultCustomerId}
                  onChange={(id, c) => { if (c) handleNewFetchedCustomers([c]); setDefaultCustomerId(id === '' ? '' : String(id)); }}
                  onResolve={c => handleNewFetchedCustomers([c])}
                  placeholder={t('wholesale.selectOrSearchCustomer')}
                />
                <p className="text-[11px] text-slate-400 mt-1">{t('wholesale.defaultCustomerHint')}</p>
              </div>
              <div className='flex items-center justify-between'>
                <div>
                  <h3 className="text-sm font-bold text-slate-800">{t('wholesale.onlySomTrading')}</h3>
                  <p className="text-[12px] text-slate-500 mt-0.5">{t('wholesale.onlySomTradingHint')}</p>
                </div>
                <button onClick={() => setOnlySom(!onlySom)} className={`w-12 h-6 min-w-max cursor-pointer rounded-full p-1 transition-colors ${onlySom ? 'bg-blue-500' : 'bg-slate-300'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform ${onlySom ? 'translate-x-6' : 'translate-x-0'}`} />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-800">{t('wholesale.autoPrintReceipt')}</h3>
                  <p className="text-[12px] text-slate-500 mt-0.5">{t('wholesale.autoPrintReceiptHint')}</p>
                </div>
                <button onClick={() => setAutoPrint(!autoPrint)} className={`w-12 h-6 cursor-pointer rounded-full p-1 transition-colors ${autoPrint ? 'bg-blue-500' : 'bg-slate-300'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform ${autoPrint ? 'translate-x-6' : 'translate-x-0'}`} />
                </button>
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 block">{t('wholesale.receiptFormat')}</label>
                <div className="grid grid-cols-3 gap-2">
                  {[{ id: '58', label: '58 mm' }, { id: '80', label: '80 mm' }, { id: 'A4', label: 'A4' }].map(w => (
                    <button key={w.id} onClick={() => setReceiptWidth(w.id)}
                      className={`py-2 text-sm font-semibold rounded-xl border-2 transition-colors ${receiptWidth === w.id ? 'border-blue-500 text-blue-700 bg-blue-50' : 'border-slate-100 text-slate-500 hover:border-slate-300'}`}>
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setSettingsOpen(false)} className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-2xl text-sm">{t('common.cancel')}</button>
              <button onClick={saveSettings} className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-2xl text-sm shadow-md shadow-blue-200">{t('common.save')}</button>
            </div>
          </div>
        </div>
      )}
      {/* ── VARIANT PICKER MODAL ── */}
      {/* ── D2.6: RETSEPT OYNASI (faqat dorixona rejimi) ── */}
      {pharmacy && rxModal && (() => {
        const rxItems = rxProductsOf(cart).filter((it, i, arr) => arr.findIndex(x => x.product_id === it.product_id) === i);
        const anyNoRx = rxItems.some(it => !isControlled(it) && rxMode !== 'block' && (rxData[it.product_id]?.mode === 'norx'));
        const inputCls = 'border border-slate-300 rounded-lg px-2 py-1.5 text-sm font-semibold text-slate-700 outline-none focus:border-blue-500 w-full';
        return (
          <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="rx-modal">
            <div className="bg-white rounded-2xl shadow-2xl w-[640px] max-w-[96vw] max-h-[92vh] flex flex-col overflow-hidden">
              <div className="bg-violet-700 px-5 py-3 text-white">
                <div className="font-black text-base">{tfb('pos.rxTitle', "Retsept ma'lumotlari")}</div>
                <div className="text-violet-100 text-xs">
                  {rxMode === 'block'
                    ? tfb('pos.rxModeBlock', 'Retseptli dori retseptsiz sotilmaydi')
                    : tfb('pos.rxModeWarn', 'Retsept kiriting yoki retseptsiz sotish sababini yozing')}
                </div>
              </div>
              <div className="p-4 overflow-y-auto space-y-3">
                {rxModal.message && (
                  <div className="bg-red-50 border border-red-200 text-red-700 text-sm font-semibold rounded-lg px-3 py-2">{rxModal.message}</div>
                )}
                {rxItems.map(it => {
                  const d = rxData[it.product_id] || {};
                  const controlled = isControlled(it);
                  const canSkip = !controlled && rxMode !== 'block';
                  const mode = canSkip ? (d.mode || 'rx') : 'rx';
                  return (
                    <div key={it.product_id} className="border border-slate-200 rounded-xl p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-black text-slate-800 text-sm flex-1">{it.name}</span>
                        {controlled
                          ? <span className="px-1.5 rounded text-[10px] font-bold bg-red-100 text-red-700">{tfb('pos.rxControlled', 'Nazoratda')}</span>
                          : <span className="px-1.5 rounded text-[10px] font-bold bg-violet-100 text-violet-700">Rx</span>}
                      </div>
                      {canSkip && (
                        <div className="flex gap-4 mb-2 text-sm font-bold text-slate-600">
                          <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="radio" checked={mode === 'rx'} onChange={() => setRxField(it.product_id, 'mode', 'rx')} />
                            {tfb('pos.rxHas', 'Retsept bor')}
                          </label>
                          <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="radio" checked={mode === 'norx'} onChange={() => setRxField(it.product_id, 'mode', 'norx')} />
                            {tfb('pos.rxNone', 'Retseptsiz sotish')}
                          </label>
                        </div>
                      )}
                      {mode === 'rx' && (
                        <div className="grid grid-cols-2 gap-2">
                          <input className={inputCls} placeholder={tfb('pos.rxNumber', 'Retsept raqami')} value={d.number || ''} onChange={e => setRxField(it.product_id, 'number', e.target.value)} />
                          <input className={inputCls} type="date" max={todayLocalIso()} value={d.issued_at || ''} onChange={e => setRxField(it.product_id, 'issued_at', e.target.value)} />
                          <input className={inputCls} placeholder={tfb('pos.rxDoctor', 'Shifokor')} value={d.doctor || ''} onChange={e => setRxField(it.product_id, 'doctor', e.target.value)} />
                          <input className={inputCls} placeholder={tfb('pos.rxClinic', 'Muassasa')} value={d.clinic || ''} onChange={e => setRxField(it.product_id, 'clinic', e.target.value)} />
                          <input className={inputCls} placeholder={tfb('pos.rxPatient', 'Bemor (ixtiyoriy)')} value={d.patient || ''} onChange={e => setRxField(it.product_id, 'patient', e.target.value)} />
                          <select
                            className={inputCls}
                            value={d.blank_type || (controlled ? '' : 'simple')}
                            onChange={e => setRxField(it.product_id, 'blank_type', e.target.value)}
                          >
                            {controlled && <option value="">{tfb('pos.rxBlankPick', 'Blank turini tanlang (majburiy)')}</option>}
                            {!controlled && <option value="simple">{tfb('pos.rxBlankSimple', 'Oddiy blank')}</option>}
                            <option value="form_107">{tfb('pos.rxBlank107', '107-1/u blank')}</option>
                            <option value="form_148">{tfb('pos.rxBlank148', '148-1/u blank')}</option>
                            <option value="special">{tfb('pos.rxBlankSpecial', 'Maxsus blank')}</option>
                          </select>
                        </div>
                      )}
                    </div>
                  );
                })}
                {anyNoRx && (
                  <textarea
                    className={`${inputCls} h-16`}
                    placeholder={tfb('pos.rxReason', 'Retseptsiz sotish sababi (majburiy)')}
                    value={rxReason}
                    onChange={e => setRxReason(e.target.value)}
                  />
                )}
                {rxError && <div className="text-red-600 text-sm font-bold">{rxError}</div>}
              </div>
              <div className="px-4 py-3 border-t border-slate-100 flex gap-3">
                <button onClick={() => { setRxModal(null); setRxError(''); }} className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50">
                  {tfb('common.cancel', 'Bekor qilish')}
                </button>
                <button onClick={confirmRx} className="flex-1 py-2.5 rounded-xl bg-violet-700 hover:bg-violet-800 text-white font-black text-sm">
                  {tfb('pos.rxConfirm', 'Tasdiqlash')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── D2.6: ANALOGLAR OYNASI ── */}
      {pharmacy && analogModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="analog-modal">
          <div className="bg-white rounded-2xl shadow-2xl w-[620px] max-w-[96vw] max-h-[88vh] flex flex-col overflow-hidden">
            <div className="bg-emerald-700 px-5 py-3 text-white flex items-center">
              <div className="flex-1">
                <div className="font-black text-base">{tfb('pos.analogs', 'Analoglar')}</div>
                <div className="text-emerald-100 text-xs">
                  {analogModal.auto ? tfb('pos.analogsAuto', "Qoldiq yo'q — {name} o'rniga:", { name: analogModal.name }) : analogModal.name}
                </div>
              </div>
              <button onClick={() => setAnalogModal(null)} className="w-8 h-8 rounded-full bg-white/20 hover:bg-white/30 font-bold">&times;</button>
            </div>
            <div className="p-3 overflow-y-auto space-y-2">
              {analogModal.loading && <div className="text-center text-slate-400 font-bold py-6">{t('pos.productsLoading')}</div>}
              {!analogModal.loading && analogModal.error && <div className="text-center text-red-500 font-bold py-6">{t('common.error')}</div>}
              {!analogModal.loading && !analogModal.error && analogModal.items.length === 0 && (
                <div className="text-center text-slate-400 font-bold py-6">{tfb('pos.analogsNone', 'Analog topilmadi')}</div>
              )}
              {analogModal.items.map(a => (
                <div key={a.id} className="border border-slate-200 rounded-xl p-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="font-black text-slate-800 text-sm truncate">{a.name}</div>
                    <div className="flex flex-wrap gap-1.5 mt-1 text-[11px] font-bold">
                      <span className="text-blue-700">{fmt(a.sale_price)}</span>
                      <span className={a.in_stock ? 'text-emerald-600' : 'text-red-500'}>
                        {a.in_stock ? `${tfb('pos.stockLabel', 'Qoldiq')}: ${fmt(a.valid_quantity)}` : t('pos.zeroStock')}
                      </span>
                      {a.nearest_expiry && (
                        <span className={`px-1 rounded ${a.expiry_warn ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
                          {a.expiry_warn ? '⚠ ' : ''}{fmtExpiry(a.nearest_expiry)}
                        </span>
                      )}
                      {a.is_rx && <span className="px-1 rounded bg-violet-100 text-violet-700">Rx</span>}
                      {[a.dosage_form, a.strength, a.manufacturer].filter(Boolean).length > 0 && (
                        <span className="text-slate-400">{[a.dosage_form, a.strength, a.manufacturer].filter(Boolean).join(' · ')}</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => addAnalogToCart(a)}
                    disabled={!a.in_stock}
                    className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-black text-xs disabled:opacity-40"
                  >
                    {tfb('pos.analogAdd', 'Savatga')}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── D2.6: SOTUV XATOSI (server 400: muddat, butun quti, markirovka...) ── */}
      {pharmacy && saleError && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="sale-error-modal">
          <div className="bg-white rounded-2xl shadow-2xl w-[480px] max-w-[96vw] overflow-hidden">
            <div className="bg-red-600 px-5 py-3 text-white font-black text-base">
              {saleError.category === 'expiry' ? tfb('pos.errExpiry', "Muddati o'tgan yoki yaroqsiz dori")
                : saleError.category === 'marking' ? tfb('pos.errMarking', 'Markirovka xatosi')
                : saleError.category === 'stock' ? tfb('pos.errStock', 'Qoldiq yetarli emas')
                : tfb('pos.errRejected', 'Sotuv rad etildi')}
            </div>
            <div className="px-5 py-4 text-slate-700 font-semibold text-sm">{saleError.message}</div>
            {saleError.boxFix && (
              <div className="px-5 pb-2 text-xs text-slate-500 font-semibold">
                {tfb('pos.wholeBoxHint', 'Butun quti yetmaydi — dona qilib sotishingiz mumkin.')}
              </div>
            )}
            <div className="px-5 pb-4 pt-2 flex gap-3">
              <button onClick={() => setSaleError(null)} className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50">
                {tfb('common.close', 'Yopish')}
              </button>
              {saleError.boxFix && (
                <button onClick={applyBoxFix} className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-black text-sm">
                  {tfb('pos.sellByPiece', 'Dona qilib sotish')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {markingModal && cart[markingModal.idx] && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-900/70 p-4" onClick={() => setMarkingModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 px-5 py-3.5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-black text-white">{t('wholesale.scanMarkingCode')}</h2>
                <p className="text-red-100 text-xs font-medium">{cart[markingModal.idx].name}</p>
              </div>
              <button onClick={() => setMarkingModal(null)} className="w-8 h-8 bg-white/20 hover:bg-white/30 rounded-lg flex items-center justify-center text-white">
                <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 flex flex-col gap-3">
              <p className="text-sm text-slate-500">
                {t('wholesale.scanDataMatrixHint')}
                {' '}{t('wholesale.required')}: <span className="font-bold text-slate-700">{cart[markingModal.idx].qty}</span> {t('common.piece')}.
              </p>
              <input
                autoFocus
                type="text"
                placeholder={t('wholesale.scanCodePlaceholder')}
                className="w-full border border-slate-300 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-200"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addMarkingCode(markingModal.idx, e.target.value);
                    e.target.value = '';
                  }
                }}
              />
              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
                {(cart[markingModal.idx].marking_codes || []).length === 0 && (
                  <div className="text-xs text-slate-400 text-center py-3">{t('wholesale.noCodeScannedYet')}</div>
                )}
                {(cart[markingModal.idx].marking_codes || []).map((code, ci) => (
                  <div key={ci} className="flex items-center justify-between gap-2 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5">
                    <span className="text-xs font-mono text-slate-700 truncate">{code}</span>
                    <button onClick={() => removeMarkingCode(markingModal.idx, ci)} className="text-red-400 hover:text-red-600 shrink-0">
                      <Ic d="M6 18L18 6M6 6l12 12" cls="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
              <button
                onClick={() => setMarkingModal(null)}
                disabled={!pharmacy && (cart[markingModal.idx].marking_codes || []).length < cart[markingModal.idx].qty}
                className="w-full py-2.5 rounded-xl font-bold text-white bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-300 disabled:cursor-not-allowed"
              >
                {t('wholesale.scannedCloseCount', { done: (cart[markingModal.idx].marking_codes || []).length, qty: cart[markingModal.idx].qty })}
              </button>
            </div>
          </div>
        </div>
      )}

      {variantPickerProduct && (
        <VariantPickerModal
          parent={variantPickerProduct}
          onClose={() => setVariantPickerProduct(null)}
          onSelect={(variant) => {
            setVariantPickerProduct(null);
            selectFormProduct(variant);
          }}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════ */
/* Variant tanlash modali                      */
/* ═══════════════════════════════════════════ */
function VariantPickerModal({ parent, onClose, onSelect }) {
  const { t } = useLang();
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/products/${parent.id}/variants`)
      .then(r => setVariants(Array.isArray(r.data) ? r.data : []))
      .catch(() => {
        // fallback: /products?parent_id=X
        api.get('/products', { params: { parent_id: parent.id, limit: 100 } })
          .then(r => setVariants(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
          .catch(() => setVariants([]));
      })
      .finally(() => setLoading(false));
  }, [parent.id]);

  // Rang × Razmer guruhlash
  const colors = [...new Set(variants.map(v => v.color).filter(Boolean))];
  const sizes  = [...new Set(variants.map(v => v.size).filter(Boolean))];

  const getVariant = (color, size) =>
    variants.find(v => v.color === color && v.size === size) ||
    variants.find(v => v.color === color && !size) ||
    variants.find(v => !color && v.size === size);

  const fmt = v => Number(v || 0).toLocaleString('uz-UZ');

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-white font-black text-lg">{parent.name}</h2>
            <p className="text-blue-200 text-xs mt-0.5">{t('wholesale.selectSizeAndColor')}</p>
          </div>
          <button onClick={onClose} className="w-9 h-9 bg-white/20 hover:bg-white/30 rounded-xl flex items-center justify-center transition-colors">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"/>
            </div>
          ) : variants.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <svg className="w-16 h-16 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/></svg>
              <p className="font-semibold">{t('wholesale.variantsNotFound')}</p>
            </div>
          ) : colors.length > 0 && sizes.length > 0 ? (
            /* Jadval ko'rinishi (Rang × Razmer) */
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left text-xs font-bold text-slate-500 pb-3 pr-3">{t('wholesale.colorSlashSize')}</th>
                    {sizes.map(s => (
                      <th key={s} className="text-center text-xs font-bold text-blue-700 bg-blue-50 rounded-lg px-3 py-2 min-w-[80px]">{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {colors.map(color => (
                    <tr key={color}>
                      <td className="pr-3 py-1.5">
                        <span className="text-sm font-bold text-slate-700">{color}</span>
                      </td>
                      {sizes.map(size => {
                        const v = getVariant(color, size);
                        return (
                          <td key={size} className="text-center py-1.5 px-1">
                            {v ? (
                              <button
                                onClick={() => onSelect(v)}
                                className="w-full px-2 py-2 bg-white border-2 border-slate-200 hover:border-blue-500 hover:bg-blue-50 rounded-xl transition-all group">
                                <div className="text-xs font-black text-blue-700">{fmt(v.sale_price)}</div>
                                <div className={`text-[10px] font-semibold mt-0.5 ${Number(v.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                                  {Number(v.stock_quantity) > 0 ? `${fmt(v.stock_quantity)} ${t('common.piece')}` : t('wholesale.outOfStock')}
                                </div>
                              </button>
                            ) : (
                              <div className="px-2 py-2 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-slate-300 text-xs">—</div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            /* Oddiy ro'yxat (faqat size yoki faqat color) */
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {variants.map(v => (
                <button key={v.id} onClick={() => onSelect(v)}
                  className="p-4 bg-white border-2 border-slate-200 hover:border-blue-500 hover:bg-blue-50 rounded-2xl transition-all text-left">
                  <div className="font-bold text-slate-800 text-sm">{v.size || v.color || v.name}</div>
                  <div className="text-blue-700 font-black mt-1">{fmt(v.sale_price)} UZS</div>
                  <div className={`text-xs font-semibold mt-1 ${Number(v.stock_quantity) <= 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                    {Number(v.stock_quantity) > 0 ? `${fmt(v.stock_quantity)} dona` : 'Tugagan'}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-between items-center bg-slate-50">
          <span className="text-xs text-slate-500 font-medium">{t('wholesale.variantsCount', { count: variants.length })}</span>
          <button onClick={onClose} className="px-5 py-2.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-xl text-sm transition-colors">
            {t('common.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
}

function SaleDetailContent({ saleId }) {
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/sales/${saleId}`).then(r => setData(r.data)).catch(() => { }).finally(() => setLoading(false));
  }, [saleId]);

  if (loading) return <div className="flex justify-center py-16"><div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>;
  if (!data) return <div className="text-center py-16 text-slate-400">{t('common.noData')}</div>;

  const fmtL = v => Number(v || 0).toLocaleString('uz-UZ');
  const debt = Number(data.total_amount) - Number(data.paid_amount);

  return (
    <div className="space-y-4">
      {data.note && <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-sm text-blue-700 font-medium">📝 {data.note}</div>}
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            <th className="text-left px-4 py-2.5 text-xs font-bold text-slate-500">{t('wholesale.product')}</th>
            <th className="text-center px-3 py-2.5 text-xs font-bold text-slate-500">{t('common.quantity')}</th>
            <th className="text-right px-3 py-2.5 text-xs font-bold text-slate-500">{t('common.price')}</th>
            <th className="text-right px-3 py-2.5 text-xs font-bold text-slate-500">{t('common.discount')}</th>
            <th className="text-right px-4 py-2.5 text-xs font-bold text-slate-500">{t('common.total')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {(data.items || []).map(it => (
            <tr key={it.id} className="hover:bg-slate-50">
              <td className="px-4 py-3 font-semibold text-slate-800">{it.product_name}</td>
              <td className="px-3 py-3 text-center text-slate-600">{fmt(it.quantity)}</td>
              <td className="px-3 py-3 text-right text-slate-600">{fmtL(it.unit_price)} s</td>
              <td className="px-3 py-3 text-right text-amber-600">{it.discount > 0 ? `−${fmtL(it.discount)} s` : '—'}</td>
              <td className="px-4 py-3 text-right font-bold text-slate-800">{fmtL(it.subtotal)} s</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="bg-slate-50 rounded-xl p-4 space-y-2">
        {[
          { l: t('wholesale.totalAmount'), v: fmtL(data.total_amount) + ' s', c: 'font-bold text-slate-800' },
          Number(data.discount_amount) > 0 && { l: t('common.discount'), v: '−' + fmtL(data.discount_amount) + ' s', c: 'text-amber-600 font-semibold' },
          { l: t('common.paid'), v: fmtL(data.paid_amount) + ' s', c: 'font-bold text-emerald-700' },
          debt > 0 && { l: t('common.debt'), v: fmtL(debt) + ' s', c: 'font-bold text-red-600' },
        ].filter(Boolean).map((r, i) => (
          <div key={i} className="flex justify-between text-sm">
            <span className="text-slate-500">{r.l}</span><span className={r.c}>{r.v}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
        <button
          onClick={async () => {
            toast.info("PDF tayyorlanmoqda...");
            try {
              const res = await api.get(`/sales/${data.id}/pdf`, { responseType: 'blob' });
              const cust = data.customer_name || data.contractor_name || 'Mijoz';
              const datePart = (data.created_at || '').replace(/[- :]/g, '_').slice(0, 19);
              const fallbackName = `Sotuv_${cust.replace(/[^\w\s-]/g, '').trim().replace(/[-\s]+/g, '_')}_${datePart}.pdf`;
              const filename = filenameFromDisposition(res.headers && (res.headers['content-disposition'] || res.headers['Content-Disposition']), fallbackName);
              const saveAs = await loadSaveAs();
              saveAs(new Blob([res.data], { type: 'application/pdf' }), filename);
              toast.success("PDF muvaffaqiyatli yuklab olindi");
            } catch (err) {
              const msg = await blobErrorMessage(err);
              console.error('Sotuv PDF xatosi:', err, msg);
              toast.error(`PDF yuklanmadi: ${msg}`);
            }
          }}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200/80 rounded-xl text-xs font-bold transition-all shadow-2xs"
        >
          <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          PDF yuklab olish
        </button>
      </div>
    </div>
  );
}

