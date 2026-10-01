import React, { useState, useEffect, useMemo } from 'react';
import api from '../../api/axios';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';
import { useLang } from '../../context/LangContext';
import { matchesSearch } from '../../utils/translit';
import toast from 'react-hot-toast';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";
const fmtCurr = (v, curr) => {
  const n = Number(v || 0);
  if (!curr || curr === 'UZS') return n.toLocaleString('uz-UZ') + " so'm";
  if (curr === 'USD') return '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return n.toLocaleString('uz-UZ') + ' ' + curr;
};
const fmtNum = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 2 });
const positiveDebts = (s) => {
  if (s?.debt_balances && typeof s.debt_balances === 'object' && Object.keys(s.debt_balances).length > 0) {
    return Object.entries(s.debt_balances).filter(([, v]) => Number(v) > 0);
  }
  return Number(s?.debt_balance) > 0 ? [['UZS', s.debt_balance]] : [];
};
const newPayRow = (currency = 'UZS', amount = '') => ({ id: Date.now() + Math.random(), payType: 'cash', payAmount: amount, currency });
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);

export default function ChiqimTolovlar() {
  const { t } = useLang();
  const PAYMENT_TYPES = [
    { value: 'cash', label: t('chiqimTolov.paymentCash') },
    { value: 'card', label: t('chiqimTolov.paymentCard') },
    { value: 'bank_transfer', label: t('chiqimTolov.paymentBankTransfer') },
    { value: 'click', label: t('chiqimTolov.paymentClick') },
    { value: 'payme', label: t('chiqimTolov.paymentPayme') },
    { value: 'uzum', label: t('chiqimTolov.paymentUzum') },
  ];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState(today());
  const [dateTo, setDateTo] = useState(today());

  // Edit modal state
  const [editItem, setEditItem] = useState(null);
  const [editForm, setEditForm] = useState({ amount: '', payment_type: '', description: '' });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState('');

  // Yangi chiqim to'lov (ta'minotchi qarzini to'lash) modali
  const [payOpen, setPayOpen] = useState(false);
  const [suppliers, setSuppliers] = useState([]);
  const [wallets, setWallets] = useState([]);
  const [currencies, setCurrencies] = useState([{ code: 'UZS', rate: 1 }]);
  const [supSearch, setSupSearch] = useState('');
  const [onlyDebtors, setOnlyDebtors] = useState(true);
  const [paySupplier, setPaySupplier] = useState(null);
  const [payWallet, setPayWallet] = useState('');
  const [payRows, setPayRows] = useState([newPayRow()]);
  const [payNote, setPayNote] = useState('');
  const [paySaving, setPaySaving] = useState(false);
  const [payError, setPayError] = useState('');

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

  const summaryData = useMemo(() => {
    if (!data?.items) return {};
    const res = {};
    data.items.forEach(i => {
      const cur = i.currency_code || 'UZS';
      if (!res[cur]) res[cur] = { naqd: 0, plastik: 0, bank: 0, umumiy: 0, taminotchi: 0, xarajat: 0, qaytaruv: 0 };
      
      const amt = Number(i.amount) || 0;
      res[cur].umumiy += amt;
      
      if (['cash', 'naqd'].includes(i.payment_type)) res[cur].naqd += amt;
      else if (['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type)) res[cur].plastik += amt;
      else if (['bank', 'bank_transfer'].includes(i.payment_type)) res[cur].bank += amt;

      if (i.reference_type === 'supplier_payment' || i.reference_type === 'purchase_order' || i.reference_type === 'kirim') {
        res[cur].taminotchi += amt;
      } else if (i.reference_type === 'expense') {
        res[cur].xarajat += amt;
      } else if (i.reference_type === 'sale_refund') {
        res[cur].qaytaruv += amt;
      }
    });
    return res;
  }, [data?.items]);

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
      setEditError(e.response?.data?.detail || e.message || t('auth.errGeneral'));
    } finally {
      setEditLoading(false);
    }
  };

  const handleDelete = async (item) => {
    if (!window.confirm(t('chiqimTolov.deleteConfirm'))) return;
    try {
      await api.delete(`/finance/transactions/${item.id}`);
      loadData();
    } catch (e) {
      alert(t('chiqimTolov.errorPrefix') + (e.response?.data?.detail || e.message));
    }
  };

  const openPay = async () => {
    setPayOpen(true);
    setPaySupplier(null);
    setSupSearch('');
    setOnlyDebtors(true);
    setPayRows([newPayRow()]);
    setPayNote('');
    setPayError('');
    const [sRes, wRes, cRes] = await Promise.all([
      api.get('/suppliers', { params: { limit: 5000 } }).catch(() => ({ data: [] })),
      api.get('/finance/wallets').catch(() => ({ data: [] })),
      api.get('/currencies/active').catch(() => ({ data: [] })),
    ]);
    setSuppliers(Array.isArray(sRes.data) ? sRes.data : []);
    const ws = Array.isArray(wRes.data) ? wRes.data : [];
    setWallets(ws);
    setPayWallet(ws.length > 0 ? String(ws[0].id) : '');
    const cs = Array.isArray(cRes.data) ? [...cRes.data] : [];
    if (!cs.find(c => c.code === 'UZS')) cs.unshift({ code: 'UZS', rate: 1 });
    setCurrencies(cs);
  };

  const closePay = () => { if (!paySaving) setPayOpen(false); };

  const pickSupplier = (s) => {
    setPaySupplier(s);
    const first = positiveDebts(s)[0];
    setPayRows([newPayRow(first?.[0] || 'UZS', first ? String(first[1]) : '')]);
    setPayError('');
  };

  const updatePayRow = (idx, field, value) =>
    setPayRows(prev => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));

  const debtFor = (cur) => Number((positiveDebts(paySupplier).find(([c]) => c === cur) || [])[1] || 0);

  const handlePaySave = async () => {
    if (!paySupplier) { setPayError(t('chiqimTolov.selectSupplierFirst')); return; }
    const valid = payRows.filter(r => Number(r.payAmount) > 0 && r.payType);
    if (valid.length === 0) { setPayError(t('chiqimTolov.enterAmount')); return; }
    setPaySaving(true);
    setPayError('');
    let done = 0;
    try {
      for (const row of valid) {
        await api.post(`/suppliers/${paySupplier.id}/pay-debt`, {
          amount: Number(row.payAmount),
          currency: row.currency || 'UZS',
          payment_type: row.payType,
          reason: payNote.trim() || t('chiqimTolov.defaultReason'),
          wallet_id: payWallet ? Number(payWallet) : null,
        });
        done += 1;
      }
      toast.success(t('chiqimTolov.paymentSaved'));
      setPayOpen(false);
      loadData();
    } catch (e) {
      // Bir nechta qatordan bir qismi saqlangan bo'lsa — saqlanganlarini ro'yxatdan olib tashlaymiz,
      // aks holda qayta bosilganda ular ikki marta yoziladi.
      if (done > 0) {
        const savedIds = new Set(valid.slice(0, done).map(r => r.id));
        setPayRows(prev => prev.filter(r => !savedIds.has(r.id)));
        loadData();
      }
      setPayError(e.response?.data?.detail || e.message || t('auth.errGeneral'));
    } finally {
      setPaySaving(false);
    }
  };

  const filteredSuppliers = useMemo(() => {
    let list = suppliers;
    if (onlyDebtors) list = list.filter(s => positiveDebts(s).length > 0);
    if (supSearch.trim()) list = list.filter(s => matchesSearch(`${s.name || ''} ${s.phone || ''}`, supSearch));
    return list;
  }, [suppliers, onlyDebtors, supSearch]);

  const exportExcel = async () => {
    if (!data?.items) return;
    const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
    const ws = XLSX.utils.json_to_sheet(data.items.map((i, index) => ({
      '#': index + 1,
      [t('chiqimTolov.colContragent')]: i.contragent,
      [t('chiqimTolov.colType')]: i.turi,
      [t('chiqimTolov.colPayment')]: i.amount,
      [t('chiqimTolov.colPaymentType')]: i.payment_type,
      [t('chiqimTolov.colSourceShort')]: i.reference_type,
      [t('chiqimTolov.colWallet')]: i.wallet,
      [t('chiqimTolov.colInfo')]: i.description || '',
      [t('chiqimTolov.colDate')]: new Date(i.created_at).toLocaleString('uz-UZ')
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, t('chiqimTolov.title'));
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `chiqim_tolovlar_${today()}.xlsx`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">{t('chiqimTolov.title')}</h1>
        <div className="flex items-center gap-3">
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <button onClick={exportExcel} className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-xl">
            {t('chiqimTolov.exportExcel')}
          </button>
          <button onClick={openPay} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" /></svg>
            {t('chiqimTolov.newPayment')}
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">#</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colContragent')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colType')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colPayment')}</th>
                <th className="px-2 py-2 text-center text-[11px] font-semibold text-slate-500" colSpan="6">{t('chiqimTolov.colPaymentTypes')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colSource')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colWallet')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colInfo')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('chiqimTolov.colDate')}</th>
                <th className="px-2 py-2 text-left text-[11px] font-semibold text-slate-500">{t('common.actions')}</th>
              </tr>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th colSpan="4"></th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('chiqimTolov.colCash')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('chiqimTolov.colCard')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('chiqimTolov.colBankTransfer')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('chiqimTolov.colClick')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('chiqimTolov.colPayme')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('chiqimTolov.colUzum')}</th>
                <th colSpan="5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr><td colSpan="15" className="text-center py-8">{t('common.loading')}</td></tr>
              ) : data?.items?.length > 0 ? (
                data.items.map((i, idx) => (
                  <tr key={i.id} className="hover:bg-slate-50 text-xs">
                    <td className="px-2 py-2 text-slate-500">{idx + 1}</td>
                    <td className="px-2 py-2 font-semibold text-blue-600">{i.contragent}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <span className={`px-2 py-1 rounded-md font-medium ${i.turi === 'Xarajat' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'}`}>
                        {i.turi}
                      </span>
                    </td>
                    <td className="px-2 py-2 font-bold text-red-500 whitespace-nowrap">{fmtCurr(i.amount, i.currency_code)}</td>
                    <td className="px-2 py-2 text-center border-x border-slate-50 whitespace-nowrap">{['cash', 'naqd'].includes(i.payment_type) ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-2 text-center border-x border-slate-50 whitespace-nowrap">{['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type) ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-2 text-center border-x border-slate-50 whitespace-nowrap">{['bank', 'bank_transfer'].includes(i.payment_type) ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-2 text-center border-x border-slate-50 whitespace-nowrap">{i.payment_type === 'click' ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-2 text-center border-x border-slate-50 whitespace-nowrap">{i.payment_type === 'payme' ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-2 text-center border-x border-slate-50 whitespace-nowrap">{i.payment_type === 'uzum' ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <span className="px-1.5 py-0.5 rounded-md bg-blue-50 text-blue-600 border border-blue-100">
                        {i.reference_type === 'supplier_payment' || i.reference_type === 'purchase_order' ? t('chiqimTolov.sourceSupplier') : i.reference_type === 'expense' ? t('chiqimTolov.sourceExpense') : t('chiqimTolov.sourceCustomerReturn')}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-slate-600 whitespace-nowrap">{i.wallet}</td>
                    <td className="px-2 py-2 text-slate-500 max-w-[120px] truncate" title={i.description || ''}>{i.description || '—'}</td>
                    <td className="px-2 py-2 text-slate-500 whitespace-nowrap">{new Date(i.created_at).toLocaleString('uz-UZ')}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <div className="flex gap-1.5">
                        {i.reference_type !== 'purchase_order' ? (
                          <>
                            <button
                              onClick={() => openEdit(i)}
                              className="px-2 py-1 font-semibold bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg transition-colors"
                            >
                              {t('common.edit')}
                            </button>
                            <button
                              onClick={() => handleDelete(i)}
                              className="px-2 py-1 font-semibold bg-red-50 text-red-500 hover:bg-red-100 rounded-lg transition-colors"
                            >
                              {t('common.delete')}
                            </button>
                          </>
                        ) : (
                          <span className="text-[10px] text-red-400 italic bg-red-50 px-1 py-0.5 rounded">{t('chiqimTolov.editFromPurchases')}</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan="15" className="text-center py-8 text-slate-500">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary cards */}
      {data?.items && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('chiqimTolov.totalPaymentsSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => (
              <div key={cur} className="mb-3 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-slate-600 text-sm flex justify-between mb-1"><span>{t('chiqimTolov.cashColon')}</span> <span className="font-bold text-slate-800">{fmtCurr(sums.naqd, cur)}</span></div>
                <div className="text-slate-600 text-sm flex justify-between mb-1"><span>{t('chiqimTolov.cardColon')}</span> <span className="font-bold text-slate-800">{fmtCurr(sums.plastik, cur)}</span></div>
                <div className="text-slate-600 text-sm flex justify-between mb-2"><span>{t('chiqimTolov.bankColon')}</span> <span className="font-bold text-slate-800">{fmtCurr(sums.bank, cur)}</span></div>
                <div className="text-sm flex justify-between font-bold text-emerald-600"><span>{t('chiqimTolov.totalColon')}</span> <span>{fmtCurr(sums.umumiy, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('chiqimTolov.supplierPaymentsSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => sums.taminotchi > 0 && (
              <div key={cur} className="mb-2 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-sm flex justify-between font-bold text-blue-600"><span>{t('chiqimTolov.totalColon')}</span> <span>{fmtCurr(sums.taminotchi, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('chiqimTolov.expensesSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => sums.xarajat > 0 && (
              <div key={cur} className="mb-2 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-sm flex justify-between font-bold text-blue-600"><span>{t('chiqimTolov.totalColon')}</span> <span>{fmtCurr(sums.xarajat, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('chiqimTolov.customerReturnSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => sums.qaytaruv > 0 && (
              <div key={cur} className="mb-2 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-sm flex justify-between font-bold text-amber-600"><span>{t('chiqimTolov.totalColon')}</span> <span>{fmtCurr(sums.qaytaruv, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-slate-800">{t('chiqimTolov.editPaymentTitle')}</h2>
              <button onClick={closeEdit} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
            </div>

            <div className="space-y-4">
              {/* Contragent info (read-only) */}
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-xs text-slate-500 mb-1">{t('admin.dict.contragent')}</div>
                <div className="font-semibold text-slate-800">{editItem.contragent}</div>
              </div>

              {/* Amount */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('chiqimTolov.amountSom')}</label>
                <input
                  type="number"
                  value={editForm.amount}
                  onChange={e => setEditForm(f => ({ ...f, amount: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder={t('common.amount')}
                />
              </div>

              {/* Payment type */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('chiqimTolov.paymentTypeLabel')}</label>
                <select
                  value={editForm.payment_type}
                  onChange={e => setEditForm(f => ({ ...f, payment_type: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {PAYMENT_TYPES.map(pt => (
                    <option key={pt.value} value={pt.value}>{pt.label}</option>
                  ))}
                </select>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('chiqimTolov.infoNoteLabel')}</label>
                <textarea
                  value={editForm.description}
                  onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                  rows={3}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  placeholder={t('chiqimTolov.notePlaceholder')}
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
                {t('admin.dict.cancel')}
              </button>
              <button
                onClick={handleEditSave}
                disabled={editLoading}
                className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                {editLoading ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Yangi chiqim to'lov — ta'minotchi qarzini to'lash */}
      {payOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-2 md:p-4 bg-black/40 backdrop-blur-sm" onClick={closePay}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 md:px-6 py-4 border-b border-slate-100 shrink-0">
              <div>
                <h2 className="text-lg font-bold text-slate-800">{t('chiqimTolov.newPaymentTitle')}</h2>
                <p className="text-xs text-blue-500 font-medium mt-0.5">{new Date().toLocaleString('uz-UZ').replace(',', '')}</p>
              </div>
              <button onClick={closePay} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
            </div>

            <div className="px-5 md:px-6 py-4 overflow-y-auto space-y-4">
              {/* Ta'minotchi */}
              {paySupplier ? (
                <div className="flex items-start justify-between gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                  <div className="min-w-0">
                    <div className="text-xs text-slate-500 mb-0.5">{t('chiqimTolov.supplierLabel')}</div>
                    <div className="font-bold text-slate-800 truncate">{paySupplier.name}</div>
                    {paySupplier.phone && <div className="text-xs text-slate-500">{paySupplier.phone}</div>}
                    <div className="text-sm font-bold mt-1">
                      {positiveDebts(paySupplier).length > 0 ? (
                        <span className="text-red-500">
                          {t('chiqimTolov.currentDebt')}
                          {positiveDebts(paySupplier).map(([cur, amt]) => <span key={cur} className="ml-2 inline-block">{fmtNum(amt)} {cur}</span>)}
                        </span>
                      ) : <span className="text-emerald-600">{t('chiqimTolov.noDebt')}</span>}
                    </div>
                  </div>
                  <button onClick={() => setPaySupplier(null)} disabled={paySaving}
                    className="px-2.5 py-1 text-xs font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg shrink-0">
                    {t('chiqimTolov.changeSupplier')}
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-slate-700">{t('chiqimTolov.supplierLabel')} *</label>
                  <input autoFocus value={supSearch} onChange={e => setSupSearch(e.target.value)}
                    placeholder={t('chiqimTolov.searchSupplier')}
                    className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  <label className="flex items-center gap-2 text-xs text-slate-600 select-none cursor-pointer">
                    <input type="checkbox" checked={onlyDebtors} onChange={e => setOnlyDebtors(e.target.checked)} />
                    {t('chiqimTolov.onlyDebtors')}
                  </label>
                  <div className="max-h-64 overflow-y-auto border border-slate-100 rounded-xl divide-y divide-slate-50">
                    {filteredSuppliers.length > 0 ? filteredSuppliers.slice(0, 200).map(s => (
                      <button key={s.id} type="button" onClick={() => pickSupplier(s)}
                        className="w-full flex items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-blue-50 transition-colors">
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-slate-800 truncate">{s.name}</span>
                          {s.phone && <span className="block text-xs text-slate-400">{s.phone}</span>}
                        </span>
                        <span className="text-xs font-bold whitespace-nowrap">
                          {positiveDebts(s).length > 0
                            ? positiveDebts(s).map(([cur, amt]) => <span key={cur} className="block text-red-500">{fmtNum(amt)} {cur}</span>)
                            : <span className="text-emerald-600">{t('chiqimTolov.noDebt')}</span>}
                        </span>
                      </button>
                    )) : <div className="py-6 text-center text-sm text-slate-400">{t('common.noData')}</div>}
                  </div>
                </div>
              )}

              {paySupplier && (
                <>
                  {/* Kassa */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">{t('chiqimTolov.walletLabel')}</label>
                    <select value={payWallet} onChange={e => setPayWallet(e.target.value)}
                      className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="">{t('chiqimTolov.mainWallet')}</option>
                      {wallets.map(w => <option key={w.id} value={w.id}>{w.name} — {fmtNum(w.balance)} {t('common.sum')}</option>)}
                    </select>
                  </div>

                  {/* To'lov qatorlari */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-slate-700">{t('chiqimTolov.paymentTypeLabel')} *</label>
                    {payRows.map((row, idx) => (
                      <div key={row.id} className="flex gap-2">
                        <select value={row.payType} onChange={e => updatePayRow(idx, 'payType', e.target.value)}
                          className="w-28 sm:w-40 shrink-0 px-3 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                          {PAYMENT_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
                        </select>
                        <div className="flex flex-1 min-w-0">
                          <input type="number" min="0" value={row.payAmount} placeholder="0"
                            onChange={e => updatePayRow(idx, 'payAmount', e.target.value)}
                            className="flex-1 min-w-0 px-3 py-2.5 border border-slate-200 rounded-l-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                          <select value={row.currency} onChange={e => updatePayRow(idx, 'currency', e.target.value)}
                            className="px-2 py-2.5 border border-l-0 border-slate-200 text-sm font-bold text-blue-600 bg-white focus:outline-none">
                            {currencies.map(c => <option key={c.code} value={c.code}>{c.code}</option>)}
                          </select>
                          <button type="button" onClick={() => updatePayRow(idx, 'payAmount', String(debtFor(row.currency) || ''))}
                            className="px-3 border border-l-0 border-slate-200 rounded-r-xl bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-bold whitespace-nowrap">
                            {t('chiqimTolov.allAmount')}
                          </button>
                        </div>
                        <button type="button"
                          onClick={() => setPayRows(prev => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : [newPayRow(row.currency)]))}
                          className="px-3 bg-red-50 hover:bg-red-100 text-red-500 rounded-xl font-bold">&minus;</button>
                      </div>
                    ))}
                    {payRows.length < 4 && (
                      <button type="button" onClick={() => setPayRows(prev => [...prev, newPayRow(prev[prev.length - 1]?.currency || 'UZS')])}
                        className="ml-auto flex items-center gap-1 px-2 py-0.5 text-sm font-semibold text-blue-600 hover:bg-blue-50 rounded-xl">
                        + {t('chiqimTolov.addRow')}
                      </button>
                    )}
                  </div>

                  {/* Izoh */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">{t('chiqimTolov.infoNoteLabel')}</label>
                    <textarea rows={2} value={payNote} onChange={e => setPayNote(e.target.value)}
                      placeholder={t('chiqimTolov.notePlaceholder')}
                      className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
                  </div>

                  {/* Valyuta bo'yicha qoldiq */}
                  {(() => {
                    const paid = payRows.reduce((acc, r) => {
                      acc[r.currency] = (acc[r.currency] || 0) + (Number(r.payAmount) || 0);
                      return acc;
                    }, {});
                    const codes = [...new Set([...positiveDebts(paySupplier).map(([c]) => c), ...Object.keys(paid).filter(c => paid[c] > 0)])];
                    if (codes.length === 0) return null;
                    return (
                      <div className="bg-blue-50/50 rounded-xl p-3 border border-blue-100/50 space-y-1">
                        {codes.map(cur => {
                          const debt = debtFor(cur);
                          const pay = paid[cur] || 0;
                          const left = debt - pay;
                          return (
                            <div key={cur} className="flex flex-wrap justify-between gap-x-4 text-xs">
                              <span className="text-slate-500">{t('chiqimTolov.currentDebt')} <b className="text-slate-700">{fmtNum(debt)} {cur}</b></span>
                              <span className="text-slate-500">{t('chiqimTolov.paidColon')} <b className="text-blue-600">{fmtNum(pay)} {cur}</b></span>
                              <span className="text-slate-500">
                                {left >= 0 ? t('chiqimTolov.remainingAfter') : t('chiqimTolov.advanceAfter')}{' '}
                                <b className={left > 0 ? 'text-red-500' : left < 0 ? 'text-amber-600' : 'text-emerald-600'}>{fmtNum(Math.abs(left))} {cur}</b>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </>
              )}

              {payError && <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">{payError}</div>}
            </div>

            <div className="flex gap-3 px-5 md:px-6 py-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl shrink-0">
              <button onClick={closePay} disabled={paySaving}
                className="flex-1 px-4 py-2.5 border border-slate-200 bg-white text-slate-600 text-sm font-semibold rounded-xl hover:bg-slate-50">
                {t('admin.dict.cancel')}
              </button>
              <button onClick={handlePaySave}
                disabled={paySaving || !paySupplier || !payRows.some(r => Number(r.payAmount) > 0)}
                className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">
                {paySaving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
