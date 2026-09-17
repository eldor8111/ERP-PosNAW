import { useState, useEffect, useCallback, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';
import toast from 'react-hot-toast';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtS = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const pct = (v) => `${Number(v || 0).toFixed(1)}%`;
// Multi-currency dict formatter: {UZS: 1000, USD: 5} -> "1,000 so'm + 5 USD"
const fmtDebt = (v) => {
  if (!v) return "0 so'm";
  if (typeof v === 'object' && !Array.isArray(v)) {
    const parts = Object.entries(v).filter(([, amt]) => amt > 0)
      .map(([c, amt]) => `${Number(amt).toLocaleString('uz-UZ')} ${c === 'UZS' ? "so'm" : c}`);
    return parts.length ? parts.join(' + ') : "0 so'm";
  }
  return fmtS(v);
};
const fmtRowDebt = (balance, currency) => {
  const curr = currency || 'UZS';
  return `${Number(balance || 0).toLocaleString('uz-UZ')} ${curr === 'UZS' ? "so'm" : curr}`;
};

// в”Ђв”Ђв”Ђ Kunlik sanalar в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const firstOfMonth = () => {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
};

// в”Ђв”Ђв”Ђ PDF chop etish (window.print orqali) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function printTable(title, headers, rows, totalsRow = null) {
  const headerHtml = headers.map(h => `<th style="border:1px solid #ddd;padding:8px;background:#f3f4f6;font-size:12px">${h}</th>`).join('');
  const rowsHtml = rows.map((row, i) =>
    `<tr style="background:${i % 2 ? '#f9fafb' : '#fff'}">${row.map(cell =>
      `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${cell ?? 'вЂ”'}</td>`
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
      <button onclick="window.print()" style="padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">{t('common.print')}</button>
    </div></body></html>`);
  win.document.close();
}

// в”Ђв”Ђв”Ђ Umumiy Tab tugmasi в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function TabBtn({ label, icon, active, onClick }) {
  const { t } = useLang();
