import { useState, useEffect, useCallback, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';
import api from '../../api/axios';
import toast from 'react-hot-toast';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtS = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const pct = (v) => `${Number(v || 0).toFixed(1)}%`;
// Multi-currency dict formatter: {UZS: 1000, USD: 5} -> "1,000 so'm + 5 USD"
const fmtDebt = (v) => {
  if (!v) return "0 so'm";
  if (typeof v === 'object' && !Array.isArray(v)) {
    const parts = Object.entries(v).filter(([, amt]) => Math.abs(amt) > 0.001)
      .map(([c, amt]) => `${Number(Number(amt).toFixed(2)).toLocaleString('uz-UZ')} ${c === 'UZS' ? "so'm" : c}`);
    return parts.length ? parts.join(' + ') : "0 so'm";
  }
  return fmtS(v);
};
const fmtRowDebt = (balance, currency) => {
  const curr = currency || 'UZS';
  return `${Number(balance || 0).toLocaleString('uz-UZ')} ${curr === 'UZS' ? "so'm" : curr}`;
};

const sumDebtList = (list, key) => {
  const result = {};
  list.forEach(item => {
    const val = item[key];
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      Object.entries(val).forEach(([c, amt]) => {
        result[c] = (result[c] || 0) + amt;
      });
    } else {
      result['UZS'] = (result['UZS'] || 0) + Number(val || 0);
    }
  });
  return result;
};

// ─── Kunlik sanalar ────────────────────────────────────────────────────────────
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const firstOfMonth = () => {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
};

// ─── PDF chop etish (window.print orqali) ─────────────────────────────────────
function printTable(title, headers, rows, totalsRow = null, printLabel = 'Print') {
  const headerHtml = headers.map(h => `<th style="border:1px solid #ddd;padding:8px;background:#f3f4f6;font-size:12px">${h}</th>`).join('');
  const rowsHtml = rows.map((row, i) =>
    `<tr style="background:${i % 2 ? '#f9fafb' : '#fff'}">${row.map(cell =>
      `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${cell ?? '—'}</td>`
    ).join('')}</tr>`
  ).join('');
  const totalsHtml = totalsRow
    ? `<tr style="background:#e0f2fe;font-weight:bold">${totalsRow.map(cell =>
        `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${cell ?? ''}</td>`
      ).join('')}</tr>`
    : '';

  const win = window.open('', '_blank');
  win.document.write(`<!DOCTYPE html><html><head><title>${title}</title>
    <style>body{font-family:Arial,sans-serif;margin:20px}h2{color:#1e293b}table{border-collapse:collapse;width:100%}@media print{button{display:none}}</style>
    </head><body>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2>${title}</h2>
      <div style="font-size:12px;color:#64748b">${new Date().toLocaleString('uz-UZ')}</div>
    </div>
    <table><thead><tr>${headerHtml}</tr></thead>
    <tbody>${rowsHtml}${totalsHtml}</tbody></table>
    <div style="margin-top:16px;text-align:center">
      <button onclick="window.print()" style="padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">${printLabel}</button>
    </div></body></html>`);
  win.document.close();
}

