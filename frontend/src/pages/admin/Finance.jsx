import { useState, useEffect, useCallback } from 'react';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

const fmt = (v, t) => Number(v || 0).toLocaleString('uz-UZ') + " " + (t ? (t('common.sum') || "so'm") : "so'm");
const today = () => new Date().toISOString().slice(0, 10);
const firstOfMonth = () => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); };

// ─── Spinner ───────────────────────────────────────────────────────────────────
const Spinner = () => (
  <div className="flex justify-center py-16">
    <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

export default function Finance() {
  const { t } = useLang();
  const [activeTab, setActiveTab] = useState('expenses');
  const [expenses, setExpenses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [balance, setBalance] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [customerDebts, setCustomerDebts] = useState(null);
  const [debtSearch, setDebtSearch] = useState('');
  const [supplierDebts, setSupplierDebts] = useState(null);
  const [plData, setPlData] = useState(null);

  const [showAddExpense, setShowAddExpense] = useState(false);
  const [showAddCat, setShowAddCat] = useState(false);
  const [form, setForm] = useState({ category_id: '', amount: '', description: '', branch_id: 1 });
  const [catForm, setCatForm] = useState({ name: '', description: '' });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  // Sana filtrlari
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());

  // Qarz to'lash modal
  const [payModal, setPayModal] = useState(null); // {type: 'customer'|'supplier', id, name, balance}
  const [payAmount, setPayAmount] = useState('');
  const [paying, setPaying] = useState(false);

  const loadBase = useCallback(async () => {
    const [cats, bal] = await Promise.all([
      api.get('/finance/expense-categories'),
      api.get('/finance/cash-balance'),
    ]);
    setCategories(cats.data);
    setBalance(bal.data);
  }, []);

  const loadTab = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 'expenses') {
        const r = await api.get(`/finance/expenses?date_from=${dateFrom}&date_to=${dateTo}`);
        setExpenses(r.data);
      } else if (activeTab === 'transactions') {
        const r = await api.get(`/finance/transactions?date_from=${dateFrom}&date_to=${dateTo}`);
        setTransactions(r.data);
      } else if (activeTab === 'customer-debts') {
        const r = await api.get('/finance/customer-debts');
        setCustomerDebts(r.data);
      } else if (activeTab === 'supplier-debts') {
        const r = await api.get('/finance/supplier-debts');
        setSupplierDebts(r.data);
      } else if (activeTab === 'pl') {
        const r = await api.get(`/finance/profit-loss?date_from=${dateFrom}&date_to=${dateTo}`);
        setPlData(r.data);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [activeTab, dateFrom, dateTo]);

  useEffect(() => { loadBase(); }, []);
  useEffect(() => { loadTab(); }, [activeTab]);

  const addExpense = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/finance/expenses', form);
      setShowAddExpense(false);
      setForm({ category_id: '', amount: '', description: '', branch_id: 1 });
      loadBase();
      loadTab();
    } finally { setSaving(false); }
  };

  const addCategory = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/finance/expense-categories', catForm);
      setShowAddCat(false);
      setCatForm({ name: '', description: '' });
      loadBase();
    } finally { setSaving(false); }
  };

  const deleteExpense = async (id) => {
    if (!confirm(t('confirm.delete'))) return;
    await api.delete(`/finance/expenses/${id}`);
    loadTab();
    loadBase();
  };

  const handlePay = async () => {
    if (!payModal || !payAmount) return;
    setPaying(true);
    try {
      const endpoint = payModal.type === 'customer'
        ? `/finance/customer-debts/${payModal.id}/pay`
        : `/finance/supplier-debts/${payModal.id}/pay`;
      await api.post(endpoint, { amount: parseFloat(payAmount) });
      setPayModal(null);
      setPayAmount('');
      loadTab();
      loadBase();
    } finally { setPaying(false); }
  };

  const exportExpenses = () => {
    const ws = XLSX.utils.json_to_sheet(expenses.map(e => ({
      'Kategoriya': e.category_name, 'Summa': e.amount,
      'Izoh': e.description, 'Sana': new Date(e.created_at).toLocaleDateString('uz-UZ'),
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Xarajatlar');
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `xarajatlar_${today()}.xlsx`);
  };

  const tabs = [
    { key: 'expenses', label: t('finance.expense') },
    { key: 'categories', label: t('common.category') },
    { key: 'transactions', label: t('finance.transaction') },
    { key: 'customer-debts', label: t('customer.totalDebtors') || 'Debitorlar' },
    { key: 'supplier-debts', label: t('customer.totalCreditors') || 'Kreditorlar' },
    { key: 'pl', label: t('finance.pl') || 'Foyda/Zarar' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t('finance.title')}</h1>
        <p className="text-slate-500 text-sm mt-0.5">{t('finance.income')}, {t('finance.expense').toLowerCase()}, {t('common.debt').toLowerCase()}</p>
      </div>

      {/* KPI Cards */}
      {balance && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center shrink-0">
              <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 11l5-5m0 0l5 5m-5-5v12" />
              </svg>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('finance.income')}</div>
              <div className="text-xl font-bold text-emerald-600 mt-0.5">{fmt(balance.total_income, t)}</div>
            </div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center shrink-0">
              <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 13l-5 5m0 0l-5-5m5 5V6" />
              </svg>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('finance.expense')}</div>
              <div className="text-xl font-bold text-red-500 mt-0.5">{fmt(balance.total_expense, t)}</div>
            </div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${balance.balance >= 0 ? 'bg-indigo-100' : 'bg-red-100'}`}>
              <svg className={`w-6 h-6 ${balance.balance >= 0 ? 'text-indigo-600' : 'text-red-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('finance.cashBalance')}</div>
              <div className={`text-xl font-bold mt-0.5 ${balance.balance >= 0 ? 'text-indigo-600' : 'text-red-500'}`}>
                {fmt(balance.balance, t)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs + Content */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        {/* Tab Bar */}
        <div className="flex border-b border-slate-100 px-2 pt-2 gap-1 overflow-x-auto">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setActiveTab(t.key)}
              className={`px-5 py-2.5 text-sm font-medium rounded-t-xl transition-all whitespace-nowrap ${
                activeTab === t.key
                  ? 'bg-indigo-50 text-indigo-600 border-b-2 border-indigo-500'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Expenses Tab ── */}
        {activeTab === 'expenses' && (
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-50">
              <span className="text-sm font-semibold text-slate-700">{t('finance.allExpenses') || 'Barcha xarajatlar'}</span>
              <div className="flex gap-2">
                <button onClick={exportExpenses}
                  className="inline-flex items-center gap-2 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Excel
                </button>
                <button onClick={() => setShowAddExpense(!showAddExpense)}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl transition-colors">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                  </svg>
                  {t('finance.addExpense')}
                </button>
              </div>
            </div>

            {/* Sana filtri */}
            <div className="flex flex-wrap items-end gap-3 px-6 py-3 bg-slate-50/50 border-b border-slate-100">
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">{t('common.from')}</label>
                <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">{t('common.to')}</label>
                <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <button onClick={loadTab}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl transition-colors">
                {t('common.filter')}
              </button>
            </div>

            {showAddExpense && (
              <form onSubmit={addExpense} className="px-6 py-4 bg-slate-50 border-b border-slate-100 flex flex-wrap gap-3 items-end">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">{t('admin.dict.category') || 'Kategoriya'}</label>
                  <select required className="px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    onChange={e => setForm({ ...form, category_id: e.target.value })} value={form.category_id}>
                    <option value="">Tanlang...</option>
                    {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">{t('finance.amount') || 'Summa'} ({t('common.sum') || "so'm"})</label>
                  <input type="number" required placeholder="100000"
                    className="px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    onChange={e => setForm({ ...form, amount: e.target.value })} value={form.amount} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">{t('admin.dict.comment') || 'Izoh'}</label>
                  <input type="text" placeholder={t('finance.expenseAbout') || "Xarajat haqida..."}
                    className="px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    onChange={e => setForm({ ...form, description: e.target.value })} value={form.description} />
                </div>
                <button type="submit" disabled={saving}
                  className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
                  {saving ? t('common.saving') : t('common.save')}
                </button>
                <button type="button" onClick={() => setShowAddExpense(false)}
                  className="px-5 py-2.5 bg-slate-200 hover:bg-slate-300 text-slate-700 text-sm font-medium rounded-xl transition-colors">
                  {t('common.cancel')}
                </button>
              </form>
            )}

            {loading ? <Spinner /> : (
              <table className="min-w-full">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {[t('common.category'), t('common.amount'), t('common.note'), t('common.date'), ''].map((h, i) => (
                      <th key={i} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {expenses.map(e => (
                    <tr key={e.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center px-2.5 py-1 bg-indigo-50 text-indigo-600 text-xs font-medium rounded-lg">{e.category_name}</span>
                      </td>
                      <td className="px-6 py-4 text-sm font-semibold text-red-500">{fmt(e.amount, t)}</td>
                      <td className="px-6 py-4 text-sm text-slate-500">{e.description || '—'}</td>
                      <td className="px-6 py-4 text-sm text-slate-400">{new Date(e.created_at).toLocaleDateString('uz-UZ')}</td>
                      <td className="px-6 py-4">
                        <button onClick={() => deleteExpense(e.id)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                  {expenses.length === 0 && (
                    <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-slate-400">{t('finance.noExpenses') || "Xarajat yo'q"}</td></tr>
                  )}
                </tbody>
                {expenses.length > 0 && (
                  <tfoot>
                    <tr className="bg-red-50">
                      <td className="px-6 py-3 text-sm font-semibold text-slate-600">{t('admin.dict.th_total') || 'JAMI'}</td>
                      <td className="px-6 py-3 text-sm font-bold text-red-600">{fmt(expenses.reduce((a, e) => a + Number(e.amount), 0), t)}</td>
                      <td colSpan={3} />
                    </tr>
                  </tfoot>
                )}
              </table>
            )}
          </div>
        )}

        {/* ── Categories Tab ── */}
        {activeTab === 'categories' && (
          <div>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-50">
              <span className="text-sm font-semibold text-slate-700">{t('finance.expenseCategories') || 'Xarajat kategoriyalari'}</span>
              <button onClick={() => setShowAddCat(!showAddCat)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
                {t('finance.category')} +
              </button>
            </div>
            {showAddCat && (
              <form onSubmit={addCategory} className="px-6 py-4 bg-slate-50 border-b border-slate-100 flex flex-wrap gap-3 items-end">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">{t('common.name') || 'Nomi'}</label>
                  <input required placeholder={t('finance.categoryName') || "Kategoriya nomi"}
                    className="px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    onChange={e => setCatForm({ ...catForm, name: e.target.value })} value={catForm.name} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">{t('common.description') || 'Tavsif'}</label>
                  <input placeholder={t('common.descPlaceholder') || "Qisqacha tavsif"}
                    className="px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    onChange={e => setCatForm({ ...catForm, description: e.target.value })} value={catForm.description} />
                </div>
                <button type="submit" disabled={saving}
                  className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">{saving ? t('common.saving') : t('common.save')}</button>
                <button type="button" onClick={() => setShowAddCat(false)}
                  className="px-5 py-2.5 bg-slate-200 hover:bg-slate-300 text-slate-700 text-sm font-medium rounded-xl transition-colors">{t('common.cancel')}</button>
              </form>
            )}
            <div className="p-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {categories.map(c => (
                <div key={c.id} className="bg-slate-50 border border-slate-100 rounded-xl p-4 hover:border-indigo-200 hover:bg-indigo-50 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-2 h-2 rounded-full bg-indigo-500" />
                    <div className="text-sm font-semibold text-slate-800">{c.name}</div>
                  </div>
                  {c.description && <div className="text-xs text-slate-400 ml-4">{c.description}</div>}
                </div>
              ))}
              {categories.length === 0 && (
                <div className="col-span-4 text-center py-10 text-sm text-slate-400">{t('finance.noCategories') || 'Kategoriyalar topilmadi'}</div>
              )}
            </div>
          </div>
        )}

        {/* ── Transactions Tab ── */}
        {activeTab === 'transactions' && (
          <div>
            <div className="flex flex-wrap items-end gap-3 px-6 py-4 border-b border-slate-50">
              <span className="text-sm font-semibold text-slate-700 self-center mr-2">{t('finance.cashMovements') || 'Kassa harakatlari'}</span>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">{t('common.from') || 'Dan'}</label>
                <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">{t('common.to') || 'Gacha'}</label>
                <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <button onClick={loadTab}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl transition-colors">{t('admin.dict.filter') || 'Filtrlash'}</button>
            </div>
            {loading ? <Spinner /> : (
              <table className="min-w-full">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {[t('common.type') || 'Tur', t('common.amount') || 'Summa', t('admin.dict.comment') || 'Izoh', t('finance.source') || 'Manba', t('common.date') || 'Sana'].map(h => (
                      <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {transactions.map(t => (
                    <tr key={t.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                          t.type === 'income' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
                        }`}>
                          {t.type === 'income'
                            ? <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 11l5-5m0 0l5 5m-5-5v12" /></svg>
                            : <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 13l-5 5m0 0l-5-5m5 5V6" /></svg>}
                          {t.type === 'income' ? (t('finance.income') || 'Kirim') : (t('finance.expense') || 'Chiqim')}
                        </span>
                      </td>
                      <td className={`px-6 py-4 text-sm font-semibold ${t.type === 'income' ? 'text-emerald-600' : 'text-red-500'}`}>
                        {fmt(t.amount, t)}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">{t.description || '—'}</td>
                      <td className="px-6 py-4 text-sm text-slate-400">{t.reference_type || '—'}</td>
                      <td className="px-6 py-4 text-sm text-slate-400">{new Date(t.created_at).toLocaleDateString('uz-UZ')}</td>
                    </tr>
                  ))}
                  {transactions.length === 0 && (
                    <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-slate-400">{t('finance.noTransactions') || 'Tranzaksiyalar topilmadi'}</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* ── Customer Debts Tab ── */}
        {activeTab === 'customer-debts' && (
          <div>
            {/* Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('finance.customerDebts') || 'Debitor qarzdorlik — Mijozlar'}</span>
              <div className="flex items-center gap-2">
                <input
                  value={debtSearch} onChange={e => setDebtSearch(e.target.value)}
                  placeholder={t('finance.searchDebt') || "Ism yoki telefon..."}
                  className="px-3 py-2 text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-300 w-52"
                />
                <button
                  onClick={() => {
                    if (!customerDebts?.items) return;
                    const filtered = customerDebts.items.filter(c =>
                      !debtSearch || c.name.toLowerCase().includes(debtSearch.toLowerCase()) || (c.phone||'').includes(debtSearch)
                    );
                    const ws = XLSX.utils.json_to_sheet(filtered.map(c => ({
                      'Mijoz': c.name,
                      'Telefon': c.phone || '',
                      "Qarz (so'm)": c.debt_balance,
                      'Muddat': c.earliest_due_date || '',
                      'Holat': c.overdue ? 'Muddati o\'tgan' : 'Faol',
                    })));
                    const wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, 'Debitorlar');
                    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `debitorlar_${today()}.xlsx`);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Excel
                </button>
              </div>
            </div>
            {loading ? <Spinner /> : customerDebts ? (
              <>
                {/* Summary bar */}
                <div className="px-6 py-3 border-b border-slate-100 bg-amber-50 flex flex-wrap gap-4 items-center">
                  <span className="text-sm text-slate-600">{t('finance.totalDebt') || 'Jami qarz:'} <strong className="text-amber-700">{fmt(customerDebts.total_debt, t)}</strong></span>
                  <span className="text-sm text-slate-500">{customerDebts.count} ta mijoz</span>
                  {customerDebts.overdue_count > 0 && (
                    <span className="text-sm font-semibold text-red-600 bg-red-50 px-2 py-0.5 rounded-lg">
                      ⚠ {customerDebts.overdue_count} ta muddati o'tgan
                    </span>
                  )}
                </div>
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('nav.clients') || 'Mijoz', t('settings.phone') || 'Telefon', (t('common.debt')||'Qarz') + ' (' + (t('common.sum')||"so'm") + ')', t('common.deadline') || 'Muddat', t('common.status') || 'Holat', t('common.action') || 'Amal'].map(h => (
                        <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {customerDebts.items
                      .filter(c => !debtSearch || c.name.toLowerCase().includes(debtSearch.toLowerCase()) || (c.phone||'').includes(debtSearch))
                      .map(c => (
                        <tr key={c.id} className={`transition-colors ${c.overdue ? 'bg-red-50/50 hover:bg-red-50' : 'hover:bg-slate-50'}`}>
                          <td className="px-6 py-4 text-sm font-semibold text-slate-800">{c.name}</td>
                          <td className="px-6 py-4 text-sm text-slate-500">{c.phone || '—'}</td>
                          <td className="px-6 py-4 text-sm font-bold text-amber-600">{fmt(c.debt_balance, t)}</td>
                          <td className="px-6 py-4 text-sm text-slate-500">{c.earliest_due_date || '—'}</td>
                          <td className="px-6 py-4">
                            {c.overdue
                              ? <span className="text-xs font-semibold text-red-600 bg-red-100 px-2 py-1 rounded-lg">Muddati o'tgan</span>
                              : c.earliest_due_date
                                ? <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-1 rounded-lg">Kutilmoqda</span>
                                : <span className="text-xs text-slate-400">—</span>
                            }
                          </td>
                          <td className="px-6 py-4">
                            <button
                              onClick={() => setPayModal({ type: 'customer', id: c.id, name: c.name, balance: c.debt_balance })}
                              className="px-3 py-1.5 text-xs font-semibold bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-lg transition-colors">
                              To'lash
                            </button>
                          </td>
                        </tr>
                    ))}
                    {customerDebts.items.filter(c => !debtSearch || c.name.toLowerCase().includes(debtSearch.toLowerCase()) || (c.phone||'').includes(debtSearch)).length === 0 && (
                      <tr><td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400">
                        {debtSearch ? (t('common.noResult') || 'Natija topilmadi') : (t('finance.noDebtors') || "Debitorlar yo'q!")}
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </>
            ) : null}
          </div>
        )}

        {/* ── Supplier Debts Tab ── */}
        {activeTab === 'supplier-debts' && (
          <div>
            <div className="px-6 py-4 border-b border-slate-50">
              <span className="text-sm font-semibold text-slate-700">{t('finance.supplierDebts') || 'Kreditor qarzdorlik — Supplierlar'}</span>
            </div>
            {loading ? <Spinner /> : supplierDebts ? (
              <>
                <div className="px-6 py-3 border-b border-slate-100 bg-red-50 flex gap-4">
                  <span className="text-sm text-slate-600">{t('finance.totalDebt') || 'Jami qarz:'} <strong className="text-red-600">{fmt(supplierDebts.total_debt, t)}</strong></span>
                  <span className="text-sm text-slate-500">({supplierDebts.count} ta supplier)</span>
                </div>
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('nav.suppliers') || 'Ta\'minotchi', t('settings.phone') || 'Telefon', t('finance.debtBalance') || 'Qarz balansi', t('finance.paymentTerms') || "To'lov muddati", t('common.action') || 'Amal'].map(h => (
                        <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {supplierDebts.items.map(s => (
                      <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-6 py-4 text-sm font-semibold text-slate-800">{s.name}</td>
                        <td className="px-6 py-4 text-sm text-slate-500">{s.phone || '—'}</td>
                        <td className="px-6 py-4 text-sm font-bold text-red-600">{fmt(s.debt_balance)}</td>
                        <td className="px-6 py-4 text-sm text-slate-500">{s.payment_terms} kun</td>
                        <td className="px-6 py-4">
                          <button
                            onClick={() => setPayModal({ type: 'supplier', id: s.id, name: s.name, balance: s.debt_balance })}
                            className="px-3 py-1.5 text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg transition-colors">
                            To'lash
                          </button>
                        </td>
                      </tr>
                    ))}
                    {supplierDebts.items.length === 0 && (
                      <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-emerald-600">{t('finance.noCreditors') || "Kreditorlar yo'q!"}</td></tr>
                    )}
                  </tbody>
                </table>
              </>
            ) : null}
          </div>
        )}

        {/* ── P&L Tab ── */}
        {activeTab === 'pl' && (
          <div>
            <div className="flex flex-wrap items-end gap-3 px-6 py-4 border-b border-slate-50">
              <span className="text-sm font-semibold text-slate-700 self-center mr-2">{t('finance.pl') || 'Foyda va Zarar (P&L)'}</span>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">{t('common.from') || 'Dan'}</label>
                <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">{t('common.to') || 'Gacha'}</label>
                <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                  className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <button onClick={loadTab}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl transition-colors">
                {t('finance.plCalc') || 'Hisoblash'}
              </button>
            </div>
            {loading ? <Spinner /> : plData ? (
              <div className="p-6 max-w-2xl">
                <p className="text-sm text-slate-500 mb-5">
                  {t('finance.period') || 'Davr:'} <strong>{plData.period?.from}</strong> — <strong>{plData.period?.to}</strong>
                </p>
                <div className="space-y-2">
                  {[
                    { label: t('finance.revenue') || 'Daromad (sotuv)', value: plData.revenue, cls: 'text-slate-800', pct: 100, bg: 'bg-slate-50' },
                    { label: t('finance.cogs') || 'Tannarx (COGS)', value: plData.cogs, neg: true, cls: 'text-red-500', pct: plData.revenue ? plData.cogs / plData.revenue * 100 : 0, bg: '' },
                    { label: t('finance.grossProfit') || 'Brutto foyda', value: plData.gross_profit, cls: 'font-bold text-indigo-600', pct: plData.gross_margin_pct, bg: 'bg-indigo-50' },
                    { label: t('finance.totalExpenses') || 'Jami xarajatlar', value: plData.expenses?.total, neg: true, cls: 'text-red-500', pct: plData.revenue ? plData.expenses?.total / plData.revenue * 100 : 0, bg: '' },
                    { label: t('finance.netProfit') || 'Net foyda', value: plData.net_profit, cls: `font-bold ${plData.net_profit >= 0 ? 'text-emerald-600' : 'text-red-600'}`, pct: plData.net_margin_pct, bg: plData.net_profit >= 0 ? 'bg-emerald-50' : 'bg-red-50' },
                  ].map(row => (
                    <div key={row.label} className={`flex items-center justify-between p-3 rounded-xl ${row.bg || 'border border-slate-100'}`}>
                      <span className={`text-sm ${row.cls}`}>{row.label}</span>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-400">{Number(Math.abs(row.pct || 0)).toFixed(1)}%</span>
                        <span className={`text-sm font-semibold min-w-36 text-right ${row.cls}`}>
                          {row.neg && Number(row.value) > 0 ? '-' : ''}{fmt(Math.abs(Number(row.value) || 0), t)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                {plData.expenses?.by_category?.length > 0 && (
                  <div className="mt-6">
                    <p className="text-sm font-semibold text-slate-600 mb-3">{t('finance.expenseByCategory') || "Xarajatlar kategoriya bo'yicha:"}</p>
                    <div className="space-y-1.5">
                      {plData.expenses.by_category.map(c => (
                        <div key={c.name} className="flex items-center justify-between text-sm px-3 py-2 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-600">{c.name}</span>
                          <span className="font-medium text-red-500">{fmt(c.total, t)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : <div className="py-12 text-center text-sm text-slate-400">{t('finance.selectPeriod') || 'Davr tanlang va hisoblang'}</div>}
          </div>
        )}
      </div>

      {/* ── Qarz to'lash modali ── */}
      {payModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4">
            <h3 className="text-base font-bold text-slate-800 mb-1">{t('customer.payDebt')}</h3>
            <p className="text-sm text-slate-500 mb-4">
              {payModal.name} — {t('finance.currentDebt') || 'joriy qarz'}: <strong className="text-amber-600">{fmt(payModal.balance, t)}</strong>
            </p>
            <div className="mb-4">
              <label className="block text-xs font-medium text-slate-600 mb-1.5">{t('finance.paymentAmount') || "To'lov summasi"} ({t('common.sum') || "so'm"})</label>
              <input type="number" placeholder="0" max={payModal.balance}
                className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={payAmount} onChange={e => setPayAmount(e.target.value)} />
            </div>
            <div className="flex gap-2">
              <button onClick={handlePay} disabled={paying || !payAmount}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
                {paying ? t('common.saving') : t('customer.payDebt')}
              </button>
              <button onClick={() => { setPayModal(null); setPayAmount(''); }}
                className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-xl transition-colors">
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
