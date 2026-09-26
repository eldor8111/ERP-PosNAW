import { useState, useEffect, useCallback, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';
import api from '../../api/axios';
import toast from 'react-hot-toast';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtS = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const pct = (v) => `${Number(v || 0).toFixed(1)}%`;
const curLabel = (c) => (!c || c === 'UZS' ? "so'm" : c);
// Valyuta bo'yicha dict: {UZS: 1000, USD: 5} -> "1 000 so'm + 5 USD"
const fmtDebt = (v) => {
  if (!v) return "0 so'm";
  if (typeof v === 'object' && !Array.isArray(v)) {
    const parts = Object.entries(v).filter(([, amt]) => Math.abs(amt) > 0.001)
      .map(([c, amt]) => `${Number(Number(amt).toFixed(2)).toLocaleString('uz-UZ')} ${curLabel(c)}`);
    return parts.length ? parts.join(' + ') : "0 so'm";
  }
  return fmtS(v);
};
const fmtRowDebt = (amount, currency) => `${Number(amount || 0).toLocaleString('uz-UZ')} ${curLabel(currency)}`;
const sumBy = (list, key) => list.reduce((a, r) => a + Number(r[key] || 0), 0);
const errMsg = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : (err?.message || fallback);
};

// ─── Kunlik sanalar (mahalliy vaqt bo'yicha) ──────────────────────────────────
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const today = () => ymd(new Date());
const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return ymd(d); };
const firstOfMonth = () => { const d = new Date(); d.setDate(1); return ymd(d); };

const MOV_LIMIT = 500;
const DEAD_MONTHS = [1, 3, 6, 12];
// Filial filtri qo'llanadigan tablar (qarzlar kompaniya bo'yicha, harakatlarda ombor yozilmaydi)
const BRANCH_TABS = new Set(['sales', 'profit', 'pl', 'cashier', 'deadstock', 'expenses', 'purchases', 'abc', 'batches', 'product-sales']);
const EMPTY_SALES = { items: [], summary: null, total_count: 0, truncated: false };

// Harakat miqdori o'zgarishi: qoldiq farqidan, bo'lmasa turidan
const movementDelta = (m) => {
  const diff = Number(m.qty_after) - Number(m.qty_before);
  if (Number.isFinite(diff) && Math.abs(diff) > 1e-9) return diff;
  const q = Math.abs(Number(m.quantity) || 0);
  return ['OUT', 'TRANSFER_OUT', 'EXPIRED'].includes(m.type) ? -q : q;
};

// ─── PDF chop etish (window.print orqali) ─────────────────────────────────────
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

function printTable(title, headers, rows, totalsRow = null, printLabel = 'Print') {
  const headerHtml = headers.map(h => `<th style="border:1px solid #ddd;padding:8px;background:#f3f4f6;font-size:12px">${esc(h)}</th>`).join('');
  const rowsHtml = rows.map((row, i) =>
    `<tr style="background:${i % 2 ? '#f9fafb' : '#fff'}">${row.map(cell =>
      `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${cell === null || cell === undefined || cell === '' ? '—' : esc(cell)}</td>`
    ).join('')}</tr>`
  ).join('');
  const totalsHtml = totalsRow
    ? `<tr style="background:#e0f2fe;font-weight:bold">${totalsRow.map(cell =>
        `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${esc(cell)}</td>`
      ).join('')}</tr>`
    : '';

  const win = window.open('', '_blank');
  if (!win) return;
  win.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
    <style>body{font-family:Arial,sans-serif;margin:20px}h2{color:#1e293b}table{border-collapse:collapse;width:100%}@media print{button{display:none}}</style>
    </head><body>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2>${esc(title)}</h2>
      <div style="font-size:12px;color:#64748b">${esc(new Date().toLocaleString('uz-UZ'))}</div>
    </div>
    <table><thead><tr>${headerHtml}</tr></thead>
    <tbody>${rowsHtml}${totalsHtml}</tbody></table>
    <div style="margin-top:16px;text-align:center">
      <button onclick="window.print()" style="padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">${esc(printLabel)}</button>
    </div></body></html>`);
  win.document.close();
}

async function saveSheet(rows, sheetName, fileName) {
  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, sheetName.slice(0, 31));
  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), fileName);
}

// ─── Umumiy Tab tugmasi ────────────────────────────────────────────────────────
function TabBtn({ label, icon, active, onClick }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap ${
        active ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'
      }`}>
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={icon} />
      </svg>
      {label}
    </button>
  );
}

// ─── Sana filtri komponenti ────────────────────────────────────────────────────
function DateFilter({ dateFrom, dateTo, setDateFrom, setDateTo, onSearch, loading }) {
  const { t } = useLang();
  const presets = [
    { label: t('reports.date.today'), from: today(), to: today() },
    { label: t('reports.date.thisWeek'), from: daysAgo(6), to: today() },
    { label: t('reports.date.thisMonth'), from: firstOfMonth(), to: today() },
    { label: t('reports.date.last30'), from: daysAgo(29), to: today() },
  ];
  return (
    <div className="flex flex-wrap items-end gap-2 px-6 py-4 border-b border-slate-100 bg-slate-50/50">
      <div className="flex gap-1 flex-wrap">
        {presets.map(p => (
          <button key={p.label} onClick={() => { setDateFrom(p.from); setDateTo(p.to); }}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              dateFrom === p.from && dateTo === p.to
                ? 'bg-blue-100 text-blue-700'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}>{p.label}</button>
        ))}
      </div>
      <div className="flex items-end gap-2 ml-auto flex-wrap">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.date.from')}</label>
          <input type="date" value={dateFrom} max={dateTo || undefined} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.date.to')}</label>
          <input type="date" value={dateTo} min={dateFrom || undefined} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <button onClick={onSearch} disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
          {loading ? t('reports.loading') : t('reports.search')}
        </button>
      </div>
    </div>
  );
}

// ─── Excel va PDF tugmalari ────────────────────────────────────────────────────
function ExportBtns({ onExcel, onPdf, on1c }) {
  const { t } = useLang();
  return (
    <div className="flex gap-2">
      {onExcel && (
        <button onClick={onExcel}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {t('reports.excel')}
        </button>
      )}
      {onPdf && (
        <button onClick={onPdf}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          {t('reports.pdf')}
        </button>
      )}
      {on1c && (
        <button onClick={on1c}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          {t('reports.export1c')}
        </button>
      )}
    </div>
  );
}

