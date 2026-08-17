import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';
import { saveReceiptSettings } from '../../utils/receiptBuilder';
import { Search, Zap } from 'lucide-react';
import axios from 'axios';
import { getFiscalModules } from '../../api/hippoLocal';
import RolesTab from './Settings/Roles';
import UsersTab from './Settings/Users';

// Add placeholder for missing tabs
const PlaceholderTab = ({ name }) => (
  <div className="py-12 text-center text-slate-400">
    <h3 className="text-lg font-bold text-slate-700 mb-2">{name} tez orada ishga tushadi</h3>
    <p className="text-sm">Bu bo'lim ustida ish olib borilmoqda.</p>
  </div>
);

// ── Default chek shablon konfiguratsiyalari ───────────────────────────────────
const defaultReceiptCfg = {
  company: '', address: '', phone: '', inn: '', logo: '', logo_size: 40,
  header: '', footer: 'Xaridingiz uchun rahmat!',
  show_number: true, show_date: true, show_status: false,
  show_account_name: true, show_employee: true,
  show_ordering_number: false, show_unit: false, show_warehouse: false,
  show_package: false, show_price_per_unit: true, show_discount: true,
  show_price_with_discount: false, show_currency: false,
  show_total: true, show_net_price: false, show_total_quantity: false,
  show_total_national: false, show_payment_type: true,
  show_debt: true, show_before_debt: false, show_last_payment: false,
  show_note: false, show_contractor_contact: false,
  show_cashier: true, show_barcode: false, show_qr: false,
  copies: '1',
};

const defaultNakladnoyCfg = {
  company: '', inn: '', address: '', phone: '', logo: '', logo_size: 50,
  logo_position: 'center', bank: '', account: '', mfo: '',
  director: '', accountant: '', storekeeper: '', footer_note: '',
  show_contractor_name: true, show_account_name: true,
  show_account_username: false, show_employee: true,
  show_status: false, show_number: true, show_date: true,
  show_ordering_number: true, show_measurement: true,
  show_package: false, show_quantity_in_package: false,
  show_price: true, show_discount: false, show_price_with_discount: false,
  show_currency: false, show_net_price: false, show_warehouse: false,
  show_sku: false, show_image: false, show_category: false,
  show_totals: true, show_total_national: false, show_total_quantity: false,
  show_total_quantity_package: false, show_payment_amounts: true,
  show_exact_discounts: false, show_percent_discount: false,
  show_contractor_debts: false, show_before_debts: false,
  show_last_payment: false, show_debts: false,
  show_contractor_contacts: false, show_note: false,
  show_director: true, show_accountant: false, show_storekeeper: false,
};