// ─── Umumiy Tab tugmasi ────────────────────────────────────────────────────────
function TabBtn({ label, icon, active, onClick }) {
  const { t } = useLang();
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
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.date.to')}</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
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

// ─── Asosiy komponent ─────────────────────────────────────────────────────────
export default function Reports() {
  const { t } = useLang();
  const [tab, setTab] = useState('sales');
  const urlReadRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(today());
  const [dateTo, setDateTo] = useState(today());
  const [branchId, setBranchId] = useState('');
  const [branches, setBranches] = useState([]);

  // Ma'lumotlar
  const [salesData, setSalesData] = useState({ items: [], summary: null });
  const [expenseData, setExpenseData] = useState(null);
  const [profitData, setProfitData] = useState([]);
  const [cashierData, setCashierData] = useState([]);
  const [cashBalance, setCashBalance] = useState(null);
  const [deadStockData, setDeadStockData] = useState(null);
  const [purchasesData, setPurchasesData] = useState([]);
  const [customerDebts, setCustomerDebts] = useState(null);
  const [supplierDebts, setSupplierDebts] = useState(null);
  const [abcData, setAbcData] = useState([]);
  const [plData, setPlData] = useState(null);
  const [batchData, setBatchData] = useState([]);
  const [productSalesData, setProductSalesData] = useState([]);
  const [movementsData, setMovementsData] = useState([]);
  const [movSearch, setMovSearch] = useState('');
  const [movRefType, setMovRefType] = useState('');
  const [movDateFrom, setMovDateFrom] = useState(today());
  const [movDateTo, setMovDateTo] = useState(today());
  const [fromSellProduct, setFromSellProduct] = useState('');
  const [convRatio, setConvRatio] = useState('');
  const [movProductId, setMovProductId] = useState('');

  // Load branches on mount
  useEffect(() => {
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('reports.errorOccurred')) });
  }, []);

  const qs = () => {
    const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    if (branchId) p.set('branch_id', branchId);
    return '?' + p.toString();
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === 'sales') {
        const r = await api.get(`/reports/sales${qs()}&include_returns=false`);
        // Backend { items: [...], summary: {...} } yoki oddiy array qaytaradi
        const data = r.data;
        if (data && Array.isArray(data.items)) {
          setSalesData(data);
        } else if (Array.isArray(data)) {
          setSalesData({ items: data, summary: null });
        } else {
          setSalesData({ items: [], summary: null });
        }
      } else if (tab === 'expenses') {
        const r = await api.get(`/reports/expenses${qs()}`);
        setExpenseData(r.data);
      } else if (tab === 'profit') {
        const r = await api.get(`/reports/profit${qs()}`);
        setProfitData(r.data);
      } else if (tab === 'cashier') {
        const r = await api.get(`/reports/cashier-report${qs()}`);
        setCashierData(r.data);
        try { const cb = await api.get('/finance/cash-balance'); setCashBalance(cb.data); } catch { /* ignore */ }
      } else if (tab === 'deadstock') {
        const r = await api.get('/reports/dead-stock');
        setDeadStockData(r.data);
      } else if (tab === 'purchases') {
        const r = await api.get(`/reports/purchases${qs()}`);
        setPurchasesData(r.data);
      } else if (tab === 'customer-debts') {
        const r = await api.get('/reports/customer-debts');
        setCustomerDebts(r.data);
      } else if (tab === 'supplier-debts') {
        const r = await api.get('/reports/supplier-debts');
        setSupplierDebts(r.data);
      } else if (tab === 'abc') {
        const r = await api.get(`/reports/abc-xyz${qs()}`);
        setAbcData(r.data);
      } else if (tab === 'pl') {
        const r = await api.get(`/reports/profit-loss${qs()}`);
        setPlData(r.data);
      } else if (tab === 'batches') {
        const r = await api.get(`/reports/batches${qs()}`);
        setBatchData(r.data);
      } else if (tab === 'product-sales') {
        const r = await api.get(`/reports/product-sales${qs()}`);
        setProductSalesData(r.data);
      } else if (tab === 'movements') {
        const p = new URLSearchParams({ date_from: movDateFrom, date_to: movDateTo, limit: '300' });
        if (movSearch) p.set('search', movSearch);
        if (movRefType) p.set('reference_type', movRefType);
        if (movProductId) p.set('product_id', movProductId);
        const r = await api.get(`/inventory/movements?${p}`);
        setMovementsData(r.data);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tab, dateFrom, dateTo, branchId]);

  useEffect(() => { load(); }, [tab]);

  // URL params orqali kelganda avtomatik tab va filtr
  useEffect(() => {
    if (urlReadRef.current) return;
    urlReadRef.current = true;
    const params = new URLSearchParams(window.location.search);
    const urlTab = params.get('tab');
    const urlProductId = params.get('product_id');
    const urlProductName = params.get('product_name');
    const urlFromSell = params.get('from_sell');
    const urlRatio = params.get('ratio');
    if (urlTab === 'movements') {
      setTab('movements');
      if (urlProductName) setMovSearch(decodeURIComponent(urlProductName));
      if (urlProductId) setMovProductId(urlProductId);
      if (urlFromSell) setFromSellProduct(decodeURIComponent(urlFromSell));
      if (urlRatio) setConvRatio(urlRatio);
      setMovDateFrom(daysAgo(29));
      setMovDateTo(today());
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t('reports.title')}</h1>
        <p className="text-slate-500 text-sm mt-0.5">{t('reports.subtitle')}</p>
      </div>

      {/* Branch filter */}
      {branches.length > 0 && (
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
          {tabs.map(t => (
            <TabBtn key={t.key} label={t.label} icon={t.icon} active={tab === t.key} onClick={() => setTab(t.key)} />
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">

        {/* ── Sotuvlar ── */}
        {tab === 'sales' && (() => {
          const items = salesData?.items || [];
          const totalSum = items.reduce((a, s) => a + s.total_amount, 0);
          return (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.salesListTitle')}</span>
              <ExportBtns
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(items.map(s => ({
                    [t('reports.th.number')]: s.number, [t('reports.th.cashier')]: s.cashier_name,
                    [t('reports.th.amount')]: s.total_amount, [t('reports.th.discount')]: s.discount_amount,
                    [t('reports.th.payment')]: s.payment_type, [t('reports.th.date')]: new Date(s.created_at).toLocaleString('uz-UZ'),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.sales'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `sotuvlar_${today()}.xlsx`);
                }}
                onPdf={() => printTable(t('reports.salesReportTitle'),
                  [t('reports.th.number'), t('reports.th.cashier'), t('reports.th.amount'), t('reports.th.payment'), t('reports.th.date')],
                  items.map(s => [s.number, s.cashier_name, fmtRowDebt(s.total_amount, s.currency_code), s.payment_type, new Date(s.created_at).toLocaleDateString('uz-UZ')]),
                  ['', t('reports.total'), fmtS(totalSum), '', ''],
                  t('common.print')
                )}
                on1c={async () => {
                  const saveAs = await loadSaveAs();
                  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, format: 'csv' });
                  const r = await api.get(`/reports/1c-export?${params}`, { responseType: 'blob' });
                  saveAs(r.data, `1c_export_${today()}.csv`);
                }}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
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
                      {items.map(s => (
                        <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-5 py-3.5 text-sm font-mono font-semibold text-blue-600">{s.number}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-700">{s.cashier_name}</td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{fmtRowDebt(s.total_amount, s.currency_code)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.discount_amount > 0 ? fmtRowDebt(s.discount_amount, s.currency_code) : '—'}</td>
                          <td className="px-5 py-3.5">
                            <span className="inline-flex px-2 py-0.5 bg-blue-50 text-blue-600 text-xs font-medium rounded-lg">{s.payment_type}</span>
                          </td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">{new Date(s.created_at).toLocaleString('uz-UZ')}</td>
                        </tr>
                      ))}
                      {items.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                    </tbody>
                  </table>
                </div>
                {items.length > 0 && (
                  <div className="px-6 py-3 border-t border-slate-100 flex justify-between text-sm text-slate-500 bg-slate-50">
                    <span>{t('reports.totalSalesCount', { count: items.length })}</span>
                    <span>{t('reports.overallLabel')} <strong className="text-emerald-600">{fmtS(totalSum)}</strong></span>
                  </div>
                )}
              </>
            )}
          </>
          );
        })()}

        {/* ── Foyda (mahsulot bo'yicha) ── */}
        {tab === 'profit' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.profitByProductTitle')}</span>
              <ExportBtns
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(profitData.map(r => ({
                    [t('reports.th.product')]: r.product_name, 'SKU': r.sku, [t('reports.th.category')]: r.category_name,
                    [t('reports.th.sold')]: r.qty_sold, [t('reports.th.revenue')]: fmtDebt(r.revenue), [t('reports.th.cost')]: fmtDebt(r.cost),
                    [t('reports.th.profit')]: fmtDebt(r.profit), [t('reports.th.marginPct')]: r.margin_pct,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.th.profit'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `foyda_${today()}.xlsx`);
                }}
                onPdf={() => printTable(t('reports.profitByProductTitle'),
                  [t('reports.th.product'), t('reports.th.category'), t('reports.th.sold'), t('reports.th.revenue'), t('reports.th.cost'), t('reports.th.profit'), t('reports.th.margin')],
                  profitData.map(r => [r.product_name, r.category_name, fmt(r.qty_sold), fmtDebt(r.revenue), fmtDebt(r.cost), fmtDebt(r.profit), pct(r.margin_pct)]),
                  [t('reports.total'), '', '', '', '', '', ''],
                  t('common.print')
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
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
                        <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{fmtDebt(r.revenue)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtDebt(r.cost)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-emerald-600">{fmtDebt(r.profit)}</td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 bg-slate-200 rounded-full h-1.5 min-w-12">
                              <div className="h-1.5 rounded-full bg-emerald-500 transition-all" style={{ width: `${Math.min(r.margin_pct, 100)}%` }} />
                            </div>
                            <span className="text-xs font-bold text-emerald-600">{pct(r.margin_pct)}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {profitData.length === 0 && <tr><td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                  {profitData.length > 0 && (
                    <tfoot>
                      <tr className="bg-blue-50 font-bold">
                        <td className="px-5 py-3 text-sm text-slate-700">{t('reports.total')}</td>
                        <td />
                        <td className="px-5 py-3 text-sm">{fmt(profitData.reduce((a, r) => a + r.qty_sold, 0))}</td>
                        <td className="px-5 py-3 text-sm">{fmtDebt(sumDebtList(profitData, 'revenue'))}</td>
                        <td className="px-5 py-3 text-sm">{fmtDebt(sumDebtList(profitData, 'cost'))}</td>
                        <td className="px-5 py-3 text-sm text-emerald-600">{fmtDebt(sumDebtList(profitData, 'profit'))}</td>
                        <td />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}
          </>
        )}

        {/* ── Mahsulotlar (Sotuv) ── */}
        {tab === 'product-sales' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('reports.productSalesReportTitle')}</span>
              <ExportBtns
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(productSalesData.map(r => ({
                    [t('reports.th.product')]: r.product_name, 'SKU': r.sku,
                    [t('reports.th.soldQty')]: r.total_qty, [t('reports.th.revenue')]: fmtDebt(r.total_revenue), [t('reports.th.profit')]: fmtDebt(r.total_profit),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.productSales'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `mahsulot_sotuv_${today()}.xlsx`);
                }}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('reports.th.product'), 'SKU', t('reports.th.soldQty'), t('reports.th.revenue'), t('reports.th.profit')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {productSalesData.map((r, i) => (
                      <tr key={r.product_id} className={i % 2 ? 'bg-slate-50/50 hover:bg-slate-100 transition-colors' : 'bg-white hover:bg-slate-50 transition-colors'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.product_name}</td>
                        <td className="px-5 py-3.5 text-sm font-mono text-blue-600">{r.sku}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-600 font-bold">{fmt(r.total_qty)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-emerald-600">{fmtDebt(r.total_revenue)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-blue-600">{fmtDebt(r.total_profit)}</td>
                      </tr>
                    ))}
                    {productSalesData.length === 0 && <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                  {productSalesData.length > 0 && (
                    <tfoot>
                      <tr className="bg-blue-50 font-bold">
                        <td className="px-5 py-3 text-sm text-slate-700">{t('reports.total')}</td>
                        <td />
                        <td className="px-5 py-3 text-sm">{fmt(productSalesData.reduce((a, r) => a + r.total_qty, 0))}</td>
                        <td className="px-5 py-3 text-sm text-emerald-600">{fmtDebt(sumDebtList(productSalesData, 'total_revenue'))}</td>
                        <td className="px-5 py-3 text-sm text-blue-600">{fmtDebt(sumDebtList(productSalesData, 'total_profit'))}</td>
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
          const OP_MAP = {
            // IN variants
            'IN_purchase_order':        { label: t('reports.op.inPurchase'),      bg: 'bg-emerald-100', text: 'text-emerald-700' },
            'IN_manual_receive':        { label: t('reports.op.manualReceive'),   bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'IN_return_from_customer':  { label: t('reports.op.returnCustomer'),  bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'IN_customer_return':       { label: t('reports.op.returnCustomer'),  bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'IN_inventory_count':       { label: t('reports.op.inventoryPlus'),   bg: 'bg-blue-100',  text: 'text-blue-700' },
            'IN_stock_transfer':        { label: t('reports.op.transferIn'),      bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'IN_transfer':              { label: t('reports.op.transferIn'),      bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'IN_':                      { label: t('reports.op.receive'),         bg: 'bg-emerald-100', text: 'text-emerald-700' },
            // OUT variants
            'OUT_sale':                 { label: t('reports.tab.sales'),          bg: 'bg-blue-100',  text: 'text-blue-700' },
            'OUT_chiqim':               { label: t('reports.op.expense'),         bg: 'bg-orange-100',  text: 'text-orange-700' },
            'OUT_return_to_supplier':   { label: t('reports.op.returnSupplier'),  bg: 'bg-amber-100',   text: 'text-amber-700'  },
            'OUT_inventory_count':      { label: t('reports.op.inventoryMinus'),  bg: 'bg-blue-100', text: 'text-blue-700' },
            'OUT_stock_transfer':       { label: t('reports.op.transferOut'),     bg: 'bg-slate-100',   text: 'text-slate-600'  },
            'OUT_transfer':             { label: t('reports.op.transferOut'),     bg: 'bg-slate-100',   text: 'text-slate-600'  },
            'OUT_':                     { label: t('reports.op.expense'),         bg: 'bg-orange-100',  text: 'text-orange-700' },
            // ADJUST
            'ADJUST_adjustment':        { label: t('reports.op.adjustment'),      bg: 'bg-slate-100',   text: 'text-slate-700'  },
            'ADJUST_inventory_count':   { label: t('warehouse.inventory'), bg: 'bg-blue-100',  text: 'text-blue-700' },
            'ADJUST_':                  { label: t('reports.op.adjustment'),      bg: 'bg-slate-100',   text: 'text-slate-700'  },
            // TRANSFER
            'TRANSFER_IN_transfer':     { label: t('reports.op.transferIn'),      bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'TRANSFER_IN_stock_transfer':{ label: t('reports.op.transferIn'),     bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'TRANSFER_IN_':             { label: t('reports.op.transferIn'),      bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'TRANSFER_OUT_transfer':    { label: t('reports.op.transferOut'),     bg: 'bg-slate-100',   text: 'text-slate-600'  },
            'TRANSFER_OUT_stock_transfer':{ label: t('reports.op.transferOut'),   bg: 'bg-slate-100',   text: 'text-slate-600'  },
            'TRANSFER_OUT_':            { label: t('reports.op.transferOut'),     bg: 'bg-slate-100',   text: 'text-slate-600'  },
            // RETURN
            'RETURN_return':            { label: t('reports.op.returnGeneric'),   bg: 'bg-blue-100',    text: 'text-blue-700'   },
            'RETURN_':                  { label: t('reports.op.returnGeneric'),   bg: 'bg-blue-100',    text: 'text-blue-700'   },
          };
          const getOp = (m) => {
            const key = `${m.type}_${m.reference_type || ''}`;
            return (
              OP_MAP[key] ||
              OP_MAP[`${m.type}_`] ||
              { label: m.reference_type ? m.reference_type.replace(/_/g, ' ') : m.type, bg: 'bg-slate-100', text: 'text-slate-600' }
            );
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
          const inCount  = movementsData.filter(m => m.type === 'IN').length;
          const outCount = movementsData.filter(m => m.type === 'OUT').length;
          return (
            <>
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
                <span className="text-sm font-bold text-slate-700">{`📦 ${t('reports.movementsReportTitle')}`}</span>
                <button onClick={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(movementsData.map(m => ({
                    [t('reports.th.date')]: new Date(m.created_at).toLocaleString('uz-UZ'),
                    [t('reports.th.operation')]: getOp(m).label,
                    [t('reports.th.product')]: m.product_name,
                    'SKU': m.product_sku || '',
                    [t('reports.th.qtyBefore')]: Number(m.qty_before),
                    [t('reports.th.change')]: m.type === 'OUT' ? -Number(m.quantity) : Number(m.quantity),
                    [t('reports.th.qtyAfter')]: Number(m.qty_after),
                    [t('reports.th.contragent')]: m.contragent_name || '',
                    [t('reports.th.unit')]: m.product_unit || t('reports.unitPiece'),
                    [t('reports.th.user')]: m.user_name || '',
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.movements'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `mahsulot_harakatlar_${today()}.xlsx`);
                }} className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors">
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
                    { l: t('reports.date.today'), f: today(), t: today() },
                    { l: t('reports.date.thisWeek'), f: daysAgo(6), t: today() },
                    { l: t('reports.date.thisMonth'), f: firstOfMonth(), t: today() },
                    { l: t('reports.date.last30'), f: daysAgo(29), t: today() },
                  ].map(p => (
                    <button key={p.l} onClick={() => { setMovDateFrom(p.f); setMovDateTo(p.t); }}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                        movDateFrom === p.f && movDateTo === p.t
                          ? 'bg-blue-100 text-blue-700' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}>{p.l}</button>
                  ))}
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.dateFromLabel')}</label>
                    <input type="date" value={movDateFrom} onChange={e => setMovDateFrom(e.target.value)}
                      className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.dateToLabel')}</label>
                    <input type="date" value={movDateTo} onChange={e => setMovDateTo(e.target.value)}
                      className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-500 mb-1">{t('product.title')}</label>
                    <input value={movSearch} onChange={e => setMovSearch(e.target.value)}
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
                    { l: t('reports.totalMovements'), v: `${movementsData.length} ${t('common.item')}`, color: 'slate' },
                    { l: t('reports.inCount'), v: `${inCount} ${t('common.item')}`, color: 'emerald' },
                    { l: t('reports.outCount'), v: `${outCount} ${t('common.item')}`, color: 'red' },
                  ].map(c => (
                    <div key={c.l} className="bg-white rounded-xl border border-slate-100 p-4 flex items-center gap-3 shadow-sm">
                      <div>
                        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{c.l}</div>
                        <div className={`text-xl font-black text-${c.color}-600 mt-0.5`}>{c.v}</div>
                      </div>
                    </div>
                  ))}
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
                        const delta = m.type === 'OUT' || m.type === 'TRANSFER_OUT'
                          ? -Math.abs(Number(m.quantity))
                          : Math.abs(Number(m.quantity));
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
                                const match = m.reason.match(/\(([^→\u2192]+)[→\u2192]/);
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
                              <span className={`text-sm font-bold tabular-nums ${delta < 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                                {delta > 0 ? '+' : ''}{fmt(Math.abs(delta))}
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
              <span className="text-sm font-semibold text-slate-700">{t('reports.plReportTitle')}</span>
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
                    t('common.print')
                  );
                }}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : plData ? (
              <div className="p-6 max-w-2xl">
                <p className="text-sm text-slate-500 mb-5">{t('finance.period')} <strong>{plData.period?.from}</strong> — <strong>{plData.period?.to}</strong></p>
                <div className="space-y-2">
                  {[
                    { label: t('reports.pl.grossRevenue'), value: plData.gross_revenue, cls: 'text-slate-800', pctV: null, bg: '' },
                    { label: t('reports.pl.returns'), value: -plData.returns, cls: 'text-orange-500', pctV: plData.revenue > 0 ? plData.returns / plData.gross_revenue * 100 : 0, bg: '' },
                    { label: t('reports.pl.netRevenue'), value: plData.revenue, cls: 'font-semibold text-slate-800', pctV: 100, bg: 'bg-slate-50' },
                    { label: t('reports.pl.cogsFifo'), value: -plData.cogs, cls: 'text-red-500', pctV: plData.revenue > 0 ? plData.cogs / plData.revenue * 100 : 0, bg: '' },
                    { label: t('finance.grossProfit'), value: plData.gross_profit, cls: 'font-bold text-blue-600', pctV: plData.gross_margin_pct, bg: 'bg-blue-50' },
                    { label: t('reports.pl.expensesNegative'), value: -plData.expenses?.total, cls: 'text-red-500', pctV: plData.revenue > 0 ? plData.expenses?.total / plData.revenue * 100 : 0, bg: '' },
                    { label: t('finance.netProfit'), value: plData.net_profit, cls: `font-bold ${plData.net_profit >= 0 ? 'text-emerald-600' : 'text-red-600'}`, pctV: plData.net_margin_pct, bg: plData.net_profit >= 0 ? 'bg-emerald-50' : 'bg-red-50' },
                  ].map(row => (
                    <div key={row.label} className={`flex items-center justify-between p-3 rounded-xl ${row.bg || 'border border-slate-100'}`}>
                      <span className={`text-sm ${row.cls}`}>{row.label}</span>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-400">{row.pctV != null ? pct(Math.abs(row.pctV)) : ''}</span>
                        <span className={`text-sm font-semibold ${row.cls} min-w-32 text-right`}>{fmtS(Math.abs(row.value ?? 0))}</span>
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
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(cashierData.map(r => ({
                    [t('shift.cashier')]: r.cashier_name, [t('reports.tab.sales')]: r.sales_count,
                    [t('reports.th.totalAmount')]: fmtDebt(r.total_amount), [t('reports.th.avgCheck')]: fmtDebt(r.avg_check), [t('reports.th.discount')]: fmtDebt(r.total_discount),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('shift.cashier'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `kassir_${today()}.xlsx`);
                }}
                onPdf={() => printTable(t('reports.cashierReportTitle'),
                  [t('shift.cashier'), t('reports.tab.sales'), t('reports.th.totalAmount'), t('reports.th.avgCheck')],
                  cashierData.map(r => [r.cashier_name, r.sales_count, fmtDebt(r.total_amount), fmtDebt(r.avg_check)]),
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
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['#', t('shift.cashier'), t('reports.th.salesCount'), t('reports.th.totalAmount'), t('reports.th.avgCheck'), t('reports.th.discount')].map(h => (
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
                        <td className="px-5 py-3.5 text-sm font-bold text-emerald-600">{fmtDebt(r.total_amount)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtDebt(r.avg_check)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtDebt(r.total_discount)}</td>
                      </tr>
                    ))}
                    {cashierData.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
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
                onExcel={async () => {
                  if (!deadStockData) return;
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(deadStockData.items.map(i => ({
                    [t('reports.th.product')]: i.product_name, 'SKU': i.sku,
                    [t('reports.th.qty')]: i.quantity, [t('reports.th.cost')]: fmtRowDebt(i.cost_price, i.currency), [t('reports.th.value')]: fmtRowDebt(i.value, i.currency),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.deadstock'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `olik_stok_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!deadStockData) return;
                  printTable(t('reports.deadStockReportTitle'),
                    [t('reports.th.product'), 'SKU', t('reports.th.qty'), t('reports.th.cost'), t('reports.th.value')],
                    deadStockData.items.map(i => [i.product_name, i.sku, i.quantity, fmtRowDebt(i.cost_price, i.currency), fmtRowDebt(i.value, i.currency)]),
                    [t('reports.total'), '', '', '', fmtDebt(deadStockData.total_value)],
                    t('common.print')
                  );
                }}
              />
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
                    <div className="text-2xl font-bold text-amber-700">{fmtDebt(deadStockData.total_value)}</div>
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
                        {[t('reports.th.product'), 'SKU', t('reports.th.qty'), t('reports.th.cost'), t('reports.th.value')].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {deadStockData.items.map((i) => (
                        <tr key={i.product_id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{i.product_name}</td>
                          <td className="px-5 py-3.5 text-sm font-mono text-blue-600">{i.sku}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-600">{i.quantity}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{fmtRowDebt(i.cost_price, i.currency)}</td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-blue-600">{fmtRowDebt(i.value, i.currency)}</td>
                        </tr>
                      ))}
                      {deadStockData.items.length === 0 && (
                        <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-emerald-600">{t('reports.noDeadStock')}</td></tr>
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
                onExcel={async () => {
                  if (!expenseData) return;
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(expenseData.items.map(e => ({
                    [t('reports.th.category')]: e.category, [t('reports.th.amount')]: e.amount,
                    [t('reports.th.comment')]: e.description, [t('reports.th.date')]: new Date(e.created_at).toLocaleDateString('uz-UZ'),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.expenses'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `xarajatlar_${today()}.xlsx`);
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
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
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
              <span className="text-sm font-semibold text-slate-700">{t('reports.purchasesBySupplierTitle')}</span>
              <ExportBtns
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(purchasesData.map(r => ({
                    [t('purchase.supplier')]: r.supplier_name, [t('common.phone')]: r.phone,
                    [t('reports.th.poCount')]: r.po_count, [t('reports.th.totalAmount')]: r.total_amount,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.purchases'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `xaridlar_${today()}.xlsx`);
                }}
                onPdf={() => printTable(t('reports.purchasesReportTitle'),
                  [t('purchase.supplier'), t('common.phone'), t('reports.th.poCount'), t('reports.th.totalAmount')],
                  purchasesData.map(r => [r.supplier_name, r.phone, r.po_count, fmtS(r.total_amount)]),
                  [t('reports.total'), '', purchasesData.reduce((a, r) => a + r.po_count, 0), fmtS(purchasesData.reduce((a, r) => a + r.total_amount, 0))],
                  t('common.print')
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
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
                onExcel={async () => {
                  if (!customerDebts) return;
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(customerDebts.items.map(c => ({
                    [t('sale.customer')]: c.customer_name, [t('common.phone')]: c.phone,
                    [t('reports.th.debt')]: c.debt_balance, [t('reports.th.limit')]: c.debt_limit, [t('reports.th.usagePct')]: c.usage_pct,
                  })));
                  const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.customerDebts'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `debitorlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!customerDebts) return;
                  printTable(t('reports.customerDebtsTitle'),
                    [t('sale.customer'), t('common.phone'), t('reports.th.debt'), t('reports.th.limit'), t('reports.th.usage')],
                    customerDebts.items.map(c => [c.customer_name, c.phone, fmtS(c.debt_balance), fmtS(c.debt_limit), pct(c.usage_pct)]),
                    [t('reports.total'), '', fmtS(customerDebts.total_debt), '', ''],
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
                          <td className="px-5 py-3.5 text-sm font-bold text-amber-600">{fmtRowDebt(c.debt_balance, c.debt_currency)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">{fmtS(c.debt_limit)}</td>
                          <td className="px-5 py-3.5">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 bg-slate-200 rounded-full h-1.5 min-w-16">
                                <div className={`h-1.5 rounded-full ${c.usage_pct >= 90 ? 'bg-red-500' : c.usage_pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                                  style={{ width: `${Math.min(c.usage_pct, 100)}%` }} />
                              </div>
                              <span className="text-xs font-bold text-slate-600">{pct(c.usage_pct)}</span>
                            </div>
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
                onExcel={async () => {
                  if (!supplierDebts) return;
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(supplierDebts.items.map(s => ({
                    [t('purchase.supplier')]: s.supplier_name, [t('common.phone')]: s.phone,
                    [t('reports.th.debt')]: s.debt_balance, [t('finance.paymentTerms')]: `${s.payment_terms} ${t('reports.daysUnit')}`,
                  })));
                  const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.supplierDebts'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `kreditorlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!supplierDebts) return;
                  printTable(t('reports.supplierDebtsTitle'),
                    [t('purchase.supplier'), t('common.phone'), t('reports.th.debt'), t('finance.paymentTerms')],
                    supplierDebts.items.map(s => [s.supplier_name, s.phone, fmtS(s.debt_balance), `${s.payment_terms} ${t('reports.daysUnit')}`]),
                    [t('reports.total'), '', fmtS(supplierDebts.total_debt), ''],
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
                          <td className="px-5 py-3.5 text-sm font-bold text-red-600">{fmtRowDebt(s.debt_balance, s.debt_currency)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.payment_terms} {t('reports.daysUnit')}</td>
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
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(abcData.map(r => ({
                    [t('reports.th.product')]: r.product_name, 'SKU': r.sku,
                    [t('reports.th.revenue')]: r.revenue, [t('reports.th.frequency')]: r.frequency, [t('reports.th.qty')]: r.qty,
                    'ABC': r.abc, 'XYZ': r.xyz, [t('reports.th.group')]: r.group,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'ABC-XYZ');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `abc_xyz_${today()}.xlsx`);
                }}
                onPdf={() => printTable(t('reports.abcXyzTitle'),
                  [t('reports.th.product'), t('reports.th.revenue'), t('reports.th.frequency'), 'ABC', 'XYZ', t('reports.th.group')],
                  abcData.map(r => [r.product_name, fmtS(r.revenue), r.frequency, r.abc, r.xyz, r.group]),
                  null,
                  t('common.print')
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
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
                        <td className="px-5 py-3.5 text-sm font-semibold text-emerald-600">{fmtS(r.revenue)}</td>
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
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  const ws = XLSX.utils.json_to_sheet(batchData.map(r => ({
                    [t('reports.th.product')]: r.product_name, Lot: r.lot_number,
                    [t('reports.th.cost')]: r.purchase_price, [t('reports.th.initialQty')]: r.initial_quantity,
                    [t('reports.th.remaining')]: r.remaining_quantity, [t('reports.th.sold')]: r.sold_qty,
                    [t('reports.th.revenue')]: r.revenue, [t('reports.th.profit')]: r.profit, [t('reports.th.marginPct')]: r.margin_pct,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, t('reports.tab.batches'));
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `partiyalar_${today()}.xlsx`);
                }}
                onPdf={() => printTable(t('reports.batchesFifoTitle'),
                  [t('reports.th.product'), 'Lot', t('reports.th.cost'), t('reports.th.remaining'), t('reports.th.sold'), t('reports.th.profit')],
                  batchData.map(r => [r.product_name, r.lot_number, fmtS(r.purchase_price), fmt(r.remaining_quantity), fmt(r.sold_qty), fmtS(r.profit)]),
                  null,
                  t('common.print')
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {!loading && batchData.length > 0 && (
              <div className="grid grid-cols-4 gap-4 px-6 py-4 border-b border-slate-100 bg-slate-50">
                {[
                  { label: t('reports.totalBatches'), val: `${batchData.length} ${t('common.item')}`, cls: 'text-blue-600' },
                  { label: t('reports.totalSold'), val: `${fmt(batchData.reduce((a, r) => a + r.sold_qty, 0))} ${t('reports.unitPiece')}`, cls: 'text-slate-700' },
                  { label: t('reports.totalRevenueLabel'), val: fmtS(batchData.reduce((a, r) => a + r.revenue, 0)), cls: 'text-emerald-600' },
                  { label: t('reports.totalProfitLabel'), val: fmtS(batchData.reduce((a, r) => a + r.profit, 0)), cls: 'text-emerald-700' },
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
                        <td className="px-5 py-3.5 text-sm font-semibold text-emerald-600">{fmtS(r.profit)}</td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2">
                            <div className="w-12 bg-slate-200 rounded-full h-1.5">
                              <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${Math.min(r.margin_pct, 100)}%` }} />
                            </div>
                            <span className="text-xs font-bold text-emerald-600">{pct(r.margin_pct)}</span>
                          </div>
                        </td>
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

