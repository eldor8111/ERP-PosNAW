import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';

const fmtDate = (s) => s ? new Date(s).toLocaleString('ru-RU', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' }).replace(',','') : '—';
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);
const fmtS = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";

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
      <button onclick="window.print()" style="padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">Chop etish</button>
    </div></body></html>`);
  win.document.close();
}

function ExportBtns({ onExcel, onPdf }) {
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
    </div>
  );
}

const Spinner = () => (
  <div className="flex justify-center py-16">
    <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

function TabBtn({ label, icon, active, onClick }) {
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

export default function Warehouse() {
  const { t } = useLang();
  const [tab, setTab] = useState('inventory');
  
  const [warehouses, setWarehouses] = useState([]);
  const [branches, setBranches]     = useState([]);
  const [loading, setLoading]       = useState(true);
  
  // Create/Edit state for warehouses
  const [modal, setModal]           = useState(null);
  const [name, setName]             = useState('');
  const [branchId, setBranchId]     = useState('');
  const [saving, setSaving]         = useState(false);
  const [err, setErr]               = useState('');
  const [delConfirm, setDelConfirm] = useState(null);

  // Inventory state
  const [inventoryData, setInventoryData] = useState([]);

  const load = async () => {
    setLoading(true);
    try {
      if (tab === 'warehouses') {
        const { data } = await api.get('/warehouses'); 
        setWarehouses(data); 
      } else if (tab === 'inventory') {
        const r = await api.get('/reports/inventory');
        setInventoryData(r.data);
      }
    }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    if (branches.length === 0) {
      api.get('/branches').then(r => setBranches(r.data)).catch(() => {});
    }
  }, [tab]);

  const openCreate = () => { setName(''); setBranchId(''); setErr(''); setModal({ mode:'create' }); };
  const openEdit   = (wh) => { setName(wh.name); setBranchId(wh.branch_id ?? ''); setErr(''); setModal({ mode:'edit', wh }); };
  const closeModal = () => { setModal(null); setErr(''); };

  const remove = async () => {
    try {
      await api.delete(`/warehouses/${delConfirm.id}`);
      setDelConfirm(null);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik yuz berdi');
    }
  };

  const save = async () => {
    if (!name.trim()) { setErr("Nomi bo'sh bo'lmasin"); return; }
    setSaving(true); setErr('');
    try {
      const payload = { name: name.trim(), branch_id: branchId ? Number(branchId) : null };
      if (modal.mode === 'create') {
        await api.post('/warehouses', payload);
      } else {
        await api.patch(`/warehouses/${modal.wh.id}`, payload);
      }
      closeModal();
      load();
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-slate-700">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
          </svg>
          <span className="text-base font-semibold">Ombor</span>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-3">
        <div className="flex flex-wrap gap-1">
          <TabBtn 
            label="Ombor qoldiqlari" 
            icon="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" 
            active={tab === 'inventory'} 
            onClick={() => setTab('inventory')} 
          />
          <TabBtn 
            label="Omborlar ro'yxati" 
            icon="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" 
            active={tab === 'warehouses'} 
            onClick={() => setTab('warehouses')} 
          />
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        {tab === 'inventory' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Ombor qoldiqlari hisoboti</span>
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
                    {inventoryData.length === 0 && <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">Hech qanday ma'lumot yo'q</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {tab === 'warehouses' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">Omborlar ro'yxati</span>
              <button
                onClick={openCreate}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Yangi ombor qo'shish
              </button>
            </div>
            {loading ? <Spinner /> : (
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase w-12">#</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Nomi</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Filial</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Sana</th>
                    <th className="px-4 py-3 w-24" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {warehouses.map((wh, i) => (
                    <tr key={wh.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 text-sm text-slate-500">{i + 1}</td>
                      <td className="px-4 py-3 text-sm text-slate-800 font-medium">{wh.name}</td>
                      <td className="px-4 py-3 text-sm text-slate-500">
                        {wh.branch_id ? (branches.find(b => b.id === wh.branch_id)?.name || '—') : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500">{fmtDate(wh.created_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => openEdit(wh)}
                            className="p-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                            title="Tahrirlash"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M15.232 5.232l3.536 3.536M9 13l6.5-6.5a2 2 0 012.828 0l.172.172a2 2 0 010 2.828L12 16H9v-3z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => setDelConfirm(wh)}
                            className="p-1.5 bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                            title="O'chirish"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {warehouses.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center text-sm text-slate-400">
                        Ma'lumot topilmadi
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      {/* Delete confirm */}
      {delConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-5">
              <h3 className="text-base font-semibold text-slate-800 mb-2">O'chirishni tasdiqlash</h3>
              <p className="text-sm text-slate-500">
                <span className="font-medium text-slate-700">"{delConfirm.name}"</span> omborini o'chirishni xohlaysizmi?
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={() => setDelConfirm(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                Bekor qilish
              </button>
              <button
                onClick={remove}
                className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                O'chirish
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h3 className="text-base font-semibold text-slate-800">
                {modal.mode === 'create' ? "Yangi ombor qo'shish" : "Tahrirlash"}
              </h3>
              <button onClick={closeModal} className="text-slate-400 hover:text-slate-600 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="px-6 py-5">
              <input
                autoFocus
                placeholder="Nomi"
                value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && save()}
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {branches.length > 0 && (
                <div className="mt-3">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Filial (ixtiyoriy)</label>
                  <select
                    value={branchId}
                    onChange={e => setBranchId(e.target.value)}
                    className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">— Filialsiz —</option>
                    {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              )}
              {err && <p className="mt-2 text-sm text-red-500">{err}</p>}
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                Bekor qilish
              </button>
              <button
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
                {saving ? "Saqlanmoqda..." : "Saqlash"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
