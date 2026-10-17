import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import BranchSelect from '../../components/BranchSelect';
import { useBranch } from '../../context/BranchContext';
import toast from 'react-hot-toast';
import { WAREHOUSE_TYPES as WH_TYPE_DEFS } from '../../constants/warehouseTypes';
import { useBranches } from '../../hooks/useBranches';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ');
// T1.3: ombor varianti "Ombor — Filial" ko'rinishida (bir xil nomli omborlar chalkashmasin)
const whLabel = (w) => (w.branch_name ? `${w.name} — ${w.branch_name}` : w.name);
// Kalit i18n fayllarida hali bo'lmasa — o'zbekcha zaxira matn
const tOr = (t, key, fallback) => { const v = t(key); return v === key ? fallback : v; };
// Yuklash xatosi (T3.5): jim yutmaymiz — toast (interceptor 422/5xx uchun o'zi chiqaradi) va xato holati
const loadErrToast = (e, t) => {
  const st = e?.response?.status;
  if (!(st === 422 || st >= 500)) toast.error(e?.response?.data?.detail || t('common.loadError'));
};
const LoadError = ({ t, onRetry }) => (
  <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
    <p className="text-sm text-red-500">{t('common.loadError')}</p>
    <button type="button" onClick={onRetry}
      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl transition-colors">
      {t('common.retry')}
    </button>
  </div>
);
const fmtDate = (s) =>
  s
    ? new Date(s).toLocaleString('ru-RU', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      }).replace(',', '')
    : '—';

