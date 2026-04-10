import { useState, useEffect, useCallback } from 'react';
import { useLang } from '../../context/LangContext';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtS = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const pct = (v) => `${Number(v || 0).toFixed(1)}%`;

// ─── Kunlik sanalar ────────────────────────────────────────────────────────────
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const firstOfMonth = () => {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
};

// ─── PDF chop etish (window.print orqali) ─────────────────────────────────────
function printTable(title, headers, rows, totalsRow = null) {
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
      <button onclick="window.print()" style="padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">{t('common.print')}</button>
    </div></body></html>`);
  win.document.close();
}

// ─── Umumiy Tab tugmasi ────────────────────────────────────────────────────────
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

// ─── Sana filtri komponenti ────────────────────────────────────────────────────
function DateFilter({ dateFrom, dateTo, setDateFrom, setDateTo, onSearch, loading }) {
  const { t } = useLang();
const presets = [
    { label: 'Bugun', from: today(), to: today() },
    { label: 'Bu hafta', from: daysAgo(6), to: today() },
    { label: 'Bu oy', from: firstOfMonth(), to: today() },
    { label: 'O\'tgan 30 kun', from: daysAgo(29), to: today() },
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
          <label className="block text-xs font-medium text-slate-500 mb-1">Dan</label>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">Gacha</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <button onClick={onSearch} disabled={loading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
          {loading ? 'Yuklanmoqda...' : 'Qidiruv'}
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

// ─── Spinner ───────────────────────────────────────────────────────────────────
const Spinner = () => (
  <div className="flex justify-center py-16">
    <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

// ─── Asosiy komponent ─────────────────────────────────────────────────────────
export default function Reports() {
  const { t } = useLang();
const [tab, setTab] = useState('sales');
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
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

  // Load branches on mount
  useEffect(() => {
    api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch(() => {});
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
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tab, dateFrom, dateTo, branchId]);

  useEffect(() => { load(); }, [tab]);

  const tabs = [
    { key: 'sales', label: 'Sotuvlar', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
    { key: 'profit', label: 'Foyda', icon: 'M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z' },
    { key: 'pl', label: 'Foyda/Zarar', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
    { key: 'cashier', label: 'Kassir', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' },
    { key: 'inventory', label: 'Ombor', icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
    { key: 'deadstock', label: "O'lik stok", icon: 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    { key: 'expenses', label: 'Xarajatlar', icon: 'M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z' },
    { key: 'purchases', label: 'Xaridlar', icon: 'M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z' },
    { key: 'customer-debts', label: 'Debitorlar', icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { key: 'supplier-debts', label: 'Kreditorlar', icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { key: 'abc', label: 'ABC/XYZ', icon: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' },
    { key: 'batches', label: 'Partiyalar (FIFO)', icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Hisobotlar</h1>
        <p className="text-slate-500 text-sm mt-0.5">Kengaytirilgan tahlil, eksport va 1C integratsiya</p>
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
            <option value="">🏢 Barcha filiallar</option>
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
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.discount_amount > 0 ? fmtS(s.discount_amount) : '—'}</td>
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

        {/* ── Foyda (mahsulot bo'yicha) ── */}
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

        {/* ── Foyda va Zarar (P&L) ── */}
        {tab === 'pl' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Foyda va Zarar hisoboti (P&L)</span>
              <ExportBtns
                onPdf={() => {
                  if (!plData) return;
                  printTable(`Foyda va Zarar — ${plData.period?.from} / ${plData.period?.to}`,
                    ['Ko\'rsatkich', 'Summa', 'Foiz'],
                    [
                      ['Yalpi daromad (sotuv)', fmtS(plData.gross_revenue), ''],
                      ['Vazvratlar (−)', fmtS(plData.returns), ''],
                      ['Net daromad', fmtS(plData.revenue), '100%'],
                      ['Tannarx/COGS (FIFO)', fmtS(plData.cogs), pct(plData.revenue > 0 ? plData.cogs / plData.revenue * 100 : 0)],
                      ['Brutto foyda', fmtS(plData.gross_profit), pct(plData.gross_margin_pct)],
                      ['Xarajatlar (−)', fmtS(plData.expenses?.total), ''],
                      ...(plData.expenses?.by_category || []).map(c => [`  • ${c.name}`, fmtS(c.total), '']),
                      ['Net foyda', fmtS(plData.net_profit), pct(plData.net_margin_pct)],
                    ]
                  );
                }}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : plData ? (
              <div className="p-6 max-w-2xl">
                <p className="text-sm text-slate-500 mb-5">Davr: <strong>{plData.period?.from}</strong> — <strong>{plData.period?.to}</strong></p>
                <div className="space-y-2">
                  {[
                    { label: 'Yalpi daromad (sotuv)', value: plData.gross_revenue, cls: 'text-slate-800', pctV: null, bg: '' },
                    { label: 'Vazvratlar (−)', value: -plData.returns, cls: 'text-orange-500', pctV: plData.revenue > 0 ? plData.returns / plData.gross_revenue * 100 : 0, bg: '' },
                    { label: 'Net daromad', value: plData.revenue, cls: 'font-semibold text-slate-800', pctV: 100, bg: 'bg-slate-50' },
                    { label: 'Tannarx/COGS (FIFO)', value: -plData.cogs, cls: 'text-red-500', pctV: plData.revenue > 0 ? plData.cogs / plData.revenue * 100 : 0, bg: '' },
                    { label: 'Brutto foyda', value: plData.gross_profit, cls: 'font-bold text-indigo-600', pctV: plData.gross_margin_pct, bg: 'bg-indigo-50' },
                    { label: 'Xarajatlar (−)', value: -plData.expenses?.total, cls: 'text-red-500', pctV: plData.revenue > 0 ? plData.expenses?.total / plData.revenue * 100 : 0, bg: '' },
                    { label: 'Net foyda', value: plData.net_profit, cls: `font-bold ${plData.net_profit >= 0 ? 'text-emerald-600' : 'text-red-600'}`, pctV: plData.net_margin_pct, bg: plData.net_profit >= 0 ? 'bg-emerald-50' : 'bg-red-50' },
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
                    <p className="text-sm font-semibold text-slate-600 mb-3">Xarajatlar kategoriya bo'yicha:</p>
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
              <span className="text-sm font-semibold text-slate-700">Kassir bo'yicha hisobot</span>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(cashierData.map(r => ({
                    'Kassir': r.cashier_name, 'Sotuvlar': r.sales_count,
                    'Jami summa': r.total_amount, 'O\'rt. chek': r.avg_check, 'Chegirma': r.total_discount,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Kassir');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `kassir_${today()}.xlsx`);
                }}
                onPdf={() => printTable('Kassir hisoboti',
                  ['Kassir', 'Sotuvlar', 'Jami summa', "O'rt. chek"],
                  cashierData.map(r => [r.cashier_name, r.sales_count, fmtS(r.total_amount), fmtS(r.avg_check)])
                )}
              />
            </div>
            {cashBalance && (
              <div className="grid grid-cols-3 gap-4 px-6 py-4 border-b border-slate-100 bg-linear-to-r from-slate-50 to-blue-50/30">
                <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm">
                  <div className="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">Jami Kirim</div>
                  <div className="text-2xl font-black text-emerald-600">{Number(cashBalance.total_income || 0).toLocaleString('ru-RU')} s</div>
                </div>
                <div className="bg-white rounded-xl p-4 border border-red-100 shadow-sm">
                  <div className="text-xs font-bold text-red-500 uppercase tracking-widest mb-1">Jami Chiqim</div>
                  <div className="text-2xl font-black text-red-500">{Number(cashBalance.total_expense || 0).toLocaleString('ru-RU')} s</div>
                </div>
                <div className={`rounded-xl p-4 border shadow-sm ${cashBalance.balance >= 0 ? 'bg-white border-blue-100' : 'bg-red-50 border-red-200'}`}>
                  <div className="text-xs font-bold text-blue-600 uppercase tracking-widest mb-1">Kassadagi Balans</div>
                  <div className={`text-2xl font-black ${cashBalance.balance >= 0 ? 'text-blue-700' : 'text-red-600'}`}>{Number(cashBalance.balance || 0).toLocaleString('ru-RU')} s</div>
                </div>
              </div>
            )}
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['#', 'Kassir', 'Sotuvlar soni', 'Jami summa', "O'rt. chek", 'Chegirma'].map(h => (
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
                        <td className="px-5 py-3.5 text-sm text-slate-600">{r.sales_count} ta</td>
                        <td className="px-5 py-3.5 text-sm font-bold text-emerald-600">{fmtS(r.total_amount)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtS(r.avg_check)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmtS(r.total_discount)}</td>
                      </tr>
                    ))}
                    {cashierData.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* ── Ombor ── */}
        {tab === 'inventory' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Ombor qoldiqlari</span>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(inventoryData.map(i => ({
                    'Mahsulot': i.product_name, 'SKU': i.sku, 'Qoldiq': i.quantity,
                    'Min. qoldiq': i.min_stock, 'Qiymat': i.value, 'Holat': i.is_low ? 'Kam' : 'Yetarli',
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Ombor');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `ombor_${today()}.xlsx`);
                }}
                onPdf={() => printTable('Ombor qoldiqlari',
                  ['Mahsulot', 'SKU', 'Qoldiq', 'Min. qoldiq', 'Qiymat', 'Holat'],
                  inventoryData.map(i => [i.product_name, i.sku, i.quantity, i.min_stock, fmtS(i.value), i.is_low ? '⚠ Kam' : 'Yetarli'])
                )}
              />
            </div>
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['Mahsulot', 'SKU', 'Qoldiq', 'Min. qoldiq', 'Qiymat', 'Holat'].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {inventoryData.map(i => (
                      <tr key={i.product_id} className={`hover:bg-slate-50 transition-colors ${i.is_low ? 'bg-rose-50/30' : ''}`}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{i.product_name}</td>
                        <td className="px-5 py-3.5 text-sm font-mono text-indigo-600">{i.sku}</td>
                        <td className="px-5 py-3.5">
                          <span className={`text-sm font-bold ${i.is_low ? 'text-red-500' : 'text-slate-800'}`}>{i.quantity}</span>
                        </td>
                        <td className="px-5 py-3.5 text-sm text-slate-400">{i.min_stock}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-700">{fmtS(i.value)}</td>
                        <td className="px-5 py-3.5">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                            i.is_low ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-700'
                          }`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            {i.is_low ? 'Kam' : 'Yetarli'}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {inventoryData.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>}
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
              <span className="text-sm font-semibold text-slate-700">O'lik stok (6+ oy sotilmagan)</span>
              <ExportBtns
                onExcel={() => {
                  if (!deadStockData) return;
                  const ws = XLSX.utils.json_to_sheet(deadStockData.items.map(i => ({
                    'Mahsulot': i.product_name, 'SKU': i.sku,
                    'Miqdor': i.quantity, 'Tannarx': i.cost_price, 'Qiymat': i.value,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, "O'lik stok");
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `olik_stok_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!deadStockData) return;
                  printTable("O'lik stok hisoboti",
                    ['Mahsulot', 'SKU', 'Miqdor', 'Tannarx', 'Qiymat'],
                    deadStockData.items.map(i => [i.product_name, i.sku, i.quantity, fmtS(i.cost_price), fmtS(i.value)]),
                    ['JAMI', '', '', '', fmtS(deadStockData.total_value)]
                  );
                }}
              />
            </div>
            {loading ? <Spinner /> : deadStockData ? (
              <>
                <div className="grid grid-cols-3 gap-4 p-6 border-b border-slate-100">
                  <div className="bg-rose-50 rounded-xl p-4">
                    <div className="text-xs font-semibold text-rose-500 mb-1">Jami mahsulot</div>
                    <div className="text-2xl font-bold text-rose-700">{deadStockData.total_items} ta</div>
                  </div>
                  <div className="bg-amber-50 rounded-xl p-4">
                    <div className="text-xs font-semibold text-amber-600 mb-1">Umumiy qiymat</div>
                    <div className="text-2xl font-bold text-amber-700">{fmtS(deadStockData.total_value)}</div>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-4">
                    <div className="text-xs font-semibold text-slate-500 mb-1">Muddat</div>
                    <div className="text-2xl font-bold text-slate-700">{deadStockData.months} oy</div>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {['Mahsulot', 'SKU', 'Miqdor', 'Tannarx', 'Qiymat'].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {deadStockData.items.map((i) => (
                        <tr key={i.product_id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{i.product_name}</td>
                          <td className="px-5 py-3.5 text-sm font-mono text-indigo-600">{i.sku}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-600">{i.quantity}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{fmtS(i.cost_price)}</td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-rose-600">{fmtS(i.value)}</td>
                        </tr>
                      ))}
                      {deadStockData.items.length === 0 && (
                        <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-emerald-600">O'lik stok yo'q!</td></tr>
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
              <span className="text-sm font-semibold text-slate-700">Xarajatlar hisoboti</span>
              <ExportBtns
                onExcel={() => {
                  if (!expenseData) return;
                  const ws = XLSX.utils.json_to_sheet(expenseData.items.map(e => ({
                    'Kategoriya': e.category, 'Summa': e.amount,
                    'Izoh': e.description, 'Sana': new Date(e.created_at).toLocaleDateString('uz-UZ'),
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Xarajatlar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `xarajatlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!expenseData) return;
                  printTable('Xarajatlar hisoboti',
                    ['Kategoriya', 'Summa', 'Izoh', 'Sana'],
                    expenseData.items.map(e => [e.category, fmtS(e.amount), e.description, new Date(e.created_at).toLocaleDateString('uz-UZ')]),
                    ['JAMI', fmtS(expenseData.total), '', '']
                  );
                }}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : expenseData ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-red-50">
                  <span className="text-sm text-slate-600">Jami xarajat: </span>
                  <strong className="text-red-600">{fmtS(expenseData.total)}</strong>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {['Kategoriya', 'Summa', 'Izoh', 'Sana'].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {expenseData.items.map((e, i) => (
                        <tr key={e.id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                          <td className="px-5 py-3.5"><span className="text-xs px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded-lg">{e.category}</span></td>
                          <td className="px-5 py-3.5 text-sm font-semibold text-red-500">{fmtS(e.amount)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{e.description || '—'}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-400">{new Date(e.created_at).toLocaleDateString('uz-UZ')}</td>
                        </tr>
                      ))}
                      {expenseData.items.length === 0 && <tr><td colSpan={4} className="px-6 py-12 text-center text-sm text-slate-400">Xarajat yo'q</td></tr>}
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
              <span className="text-sm font-semibold text-slate-700">Supplier bo'yicha xaridlar</span>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(purchasesData.map(r => ({
                    'Supplier': r.supplier_name, 'Telefon': r.phone,
                    'PO soni': r.po_count, 'Jami summa': r.total_amount,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Xaridlar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `xaridlar_${today()}.xlsx`);
                }}
                onPdf={() => printTable('Xaridlar hisoboti',
                  ['Supplier', 'Telefon', 'PO soni', 'Jami summa'],
                  purchasesData.map(r => [r.supplier_name, r.phone, r.po_count, fmtS(r.total_amount)]),
                  ['JAMI', '', purchasesData.reduce((a, r) => a + r.po_count, 0), fmtS(purchasesData.reduce((a, r) => a + r.total_amount, 0))]
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['Supplier', 'Telefon', 'PO soni', 'Jami summa'].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {purchasesData.map((r, i) => (
                      <tr key={r.supplier_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{r.supplier_name}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{r.phone || '—'}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-600">{r.po_count} ta</td>
                        <td className="px-5 py-3.5 text-sm font-bold text-indigo-600">{fmtS(r.total_amount)}</td>
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
              <span className="text-sm font-semibold text-slate-700">Debitor qarzdorlik — mijozlar</span>
              <ExportBtns
                onExcel={() => {
                  if (!customerDebts) return;
                  const ws = XLSX.utils.json_to_sheet(customerDebts.items.map(c => ({
                    'Mijoz': c.customer_name, 'Telefon': c.phone,
                    'Qarz': c.debt_balance, 'Limit': c.debt_limit, 'Foydalanish %': c.usage_pct,
                  })));
                  const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, 'Debitorlar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `debitorlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!customerDebts) return;
                  printTable('Debitor qarzdorlik',
                    ['Mijoz', 'Telefon', 'Qarz', 'Limit', 'Foydalanish'],
                    customerDebts.items.map(c => [c.customer_name, c.phone, fmtS(c.debt_balance), fmtS(c.debt_limit), pct(c.usage_pct)]),
                    ['JAMI', '', fmtS(customerDebts.total_debt), '', '']
                  );
                }}
              />
            </div>
            {loading ? <Spinner /> : customerDebts ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-amber-50">
                  <span className="text-sm text-slate-600">Jami debitor qarz: </span>
                  <strong className="text-amber-700">{fmtS(customerDebts.total_debt)}</strong>
                  <span className="ml-4 text-sm text-slate-500">({customerDebts.count} ta mijoz)</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {['Mijoz', 'Telefon', 'Qarz', 'Limit', 'Foydalanish'].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {customerDebts.items.map((c, i) => (
                        <tr key={c.customer_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                          <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{c.customer_name}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{c.phone || '—'}</td>
                          <td className="px-5 py-3.5 text-sm font-bold text-amber-600">{fmtS(c.debt_balance)}</td>
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
                      {customerDebts.items.length === 0 && <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-emerald-600">Debitor yo'q!</td></tr>}
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
              <span className="text-sm font-semibold text-slate-700">Kreditor qarzdorlik — supplierlar</span>
              <ExportBtns
                onExcel={() => {
                  if (!supplierDebts) return;
                  const ws = XLSX.utils.json_to_sheet(supplierDebts.items.map(s => ({
                    'Supplier': s.supplier_name, 'Telefon': s.phone,
                    'Qarz': s.debt_balance, 'To\'lov muddati': s.payment_terms + ' kun',
                  })));
                  const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, 'Kreditorlar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `kreditorlar_${today()}.xlsx`);
                }}
                onPdf={() => {
                  if (!supplierDebts) return;
                  printTable('Kreditor qarzdorlik',
                    ['Supplier', 'Telefon', 'Qarz', "To'lov muddati"],
                    supplierDebts.items.map(s => [s.supplier_name, s.phone, fmtS(s.debt_balance), s.payment_terms + ' kun']),
                    ['JAMI', '', fmtS(supplierDebts.total_debt), '']
                  );
                }}
              />
            </div>
            {loading ? <Spinner /> : supplierDebts ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-red-50">
                  <span className="text-sm text-slate-600">Jami kreditor qarz: </span>
                  <strong className="text-red-600">{fmtS(supplierDebts.total_debt)}</strong>
                  <span className="ml-4 text-sm text-slate-500">({supplierDebts.count} ta supplier)</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        {['Supplier', 'Telefon', 'Qarz', "To'lov muddati"].map(h => (
                          <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {supplierDebts.items.map((s, i) => (
                        <tr key={s.supplier_id} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                          <td className="px-5 py-3.5 text-sm font-semibold text-slate-800">{s.supplier_name}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.phone || '—'}</td>
                          <td className="px-5 py-3.5 text-sm font-bold text-red-600">{fmtS(s.debt_balance)}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{s.payment_terms} kun</td>
                        </tr>
                      ))}
                      {supplierDebts.items.length === 0 && <tr><td colSpan={4} className="px-6 py-12 text-center text-sm text-emerald-600">Kreditor yo'q!</td></tr>}
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
                <span className="text-sm font-semibold text-slate-700">ABC/XYZ tahlil</span>
                <p className="text-xs text-slate-400 mt-0.5">A=top 80% daromad, B=80-95%, C=qolgan • X=tez aylanuvchi, Y=o'rta, Z=sekin</p>
              </div>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(abcData.map(r => ({
                    'Mahsulot': r.product_name, 'SKU': r.sku,
                    'Daromad': r.revenue, 'Chastota': r.frequency, 'Miqdor': r.qty,
                    'ABC': r.abc, 'XYZ': r.xyz, 'Guruh': r.group,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'ABC-XYZ');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `abc_xyz_${today()}.xlsx`);
                }}
                onPdf={() => printTable('ABC/XYZ Tahlil',
                  ['Mahsulot', 'Daromad', 'Chastota', 'ABC', 'XYZ', 'Guruh'],
                  abcData.map(r => [r.product_name, fmtS(r.revenue), r.frequency, r.abc, r.xyz, r.group])
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {loading ? <Spinner /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['Mahsulot', 'Daromad', 'Chastota', 'Miqdor', 'ABC', 'XYZ', 'Guruh'].map(h => (
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
                            r.xyz === 'X' ? 'bg-indigo-100 text-indigo-700' : r.xyz === 'Y' ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-500'
                          }`}>{r.xyz}</span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`px-2 py-0.5 rounded-lg text-xs font-bold ${
                            r.group === 'AX' ? 'bg-emerald-100 text-emerald-700' :
                            r.group === 'AY' || r.group === 'BX' ? 'bg-indigo-100 text-indigo-700' :
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
                <span className="text-sm font-semibold text-slate-700">Partiyalar (FIFO) hisoboti</span>
                <p className="text-xs text-slate-400 mt-0.5">Har bir partiyaning kirim narxi, qoldig&apos;i va foydasi</p>
              </div>
              <ExportBtns
                onExcel={() => {
                  const ws = XLSX.utils.json_to_sheet(batchData.map(r => ({
                    Tovar: r.product_name, Lot: r.lot_number,
                    KirimNarxi: r.purchase_price, Boshlangich: r.initial_quantity,
                    Qoldiq: r.remaining_quantity, Sotildi: r.sold_qty,
                    Daromad: r.revenue, Foyda: r.profit, MarginPct: r.margin_pct,
                  })));
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Partiyalar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `partiyalar_${today()}.xlsx`);
                }}
                onPdf={() => printTable('Partiyalar FIFO',
                  ['Tovar', 'Lot', 'Kirim narxi', 'Qoldiq', 'Sotildi', 'Foyda'],
                  batchData.map(r => [r.product_name, r.lot_number, fmtS(r.purchase_price), fmt(r.remaining_quantity), fmt(r.sold_qty), fmtS(r.profit)])
                )}
              />
            </div>
            <DateFilter dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} onSearch={load} loading={loading} />
            {!loading && batchData.length > 0 && (
              <div className="grid grid-cols-4 gap-4 px-6 py-4 border-b border-slate-100 bg-slate-50">
                {[
                  { label: 'Jami partiyalar', val: batchData.length + ' ta', cls: 'text-indigo-600' },
                  { label: 'Jami sotildi', val: fmt(batchData.reduce((a, r) => a + r.sold_qty, 0)) + ' dona', cls: 'text-slate-700' },
                  { label: 'Jami daromad', val: fmtS(batchData.reduce((a, r) => a + r.revenue, 0)), cls: 'text-emerald-600' },
                  { label: 'Jami foyda', val: fmtS(batchData.reduce((a, r) => a + r.profit, 0)), cls: 'text-emerald-700' },
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
                      {['Tovar nomi', 'Lot', 'Kirim narxi', 'Kirim miqdori', 'Qoldiq', 'Sotildi', 'Daromad', 'Foyda', 'Margin'].map(h => (
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
                        <td className="px-5 py-3.5 text-sm font-bold text-indigo-700">{fmtS(r.purchase_price)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{fmt(r.initial_quantity)}</td>
                        <td className="px-5 py-3.5">
                          <span className={`text-sm font-bold ${r.remaining_quantity > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                            {fmt(r.remaining_quantity)}{r.remaining_quantity === 0 ? ' (tugadi)' : ''}
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
                      <tr><td colSpan={9} className="px-6 py-12 text-center text-sm text-slate-400">Ma&apos;lumot yo&apos;q</td></tr>
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

