import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../api/axios';
import { useLang } from '../context/LangContext';
import { matchesSearch } from '../utils/translit';
import { getDebtEntries, hasAnyDebt } from '../utils/debt';

/**
 * Mijoz tanlash (T3.8) — serverdagi qidiruv: `GET /customers?search=<q>&limit=20`.
 * Avval klientda yuklangan 200/500/2000 talik ro'yxat ichida qidirilardi, undan keyingi mijozlar
 * topilmasdi. Endi:
 *  - onlayn: 300 ms debounce + AbortController bilan serverdan (ism, telefon yoki karta raqami);
 *  - tanlangan mijoz ro'yxatda bo'lmasa alohida `GET /customers/{id}` bilan olinadi;
 *  - oflayn (`isOnline === false`): `customers` (oflayn zaxira ro'yxat) bo'yicha klientda qidiradi.
 *
 * Props:
 *  - value        — tanlangan mijoz id (yoki '')
 *  - onChange(id, customer) — tanlanganda; tozalanganda ('', null)
 *  - onResolve(customer)    — tanlangan mijoz serverdan olinganda (ixtiyoriy)
 *  - customers    — oflayn zaxira ro'yxat (ixtiyoriy)
 *  - isOnline     — default: navigator.onLine
 *  - variant      — 'pos' (katta, kassa) | 'compact' (jadval/forma)
 */
const normCard = (s) => String(s || '').replace(/\D/g, '');
const PAGE_LIMIT = 20;

const toList = (data) => (Array.isArray(data) ? data : (data?.items || []));

const STYLES = {
  pos: {
    box: 'flex items-center border-[2px] border-slate-300 rounded-xl bg-white overflow-hidden focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-500/20 transition-all pr-2',
    input: 'w-full px-3 py-3 text-base font-bold text-slate-700 outline-none bg-transparent placeholder:text-slate-400',
    clear: 'text-slate-400 hover:text-red-500 font-bold p-1',
    list: 'absolute top-full mt-2 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto',
    item: 'w-full text-left px-4 py-3 hover:bg-blue-50 border-b border-slate-50 last:border-0 flex items-center justify-between transition-colors',
    name: 'text-sm font-bold text-slate-800',
    sub: 'text-xs text-slate-500 font-medium',
    debt: 'text-xs text-red-600 font-bold bg-red-50 px-2.5 py-1 rounded-lg',
    empty: 'px-4 py-3 text-sm text-slate-500 text-center font-medium',
  },
  compact: {
    box: 'flex items-center border border-slate-200 rounded-lg bg-white overflow-hidden focus-within:ring-2 focus-within:ring-blue-400',
    input: 'flex-1 px-3 py-1.5 text-sm outline-none bg-transparent min-w-0',
    clear: 'px-2 text-slate-400 hover:text-red-400 text-lg leading-none',
    list: 'absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto',
    item: 'w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-slate-50 last:border-0 flex items-center justify-between',
    name: 'text-sm font-medium text-slate-800',
    sub: 'text-xs text-slate-400',
    debt: 'text-xs text-red-500 font-medium ml-2',
    empty: 'px-4 py-3 text-sm text-slate-400',
  },
};