// ─── STATUS BADGE ──────────────────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const { t } = useLang();
  const map = {
    pending:   { label: t('ombor.statusPending'),   cls: "bg-amber-100 text-amber-700"  },
    completed: { label: t('ombor.statusCompleted'), cls: "bg-emerald-100 text-emerald-700" },
    cancelled: { label: t('ombor.statusCancelled'), cls: "bg-red-100 text-red-600"       },
    in:        { label: t('ops.incoming'),          cls: "bg-emerald-100 text-emerald-700" },
    out:       { label: t('ops.outgoing'),           cls: "bg-blue-100 text-blue-700"     },
    adjust:    { label: t('ombor.statusAdjust'),     cls: "bg-blue-100 text-blue-700"     },
    // T3.3: transfer holatlari (backend: pending / in_transit / received / cancelled)
    received:  { label: t('ombor.statusReceived'),  cls: "bg-emerald-100 text-emerald-700" },
    in_transit: { label: t('ombor.statusInTransit'), cls: "bg-blue-100 text-blue-700"     },
    transfer_in:  { label: t('ops.incoming'),       cls: "bg-emerald-100 text-emerald-700" },
    transfer_out: { label: t('ops.outgoing'),       cls: "bg-blue-100 text-blue-700"     },
  };
  // Harakat turlari backendda katta harfda keladi (IN / OUT / TRANSFER_IN ...)
  const m = map[status] || map[String(status ?? '').toLowerCase()] || { label: status, cls: "bg-slate-100 text-slate-600" };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${m.cls}`}>
      {m.label}
    </span>
  );
};

// ─── TABS (will be rendered inside component with t()) ────────────────────────────
const TABS = [
  { id: 'qoldiq',    label: 'Qoldiqlar',   icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
  { id: 'kirim',     label: 'Kirim',        icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12' },
  { id: 'chiqim',    label: "Chiqim",       icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4' },
  { id: 'kochirish', label: "Ko'chirish",   icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
  { id: 'omborlar',  label: 'Omborlar',     icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' },
];

// ─── QOLDIQLAR TAB ─────────────────────────────────────────────────────────
const PAGE_SIZE = 200;   // /inventory/stock sahifasi (backend limiti 500)
function QoldiqlarTab() {
  const { t } = useLang();
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch]   = useState('');
  const [lowOnly, setLowOnly] = useState(false);
  // T2.3: filial/ombor filtri va sahifalash ("Yana yuklash")
  const { branches } = useBranches();   // T3.8: yagona filial hooki (keshlangan)
  const [warehouses, setWarehouses] = useState([]);
  const [branchId, setBranchId]     = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [hasMore, setHasMore]       = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const buildParams = useCallback((skip) => ({
    search: search || undefined, low_stock_only: lowOnly, limit: PAGE_SIZE, skip,
    branch_id: branchId || undefined, warehouse_id: warehouseId || undefined,
  }), [search, lowOnly, branchId, warehouseId]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const { data } = await api.get('/inventory/stock', { params: buildParams(0), _silent: true, _suppressToast: true });
      setItems(data);
      setHasMore(data.length >= PAGE_SIZE);
    } catch (e) { setLoadError(true); loadErrToast(e, t); }
    finally { setLoading(false); }
  }, [buildParams, t]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const { data } = await api.get('/inventory/stock', { params: buildParams(items.length), _silent: true, _suppressToast: true });
      setItems(prev => [...prev, ...data]);
      setHasMore(data.length >= PAGE_SIZE);
    } catch (e) { loadErrToast(e, t); }
    finally { setLoadingMore(false); }
  };

  useEffect(() => { load(); }, [load]);

  // Ombor selektori tanlangan filial omborlari bilan to'ldiriladi
  useEffect(() => {
    api.get('/inventory/warehouses', { params: { scope: 'all', ...(branchId ? { branch_id: branchId } : {}) }, _silent: true })
      .catch(() => api.get('/inventory/warehouses', { params: branchId ? { branch_id: branchId } : {}, _silent: true }))
      .then(r => setWarehouses(r.data || []))
      .catch(() => setWarehouses([]));
  }, [branchId]);

  const onBranchChange = (v) => { setBranchId(v); setWarehouseId(''); };

  // Mahsulot darajasida (bir mahsulot bir necha omborda/variantda bo'lishi mumkin)
  const uniqueProducts = new Set(items.map(i => i.product_id));
  const lowProducts = new Set(items.filter(i => i.is_low_stock).map(i => i.product_id));

  return (
    <div className="space-y-4">
      {/* filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t('ombor.searchPlaceholder')}
            className="w-full pl-9 pr-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <BranchSelect value={branchId} onChange={onBranchChange} branches={branches} />
        <select
          value={warehouseId}
          onChange={e => setWarehouseId(e.target.value)}
          className="px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">{t('common.allWarehouses')}</option>
          {warehouses.map(w => <option key={w.id} value={String(w.id)}>{whLabel(w)}</option>)}
        </select>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" checked={lowOnly} onChange={e => setLowOnly(e.target.checked)} className="w-4 h-4 rounded text-blue-600" />
          <span className="text-sm text-slate-600 font-medium">{t('product.lowStock')}</span>
        </label>
        <button onClick={load} className="px-4 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors">
          {t('common.refresh')}
        </button>
      </div>

      {/* summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: t('dashboard.totalProducts'), value: uniqueProducts.size, color: "indigo" },
          { label: t('product.lowStock'),         value: lowProducts.size, color: "amber" },
          { label: t('product.active'),            value: uniqueProducts.size - lowProducts.size, color: "emerald" },
        ].map(c => (
          <div key={c.label} className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
            <p className="text-xs text-slate-500 font-medium">{c.label}</p>
            <p className={`text-2xl font-bold mt-1 text-${c.color}-600`}>{c.value}</p>
          </div>
        ))}
      </div>

      {/* table */}
      <div className="bg-white rounded-xl border border-slate-100 overflow-x-auto shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loadError ? (
          <LoadError t={t} onRetry={load} />
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.product') || 'Mahsulot'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SKU</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{tOr(t, 'warehouse.warehouseCol', 'Ombor')}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.balance') || 'Qoldiq'}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.min')}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{tOr(t, 'ombor.max', 'Max')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.status') || 'Holat'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.updated')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map((it, i) => (
                <tr key={`${it.product_id}-${it.variant_id ?? 0}-${it.warehouse_id ?? 0}`} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-400">{i + 1}</td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{it.product_name}</td>
                  <td className="px-4 py-3 text-sm text-slate-500 font-mono">{it.product_sku || '—'}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{it.warehouse_name || '—'}</td>
                  <td className="px-4 py-3 text-sm text-right font-bold text-slate-800">{fmt(it.quantity)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{fmt(it.min_stock)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{it.max_stock == null ? '—' : fmt(it.max_stock)}</td>
                  <td className="px-4 py-3">
                    {it.is_low_stock
                      ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-100 text-red-600">⚠ {t('product.lowStock')}</span>
                      : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">✓ {t('common.active')}</span>
                    }
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(it.updated_at)}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      {hasMore && !loading && (
        <div className="flex justify-center">
          <button onClick={loadMore} disabled={loadingMore}
            className="px-5 py-2 bg-white border border-slate-200 text-sm font-semibold text-slate-600 rounded-xl hover:bg-slate-50 disabled:opacity-60">
            {loadingMore ? '...' : tOr(t, 'warehouse.loadMore', 'Yana yuklash')}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── HARAKATLAR (Kirim / Chiqim) TAB ──────────────────────────────────────
// T3.3: Kirim tabi — IN + TRANSFER_IN, Chiqim tabi — OUT + TRANSFER_OUT (backend `type` ko'p qiymatli)
const MOVEMENT_TYPES = { in: ['IN', 'TRANSFER_IN'], out: ['OUT', 'TRANSFER_OUT'] };

function MovementsTab({ type }) {
  const { t } = useLang();
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const { data } = await api.get('/inventory/movements', {
        params: { type: MOVEMENT_TYPES[type] || String(type).toUpperCase(), limit: 100 },
        paramsSerializer: { indexes: null },   // type=IN&type=TRANSFER_IN
        _silent: true, _suppressToast: true, _noCache: true,
      });
      setItems(data);
    } catch (e) { setLoadError(true); loadErrToast(e, t); }
    finally { setLoading(false); }
  }, [type, t]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {type === 'in' ? t('ops.incoming') : t('ops.outgoing')}
        </p>
        <button onClick={load} className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors">
          {t('common.refresh')}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-x-auto shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loadError ? (
          <LoadError t={t} onRetry={load} />
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.product') || 'Mahsulot'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('common.type')}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.qty') || 'Miqdor'}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.before')}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.after')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('movements.warehouse')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.reason')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.date') || 'Sana'}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map((it, i) => (
                <tr key={it.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-400">{i + 1}</td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{it.product_name}</td>
                  <td className="px-4 py-3"><StatusBadge status={it.type} /></td>
                  <td className="px-4 py-3 text-sm text-right font-bold text-slate-800">{fmt(it.quantity)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{fmt(it.qty_before)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{fmt(it.qty_after)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{it.warehouse_name || '—'}</td>
                  <td className="px-4 py-3 text-sm text-slate-500 max-w-[160px] truncate">{it.reason || '—'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(it.created_at)}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── MAHSULOT QIDIRUV COMBOBOX (T3.3) ──────────────────────────────────────
// Serverdan qidiradi (debounce 300ms): GET /products/?search=&warehouse_id=<manba>&limit=30.
// warehouse_id berilganda stock_quantity — shu ombor qoldig'i.
function ProductCombo({ warehouseId, value, onSelect, disabled }) {
  const { t } = useLang();
  const [q, setQ]             = useState('');
  const [open, setOpen]       = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  useEffect(() => {
    if (!open || !warehouseId) return undefined;
    let alive = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await api.get('/products/', {
          params: { search: q.trim() || undefined, warehouse_id: warehouseId, limit: 30 },
          _silent: true, _suppressToast: true, _noCache: true,
        });
        const list = Array.isArray(data) ? data : (data?.items || []);
        if (alive) setResults(list.filter(p => p.product_type !== 'sell'));
      } catch (e) {
        if (alive) { setResults([]); loadErrToast(e, t); }
      } finally { if (alive) setLoading(false); }
    }, q.trim() ? 300 : 0);
    return () => { alive = false; clearTimeout(timer); };
  }, [q, open, warehouseId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative flex-1 min-w-0" ref={ref}>
      <input
        value={open ? q : (value?.name || '')}
        disabled={disabled}
        onChange={e => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => { setQ(''); setOpen(true); }}
        placeholder={disabled ? tOr(t, 'ombor.selectSourceFirst', 'Avval manba omborni tanlang') : t('ombor.selectProductEllipsis')}
        className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-50 disabled:text-slate-400"
      />
      {open && !disabled && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 max-h-60 overflow-y-auto">
          {loading && results.length === 0 ? (
            <div className="px-3 py-3 text-xs text-slate-400 text-center">{t('common.loading')}</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-3 text-xs text-slate-400 text-center">{q.trim() ? `«${q.trim()}» ${t('ops.notFoundBy')}` : t('common.noData')}</div>
          ) : results.map(p => (
            <button key={p.id} type="button"
              onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
              className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-800 truncate">{p.name}</div>
                <div className="text-[11px] text-slate-400 truncate">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div>
              </div>
              <div className={`text-xs font-semibold shrink-0 ${Number(p.stock_quantity) > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                {fmt(p.stock_quantity)} {p.unit || ''}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── KO'CHIRISH TAB ────────────────────────────────────────────────────────
const EMPTY_ITEM = { product_id: '', product: null, variant_id: '', quantity: '' };

function KochirTab() {
  const { t } = useLang();
  const [transfers, setTransfers]       = useState([]);
  const [warehouses, setWarehouses]     = useState([]);
  // T1.3: maqsad ombor — korxonaning barcha filiallari omborlari (scope=all); manba — joriy filial konteksti
  const [targetWarehouses, setTargetWarehouses] = useState([]);
  const [loading, setLoading]           = useState(true);
  const [loadError, setLoadError]       = useState(false);
  const [showModal, setShowModal]       = useState(false);
  const [form, setForm]                 = useState({ from_warehouse_id: '', to_warehouse_id: '', note: '', items: [{ ...EMPTY_ITEM }] });
  const [saving, setSaving]             = useState(false);
  const [err, setErr]                   = useState('');
  /* detail state reserved for future transfer detail view */

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const [tr, wh, whAll] = await Promise.all([
        api.get('/transfers', { params: { limit: 50 }, _silent: true, _suppressToast: true }),
        api.get('/inventory/warehouses', { _silent: true, _suppressToast: true }),
        api.get('/inventory/warehouses', { params: { scope: 'all' }, _silent: true, _suppressToast: true }).catch(() => null),
      ]);
      setTransfers(tr.data);
      setWarehouses(wh.data);
      setTargetWarehouses((whAll?.data) || wh.data);
    } catch (e) { setLoadError(true); loadErrToast(e, t); }
    finally { setLoading(false); }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const addItem = () => setForm(f => ({ ...f, items: [...f.items, { ...EMPTY_ITEM }] }));
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const setItem = (idx, key, val) => setForm(f => {
    const items = [...f.items];
    items[idx] = { ...items[idx], [key]: val };
    if (key === 'product_id') items[idx].variant_id = ''; // mahsulot almashtirilsa variant tozalanadi
    return { ...f, items };
  });
  // T3.3: qidiruv natijasidan mahsulot tanlash (stock_quantity — manba ombor qoldig'i)
  const pickProduct = (idx, p) => setForm(f => {
    const items = [...f.items];
    items[idx] = { ...items[idx], product_id: p.id, product: p, variant_id: '' };
    return { ...f, items };
  });
  // Manba ombor o'zgarsa qoldiqlar eskirgan — qatorlar tozalanadi
  const setFromWarehouse = (val) => setForm(f => (
    String(f.from_warehouse_id) === String(val) ? f : { ...f, from_warehouse_id: val, items: [{ ...EMPTY_ITEM }] }
  ));

  const submit = async () => {
    if (!form.from_warehouse_id || !form.to_warehouse_id) { setErr(t('ombor.selectWarehouses')); return; }
    if (form.from_warehouse_id === form.to_warehouse_id) { setErr(t('ombor.sameWarehouseError')); return; }
    const validItems = form.items.filter(i => i.product_id && Number(i.quantity) > 0);
    if (!validItems.length) { setErr(t('ombor.atLeastOneProduct')); return; }
    // Variantli mahsulotda variant tanlanishi shart (aks holda qaysi variant
    // ko'chirilayotgani noaniq bo'lib, qoldiq noto'g'ri joyga tushib qoladi)
    const missingVariant = validItems.find(i => i.product?.variants?.length > 0 && !i.variant_id);
    if (missingVariant) { setErr(tOr(t, 'ombor.selectVariantError', 'Variant tanlang')); return; }
    // Manba ombor qoldig'i (qidiruvdan kelgan, shu ombor bo'yicha) dan oshmasin
    const overStock = validItems.find(i => !i.product?.variants?.length && Number(i.quantity) > Number(i.product?.stock_quantity ?? 0));
    if (overStock) { setErr(`${overStock.product?.name}: ${t('ops.qtyExceedsStock')} (${fmt(overStock.product?.stock_quantity)})`); return; }
    setSaving(true); setErr('');
    try {
      await api.post('/transfers', {
        from_warehouse_id: Number(form.from_warehouse_id),
        to_warehouse_id: Number(form.to_warehouse_id),
        note: form.note,
        items: validItems.map(i => ({
          product_id: Number(i.product_id),
          variant_id: i.variant_id ? Number(i.variant_id) : null,
          quantity: Number(i.quantity),
        })),
      });
      setShowModal(false);
      setForm({ from_warehouse_id: '', to_warehouse_id: '', note: '', items: [{ ...EMPTY_ITEM }] });
      load();
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  // T4.1: pending -> in_transit (faqat manba ombor kamayadi)
  const send = async (id) => {
    try { await api.post(`/transfers/${id}/send`); toast.success(tOr(t, 'transfers.sentOk', 'Transfer yuborildi')); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };
  // T4.1: yo'ldagi transferni to'liq qabul qilish (haqiqiy miqdor/kamomad — Operatsiyalar > Transferlar)
  const receive = async (id) => {
    if (!window.confirm(tOr(t, 'transfers.receiveFullConfirm', "Hamma tovar to'liq qabul qilinganini tasdiqlaysizmi? Kamomad bo'lsa Operatsiyalar bo'limida haqiqiy miqdorni kiriting."))) return;
    try { await api.post(`/transfers/${id}/receive`, { items: [] }); toast.success(tOr(t, 'transfers.receivedOk', 'Transfer qabul qilindi')); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };
  const cancel = async (id, received = false) => {
    // T3.3: qabul qilingan (received) transfer bekor qilinsa qoldiq manba omborga qaytadi
    // T4.1: yo'lda (in_transit) bekor qilinsa yuborilgan miqdor manba omborga qaytadi
    if (!window.confirm(received ? tOr(t, 'ombor.cancelReceivedConfirm', "Qabul qilingan transfer bekor qilinadi va qoldiq manba omborga qaytariladi. Davom etasizmi?") : t('ombor.cancelTransferConfirm'))) return;
    try { await api.post(`/transfers/${id}/cancel`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{t('ombor.transferBetweenWarehouses')}</p>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('ops.newTransfer')}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-x-auto shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loadError ? (
          <LoadError t={t} onRetry={load} />
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">№</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('warehouse.from')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('warehouse.destination')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.status') || 'Holat'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.date') || 'Sana'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {transfers.map((tr) => (
                <tr key={tr.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm font-mono text-slate-700 font-semibold">{tr.number}</td>
                  <td className="px-4 py-3 text-sm text-slate-700">{whLabel({ name: tr.from_warehouse_name, branch_name: tr.from_branch_name })}</td>
                  <td className="px-4 py-3 text-sm text-slate-700">{whLabel({ name: tr.to_warehouse_name, branch_name: tr.to_branch_name })}</td>
                  <td className="px-4 py-3"><StatusBadge status={tr.status} /></td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(tr.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      {/* T4.1: tugmalar holat va filial ruxsatiga qarab (server can_send / can_receive / can_cancel) */}
                      {tr.status === 'pending' && tr.can_send && (
                        <button onClick={() => send(tr.id)}
                          className="px-2.5 py-1 text-xs font-semibold bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition-colors">
                          {tOr(t, 'transfers.send', 'Yuborish')}
                        </button>
                      )}
                      {tr.status === 'in_transit' && tr.can_receive && (
                        <button onClick={() => receive(tr.id)}
                          className="px-2.5 py-1 text-xs font-semibold bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors">
                          {tOr(t, 'transfers.receive', 'Qabul qilish')}
                        </button>
                      )}
                      {(tr.status === 'pending' || tr.status === 'in_transit') && tr.can_cancel && (
                        <button onClick={() => cancel(tr.id)}
                          className="px-2.5 py-1 text-xs font-semibold bg-red-100 text-red-600 rounded-lg hover:bg-red-200 transition-colors">
                          {t('common.cancel')}
                        </button>
                      )}
                      {tr.status === 'received' && tr.can_cancel && (
                        <button onClick={() => cancel(tr.id, true)}
                          className="px-2.5 py-1 text-xs font-semibold bg-red-100 text-red-600 rounded-lg hover:bg-red-200 transition-colors">
                          {tOr(t, 'ombor.cancelReceived', 'Bekor qilish (qoldiqni qaytarish)')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {transfers.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Create Transfer Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-800">{t('ops.newTransfer')}</h3>
              <button onClick={() => { setShowModal(false); setErr(''); }} className="text-slate-400 hover:text-slate-600">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">{t('ombor.fromWarehouse')}</label>
                  <select value={form.from_warehouse_id} onChange={e => setFromWarehouse(e.target.value)}
                    className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="">{t('admin.dict.select') || 'Tanlang...'}</option>
                    {warehouses.map(w => <option key={w.id} value={w.id}>{whLabel(w)}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">{t('ombor.toWarehouse')}</label>
                  <select value={form.to_warehouse_id} onChange={e => setForm(f => ({...f, to_warehouse_id: e.target.value}))}
                    className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="">{t('admin.dict.select') || 'Tanlang...'}</option>
                    {targetWarehouses.map(w => <option key={w.id} value={w.id}>{whLabel(w)}</option>)}
                  </select>
                  {targetWarehouses.length <= 1 && (
                    <p className="mt-1 text-xs text-amber-600">{tOr(t, 'ombor.noTargetWarehouse', "Maqsad ombor yo'q — avval boshqa ombor yarating")}</p>
                  )}
                </div>
              </div>
              {(() => {
                const fw = warehouses.find(w => String(w.id) === String(form.from_warehouse_id));
                const tw = targetWarehouses.find(w => String(w.id) === String(form.to_warehouse_id));
                return fw?.branch_id && tw?.branch_id && fw.branch_id !== tw.branch_id ? (
                  <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2">
                    {tOr(t, 'transfers.twoStepHint', "Boshqa filialga ko'chirish ikki bosqichli: yuborilgach tovar \"yo'lda\" bo'ladi, qoldiq esa qabul qiluvchi filial tasdiqlagandan keyin o'tadi.")}
                  </p>
                ) : null;
              })()}
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">{t('ombor.noteOptional')}</label>
                <input value={form.note} onChange={e => setForm(f => ({...f, note: e.target.value}))}
                  placeholder={t('ombor.reasonOrNotePlaceholder')}
                  className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.products')}</label>
                  <button onClick={addItem} className="text-xs text-blue-600 font-semibold hover:text-blue-800">+ {t('common.add')}</button>
                </div>
                {form.items.map((it, idx) => {
                  const selectedProduct = it.product;
                  const hasVariants = selectedProduct?.variants?.length > 0;
                  return (
                    <div key={idx} className="flex gap-2 items-center">
                      <ProductCombo warehouseId={form.from_warehouse_id} value={selectedProduct}
                        disabled={!form.from_warehouse_id} onSelect={p => pickProduct(idx, p)} />
                      {selectedProduct && (
                        <span className={`text-[11px] font-semibold whitespace-nowrap ${Number(selectedProduct.stock_quantity) > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                          {tOr(t, 'ombor.stockInSource', 'Manbada')}: {fmt(selectedProduct.stock_quantity)}
                        </span>
                      )}
                      {hasVariants && (
                        <select value={it.variant_id} onChange={e => setItem(idx, 'variant_id', e.target.value)}
                          className="w-32 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                          <option value="">{tOr(t, 'ombor.selectVariant', 'Variant...')}</option>
                          {selectedProduct.variants.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                        </select>
                      )}
                      <input type="number" min="1" value={it.quantity} onChange={e => setItem(idx, 'quantity', e.target.value)}
                        placeholder={t('admin.dict.qty') || 'Miqdor'}
                        className="w-24 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                      {form.items.length > 1 && (
                        <button onClick={() => removeItem(idx)} className="text-red-400 hover:text-red-600">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>

              {err && <p className="text-sm text-red-500 font-medium">{err}</p>}
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
              <button onClick={() => { setShowModal(false); setErr(''); }}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
              <button onClick={submit} disabled={saving}
                className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('warehouse.transfer')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── OMBORLAR TAB ──────────────────────────────────────────────────────────
function OmborlarTab() {
  const { t } = useLang();
  const { currentBranchId, assignedBranchId, canSelectAll } = useBranch();
  const [warehouses, setWarehouses] = useState([]);
  const { branches } = useBranches();   // T3.8: yagona filial hooki (keshlangan)
  const [loading, setLoading]       = useState(true);
  const [loadError, setLoadError]   = useState(false);
  const [modal, setModal]           = useState(null);
  const [name, setName]             = useState('');
  const [branchId, setBranchId]     = useState('');
  const [whType, setWhType]         = useState('main');
  const [saving, setSaving]         = useState(false);
  const [err, setErr]               = useState('');
  const [delConfirm, setDelConfirm] = useState(null);

  // T3.1: ombor turlari umumiy constants/warehouseTypes.js dan
  const WAREHOUSE_TYPES = WH_TYPE_DEFS.map(wt => ({ value: wt.value, label: t(wt.labelKey) }));

  const load = async () => {
    setLoading(true);
    setLoadError(false);
    try {
      // T1.3: boshqaruv sahifasi — barcha filiallar omborlari (ruxsat bo'lmasa — joriy kontekst)
      const wh = await api.get('/warehouses', { params: { scope: 'all' }, _silent: true, _suppressToast: true }).catch(() => api.get('/warehouses', { _silent: true, _suppressToast: true }));
      setWarehouses(wh.data);
    } catch (e) { setLoadError(true); loadErrToast(e, t); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!name.trim()) { setErr(t('ombor.nameEmptyError')); return; }
    // T3.3: filiallar bor bo'lsa filial majburiy ("Filialsiz" faqat filial cheklovi yo'q admin/director uchun)
    if (branches.length > 0 && !canSelectAll && !branchId) { setErr(tOr(t, 'warehouse.branchRequiredError', 'Filialni tanlang')); return; }
    setSaving(true); setErr('');
    try {
      const payload = { name: name.trim(), branch_id: branchId ? Number(branchId) : null, type: whType };
      if (modal.mode === 'create') {
        const created = await api.post('/warehouses', payload);
        // Filialga biriktirilgan foydalanuvchi o'z filialiga tegishli bo'lmagan omborni ro'yxatda ko'rmaydi
        if (assignedBranchId && (created?.data?.branch_id ?? null) !== assignedBranchId) {
          toast(tOr(t, 'warehouse.notVisibleWarning', "Ombor yaratildi, lekin u sizning filialingiz ro'yxatida ko'rinmaydi"), { duration: 7000 });
        }
      } else await api.patch(`/warehouses/${modal.wh.id}`, payload);
      setModal(null); load();
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    try { await api.delete(`/warehouses/${delConfirm.id}`); setDelConfirm(null); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {assignedBranchId ? tOr(t, 'ombor.branchWarehousesList', "Filial omborlari ro'yxati") : t('ombor.allWarehousesList')}
        </p>
        <button
          onClick={() => {
            setName('');
            // T3.3: standart filial — joriy / biriktirilgan filial, bo'lmasa yagona filial
            setBranchId(currentBranchId ?? assignedBranchId ?? (branches.length === 1 ? branches[0].id : ''));
            setWhType('main'); setErr(''); setModal({ mode: 'create' });
          }}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('warehouse.addWarehouse')}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-x-auto shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loadError ? (
          <LoadError t={t} onRetry={load} />
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('common.name')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('branch.warehouseType')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.branch')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('ombor.created')}</th>
                <th className="px-4 py-3 w-24" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {warehouses.map((wh, i) => (
                <tr key={wh.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-400">{i + 1}</td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{wh.name}</td>
                  <td className="px-4 py-3 text-sm text-slate-500">{WAREHOUSE_TYPES.find(x => x.value === wh.type)?.label || wh.type}</td>
                  <td className="px-4 py-3 text-sm text-slate-500">{branches.find(b => b.id === wh.branch_id)?.name || '—'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(wh.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => { setName(wh.name); setBranchId(wh.branch_id ?? ''); setWhType(wh.type || 'main'); setErr(''); setModal({ mode: 'edit', wh }); }}
                        className="p-1.5 bg-blue-100 text-blue-600 hover:bg-blue-200 rounded-lg transition-colors" title={t('common.edit')}>
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536M9 13l6.5-6.5a2 2 0 012.828 0l.172.172a2 2 0 010 2.828L12 16H9v-3z" />
                        </svg>
                      </button>
                      <button onClick={() => setDelConfirm(wh)}
                        className="p-1.5 bg-red-100 text-red-500 hover:bg-red-200 rounded-lg transition-colors" title={t('common.delete')}>
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {warehouses.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">{t('warehouse.noWarehouses')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Ombor Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-800">
                {modal.mode === 'create' ? t('warehouse.addWarehouse') : t('common.edit')}
              </h3>
              <button onClick={() => setModal(null)} className="text-slate-400 hover:text-slate-600">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">{t('common.name')} *</label>
                <input autoFocus value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && save()}
                  placeholder={t('ombor.warehouseNamePlaceholder')}
                  className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">{t('branch.warehouseType')}</label>
                <select value={whType} onChange={e => setWhType(e.target.value)}
                  className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                  {WAREHOUSE_TYPES.map(x => <option key={x.value} value={x.value}>{x.label}</option>)}
                </select>
              </div>
              {branches.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">{canSelectAll ? t('ombor.branchOptional') : `${t('ombor.branch')} *`}</label>
                  <select value={branchId} onChange={e => setBranchId(e.target.value)} required
                    className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    {canSelectAll ? <option value="">{t('ombor.noBranch')}</option>
                      : !branchId && <option value="" disabled>{tOr(t, 'warehouse.branchRequiredError', 'Filialni tanlang')}</option>}
                    {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                  {/* T4.5: filialsiz tanlansa, tahrirlangan ombor filialdan ajratiladi */}
                  {modal.mode === 'edit' && modal.wh?.branch_id && !branchId && (
                    <p className="mt-1 text-xs font-semibold text-amber-600">{t('ombor.detachFromBranchHint')}</p>
                  )}
                </div>
              )}
              {err && <p className="text-sm text-red-500">{err}</p>}
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
              <button onClick={() => setModal(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
              <button onClick={save} disabled={saving}
                className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {delConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-5">
              <h3 className="text-base font-bold text-slate-800 mb-2">{t('ombor.confirmDeleteTitle')}</h3>
              <p className="text-sm text-slate-500">
                <span className="font-semibold text-slate-700">"{delConfirm.name}"</span> {t('ombor.confirmDeleteWarehouse')}
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
              <button onClick={() => setDelConfirm(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
              <button onClick={remove}
                className="px-4 py-2 bg-red-500 text-white text-sm font-semibold rounded-xl hover:bg-red-600 transition-colors">
                {t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── MAIN OMBOR PAGE ────────────────────────────────────────────────────────
export default function Ombor() {
  const { t } = useLang();
  const [activeTab, setActiveTab] = useState('qoldiq');

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-linear-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-lg shadow-blue-900/20">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-800">{t('warehouse.title')}</h2>
          <p className="text-xs text-slate-500">{t('warehouse.inventory')}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-2xl">
        {[
          { id: 'qoldiq',    label: t('warehouse.stockLevel') || 'Остатки',   icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
          { id: 'kirim',     label: t('ops.incoming') || 'Приход',        icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12' },
          { id: 'chiqim',    label: t('ops.outgoing') || 'Расход',       icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4' },
          { id: 'kochirish', label: t('warehouse.transfer') || 'Перемещение',   icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
          { id: 'omborlar',  label: t('nav.warehouse') || 'Склады',     icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' },
        ].map(tab => (
          <button
            key={tab.id}
            title={tab.label}
            aria-label={tab.label}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 ${
              activeTab === tab.id
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
            </svg>
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'qoldiq'    && <QoldiqlarTab />}
      {activeTab === 'kirim'     && <MovementsTab type="in" />}
      {activeTab === 'chiqim'    && <MovementsTab type="out" />}
      {activeTab === 'kochirish' && <KochirTab />}
      {activeTab === 'omborlar'  && <OmborlarTab />}
    </div>
  );
}
