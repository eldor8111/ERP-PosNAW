import React, { useState, useEffect } from 'react';
import api from '../../api/axios';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const today = () => new Date().toISOString().slice(0, 10);
const firstOfMonth = () => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); };

export default function KirimTolovlar() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(today());
  const [dateTo, setDateTo] = useState(today());

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/finance/payments/income?date_from=${dateFrom}&date_to=${dateTo}`);
      setData(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [dateFrom, dateTo]);

  const exportExcel = () => {
    if (!data?.items) return;
    const ws = XLSX.utils.json_to_sheet(data.items.map((i, index) => ({
      '#': index + 1,
      'CONTRAGENT': i.contragent,
      'TURI': i.turi,
      'TO\'LOV': i.amount,
      'TO\'LOV TURI': i.payment_type,
      'MANBA': i.reference_type,
      'KASSA': i.wallet,
      'MA\'LUMOT': i.description || '',
      'SANA': new Date(i.created_at).toLocaleString('uz-UZ')
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Kirim to\'lovlar');
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `kirim_tolovlar_${today()}.xlsx`);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">Kirim to'lovlar</h1>
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
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">KIRIM MANBASI</th>
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
                <th colSpan="4"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr><td colSpan="14" className="text-center py-8">Yuklanmoqda...</td></tr>
              ) : data?.items?.length > 0 ? (
                data.items.map((i, idx) => (
                  <tr key={i.id} className="hover:bg-slate-50 text-sm">
                    <td className="px-4 py-3 text-slate-500">{idx + 1}</td>
                    <td className="px-4 py-3 font-semibold text-indigo-600">{i.contragent}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-md text-xs font-medium ${i.turi === 'Mijoz' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                        {i.turi}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-bold text-emerald-600">{fmt(i.amount)}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['cash', 'naqd'].includes(i.payment_type) ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type) ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['bank', 'bank_transfer'].includes(i.payment_type) ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'click' ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'payme' ? fmt(i.amount) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'uzum' ? fmt(i.amount) : 0}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded-md text-xs bg-blue-50 text-blue-600 border border-blue-100">
                        {i.reference_type === 'customer_payment' ? "Qarz yopish" : i.reference_type === 'sale' ? "Sotuv" : "Ta'minotchidan qaytaruv"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{i.wallet}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{i.description || '—'}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{new Date(i.created_at).toLocaleString('uz-UZ')}</td>
                    <td className="px-4 py-3">
                      <button 
                        onClick={async () => {
                          if(window.confirm("Rostdan ham ushbu to'lovni o'chirasizmi?")) {
                            try {
                              await api.delete(`/finance/transactions/${i.id}`);
                              loadData();
                            } catch(e) {
                              alert("Xatolik: " + (e.response?.data?.detail || e.message));
                            }
                          }
                        }}
                        className="text-red-500 hover:text-red-700 text-xs font-medium"
                      >
                        O'chirish
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan="14" className="text-center py-8 text-slate-500">Ma'lumot topilmadi</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

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
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Mijozdan to'lovlar summasi (Qarz)</h3>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-indigo-600">{fmt(data.summary.mijoz_qarz_yopish)}</span>
            </div>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Sotuv to'lovlari summasi</h3>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-blue-600">{fmt(data.summary.sotuv_summasi)}</span>
            </div>
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">Ta'minotchidan qaytaruv summasi</h3>
            <div className="text-slate-600 text-sm mt-3 pt-3 border-t border-slate-100">
              Umumiy summa: <span className="font-bold text-lg text-amber-600">{fmt(data.summary.taminotchi_qaytaruv)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