export default function CustomerPicker({
  value, onChange, onResolve, customers = [], isOnline, placeholder, variant = 'compact',
}) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const st = STYLES[variant] || STYLES.compact;
  const online = isOnline === undefined ? (typeof navigator === 'undefined' ? true : navigator.onLine) : isOnline;
  const ph = placeholder || t('ops.nameOrPhone');

  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState(null);       // null = serverdan hali natija yo'q
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(null);       // ro'yxatda yo'q tanlangan mijoz (GET /customers/{id})
  const ref = useRef(null);

  const hasValue = value !== undefined && value !== null && value !== '';
  const selected = hasValue
    ? (customers.find(c => String(c.id) === String(value))
      || (fetched && String(fetched.id) === String(value) ? fetched : null))
    : null;

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  // Tanlangan mijoz ro'yxatda bo'lmasa (masalan 500-dan keyingi) — alohida olamiz
  useEffect(() => {
    if (!hasValue) return undefined;
    if (customers.some(c => String(c.id) === String(value)) || (fetched && String(fetched.id) === String(value))) return undefined;
    if (!online) return undefined;
    const ctrl = new AbortController();
    // Backendda yagona mijozni olish: POST /customers/{id} (GET marshruti yo'q)
    api.post(`/customers/${value}`, null, { signal: ctrl.signal, _silent: true, _suppressToast: true })
      .then(r => { setFetched(r.data); if (onResolve) onResolve(r.data); })
      .catch(() => { /* topilmasa nom ko'rinmaydi, id saqlanadi */ });
    return () => ctrl.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, online]);

  const select = useCallback((c) => {
    if (c) setFetched(c);
    onChange(c ? c.id : '', c || null);
    setQ('');
    setOpen(false);
  }, [onChange]);

  // Onlayn qidiruv: 300 ms debounce + oldingi so'rovni bekor qilish
  useEffect(() => {
    if (!open || !online) { setResults(null); setLoading(false); return undefined; }
    const term = q.trim();
    const ctrl = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      const params = { limit: PAGE_LIMIT };
      if (term) params.search = term;
      api.get('/customers', { params, signal: ctrl.signal, _silent: true, _suppressToast: true })
        .then(r => {
          const list = toList(r.data);
          setResults(list);
          setLoading(false);
          // Karta skaneri: aniq bitta mijoz topilsa avtomatik tanlanadi
          const digits = normCard(term);
          if (digits.length >= 8 && /^[\d\s-]+$/.test(term) && list.length === 1) select(list[0]);
        })
        .catch((err) => {
          if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
          setResults(null);   // xato: klient tomonidagi zaxira ro'yxat ko'rsatiladi
          setLoading(false);
        });
    }, term ? 300 : 0);
    return () => { clearTimeout(timer); ctrl.abort(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, open, online]);

  // Oflayn (yoki server javobi hali yo'q): zaxira ro'yxat bo'yicha klientda qidirish
  const nq = normCard(q);
  const localFiltered = q.trim()
    ? customers.filter(c => matchesSearch(c.name, q) || (c.phone && c.phone.includes(q))
      || (c.card_number && (c.card_number.includes(q) || (nq.length >= 4 && normCard(c.card_number).includes(nq))))).slice(0, 12)
    : customers.slice(0, 12);
  const shown = online && results ? results : localFiltered;

  const handleInput = (e) => {
    const input = e.target.value;
    setQ(input);
    setOpen(true);
    if (!input && hasValue) onChange('', null);
  };

  return (
    <div className="relative w-full" ref={ref}>
      <div className={st.box}>
        <input
          value={open ? q : (selected ? selected.name : '')}
          onChange={handleInput}
          onFocus={() => setOpen(true)}
          placeholder={ph}
          className={st.input}
        />
        {selected && <button type="button" onClick={() => select(null)} className={st.clear}>×</button>}
      </div>
      {open && (
        <div className={st.list}>
          {!online && (
            <div className="px-4 py-1.5 text-xs text-amber-700 bg-amber-50">
              {tf('customerPicker.offline', "Oflayn rejim: saqlangan ro'yxatdan qidirilmoqda")}
            </div>
          )}
          {shown.length === 0 ? (
            <div className={st.empty}>
              {loading ? tf('customerPicker.searching', 'Qidirilmoqda...') : t('pos.customerNotFound')}
            </div>
          ) : shown.map(c => (
            <button type="button" key={c.id} onMouseDown={() => select(c)} className={st.item}>
              <div>
                <div className={st.name}>{c.name}</div>
                {c.phone && <div className={st.sub}>{c.phone}</div>}
              </div>
              {hasAnyDebt(c) && (
                <div className="flex flex-col items-end gap-1">
                  {getDebtEntries(c).map(({ currency, amount }) => (
                    <span key={currency} className={st.debt}>
                      {t('common.debt')}: {Number(amount || 0).toLocaleString('uz-UZ')} {currency}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