// ─── Spinner ───────────────────────────────────────────────────────────────────
const Spinner = () => (
  <div className="flex justify-center py-16">
    <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

function MarginBar({ value, width = 'flex-1 min-w-12' }) {
  const v = Number(value || 0);
  const negative = v < 0;
  return (
    <div className="flex items-center gap-2">
      <div className={`${width} bg-slate-200 rounded-full h-1.5`}>
        <div className={`h-1.5 rounded-full transition-all ${negative ? 'bg-red-500' : 'bg-emerald-500'}`}
          style={{ width: `${Math.min(Math.abs(v), 100)}%` }} />
      </div>
      <span className={`text-xs font-bold ${negative ? 'text-red-600' : 'text-emerald-600'}`}>{pct(v)}</span>
    </div>
  );
}

// ─── Asosiy komponent ─────────────────────────────────────────────────────────
export default function Reports() {
  const { t } = useLang();

  // URL orqali kelganda (masalan mahsulot kartochkasidan) — harakatlar tabi va filtrlar
  const [urlInit] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('tab') !== 'movements') return null;
    return {
      productId: params.get('product_id') || '',
      productName: params.get('product_name') || '',
      fromSell: params.get('from_sell') || '',
      ratio: params.get('ratio') || '',
    };
  });

  const [tab, setTab] = useState(urlInit ? 'movements' : 'sales');
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(today());
  const [dateTo, setDateTo] = useState(today());
  const [branchId, setBranchId] = useState('');
  const [branches, setBranches] = useState([]);

  // Ma'lumotlar
  const [salesData, setSalesData] = useState(EMPTY_SALES);
  const [salesIncludeReturns, setSalesIncludeReturns] = useState(false);
  const [expenseData, setExpenseData] = useState(null);
  const [profitData, setProfitData] = useState([]);
  const [cashierData, setCashierData] = useState([]);
  const [cashBalance, setCashBalance] = useState(null);
  const [deadStockData, setDeadStockData] = useState(null);
  const [deadMonths, setDeadMonths] = useState(6);
  const [purchasesData, setPurchasesData] = useState([]);
  const [customerDebts, setCustomerDebts] = useState(null);
  const [supplierDebts, setSupplierDebts] = useState(null);
  const [abcData, setAbcData] = useState([]);
  const [plData, setPlData] = useState(null);
  const [batchData, setBatchData] = useState([]);
  const [productSalesData, setProductSalesData] = useState([]);
  const [movementsData, setMovementsData] = useState([]);
  const [movSearch, setMovSearch] = useState(urlInit?.productName || '');
  const [movRefType, setMovRefType] = useState('');
  const [movDateFrom, setMovDateFrom] = useState(urlInit ? daysAgo(29) : today());
  const [movDateTo, setMovDateTo] = useState(today());
  const [fromSellProduct, setFromSellProduct] = useState(urlInit?.fromSell || '');
  const [convRatio, setConvRatio] = useState(urlInit?.ratio || '');
  const [movProductId] = useState(urlInit?.productId || '');

  const payLabel = (p) => {
    if (!p) return '—';
    const label = t(`pay.${p}`);
    return label === `pay.${p}` ? p : label;
  };

  // Load branches on mount
  useEffect(() => {
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch((err) => { toast.error(errMsg(err, t('reports.errorOccurred'))) });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Faqat oxirgi so'rov natijasi ekranga chiqadi (tab tez almashtirilganda eski javob ustiga yozmasin)
  const reqIdRef = useRef(0);

  const load = useCallback(async () => {
    const reqId = ++reqIdRef.current;
    const isCurrent = () => reqId === reqIdRef.current;
    const qs = (extra = {}) => {
      const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, ...extra });
      if (branchId) p.set('branch_id', branchId);
      return '?' + p.toString();
    };
    setLoading(true);
    try {
      if (tab === 'sales') {
        const r = await api.get(`/reports/sales${qs({ include_returns: salesIncludeReturns ? 'true' : 'false' })}`);
        if (isCurrent()) setSalesData({ ...EMPTY_SALES, ...r.data });
      } else if (tab === 'expenses') {
        const r = await api.get(`/reports/expenses${qs()}`);
        if (isCurrent()) setExpenseData(r.data);
      } else if (tab === 'profit') {
        const r = await api.get(`/reports/profit${qs()}`);
        if (isCurrent()) setProfitData(r.data);
      } else if (tab === 'cashier') {
        const [r, cb] = await Promise.all([
          api.get(`/reports/cashier-report${qs()}`),
          api.get(`/finance/cash-balance${qs()}`).catch(() => null),
        ]);
        if (isCurrent()) {
          setCashierData(r.data);
          setCashBalance(cb ? cb.data : null);
        }
      } else if (tab === 'deadstock') {
        const p = new URLSearchParams({ months: String(deadMonths) });
        if (branchId) p.set('branch_id', branchId);
        const r = await api.get(`/reports/dead-stock?${p}`);
        if (isCurrent()) setDeadStockData(r.data);
      } else if (tab === 'purchases') {
        const r = await api.get(`/reports/purchases${qs()}`);
        if (isCurrent()) setPurchasesData(r.data);
      } else if (tab === 'customer-debts') {
        const r = await api.get('/reports/customer-debts');
        if (isCurrent()) setCustomerDebts(r.data);
      } else if (tab === 'supplier-debts') {
        const r = await api.get('/reports/supplier-debts');
        if (isCurrent()) setSupplierDebts(r.data);
      } else if (tab === 'abc') {
        const r = await api.get(`/reports/abc-xyz${qs()}`);
        if (isCurrent()) setAbcData(r.data);
      } else if (tab === 'pl') {
        const r = await api.get(`/reports/profit-loss${qs()}`);
        if (isCurrent()) setPlData(r.data);
      } else if (tab === 'batches') {
        const r = await api.get(`/reports/batches${qs()}`);
        if (isCurrent()) setBatchData(r.data);
      } else if (tab === 'product-sales') {
        const r = await api.get(`/reports/product-sales${qs()}`);
        if (isCurrent()) setProductSalesData(r.data);
      } else if (tab === 'movements') {
        const p = new URLSearchParams({ date_from: movDateFrom, date_to: movDateTo, limit: String(MOV_LIMIT) });
        if (movSearch) p.set('search', movSearch);
        if (movRefType) p.set('reference_type', movRefType);
        if (movProductId) p.set('product_id', movProductId);
        const r = await api.get(`/inventory/movements?${p}`);
        if (isCurrent()) setMovementsData(r.data);
      }
    } catch (err) {
      if (!isCurrent()) return;
      toast.error(errMsg(err, t('reports.errorOccurred')));
      // Eski ma'lumot yangi filtr natijasidek ko'rinib qolmasin
      const reset = {
        sales: () => setSalesData(EMPTY_SALES),
        expenses: () => setExpenseData(null),
        profit: () => setProfitData([]),
        cashier: () => { setCashierData([]); setCashBalance(null); },
        deadstock: () => setDeadStockData(null),
        purchases: () => setPurchasesData([]),
        'customer-debts': () => setCustomerDebts(null),
        'supplier-debts': () => setSupplierDebts(null),
        abc: () => setAbcData([]),
        pl: () => setPlData(null),
        batches: () => setBatchData([]),
        'product-sales': () => setProductSalesData([]),
        movements: () => setMovementsData([]),
      };
      reset[tab]?.();
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, [tab, dateFrom, dateTo, branchId, salesIncludeReturns, deadMonths, movDateFrom, movDateTo, movSearch, movRefType, movProductId, t]);

  // Tab, filial va tab ichidagi tanlovlar o'zgarganda avtomatik yuklash;
  // sana va qidiruv filtrlari "Qidiruv" tugmasi bilan qo'llanadi.
  const loadRef = useRef(load);
  useEffect(() => { loadRef.current = load; }, [load]);
  useEffect(() => { loadRef.current(); }, [tab, branchId, salesIncludeReturns, deadMonths]);

  const tabs = [
    { key: 'sales', label: t('reports.tab.sales'), icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
    { key: 'profit', label: t('reports.tab.profit'), icon: 'M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z' },
    { key: 'pl', label: t('reports.tab.pl'), icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
    { key: 'cashier', label: t('reports.tab.cashier'), icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' },
    { key: 'deadstock', label: t('reports.tab.deadstock'), icon: 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    { key: 'expenses', label: t('reports.tab.expenses'), icon: 'M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z' },
    { key: 'purchases', label: t('reports.tab.purchases'), icon: 'M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z' },
    { key: 'customer-debts', label: t('reports.tab.customerDebts'), icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { key: 'supplier-debts', label: t('reports.tab.supplierDebts'), icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { key: 'abc', label: t('reports.tab.abc'), icon: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' },
    { key: 'batches', label: t('reports.tab.batches'), icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
    { key: 'product-sales', label: t('reports.tab.productSales'), icon: 'M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z' },
    { key: 'movements', label: `📦 ${t('reports.tab.movements')}`, icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
  ];

  const dateFilter = <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />;
  const uzsNote = <p className="text-xs text-slate-400 mt-0.5">{t('reports.uzsNote')}</p>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t('reports.title')}</h1>
        <p className="text-slate-500 text-sm mt-0.5">{t('reports.subtitle')}</p>
      </div>

      {/* Branch filter — faqat filial bo'yicha ajratiladigan hisobotlarda */}
      {branches.length > 0 && BRANCH_TABS.has(tab) && (
        <div className="flex items-center gap-3">
          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
          <span className="text-sm font-semibold text-slate-500">{t('reports.branchLabel')}</span>
          <select
            value={branchId}
            onChange={e => { setBranchId(e.target.value); }}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            <option value="">{`🏢 ${t('common.allBranches')}`}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          {branchId && (
            <button onClick={() => setBranchId('')}
              className="text-xs text-slate-400 hover:text-slate-600 underline">{t('admin.dict.clear') || 'Tozalash'}</button>
          )}
        </div>
      )}

      {/* Tab bar */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-3">
        <div className="flex flex-wrap gap-1">
          {tabs.map(tb => (
            <TabBtn key={tb.key} label={tb.label} icon={tb.icon} active={tab === tb.key} onClick={() => setTab(tb.key)} />
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">

        {/* ── Sotuvlar ── */}
        {tab === 'sales' && (() => {
          const items = salesData.items || [];
          const summary = salesData.summary || {};
          const hasReturns = Object.keys(summary.returns_by_currency || {}).length > 0;
          const STATUS_BADGE = {
            partial_refund: { label: t('reports.status.partialRefund'), cls: 'bg-amber-50 text-amber-700' },
            refunded: { label: t('reports.status.refunded'), cls: 'bg-slate-100 text-slate-600' },
          };
          const badgeFor = (s) => (s.type === 'return'
            ? { label: t('reports.status.return'), cls: 'bg-red-50 text-red-600' }
            : STATUS_BADGE[s.status]);
          return (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.salesListTitle')}</span>
              <ExportBtns
                onExcel={() => saveSheet(items.map(s => ({
                  [t('reports.th.number')]: s.number,
                  [t('reports.th.type')]: badgeFor(s)?.label || '',
                  [t('reports.th.cashier')]: s.cashier_name,
                  [t('sale.customer')]: s.customer_name || '',
                  [t('reports.th.amount')]: s.total_amount,
                  [t('reports.th.currency')]: s.currency_code,
                  [t('reports.th.discount')]: s.discount_amount,
                  [t('reports.th.payment')]: payLabel(s.payment_type),
                  [t('reports.th.date')]: new Date(s.created_at).toLocaleString('uz-UZ'),
                })), t('reports.tab.sales'), `sotuvlar_${today()}.xlsx`)}
                onPdf={() => printTable(t('reports.salesReportTitle'),
                  [t('reports.th.number'), t('reports.th.cashier'), t('reports.th.amount'), t('reports.th.payment'), t('reports.th.date')],
                  items.map(s => [s.number, s.cashier_name, fmtRowDebt(s.total_amount, s.currency_code), payLabel(s.payment_type), new Date(s.created_at).toLocaleDateString('uz-UZ')]),
                  ['', t('reports.total'), fmtDebt(summary.net_by_currency), '', ''],
                  t('common.print')
                )}
                on1c={async () => {
                  try {
                    const saveAs = await loadSaveAs();
                    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, format: 'csv', include_returns: 'true' });
                    if (branchId) params.set('branch_id', branchId);
                    const r = await api.get(`/reports/1c-export?${params}`, { responseType: 'blob' });
                    saveAs(r.data, `1c_export_${today()}.csv`);
                  } catch (err) {
                    toast.error(errMsg(err, t('reports.errorOccurred')));
                  }
                }}
              />
            </div>
            {dateFilter}
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 border-b border-slate-100">
              <label className="inline-flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
                <input type="checkbox" checked={salesIncludeReturns} onChange={e => setSalesIncludeReturns(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                {t('reports.includeReturns')}
              </label>
              {salesData.truncated && (
                <span className="text-xs font-medium text-amber-700 bg-amber-50 px-3 py-1 rounded-lg">
                  {t('reports.truncatedWarning', { shown: items.length, total: salesData.total_count })}
                </span>
              )}
            </div>
            {loading ? <Spinner /> : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {[t('reports.th.number'), t('reports.th.cashier'), t('reports.th.amount'), t('reports.th.discount'), t('reports.th.payment'), t('reports.th.date')].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {items.map(s => {
                        const isReturn = s.type === 'return';
                        const badge = badgeFor(s);
                        return (
                          <tr key={s.id} className={`transition-colors ${isReturn ? 'bg-red-50/30 hover:bg-red-50/60' : 'hover:bg-slate-50'}`}>
                            <td className="px-5 py-3.5 text-sm">
                              <span className="font-mono font-semibold text-blue-600">{s.number}</span>
                              {badge && <span className={`ml-2 inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold ${badge.cls}`}>{badge.label}</span>}
                            </td>
                            <td className="px-5 py-3.5 text-sm text-slate-700">{s.cashier_name}</td>
                            <td className={`px-5 py-3.5 text-sm font-semibold ${isReturn ? 'text-red-600' : 'text-slate-800'}`}>{fmtRowDebt(s.total_amount, s.currency_code)}</td>
                            <td className="px-5 py-3.5 text-sm text-slate-500">{s.discount_amount > 0 ? fmtRowDebt(s.discount_amount, s.currency_code) : '—'}</td>
                            <td className="px-5 py-3.5">
                              <span className="inline-flex px-2 py-0.5 bg-blue-50 text-blue-600 text-xs font-medium rounded-lg">{payLabel(s.payment_type)}</span>
                            </td>
                            <td className="px-5 py-3.5 text-sm text-slate-400">{new Date(s.created_at).toLocaleString('uz-UZ')}</td>
                          </tr>
                        );
                      })}
                      {items.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                    </tbody>
                  </table>
                </div>
                {(items.length > 0 || hasReturns) && (
                  <div className="px-6 py-3 border-t border-slate-100 flex flex-wrap justify-between gap-x-6 gap-y-1 text-sm text-slate-500 bg-slate-50">
                    <span>{t('reports.totalSalesCount', { count: salesData.total_count ?? items.length })}</span>
                    <div className="flex flex-wrap gap-x-5 gap-y-1">
                      <span>{t('reports.summary.sales')}: <strong className="text-slate-700">{fmtDebt(summary.sales_by_currency)}</strong></span>
                      <span>{t('reports.summary.returns')}: <strong className="text-orange-600">{fmtDebt(summary.returns_by_currency)}</strong></span>
                      <span>{t('reports.summary.net')}: <strong className="text-emerald-600">{fmtDebt(summary.net_by_currency)}</strong></span>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
          );
        })()}

        {/* ── Foyda (mahsulot bo'yicha) ── */}
        {tab === 'profit' && (() => {
          const totalRevenue = sumBy(profitData, 'revenue');
          const totalCost = sumBy(profitData, 'cost');
          const totalProfit = sumBy(profitData, 'profit');
          const totalMargin = totalRevenue > 0 ? totalProfit / totalRevenue * 100 : 0;
          return (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <div>
                <span className="text-sm font-semibold text-slate-700">{t('reports.profitByProductTitle')}</span>
                {uzsNote}
              </div>
              <ExportBtns
                onExcel={() => saveSheet(profitData.map(r => ({
                  [t('reports.th.product')]: r.product_name, 'SKU': r.sku, [t('reports.th.category')]: r.category_name,
                  [t('reports.th.sold')]: r.qty_sold, [t('reports.th.revenue')]: r.revenue, [t('reports.th.cost')]: r.cost,
                  [t('reports.th.profit')]: r.profit, [t('reports.th.marginPct')]: r.margin_pct,
                })), t('reports.th.profit'), `foyda_${today()}.xlsx`)}
                onPdf={() => printTable(t('reports.profitByProductTitle'),
                  [t('reports.th.product'), t('reports.th.category'), t('reports.th.sold'), t('reports.th.revenue'), t('reports.th.cost'), t('reports.th.profit'), t('reports.th.margin')],
                  profitData.map(r => [r.product_name, r.category_name, fmt(r.qty_sold), fmtS(r.revenue), fmtS(r.cost), fmtS(r.profit), pct(r.margin_pct)]),
                  [t('reports.total'), '', fmt(sumBy(profitData, 'qty_sold')), fmtS(totalRevenue), fmtS(totalCost), fmtS(totalProfit), pct(totalMargin)],
                  t('common.print')
                )}
              />
            </div>
            {dateFilter}
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('reports.th.product'), t('reports.th.category'), t('reports.th.sold'), t('reports.th.revenue'), t('reports.th.cost'), t('reports.th.profit'), t('reports.th.margin')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {profitData.map((r, i) => (
                      <tr key={r.product_id} className={i % 2 ? 'bg-slate-50/50 hover:bg-slate-100 transition-colors' : 'bg-white hover:bg-slate-50 transition-colors'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.product_name}</td>
                        <td className="px-5 py-3.5"><span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded-lg">{r.category_name}</span></td>
                        <td className="px-5 py-3.5 text-sm text-slate-600">{fmt(r.qty_sold)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{fmtS(r.revenue)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtS(r.cost)}</td>
                        <td className={`px-5 py-3.5 text-sm font-semibold ${r.profit < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtS(r.profit)}</td>
                        <td className="px-5 py-3.5"><MarginBar value={r.margin_pct} /></td>
                      </tr>
                    ))}
                    {profitData.length === 0 && <tr><td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                  {profitData.length > 0 && (
                    <tfoot>
                      <tr className="bg-blue-50 font-bold">
                        <td className="px-5 py-3 text-sm text-slate-700">{t('reports.total')}</td>
                        <td />
                        <td className="px-5 py-3 text-sm">{fmt(sumBy(profitData, 'qty_sold'))}</td>
                        <td className="px-5 py-3 text-sm">{fmtS(totalRevenue)}</td>
                        <td className="px-5 py-3 text-sm">{fmtS(totalCost)}</td>
                        <td className={`px-5 py-3 text-sm ${totalProfit < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtS(totalProfit)}</td>
                        <td className="px-5 py-3 text-sm">{pct(totalMargin)}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}
          </>
          );
        })()}

        {/* ── Mahsulotlar (Sotuv) ── */}
        {tab === 'product-sales' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <div>
                <span className="text-sm font-semibold text-slate-700">{t('reports.productSalesReportTitle')}</span>
                {uzsNote}
              </div>
              <ExportBtns
                onExcel={() => saveSheet(productSalesData.map(r => ({
                  [t('reports.th.product')]: r.product_name, 'SKU': r.sku,
                  [t('reports.th.soldQty')]: r.sold_qty, [t('reports.th.returnedQty')]: r.returned_qty, [t('reports.th.netQty')]: r.total_qty,
                  [t('reports.th.revenue')]: r.total_revenue, [t('reports.th.profit')]: r.total_profit,
                })), t('reports.tab.productSales'), `mahsulot_sotuv_${today()}.xlsx`)}
              />
            </div>
            {dateFilter}
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('reports.th.product'), 'SKU', t('reports.th.soldQty'), t('reports.th.returnedQty'), t('reports.th.netQty'), t('reports.th.revenue'), t('reports.th.profit')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {productSalesData.map((r, i) => (
                      <tr key={r.product_id} className={i % 2 ? 'bg-slate-50/50 hover:bg-slate-100 transition-colors' : 'bg-white hover:bg-slate-50 transition-colors'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.product_name}</td>
                        <td className="px-5 py-3.5 text-sm font-mono text-blue-600">{r.sku}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-600">{fmt(r.sold_qty)}</td>
                        <td className="px-5 py-3.5 text-sm text-orange-600">{r.returned_qty > 0 ? fmt(r.returned_qty) : '—'}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-700 font-bold">{fmt(r.total_qty)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-emerald-600">{fmtS(r.total_revenue)}</td>
                        <td className={`px-5 py-3.5 text-sm font-semibold ${r.total_profit < 0 ? 'text-red-600' : 'text-blue-600'}`}>{fmtS(r.total_profit)}</td>
                      </tr>
                    ))}
                    {productSalesData.length === 0 && <tr><td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                  {productSalesData.length > 0 && (
                    <tfoot>
                      <tr className="bg-blue-50 font-bold">
                        <td className="px-5 py-3 text-sm text-slate-700">{t('reports.total')}</td>
                        <td />
                        <td className="px-5 py-3 text-sm">{fmt(sumBy(productSalesData, 'sold_qty'))}</td>
                        <td className="px-5 py-3 text-sm text-orange-600">{fmt(sumBy(productSalesData, 'returned_qty'))}</td>
                        <td className="px-5 py-3 text-sm">{fmt(sumBy(productSalesData, 'total_qty'))}</td>
                        <td className="px-5 py-3 text-sm text-emerald-600">{fmtS(sumBy(productSalesData, 'total_revenue'))}</td>
                        <td className="px-5 py-3 text-sm text-blue-600">{fmtS(sumBy(productSalesData, 'total_profit'))}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}
          </>
        )}

        {/* ── Mahsulot harakatlari ── */}
        {tab === 'movements' && (() => {
          // Operatsiya nomi reference_type bo'yicha (bazadagi haqiqiy qiymatlar), yo'nalish — qoldiq o'zgarishidan
          const REF_LABELS = {
            purchase_order: t('reports.op.inPurchase'),
            manual_receive: t('reports.op.manualReceive'),
            return_from_customer: t('reports.op.returnCustomer'),
            customer_return: t('reports.op.returnCustomer'),
            sale_refund: t('reports.op.returnCustomer'),
            sale: t('reports.tab.sales'),
            chiqim: t('reports.op.expense'),
            chiqim_revert: t('reports.op.expenseRevert'),
            return_to_supplier: t('reports.op.returnSupplier'),
            return_revert: t('reports.op.returnRevert'),
            revision: t('warehouse.inventory'),
            inventory_count: t('warehouse.inventory'),
            adjustment: t('reports.op.adjustment'),
            batch_write_off: t('reports.op.writeOff'),
            auto_batch_write_off: t('reports.op.writeOff'),
          };
          const TRANSFER_REFS = new Set(['stock_transfer', 'transfer', 'transfer_in', 'transfer_out']);
          const getOp = (m) => {
            const rt = m.reference_type || '';
            const delta = movementDelta(m);
            const color = delta > 0
              ? { bg: 'bg-emerald-100', text: 'text-emerald-700' }
              : delta < 0 ? { bg: 'bg-orange-100', text: 'text-orange-700' } : { bg: 'bg-slate-100', text: 'text-slate-600' };
            let label;
            if (TRANSFER_REFS.has(rt) || m.type === 'TRANSFER_IN' || m.type === 'TRANSFER_OUT') {
              label = delta < 0 ? t('reports.op.transferOut') : t('reports.op.transferIn');
            } else if (REF_LABELS[rt]) {
              label = REF_LABELS[rt];
            } else if (m.type === 'ADJUST') {
              label = t('reports.op.adjustment');
            } else if (m.type === 'RETURN') {
              label = t('reports.op.returnGeneric');
            } else if (rt) {
              label = rt.replace(/_/g, ' ');
            } else {
              label = delta < 0 ? t('reports.op.expense') : t('reports.op.receive');
            }
            return { label, ...color };
          };

          const REF_TYPES = [
            { v: '', l: t('reports.op.allOperations') },
            { v: 'purchase_order', l: t('reports.op.inPurchase') },
            { v: 'sale', l: t('reports.tab.sales') },
            { v: 'chiqim', l: t('reports.op.expense') },
            { v: 'return_to_supplier', l: t('reports.op.returnSupplierFull') },
            { v: 'return_from_customer', l: t('reports.op.returnCustomer') },
            { v: 'adjustment', l: t('reports.op.adjustment') },
            { v: 'inventory_count', l: t('warehouse.inventory') },
            { v: 'transfer', l: t('reports.op.transfer') },
          ];
          const inCount = movementsData.filter(m => movementDelta(m) > 0).length;
          const outCount = movementsData.filter(m => movementDelta(m) < 0).length;
          return (
            <>
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
                <span className="text-sm font-bold text-slate-700">{`📦 ${t('reports.movementsReportTitle')}`}</span>
                <button onClick={() => saveSheet(movementsData.map(m => ({
                    [t('reports.th.date')]: new Date(m.created_at).toLocaleString('uz-UZ'),
                    [t('reports.th.operation')]: getOp(m).label,
                    [t('reports.th.product')]: m.product_name,
                    'SKU': m.product_sku || '',
                    [t('reports.th.qtyBefore')]: Number(m.qty_before),
                    [t('reports.th.change')]: movementDelta(m),
                    [t('reports.th.qtyAfter')]: Number(m.qty_after),
                    [t('reports.th.contragent')]: m.contragent_name || '',
                    [t('reports.th.unit')]: m.product_unit || t('reports.unitPiece'),
                    [t('reports.th.user')]: m.user_name || '',
                  })), t('reports.tab.movements'), `mahsulot_harakatlar_${today()}.xlsx`)}
                  className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                  {t('reports.excel')}
                </button>
              </div>

              {/* Tarkibi mahsulot banner */}
              {fromSellProduct && (
                <div className="mx-6 mt-4 mb-1 bg-amber-50 border border-amber-200 rounded-2xl p-4 flex items-start gap-3">
                  <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center shrink-0 mt-0.5">
                    <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <p className="font-bold text-amber-800 text-sm">
                      {t('reports.virtualProductBanner', { name: fromSellProduct })}
                    </p>
                    <p className="text-amber-700 text-sm mt-0.5">
                      {t('reports.virtualProductSoldFrom')} <strong>«{movSearch}»</strong>{t('reports.virtualProductDeducted')}
                      {t('reports.virtualProductBelow')} <strong>«{movSearch}»</strong>{t('reports.virtualProductAllMovements')}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-100 text-amber-700 text-xs font-bold rounded-lg">
                        {fromSellProduct}
                      </span>
                      <svg className="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                      </svg>
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-100 text-emerald-700 text-xs font-bold rounded-lg">
                        {movSearch}
                      </span>
                      {convRatio && (
                        <span className="text-xs text-amber-600 ml-1">
                          {t('reports.ratioLabel', { ratio: convRatio })}
                        </span>
                      )}
                    </div>
                  </div>
                  <button onClick={() => { setFromSellProduct(''); setConvRatio(''); }}
                    className="text-amber-400 hover:text-amber-600 p-1 rounded-lg hover:bg-amber-100 transition-colors shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              )}

              {/* Filtrlar */}
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {[
                    { l: t('reports.date.today'), f: today(), to: today() },
                    { l: t('reports.date.thisWeek'), f: daysAgo(6), to: today() },
                    { l: t('reports.date.thisMonth'), f: firstOfMonth(), to: today() },
                    { l: t('reports.date.last30'), f: daysAgo(29), to: today() },
                  ].map(p => (
                    <button key={p.l} onClick={() => { setMovDateFrom(p.f); setMovDateTo(p.to); }}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                        movDateFrom === p.f && movDateTo === p.to
                          ? 'bg-blue-100 text-blue-700' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}>{p.l}</button>
                  ))}
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.dateFromLabel')}</label>
                    <input type="date" value={movDateFrom} max={movDateTo || undefined} onChange={e => setMovDateFrom(e.target.value)}
                      className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.dateToLabel')}</label>
                    <input type="date" value={movDateTo} min={movDateFrom || undefined} onChange={e => setMovDateTo(e.target.value)}
                      className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('product.title')}</label>
                    <input value={movSearch} onChange={e => setMovSearch(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') load(); }}
                      placeholder={t('reports.namePlaceholder')}
                      className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-44" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.operationTypeLabel')}</label>
                    <select value={movRefType} onChange={e => setMovRefType(e.target.value)}
                      className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
                      {REF_TYPES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                  </div>
                  <button onClick={load} disabled={loading}
                    className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-bold rounded-xl transition-colors">
                    {loading ? t('reports.loading') : `🔍 ${t('reports.search')}`}
                  </button>
                </div>
              </div>

              {/* Summary */}
              {movementsData.length > 0 && (
                <div className="grid grid-cols-3 gap-4 px-6 py-4 border-b border-slate-100">
                  {[
                    { l: t('reports.totalMovements'), v: `${movementsData.length} ${t('common.item')}`, cls: 'text-slate-600' },
                    { l: t('reports.inCount'), v: `${inCount} ${t('common.item')}`, cls: 'text-emerald-600' },
                    { l: t('reports.outCount'), v: `${outCount} ${t('common.item')}`, cls: 'text-red-600' },
                  ].map(c => (
                    <div key={c.l} className="bg-white rounded-xl border border-slate-100 p-4 flex items-center gap-3 shadow-sm">
                      <div>
                        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{c.l}</div>
                        <div className={`text-xl font-black ${c.cls} mt-0.5`}>{c.v}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {movementsData.length >= MOV_LIMIT && (
                <div className="px-6 py-2 border-b border-slate-100 text-xs font-medium text-amber-700 bg-amber-50">
                  {t('reports.movementsTruncated', { limit: MOV_LIMIT })}
                </div>
              )}

              {/* Jadval */}
              {loading ? <Spinner /> : (
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {['#', t('reports.th.date'), t('reports.th.operation'), t('reports.productNameLabel'), t('reports.th.qtyBefore'), t('reports.th.change'), t('reports.th.qtyAfter'), t('reports.th.contragent'), t('reports.th.unit'), t('reports.whoLabel')].map(h => (
                          <th key={h} className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {movementsData.map((m, i) => {
                        const op = getOp(m);
                        const delta = movementDelta(m);
                        const qAfter = Number(m.qty_after);
                        return (
                          <tr key={m.id} className="hover:bg-slate-50 transition-colors">
                            <td className="px-4 py-3 text-xs text-slate-400">{i + 1}</td>
                            <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                              {new Date(m.created_at).toLocaleString('uz-UZ')}
                            </td>
                            <td className="px-4 py-3">
                              <span className={`inline-flex px-2 py-0.5 rounded-lg text-xs font-bold ${op.bg} ${op.text}`}>
                                {op.label}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="text-sm font-medium text-slate-800">{m.product_name}</div>
                              {m.product_sku && <div className="text-xs text-blue-500 font-mono">{m.product_sku}</div>}
                              {m.reason && (() => {
                                // "(Dumba → Butun qo'y x1.0000)" formatdan sell mahsulot nomini ajratib olamiz
                                const match = m.reason.match(/\(([^→→]+)[→→]/);
                                const sellName = match ? match[1].trim() : null;
                                return sellName ? (
                                  <div className="flex items-center gap-1 mt-0.5">
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 border border-amber-200 text-amber-700 text-[10px] font-bold rounded">
                                      <span>⤷</span>
                                      <span>{sellName}</span>
                                    </span>
                                  </div>
                                ) : null;
                              })()}
                            </td>

                            <td className="px-4 py-3 text-sm text-slate-600 tabular-nums">{fmt(m.qty_before)}</td>
                            <td className="px-4 py-3">
                              <span className={`text-sm font-bold tabular-nums ${delta < 0 ? 'text-red-500' : delta > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                                {delta > 0 ? '+' : delta < 0 ? '−' : ''}{fmt(Math.abs(delta))}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span className={`text-sm font-bold tabular-nums ${qAfter < 0 ? 'text-red-600' : qAfter === 0 ? 'text-slate-400' : 'text-slate-800'}`}>
                                {fmt(qAfter)}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm text-slate-500 max-w-[140px] truncate">
                              {m.contragent_name || <span className="text-slate-300">—</span>}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-400">{m.product_unit || t('reports.unitPiece')}</td>
                            <td className="px-4 py-3 text-xs text-slate-400">{m.user_name || '—'}</td>
                          </tr>
                        );
                      })}
                      {movementsData.length === 0 && (
                        <tr><td colSpan={10} className="px-6 py-12 text-center text-sm text-slate-400">{t('reports.noDataChangeFilters')}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          );
        })()}


        {tab === 'pl' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <div>
                <span className="text-sm font-semibold text-slate-700">{t('reports.plReportTitle')}</span>
                {uzsNote}
              </div>
              <ExportBtns
                onPdf={() => {
                  if (!plData) return;
                  printTable(t('reports.plTitleWithPeriod', { from: plData.period?.from, to: plData.period?.to }),
                    [t('reports.th.indicator'), t('reports.th.amount'), t('reports.th.percent')],
                    [
                      [t('reports.pl.grossRevenue'), fmtS(plData.gross_revenue), ''],
                      [t('reports.pl.returns'), fmtS(plData.returns), ''],
                      [t('reports.pl.netRevenue'), fmtS(plData.revenue), '100%'],
                      [t('reports.pl.cogsFifo'), fmtS(plData.cogs), pct(plData.revenue > 0 ? plData.cogs / plData.revenue * 100 : 0)],
                      [t('finance.grossProfit'), fmtS(plData.gross_profit), pct(plData.gross_margin_pct)],
                      [t('reports.pl.expensesNegative'), fmtS(plData.expenses?.total), ''],
                      ...(plData.expenses?.by_category || []).map(c => [`  • ${c.name}`, fmtS(c.total), '']),
                      [t('finance.netProfit'), fmtS(plData.net_profit), pct(plData.net_margin_pct)],
                    ],
                    null,
                    t('common.print')
                  );
                }}
              />
            </div>
            {dateFilter}
            {loading ? <Spinner /> : plData ? (
              <div className="p-6 max-w-2xl">
                <p className="text-sm text-slate-500 mb-5">{t('finance.period')} <strong>{plData.period?.from}</strong> — <strong>{plData.period?.to}</strong></p>
                <div className="space-y-2">
                  {/* Ayiriladigan qatorlar (−) yorlig'i bilan musbat ko'rsatiladi; natija qatorlari o'z ishorasi bilan */}
                  {[
                    { label: t('reports.pl.grossRevenue'), value: plData.gross_revenue, cls: 'text-slate-800', pctV: null, bg: '' },
                    { label: t('reports.pl.returns'), value: plData.returns, cls: 'text-orange-500', pctV: plData.gross_revenue > 0 ? plData.returns / plData.gross_revenue * 100 : 0, bg: '' },
                    { label: t('reports.pl.netRevenue'), value: plData.revenue, signed: true, cls: 'font-semibold text-slate-800', pctV: 100, bg: 'bg-slate-50' },
                    { label: t('reports.pl.cogsFifo'), value: plData.cogs, cls: 'text-red-500', pctV: plData.revenue > 0 ? plData.cogs / plData.revenue * 100 : 0, bg: '' },
                    { label: t('finance.grossProfit'), value: plData.gross_profit, signed: true, cls: `font-bold ${plData.gross_profit >= 0 ? 'text-blue-600' : 'text-red-600'}`, pctV: plData.gross_margin_pct, bg: 'bg-blue-50' },
                    { label: t('reports.pl.expensesNegative'), value: plData.expenses?.total || 0, cls: 'text-red-500', pctV: plData.revenue > 0 ? (plData.expenses?.total || 0) / plData.revenue * 100 : 0, bg: '' },
                    { label: t('finance.netProfit'), value: plData.net_profit, signed: true, cls: `font-bold ${plData.net_profit >= 0 ? 'text-emerald-600' : 'text-red-600'}`, pctV: plData.net_margin_pct, bg: plData.net_profit >= 0 ? 'bg-emerald-50' : 'bg-red-50' },
                  ].map(row => (
                    <div key={row.label} className={`flex items-center justify-between p-3 rounded-xl ${row.bg || 'border border-slate-100'}`}>
                      <span className={`text-sm ${row.cls}`}>{row.label}</span>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-400">{row.pctV != null ? pct(row.pctV) : ''}</span>
                        <span className={`text-sm font-semibold ${row.cls} min-w-32 text-right`}>
                          {row.signed && (row.value ?? 0) < 0 ? '−' : ''}{fmtS(Math.abs(row.value ?? 0))}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                {plData.expenses?.by_category?.length > 0 && (
                  <div className="mt-6">
                    <p className="text-sm font-semibold text-slate-600 mb-3">{t('finance.expenseByCategory')}</p>
                    <div className="space-y-1.5">
                      {plData.expenses.by_category.map(c => (
                        <div key={c.name} className="flex items-center justify-between text-sm px-3 py-2 rounded-lg bg-slate-50">
                          <span className="text-slate-600">{c.name}</span>
                          <span className="font-medium text-red-500">{fmtS(c.total)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : <div className="py-12 text-center text-sm text-slate-400">{t('common.noData')}</div>}
          </>
        )}

        {/* ── Kassir hisoboti ── */}
        {tab === 'cashier' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.cashierReportTitle')}</span>
              <ExportBtns
                onExcel={() => saveSheet(cashierData.map(r => ({
                  [t('shift.cashier')]: r.cashier_name, [t('reports.th.salesCount')]: r.sales_count,
                  [t('reports.th.returns')]: r.returns_count, [`${t('reports.th.returns')} (${t('reports.th.amount')})`]: fmtDebt(r.returns_amount),
                  [t('reports.th.totalAmount')]: fmtDebt(r.total_amount), [t('reports.th.avgCheck')]: fmtDebt(r.avg_check), [t('reports.th.discount')]: fmtDebt(r.total_discount),
                })), t('shift.cashier'), `kassir_${today()}.xlsx`)}
                onPdf={() => printTable(t('reports.cashierReportTitle'),
                  [t('shift.cashier'), t('reports.th.salesCount'), t('reports.th.returns'), t('reports.th.totalAmount'), t('reports.th.avgCheck')],
                  cashierData.map(r => [r.cashier_name, r.sales_count, r.returns_count ? `${r.returns_count} (${fmtDebt(r.returns_amount)})` : '0', fmtDebt(r.total_amount), fmtDebt(r.avg_check)]),
                  null,
                  t('common.print')
                )}
              />
            </div>
            {cashBalance && (
              <div className="grid grid-cols-2 gap-4 px-6 py-4 border-b border-slate-100 bg-linear-to-r from-slate-50 to-blue-50/30">
                <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm">
                  <div className="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">{t('reports.totalIncome')}</div>
                  <div className="text-2xl font-black text-emerald-600">{fmtDebt(cashBalance.income_by_currency || {})}</div>
                </div>
                <div className="bg-white rounded-xl p-4 border border-red-100 shadow-sm">
                  <div className="text-xs font-bold text-red-500 uppercase tracking-widest mb-1">{t('reports.totalExpense')}</div>
                  <div className="text-2xl font-black text-red-500">{fmtDebt(cashBalance.expense_by_currency || {})}</div>
                </div>
              </div>
            )}
            {dateFilter}
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['#', t('shift.cashier'), t('reports.th.salesCount'), t('reports.th.returns'), t('reports.th.totalAmount'), t('reports.th.avgCheck'), t('reports.th.discount')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {cashierData.map((r, i) => (
                      <tr key={r.cashier_id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-5 py-3.5">
                          <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                            i === 0 ? 'bg-amber-100 text-amber-700' : i === 1 ? 'bg-slate-100 text-slate-600' : 'bg-slate-50 text-slate-400'
                          }`}>{i + 1}</span>
                        </td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{r.cashier_name}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-600">{r.sales_count} {t('common.item')}</td>
                        <td className="px-5 py-3.5 text-sm text-orange-600">
                          {r.returns_count > 0 ? `${r.returns_count} ${t('common.item')} · ${fmtDebt(r.returns_amount)}` : '—'}
                        </td>
                        <td className="px-5 py-3.5 text-sm font-bold text-emerald-600">{fmtDebt(r.total_amount)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtDebt(r.avg_check)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtDebt(r.total_discount)}</td>
                      </tr>
                    ))}
                    {cashierData.length === 0 && <tr><td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* ── O'lik stok ── */}
        {tab === 'deadstock' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.deadStockTitle')}</span>
              <ExportBtns
                onExcel={() => {
                  if (!deadStockData) return;
                  saveSheet(deadStockData.items.map(i => ({
                    [t('reports.th.product')]: i.product_name, 'SKU': i.sku,
                    [t('reports.th.qty')]: i.quantity, [t('reports.th.cost')]: i.cost_price, [t('reports.th.value')]: i.value,
                    [t('reports.th.lastSold')]: i.last_sold_at ? new Date(i.last_sold_at).toLocaleDateString('uz-UZ') : t('reports.neverSold'),
                  })), t('reports.tab.deadstock'), `olik_stok_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!deadStockData) return;
                  printTable(t('reports.deadStockReportTitle'),
                    [t('reports.th.product'), 'SKU', t('reports.th.qty'), t('reports.th.cost'), t('reports.th.value'), t('reports.th.lastSold')],
                    deadStockData.items.map(i => [i.product_name, i.sku, fmt(i.quantity), fmtS(i.cost_price), fmtS(i.value),
                      i.last_sold_at ? new Date(i.last_sold_at).toLocaleDateString('uz-UZ') : t('reports.neverSold')]),
                    [t('reports.total'), '', '', '', fmtS(deadStockData.total_value), ''],
                    t('common.print')
                  );
                }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2 px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <span className="text-xs font-medium text-slate-500 mr-1">{t('reports.termLabel')}:</span>
              {DEAD_MONTHS.map(n => (
                <button key={n} onClick={() => setDeadMonths(n)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                    deadMonths === n ? 'bg-blue-100 text-blue-700' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}>{n} {t('reports.monthsUnit')}</button>
              ))}
            </div>
            {loading ? <Spinner /> : deadStockData ? (
              <>
                <div className="grid grid-cols-3 gap-4 p-6 border-b border-slate-100">
                  <div className="bg-blue-50 rounded-xl p-4">
                    <div className="text-xs font-semibold text-blue-500 mb-1">{t('product.totalProducts')}</div>
                    <div className="text-2xl font-bold text-blue-700">{deadStockData.total_items} {t('common.item')}</div>
                  </div>
                  <div className="bg-amber-50 rounded-xl p-4">
                    <div className="text-xs font-semibold text-amber-600 mb-1">{t('reports.totalValue')}</div>
                    <div className="text-2xl font-bold text-amber-700">{fmtS(deadStockData.total_value)}</div>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-4">
                    <div className="text-xs font-semibold text-slate-500 mb-1">{t('reports.termLabel')}</div>
                    <div className="text-2xl font-bold text-slate-700">{deadStockData.months} {t('reports.monthsUnit')}</div>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {[t('reports.th.product'), 'SKU', t('reports.th.qty'), t('reports.th.cost'), t('reports.th.value'), t('reports.th.lastSold')].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {deadStockData.items.map((i) => (
                        <tr key={i.product_id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{i.product_name}</td>
                          <td className="px-5 py-3.5 text-sm font-mono text-blue-600">{i.sku}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-600">{fmt(i.quantity)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{fmtS(i.cost_price)}</td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-blue-600">{fmtS(i.value)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">
                            {i.last_sold_at ? new Date(i.last_sold_at).toLocaleDateString('uz-UZ') : t('reports.neverSold')}
                          </td>
                        </tr>
                      ))}
                      {deadStockData.items.length === 0 && (
                        <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-emerald-600">{t('reports.noDeadStock')}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </>
        )}

        {/* ── Xarajatlar ── */}
        {tab === 'expenses' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.expensesReportTitle')}</span>
              <ExportBtns
                onExcel={() => {
                  if (!expenseData) return;
                  saveSheet(expenseData.items.map(e => ({
                    [t('reports.th.category')]: e.category, [t('reports.th.amount')]: e.amount,
                    [t('reports.th.comment')]: e.description, [t('reports.th.date')]: new Date(e.created_at).toLocaleDateString('uz-UZ'),
                  })), t('reports.tab.expenses'), `xarajatlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!expenseData) return;
                  printTable(t('reports.expensesReportTitle'),
                    [t('reports.th.category'), t('reports.th.amount'), t('reports.th.comment'), t('reports.th.date')],
                    expenseData.items.map(e => [e.category, fmtS(e.amount), e.description, new Date(e.created_at).toLocaleDateString('uz-UZ')]),
                    [t('reports.total'), fmtS(expenseData.total), '', ''],
                    t('common.print')
                  );
                }}
              />
            </div>
            {dateFilter}
            {loading ? <Spinner /> : expenseData ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-red-50">
                  <span className="text-sm text-slate-600">{t('reports.totalExpenseLabel')} </span>
                  <strong className="text-red-600">{fmtS(expenseData.total)}</strong>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {[t('reports.th.category'), t('reports.th.amount'), t('reports.th.comment'), t('reports.th.date')].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {expenseData.items.map((e, i) => (
                        <tr key={e.id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                          <td className="px-5 py-3.5"><span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded-lg">{e.category}</span></td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-red-500">{fmtS(e.amount)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{e.description || '—'}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">{new Date(e.created_at).toLocaleDateString('uz-UZ')}</td>
                        </tr>
                      ))}
                      {expenseData.items.length === 0 && <tr><td colSpan={4} className="px-6 py-12 text-center text-sm text-slate-400">{t('finance.noExpenses')}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </>
        )}

        {/* ── Xaridlar ── */}
        {tab === 'purchases' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <div>
                <span className="text-sm font-semibold text-slate-700">{t('reports.purchasesBySupplierTitle')}</span>
                {uzsNote}
              </div>
              <ExportBtns
                onExcel={() => saveSheet(purchasesData.map(r => ({
                  [t('purchase.supplier')]: r.supplier_name, [t('common.phone')]: r.phone,
                  [t('reports.th.poCount')]: r.po_count, [t('reports.th.totalAmount')]: r.total_amount,
                })), t('reports.tab.purchases'), `xaridlar_${today()}.xlsx`)}
                onPdf={() => printTable(t('reports.purchasesReportTitle'),
                  [t('purchase.supplier'), t('common.phone'), t('reports.th.poCount'), t('reports.th.totalAmount')],
                  purchasesData.map(r => [r.supplier_name, r.phone, r.po_count, fmtS(r.total_amount)]),
                  [t('reports.total'), '', sumBy(purchasesData, 'po_count'), fmtS(sumBy(purchasesData, 'total_amount'))],
                  t('common.print')
                )}
              />
            </div>
            {dateFilter}
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('purchase.supplier'), t('common.phone'), t('reports.th.poCount'), t('reports.th.totalAmount')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {purchasesData.map((r, i) => (
                      <tr key={r.supplier_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.supplier_name}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{r.phone || '—'}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-600">{r.po_count} {t('common.item')}</td>
                        <td className="px-5 py-3.5 text-sm font-bold text-blue-600">{fmtS(r.total_amount)}</td>
                      </tr>
                    ))}
                    {purchasesData.length === 0 && <tr><td colSpan={4} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                  {purchasesData.length > 0 && (
                    <tfoot>
                      <tr className="bg-blue-50 font-bold">
                        <td className="px-5 py-3 text-sm text-slate-700">{t('reports.total')}</td>
                        <td />
                        <td className="px-5 py-3 text-sm">{sumBy(purchasesData, 'po_count')} {t('common.item')}</td>
                        <td className="px-5 py-3 text-sm text-blue-600">{fmtS(sumBy(purchasesData, 'total_amount'))}</td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}
          </>
        )}

        {/* ── Debitorlar ── */}
        {tab === 'customer-debts' && (
          <>
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
              <span className="text-sm font-semibold text-slate-700">{t('reports.customerDebtsTitle')}</span>
              <ExportBtns
                onExcel={() => {
                  if (!customerDebts) return;
                  const codes = Object.keys(customerDebts.total_debt || {});
                  saveSheet(customerDebts.items.map(c => ({
                    [t('sale.customer')]: c.customer_name, [t('common.phone')]: c.phone,
                    ...Object.fromEntries(codes.map(code => [`${t('reports.th.debt')} (${curLabel(code)})`, c.debts?.[code] || 0])),
                    [t('reports.th.limit')]: c.debt_limit, [t('reports.th.usagePct')]: c.usage_pct ?? '',
                  })), t('reports.tab.customerDebts'), `debitorlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!customerDebts) return;
                  printTable(t('reports.customerDebtsTitle'),
                    [t('sale.customer'), t('common.phone'), t('reports.th.debt'), t('reports.th.limit'), t('reports.th.usage')],
                    customerDebts.items.map(c => [c.customer_name, c.phone, fmtDebt(c.debts), c.debt_limit > 0 ? fmtS(c.debt_limit) : '—', c.usage_pct == null ? '—' : pct(c.usage_pct)]),
                    [t('reports.total'), '', fmtDebt(customerDebts.total_debt), '', ''],
                    t('common.print')
                  );
                }}
              />
            </div>
            {loading ? <Spinner /> : customerDebts ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-amber-50">
                  <span className="text-sm text-slate-600">{t('reports.totalDebtorDebtLabel')} </span>
                  <strong className="text-amber-700">{fmtDebt(customerDebts.total_debt)}</strong>
                  {Object.keys(customerDebts.total_debt || {}).some(c => c !== 'UZS') && (
                    <span className="ml-2 text-xs text-slate-500">{t('reports.debtUzsApprox', { amount: fmtS(customerDebts.total_debt_uzs) })}</span>
                  )}
                  <span className="ml-4 text-sm text-slate-500">({customerDebts.count} {t('customer.customers')})</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {[t('sale.customer'), t('common.phone'), t('reports.th.debt'), t('reports.th.limit'), t('reports.th.usage')].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {customerDebts.items.map((c, i) => (
                        <tr key={c.customer_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                          <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{c.customer_name}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{c.phone || '—'}</td>
                          <td className="px-5 py-3.5 text-sm font-bold text-amber-600">{fmtDebt(c.debts)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">{c.debt_limit > 0 ? fmtS(c.debt_limit) : '—'}</td>
                          <td className="px-5 py-3.5">
                            {c.usage_pct == null ? <span className="text-sm text-slate-300">—</span> : (
                              <div className="flex items-center gap-2">
                                <div className="flex-1 bg-slate-200 rounded-full h-1.5 min-w-16">
                                  <div className={`h-1.5 rounded-full ${c.usage_pct >= 90 ? 'bg-red-500' : c.usage_pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                                    style={{ width: `${Math.min(c.usage_pct, 100)}%` }} />
                                </div>
                                <span className="text-xs font-bold text-slate-600">{pct(c.usage_pct)}</span>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {customerDebts.items.length === 0 && <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-emerald-600">{t('reports.noDebtors')}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </>
        )}

        {/* ── Kreditorlar ── */}
        {tab === 'supplier-debts' && (
          <>
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
              <span className="text-sm font-semibold text-slate-700">{t('reports.supplierDebtsTitle')}</span>
              <ExportBtns
                onExcel={() => {
                  if (!supplierDebts) return;
                  const codes = Object.keys(supplierDebts.total_debt || {});
                  saveSheet(supplierDebts.items.map(s => ({
                    [t('purchase.supplier')]: s.supplier_name, [t('common.phone')]: s.phone,
                    ...Object.fromEntries(codes.map(code => [`${t('reports.th.debt')} (${curLabel(code)})`, s.debts?.[code] || 0])),
                    [t('finance.paymentTerms')]: `${s.payment_terms ?? 0} ${t('reports.daysUnit')}`,
                  })), t('reports.tab.supplierDebts'), `kreditorlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!supplierDebts) return;
                  printTable(t('reports.supplierDebtsTitle'),
                    [t('purchase.supplier'), t('common.phone'), t('reports.th.debt'), t('finance.paymentTerms')],
                    supplierDebts.items.map(s => [s.supplier_name, s.phone, fmtDebt(s.debts), `${s.payment_terms ?? 0} ${t('reports.daysUnit')}`]),
                    [t('reports.total'), '', fmtDebt(supplierDebts.total_debt), ''],
                    t('common.print')
                  );
                }}
              />
            </div>
            {loading ? <Spinner /> : supplierDebts ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-red-50">
                  <span className="text-sm text-slate-600">{t('reports.totalCreditorDebtLabel')} </span>
                  <strong className="text-red-600">{fmtDebt(supplierDebts.total_debt)}</strong>
                  {Object.keys(supplierDebts.total_debt || {}).some(c => c !== 'UZS') && (
                    <span className="ml-2 text-xs text-slate-500">{t('reports.debtUzsApprox', { amount: fmtS(supplierDebts.total_debt_uzs) })}</span>
                  )}
                  <span className="ml-4 text-sm text-slate-500">({supplierDebts.count} {t('purchase.supplier')})</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {[t('purchase.supplier'), t('common.phone'), t('reports.th.debt'), t('finance.paymentTerms')].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {supplierDebts.items.map((s, i) => (
                        <tr key={s.supplier_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                          <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{s.supplier_name}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.phone || '—'}</td>
                          <td className="px-5 py-3.5 text-sm font-bold text-red-600">{fmtDebt(s.debts)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.payment_terms ?? 0} {t('reports.daysUnit')}</td>
                        </tr>
                      ))}
                      {supplierDebts.items.length === 0 && <tr><td colSpan={4} className="px-6 py-12 text-center text-sm text-emerald-600">{t('reports.noCreditors')}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </>
        )}

        {/* ── ABC/XYZ tahlil ── */}
        {tab === 'abc' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <div>
                <span className="text-sm font-semibold text-slate-700">{t('reports.abcXyzTitle')}</span>
                <p className="text-xs text-slate-400 mt-0.5">{t('reports.abcXyzLegend')}</p>
              </div>
              <ExportBtns
                onExcel={() => saveSheet(abcData.map(r => ({
                  [t('reports.th.product')]: r.product_name, 'SKU': r.sku,
                  [t('reports.th.revenue')]: r.revenue, [t('reports.th.frequency')]: r.frequency, [t('reports.th.qty')]: r.qty,
                  'ABC': r.abc, 'XYZ': r.xyz, [t('reports.th.group')]: r.group,
                })), 'ABC-XYZ', `abc_xyz_${today()}.xlsx`)}
                onPdf={() => printTable(t('reports.abcXyzTitle'),
                  [t('reports.th.product'), t('reports.th.revenue'), t('reports.th.frequency'), 'ABC', 'XYZ', t('reports.th.group')],
                  abcData.map(r => [r.product_name, fmtS(r.revenue), r.frequency, r.abc, r.xyz, r.group]),
                  null,
                  t('common.print')
                )}
              />
            </div>
            {dateFilter}
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('reports.th.product'), t('reports.th.revenue'), t('reports.th.frequency'), t('reports.th.qty'), 'ABC', 'XYZ', t('reports.th.group')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {abcData.map((r, i) => (
                      <tr key={r.product_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.product_name}</td>
                        <td className={`px-5 py-3.5 text-sm font-semibold ${r.revenue < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtS(r.revenue)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{r.frequency}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmt(r.qty)}</td>
                        <td className="px-5 py-3.5">
                          <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                            r.abc === 'A' ? 'bg-emerald-100 text-emerald-700' : r.abc === 'B' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'
                          }`}>{r.abc}</span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                            r.xyz === 'X' ? 'bg-blue-100 text-blue-700' : r.xyz === 'Y' ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-500'
                          }`}>{r.xyz}</span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`px-2 py-0.5 rounded-lg text-xs font-bold ${
                            r.group === 'AX' ? 'bg-emerald-100 text-emerald-700' :
                            r.group === 'AY' || r.group === 'BX' ? 'bg-blue-100 text-blue-700' :
                            r.group.startsWith('C') || r.group.endsWith('Z') ? 'bg-slate-100 text-slate-500' : 'bg-amber-100 text-amber-700'
                          }`}>{r.group}</span>
                        </td>
                      </tr>
                    ))}
                    {abcData.length === 0 && <tr><td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* ── Partiyalar (FIFO) ── */}
        {tab === 'batches' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <div>
                <span className="text-sm font-semibold text-slate-700">{t('reports.batchesReportTitle')}</span>
                <p className="text-xs text-slate-400 mt-0.5">{t('reports.batchesDesc')}</p>
              </div>
              <ExportBtns
                onExcel={() => saveSheet(batchData.map(r => ({
                  [t('reports.th.product')]: r.product_name, Lot: r.lot_number,
                  [t('reports.th.cost')]: r.purchase_price, [t('reports.th.initialQty')]: r.initial_quantity,
                  [t('reports.th.remaining')]: r.remaining_quantity, [t('reports.th.sold')]: r.sold_qty,
                  [t('reports.th.revenue')]: r.revenue, [t('reports.th.profit')]: r.profit, [t('reports.th.marginPct')]: r.margin_pct,
                })), t('reports.tab.batches'), `partiyalar_${today()}.xlsx`)}
                onPdf={() => printTable(t('reports.batchesFifoTitle'),
                  [t('reports.th.product'), 'Lot', t('reports.th.cost'), t('reports.th.remaining'), t('reports.th.sold'), t('reports.th.revenue'), t('reports.th.profit')],
                  batchData.map(r => [r.product_name, r.lot_number, fmtS(r.purchase_price), fmt(r.remaining_quantity), fmt(r.sold_qty), fmtS(r.revenue), fmtS(r.profit)]),
                  [t('reports.total'), '', '', '', fmt(sumBy(batchData, 'sold_qty')), fmtS(sumBy(batchData, 'revenue')), fmtS(sumBy(batchData, 'profit'))],
                  t('common.print')
                )}
              />
            </div>
            {dateFilter}
            {!loading && batchData.length > 0 && (
              <div className="grid grid-cols-4 gap-4 px-6 py-4 border-b border-slate-100 bg-slate-50">
                {[
                  { label: t('reports.totalBatches'), val: `${batchData.length} ${t('common.item')}`, cls: 'text-blue-600' },
                  { label: t('reports.totalSold'), val: `${fmt(sumBy(batchData, 'sold_qty'))} ${t('reports.unitPiece')}`, cls: 'text-slate-700' },
                  { label: t('reports.totalRevenueLabel'), val: fmtS(sumBy(batchData, 'revenue')), cls: 'text-emerald-600' },
                  { label: t('reports.totalProfitLabel'), val: fmtS(sumBy(batchData, 'profit')), cls: sumBy(batchData, 'profit') < 0 ? 'text-red-600' : 'text-emerald-700' },
                ].map(c => (
                  <div key={c.label} className="bg-white rounded-xl p-3 border border-slate-100 shadow-sm">
                    <div className="text-xs text-slate-400 mb-1">{c.label}</div>
                    <div className={`text-lg font-bold ${c.cls}`}>{c.val}</div>
                  </div>
                ))}
              </div>
            )}
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('reports.productNameLabel'), 'Lot', t('reports.th.cost'), t('reports.th.initialQty'), t('reports.th.remaining'), t('reports.th.sold'), t('reports.th.revenue'), t('reports.th.profit'), t('reports.th.margin')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {batchData.map(r => (
                      <tr key={r.batch_id} className={`hover:bg-slate-50 transition-colors${r.remaining_quantity === 0 ? ' opacity-50' : ''}`}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.product_name}</td>
                        <td className="px-5 py-3.5">
                          <span className="text-xs font-mono px-2 py-0.5 bg-slate-100 text-slate-600 rounded">{r.lot_number || '—'}</span>
                        </td>
                        <td className="px-5 py-3.5 text-sm font-bold text-blue-700">{fmtS(r.purchase_price)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmt(r.initial_quantity)}</td>
                        <td className="px-5 py-3.5">
                          <span className={`text-sm font-bold ${r.remaining_quantity > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                            {fmt(r.remaining_quantity)}{r.remaining_quantity === 0 ? ` (${t('reports.finished')})` : ''}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-sm text-slate-700">{fmt(r.sold_qty)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-700">{fmtS(r.revenue)}</td>
                        <td className={`px-5 py-3.5 text-sm font-semibold ${r.profit < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtS(r.profit)}</td>
                        <td className="px-5 py-3.5"><MarginBar value={r.margin_pct} width="w-12" /></td>
                      </tr>
                    ))}
                    {batchData.length === 0 && (
                      <tr><td colSpan={9} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