// ── Valyutalar tab ────────────────────────────────────────────────────────────
function CurrenciesTab() {
  const { t } = useLang();
  const [currencies, setCurrencies] = useState([]);
  const [form, setForm] = useState({ name: '', code: '', rate: '', is_default: false });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // per-row inline edit state: { [id]: rateValue }
  const [editRates, setEditRates] = useState({});
  const [updatingId, setUpdatingId] = useState(null);
  const [makingDefaultId, setMakingDefaultId] = useState(null);

  const load = () =>
    api.get('/currencies/').then(r => {
      setCurrencies(r.data);
      const init = {};
      r.data.forEach(c => { init[c.id] = String(c.rate); });
      setEditRates(init);
    }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });

  // On mount: load currencies
  useEffect(() => { load(); }, []);


  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await api.post('/currencies/', {
        name: form.name,
        code: form.code.toUpperCase(),
        rate: Number(form.rate),
        is_default: form.is_default,
      });
      setForm({ name: '', code: '', rate: '', is_default: false });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  const handleUpdateRate = async (c) => {
    const newRate = Number(editRates[c.id]);
    if (!newRate || newRate <= 0) return;
    setUpdatingId(c.id);
    try {
      await api.patch(`/currencies/${c.id}`, { rate: newRate });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setUpdatingId(null); }
  };

  const handleMakeDefault = async (c) => {
    if (c.is_default) return;
    setMakingDefaultId(c.id);
    try {
      await api.patch(`/currencies/${c.id}`, { is_default: true });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setMakingDefaultId(null); }
  };

  const handleDelete = async (id) => {
    if (!confirm(t('confirm.delete'))) return;
    try {
      await api.delete(`/currencies/${id}`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || t('common.error'));
    }
  };

  return (
    <div className="space-y-6">
      {/* Add form */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
        <h3 className="text-base font-bold text-slate-800 mb-4">{t('common.currency')} {t('common.add').toLowerCase()}</h3>
        <form onSubmit={handleAdd} className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.currencyName')}</label>
            <input
              required value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="US Dollar"
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.currencyCode')}</label>
            <input
              required value={form.code} maxLength={5}
              onChange={e => setForm({ ...form, code: e.target.value })}
              placeholder="USD"
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('common.currency')} ({t('common.sum')}ga)</label>
            <input
              required type="number" min="0.0001" step="any" value={form.rate}
              onChange={e => setForm({ ...form, rate: e.target.value })}
              placeholder="12800"
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex flex-col justify-end gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
              <input
                type="checkbox" checked={form.is_default}
                onChange={e => setForm({ ...form, is_default: e.target.checked })}
                className="w-4 h-4 accent-blue-600"
              />
              {t('settings.primaryCurrency')}
            </label>
            <button
              type="submit" disabled={saving}
              className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              {saving ? t('common.saving') : t('common.add')}
            </button>
          </div>
        </form>
        {error && <div className="mt-3 px-4 py-2 bg-red-50 text-red-600 text-sm rounded-xl">{error}</div>}
      </div>

      {/* List */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['#', t('common.currency'), t('common.currency'), t('common.rate'), t('common.active'), t('common.status'), ''].map(h => (
                <th key={h} className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {currencies.map((c, idx) => (
              <tr key={c.id} className={`transition-colors ${c.is_active ? 'hover:bg-slate-50' : 'bg-slate-50/60 opacity-60 hover:opacity-80'}`}>
                {/* # */}
                <td className="px-4 py-3.5 text-sm text-slate-400">{idx + 1}</td>

                {/* Nom + badges */}
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-slate-800">{c.name || c.code}</span>
                    {c.code === 'UZS' && (
                      <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-[10px] font-semibold rounded">{t('settings.nationalCurrency')}</span>
                    )}
                    {c.is_default && (
                      <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[10px] font-semibold rounded">{t('settings.permanent')}</span>
                    )}
                  </div>
                </td>

                {/* Kod */}
                <td className="px-4 py-3.5">
                  <span className="px-2 py-1 bg-slate-100 text-slate-700 text-xs font-bold rounded-md font-mono">{c.code}</span>
                </td>

                {/* Kurs — inline editable, UZS locked */}
                <td className="px-4 py-3.5">
                  {c.code === 'UZS' ? (
                    <span className="text-sm font-semibold text-slate-400">1</span>
                  ) : (
                    <div className="flex items-center gap-2">
                      <input
                        type="number" min="0.0001" step="any"
                        value={editRates[c.id] ?? c.rate}
                        onChange={e => setEditRates(prev => ({ ...prev, [c.id]: e.target.value }))}
                        className="w-28 px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-semibold"
                      />
                      <button
                        onClick={() => handleUpdateRate(c)}
                        disabled={updatingId === c.id}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold rounded-lg transition-colors whitespace-nowrap"
                      >
                        {updatingId === c.id ? '...' : t('settings.updateRate')}
                      </button>
                    </div>
                  )}
                </td>

                {/* Faollashtirish — interactive toggle */}
                <td className="px-4 py-3.5">
                  <button
                    type="button"
                    disabled={c.is_default}  // Asosiy valyutani o'chirish mumkin emas
                    onClick={() => api.patch(`/currencies/${c.id}`, { is_active: !c.is_active }).then(() => load()).catch(e => alert(e.response?.data?.detail || 'Xatolik'))}
                    title={c.is_default ? "Asosiy valyutani o'chirib bo'lmaydi" : (c.is_active ? "Faolsizlashtirish" : "Faollashtirish")}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${c.is_active ? 'bg-blue-500' : 'bg-slate-200'
                      } ${c.is_default ? 'cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${c.is_active ? 'translate-x-[18px]' : 'translate-x-0.5'
                      }`} />
                  </button>
                </td>

                {/* Doimiy valyuta — Asosiy qilish */}
                <td className="px-4 py-3.5">
                  {c.is_default ? (
                    <input type="checkbox" readOnly checked className="w-4 h-4 accent-blue-600 cursor-default" />
                  ) : (
                    <button
                      onClick={() => handleMakeDefault(c)}
                      disabled={makingDefaultId === c.id}
                      className="px-3 py-1.5 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-500 text-xs font-semibold rounded-lg border border-slate-200 hover:border-blue-300 transition-all disabled:opacity-50 whitespace-nowrap"
                    >
                      {makingDefaultId === c.id ? '...' : t('settings.makeDefault')}
                    </button>
                  )}
                </td>

                {/* Delete */}
                <td className="px-4 py-3.5">
                  {!c.is_default && (
                    <button
                      onClick={() => handleDelete(c.id)}
                      className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                      title="O'chirish"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {currencies.length === 0 && (
              <tr><td colSpan={7} className="px-6 py-12 text-center text-slate-400 text-sm">{t('settings.currenciesLoading')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── API Kalitlar tab ──────────────────────────────────────────────────────────
function ApiKeysTab() {
  const { t } = useLang();
  const [keys, setKeys] = useState([]);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [newToken, setNewToken] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = () => api.get('/api-keys/').then(r => setKeys(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });

  useEffect(() => { load(); }, []);

  const handleGenerate = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.post('/api-keys/', { name });
      setNewToken(data);
      setName('');
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!confirm("API kalitni o'chirishni tasdiqlaysizmi?")) return;
    await api.delete(`/api-keys/${id}`);
    load();
  };

  const copyToken = () => {
    navigator.clipboard.writeText(newToken.token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* New token banner */}
      {newToken && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-amber-800 mb-1">"{newToken.name}" — tokenni nusxalab oling!</p>
              <p className="text-xs text-amber-700 mb-3">{t('settings.tokenWarning') || "Bu token faqat bir marta ko'rsatiladi."}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 bg-white border border-amber-300 rounded-lg text-xs font-mono text-amber-900 break-all">
                  {newToken.token}
                </code>
                <button
                  onClick={copyToken}
                  className={`px-3 py-2 text-xs font-semibold rounded-lg transition-colors shrink-0 ${copied ? 'bg-emerald-500 text-white' : 'bg-amber-200 hover:bg-amber-300 text-amber-800'
                    }`}
                >
                  {copied ? 'Nusxalandi!' : 'Nusxalash'}
                </button>
              </div>
            </div>
            <button onClick={() => setNewToken(null)} className="text-amber-400 hover:text-amber-600 shrink-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Generate form */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
        <h3 className="text-base font-bold text-slate-800 mb-4">Yangi API kaliti yaratish</h3>
        <form onSubmit={handleGenerate} className="flex gap-3">
          <input
            required value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Masalan: 1C Integration, Mobile App..."
            className="flex-1 px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit" disabled={saving}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            {saving ? 'Yaratilmoqda...' : 'Yaratish'}
          </button>
        </form>
      </div>

      {/* List */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['Nom', 'Hash (sha256)', ''].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {keys.map(k => (
              <tr key={k.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 text-sm font-semibold text-slate-800">{k.name}</td>
                <td className="px-6 py-4">
                  <code className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-1 rounded">
                    {k.key_hash.slice(0, 20)}...
                  </code>
                </td>
                <td className="px-6 py-4 text-right">
                  <button
                    onClick={() => handleDelete(k.id)}
                    className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    title="O'chirish"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={3} className="px-6 py-12 text-center text-slate-400 text-sm">API kalitlar yo'q</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Info box */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
        <h4 className="text-sm font-bold text-slate-700 mb-2">API integratsiya haqida</h4>
        <ul className="space-y-1 text-xs text-slate-500">
          <li>• API kalitni so'rovlarda <code className="bg-slate-200 px-1.5 py-0.5 rounded font-mono">X-API-Key</code> sarlavhasi orqali yuboring</li>
          <li>• Kalitni xavfsiz saqlang — uni hech kim bilan baham ko'rmang</li>
          <li>• 1C integratsiyasi uchun <code className="bg-slate-200 px-1.5 py-0.5 rounded font-mono">/api/reports/1c-export</code> endpointidan foydalaning</li>
          <li>• Kalitni yo'qotsangiz — yangisini yaratib, eskisini o'chiring</li>
        </ul>
      </div>
    </div>
  );
}

// ── Password tab ─────────────────────────────────────────────────────────────
function PasswordTab() {
  const { t } = useLang();
  const [form, setForm] = useState({ new_password: '', confirm: '' });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [show, setShow] = useState({ new: false, confirm: false });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErr(''); setMsg('');
    if (form.new_password.length < 6) { setErr("Parol kamida 6 ta belgi bo'lishi kerak"); return; }
    if (form.new_password !== form.confirm) { setErr("Yangi parollar mos emas"); return; }
    setSaving(true);
    try {
      const me = await api.get('/auth/me');
      await api.patch(`/users/${me.data.id}/password`, { new_password: form.new_password });
      setMsg("Parol muvaffaqiyatli o'zgartirildi!");
      setForm({ new_password: '', confirm: '' });
    } catch (e) {
      setErr(e.response?.data?.detail || "Xatolik yuz berdi");
    } finally { setSaving(false); }
  };

  const inputCls = 'w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white';

  return (
    <div className="max-w-md space-y-6">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 space-y-5">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
          </div>
          <div>
            <h3 className="font-bold text-slate-800">Parolni o'zgartirish</h3>
            <p className="text-xs text-slate-400">Yangi parol kamida 6 ta belgi bo'lishi kerak</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Yangi parol</label>
            <div className="relative">
              <input type={show.new ? 'text' : 'password'} required value={form.new_password}
                onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))}
                placeholder="Yangi parol kiriting"
                className={inputCls} />
              <button type="button" onClick={() => setShow(s => ({ ...s, new: !s.new }))}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {show.new
                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    : <><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></>
                  }
                </svg>
              </button>
            </div>
            {form.new_password.length > 0 && (
              <div className="flex gap-1 mt-2">
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${form.new_password.length >= i * 3
                    ? (form.new_password.length >= 12 ? 'bg-emerald-500' : form.new_password.length >= 8 ? 'bg-amber-400' : 'bg-red-400')
                    : 'bg-slate-200'
                    }`} />
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Parolni tasdiqlang</label>
            <div className="relative">
              <input type={show.confirm ? 'text' : 'password'} required value={form.confirm}
                onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
                placeholder="Parolni qayta kiriting"
                className={`${inputCls} ${form.confirm && form.confirm !== form.new_password ? 'border-red-400 focus:ring-red-400' : form.confirm && form.confirm === form.new_password ? 'border-emerald-400 focus:ring-emerald-400' : ''}`} />
              <button type="button" onClick={() => setShow(s => ({ ...s, confirm: !s.confirm }))}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {show.confirm
                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    : <><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></>
                  }
                </svg>
              </button>
            </div>
            {form.confirm && form.confirm !== form.new_password && (
              <p className="text-xs text-red-500 mt-1">Parollar mos emas</p>
            )}
          </div>

          {err && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">{err}</div>}
          {msg && <div className="px-4 py-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            {msg}
          </div>}

          <button type="submit" disabled={saving}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
            {saving ? 'Saqlanmoqda...' : "Parolni o'zgartirish"}
          </button>
        </form>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
        <h4 className="text-sm font-bold text-amber-800 mb-2">Xavfsizlik bo'yicha maslahatlar</h4>
        <ul className="space-y-1 text-xs text-amber-700">
          <li>• Kamida 8 ta belgi, katta va kichik harflar ishlating</li>
          <li>• Raqam va maxsus belgilar (`@`, `#`, `!`) qo'shing</li>
          <li>• Parolni boshqalar bilan ulashmang</li>
          <li>• Har 3 oyda bir parolni yangilang</li>
        </ul>
      </div>
    </div>
  );
}

// ── Telegram Bot Tab ───────────────────────────────────────────────────────────
const TG_PATH = "M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a5.962 5.962 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.699 1.201-1.22 1.28-.106.016-.215.023-.324.023-.329 0-.655-.078-.962-.23-.09-.045-2.072-1.373-2.91-2.133-.255-.23-.55-.664-.047-1.12.13-.12 2.4-2.2 4.414-4.043.203-.186.417-.384.417-.61 0-.306-.275-.417-.463-.384l-.536.09-5.694 3.447c-.382.235-.905.39-1.424.39-.17 0-.339-.022-.505-.065L4.053 12.55c-.71-.225-.71-.708.15-1.047 2.768-1.196 9.2-3.953 11.233-4.279.172-.027.35-.042.508-.042z";

function ToggleSwitch({ checked, onChange, disabled = false }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none shrink-0
        ${checked ? 'bg-blue-500' : 'bg-slate-200'}
        ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-md transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  );
}

function AdminBotSettingsModal({ companyId, onClose }) {
  const [settings, setSettings] = useState({
    notify_instant_sales: true,
    notify_instant_finance: true,
    notify_scheduled: false,
    scheduled_time: '21:00',
    notify_expired_products: true,
    expired_days_before: 7,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get(`/companies/${companyId}/admin-bot`)
      .then(r => {
        setSettings({
          notify_instant_sales:   r.data.notify_instant_sales   ?? true,
          notify_instant_finance: r.data.notify_instant_finance ?? true,
          notify_scheduled:       r.data.notify_scheduled       ?? false,
          scheduled_time:         r.data.scheduled_time         ?? '21:00',
          notify_expired_products: r.data.notify_expired_products ?? true,
          expired_days_before:    r.data.expired_days_before    ?? 7,
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [companyId]);

  const upd = (key, val) => setSettings(s => ({ ...s, [key]: val }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/companies/${companyId}/admin-bot/settings`, settings);
      setSaved(true);
      setTimeout(() => { setSaved(false); }, 2500);
      toast.success('Sozlamalar saqlandi!');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6 bg-slate-900/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white shadow-2xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-5 flex items-center justify-between border-b border-slate-100 sticky top-0 bg-white/95 backdrop-blur z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-800">Admin Bot Sozlamalari</h2>
              <p className="text-sm text-slate-500">Bildirishnoma va hisobotlarni boshqarish</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="p-6 flex-1 overflow-y-auto bg-slate-50/50">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 rounded-full border-4 border-slate-200 border-t-blue-600 animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* === 1. Joyida yuborish === */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex flex-col">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-orange-50 text-orange-500 flex items-center justify-center shrink-0">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    </div>
                    <div>
                      <p className="text-sm font-bold text-slate-800">Tezkor Xabarlar</p>
                      <p className="text-xs text-slate-500">Amaliyot vaqtida darhol xabar</p>
                    </div>
                  </div>
                </div>

                <div className="flex-1 space-y-4">
                  <label className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-blue-100 hover:bg-blue-50/30 cursor-pointer transition-colors group">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded bg-slate-100 flex items-center justify-center text-slate-500 group-hover:bg-blue-100 group-hover:text-blue-600 transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-700">Yangi sotuv</p>
                        <p className="text-xs text-slate-400">Mijoz xarid qilganda</p>
                      </div>
                    </div>
                    <PremiumToggle checked={settings.notify_instant_sales} onChange={v => upd('notify_instant_sales', v)} color="blue" />
                  </label>

                  <label className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-blue-100 hover:bg-blue-50/30 cursor-pointer transition-colors group">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded bg-slate-100 flex items-center justify-center text-slate-500 group-hover:bg-blue-100 group-hover:text-blue-600 transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-700">Moliyaviy</p>
                        <p className="text-xs text-slate-400">Xarajat va qarz to'lovlari</p>
                      </div>
                    </div>
                    <PremiumToggle checked={settings.notify_instant_finance} onChange={v => upd('notify_instant_finance', v)} color="blue" />
                  </label>
                </div>
              </div>

              <div className="space-y-6 flex flex-col">
                {/* === 2. Kunlik hisobot === */}
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-500 flex items-center justify-center shrink-0">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                      </div>
                      <div>
                        <p className="text-sm font-bold text-slate-800">Kunlik Hisobot</p>
                        <p className="text-xs text-slate-500">Kun yakunida umumiy xulosa</p>
                      </div>
                    </div>
                    <PremiumToggle checked={settings.notify_scheduled} onChange={v => upd('notify_scheduled', v)} color="blue" />
                  </div>
                  <div className={`transition-opacity ${settings.notify_scheduled ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
                    <div className="flex items-center gap-3 bg-slate-50 rounded-lg p-3 border border-slate-100">
                      <input
                        type="time"
                        value={settings.scheduled_time}
                        onChange={e => upd('scheduled_time', e.target.value)}
                        className="px-3 py-2 rounded-md border border-slate-200 text-sm font-mono font-bold w-32 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-white"
                      />
                      <p className="text-xs text-slate-500 leading-tight">
                        Har kuni ko'rsatilgan vaqtda to'liq hisobot botga keladi
                      </p>
                    </div>
                  </div>
                </div>

                {/* === 3. Muddati tugayotgan tovarlar === */}
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-rose-50 text-rose-500 flex items-center justify-center shrink-0">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      </div>
                      <div>
                        <p className="text-sm font-bold text-slate-800">Yaroqlilik Muddati</p>
                        <p className="text-xs text-slate-500">Tugayotgan tovarlar haqida</p>
                      </div>
                    </div>
                    <PremiumToggle checked={settings.notify_expired_products} onChange={v => upd('notify_expired_products', v)} color="blue" />
                  </div>
                  
                  <div className={`transition-opacity ${settings.notify_expired_products ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
                    <p className="text-xs font-semibold text-slate-600 mb-2">Qancha oldin ogohlantirilsin?</p>
                    <div className="flex flex-wrap gap-2">
                      {[3, 5, 7, 14, 30].map(d => {
                        const isSel = settings.expired_days_before === d;
                        return (
                          <button
                            key={d}
                            onClick={() => upd('expired_days_before', d)}
                            className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors ${
                              isSel ? 'bg-blue-50 border-blue-600 text-blue-700 shadow-sm' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                            }`}
                          >
                            {d} kun
                          </button>
                        );
                      })}
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          min="1" max="180"
                          value={settings.expired_days_before}
                          onChange={e => upd('expired_days_before', parseInt(e.target.value) || 7)}
                          className="w-16 px-2 py-1.5 rounded-md text-xs font-semibold text-center focus:outline-none border border-slate-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-white"
                        />
                        <span className="text-xs text-slate-400">kun</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between bg-white rounded-b-2xl">
          {saved ? (
            <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-600">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
              Saqlandi!
            </span>
          ) : <span />}
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors"
            >
              Bekor qilish
            </button>
            <button
              onClick={handleSave}
              disabled={saving || loading}
              className="px-6 py-2 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2 shadow-sm"
            >
              {saving ? (
                <>
                  <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Saqlanmoqda
                </>
              ) : 'Saqlash'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Chiroyli iOS-style toggle
function PremiumToggle({ checked, onChange, color = 'blue' }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
        checked ? 'bg-blue-600' : 'bg-slate-200'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

function TelegramBotTab({ companyId }) {
  const [userBot, setUserBot] = useState(null);
  const [adminBot, setAdminBot] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [botType, setBotType] = useState('user');
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [showAdminSettings, setShowAdminSettings] = useState(false);

  const load = () => {
    api.get('/companies').then(r => {
      if (r.data?.length > 0) {
        const co = r.data[0];
        if (co.tg_bot_token) {
           setUserBot({ bot_token: co.tg_bot_token, bot_username: co.tg_bot_username });
        } else {
           setUserBot(null);
        }
      }
    }).catch(e => toast.error(e.response?.data?.detail || e.message));

    if (companyId) {
      api.get(`/companies/${companyId}/admin-bot`).then(r => {
        if (r.data?.bot_username) {
          setAdminBot(r.data);
        } else {
          setAdminBot(null);
        }
      }).catch(e => {
         if (e.response?.status !== 404) {
            toast.error(e.response?.data?.detail || e.message);
         } else {
           setAdminBot(null);
         }
      });
    }
  };

  useEffect(() => { load(); }, [companyId]);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!companyId || !token.trim()) return;

    if (botType === "admin") {
      setSaving(true); setErr('');
      try {
        const res = await api.put(`/companies/${companyId}/admin-bot`, { bot_token: token });
        toast.success('Admin bot ulandi!');
        setAdminBot(res.data);
        setToken('');
        setShowModal(false);
      } catch (error) {
        setErr(error.response?.data?.detail || 'Xatolik yuz berdi');
      } finally {
        setSaving(false);
      }
    } else {
      setSaving(true); setErr('');
      try {
        const res = await api.put(`/companies/${companyId}`, { tg_bot_token: token });
        toast.success('Mijoz boti ulandi!');
        setUserBot({ bot_token: res.data?.tg_bot_token, bot_username: res.data?.tg_bot_username });
        setToken('');
        setShowModal(false);
      } catch (error) {
        setErr(error.response?.data?.detail || 'Xatolik yuz berdi');
      } finally {
        setSaving(false);
      }
    }
  };

  const handleDelete = async (type) => {
    if (!confirm("Tasdiqlaysizmi? Bot uzilib, xabarlar to'xtatiladi.")) return;
    try {
      if (type === 'admin') {
         await api.delete(`/companies/${companyId}/admin-bot`);
         setAdminBot(null);
         setShowAdminSettings(false);
         toast.success("Admin bot uzib qo'yildi.");
      } else {
         await api.put(`/companies/${companyId}`, { tg_bot_token: null });
         setUserBot(null);
         toast.success("Mijoz bot uzib qo'yildi.");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik');
    }
  };

  return (
    <div className="space-y-6">
      {!companyId && (
        <div className="flex items-center justify-center py-16">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"/>
            <p className="text-sm text-slate-400">Yuklanmoqda...</p>
          </div>
        </div>
      )}
      {companyId && (
      <><div>
        <h3 className="text-base font-bold text-slate-800">Telegram Botlar</h3>
        <p className="text-xs text-slate-400 mt-0.5">Mijozlar va rahbarlar uchun botlarni alohida boshqarish</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">

        {/* ── Mijoz boti ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h4 className="font-bold text-slate-800">Mijoz boti</h4>
              <p className="text-xs text-slate-400 mt-0.5">Chegirma, aksiya va xarid xabarlarini yuborish uchun</p>
            </div>
            {!userBot?.bot_username ? (
              <button
                onClick={() => { setBotType('user'); setShowModal(true); setErr(''); setToken(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 text-xs font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                Ulash
              </button>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-md">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />Faol
              </span>
            )}
          </div>
          {userBot?.bot_username ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center text-blue-500">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
                </div>
                <div className="flex-1 min-w-0">
                  <a href={'https://t.me/' + userBot.bot_username} target="_blank" rel="noreferrer" className="text-sm font-bold text-blue-600 hover:underline">@{userBot.bot_username}</a>
                </div>
              </div>
              <div className="flex gap-2 pt-2 border-t border-slate-50">
                <button onClick={() => { setBotType('user'); setShowModal(true); setErr(''); setToken(''); }}
                  className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg transition-colors">Yangilash</button>
                <button onClick={() => handleDelete('user')}
                  className="flex-1 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold rounded-lg transition-colors">O'chirish</button>
              </div>
            </div>
          ) : (
            <div className="py-6 flex flex-col items-center justify-center border-2 border-dashed border-slate-100 rounded-xl bg-slate-50/50 mt-4">
              <svg className="w-8 h-8 text-slate-300 mb-2" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
              <p className="text-sm font-medium text-slate-500">Bot ulanmagan</p>
            </div>
          )}
        </div>

        {/* ── Admin boti ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h4 className="font-bold text-slate-800">Admin boti</h4>
              <p className="text-xs text-slate-400 mt-0.5">Rahbarlar uchun hisobot va ogohlantirishlar</p>
            </div>
            {!adminBot?.bot_username ? (
              <button
                onClick={() => { setBotType('admin'); setShowModal(true); setErr(''); setToken(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 text-xs font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                Ulash
              </button>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-md">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />Faol
              </span>
            )}
          </div>

          {adminBot?.bot_username ? (
            <div className="space-y-0">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center text-blue-500">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
                </div>
                <div className="flex-1 min-w-0">
                  <a href={'https://t.me/' + adminBot.bot_username} target="_blank" rel="noreferrer" className="text-sm font-bold text-blue-600 hover:underline">@{adminBot.bot_username}</a>
                </div>
              </div>

              <div className="flex gap-2 pt-3 mt-3 border-t border-slate-50">
                <button
                  onClick={() => setShowAdminSettings(v => !v)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-semibold rounded-lg transition-colors
                    ${showAdminSettings ? 'bg-blue-600 text-white' : 'bg-blue-50 text-blue-600 hover:bg-blue-100'}`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Sozlamalar
                </button>
                <button onClick={() => { setBotType('admin'); setShowModal(true); setErr(''); setToken(''); }}
                  className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg transition-colors">Yangilash</button>
                <button onClick={() => handleDelete('admin')}
                  className="flex-1 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold rounded-lg transition-colors">O'chirish</button>
              </div>

              {showAdminSettings && (
                <AdminBotSettingsModal
                  companyId={companyId}
                  onClose={() => setShowAdminSettings(false)}
                />
              )}
            </div>
          ) : (
            <div className="py-6 flex flex-col items-center justify-center border-2 border-dashed border-slate-100 rounded-xl bg-slate-50/50 mt-4">
              <svg className="w-8 h-8 text-slate-300 mb-2" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
              <p className="text-sm font-medium text-slate-500">Bot ulanmagan</p>
            </div>
          )}
        </div>
      </div>
      </>)}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={e => { if (e.target === e.currentTarget) setShowModal(false); }}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-blue-100 rounded-xl flex items-center justify-center text-blue-600">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
                </div>
                <h3 className="font-bold text-slate-800">Bot ulash ({botType === 'admin' ? 'Admin' : 'Mijoz'})</h3>
              </div>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-[13px] font-bold text-slate-700 mb-1.5">Bot Token</label>
                <input
                  type="text" required value={token}
                  onChange={e => setToken(e.target.value)}
                  placeholder="1234567890:AAH_abcxyz..."
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono transition-all"
                />
                <p className="text-xs text-slate-400 mt-1.5">@BotFather orqali olingan API tokenni kiriting</p>
              </div>
              {err && (
                <div className="p-3 bg-red-50 rounded-xl flex gap-2 text-red-600 text-sm">
                  <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p>{err}</p>
                </div>
              )}
              <button
                type="submit" disabled={saving || !token.trim()}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold text-sm rounded-xl transition-colors"
              >
                {saving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}


function ReceiptPreview({ cfg, mm }) {
  const { t } = useLang();
  const narrow = mm === 58;

  const lineSolid = { borderTop: '1.5px solid #000', margin: '6px 0' };
  const lineDashed = { borderTop: '1.5px dashed #000', margin: '6px 0' };

  return (
    <div className={`${narrow ? 'w-48' : 'w-64'} bg-white border border-slate-300 shadow-xl rounded-sm mx-auto font-mono leading-snug text-black font-bold`}
      style={{ fontSize: narrow ? '10px' : '11.5px', padding: '10px' }}>

      {cfg.logo && <div className="text-center mb-1"><img src={cfg.logo} alt="logo" style={{ height: `${Math.round((cfg.logo_size || 40) * 0.6)}px`, maxWidth: '100%', objectFit: 'contain', margin: '0 auto' }} /></div>}
      {cfg.company ? <div className="text-center mb-1.5" style={{ fontSize: '13px' }}>{cfg.company}</div> : null}
      {cfg.address && <div className="text-center mb-1.5">{cfg.address}</div>}
      {cfg.phone && <div className="text-center mb-1.5">Tel: {cfg.phone}</div>}
      {cfg.inn && <div className="text-center mb-1.5">STIR: {cfg.inn}</div>}
      {cfg.header && <div className="text-center mb-1.5">{cfg.header}</div>}

      <div className="flex justify-between">
        <span>Chek:</span>
        <span>#00001</span>
      </div>
      <div className="flex justify-between">
        <span>Kassir:</span>
        <span>{cfg.show_cashier ? 'Sardor' : 'Sardor'}</span>
      </div>
      <div className="flex justify-between">
        <span>Sana:</span>
        <span>15.06.2026 09:56</span>
      </div>

      <div style={lineDashed}></div>
      <div className="flex justify-between">
        <span>Mijoz:</span>
        <span>AKMAL AKA</span>
      </div>
      <div style={lineDashed}></div>

      {/* Items */}
      <div>1. Mahsulot A</div>
      <div className="flex justify-between">
        <span>2 x 25,000</span>
        <span>50,000</span>
      </div>
      <div style={lineDashed}></div>

      <div>2. Mahsulot B</div>
      <div className="flex justify-between">
        <span>1 x 30,000</span>
        <span>30,000</span>
      </div>
      <div style={lineDashed}></div>

      <div className="flex justify-between">
        <span>Jami:</span>
        <span>2 xil mahsulot</span>
      </div>
      <div style={lineSolid}></div>

      <div className="flex justify-between">
        <span>JAMI:</span>
        <span>80,000 so'm</span>
      </div>
      <div style={lineDashed}></div>

      <div className="flex justify-between">
        <span>To'lov:</span>
        <span>100,000 so'm</span>
      </div>
      <div style={lineDashed}></div>

      <div className="flex justify-between">
        <span>Oldingi qarz:</span>
        <span>0 so'm</span>
      </div>
      <div className="flex justify-between">
        <span>Qarzga:</span>
        <span>0 so'm</span>
      </div>
      <div style={lineSolid}></div>

      <div className="flex justify-between">
        <span>Jami qarz:</span>
        <span>0 so'm</span>
      </div>
      <br />
      <div className="flex justify-between">
        <span>Qaytim:</span>
        <span>20,000 so'm</span>
      </div>

      {cfg.show_qr && (
        <>
          <div style={lineDashed}></div>
          <div className="text-center">
            <div className="w-12 h-12 bg-slate-100 border border-slate-200 mx-auto grid" style={{ gridTemplateColumns: 'repeat(5,1fr)', gap: '1px', padding: '3px' }}>
              {Array.from({ length: 25 }).map((_, i) => <div key={i} className={i % 3 === 0 ? 'bg-slate-800' : 'bg-white'} />)}
            </div>
          </div>
        </>
      )}

      <div className="text-center mt-3">{cfg.footer || 'Xaridingiz uchun raxmat!'}</div>
    </div>
  );
}

// ── Nakladnoy preview ─────────────────────────────────────────────────────────
function NakladnoyPreview({ cfg }) {
  const sh = (key, def = true) => cfg[key] !== undefined ? cfg[key] : def;
  const logoPos = cfg.logo_position || 'center';

  const cols = [
    { key: 'show_ordering_number', label: '№' },
    { label: 'Mahsulot nomi', always: true },
    { key: 'show_measurement', label: "O'lchov" },
    { key: 'show_warehouse', label: 'Ombor' },
    { key: 'show_sku', label: 'SKU' },
    { key: 'show_price', label: 'Narxi' },
    { key: 'show_discount', label: 'Chegirma' },
    { key: 'show_price_with_discount', label: "Cheg.narx" },
    { key: 'show_net_price', label: 'Sof narx' },
    { key: 'show_currency', label: 'Val.' },
    { label: 'Soni', always: true },
    { label: 'Jami', always: true },
  ].filter(col => col.always || sh(col.key, col.key === 'show_ordering_number' || col.key === 'show_price'));

  const sampleItems = [
    { n: 1, name: 'Mahsulot A', unit: "dona", wh: 'Asosiy', sku: 'A001', price: '25,000', disc: '-', pw: '25,000', net: '50,000', cur: "so'm", qty: 2, total: '50,000' },
    { n: 2, name: 'Mahsulot B', unit: "kg", wh: 'Filial', sku: 'B002', price: '30,000', disc: '-', pw: '30,000', net: '30,000', cur: "so'm", qty: 1, total: '30,000' },
  ];
  const colKeys = ['show_ordering_number', 'always_name', 'show_measurement', 'show_warehouse', 'show_sku', 'show_price', 'show_discount', 'show_price_with_discount', 'show_net_price', 'show_currency', 'always_qty', 'always_total'];
  const sampleVals = { show_ordering_number: 'n', always_name: 'name', show_measurement: 'unit', show_warehouse: 'wh', show_sku: 'sku', show_price: 'price', show_discount: 'disc', show_price_with_discount: 'pw', show_net_price: 'net', show_currency: 'cur', always_qty: 'qty', always_total: 'total' };

  return (
    <div className="bg-white border border-slate-300 shadow-lg rounded p-3 w-full max-w-sm mx-auto text-[7px] font-mono text-slate-700 leading-snug">
      {cfg.logo && (
        <div style={{ textAlign: logoPos, marginBottom: '4px' }}>
          <img src={cfg.logo} alt="logo" style={{ height: `${Math.round((cfg.logo_size || 50) * 0.35)}px`, maxWidth: '70px', objectFit: 'contain', display: 'inline-block' }} />
        </div>
      )}
      <div className="text-center border-b border-slate-300 pb-1.5 mb-1.5">
        <div className="font-bold text-[9px]">{cfg.company || 'KORXONA NOMI'}</div>
        {cfg.inn && <div>STIR: {cfg.inn}</div>}
        {cfg.address && <div>{cfg.address}</div>}
        {cfg.phone && <div>Tel: {cfg.phone}</div>}
        {cfg.bank && <div>Bank: {cfg.bank}{cfg.mfo ? ` | MFO: ${cfg.mfo}` : ''}</div>}
      </div>

      <div className="text-center font-bold text-[8px] mb-1">
        NAKLADNOY № {sh('show_number') ? '___' : ''} {sh('show_date') ? '/ 17.03.2025' : ''}
      </div>

      {/* Info satrlari */}
      <div className="text-[7px] mb-1 space-y-0.5">
        {sh('show_contractor_name') && <div><b>Mijoz:</b> Abdullayev Jasur</div>}
        {sh('show_account_name') && <div><b>Filial:</b> Asosiy filial</div>}
        {sh('show_employee') && <div><b>Xodim:</b> Sardor</div>}
        {sh('show_status') && <div><b>Holat:</b> Tasdiqlangan</div>}
      </div>

      <table className="w-full border-collapse mb-1.5" style={{ borderSpacing: 0 }}>
        <thead>
          <tr>{cols.map((col, i) => <th key={i} className="border border-slate-400 px-0.5 py-0.5 text-center bg-slate-100 text-[6px]">{col.label}</th>)}</tr>
        </thead>
        <tbody>
          {sampleItems.map((item, ri) => (
            <tr key={ri}>
              {cols.map((col, ci) => {
                const ck = colKeys[['show_ordering_number', 'always_name', 'show_measurement', 'show_warehouse', 'show_sku', 'show_price', 'show_discount', 'show_price_with_discount', 'show_net_price', 'show_currency', 'always_qty', 'always_total'].indexOf(col.key || (col.always && (ci === 0 ? 'show_ordering_number' : ci === cols.length - 1 ? 'always_total' : 'always_name')))];
                const allCols = ['show_ordering_number', 'always_name', 'show_measurement', 'show_warehouse', 'show_sku', 'show_price', 'show_discount', 'show_price_with_discount', 'show_net_price', 'show_currency', 'always_qty', 'always_total'];
                const origIdx = allCols.indexOf(col.key || (col.label === 'Mahsulot nomi' ? 'always_name' : col.label === 'Soni' ? 'always_qty' : 'always_total'));
                const vkey = sampleVals[allCols[origIdx]];
                return <td key={ci} className="border border-slate-300 px-0.5 py-0.5 text-center">{item[vkey]}</td>;
              })}
            </tr>
          ))}
          <tr>
            <td colSpan={cols.length - 1} className="border border-slate-300 px-0.5 py-0.5 text-right font-bold">JAMI:</td>
            <td className="border border-slate-300 px-0.5 py-0.5 text-center font-bold">80,000</td>
          </tr>
        </tbody>
      </table>

      {/* Jami bo'lim */}
      {sh('show_totals') && (
        <div className="text-[7px] space-y-0.5 border-t border-slate-200 pt-1 mb-1">
          <div className="flex justify-between"><span>JAMI:</span><span className="font-bold">80,000 so'm</span></div>
          {sh('show_payment_amounts') && <div className="flex justify-between"><span>To'langan:</span><span>100,000 so'm</span></div>}
          {sh('show_contractor_debts') && <div className="flex justify-between text-red-600"><span>Qarz:</span><span>0 so'm</span></div>}
          {sh('show_exact_discounts') && <div className="flex justify-between"><span>Chegirma:</span><span>-5,000 so'm</span></div>}
          {sh('show_total_quantity') && <div className="flex justify-between"><span>Jami miqdor:</span><span>3</span></div>}
        </div>
      )}

      {/* Izoh */}
      {sh('show_note') && <div className="text-[7px] text-slate-500 italic mb-1">Izoh: Toshkentga yetkazish</div>}

      {/* Imzolar */}
      <div className="flex justify-between mt-2 pt-1.5 border-t border-slate-300 text-[7px] flex-wrap gap-1">
        {sh('show_director') && <div>Direktor: {cfg.director || '__________'}</div>}
        {sh('show_accountant') && <div>Buxgalter: {cfg.accountant || '__________'}</div>}
        {sh('show_storekeeper') && <div>Omborchi: {cfg.storekeeper || '__________'}</div>}
      </div>
      {cfg.footer_note && <div className="mt-1 italic text-slate-500 text-center text-[7px]">{cfg.footer_note}</div>}
    </div>
  );
}

// ── Receipt field style (module-level so components don't recreate it) ─────────
const RIC = 'w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white';

const SUB_TABS = [
  { id: '58', label: 'Chek 58mm', icon: '🧾' },
  { id: '80', label: 'Chek 80mm', icon: '🧾' },
  { id: 'nak', label: 'Nakladnoy (A4)', icon: '📄' },
];

// ── These must be module-level functions — NOT defined inside ReceiptTab ───────
function LogoUpload({ logo, size, onUpload, onRemove, onSizeChange, positionPicker, position, onPositionChange }) {
  const { t } = useLang();
  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 500 * 1024) { alert("Logo hajmi 500KB dan oshmasin"); return; }
    const reader = new FileReader();
    reader.onload = () => onUpload(reader.result);
    reader.readAsDataURL(file);
  };

  return (
    <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-3">
      <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">Logo (chekda chiqariladi)</p>
      <div className="flex items-start gap-4">
        {/* Thumbnail — shows at selected size */}
        <div className="w-20 h-16 border-2 border-dashed border-slate-300 rounded-xl flex items-center justify-center bg-white shrink-0 overflow-hidden">
          {logo
            ? <img src={logo} alt="logo" style={{ height: `${Math.min(size || 40, 60)}px`, maxWidth: '74px', objectFit: 'contain' }} />
            : <span className="text-2xl">🖼</span>
          }
        </div>
        <div className="flex-1 space-y-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="file" accept="image/*" className="hidden" onChange={handleFile} />
            <span className="inline-flex items-center gap-1.5 px-3 py-2 bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-700 text-xs font-semibold rounded-lg transition-colors">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
              Rasm yuklash
            </span>
          </label>
          {logo && (
            <button onClick={onRemove} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 border border-red-200 rounded-lg transition-colors">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              Logoni olib tashlash
            </button>
          )}
          {/* Size slider */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-500 whitespace-nowrap">Hajmi:</span>
            <input type="range" min={16} max={100} step={4}
              value={size || 40}
              onChange={e => onSizeChange(Number(e.target.value))}
              className="flex-1 h-1.5 accent-blue-500 cursor-pointer"
            />
            <span className="text-[11px] font-mono text-slate-600 w-8 text-right">{size || 40}px</span>
          </div>
          {positionPicker && (
            <div>
              <p className="text-[11px] text-slate-500 mb-1">Logo holati:</p>
              <div className="flex gap-1">
                {[['left', '◀ Chap'], ['center', '▪ Markaz'], ['right', "O'ng ▶"]].map(([v, l]) => (
                  <button key={v} onClick={() => onPositionChange(v)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg border transition-all ${position === v ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:border-blue-300'
                      }`}>{l}
                  </button>
                ))}
              </div>
            </div>
          )}
          <p className="text-[10px] text-slate-400">JPG, PNG, SVG — max 500KB</p>
        </div>
      </div>
    </div>
  );
}

function ReceiptFields({ cfg, upd }) {
  const { t } = useLang();
  return (
    <div className="space-y-4">
      {/* Logo upload (centered for thermal) */}
      <LogoUpload
        logo={cfg.logo}
        size={cfg.logo_size || 40}
        onUpload={(v) => upd('logo', v)}
        onRemove={() => upd('logo', '')}
        onSizeChange={(v) => upd('logo_size', v)}
        positionPicker={false}
      />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">Korxona nomi *</label>
          <input value={cfg.company} onChange={e => upd('company', e.target.value)} placeholder="Masalan: Farrukh Do'koni" className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.phone') || 'Telefon'}</label>
          <input value={cfg.phone} onChange={e => upd('phone', e.target.value)} placeholder="+998 90 000 00 00" className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.address') || 'Manzil'}</label>
          <input value={cfg.address} onChange={e => upd('address', e.target.value)} placeholder="Shahar, ko'cha, uy" className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">STIR / INN</label>
          <input value={cfg.inn} onChange={e => upd('inn', e.target.value)} placeholder="123456789" className={RIC} />
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1">Bosh satr (sarlavha)</label>
        <input value={cfg.header} onChange={e => upd('header', e.target.value)} placeholder="Masalan: Toshkent shahri, Chilonzor t." className={RIC} />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1">Oxirgi satr (tagso'z)</label>
        <input value={cfg.footer} onChange={e => upd('footer', e.target.value)} placeholder="Xaridingiz uchun rahmat!" className={RIC} />
      </div>
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">Chekda ko'rsatiladigan maydonlar</p>

        {[
          {
            label: 'Sarlavha bo\'limi',
            fields: [
              ['show_number', 'Chek raqami'],
              ['show_date', 'Sana va vaqt'],
              ['show_status', 'Holat'],
              ['show_account_name', 'Filial nomi'],
              ['show_employee', 'Xodim / Kassir ismi'],
            ],
          },
          {
            label: 'Mahsulot qatori',
            fields: [
              ['show_ordering_number', '№ tartib raqami'],
              ['show_unit', "O'lchov birligi"],
              ['show_warehouse', 'Ombor nomi'],
              ['show_package', 'Paket ma\'lumoti'],
              ['show_price_per_unit', 'Birlik narxi'],
              ['show_discount', 'Chegirma'],
              ['show_price_with_discount', 'Chegirmali narx'],
              ['show_currency', 'Valyuta nomi'],
            ],
          },
          {
            label: 'Jami bo\'lim',
            fields: [
              ['show_total', 'Jami summa'],
              ['show_net_price', 'Sof narx'],
              ['show_total_quantity', 'Jami miqdor'],
              ['show_total_national', "Milliy valyutada jami"],
              ['show_payment_type', "To'lov turi va summasi"],
            ],
          },
          {
            label: 'Qarz bo\'limi',
            fields: [
              ['show_debt', 'Joriy qarzdorlik'],
              ['show_before_debt', 'Oldingi qarz'],
              ['show_last_payment', "Oxirgi to'lov"],
            ],
          },
          {
            label: 'Qo\'shimcha',
            fields: [
              ['show_note', 'Izoh'],
              ['show_contractor_contact', 'Mijoz kontakti'],
              ['show_cashier', 'Kassir imzosi satri'],
              ['show_barcode', 'Barkod'],
              ['show_qr', 'QR kod'],
            ],
          },
        ].map(group => (
          <div key={group.label}>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">{group.label}</p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              {group.fields.map(([key, label]) => (
                <label key={key} className="flex items-center gap-2.5 cursor-pointer select-none">
                  <div onClick={() => upd(key, !cfg[key])}
                    className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${cfg[key] ? 'bg-blue-500' : 'bg-slate-300'}`}>
                    <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${cfg[key] ? 'translate-x-4' : ''}`} />
                  </div>
                  <span className="text-sm text-slate-700">{label}</span>
                </label>
              ))}
            </div>
          </div>
        ))}

        <div className="flex items-center gap-2 pt-2 border-t border-slate-200">
          <span className="text-xs font-semibold text-slate-500">Nusxalar soni:</span>
          <select value={cfg.copies} onChange={e => upd('copies', e.target.value)}
            className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
            {['1', '2', '3'].map(n => <option key={n} value={n}>{n} ta</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}

function ToggleGroup({ title, fields, cfg, upd }) {
  return (
    <div>
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">{title}</p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        {fields.map(([key, label]) => (
          <label key={key} className="flex items-center gap-2.5 cursor-pointer select-none">
            <div onClick={() => upd(key, !cfg[key])}
              className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${cfg[key] ? 'bg-blue-500' : 'bg-slate-300'}`}>
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${cfg[key] ? 'translate-x-4' : ''}`} />
            </div>
            <span className="text-sm text-slate-700">{label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function NakladnoyFields({ cfg, upd }) {
  const { t } = useLang();
  return (
    <div className="space-y-4">
      <LogoUpload
        logo={cfg.logo} size={cfg.logo_size || 50}
        onUpload={(v) => upd('logo', v)} onRemove={() => upd('logo', '')}
        onSizeChange={(v) => upd('logo_size', v)}
        positionPicker={true} position={cfg.logo_position || 'center'}
        onPositionChange={(v) => upd('logo_position', v)}
      />

      {/* Korxona ma'lumotlari */}
      <div className="grid grid-cols-2 gap-3">
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">Korxona nomi *</label>
          <input value={cfg.company} onChange={e => upd('company', e.target.value)} placeholder="MCHJ / YaTT nomi" className={RIC} /></div>
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">STIR / INN</label>
          <input value={cfg.inn} onChange={e => upd('inn', e.target.value)} placeholder="123456789" className={RIC} /></div>
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">Manzil</label>
          <input value={cfg.address} onChange={e => upd('address', e.target.value)} className={RIC} /></div>
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">Telefon</label>
          <input value={cfg.phone} onChange={e => upd('phone', e.target.value)} className={RIC} /></div>
      </div>

      {/* Bank */}
      <div className="border-t border-slate-100 pt-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Bank rekvizitlari</p>
        <div className="grid grid-cols-3 gap-3">
          <div><label className="block text-xs font-semibold text-slate-500 mb-1">Bank nomi</label>
            <input value={cfg.bank} onChange={e => upd('bank', e.target.value)} placeholder="NBU, Kapitalbank..." className={RIC} /></div>
          <div><label className="block text-xs font-semibold text-slate-500 mb-1">Hisob raqam</label>
            <input value={cfg.account} onChange={e => upd('account', e.target.value)} placeholder="2020..." className={RIC} /></div>
          <div><label className="block text-xs font-semibold text-slate-500 mb-1">MFO</label>
            <input value={cfg.mfo} onChange={e => upd('mfo', e.target.value)} placeholder="01001" className={RIC} /></div>
        </div>
      </div>

      {/* Imzo */}
      <div className="border-t border-slate-100 pt-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Imzo egalari</p>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-semibold text-slate-500">Direktor</label>
              <div onClick={() => upd('show_director', !cfg.show_director)}
                className={`relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0 ${cfg.show_director ? 'bg-blue-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${cfg.show_director ? 'translate-x-3' : ''}`} />
              </div>
            </div>
            <input value={cfg.director} onChange={e => upd('director', e.target.value)} placeholder="F.I.Sh." className={RIC} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-semibold text-slate-500">Bosh buxgalter</label>
              <div onClick={() => upd('show_accountant', !cfg.show_accountant)}
                className={`relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0 ${cfg.show_accountant ? 'bg-blue-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${cfg.show_accountant ? 'translate-x-3' : ''}`} />
              </div>
            </div>
            <input value={cfg.accountant} onChange={e => upd('accountant', e.target.value)} placeholder="F.I.Sh." className={RIC} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-semibold text-slate-500">Omborchi</label>
              <div onClick={() => upd('show_storekeeper', !cfg.show_storekeeper)}
                className={`relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0 ${cfg.show_storekeeper ? 'bg-blue-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${cfg.show_storekeeper ? 'translate-x-3' : ''}`} />
              </div>
            </div>
            <input value={cfg.storekeeper} onChange={e => upd('storekeeper', e.target.value)} placeholder="F.I.Sh." className={RIC} />
          </div>
        </div>
      </div>

      <div><label className="block text-xs font-semibold text-slate-500 mb-1">Izoh (ixtiyoriy)</label>
        <input value={cfg.footer_note} onChange={e => upd('footer_note', e.target.value)} placeholder="Qo'shimcha eslatma..." className={RIC} /></div>

      {/* Togglelar */}
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">A4 da ko'rsatiladigan maydonlar</p>
        <ToggleGroup title="Sarlavha bo'limi" cfg={cfg} upd={upd} fields={[
          ['show_contractor_name', 'Mijoz ismi'],
          ['show_account_name', 'Filial nomi'],
          ['show_account_username', 'Foydalanuvchi'],
          ['show_employee', 'Xodim ismi'],
          ['show_status', 'Holat'],
          ['show_number', 'Hujjat raqami'],
          ['show_date', 'Sana'],
        ]} />
        <ToggleGroup title="Jadval ustunlari" cfg={cfg} upd={upd} fields={[
          ['show_ordering_number', '№ tartib raqami'],
          ['show_measurement', "O'lchov birligi"],
          ['show_package', 'Paket nomi'],
          ['show_quantity_in_package', 'Paketdagi miqdor'],
          ['show_price', 'Narx'],
          ['show_discount', 'Chegirma'],
          ['show_price_with_discount', 'Chegirmali narx'],
          ['show_currency', 'Valyuta'],
          ['show_net_price', 'Sof narx'],
          ['show_warehouse', 'Ombor nomi'],
          ['show_sku', 'SKU (Artikul)'],
          ['show_image', 'Mahsulot rasmi'],
          ['show_category', 'Kategoriya'],
        ]} />
        <ToggleGroup title="Jami bo'lim" cfg={cfg} upd={upd} fields={[
          ['show_totals', 'Jami summa'],
          ['show_total_national', "Milliy valyutada jami"],
          ['show_total_quantity', 'Jami miqdor'],
          ['show_total_quantity_package', 'Jami paket miqdori'],
          ['show_payment_amounts', "To'lov summasi"],
          ['show_exact_discounts', 'Chegirma summasi'],
          ['show_percent_discount', '% chegirma'],
        ]} />
        <ToggleGroup title="Qarz bo'limi" cfg={cfg} upd={upd} fields={[
          ['show_contractor_debts', 'Joriy qarzdorlik'],
          ['show_before_debts', 'Oldingi qarz'],
          ['show_last_payment', "Oxirgi to'lov"],
          ['show_debts', 'Umumiy qarzlar'],
        ]} />
        <ToggleGroup title="Qo'shimcha" cfg={cfg} upd={upd} fields={[
          ['show_contractor_contacts', 'Mijoz kontaktlari'],
          ['show_note', 'Izoh'],
        ]} />
      </div>
    </div>
  );
}

// ── Receipt / Nakladnoy settings tab ──────────────────────────────────────────
function ReceiptTab() {
  const { t } = useLang();
  const [loading, setLoading] = useState(true);
  const [sub, setSub] = useState('58');
  const [cfg58, setCfg58] = useState({ ...defaultReceiptCfg });
  const [cfg80, setCfg80] = useState({ ...defaultReceiptCfg, show_qr: true });
  const [cfgNak, setCfgNak] = useState({ ...defaultNakladnoyCfg });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get('/companies/me/receipt_templates')
      .then(r => {
        const d = r.data?.receipt_templates || {};
        const r58 = d.r58 ? { ...defaultReceiptCfg, ...d.r58 } : undefined;
        const r80 = d.r80 ? { ...defaultReceiptCfg, show_qr: true, ...d.r80 } : undefined;
        const nak = d.nak ? { ...defaultNakladnoyCfg, ...d.nak } : undefined;
        if (r58) setCfg58(r58);
        if (r80) setCfg80(r80);
        if (nak) setCfgNak(nak);
        // localStorage ni sinxronlashtirish (barcha print funksiyalar shu yerdan o'qiydi)
        const stored = {};
        if (r58) stored.r58 = r58;
        if (r80) stored.r80 = r80;
        if (nak) stored.nak = nak;
        if (Object.keys(stored).length) {
          // ✅ company_id bilan saqlash
          saveReceiptSettings(stored);
        }
      })
      .catch(e => console.error('Receipt templates load error:', e))
      .finally(() => setLoading(false));
  }, []);

  const upd58 = (k, v) => setCfg58(p => ({ ...p, [k]: v }));
  const upd80 = (k, v) => setCfg80(p => ({ ...p, [k]: v }));
  const updNak = (k, v) => setCfgNak(p => ({ ...p, [k]: v }));

  const handleSave = () => {
    // Company ma'lumotlarini barcha shablonlarga sinxronlaymiz:
    // Foydalanuvchi istalgan shablonda phone/address/company/inn kiritsа —
    // barcha shablonlarga avtomatik nusxa ko'chiriladi.
    const COMPANY_FIELDS = ['company', 'address', 'phone', 'inn', 'logo', 'logo_size', 'footer'];
    const activeCompany = {};
    for (const field of COMPANY_FIELDS) {
      activeCompany[field] =
        (sub === '58' ? cfg58 : sub === '80' ? cfg80 : cfgNak)[field] ||
        cfg58[field] || cfg80[field] || cfgNak[field] || '';
    }
    const synced58 = { ...cfg58, ...activeCompany };
    const synced80 = { ...cfg80, ...activeCompany };
    const syncedNak = { ...cfgNak, ...activeCompany };

    api.put('/companies/me/receipt_templates', {
      receipt_templates: { r58: synced58, r80: synced80, nak: syncedNak }
    }).then(() => {
      setCfg58(synced58);
      setCfg80(synced80);
      setCfgNak(syncedNak);
      saveReceiptSettings({ r58: synced58, r80: synced80, nak: syncedNak });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    }).catch(e => alert(e.response?.data?.detail || "Saqlashda xatolik yuz berdi"));
  };

  const currentCfg = sub === '58' ? cfg58 : sub === '80' ? cfg80 : cfgNak;
  const updFn = sub === '58' ? upd58 : sub === '80' ? upd80 : updNak;

  if (loading) return <div className="text-sm text-slate-500 animate-pulse py-10 px-4">Shablonlar serverdan yuklanmoqda...</div>;

  return (
    <div className="space-y-4">
      {/* Sub-tab bar */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {SUB_TABS.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${sub === t.id ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            <span>{t.icon}</span>{t.label}
          </button>
        ))}
      </div>

      {/* Two-column: form + preview */}
      <div className="flex gap-5 items-start">
        {/* Form */}
        <div className="flex-1 min-w-0 bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
          {sub !== 'nak'
            ? <ReceiptFields cfg={currentCfg} upd={updFn} />
            : <NakladnoyFields cfg={currentCfg} upd={updFn} />
          }
        </div>

        {/* Preview */}
        <div className="w-72 shrink-0">
          <div className="bg-slate-800 rounded-2xl p-5">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide text-center mb-4">
              {sub === '58' ? '58mm chek ko\'rinishi' : sub === '80' ? '80mm chek ko\'rinishi' : 'Nakladnoy ko\'rinishi'}
            </p>
            {sub === 'nak'
              ? <NakladnoyPreview cfg={cfgNak} />
              : <ReceiptPreview cfg={currentCfg} mm={Number(sub)} />
            }
          </div>
        </div>
      </div>

      {/* Save button */}
      <div className="flex items-center justify-end gap-3 pt-2">
        {saved && (
          <span className="flex items-center gap-1.5 text-sm text-emerald-600 font-semibold">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            Saqlandi!
          </span>
        )}
        <button onClick={handleSave}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm rounded-xl transition-colors flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
          Sozlamalarni saqlash
        </button>
      </div>
    </div>
  );
}

// ── Filiallar tab ────────────────────────────────────────────────────────────
function BranchesTab() {
  const { t } = useLang();
  const [branches, setBranches] = useState([]);
  const [form, setForm] = useState({ name: '', address: '', phone: '' });
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = () => api.get('/branches').then(r => setBranches(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  useEffect(() => { load(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await api.post('/branches', form);
      setForm({ name: '', address: '', phone: '' });
      load();
    } catch (err) { setError(err.response?.data?.detail || 'Xatolik'); }
    finally { setSaving(false); }
  };

  const handleSaveEdit = async (id) => {
    try {
      await api.patch(`/branches/${id}`, editForm);
      setEditId(null);
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Xatolik'); }
  };

  const handleDeactivate = async (id) => {
    if (!confirm(t('settings.deactivateBranch'))) return;
    try { await api.patch(`/branches/${id}`, { is_active: false }); load(); }
    catch (err) { alert(err.response?.data?.detail || 'Xatolik'); }
  };

  const inputCls = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';

  return (
    <div className="space-y-6">
      {/* Add form */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
        <h3 className="text-base font-bold text-slate-800 mb-4">{t('settings.addBranch')}</h3>
        <form onSubmit={handleAdd} className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.branchName')} *</label>
            <input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Masalan: Asosiy filial" className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.address') || 'Manzil'}</label>
            <input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })}
              placeholder="Shahar, ko'cha" className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.phone') || 'Telefon'}</label>
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}
              placeholder="+998 90 000 00 00" className={inputCls} />
          </div>
          <div className="md:col-span-3 flex justify-end">
            <button type="submit" disabled={saving}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
              {saving ? 'Saqlanmoqda...' : "➕ Filial qo'shish"}
            </button>
          </div>
        </form>
        {error && <div className="mt-3 px-4 py-2 bg-red-50 text-red-600 text-sm rounded-xl">{error}</div>}
      </div>

      {/* List */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['#', t('settings.branchName'), t('common.address'), t('settings.phone'), t('common.status'), ''].map(h => (
                <th key={h} className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {branches.map((b, idx) => (
              <tr key={b.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3.5 text-sm text-slate-400">{idx + 1}</td>
                <td className="px-4 py-3.5">
                  {editId === b.id ? (
                    <input value={editForm.name ?? b.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                      className="px-2 py-1.5 border border-blue-300 rounded-lg text-sm w-40" />
                  ) : (
                    <span className="text-sm font-semibold text-slate-800">{b.name}</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  {editId === b.id ? (
                    <input value={editForm.address ?? (b.address || '')} onChange={e => setEditForm(f => ({ ...f, address: e.target.value }))}
                      className="px-2 py-1.5 border border-blue-300 rounded-lg text-sm w-36" />
                  ) : (
                    <span className="text-sm text-slate-500">{b.address || '—'}</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  {editId === b.id ? (
                    <input value={editForm.phone ?? (b.phone || '')} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))}
                      className="px-2 py-1.5 border border-blue-300 rounded-lg text-sm w-32" />
                  ) : (
                    <span className="text-sm text-slate-500">{b.phone || '—'}</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${b.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${b.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                    {b.is_active ? 'Faol' : 'Faolsiz'}
                  </span>
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2">
                    {editId === b.id ? (
                      <>
                        <button onClick={() => handleSaveEdit(b.id)}
                          className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg">{t('admin.dict.save') || 'Saqlash'}</button>
                        <button onClick={() => setEditId(null)}
                          className="px-3 py-1.5 border border-slate-200 text-slate-500 text-xs rounded-lg">Bekor</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => { setEditId(b.id); setEditForm({}); }}
                          className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Tahrirlash">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        {b.is_active && (
                          <button onClick={() => handleDeactivate(b.id)}
                            className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors" title="Faolsizlashtirish">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                            </svg>
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {branches.length === 0 && (
              <tr><td colSpan={6} className="px-6 py-12 text-center text-slate-400 text-sm">{t('settings.branchEmpty')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FiskalTab() {
  const [status, setStatus]           = useState('checking'); // 'checking'|'online'|'offline'
  const [modules, setModules]         = useState([]);
  const [selectedId, setSelectedId]   = useState(() => {
    try { return JSON.parse(localStorage.getItem('fiskalId') || 'null'); } catch { return null; }
  });
  const [fiskalSend, setFiskalSend]   = useState(() => {
    try { return JSON.parse(localStorage.getItem('fiskalSend') || 'false'); } catch { return false; }
  });
  const [loading, setLoading]         = useState(false);

  // Hippo health va qurilmalarni BEVOSITA localhost:8081 dan yuklash
  const refresh = async () => {
    setLoading(true);
    setStatus('checking');
    try {
      const modules = await getFiscalModules(); // to'g'ridan localhost:8081
      const list = Array.isArray(modules) ? modules : (modules?.FiscalModules || []);
      setStatus('online');
      setModules(list);
      // Agar hali tanlanmagan bo'lsa, birinchisini avtomatik tanlaymiz
      if (!selectedId && list.length > 0) {
        const fid = list[0]?.FactoryID || null;
        setSelectedId(fid);
        localStorage.setItem('fiskalId', JSON.stringify(fid));
      }
    } catch {
      setStatus('offline');
      setModules([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const selectModule = (factoryId) => {
    setSelectedId(factoryId);
    localStorage.setItem('fiskalId', JSON.stringify(factoryId));
  };

  const toggleFiskal = (val) => {
    setFiskalSend(val);
    localStorage.setItem('fiskalSend', JSON.stringify(val));
    if (val) toast.success('Fiskalizatsiya yoqildi ✓');
    else toast("Fiskalizatsiya o'chirildi");
  };

  const statusColor = {
    checking: 'bg-amber-400',
    online:   'bg-emerald-500',
    offline:  'bg-red-500',
  }[status];

  const statusLabel = {
    checking: 'Tekshirilmoqda...',
    online:   'Online — Hippo ishlayapti',
    offline:  'Offline — Hippo topilmadi',
  }[status];

  return (
    <div className="max-w-xl space-y-4">

      {/* ── Header card ── */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-slate-800">Hippo Communicator</h2>
            <p className="text-xs text-slate-400 mt-0.5">Fiskal qurilma integratsiyasi</p>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold rounded-xl transition-all disabled:opacity-50"
          >
            <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Yangilash
          </button>
        </div>

        {/* Status badge */}
        <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl ${
          status === 'online'   ? 'bg-emerald-50 border border-emerald-200' :
          status === 'offline'  ? 'bg-red-50 border border-red-200' :
          'bg-amber-50 border border-amber-200'
        }`}>
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
            status === 'checking' ? 'animate-pulse ' : ''
          }${statusColor}`} />
          <span className={`text-sm font-semibold ${
            status === 'online'  ? 'text-emerald-700' :
            status === 'offline' ? 'text-red-700' :
            'text-amber-700'
          }`}>{statusLabel}</span>
        </div>

        {status === 'offline' && (
          <p className="text-xs text-red-500 mt-2 px-1">
            Hippo Communicator ishlamayapti. Kassir kompyuterida servis ishga tushganligini tekshiring.
          </p>
        )}
      </div>

      {/* ── Fiskal modullar ── */}
      {status === 'online' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-700 mb-3">Ulangan fiskal qurilmalar</h3>

          {modules.length === 0 ? (
            <div className="text-center py-6 text-slate-400">
              <svg className="w-10 h-10 mx-auto mb-2 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
              </svg>
              <p className="text-sm font-medium">Fiskal qurilma topilmadi</p>
            </div>
          ) : (
            <div className="space-y-2">
              {modules.map((m) => {
                const fid = m.FactoryID;
                const isSelected = fid === selectedId;
                return (
                  <button
                    key={fid}
                    onClick={() => selectModule(fid)}
                    className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 transition-all ${
                      isSelected
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-slate-200 bg-slate-50 hover:border-blue-300'
                    }`}
                  >
                    <div className="text-left">
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Factory ID</p>
                      <p className="font-black text-slate-800 tracking-widest text-sm mt-0.5">{fid}</p>
                      {m.Description && <p className="text-xs text-slate-400 mt-0.5">{m.Description}</p>}
                    </div>
                    {isSelected && (
                      <span className="flex items-center gap-1 text-blue-600 text-xs font-bold shrink-0">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                        Tanlangan
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Fiskalizatsiya toggle ── */}
      {status === 'online' && selectedId && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-800">Savdolarda fiskalizatsiya</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Yoqilsa — har bir sotuv Hippo orqali fiskal qurilmaga yuboriladi
              </p>
            </div>
            {/* Toggle switch */}
            <button
              onClick={() => toggleFiskal(!fiskalSend)}
              className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors ${
                fiskalSend ? 'bg-emerald-500' : 'bg-slate-300'
              }`}
            >
              <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition-transform ${
                fiskalSend ? 'translate-x-8' : 'translate-x-1'
              }`} />
            </button>
          </div>

          {fiskalSend && (
            <div className="mt-4 flex items-start gap-2 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
              <svg className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
              <div>
                <p className="text-xs font-bold text-emerald-700">Fiskalizatsiya faol</p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  Qurilma: <span className="font-black tracking-widest">{selectedId}</span>
                </p>
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  );
}

import { useSearchParams } from 'react-router-dom';
import { getSettingsMenus } from '../../constants/settingsMenus';

// ── Main Settings Component ──────────────────────────────────────────────────
export default function Settings() {
  const { t } = useLang();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'users';
  const [companyId, setCompanyId] = useState(null);

  const load = () => {
    api.get('/companies').then(r => {
      if (r.data?.length > 0) {
        setCompanyId(r.data[0].id);
      }
    });
  };

  useEffect(() => { load(); }, []);

  const MENUS = getSettingsMenus(t);

  return (
    <div className="absolute inset-0 flex bg-slate-50 z-10 overflow-hidden">
      {/* Content Area */}
      <div className="flex-1 h-full overflow-y-auto p-4 md:p-6 lg:p-8 relative">
        <div className="max-w-6xl mx-auto">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-2xl font-bold text-slate-800">{MENUS.find(m => m.id === tab)?.label || 'Sozlamalar'}</h1>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 min-h-[500px]">
            {tab === 'users' && <UsersTab />}
            {tab === 'roles' && <RolesTab />}
            {tab === 'branches' && <BranchesTab />}
            {tab === 'currencies' && <CurrenciesTab />}
            {tab === 'api' && <ApiKeysTab />}
            {tab === 'receipt' && <ReceiptTab />}
            {tab === 'tgbot' && <TelegramBotTab companyId={companyId} />}
            {tab === 'password' && <PasswordTab />}
            {tab === 'fiskal' && <FiskalTab />}
            
            {/* Placeholders for unfinished tabs */}
            {tab === 'tariffs' && <PlaceholderTab name="Tashkilot" />}
            {tab === 'internet_store' && <PlaceholderTab name="Интернет магазин" />}
            {tab === 'integrations' && <PlaceholderTab name="Integratsiyalar" />}
            {tab === 'references' && <PlaceholderTab name="Ma'lumotnoma" />}
            {tab === 'general' && <PlaceholderTab name="Umumiy" />}
            {tab === 'org_structure' && <PlaceholderTab name="Tashkilot tuzilmasi" />}
            {tab === 'auto_reply' && <PlaceholderTab name="Avto javob beruvchilar" />}
            {tab === 'auto_distribute' && <PlaceholderTab name="Avto-tarqatish qoidalari" />}
            {tab === 'forms' && <PlaceholderTab name="Formalar" />}
            {tab === 'shifts' && <PlaceholderTab name="Smena" />}
            {tab === 'warehouses' && <PlaceholderTab name="Ombor bo'limlari" />}
          </div>
        </div>
      </div>
    </div>
  );
}

// Icon Components for the Sidebar
const UsersTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>;
const RolesTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>;
const OrgTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>;
const StoreTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>;
const IntegrationTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>;
const RefTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>;
const GeneralTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>;
const OrgStructTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>;
const BotTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
const DistributeTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>;
const FormsTabIcon = () => <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>;




