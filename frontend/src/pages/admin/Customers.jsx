import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';
import { ChevronDown, CreditCard, Users, ListOrdered, ChevronsUpDown, CheckIcon, AlertTriangle, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, EllipsisVertical, History, Star, Banknote, Layers, CircleCheck, Plus, Minus } from 'lucide-react';
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/react';

const emptyForm = { name: '', phone: '', debt_limit: '', loyalty_points: 0, card_number: '', cashback_percent: 0, debts: [{ amount: '', currency: 'UZS' }] };

const TIERS = {
  Gold: { label: 'Gold', cls: 'bg-amber-100 text-amber-700' },
  Silver: { label: 'Silver', cls: 'bg-slate-200 text-slate-700' },
  Bronze: { label: 'Bronze', cls: 'bg-orange-100 text-orange-700' },
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

const inputCls = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';
const ic = 'border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';


function CustSearch({ customers, value, onChange, onAfterSelect }) {
  const { t } = useLang();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = customers.find(c => c.id === value);
  const filtered = q.trim() ? customers.filter(c => matchesSearch(c.name, q) || (c.phone && c.phone.includes(q))).slice(0, 12) : customers.slice(0, 12);
  useEffect(() => { const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); }; document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h); }, []);
  const select = (c) => { onChange(c ? c.id : ''); setQ(''); setOpen(false); if (c) onAfterSelect?.(); };
  return (
    <div className="relative" ref={ref}>
      <div className="flex items-center border border-slate-200 rounded-lg bg-white overflow-hidden focus-within:ring-2 focus-within:ring-indigo-400">
        <input value={open ? q : (selected ? selected.name : '')} onChange={e => { setQ(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }} onFocus={() => setOpen(true)} placeholder="Mijoz: ism yoki telefon..." className="flex-1 px-3 py-1.5 text-sm outline-none bg-transparent min-w-0" />
        {selected && <button onClick={() => select(null)} className="px-2 text-slate-400 hover:text-red-400 text-lg leading-none">×</button>}
      </div>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-50 overflow-hidden max-h-64 overflow-y-auto">
          {filtered.length === 0 ? <div className="px-4 py-3 text-sm text-slate-400">Topilmadi</div> : filtered.map(c => (
            <button key={c.id} onMouseDown={() => select(c)} className="w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-50 last:border-0 flex items-center justify-between">
              <div><div className="text-sm font-medium text-slate-800">{c.name}</div>{c.phone && <div className="text-xs text-slate-400">{c.phone}</div>}</div>
              {c.debt_balance > 0 && <span className="text-xs text-red-500 font-medium ml-2">Qarz: {fmt(c.debt_balance)}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RowMenu({ onEdit, onDelete, onPay, onPoints, onHistory, hasDebt }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0, visible: false });
  const { t } = useLang();
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const openMenu = () => {
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setPos({ top: r.bottom + 4, right: window.innerWidth - r.right, visible: false });
    }
    setOpen(o => !o);
  };

  useLayoutEffect(() => {
    if (open && menuRef.current && btnRef.current) {
      const menuRect = menuRef.current.getBoundingClientRect();
      const btnRect = btnRef.current.getBoundingClientRect();
      if (menuRect.bottom > window.innerHeight - 8) {
        setPos({ top: btnRect.top - menuRect.height - 4, right: window.innerWidth - btnRect.right, visible: true });
      } else {
        setPos(p => ({ ...p, visible: true }));
      }
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target) && btnRef.current && !btnRef.current.contains(e.target))
        setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  return (
    <div className="relative">
      <button
        ref={btnRef}
        onClick={openMenu}
        className="w-8 lg:w-10 cursor-pointer h-8 lg:h-10 flex items-center justify-center rounded-md lg:rounded-xl text-indigo-600 hover:text-indigo-800 bg-indigo-50 transition-colors border border-indigo-100"
        title={t('common.actions')}>
        <EllipsisVertical className="w-4 h-4 lg:w-5 lg:h-5" />
      </button>
      {open && (
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: pos.top, right: pos.right, zIndex: 9999, opacity: pos.visible ? 1 : 0, pointerEvents: pos.visible ? 'auto' : 'none' }}
          className="bg-white border border-slate-200 rounded-xl shadow-xl py-1.5 min-w-[200px]"
        >
          {hasDebt && (
            <button onClick={() => { onPay(); setOpen(false); }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-emerald-600 hover:bg-emerald-50 transition-colors font-medium">
              <Banknote className="w-4 h-4" />
              {t('customer.payDebt')}
            </button>
          )}
          <button onClick={() => { onPoints(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-amber-600 hover:bg-amber-50 transition-colors font-medium">
            <Star className="w-4 h-4" />
            {t('customer.adjustPoints')}
          </button>
          <button onClick={() => { onHistory(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-blue-600 hover:bg-blue-50 transition-colors font-medium">
            <History className="w-4 h-4" />
            {t('customer.history')}
          </button>
          <div className="mx-3 my-1 border-t border-slate-100" />
          <button onClick={() => { onEdit(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors">
            <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            {t('common.edit')}
          </button>
          <button onClick={() => { onDelete(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-500 hover:bg-red-50 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            {t('common.delete')}
          </button>
        </div>
      )}
    </div>
  );
}

export function SotuvMijozlar({ totalAllDebt = 0 }) {
  const navigate = useNavigate();
  const { t } = useLang();
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [payAmount, setPayAmount] = useState('');
  const [payType, setPayType] = useState('cash');
  const [payWallet, setPayWallet] = useState('');
  const [payInfo, setPayInfo] = useState('');
  const [wallets, setWallets] = useState([]);
  const [pointsDelta, setPointsDelta] = useState('');
  const [totalRecords, setTotalRecords] = useState(0);
  const [limit, setLimit] = useState(() => Number(localStorage.getItem('customers_products_limit') || 50));
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

  const sortOptions = [
    { label: "Qarzi bo'yicha (kamayish tartibda)", sort_by: "debt_balance", sort_order: "desc" },
    { label: "Qarzi bo'yicha (o'sish tartibda)", sort_by: "debt_balance", sort_order: "asc" },
    { label: "Nomi bo'yicha (kamayish tartibda)", sort_by: "name", sort_order: "desc" },
    { label: "Nomi bo'yicha (o'sish tartibda)", sort_by: "name", sort_order: "asc" },
    { label: "Yaratilgan vaqti bo'yicha (kamayish tartibda)", sort_by: "id", sort_order: "desc" },
    { label: "Yaratilgan vaqti bo'yicha (o'sish tartibda)", sort_by: "id", sort_order: "asc" },
  ];

  const currentSort = sortOptions.find(o => o.sort_by === sortBy && o.sort_order === sortOrder) || sortOptions[3];

  const [filterAmount, setFilterAmount] = useState('');
  const [filterType, setFilterType] = useState('all'); // all, eq, lt, gt

  const filterOptions = [
    { label: "Barchasi", key: "all" },
    { label: "ga teng bo'lgan qarzlar", key: "eq" },
    { label: "dan kam bo'lgan qarzlar", key: "lt" },
    { label: "dan yuqori bo'lgan qarzlar", key: "gt" },
  ];

  const currentFilter = filterOptions.find(o => o.key === filterType) || filterOptions[0];

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
  const [currencies, setCurrencies] = useState([]);
  const [currencyType, setCurrencyType] = useState('UZS');

  const IMPORT_FIELDS = [
    { key: '', label: '— Tanlang —' },
    { key: 'Ism', label: 'Mijoz ismi *' },
    { key: 'Telefon', label: 'Telefon raqam' },
    { key: 'Qarz', label: 'Joriy qarz' },
    { key: 'Kredit limit', label: 'Kredit limiti' },
    { key: 'Sodiqlik ballari', label: 'Sodiqlik ballari' },
    { key: 'Karta raqami', label: 'Karta raqami' },
    { key: 'Cashback', label: 'Keshbek (%)' },
    { key: 'Bonus', label: 'Bonus balansi' },
    { key: '__SKIP__', label: '— O\'tkazib yuborish —' },
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
    const skip = (page - 1) * limit;
    let url = `/customers/paginated?limit=${limit}&skip=${skip}`;
    if (q) url += `&search=${encodeURIComponent(q)}`;
    if (sortBy) url += `&sort_by=${sortBy}`;
    if (sortOrder) url += `&sort_order=${sortOrder}`;

    if (filterAmount && filterType !== 'all') {
      if (filterType === 'eq') url += `&exact_debt=${filterAmount}`;
      else if (filterType === 'lt') url += `&max_debt=${filterAmount}`;
      else if (filterType === 'gt') url += `&min_debt=${filterAmount}`;
    }

    api.get(url)
      .then(r => {
        setCustomers(r.data.items);
        setTotalRecords(r.data.total);
      })
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, limit, sortBy, sortOrder, filterType, filterAmount]);

  useEffect(() => {
    load();
    api.get('/currencies').then((d => {
      setCurrencies(d.data)
    }))
    api.get('/finance/wallets').then(r => {
      setWallets(r.data);
      if (r.data.length > 0) setPayWallet(String(r.data[0].id));
    }).catch(() => { });
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [search, limit]);

  useEffect(() => {
    const t = setTimeout(() => load(search), 400);
    return () => clearTimeout(t);
  }, [search, load]);

  const generateCard = () => {
    return '8888 ' + Math.floor(1000 + Math.random() * 9000) + ' ' + Math.floor(1000 + Math.random() * 9000) + ' ' + Math.floor(1000 + Math.random() * 9000);
  };

  const openAdd = () => { setForm({ ...emptyForm, card_number: generateCard() }); setError(''); setModal('add'); };
  const openEdit = (c) => {
    let debts = [{ amount: '', currency: 'UZS' }];
    if (c.debt_balances && typeof c.debt_balances === 'object' && Object.keys(c.debt_balances).length > 0) {
      debts = Object.entries(c.debt_balances).map(([curr, amt]) => ({ amount: amt, currency: curr }));
    } else if (c.debt_balance > 0) {
      debts = [{ amount: c.debt_balance, currency: c.debt_currency || 'UZS' }];
    }
    setForm({
      name: c.name,
      phone: c.phone || '',
      debt_limit: c.debt_limit || 0,
      loyalty_points: c.loyalty_points || 0,
      card_number: c.card_number || '',
      cashback_percent: c.cashback_percent || 0,
      debts
    });
    setSelected(c); setError(''); setModal('edit');
  };
  const openPay = (c) => {
    setSelected(c);
    setPayInfo('');
    setPayDebtLength([{ id: Date.now(), payType: '', payAmount: '', currencyType: 'UZS' }]);
    if (wallets.length > 0) setPayWallet(String(wallets[0].id));
    setError('');
    setModal('pay');
  };
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
      const debtBalances = {};
      form.debts.forEach(d => {
        if (d.amount && !isNaN(Number(d.amount))) {
          const amt = Number(d.amount);
          debtBalances[d.currency] = (debtBalances[d.currency] || 0) + amt;
        }
      });

      let totalInUZS = 0;
      Object.entries(debtBalances).forEach(([curr, amt]) => {
        const rate = currencies.find(c => c.code === curr)?.rate || 1;
        totalInUZS += amt * rate;
      });

      const payload = {
        name: form.name,
        phone: form.phone || null,
        debt_balance: totalInUZS,
        debt_currency: 'UZS',
        debt_balances: debtBalances,
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
      const validPayments = payDebtLength.filter(
        item => item.payAmount && Number(item.payAmount) > 0 && item.payType
      );

      if (validPayments.length === 0) {
        setError("Kamida bitta to'lov turi va miqdorini kiriting");
        setSaving(false);
        return;
      }

      for (const item of validPayments) {
        const currency = currencies.find(c => c.code === item.currencyType) || { rate: 1 };
        const amountInUZS = Number(item.payAmount) * currency.rate;

        await api.post(`/customers/${selected.id}/pay-debt`, {
          amount: amountInUZS,
          payment_type: item.payType,
          reason: payInfo || "Mijoz qarz to'lovi",
          wallet_id: payWallet ? Number(payWallet) : null,
        });
      }

      closeModal(); load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map(d => d.msg || String(d)).join(', '));
      } else if (typeof detail === 'object' && detail !== null) {
        setError(JSON.stringify(detail));
      } else {
        setError(detail || 'Xatolik yuzaga keldi');
      }
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

  const totalDebt = totalAllDebt;

  const debtors = customers.filter(c => Number(c.debt_balance) > 0).length;

  const [tab, setTab] = useState('mijozlar');

  // 1. Boshlang'ich state endi oddiy sonlar emas, ob'ektlar massivi bo'ladi:
  const [payDebtLength, setPayDebtLength] = useState([
    { id: Date.now(), payType: '', payAmount: '', currencyType: 'UZS' }
  ]);

  // 2. Qator qo'shish funksiyasi
  const handleAddRow = () => {
    if (payDebtLength.length < 4) {
      setPayDebtLength([
        ...payDebtLength,
        { id: Date.now() + Math.random(), payType: '', payAmount: '', currencyType: 'UZS' }
      ]);
    }
  };

  // 3. Qatorni o'chirish funksiyasi (Siz so'ragan qism)
  const handleRemoveRow = (indexToRemove) => {
    // Agar oxirgi bitta qator qolgan bo'lsa, o'chirmaslik tavsiya etiladi
    if (payDebtLength.length > 1) {
      setPayDebtLength(prev => prev.filter((_, index) => index !== indexToRemove));
    } else {
      // Agar oxirgi qator bo'lsa, shunchaki ichini tozalab qo'yish mumkin
      setPayDebtLength([{ id: Date.now(), payType: '', payAmount: '' }]);
    }
  };

  // 4. Inputlar o'zgarganda aynan o'sha qatorni yangilash funksiyasi
  const handleInputChange = (index, field, value) => {
    const updatedRows = [...payDebtLength];
    updatedRows[index][field] = value;
    setPayDebtLength(updatedRows);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-y-3 flex-wrap justify-between">
        <div>
          <h1 className="text-lg xl:text-2xl font-bold text-slate-800">{t('customer.title')}</h1>
          <p className="text-slate-500 leading-none text-xs xl:text-sm mt-0.5">{t('customer.subtitle')}</p>
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
              saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `mijozlar_${new Date().toISOString().slice(0, 10)}.xlsx`);
            }}
            className="inline-flex items-center leading-none gap-1 xl:gap-2 px-2.5 xl:px-4 py-1.5 xl:py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs xl:text-sm font-semibold rounded-md xl:rounded-xl transition-colors border border-emerald-200"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            {t('customer.exportExcel')}
          </button>
          <button
            onClick={openImport}
            className="inline-flex items-center leading-none gap-1 xl:gap-2 px-2.5 xl:px-4 py-1.5 xl:py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs xl:text-sm font-semibold rounded-md xl:rounded-xl transition-colors border border-indigo-200"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            {t('customer.importFromExcel')}
          </button>
          <button
            onClick={openAdd}
            className="inline-flex items-center leading-none gap-1 xl:gap-2 px-2.5 xl:px-4 py-1.5 xl:py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs xl:text-sm font-semibold rounded-md xl:rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
            </svg>
            {t('customer.newCustomer')}
          </button>
        </div>
      </div>

      <div
        onClick={(e) => {
          const main = e.currentTarget.closest('main');
          if (main) main.scrollTo({ top: main.scrollHeight, behavior: 'smooth' });
        }}
        className='fixed bottom-5 group -right-12 flex justify-left items-center z-30 hover:-right-5 transition-all w-18 h-11 text-white'
      >
        <div className='flex bg-indigo-600 items-center pl-0 group-hover:pl-2.5 transition-all w-11 h-11 rounded-lg shadow-md cursor-pointer'>
          <ChevronDown className='size-6 rotate-90 group-hover:rotate-0 transition-all' />
        </div>
      </div>

      {/* Stats */}
      <div className="grid sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg lg:rounded-2xl shadow-sm border border-slate-100 p-2.25 lg:p-3 xl:p-5 flex items-center gap-4">
          <div className="w-10 h-10 xl:w-12 xl:h-12 rounded-lg lg:rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
            <Users className="size-5 xl:size-6 text-indigo-600" />
          </div>
          <div className='flex flex-col gap-1'>
            <div className="text-[10px] lg:text-xs leading-none font-semibold text-slate-400 uppercase tracking-wider">{t('customer.totalCustomers')}</div>
            <div className="text-[16px] leading-none lg:text-xl font-bold text-indigo-600 mt-0.5">{customers.length.toLocaleString()}</div>
          </div>
        </div>
        <div className="bg-white rounded-lg lg:rounded-2xl shadow-sm border border-slate-100 p-2.25 lg:p-3 xl:p-5 flex items-center gap-4">
          <div className="w-10 h-10 xl:w-12 xl:h-12 rounded-lg lg:rounded-xl bg-red-100 flex items-center justify-center shrink-0">
            <CreditCard className="size-5 xl:size-6 text-red-500" />
          </div>
          <div className='flex flex-col gap-1'>
            <div className="text-[10px] lg:text-xs leading-none font-semibold text-slate-400 uppercase tracking-wider">{t('customer.totalDebt')}</div>
            <div className="text-[16px] leading-none lg:text-xl font-bold text-red-500 mt-0.5">{fmt(totalDebt)} {t('common.sum')}</div>
          </div>
        </div>
        <div className="bg-white rounded-lg lg:rounded-2xl shadow-sm border border-slate-100 p-2.25 lg:p-3 xl:p-5 flex items-center gap-4">
          <div className="w-10 h-10 xl:w-12 xl:h-12 rounded-lg lg:rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
            <AlertTriangle className="size-5 xl:size-6 text-amber-600" />
          </div>
          <div className='flex flex-col gap-1'>
            <div className="text-[10px] lg:text-xs leading-none font-semibold text-slate-400 uppercase tracking-wider">{t('customer.totalDebtors')}</div>
            <div className="text-[16px] leading-none lg:text-xl font-bold text-amber-600 mt-0.5">{debtors}</div>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="flex gap-2 flex-col sm:flex-row flex-wrap">
        <div className='flex border min-w-20 flex-1 border-slate-200 items-center bg-white gap-3 rounded-xl shadow-sm'>
          <svg className="w-4 xl:w-5 h-4 xl:h-5 text-slate-400 ml-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            className="w-full pr-4 py-2 xl:py-3 text-sm focus:outline-none"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t('customer.searchPlaceholder')}
          />
        </div>

        <div className="w-full sm:w-auto min-w-[240px] flex-1 sm:flex-none">
          <Listbox value={currentSort} onChange={(val) => {
            setSortBy(val.sort_by);
            setSortOrder(val.sort_order);
          }}>
            <div className="relative">
              <ListboxButton className="w-full cursor-pointer flex items-center px-3 py-2 xl:px-4 xl:py-3 justify-between rounded-xl border border-slate-200 text-sm xl:text-base bg-white text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 transition-all shadow-sm text-left">
                <span className="flex items-center gap-2">
                  <ListOrdered className="size-4 xl:size-5 shrink-0 text-slate-400" />
                  <span className="block truncate">
                    {currentSort.label}
                  </span>
                </span>
                <ChevronsUpDown aria-hidden="true" className="shrink-0 size-4 xl:size-5 text-slate-400" />
              </ListboxButton>
              <ListboxOptions transition className="absolute z-30 mt-2 max-h-72 w-full overflow-auto rounded-xl bg-white border border-slate-100 transition duration-100 ease-in data-[closed]:opacity-0 shadow-xl py-1">
                {sortOptions.map((opt, idx) => (
                  <ListboxOption key={idx} value={opt} className="group relative py-2 px-3 sm:px-4 select-none cursor-pointer text-slate-700 data-[focus]:bg-indigo-50 data-[focus]:text-indigo-700 outline-none">
                    <div className="flex items-center gap-2 sm:gap-3">
                      <CircleCheck className={`size-4 xl:size-5 shrink-0 ${currentSort.label === opt.label ? 'text-indigo-600' : 'text-slate-300'}`} />
                      <span className={`text-xs sm:text-sm truncate ${currentSort.label === opt.label ? 'font-bold text-indigo-700' : 'font-normal'}`}>
                        {opt.label}
                      </span>
                    </div>
                  </ListboxOption>
                ))}
              </ListboxOptions>
            </div>
          </Listbox>
        </div>

        {/* Debt Filter */}
        <div className="w-full sm:w-auto min-w-[300px] flex-1 sm:flex-none">
          <div className="flex items-center px-3 py-2 xl:px-4 xl:py-3 rounded-xl border border-slate-200 bg-white shadow-sm focus-within:ring-2 focus-within:ring-indigo-500 transition-all">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <Banknote className="size-4 xl:size-5 shrink-0 text-slate-400" />
              <input
                type="number"
                value={filterAmount}
                onChange={e => setFilterAmount(e.target.value)}
                placeholder="0"
                className="w-16 sm:w-20 bg-transparent outline-none font-medium text-sm xl:text-base text-slate-800 placeholder:text-slate-300"
              />
              <span className="text-slate-400 text-[10px] xl:text-xs font-semibold uppercase shrink-0">so'm</span>

              <div className="h-4 w-[1px] bg-slate-200 mx-2 shrink-0" />

              <Listbox value={currentFilter} onChange={(val) => setFilterType(val.key)}>
                <div className="relative flex-1 min-w-0">
                  <ListboxButton className="w-full flex items-center justify-between outline-none cursor-pointer">
                    <span className="block truncate text-slate-600 text-xs sm:text-sm xl:text-base mr-1">
                      {currentFilter.label}
                    </span>
                    <ChevronsUpDown aria-hidden="true" className="shrink-0 size-4 text-slate-400" />
                  </ListboxButton>
                  <ListboxOptions transition className="absolute z-30 mt-3 max-h-72 w-56 -right-3 xl:-right-4 overflow-auto rounded-xl bg-white border border-slate-100 transition duration-100 ease-in data-[closed]:opacity-0 shadow-xl py-1">
                    {filterOptions.map((opt) => (
                      <ListboxOption key={opt.key} value={opt} className="group relative py-2.5 px-4 select-none cursor-pointer text-slate-700 data-[focus]:bg-indigo-50 data-[focus]:text-indigo-700 outline-none">
                        <div className="flex items-center gap-3">
                          <CircleCheck className={`size-4 shrink-0 ${filterType === opt.key ? 'text-indigo-600' : 'text-slate-200'}`} />
                          <span className={`text-xs sm:text-sm truncate ${filterType === opt.key ? 'font-bold text-indigo-700' : 'font-normal'}`}>
                            {opt.label}
                          </span>
                        </div>
                      </ListboxOption>
                    ))}
                  </ListboxOptions>
                </div>
              </Listbox>
            </div>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="flex bg-white rounded-2xl flex-col h-full mb-10 border border-slate-100 shadow-sm ">
        <div className="overflow-x-auto table-fixed scrollbar-thin scrollbar-thumb-slate-200 rounded-t-2xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['T/r', t('common.name'), t('common.phone'), t('customer.debtBalance'), t('customer.creditLimit'), `${t('customer.bonusBalance')} / ${t('customer.cashback')}`, t('common.actions')].map(h => (
                  <th key={h} className="px-6 py-3.5 text-left text-[10px] md:text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {customers.map((c, idx) => {
                const rowNumber = (page - 1) * limit + (idx + 1);
                return (
                  <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 text-xs md:text-sm text-center text-slate-500">{rowNumber}</td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => navigate(`/admin/customers/${c.id}`)}
                        className="flex items-center gap-3 hover:opacity-75 transition-opacity text-left"
                      >
                        <Avatar name={c.name} />
                        <span className="text-xs cursor-pointer md:text-sm font-medium text-indigo-700 hover:underline">{c.name}</span>
                      </button>
                    </td>
                    <td className="px-6 py-4 text-xs md:text-sm text-slate-500">{c.phone || '—'}</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-0.5">
                        <span className={`text-xs md:text-sm font-bold ${Number(c.debt_balance) > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                          {fmt(c.debt_balance)} so'm
                        </span>
                        {c.debt_balances && typeof c.debt_balances === 'object' && Object.keys(c.debt_balances).filter(curr => curr !== 'UZS').length > 0 && (
                          <div className="flex flex-wrap gap-x-3 border-t border-slate-100 pt-0.5 mt-0.5">
                            {Object.entries(c.debt_balances).map(([curr, amt]) => curr !== 'UZS' && (
                              <span key={curr} className="text-xs text-red-500 font-medium whitespace-nowrap">
                                {fmt(amt)} {curr === 'USD' ? '$' : curr}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs md:text-sm text-slate-500">{fmt(c.debt_limit)} so'm</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1">
                        <span className="inline-flex items-center whitespace-nowrap gap-1 px-2.5 py-1 bg-amber-50 text-amber-600 text-xs md:text-sm font-semibold rounded-lg w-fit">
                          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                          </svg>
                          {fmt(c.bonus_balance || 0)} so'm
                        </span>
                        {(c.cashback_percent > 0) && (
                          <span className={`text-[10px] whitespace-nowrap md:text-xs font-semibold px-2 py-0.5 rounded-full w-fit bg-indigo-100 text-indigo-700`}>
                            {Number(c.cashback_percent)}% keshbek
                          </span>
                        )}
                        {(c.loyalty_points > 0) && (
                          <span className={`text-[10px] whitespace-nowrap md:text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${TIERS[tierOf(c.loyalty_points || 0)].cls}`}>
                            {TIERS[tierOf(c.loyalty_points || 0)].label} ({c.loyalty_points})
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <RowMenu
                        onEdit={() => openEdit(c)}
                        onDelete={() => deleteCustomer(c.id)}
                        onPay={() => openPay(c)}
                        onPoints={() => openPoints(c)}
                        onHistory={() => openHistory(c)}
                        hasDebt={Number(c.debt_balance) > 0}
                      />
                    </td>
                  </tr>)
              })}
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
        </div>
        {customers.length > 0 && (
          <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-xs md:text-sm text-slate-500 bg-slate-50">
            <span>Jami <strong className="text-slate-700">{totalRecords}</strong> ta mijoz</span>

            <div className="flex items-center flex-nowrap gap-0 sm:gap-1">
              <button disabled={page === 1} onClick={() => setPage(1)}
                className={`rounded-lg ${page === 1 ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronsLeft className='size-4 sm:size-5' />
              </button>
              <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                className={`rounded-lg ${page === 1 ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronLeft className='size-4 sm:size-5' />
              </button>
              <span className="px-2 sm:px-3 text-[12px] xl:text-[14px] whitespace-nowrap font-semibold text-slate-700">{page} / {Math.ceil(totalRecords / limit) || 1}</span>
              <button disabled={page >= (Math.ceil(totalRecords / limit) || 1)} onClick={() => setPage(p => p + 1)}
                className={`rounded-lg ${page >= (Math.ceil(totalRecords / limit) || 1) ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronRight className='size-4 sm:size-5' />
              </button>
              <button disabled={page === (Math.ceil(totalRecords / limit) || 1)} onClick={() => setPage(Math.ceil(totalRecords / limit) || 1)}
                className={`rounded-lg ${page === (Math.ceil(totalRecords / limit) || 1) ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronsRight className='size-4 sm:size-5' />
              </button>
            </div>

            <div className='flex gap-1 md:gap-3 text-right md:text-left items-center flex-col md:flex-row'>
              <span className='hidden md:block'>Umumiy qarz: <strong className="text-red-500">{fmt(totalAllDebt)} so'm</strong></span>

              {/* 5. LIMIT (PAGINATION) LISTBOX */}
              <div className="z-30 ml-auto md:ml-0">
                <Listbox
                  value={limit}
                  onChange={(val) => {
                    const v = Number(val);
                    localStorage.setItem('customers_products_limit', v);
                    setLimit(v);
                    setPage(1); // Limit o'zgarganda 1-sahifaga qaytish
                  }}
                >
                  <div className="relative min-w-[90px] sm:min-w-[120px]">
                    <ListboxButton className="w-full cursor-pointer flex items-center py-1 px-2 xl:px-3 xl:py-1.5 justify-between rounded-lg border border-slate-200 text-[13px] xl:text-[14px] bg-white text-slate-900 outline-none hover:border-indigo-400 focus:border-indigo-500 transition-colors shadow-sm text-left">
                      <span className="flex items-center gap-2">
                        <ListOrdered className="size-4 shrink-0 text-slate-400" />
                        <span>{limit} {t('common.item')}</span>
                      </span>
                      <ChevronsUpDown aria-hidden="true" className="size-4 text-gray-400" />
                    </ListboxButton>
                    <ListboxOptions
                      anchor="top end"
                      className="z-50 min-w-[120px] mb-1 overflow-auto rounded-xl bg-white border border-slate-200 p-1 shadow-2xl focus:outline-none [--anchor-gap:4px]"
                    >
                      {[5, 10, 20, 50, 100, 500].map((n) => (
                        <ListboxOption key={n} value={n} className="group flex cursor-pointer items-center gap-2 rounded-lg py-2 px-3 select-none data-[focus]:bg-indigo-50">
                          <CheckIcon className="size-4 text-indigo-600 group-not-data-[selected]:invisible" />
                          <div className="text-[13px] font-medium text-slate-700 group-data-[selected]:text-indigo-700">{n} {t('common.item')}</div>
                        </ListboxOption>
                      ))}
                    </ListboxOptions>
                  </div>
                </Listbox>
              </div>
            </div>
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
              <button onClick={closeModal} className="p-2 cursor-pointer hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
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
                  <div className="bg-white text-sm px-3.5 flex border border-slate-200 gap-2 items-center rounded-xl">
                    <span>+998</span>
                    <input
                      value={form.phone}
                      maxLength={9}
                      onChange={e => setForm({ ...form, phone: e.target.value })}
                      placeholder="90 123 45 67"
                      className="w-full border-l border-slate-300 px-2 py-2.5 focus:outline-none"
                    />
                  </div>
                </div>
                <div className="col-span-2">
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-600">Boshlang'ich qarz / Joriy qarz</label>
                    <button
                      type="button"
                      onClick={() => setForm({ ...form, debts: [...form.debts, { amount: '', currency: 'UZS' }] })}
                      className="text-xs text-indigo-600 hover:text-indigo-700 font-bold flex items-center gap-1 bg-indigo-50 px-2 py-1 rounded-lg"
                    >
                      <Plus className="size-3" /> Qo'shish
                    </button>
                  </div>
                  <div className="space-y-2">
                    {form.debts.map((debt, idx) => (
                      <div key={idx} className="flex gap-2 items-center group">
                        <div className="flex flex-1 cursor-pointer bg-white items-center border border-slate-200 rounded-xl focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500 transition-all">
                          <Listbox value={debt.currency} onChange={(val) => {
                             const newDebts = [...form.debts];
                             newDebts[idx].currency = val;
                             setForm({ ...form, debts: newDebts });
                          }}>
                            <div className="relative">
                              <ListboxButton className="h-[42px] px-3 flex items-center bg-slate-50 border-r border-slate-200 hover:bg-slate-100 rounded-l-xl transition-colors text-sm font-semibold text-slate-700 outline-none w-[85px] justify-between">
                                <span className="block truncate">{debt.currency}</span>
                                <ChevronsUpDown className="size-3.5 text-slate-400 shrink-0" />
                              </ListboxButton>
                              <ListboxOptions className="absolute z-[100] top-full mt-1 left-0 max-h-60 w-[120px] overflow-auto rounded-xl outline-none bg-white text-sm border border-slate-200 shadow-2xl p-1">
                                {currencies?.map((c) => (
                                  <ListboxOption key={c.code} value={c.code} className="group relative py-2 px-3 select-none cursor-pointer rounded-lg text-slate-700 data-[focus]:bg-indigo-50 data-[focus]:text-indigo-700 outline-none flex items-center justify-between transition-colors">
                                    <span className="block truncate font-medium group-data-[selected]:font-bold">{c.code}</span>
                                    <CheckIcon className="size-3.5 text-indigo-600 invisible group-data-[selected]:visible" />
                                  </ListboxOption>
                                ))}
                              </ListboxOptions>
                            </div>
                          </Listbox>
                          <input
                            type="number" step="any"
                            value={debt.amount}
                            onChange={e => {
                               const newDebts = [...form.debts];
                               newDebts[idx].amount = e.target.value;
                               setForm({ ...form, debts: newDebts });
                            }}
                            placeholder="Qarz miqdori"
                            className="h-[42px] flex-1 w-full px-3 rounded-r-xl text-sm outline-none bg-transparent"
                          />
                        </div>
                        {form.debts.length > 1 && (
                          <button
                            type="button"
                            onClick={() => {
                              const newDebts = form.debts.filter((_, i) => i !== idx);
                              setForm({ ...form, debts: newDebts });
                            }}
                            className="p-2.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-xl transition-colors"
                          >
                            <Minus className="size-4" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
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
                <button type="button" onClick={closeModal} className="flex-1 cursor-pointer py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                  {t('common.cancel')}
                </button>
                <button type="submit" disabled={saving} className="flex-1 cursor-pointer py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? t('common.saving') : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── PAY DEBT MODAL ──────────────────────────────────── */}
      {modal === 'pay' && selected && (() => {
        const debt = Number(selected.debt_balance) || 0;
        const paid = payDebtLength.reduce((sum, item) => {
          const currency = currencies.find(c => c.code === item.currencyType) || { rate: 1 };
          return sum + (Number(item.payAmount) || 0) * currency.rate;
        }, 0);
        const remaining = Math.max(0, debt - paid);
        const change = Math.max(0, paid - debt);
        const PAY_TYPES = [
          { key: 'cash', label: 'Naqd' },
          { key: 'card', label: 'Karta' },
          { key: 'uzcard', label: 'Uzcard' },
          { key: 'humo', label: 'Humo' },
          { key: 'transfer', label: "Bank o'tkazmasi" },
          { key: 'click', label: 'Click' },
          { key: 'payme', label: 'Payme' },
        ]

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-2 md:p-4 bg-slate-900/70 backdrop-blur-sm" onClick={closeModal}>
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[95vh] flex flex-col pointer-events-auto" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="flex items-center justify-between px-4 md:px-7 py-3 md:py-5 border-b border-slate-100 shrink-0">
                <div>
                  <h3 className="text-lg md:text-xl font-bold text-slate-800 tracking-tight">Kassadan to'lov</h3>
                  <p className="text-xs md:text-sm text-blue-500 font-medium mt-0.5">{new Date().toLocaleString('uz-UZ').replace(',', '')}</p>
                </div>
                <button onClick={closeModal} className="w-8 h-8 md:w-9 md:h-9 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 transition-colors">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>

              {/* Body */}
              <div className="p-4 md:p-7 overflow-y-auto space-y-5 md:space-y-7 custom-scrollbar">
                {/* Mijoz Info */}
                <div className="flex items-center gap-3 md:gap-4 p-3 md:p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <Avatar name={selected.name} size="lg" />
                  <div className="min-w-0">
                    <div className="font-bold text-slate-800 text-sm md:text-base truncate">{selected.name}</div>
                    {selected.phone && <div className="text-xs md:text-sm text-slate-500 mt-0.5 truncate">{selected.phone}</div>}
                    <div className="text-sm md:text-base font-bold text-red-500 mt-1">Joriy qarz: {fmt(debt)} so'm</div>
                  </div>
                </div>

                {/* Kassa tanlash */}
                <div className="space-y-1.5 md:space-y-2">
                  <label className="text-xs md:text-sm font-semibold text-slate-700">Kassa / Hisob</label>
                  <select value={payWallet} onChange={e => setPayWallet(e.target.value)}
                    className="w-full h-11 md:h-12 px-3 md:px-4 border border-slate-200 rounded-xl bg-white text-xs md:text-sm font-medium focus:border-indigo-500 outline-none transition-all">
                    <option value="">Asosiy kassa</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} — {fmt(w.balance)} so'm</option>)}
                  </select>
                </div>

                {/* To'lov miqdori */}
                <div className='flex flex-col gap-1.5'>
                  {payDebtLength.map((item, index) => (
                    <div key={item.id} className='flex w-full items-end gap-2'> {/* items-center dan items-end ga olindi, label tepada turishi uchun */}

                      {/* TO'LOV TURI (SELECT) */}
                      <div className="w-full sm:w-auto min-w-[160px] flex-1 sm:flex-none space-y-1.5 md:space-y-2">
                        <label className="text-xs md:text-sm font-semibold text-slate-700">To'lov turi *</label>
                        <Listbox
                          value={item.payType}
                          onChange={(val) => handleInputChange(index, 'payType', val)}
                        >
                          <div className="relative">
                            <ListboxButton className="w-full cursor-pointer flex items-center pl-4 pr-8 py-3 justify-between rounded-lg border border-slate-200 text-[14px] xl:text-[16px] bg-white text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors shadow-xs text-left font-medium h-11 md:h-12">
                              <span className="block truncate">
                                {PAY_TYPES.find(pt => pt.key === item.payType)?.label || "Tanlang..."}
                              </span>
                              <span className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none text-slate-400">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="size-4 xl:size-5">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" />
                                </svg>
                              </span>
                            </ListboxButton>

                            <ListboxOptions className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-md outline-none bg-white text-[14px] xl:text-[16px] border border-slate-200 shadow-lg p-1">
                              {PAY_TYPES.map((pt) => (
                                <ListboxOption
                                  key={pt.key}
                                  value={pt.key}
                                  className="group relative py-1.5 xl:py-2 px-3 select-none cursor-pointer rounded-md text-slate-800 data-[focus]:bg-indigo-600 data-[focus]:text-white outline-none transition-colors"
                                >
                                  <div className="flex items-center justify-between">
                                    <span className="block truncate font-normal group-data-[selected]:font-semibold">{pt.label}</span>
                                    <span className="text-indigo-600 group-data-[focus]:text-white group-not-data-[selected]:hidden">
                                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="size-4">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                      </svg>
                                    </span>
                                  </div>
                                </ListboxOption>
                              ))}
                            </ListboxOptions>
                          </div>
                        </Listbox>
                      </div>

                      {/* TO'LOV MIQDORI (INPUT) */}
                      <div className="space-y-1.5 flex-1 md:space-y-2">
                        <label className="text-xs md:text-sm font-semibold text-slate-700">To'lov miqdori *</label>
                        <div className="flex h-11 md:h-12">
                          <input
                            type="number"
                            value={item.payAmount}
                            onChange={e => handleInputChange(index, 'payAmount', e.target.value)}
                            className="flex-1 min-w-0 h-full border border-slate-200 rounded-l-xl px-3 md:px-4 text-sm md:text-base font-medium outline-none focus:border-indigo-500 transition-all"
                            placeholder="0"
                          />
                          {/* <select
                            value={item.currencyType || 'UZS'}
                            onChange={(e) => handleInputChange(index, 'currencyType', e.target.value)}
                            className="px-2 md:px-3 flex items-center border-y border-slate-200 text-indigo-600 text-xs md:text-sm font-bold bg-white">
                            {currencies.map((cur) => (
                              <option key={cur.code} value={cur.code}>{cur.code}</option>
                            ))}
                          </select> */}

                          <Listbox
                            value={item.currencyType || 'UZS'}
                            onChange={(val) => handleInputChange(index, 'currencyType', val)}
                          >
                            <div className="relative">
                              <ListboxButton className="w-full min-w-[100px] cursor-pointer flex items-center pl-4 pr-8 py-3 justify-between  border-l-0 border border-slate-200 text-[14px] xl:text-[16px] bg-white text-slate-900 outline-none transition-colors shadow-xs text-left font-medium h-11 md:h-12">
                                <span className="block truncate">
                                  {currencies.find(c => c.code === item.currencyType)?.code || "Tanlang..."}
                                </span>
                                <span className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none text-slate-400">
                                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="size-4 xl:size-5">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15 12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" />
                                  </svg>
                                </span>
                              </ListboxButton>

                              <ListboxOptions className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-md outline-none bg-white text-[14px] xl:text-[16px] border border-slate-200 shadow-lg p-1">
                                {currencies.map((pt) => (
                                  <ListboxOption
                                    key={pt.code}
                                    value={pt.code}
                                    className="group relative py-1.5 xl:py-2 px-3 select-none cursor-pointer rounded-md text-slate-800 data-[focus]:bg-indigo-600 data-[focus]:text-white outline-none transition-colors"
                                  >
                                    <div className="flex items-center justify-between">
                                      <span className="block truncate font-normal group-data-[selected]:font-semibold">{pt.code}</span>
                                      <span className="text-indigo-600 group-data-[focus]:text-white group-not-data-[selected]:hidden">
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" className="size-4">
                                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                        </svg>
                                      </span>
                                    </div>
                                  </ListboxOption>
                                ))}
                              </ListboxOptions>
                            </div>
                          </Listbox>

                          <button
                            type="button"
                            onClick={() => handleInputChange(index, 'payAmount', String(Math.round(debt)))}
                            className="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-slate-200 border-l-0 font-bold px-3 md:px-4 h-full rounded-r-xl transition-colors whitespace-nowrap text-xs md:text-sm"
                          >
                            Barchasi
                          </button>
                        </div>
                      </div>

                      {/* MINUS TUGMASI (O'CHIRISH) */}
                      <button
                        type="button"
                        onClick={() => handleRemoveRow(index)}
                        className='cursor-pointer p-3 bg-red-100 hover:bg-red-200 text-red-600 rounded-xl h-11 md:h-12 flex items-center justify-center shrink-0'
                      >
                        <Minus />
                      </button>

                    </div>
                  ))}

                  {/* QATOR QO'SHISH TUGMASI */}
                  <button
                    type="button"
                    onClick={handleAddRow}
                    className='cursor-pointer flex ml-auto items-center gap-1 hover:bg-indigo-50 w-max px-2 py-0.5 rounded-xl'
                  >
                    <Plus className='size-5 text-indigo-600' />
                    <span className='text-xs md:text-sm font-semibold text-indigo-600'>to'lov qo'shish</span>
                  </button>
                </div>

                {/* To'lov turi — button style */}
                {/* <div className="space-y-2 md:space-y-3">
                  <label className="text-xs md:text-sm font-semibold text-slate-700">To'lov turi</label>
                  <div className="flex flex-wrap gap-2">
                    {PAY_TYPES.map(pt => (
                      <button key={pt.key} type="button"
                        onClick={() => setPayType(pt.key)}
                        className={`px-3 md:px-5 py-1.5 md:py-2.5 rounded-lg md:rounded-xl text-xs md:text-sm font-semibold border transition-all ${payType === pt.key
                          ? 'bg-indigo-600 text-white border-indigo-600 shadow-lg shadow-indigo-200'
                          : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600'
                          }`}>
                        {pt.label}
                      </button>
                    ))}
                  </div>
                </div> */}

                {/* Izoh */}
                <div className="space-y-1.5 md:space-y-2">
                  <label className="text-xs md:text-sm font-semibold text-slate-700">Izoh</label>
                  <textarea rows={2} value={payInfo} onChange={e => setPayInfo(e.target.value)}
                    className="w-full p-3 md:p-4 border border-slate-200 rounded-xl text-xs md:text-sm leading-relaxed focus:ring-2 focus:ring-indigo-500 outline-none resize-none transition-all"
                    placeholder="Ixtiyoriy..." />
                </div>

                {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-xs md:text-sm rounded-xl animate-shake">{error}</div>}

                {/* Summary */}
                <div className="flex justify-end">
                  <div className="w-full md:w-72 space-y-2 bg-indigo-50/50 rounded-xl p-4 border border-indigo-100/50 backdrop-blur-sm">
                    <div className="flex justify-between text-xs md:text-sm items-center">
                      <span className="text-slate-500 font-medium tracking-tight">Umumiy summa:</span>
                      <span className="font-bold text-slate-700">{fmt(debt)}</span>
                    </div>
                    <div className="flex justify-between text-xs md:text-sm items-center">
                      <span className="text-slate-500 font-medium tracking-tight">To'lov:</span>
                      <span className="font-bold text-blue-600">{fmt(paid)} uzs</span>
                    </div>
                    <div className="border-t border-indigo-100/50 my-2" />
                    <div className="flex justify-between text-sm md:text-base items-center">
                      <span className="text-slate-600 font-semibold tracking-tight">Qarzga:</span>
                      <span className={`font-bold ${remaining > 0 ? 'text-red-500' : 'text-emerald-600'}`}>{fmt(remaining)}</span>
                    </div>
                    {change > 0 && (
                      <div className="flex justify-between text-sm items-center pt-1 animate-bounce-subtle">
                        <span className="text-amber-600 font-bold tracking-tight">Qaytim:</span>
                        <span className="font-bold text-amber-600">{fmt(change)}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-4 md:px-7 py-4 md:py-5 border-t border-slate-100 bg-slate-50 shrink-0">
                <div className="text-xs md:text-sm text-slate-500 font-medium text-center sm:text-left">
                  Mijoz qoldig'i qarz: <span className={`font-bold ${remaining > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmt(remaining)} UZS</span>
                </div>
                <div className="flex gap-2 md:gap-3 w-full sm:w-auto">
                  <button onClick={closeModal} className="flex-1 sm:flex-none px-4 md:px-6 py-2 md:py-2.5 rounded-xl border border-slate-300 text-slate-600 text-sm font-bold bg-white hover:bg-slate-50 transition-all">
                    Bekor qilish
                  </button>
                  <button disabled={
                    saving ||
                    !payDebtLength.some(item => item.payAmount && Number(item.payAmount) > 0 && item.payType)
                  } onClick={handlePay}
                    className="flex-1 cursor-pointer sm:flex-none px-6 md:px-8 py-2 md:py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold transition-all shadow-lg shadow-indigo-200 disabled:opacity-50 disabled:shadow-none flex items-center justify-center gap-2">
                    {saving ? (
                      <span className="flex items-center gap-2"><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>...</span>
                    ) : (
                      <><svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>Saqlash</>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

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
                              {dateObj.toLocaleDateString('uz-UZ')} {dateObj.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })}
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
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                Fayl tanlash
                <input type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { if (e.target.files[0]) parseExcel(e.target.files[0]); }} />
              </label>
              <button
                onClick={handleImport}
                disabled={!buildPayload().length || importLoading || !(Object.values(colMap).includes('Ism') || (allowUpdate && (Object.values(colMap).includes('Telefon') || Object.values(colMap).includes('Karta raqami'))))}
                className="inline-flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-colors border border-transparent"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
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

const PAY_TYPES_LIST = [
  { v: 'cash', l: 'Naqd' },
  { v: 'card', l: 'Karta' },
  { v: 'uzcard', l: 'Uzcard' },
  { v: 'humo', l: 'Humo' },
  { v: 'bank', l: "Bank o'tkazmasi" },
  { v: 'click', l: 'Click' },
  { v: 'payme', l: 'Payme' },
];

const parseAmt = (s) => {
  const clean = String(s || '').replace(/\s/g, '').replace(',', '.');
  // If dot appears as thousands separator (e.g. "4.700" or "54.700")
  // detect: dot followed by exactly 3 digits at end → thousands sep
  const thousandsDot = /^[\d.]+$/.test(clean) && /\.\d{3}$/.test(clean) && (clean.match(/\./g) || []).length === 1;
  return parseFloat(thousandsDot ? clean.replace('.', '') : clean) || 0;
};

function TolovTab({ customers, totalAllDebt = 0 }) {
  const [debtors, setDebtors] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(false);
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState({ amount: '', payType: 'cash', description: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = () => {
    api.get('/customers', { params: { limit: 500 }, _silent: true })
      .then(r => setDebtors((Array.isArray(r.data) ? r.data : []).filter(c => Number(c.debt_balance) > 0)))
      .catch(e => toast.error(e.response?.data?.detail || e.message || 'Xatolik'));
  };
  useEffect(() => { load(); }, []);

  const filtered = search.trim()
    ? debtors.filter(c =>
      c.name?.toLowerCase().includes(search.toLowerCase()) ||
      c.phone?.includes(search)
    )
    : [...debtors];

  filtered.sort((a, b) => Number(b.debt_balance) - Number(a.debt_balance));
  const totalDebt = totalAllDebt;

  const openModal = (c = null) => {
    setSel(c);
    setForm({ amount: '', payType: 'cash', description: '' });
    setErr('');
    setModal(true);
  };
  const close = () => { setModal(false); setSel(null); setErr(''); };

  const handlePay = async (e) => {
    e.preventDefault();
    if (!sel) { setErr("Mijozni tanlang"); return; }
    const amt = parseAmt(form.amount);
    if (!amt || amt <= 0) { setErr("Miqdor kiritilmagan"); return; }
    if (amt > Number(sel.debt_balance)) { setErr("Miqdor qarzdan oshib ketadi"); return; }
    setSaving(true); setErr('');
    try {
      await api.post(`/finance/customer-debts/${sel.id}/pay`, {
        amount: amt,
        description: form.description || `Mijoz to'lovi: ${sel.name}`,
      });
      toast.success("To'lov qabul qilindi!");
      close();
      load();
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 w-full gap-x-4 gap-y-2">
        <div className="bg-white rounded-lg w-full lg:rounded-2xl shadow-sm border border-slate-100 p-2.25 lg:p-3 xl:p-5 flex items-center gap-4">
          <div className="w-10 h-10 xl:w-12 xl:h-12 rounded-lg lg:rounded-xl bg-red-100 flex items-center justify-center shrink-0">
            <Users className="size-5 xl:size-6 text-red-500" />
          </div>
          <div className='flex flex-col gap-1'>
            <div className="text-[10px] lg:text-xs leading-none font-semibold text-slate-400 uppercase tracking-wider">Qarzdorlar</div>
            <div className="text-[16px] leading-none lg:text-xl font-bold text-red-500 mt-0.5">{customers.length.toLocaleString()}</div>
          </div>
        </div>
        <div className="bg-white rounded-lg w-full lg:rounded-2xl shadow-sm border border-slate-100 p-2.25 lg:p-3 xl:p-5 flex items-center gap-4">
          <div className="w-10 h-10 xl:w-12 xl:h-12 rounded-lg lg:rounded-xl bg-red-100 flex items-center justify-center shrink-0">
            <CreditCard className="size-6 text-red-500" />
          </div>
          <div className='flex flex-col gap-1'>
            <div className="text-[10px] lg:text-xs leading-none font-semibold text-slate-400 uppercase tracking-wider">Jami qarz</div>
            <div className="text-[16px] leading-none lg:text-xl font-bold text-red-500 mt-0.5">{fmt(totalDebt)} so'm</div>
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1">
          <svg className="absolute shrink-0 left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
          <input className="w-full pl-10 pr-4 py-2 md:py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Mijoz ismi yoki telefon..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <button onClick={() => openModal()}
          className="px-3 md:px-4 h-max py-2.5 md:py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs md:text-sm font-semibold rounded-xl flex items-center gap-2 shadow-sm transition-all">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
          Yangi to'lov
        </button>
      </div>

      <div className="bg-white overflow-x-auto rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['#', 'Mijoz', 'Telefon', 'Qarz miqdori', 'Qarz limiti', ''].map(h =>
                <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {filtered.map((c, i) => (
              <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-5 py-4 text-xs md:text-sm text-slate-400">{i + 1}</td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2.5">
                    <Avatar name={c.name} />
                    <span className="text-xs md:text-sm font-semibold text-slate-800">{c.name}</span>
                  </div>
                </td>
                <td className="px-5 py-4 text-xs md:text-sm text-slate-500">{c.phone || '—'}</td>
                <td className="px-5 py-4">
                  <span className="text-xs md:text-sm font-bold text-red-600">{fmt(c.debt_balance)} so'm</span>
                </td>
                <td className="px-5 py-4 text-xs md:text-sm text-slate-400">{fmt(c.debt_limit)} so'm</td>
                <td className="px-5 py-4">
                  <button onClick={() => openModal(c)}
                    className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 whitespace-nowrap cursor-pointer text-emerald-700 text-[10px] md:text-xs font-semibold rounded-lg border border-emerald-200 flex items-center gap-1.5 transition-all">
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>
                    To'lov qabul qilish
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="px-5 py-14 text-center text-slate-400 text-sm">
                {search ? 'Topilmadi' : "Barcha mijozlar qarzni to'lagan"}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">To'lov qabul qilish</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <form onSubmit={handlePay} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Mijoz *</label>
                <CustSearch customers={customers} value={sel?.id || ''} onChange={id => {
                  const c = customers.find(x => x.id === id);
                  setSel(c || null);
                }} />
              </div>
              {sel && (
                <div className="p-3 bg-red-50 border border-red-100 rounded-xl flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-slate-800 text-sm">{sel.name}</div>
                    {sel.phone && <div className="text-xs text-slate-400 mt-0.5">{sel.phone}</div>}
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-400">Qarz</div>
                    <div className="text-red-600 font-bold">{fmt(sel.debt_balance)} so'm</div>
                  </div>
                </div>
              )}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">To'lov miqdori *</label>
                <input type="text" inputMode="numeric" required className={inputCls} value={form.amount}
                  onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} placeholder="Miqdor (so'm)..." />
                {sel && form.amount && parseAmt(form.amount) > 0 && (
                  <div className="text-xs text-slate-400 mt-1">
                    To'lovdan keyin qarz: <span className="font-semibold text-amber-600">
                      {fmt(Math.max(0, Number(sel.debt_balance) - parseAmt(form.amount)))} so'm
                    </span>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-2">To'lov turi</label>
                <div className="flex flex-wrap gap-2">
                  {PAY_TYPES_LIST.map(pt => (
                    <button key={pt.v} type="button" onClick={() => setForm(f => ({ ...f, payType: pt.v }))}
                      className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all ${form.payType === pt.v ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}>
                      {pt.l}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Izoh</label>
                <input className={inputCls} value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Ixtiyoriy..." />
              </div>
              {err && <div className="px-4 py-3 bg-red-50 text-red-600 text-sm rounded-xl">{err}</div>}
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 text-sm font-medium rounded-xl hover:bg-slate-50">Bekor qilish</button>
                <button type="submit" disabled={saving || !sel} className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl">
                  {saving ? 'Saqlanmoqda...' : "To'lovni qabul qilish"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════
   MAIN PAGE
══════════════════════════════════════════════════ */
export default function Customers() {
  const { t } = useLang();
  const [tab, setTab] = useState('mijozlar');
  const TABS = [
    { id: 'mijozlar', label: t('customer.customers'), icon: <Users className='size-4 text-indigo-600' /> },
    { id: 'tolov', label: "To'lov qabul qilish", icon: <CreditCard className='size-4 text-indigo-600' /> },
  ];
  const [customers, setCustomers] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_cache_customers'))?.data || []; } catch { return []; }
  });

  useEffect(() => {
    api.get('/customers', { params: { limit: 300 }, _silent: true })
      .then(r => {
        const data = r.data;
        setCustomers(data);
        localStorage.setItem('pos_cache_customers', JSON.stringify({ ts: Date.now(), data }));
      }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const totalAllDebt = customers.reduce((s, c) => s + Number(c.debt_balance || 0), 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-0.5 bg-slate-100 p-0.5 rounded-lg">
          {TABS.map(tabItem => (
            <button key={tabItem.id} onClick={() => setTab(tabItem.id)}
              className={`px-4 py-1.5 cursor-pointer text-xs md:text-sm font-semibold rounded-md transition-all flex items-center gap-1.5 ${tab === tabItem.id ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
              <span className="text-xs">{tabItem.icon}</span>{tabItem.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'tolov' && <TolovTab customers={customers} totalAllDebt={totalAllDebt} />}
      {tab === 'mijozlar' && <SotuvMijozlar totalAllDebt={totalAllDebt} />}
    </div>
  );
}