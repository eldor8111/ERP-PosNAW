import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

const emptyForm = { name: '', phone: '', debt_limit: '', loyalty_points: 0, card_number: '', cashback_percent: 0 };

const TIERS = {
  Gold:     { label: 'Gold',     cls: 'bg-amber-100 text-amber-700' },
  Silver:   { label: 'Silver',   cls: 'bg-slate-200 text-slate-700' },
  Bronze:   { label: 'Bronze',   cls: 'bg-orange-100 text-orange-700' },
  Standard: { label: 'Standard', cls: 'bg-slate-100 text-slate-500' },
};

function tierOf(pts) {
  if (pts >= 10000) return 'Gold';
  if (pts >= 5000) return 'Silver';
  if (pts >= 1000) return 'Bronze';
  return 'Standard';
}

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const Avatar = ({ name, size = 'sm' }) => {
  const sizes = { sm: 'w-8 h-8 text-sm', lg: 'w-12 h-12 text-lg' };
  const colors = ['bg-indigo-100 text-indigo-600', 'bg-emerald-100 text-emerald-600', 'bg-violet-100 text-violet-600', 'bg-rose-100 text-rose-600', 'bg-amber-100 text-amber-600'];
  const color = colors[(name?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`${sizes[size]} ${color} rounded-full flex items-center justify-center font-bold shrink-0`}>
      {name?.charAt(0).toUpperCase()}
    </div>
  );
};

