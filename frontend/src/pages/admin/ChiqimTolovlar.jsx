import React, { useState, useEffect } from 'react';
import api from '../../api/axios';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const today = () => new Date().toISOString().slice(0, 10);

const PAYMENT_TYPES = [
  { value: 'cash', label: 'Naqd' },
  { value: 'card', label: 'Plastik (UzCard/Humo)' },
  { value: 'bank_transfer', label: "Bank o'tkazmasi" },
  { value: 'click', label: 'Click' },
  { value: 'payme', label: 'Payme' },
  { value: 'uzum', label: 'Uzum' },
];

export default function ChiqimTolovlar() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(today());
  const [dateTo, setDateTo] = useState(today());

  // Edit modal state
  const [editItem, setEditItem] = useState(null);
  const [editForm, setEditForm] = useState({ amount: '', payment_type: '', description: '' });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState('');

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/finance/payments/expense?date_from=${dateFrom}&date_to=${dateTo}`);
      setData(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [dateFrom, dateTo]);

  const openEdit = (item) => {
    setEditItem(item);
    setEditForm({
      amount: item.amount,
      payment_type: item.payment_type || 'cash',
      description: item.description || '',
      wallet_id: item.wallet_id || null,
    });
    setEditError('');
  };

  const closeEdit = () => { setEditItem(null); setEditError(''); };

  const handleEditSave = async () => {
    if (!editItem) return;
    setEditLoading(true);
    setEditError('');
    try {
      await api.put(`/finance/transactions/${editItem.id}`, {
        amount: parseFloat(editForm.amount),
        payment_type: editForm.payment_type,
        description: editForm.description,
        wallet_id: editForm.wallet_id,
      });
      closeEdit();
      loadData();
    } catch (e) {
      setEditError(e.response?.data?.detail || e.message || "Xatolik yuz berdi");
    } finally {
      setEditLoading(false);
    }
  };

  const handleDelete = async (item) => {
    if (!window.confirm("Rostdan ham ushbu to'lovni o'chirasizmi?")) return;
    try {
      await api.delete(`/finance/transactions/${item.id}`);
      loadData();
    } catch (e) {
      alert("Xatolik: " + (e.response?.data?.detail || e.message));
    }
  };

  const exportExcel = () => {
    if (!data?.items) return;
    const ws = XLSX.utils.json_to_sheet(data.items.map((i, index) => ({
      '#': index + 1,
      'CONTRAGENT': i.contragent,
      'TURI': i.turi,
      "TO'LOV": i.amount,
      "TO'LOV TURI": i.payment_type,
      'MANBA': i.reference_type,
      'KASSA': i.wallet,
      "MA'LUMOT": i.description || '',
      'SANA': new Date(i.created_at).toLocaleString('uz-UZ')
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Chiqim to'lovlar");
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `chiqim_tolovlar_${today()}.xlsx`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">Chiqim to'lovlar</h1>
        <div className="flex items-center gap-3">
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <button onClick={exportExcel} className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-xl">
            Excelga Ko'chirish
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">CONTRAGENT</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">TURI</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">TO'LOV</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500" colSpan="6">TO'LOV TURLARI</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">CHIQIM MANBASI</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">KASSA</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">MA'LUMOT</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">SANA</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">AMALLAR</th>
              </tr>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th colSpan="4"></th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">NAQD</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">UZCARD/HUMO</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">BANK O'TKAZMASI</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">CLICK</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">PAYME</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">UZUM</th>
                <th colSpan="5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr><td colSpan="15" className="text-center py-8">Yuklanmoqda...</td></tr>
              ) : data?.items?.length > 0 ? (
                data.items.map((i, idx) => (
                  <tr key={i.id} className="hover:bg-slate-50 text-sm">
                    <td className="px-4 py-3 text-slate-500">{idx + 1}</td>
                    <td className="px-4 py-3 font-semibold text-indigo-600">{i.contragent}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-md text-xs font-medium ${i.turi === 'Xarajat' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'}`}>
                        {i.turi}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-bold text-red-500">{fmt(i.amount)}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['cash', 'naqd'].includes(i.payment_type) ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type) ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['bank', 'bank_transfer'].includes(i.payment_type) ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'click' ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'payme' ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'uzum' ? fmt(i.amount) : 0}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded-md text-xs bg-blue-50 text-blue-600 border border-blue-100">
                        {i.reference_type === 'supplier_payment' || i.reference_type === 'purchase_order' ? "Ta'minotchiga to'lov" : i.reference_type === 'expense' ? "Xarajat" : "Mijozga qaytaruv"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{i.wallet}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{i.description || '—'}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{new Date(i.created_at).toLocaleString('uz-UZ')}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => openEdit(i)}
                          className="px-2 py-1 text-xs font-semibold bg-indigo-50 text-indigo-600 hover:bg-indigo-100 rounded-lg transition-colors"
                        >
                          Tahrirlash
                        </button>
                        <button
                          onClick={() => handleDelete(i)}
                          className="px-2 py-1 text-xs font-semibold bg-red-50 text-red-500 hover:bg-red-100 rounded-lg transition-colors"
                        >
                          O'chirish
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan="15" className="text-center py-8 text-slate-500">Ma'lumot topilmadi</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary cards */}
      {data?.summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Umumiy to'lovlar summasi</h3>
            <div className="text-slate-600 text-sm mb-1">Naqd: <span className="font-bold text-slate-800">{fmt(data.summary.naqd)}</span></div>
            <div className="text-slate-600 text-sm mb-1">Plastik: <span className="font-bold text-slate-800">{fmt(data.summary.plastik)}</span></div>
            <div className="text-slate-600 text-sm mb-1">Bank: <span className="font-bold text-slate-800">{fmt(data.summary.bank)}</span></div>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-emerald-600">{fmt(data.summary.umumiy)}</span>
            </div>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Ta'minotchilarga to'lovlar</h3>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-indigo-600">{fmt(data.summary.taminotchi_tolov)}</span>
            </div>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Xarajatlar summasi</h3>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-blue-600">{fmt(data.summary.xarajat_summasi)}</span>
            </div>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Mijozga qaytaruv summasi</h3>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-amber-600">{fmt(data.summary.mijoz_qaytaruv)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-slate-800">To'lovni tahrirlash</h2>
              <button onClick={closeEdit} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
            </div>

            <div className="space-y-4">
              {/* Contragent info (read-only) */}
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-xs text-slate-500 mb-1">Kontragent</div>
                <div className="font-semibold text-slate-800">{editItem.contragent}</div>
              </div>

              {/* Amount */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Summa (so'm)</label>
                <input
                  type="number"
                  value={editForm.amount}
                  onChange={e => setEditForm(f => ({ ...f, amount: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Summa"
                />
              </div>

              {/* Payment type */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">To'lov turi</label>
                <select
                  value={editForm.payment_type}
                  onChange={e => setEditForm(f => ({ ...f, payment_type: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {PAYMENT_TYPES.map(pt => (
                    <option key={pt.value} value={pt.value}>{pt.label}</option>
                  ))}
                </select>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Ma'lumot / Izoh</label>
                <textarea
                  value={editForm.description}
                  onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                  rows={3}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                  placeholder="Izoh..."
                />
              </div>

              {editError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">
                  {editError}
                </div>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={closeEdit}
                className="flex-1 px-4 py-2.5 border border-slate-200 text-slate-600 text-sm font-semibold rounded-xl hover:bg-slate-50 transition-colors"
              >
                Bekor qilish
              </button>
              <button
                onClick={handleEditSave}
                disabled={editLoading}
                className="flex-1 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                {editLoading ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