return (
    <button onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap ${
        active ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'
      }`}>
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={icon} />
      </svg>
      {label}
    </button>
  );
}

// в”Ђв”Ђв”Ђ Sana filtri komponenti в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
                ? 'bg-indigo-100 text-indigo-700'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}>{p.label}</button>
        ))}
      </div>
      <div className="flex items-end gap-2 ml-auto flex-wrap">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.date.from')}</label>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">{t('reports.date.to')}</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <button onClick={onSearch} disabled={loading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
          {loading ? t('reports.loading') : t('reports.search')}
        </button>
      </div>
    </div>
  );
}

// в”Ђв”Ђв”Ђ Excel va PDF tugmalari в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
          Excel
        </button>
      )}
      {onPdf && (
        <button onClick={onPdf}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          PDF
        </button>
      )}
      {on1c && (
        <button onClick={on1c}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          1C Eksport
        </button>
      )}
    </div>
  );
}

// в”Ђв”Ђв”Ђ Spinner в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
const Spinner = () => (
  <div className="flex justify-center py-16">
    <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

// в”Ђв”Ђв”Ђ Asosiy komponent в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
  const [salesData, setSalesData] = useState([]);
  const [inventoryData, setInventoryData] = useState([]);
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
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
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
        const r = await api.get(`/reports/sales${qs()}`);
        setSalesData(r.data);
      } else if (tab === 'inventory') {
        const r = await api.get('/reports/inventory');
        setInventoryData(r.data);
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
    { key: 'inventory', label: t('reports.tab.inventory'), icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
    { key: 'deadstock', label: t('reports.tab.deadstock'), icon: 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    { key: 'expenses', label: t('reports.tab.expenses'), icon: 'M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z' },
    { key: 'purchases', label: t('reports.tab.purchases'), icon: 'M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z' },
    { key: 'customer-debts', label: t('reports.tab.customerDebts'), icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { key: 'supplier-debts', label: t('reports.tab.supplierDebts'), icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { key: 'abc', label: t('reports.tab.abc'), icon: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' },
    { key: 'batches', label: t('reports.tab.batches'), icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
    { key: 'product-sales', label: 'Mahsulotlar (Sotuv)', icon: 'M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z' },
    { key: 'movements', label: 'рџ“¦ Mahsulot harakatlari', icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
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
          <span className="text-sm font-semibold text-slate-500">Filial:</span>
          <select
            value={branchId}
            onChange={e => { setBranchId(e.target.value); }}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          >
            <option value="">рџЏў Barcha filiallar</option>
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

        {/* в”Ђв”Ђ Sotuvlar в”Ђв”Ђ */}
        {tab === 'sales' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Sotuvlar ro'yxati</span>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(salesData.map(s => ({
                    'Raqam': s.number, 'Kassir': s.cashier_name,
                    'Summa': s.total_amount, 'Chegirma': s.discount_amount,
                    "To'lov": s.payment_type, 'Sana': new Date(s.created_at).toLocaleString('uz-UZ'),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Sotuvlar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `sotuvlar_${today()}.xlsx`);
                }}
                onPdf={() => printTable('Sotuvlar hisoboti',
                  ['Raqam', 'Kassir', 'Summa', "To'lov", 'Sana'],
                  salesData.map(s => [s.number, s.cashier_name, fmtS(s.total_amount), s.payment_type, new Date(s.created_at).toLocaleDateString('uz-UZ')]),
                  ['', 'JAMI', fmtS(salesData.reduce((a, s) => a + s.total_amount, 0)), '', '']
                )}
                on1c={async () => {
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
                        {['Raqam', 'Kassir', 'Summa', 'Chegirma', "To'lov", 'Sana'].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {salesData.map(s => (
                        <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-5 py-3.5 text-sm font-mono font-semibold text-indigo-600">{s.number}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-700">{s.cashier_name}</td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{fmtS(s.total_amount)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.discount_amount > 0 ? fmtS(s.discount_amount) : 'вЂ”'}</td>
                          <td className="px-5 py-3.5">
                            <span className="inline-flex px-2 py-0.5 bg-blue-50 text-blue-600 text-xs font-medium rounded-lg">{s.payment_type}</span>
                          </td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">{new Date(s.created_at).toLocaleString('uz-UZ')}</td>
                        </tr>
                      ))}
                      {salesData.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                    </tbody>
                  </table>
                </div>
                {salesData.length > 0 && (
                  <div className="px-6 py-3 border-t border-slate-100 flex justify-between text-sm text-slate-500 bg-slate-50">
                    <span>Jami <strong className="text-slate-700">{salesData.length}</strong> ta sotuv</span>
                    <span>Umumiy: <strong className="text-emerald-600">{fmtS(salesData.reduce((a, s) => a + s.total_amount, 0))}</strong></span>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* в”Ђв”Ђ Foyda (mahsulot bo'yicha) в”Ђв”Ђ */}
        {tab === 'profit' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Mahsulot bo'yicha foyda hisoboti</span>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(profitData.map(r => ({
                    'Mahsulot': r.product_name, 'SKU': r.sku, 'Kategoriya': r.category_name,
                    'Sotildi': r.qty_sold, 'Daromad': r.revenue, 'Tannarx': r.cost,
                    'Foyda': r.profit, 'Margin %': r.margin_pct,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Foyda');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `foyda_${today()}.xlsx`);
                }}
                onPdf={() => printTable('Mahsulot bo\'yicha foyda',
                  ['Mahsulot', 'Kategoriya', 'Sotildi', 'Daromad', 'Tannarx', 'Foyda', 'Margin'],
                  profitData.map(r => [r.product_name, r.category_name, fmt(r.qty_sold), fmtS(r.revenue), fmtS(r.cost), fmtS(r.profit), pct(r.margin_pct)]),
                  ['JAMI', '', '', fmtS(profitData.reduce((a, r) => a + r.revenue, 0)), fmtS(profitData.reduce((a, r) => a + r.cost, 0)), fmtS(profitData.reduce((a, r) => a + r.profit, 0)), '']
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['Mahsulot', 'Kategoriya', 'Sotildi', 'Daromad', 'Tannarx', 'Foyda', 'Margin'].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {profitData.map((r, i) => (
                      <tr key={r.product_id} className={i % 2 ? 'bg-slate-50/50 hover:bg-slate-100 transition-colors' : 'bg-white hover:bg-slate-50 transition-colors'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.product_name}</td>
                        <td className="px-5 py-3.5"><span className="text-xs px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded-lg">{r.category_name}</span></td>
                        <td className="px-5 py-3.5 text-sm text-slate-600">{fmt(r.qty_sold)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{fmtS(r.revenue)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtS(r.cost)}</td>
                        <td className="px-5 py-3.5 text-sm font-semibold text-emerald-600">{fmtS(r.profit)}</td>
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
                      <tr className="bg-indigo-50 font-bold">
                        <td className="px-5 py-3 text-sm text-slate-700">{t('admin.dict.th_total') || 'JAMI'}</td>
                        <td />
                        <td className="px-5 py-3 text-sm">{fmt(profitData.reduce((a, r) => a + r.qty_sold, 0))}</td>
                        <td className="px-5 py-3 text-sm">{fmtS(profitData.reduce((a, r) => a + r.revenue, 0))}</td>
                        <td className="px-5 py-3 text-sm">{fmtS(profitData.reduce((a, r) => a + r.cost, 0))}</td>
                        <td className="px-5 py-3 text-sm text-emerald-600">{fmtS(profitData.reduce((a, r) => a + r.profit, 0))}</td>
                        <td />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            )}
          </>
        )}

        {/* в”Ђв”Ђ Mahsulotlar (Sotuv) в”Ђв”Ђ */}
        {tab === 'product-sales' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Mahsulotlar (Sotuv) hisoboti</span>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(productSalesData.map(r => ({