export default function Customers() {
  const navigate = useNavigate();
  const { t } = useLang();
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [payAmount, setPayAmount] = useState('');
  const [pointsDelta, setPointsDelta] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // --- Import States ---
  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importRows, setImportRows] = useState([]);
  const [colMap, setColMap] = useState({});
  const [importLoading, setImportLoading] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState('');
  const [importPage, setImportPage] = useState(1);
  const [skipRows, setSkipRows] = useState(1);
  const [allowUpdate, setAllowUpdate] = useState(false);

  const IMPORT_FIELDS = [
    { key: '',                label: '— Tanlang —' },
    { key: 'Ism',             label: 'Mijoz ismi *' },
    { key: 'Telefon',         label: 'Telefon raqam' },
    { key: 'Qarz',            label: 'Joriy qarz' },
    { key: 'Kredit limit',    label: 'Kredit limiti' },
    { key: 'Sodiqlik ballari',label: 'Sodiqlik ballari' },
    { key: 'Karta raqami',    label: 'Karta raqami' },
    { key: 'Cashback',        label: 'Keshbek (%)' },
    { key: 'Bonus',           label: 'Bonus balansi' },
    { key: '__SKIP__',        label: '— O\'tkazib yuborish —' },
  ];

  const resetImport = () => {
    setImportOpen(false); setImportRows([]); setImportFile(null);
    setImportResult(null); setImportError(''); setColMap({}); setImportPage(1);
    setSkipRows(1); setAllowUpdate(false); setImportProgress(0);
  };
  const openImport = () => { resetImport(); setImportOpen(true); };

  const autoMap = (rows) => {
    if (!rows.length) return;
    const cols = Object.keys(rows[0]);
    const map = {};
    cols.forEach(col => {
      const lc = col.trim().toLowerCase();
      const found = IMPORT_FIELDS.find(f => f.label.toLowerCase().includes(lc) || f.key.toLowerCase() === lc);
      map[col] = found?.key && found.key !== '__SKIP__' ? found.key : '';
    });
    setColMap(map);
  };

  const parseExcel = (file) => {
    setImportFile(file); setImportResult(null); setImportError(''); setImportPage(1);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { defval: '', raw: false });
        setImportRows(rows);
        autoMap(rows);
      } catch {
        setImportError('Fayl o\'qishda xatolik. Iltimos .xlsx formatdagi faylni tanlang.');
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const buildPayload = () => {
    const actualRows = skipRows > 0 ? importRows.slice(skipRows - 1) : importRows;
    return actualRows.map((row, idx) => {
      const obj = {};
      Object.entries(colMap).forEach(([excelCol, fieldKey]) => {
        if (fieldKey && fieldKey !== '__SKIP__') {
          obj[fieldKey] = row[excelCol];
        }
      });
      obj.__row_index = (skipRows > 0 ? skipRows - 1 : 0) + idx + 2;
      return obj;
    }).filter(r => r['Ism'] || r['Telefon'] || r['Karta raqami']);
  };

  const downloadTemplate = () => {
    const ws = XLSX.utils.json_to_sheet([{
      'Ism': 'Javohir Toshmatov', 'Telefon': '+998901234567',
      'Qarz': 0, 'Kredit limit': 1000000, 'Sodiqlik ballari': 100,
      'Karta raqami': '8888 1234 5678 9012', 'Cashback': 3.5, 'Bonus': 0
    }]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Mijozlar');
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), 'mijozlar_shablon.xlsx');
  };

  const handleImport = async () => {
    const payload = buildPayload();
    if (!payload.length) return;
    setImportLoading(true); setImportResult(null); setImportError('');
    try {
      let totC = 0, totU = 0, totS = 0;
      let errs = [];
      const CHUNK_SIZE = 1000;
      
      for (let i = 0; i < payload.length; i += CHUNK_SIZE) {
        const chunk = payload.slice(i, i + CHUNK_SIZE);
        const { data } = await api.post(`/customers/bulk-import?allow_update=${allowUpdate}`, chunk);
        totC += data.created || 0;
        totU += data.updated || 0;
        totS += data.skipped || 0;
        if (data.errors) errs = [...errs, ...data.errors];
        setImportProgress(Math.round(((i + chunk.length) / payload.length) * 100));
      }
      
      setImportResult({ created: totC, updated: totU, skipped: totS, errors: errs });
      if (totC > 0 || totU > 0) load();
    } catch (err) {
      setImportError(err.response?.data?.detail || 'Server xatosi');
    } finally { setImportLoading(false); }
  };

  const load = useCallback((q = search) => {
    api.get(`/customers${q ? '?search=' + encodeURIComponent(q) : ''}`)
      .then(r => setCustomers(r.data))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setTimeout(() => load(search), 400);
    return () => clearTimeout(t);
  }, [search, load]);

  const generateCard = () => {
    return '8888 ' + Math.floor(1000 + Math.random() * 9000) + ' ' + Math.floor(1000 + Math.random() * 9000) + ' ' + Math.floor(1000 + Math.random() * 9000);
  };

  const openAdd = () => { setForm({ ...emptyForm, card_number: generateCard() }); setError(''); setModal('add'); };
  const openEdit = (c) => {
    setForm({ name: c.name, phone: c.phone || '', debt_limit: c.debt_limit || 0, loyalty_points: c.loyalty_points || 0, card_number: c.card_number || '', cashback_percent: c.cashback_percent || 0 });
    setSelected(c); setError(''); setModal('edit');
  };
  const openPay = (c) => { setSelected(c); setPayAmount(''); setError(''); setModal('pay'); };
  const openPoints = (c) => { setSelected(c); setPointsDelta(''); setError(''); setModal('points'); };
  const openHistory = async (c) => {
    setSelected(c); setModal('history'); setError(''); setLoadingHistory(true); setHistory([]);
    try {
      const { data } = await api.get(`/customers/${c.id}/history`);
      setHistory(data);
    } catch {
      setError("Tarixni yuklashda xatolik yuz berdi");
    } finally {
      setLoadingHistory(false);
    }
  };
  const closeModal = () => { setModal(null); setSelected(null); setError(''); setHistory([]); };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload = { 
        name: form.name, 
        phone: form.phone || null, 
        debt_limit: form.debt_limit ? Number(form.debt_limit) : 0, 
        loyalty_points: form.loyalty_points ? Number(form.loyalty_points) : 0,
        card_number: form.card_number || null,
        cashback_percent: form.cashback_percent ? Number(form.cashback_percent) : 0
      };
      if (modal === 'add') await api.post('/customers', payload);
      else await api.put(`/customers/${selected.id}`, payload);
      closeModal(); load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuzaga keldi');
    } finally { setSaving(false); }
  };

  const handlePay = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await api.post(`/customers/${selected.id}/pay-debt`, { amount: Number(payAmount), reason: "To'lov" });
      closeModal(); load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuzaga keldi');
    } finally { setSaving(false); }
  };

  const handleAdjustPoints = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await api.post(`/customers/${selected.id}/adjust-points`, {
        delta: Number(pointsDelta),
        reason: 'Manual adjustment',
      });
      closeModal(); load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  const deleteCustomer = async (id) => {
    if (!confirm(t('customer.deleteConfirm'))) return;
    await api.delete(`/customers/${id}`);
    load();
  };

  const totalDebt = customers.reduce((s, c) => s + Number(c.debt_balance || 0), 0);
  const debtors = customers.filter(c => Number(c.debt_balance) > 0).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('customer.title')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{t('customer.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const ws = XLSX.utils.json_to_sheet(customers.map(c => ({
                'Ism': c.name,
                'Telefon': c.phone || '—',
                'Qarz (so\'m)': Number(c.debt_balance || 0),
                'Kredit limiti': Number(c.debt_limit || 0),
                'Bonus ball': c.loyalty_points || 0,
                'Keshbek %': c.cashback_percent || 0,
              })));
              const wb = XLSX.utils.book_new();
              XLSX.utils.book_append_sheet(wb, ws, 'Mijozlar');
              saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `mijozlar_${new Date().toISOString().slice(0,10)}.xlsx`);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors border border-emerald-200"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            {t('customer.exportExcel')}
          </button>
          <button
            onClick={openImport}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-sm font-semibold rounded-xl transition-colors border border-indigo-200"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            {t('customer.importFromExcel')}
          </button>
          <button
            onClick={openAdd}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
            </svg>
            {t('customer.newCustomer')}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 100 8 4 4 0 000-8zm8 2a2 2 0 110 4 2 2 0 010-4z" />
            </svg>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('customer.totalCustomers')}</div>
            <div className="text-xl font-bold text-indigo-600 mt-0.5">{customers.length.toLocaleString()}</div>
          </div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('customer.totalDebt')}</div>
            <div className="text-xl font-bold text-red-500 mt-0.5">{fmt(totalDebt)} {t('common.sum')}</div>
          </div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('customer.totalDebtors')}</div>
            <div className="text-xl font-bold text-amber-600 mt-0.5">{debtors}</div>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          className="w-full pl-11 pr-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white shadow-sm"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('customer.searchPlaceholder')}
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {[t('common.name'), t('common.phone'), t('customer.debtBalance'), t('customer.creditLimit'), `${t('customer.bonusBalance')} / ${t('customer.cashback')}`, t('common.actions')].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {customers.map(c => (
              <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4">
                  <button
                    onClick={() => navigate(`/admin/customers/${c.id}`)}
                    className="flex items-center gap-3 hover:opacity-75 transition-opacity text-left"
                  >
                    <Avatar name={c.name} />
                    <span className="text-sm font-medium text-indigo-700 hover:underline">{c.name}</span>
                  </button>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{c.phone || '—'}</td>
                <td className="px-6 py-4">
                  <span className={`text-sm font-semibold ${Number(c.debt_balance) > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                    {fmt(c.debt_balance)} so'm
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{fmt(c.debt_limit)} so'm</td>
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-1">
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-50 text-amber-600 text-xs font-semibold rounded-lg w-fit">
                      <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      {fmt(c.bonus_balance || 0)} so'm
                    </span>
                    {(c.cashback_percent > 0) && (
                       <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit bg-indigo-100 text-indigo-700`}>
                         {Number(c.cashback_percent)}% keshbek
                       </span>
                    )}
                    {(c.loyalty_points > 0) && (
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${TIERS[tierOf(c.loyalty_points || 0)].cls}`}>
                        {TIERS[tierOf(c.loyalty_points || 0)].label} ({c.loyalty_points})
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-1">
                    {Number(c.debt_balance) > 0 && (
                      <button
                        onClick={() => openPay(c)}
                        title={t('customer.payDebt')}
                        className="p-1.5 text-emerald-500 hover:bg-emerald-50 rounded-lg transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                        </svg>
                      </button>
                    )}
                    <button
                      onClick={() => openPoints(c)}
                      title={t('customer.adjustPoints')}
                      className="p-1.5 text-amber-500 hover:bg-amber-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => openHistory(c)}
                      title={t('customer.history')}
                      className="p-1.5 text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => openEdit(c)}
                      title={t('common.edit')}
                      className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => deleteCustomer(c.id)}
                      title={t('common.delete')}
                      className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {customers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-16 text-center">
                  <div className="flex flex-col items-center gap-2 text-slate-400">
                    <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <span className="text-sm">{search ? t('common.noData') : t('customer.noCustomers')}</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {customers.length > 0 && (
          <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500 bg-slate-50">
            <span>Jami <strong className="text-slate-700">{customers.length}</strong> ta mijoz</span>
            <span>Umumiy qarz: <strong className="text-red-500">{fmt(totalDebt)} so'm</strong></span>
          </div>
        )}
      </div>

      {/* ── ADD / EDIT MODAL ────────────────────────────────── */}
      {(modal === 'add' || modal === 'edit') && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">
                {modal === 'add' ? t('customer.addCustomer') : t('customer.editCustomer')}
              </h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleSave} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Ism va familiya <span className="text-red-500">*</span></label>
                  <input
                    required
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Javohir Toshmatov"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Telefon raqam</label>
                  <input
                    value={form.phone}
                    onChange={e => setForm({ ...form, phone: e.target.value })}
                    placeholder="+998 90 123 45 67"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Kredit limiti (so'm)</label>
                  <input
                    type="number" min="0"
                    value={form.debt_limit}
                    onChange={e => setForm({ ...form, debt_limit: e.target.value })}
                    placeholder="1000000"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Boshlang'ich bonus ballari</label>
                  <input
                    type="number" min="0"
                    value={form.loyalty_points}
                    onChange={e => setForm({ ...form, loyalty_points: e.target.value })}
                    placeholder="0"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-600">Karta raqami</label>
                    <button 
                      type="button" 
                      onClick={() => setForm({ ...form, card_number: generateCard() })}
                      className="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
                    >
                      Generatsiya qilish
                    </button>
                  </div>
                  <input
                    value={form.card_number}
                    onChange={e => setForm({ ...form, card_number: e.target.value })}
                    placeholder="Masalan: 8888 1234 5678 9012"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Keshbek foizi (%)</label>
                  <input
                    type="number" min="0" max="100" step="0.1"
                    value={form.cashback_percent}
                    onChange={e => setForm({ ...form, cashback_percent: e.target.value })}
                    placeholder="Misol: 3.5"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={closeModal} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                  {t('common.cancel')}
                </button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? t('common.saving') : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── PAY DEBT MODAL ──────────────────────────────────── */}
      {modal === 'pay' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('customer.payDebt')}</h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-5">
              <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-xl">
                <Avatar name={selected.name} size="lg" />
                <div>
                  <div className="font-bold text-slate-800">{selected.name}</div>
                  <div className="text-sm text-slate-500">{selected.phone}</div>
                  <div className="text-sm font-bold text-red-500 mt-0.5">Joriy qarz: {fmt(selected.debt_balance)} so'm</div>
                </div>
              </div>
              <form onSubmit={handlePay} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">To'lov miqdori (so'm) <span className="text-red-500">*</span></label>
                  <input
                    type="number" min="1" max={selected.debt_balance} required autoFocus
                    value={payAmount}
                    onChange={e => setPayAmount(e.target.value)}
                    placeholder={`Max: ${fmt(selected.debt_balance)} so'm`}
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
                <div className="flex gap-3">
                  <button type="button" onClick={closeModal} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                    {t('common.cancel')}
                  </button>
                  <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                    {saving ? '...' : t('common.confirm')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── LOYALTY POINTS MODAL ─────────────────────────────── */}
      {modal === 'points' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('customer.adjustPoints')}</h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-5">
              <div className="flex items-center gap-3 p-4 bg-amber-50 rounded-xl">
                <Avatar name={selected.name} size="lg" />
                <div>
                  <div className="font-bold text-slate-800">{selected.name}</div>
                  <div className="text-sm text-slate-500">{selected.phone || '—'}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-sm font-bold text-amber-600">Ballar: {selected.loyalty_points || 0}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${TIERS[tierOf(selected.loyalty_points || 0)].cls}`}>
                      {TIERS[tierOf(selected.loyalty_points || 0)].label}
                    </span>
                  </div>
                </div>
              </div>
              <form onSubmit={handleAdjustPoints} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                    O'zgarish miqdori <span className="text-slate-400 font-normal">(musbat = qo'shish, manfiy = ayirish)</span>
                  </label>
                  <input
                    type="number" required autoFocus
                    value={pointsDelta}
                    onChange={e => setPointsDelta(e.target.value)}
                    placeholder="Masalan: 500 yoki -200"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                  {pointsDelta && (
                    <p className="text-xs text-slate-500 mt-1.5">
                      Natija: <strong className="text-slate-700">{Math.max(0, (selected.loyalty_points || 0) + Number(pointsDelta))} ball</strong>
                      {' → '}
                      <span className={`font-semibold ${TIERS[tierOf(Math.max(0, (selected.loyalty_points || 0) + Number(pointsDelta)))].cls.replace('bg-', 'text-').split(' ')[0]}`}>
                        {TIERS[tierOf(Math.max(0, (selected.loyalty_points || 0) + Number(pointsDelta)))].label}
                      </span>
                    </p>
                  )}
                </div>
                {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
                <div className="flex gap-3">
                  <button type="button" onClick={closeModal} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                    {t('common.cancel')}
                  </button>
                  <button type="submit" disabled={saving || !pointsDelta} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                    {saving ? '...' : t('common.save')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── HISTORY MODAL ────────────────────────────────────── */}
      {modal === 'history' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={closeModal}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">{t('customer.history')}</h3>
              <button onClick={closeModal} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50">
              <div className="flex items-center gap-3 p-4 bg-white border border-slate-100 rounded-xl mb-6 shadow-sm">
                <Avatar name={selected.name} size="lg" />
                <div>
                  <div className="font-bold text-slate-800">{selected.name}</div>
                  <div className="text-sm text-slate-500">{selected.phone || 'Telefon raqam yo\'q'}</div>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Joriy qarz</div>
                  <div className={`text-lg font-bold ${Number(selected.debt_balance) > 0 ? 'text-red-500' : 'text-slate-700'}`}>
                    {fmt(selected.debt_balance)} so'm
                  </div>
                </div>
              </div>

              {loadingHistory ? (
                <div className="py-12 flex justify-center">
                  <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
                </div>
              ) : error ? (
                <div className="p-4 bg-red-50 text-red-600 rounded-xl text-center text-sm">{error}</div>
              ) : history.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <svg className="w-12 h-12 mx-auto mb-3 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Tarix ma'lumotlari topilmadi
                </div>
              ) : (
                <div className="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-slate-200">
                  {history.map((item, idx) => {
                    const isSale = item.type === 'sale';
                    const dateObj = new Date(item.date);
                    return (
                      <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                        <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-white bg-slate-50 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 shadow-sm">
                          {isSale ? (
                            <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                            </svg>
                          )}
                        </div>
                        <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border border-slate-100 bg-white shadow-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded-md ${isSale ? 'bg-indigo-50 text-indigo-600' : 'bg-emerald-50 text-emerald-600'}`}>
                              {isSale ? 'Xarid' : "To'lov"}
                            </span>
                            <span className="text-xs text-slate-400 font-medium">
                              {dateObj.toLocaleDateString('uz-UZ')} {dateObj.toLocaleTimeString('uz-UZ', {hour: '2-digit', minute:'2-digit'})}
                            </span>
                          </div>
                          <div className="mt-2 text-slate-700">
                            {isSale ? (
                              <div className="space-y-1 text-sm">
                                <div className="flex justify-between">
                                  <span className="text-slate-500">Jami qiy.:</span>
                                  <span className="font-semibold">{fmt(item.amount)} so'm</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-slate-500">To'landi:</span>
                                  <span className="font-medium text-emerald-600">{fmt(item.paid)} so'm</span>
                                </div>
                                {item.debt > 0 && (
                                  <div className="flex justify-between border-t border-slate-100 pt-1 mt-1">
                                    <span className="text-slate-500">Qarzga:</span>
                                    <span className="font-bold text-red-500">{fmt(item.debt)} so'm</span>
                                  </div>
                                )}
                              </div>
                            ) : (
                              <div className="flex justify-between items-center text-sm">
                                <span className="text-slate-500">To'langan miqdor:</span>
                                <span className="font-bold text-emerald-600 text-base">+{fmt(item.amount)} so'm</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-slate-100 bg-white rounded-b-2xl shrink-0">
              <button onClick={closeModal} className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl transition-colors">
                {t('common.close')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── IMPORT MODAL (Full screen) ────────────── */}
      {importOpen && (
        <div className="fixed inset-0 z-50 bg-slate-50 flex flex-col">
          {/* Top Bar */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shadow-sm shrink-0">
            <div className="flex items-center gap-3">
              <button onClick={resetImport} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
              <h2 className="text-xl font-bold text-slate-800">Mijozlarni Exceldan yuklash</h2>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={downloadTemplate} className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-lg transition-colors">
                Shablon
              </button>
              <label className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-lg border border-slate-200 cursor-pointer">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                Fayl tanlash
                <input type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { if (e.target.files[0]) parseExcel(e.target.files[0]); }} />
              </label>
              <button
                onClick={handleImport}
                disabled={!buildPayload().length || importLoading || !(Object.values(colMap).includes('Ism') || (allowUpdate && (Object.values(colMap).includes('Telefon') || Object.values(colMap).includes('Karta raqami'))))}
                className="inline-flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-colors border border-transparent"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
                {importLoading ? `Saqlanmoqda... ${importProgress}%` : 'Saqlash'}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto flex flex-col">
            {!importFile ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                <svg className="w-16 h-16 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-lg font-medium">Boshlash uchun Excel fayl yuklang</p>
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Options Toolbar */}
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shadow-sm bg-white shrink-0">
                  <div className="flex items-center gap-6">
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${allowUpdate ? 'bg-indigo-600' : 'bg-slate-200'}`}>
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${allowUpdate ? 'translate-x-6' : 'translate-x-1'}`} />
                      </div>
                      <span className="text-sm font-semibold text-slate-700 group-hover:text-indigo-600 transition-colors">Mijozlarni tahrirlash</span>
                    </label>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-3 bg-white border border-slate-200 px-3 py-1.5 rounded-xl">
                      <span className="text-sm font-medium text-slate-600">O'tkazib yuborish (qator):</span>
                      <button onClick={() => setSkipRows(Math.max(0, skipRows - 1))} className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors font-bold text-slate-600">−</button>
                      <span className="text-sm font-bold w-6 text-center">{skipRows}</span>
                      <button onClick={() => setSkipRows(skipRows + 1)} className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors font-bold text-slate-600">+</button>
                    </div>
                  </div>
                </div>

                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="px-6 py-2.5 flex items-center justify-between border-b border-slate-100 shrink-0">
                    <span className="text-sm text-slate-600 font-medium">
                      Yuklanayotgan mijozlar soni: <strong>{buildPayload().length} ta</strong>
                    </span>
                    {!(Object.values(colMap).includes('Ism') || (allowUpdate && (Object.values(colMap).includes('Telefon') || Object.values(colMap).includes('Karta raqami')))) && (
                      <span className="text-sm font-semibold text-red-500">
                        * {allowUpdate ? 'Ism, Telefon yoki Karta raqami' : 'Ism'} ustunini tanlash majburiy
                      </span>
                    )}
                  </div>

                  <div className="flex-1 overflow-auto">
                    <table className="min-w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-slate-100">
                          <th className="px-3 py-2.5 text-left font-bold text-slate-500 border-b border-slate-200 text-sm">#</th>
                          {Object.keys(importRows[0] || {}).map(col => (
                            <th key={col} className="px-2 py-2 border-b border-slate-200 min-w-[160px]">
                              <select
                                value={colMap[col] || ''}
                                onChange={e => setColMap(m => ({ ...m, [col]: e.target.value }))}
                                className="w-full bg-white border border-slate-300 px-2 py-1.5 rounded-lg text-sm font-semibold text-slate-700 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                              >
                                {IMPORT_FIELDS.map(f => (
                                  <option key={f.key} value={f.key}>{f.label}</option>
                                ))}
                              </select>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {importRows.slice(0, importPage * 50).map((row, i) => {
                          const skipped = i < skipRows;
                          return (
                            <tr key={i} className={`hover:bg-slate-50/50 ${skipped ? 'opacity-40 bg-slate-50' : ''}`}>
                              <td className="px-3 py-2 text-slate-400 font-medium border-r border-slate-100 bg-slate-50">{i + 1} {skipped && <span className="text-[10px] text-amber-500 block leading-none">Skip</span>}</td>
                              {Object.keys(importRows[0] || {}).map((col, j) => (
                                <td key={j} className="px-3 py-2 border-r border-slate-100 text-slate-700 truncate max-w-[200px]" title={row[col]}>
                                  {row[col] || <span className="text-slate-300">—</span>}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {importRows.length > importPage * 50 && (
                      <div className="py-4 text-center">
                        <button onClick={() => setImportPage(p => p + 1)} className="px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">
                          Yana ko'rsatish
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Result panel */}
            {importResult && (
              <div className="px-6 py-4 bg-white border-t border-slate-100">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="px-5 py-3 bg-emerald-50 rounded-xl text-center min-w-[120px]">
                    <div className="text-3xl font-black text-emerald-600">{importResult.created}</div>
                    <div className="text-sm font-semibold text-emerald-500">Yangi qo'shildi</div>
                  </div>
                  {importResult.updated > 0 && (
                    <div className="px-5 py-3 bg-indigo-50 rounded-xl text-center min-w-[120px]">
                      <div className="text-3xl font-black text-indigo-600">{importResult.updated}</div>
                      <div className="text-sm font-semibold text-indigo-500">Yangilandi</div>
                    </div>
                  )}
                  <div className={`px-5 py-3 rounded-xl text-center min-w-[120px] ${importResult.skipped > 0 ? 'bg-amber-50' : 'bg-slate-50'}`}>
                    <div className={`text-3xl font-black ${importResult.skipped > 0 ? 'text-amber-600' : 'text-slate-400'}`}>{importResult.skipped}</div>
                    <div className={`text-sm font-semibold ${importResult.skipped > 0 ? 'text-amber-500' : 'text-slate-400'}`}>O'tkazib yuborildi</div>
                  </div>
                  <div className="flex-1 min-w-0">
                    {importResult.errors?.length > 0 && (
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {importResult.errors.map((e, i) => (
                          <div key={i} className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-100 rounded-lg text-sm">
                            <span className="font-bold text-amber-600 shrink-0">#{e.row}</span>
                            <span className="text-amber-700">{e.name && <span className="font-semibold">{e.name}: </span>}{e.error}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            {importError && (
              <div className="mx-6 mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{importError}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
