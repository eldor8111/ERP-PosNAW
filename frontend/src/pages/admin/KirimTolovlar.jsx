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
const positiveDebts = (c) => {
  if (c?.debt_balances && typeof c.debt_balances === 'object' && Object.keys(c.debt_balances).length > 0) {
    return Object.entries(c.debt_balances).filter(([, v]) => Number(v) > 0);
  }
  return Number(c?.debt_balance) > 0 ? [['UZS', c.debt_balance]] : [];
};
const newPayRow = (currency = 'UZS', amount = '') => ({ id: Date.now() + Math.random(), payType: 'cash', payAmount: amount, currency });
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);

export default function KirimTolovlar() {
  const { t } = useLang();
  const PAYMENT_TYPES = [
    { value: 'cash', label: t('kirimTolov.paymentCash') },
    { value: 'card', label: t('kirimTolov.paymentCard') },
    { value: 'bank_transfer', label: t('kirimTolov.paymentBankTransfer') },
    { value: 'click', label: t('kirimTolov.paymentClick') },
    { value: 'payme', label: t('kirimTolov.paymentPayme') },
    { value: 'uzum', label: t('kirimTolov.paymentUzum') },
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

  // Yangi kirim to'lov modali
  const [payOpen, setPayOpen] = useState(false);
  const [paySourceType, setPaySourceType] = useState('customer'); // 'customer' | 'other'
  const [customers, setCustomers] = useState([]);
  const [wallets, setWallets] = useState([]);
  const [currencies, setCurrencies] = useState([{ code: 'UZS', rate: 1 }]);
  const [custSearch, setCustSearch] = useState('');
  const [onlyDebtors, setOnlyDebtors] = useState(true);
  const [payCustomer, setPayCustomer] = useState(null);
  const [otherSourceName, setOtherSourceName] = useState('');
  const [payWallet, setPayWallet] = useState('');
  const [payRows, setPayRows] = useState([newPayRow()]);
  const [payNote, setPayNote] = useState('');
  const [paySaving, setPaySaving] = useState(false);
  const [payError, setPayError] = useState('');

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

  useEffect(() => { loadData(); }, [dateFrom, dateTo]);

  const summaryData = useMemo(() => {
    if (!data?.items) return {};
    const res = {};
    data.items.forEach(i => {
      const cur = i.currency_code || 'UZS';
      if (!res[cur]) res[cur] = { naqd: 0, plastik: 0, bank: 0, umumiy: 0, sotuv: 0, qarz_yopish: 0, qaytaruv: 0 };
      
      const amt = Number(i.amount) || 0;
      res[cur].umumiy += amt;
      
      if (['cash', 'naqd'].includes(i.payment_type)) res[cur].naqd += amt;
      else if (['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type)) res[cur].plastik += amt;
      else if (['bank', 'bank_transfer'].includes(i.payment_type)) res[cur].bank += amt;

      if (i.reference_type === 'customer_payment') {
        res[cur].qarz_yopish += amt;
      } else if (i.reference_type === 'sale') {
        res[cur].sotuv += amt;
      } else if (i.reference_type === 'return_to_supplier') {
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
    if (!window.confirm(t('kirimTolov.deleteConfirm'))) return;
    try {
      await api.delete(`/finance/transactions/${item.id}`);
      loadData();
    } catch (e) {
      alert(t('kirimTolov.errorPrefix') + (e.response?.data?.detail || e.message));
    }
  };

  const exportExcel = async () => {
    if (!data?.items) return;
    const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
    const ws = XLSX.utils.json_to_sheet(data.items.map((i, index) => ({
      '#': index + 1,
      [t('kirimTolov.colContragent')]: i.contragent,
      [t('kirimTolov.colType')]: i.turi,
      [t('kirimTolov.colPayment')]: i.amount,
      [t('kirimTolov.colPaymentType')]: i.payment_type,
      [t('kirimTolov.colSourceShort')]: i.reference_type,
      [t('kirimTolov.colWallet')]: i.wallet,
      [t('kirimTolov.colInfo')]: i.description || '',
      [t('kirimTolov.colDate')]: new Date(i.created_at).toLocaleString('uz-UZ')
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, t('kirimTolov.title'));
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `kirim_tolovlar_${today()}.xlsx`);
  };

  const openPay = async () => {
    setPayOpen(true);
    setPaySourceType('customer');
    setPayCustomer(null);
    setOtherSourceName('');
    setCustSearch('');
    setOnlyDebtors(true);
    setPayRows([newPayRow()]);
    setPayNote('');
    setPayError('');
    const [cRes, wRes, curRes] = await Promise.all([
      api.get('/customers', { params: { limit: 2000 } }).catch(() => ({ data: [] })),
      api.get('/finance/wallets').catch(() => ({ data: [] })),
      api.get('/currencies/active').catch(() => ({ data: [] })),
    ]);
    const custs = Array.isArray(cRes.data) ? cRes.data : (cRes.data?.items || []);
    setCustomers(custs);
    const ws = Array.isArray(wRes.data) ? wRes.data : [];
    setWallets(ws);
    setPayWallet(ws.length > 0 ? String(ws[0].id) : '');
    const cs = Array.isArray(curRes.data) ? [...curRes.data] : [];
    if (!cs.find(c => c.code === 'UZS')) cs.unshift({ code: 'UZS', rate: 1 });
    setCurrencies(cs);
  };

  const closePay = () => { if (!paySaving) setPayOpen(false); };

  const pickCustomer = (c) => {
    setPayCustomer(c);
    const first = positiveDebts(c)[0];
    setPayRows([newPayRow(first?.[0] || 'UZS', first ? String(first[1]) : '')]);
    setPayError('');
  };

  const updatePayRow = (idx, field, value) =>
    setPayRows(prev => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));

  const debtFor = (cur) => Number((positiveDebts(payCustomer).find(([c]) => c === cur) || [])[1] || 0);

  const handlePaySave = async () => {
    const valid = payRows.filter(r => Number(r.payAmount) > 0 && r.payType);
    if (valid.length === 0) { setPayError(t('kirimTolov.enterAmount') || "Kamida bitta to'lov summasini kiriting"); return; }
    
    if (paySourceType === 'customer') {
      if (!payCustomer) { setPayError(t('kirimTolov.selectCustomerFirst') || "Avval mijozni tanlang"); return; }
    } else {
      if (!otherSourceName.trim()) { setPayError("Kirim manbasini (nomini) kiriting"); return; }
    }

    setPaySaving(true);
    setPayError('');
    let done = 0;
    try {
      if (paySourceType === 'customer') {
        for (const row of valid) {
          await api.post(`/customers/${payCustomer.id}/pay-debt`, {
            amount: Number(row.payAmount),
            currency: row.currency || 'UZS',
            payment_type: row.payType,
            reason: payNote.trim() || t('customer.customerDebtPaymentReason') || "Mijoz qarz to'lovi",
            wallet_id: payWallet ? Number(payWallet) : null,
          });
          done += 1;
        }
      } else {
        for (const row of valid) {
          await api.post('/finance/transactions', {
            type: 'income',
            amount: Number(row.payAmount),
            currency_code: row.currency || 'UZS',
            payment_type: row.payType,
            description: `${otherSourceName.trim()}${payNote.trim() ? ' — ' + payNote.trim() : ''}`,
            wallet_id: payWallet ? Number(payWallet) : null,
            reference_type: 'other_income',
          });
          done += 1;
        }
      }

      toast.success(t('kirimTolov.paymentSaved') || "Kirim to'lov muvaffaqiyatli saqlandi");
      setPayOpen(false);
      loadData();
    } catch (e) {
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

  const filteredCustomers = useMemo(() => {
    let list = customers;
    if (onlyDebtors) list = list.filter(c => positiveDebts(c).length > 0);
    if (custSearch.trim()) list = list.filter(c => matchesSearch(`${c.name || ''} ${c.phone || ''}`, custSearch));
    return list;
  }, [customers, onlyDebtors, custSearch]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">{t('kirimTolov.title')}</h1>
        <div className="flex items-center gap-3">
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <button onClick={exportExcel} className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-xl">
            {t('kirimTolov.exportExcel')}
          </button>
          <button onClick={openPay} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl flex items-center gap-1.5 shadow-sm shadow-blue-200 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" /></svg>
            {t('kirimTolov.newPayment')}
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
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colContragent')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colType')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colPayment')}</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500" colSpan="6">{t('kirimTolov.colPaymentTypes')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colSource')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colWallet')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colInfo')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('kirimTolov.colDate')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">{t('common.actions')}</th>
              </tr>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th colSpan="4"></th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('kirimTolov.colCash')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('kirimTolov.colCard')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('kirimTolov.colBankTransfer')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('kirimTolov.colClick')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('kirimTolov.colPayme')}</th>
                <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">{t('kirimTolov.colUzum')}</th>
                <th colSpan="5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr><td colSpan="15" className="text-center py-8">{t('common.loading')}</td></tr>
              ) : data?.items?.length > 0 ? (
                data.items.map((i, idx) => (
                  <tr key={i.id} className="hover:bg-slate-50 text-sm">
                    <td className="px-4 py-3 text-slate-500">{idx + 1}</td>
                    <td className="px-4 py-3 font-semibold text-blue-600">{i.contragent}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-md text-xs font-medium ${i.turi === 'Mijoz' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                        {i.turi}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-bold text-emerald-600">{fmtCurr(i.amount, i.currency_code)}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['cash', 'naqd'].includes(i.payment_type) ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type) ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{['bank', 'bank_transfer'].includes(i.payment_type) ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'click' ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'payme' ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'uzum' ? fmtCurr(i.amount, i.currency_code) : 0}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded-md text-xs bg-blue-50 text-blue-600 border border-blue-100">
                        {i.reference_type === 'customer_payment' ? t('kirimTolov.sourceDebtPayment') : i.reference_type === 'sale' ? t('kirimTolov.sourceSale') : t('kirimTolov.sourceSupplierReturn')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{i.wallet}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{i.description || '—'}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{new Date(i.created_at).toLocaleString('uz-UZ')}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        {i.reference_type !== 'sale' ? (
                          <>
                            <button
                              onClick={() => openEdit(i)}
                              className="px-2 py-1 text-xs font-semibold bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg transition-colors"
                            >
                              {t('common.edit')}
                            </button>
                            <button
                              onClick={() => handleDelete(i)}
                              className="px-2 py-1 text-xs font-semibold bg-red-50 text-red-500 hover:bg-red-100 rounded-lg transition-colors"
                            >
                              {t('common.delete')}
                            </button>
                          </>
                        ) : (
                          <span className="text-xs text-slate-400 italic">{t('kirimTolov.fromSalesSection')}</span>
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
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('kirimTolov.totalPaymentsSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => (
              <div key={cur} className="mb-3 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-slate-600 text-sm flex justify-between mb-1"><span>{t('kirimTolov.cashColon')}</span> <span className="font-bold text-slate-800">{fmtCurr(sums.naqd, cur)}</span></div>
                <div className="text-slate-600 text-sm flex justify-between mb-1"><span>{t('kirimTolov.cardColon')}</span> <span className="font-bold text-slate-800">{fmtCurr(sums.plastik, cur)}</span></div>
                <div className="text-slate-600 text-sm flex justify-between mb-2"><span>{t('kirimTolov.bankColon')}</span> <span className="font-bold text-slate-800">{fmtCurr(sums.bank, cur)}</span></div>
                <div className="text-sm flex justify-between font-bold text-emerald-600"><span>{t('kirimTolov.totalColon')}</span> <span>{fmtCurr(sums.umumiy, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('kirimTolov.debtPaymentsSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => sums.qarz_yopish > 0 && (
              <div key={cur} className="mb-2 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-sm flex justify-between font-bold text-blue-600"><span>{t('kirimTolov.totalColon')}</span> <span>{fmtCurr(sums.qarz_yopish, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('kirimTolov.salePaymentsSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => sums.sotuv > 0 && (
              <div key={cur} className="mb-2 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-sm flex justify-between font-bold text-blue-600"><span>{t('kirimTolov.totalColon')}</span> <span>{fmtCurr(sums.sotuv, cur)}</span></div>
              </div>
            )) : <div className="text-slate-500 text-sm">{`0 ${t('common.sum')}`}</div>}
          </div>
          <div className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm">
            <h3 className="text-slate-500 text-sm font-semibold mb-3">{t('kirimTolov.supplierReturnSum')}</h3>
            {Object.entries(summaryData).length > 0 ? Object.entries(summaryData).map(([cur, sums]) => sums.qaytaruv > 0 && (
              <div key={cur} className="mb-2 last:mb-0 border-b last:border-b-0 border-slate-50 pb-2">
                <div className="text-sm flex justify-between font-bold text-amber-600"><span>{t('kirimTolov.totalColon')}</span> <span>{fmtCurr(sums.qaytaruv, cur)}</span></div>
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
              <h2 className="text-lg font-bold text-slate-800">{t('kirimTolov.editPaymentTitle')}</h2>
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
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('kirimTolov.amountSom')}</label>
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
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('kirimTolov.paymentTypeLabel')}</label>
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
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('kirimTolov.infoNoteLabel')}</label>
                <textarea
                  value={editForm.description}
                  onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                  rows={3}
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  placeholder={t('kirimTolov.notePlaceholder')}
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

      {/* ── Yangi Kirim To'lov Modali ── */}
      {payOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-2 md:p-4 bg-black/40 backdrop-blur-sm" onClick={closePay}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-5 md:px-6 py-4 border-b border-slate-100 shrink-0">
              <div>
                <h2 className="text-lg font-bold text-slate-800">{t('kirimTolov.newPaymentTitle')}</h2>
                <p className="text-xs text-emerald-600 font-medium mt-0.5">{new Date().toLocaleString('uz-UZ').replace(',', '')}</p>
              </div>
              <button onClick={closePay} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
            </div>

            <div className="px-5 md:px-6 py-4 overflow-y-auto space-y-4">
              {/* Kirim turi tanlash (Mijoz to'lovi yoki Boshqa kirim) */}
              <div className="flex gap-2 p-1 bg-slate-100 rounded-xl">
                <button
                  type="button"
                  onClick={() => { setPaySourceType('customer'); setPayError(''); }}
                  className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
                    paySourceType === 'customer' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  👤 {t('kirimTolov.sourceCustomer')}
                </button>
                <button
                  type="button"
                  onClick={() => { setPaySourceType('other'); setPayError(''); }}
                  className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
                    paySourceType === 'other' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  💰 {t('kirimTolov.sourceOther')}
                </button>
              </div>

              {/* Mijoz tanlash */}
              {paySourceType === 'customer' && (
                payCustomer ? (
                  <div className="flex items-start justify-between gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                    <div className="min-w-0">
                      <div className="text-xs text-slate-500 mb-0.5">{t('kirimTolov.customerLabel')}</div>
                      <div className="font-bold text-slate-800 truncate">{payCustomer.name}</div>
                      {payCustomer.phone && <div className="text-xs text-slate-500">{payCustomer.phone}</div>}
                      <div className="text-sm font-bold mt-1">
                        {positiveDebts(payCustomer).length > 0 ? (
                          <span className="text-red-500">
                            {t('kirimTolov.currentDebt')}{' '}
                            {positiveDebts(payCustomer).map(([cur, amt]) => (
                              <span key={cur} className="ml-2 inline-block font-black">{fmtNum(amt)} {cur}</span>
                            ))}
                          </span>
                        ) : <span className="text-emerald-600">{t('kirimTolov.noDebt')}</span>}
                      </div>
                    </div>
                    <button onClick={() => setPayCustomer(null)} disabled={paySaving}
                      className="px-2.5 py-1 text-xs font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg shrink-0">
                      {t('kirimTolov.changeCustomer')}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-slate-700">{t('kirimTolov.customerLabel')} *</label>
                    <input autoFocus value={custSearch} onChange={e => setCustSearch(e.target.value)}
                      placeholder={t('kirimTolov.searchCustomer')}
                      className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    <label className="flex items-center gap-2 text-xs text-slate-600 select-none cursor-pointer">
                      <input type="checkbox" checked={onlyDebtors} onChange={e => setOnlyDebtors(e.target.checked)} />
                      {t('kirimTolov.onlyDebtors')}
                    </label>
                    <div className="max-h-56 overflow-y-auto border border-slate-100 rounded-xl divide-y divide-slate-50">
                      {filteredCustomers.length > 0 ? filteredCustomers.slice(0, 200).map(c => (
                        <button key={c.id} type="button" onClick={() => pickCustomer(c)}
                          className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-blue-50 transition-colors">
                          <span className="min-w-0">
                            <span className="block text-sm font-semibold text-slate-800 truncate">{c.name}</span>
                            {c.phone && <span className="block text-xs text-slate-400">{c.phone}</span>}
                          </span>
                          <span className="text-xs font-bold whitespace-nowrap">
                            {positiveDebts(c).length > 0
                              ? positiveDebts(c).map(([cur, amt]) => <span key={cur} className="block text-red-500">{fmtNum(amt)} {cur}</span>)
                              : <span className="text-emerald-600">{t('kirimTolov.noDebt')}</span>}
                          </span>
                        </button>
                      )) : <div className="py-6 text-center text-sm text-slate-400">{t('common.noData')}</div>}
                    </div>
                  </div>
                )
              )}

              {/* Boshqa kirim manbasi */}
              {paySourceType === 'other' && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">{t('kirimTolov.otherSourceLabel')} *</label>
                  <input
                    value={otherSourceName}
                    onChange={e => setOtherSourceName(e.target.value)}
                    placeholder={t('kirimTolov.otherSourcePlaceholder')}
                    className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              )}

              {/* Kassa / Hamyon tanlash */}
              {(paySourceType === 'other' || payCustomer) && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">{t('kirimTolov.walletLabel')}</label>
                    <select value={payWallet} onChange={e => setPayWallet(e.target.value)}
                      className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                      <option value="">{t('kirimTolov.mainWallet')}</option>
                      {wallets.map(w => <option key={w.id} value={w.id}>{w.name} — {fmtNum(w.balance)} {t('common.sum')}</option>)}
                    </select>
                  </div>

                  {/* To'lov qatorlari */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-slate-700">{t('kirimTolov.paymentTypeLabel')} *</label>
                    {payRows.map((row, idx) => (
                      <div key={row.id} className="flex gap-2">
                        <select value={row.payType} onChange={e => updatePayRow(idx, 'payType', e.target.value)}
                          className="w-28 sm:w-40 shrink-0 px-3 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                          {PAYMENT_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
                        </select>
                        <div className="flex flex-1 min-w-0">
                          <input type="number" min="0" value={row.payAmount} placeholder="0"
                            onChange={e => updatePayRow(idx, 'payAmount', e.target.value)}
                            className="flex-1 min-w-0 px-3 py-2.5 border border-slate-200 rounded-l-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-bold" />
                          <select value={row.currency} onChange={e => updatePayRow(idx, 'currency', e.target.value)}
                            className="px-2 py-2.5 border border-l-0 border-slate-200 text-sm font-bold text-emerald-600 bg-white focus:outline-none">
                            {currencies.map(c => <option key={c.code} value={c.code}>{c.code}</option>)}
                          </select>
                          {paySourceType === 'customer' && payCustomer && (
                            <button type="button" onClick={() => updatePayRow(idx, 'payAmount', String(debtFor(row.currency) || ''))}
                              className="px-3 border border-l-0 border-slate-200 rounded-r-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs font-bold whitespace-nowrap">
                              {t('kirimTolov.allAmount')}
                            </button>
                          )}
                        </div>
                        <button type="button"
                          onClick={() => setPayRows(prev => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : [newPayRow(row.currency)]))}
                          className="px-3 bg-red-50 hover:bg-red-100 text-red-500 rounded-xl font-bold">&minus;</button>
                      </div>
                    ))}
                    {payRows.length < 4 && (
                      <button type="button" onClick={() => setPayRows(prev => [...prev, newPayRow(prev[prev.length - 1]?.currency || 'UZS')])}
                        className="ml-auto flex items-center gap-1 px-2 py-0.5 text-sm font-semibold text-blue-600 hover:bg-blue-50 rounded-xl">
                        + {t('kirimTolov.addRow')}
                      </button>
                    )}
                  </div>

                  {/* Izoh */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">{t('kirimTolov.infoNoteLabel')}</label>
                    <textarea rows={2} value={payNote} onChange={e => setPayNote(e.target.value)}
                      placeholder={t('kirimTolov.notePlaceholder')}
                      className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
                  </div>

                  {/* Valyuta bo'yicha qoldiq hisob-kitobi (agar mijoz bo'lsa) */}
                  {paySourceType === 'customer' && payCustomer && (() => {
                    const paid = payRows.reduce((acc, r) => {
                      acc[r.currency] = (acc[r.currency] || 0) + (Number(r.payAmount) || 0);
                      return acc;
                    }, {});
                    const codes = [...new Set([...positiveDebts(payCustomer).map(([c]) => c), ...Object.keys(paid).filter(c => paid[c] > 0)])];
                    if (codes.length === 0) return null;
                    return (
                      <div className="bg-emerald-50/50 rounded-xl p-3 border border-emerald-100/50 space-y-1">
                        {codes.map(cur => {
                          const debt = debtFor(cur);
                          const pay = paid[cur] || 0;
                          const left = debt - pay;
                          return (
                            <div key={cur} className="flex flex-wrap justify-between gap-x-4 text-xs">
                              <span className="text-slate-500">{t('kirimTolov.currentDebt')} <b className="text-slate-700">{fmtNum(debt)} {cur}</b></span>
                              <span className="text-slate-500">{t('kirimTolov.paidColon')} <b className="text-emerald-600">{fmtNum(pay)} {cur}</b></span>
                              <span className="text-slate-500">
                                {left >= 0 ? t('kirimTolov.remainingAfter') : t('kirimTolov.advanceAfter')}{' '}
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
                disabled={paySaving || (paySourceType === 'customer' ? !payCustomer : !otherSourceName.trim()) || !payRows.some(r => Number(r.payAmount) > 0)}
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
