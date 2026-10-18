import { useState, useEffect, useRef } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { useAuth } from '../../context/AuthContext';
import toast from 'react-hot-toast';
import { saveReceiptSettings } from '../../utils/receiptBuilder';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search, Zap, Lock, ArrowRight, Check, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { getFiscalModules } from '../../api/hippoLocal';
import RolesTab from './Settings/Roles';
import UsersTab from './Settings/Users';
import Promotions from './Promotions';
import Warehouse from './Warehouse';
import PaymentReconciliation from './PaymentReconciliation';
import FiscalCoverage from './FiscalCoverage';
import useCompanyFeatures, { refreshCompanyFeatures } from '../../hooks/useCompanyFeatures';
import { useBranches, invalidateBranches } from '../../hooks/useBranches';

// Add placeholder for missing tabs
const PlaceholderTab = ({ name }) => {
  const { t } = useLang();
  return (
    <div className="py-12 text-center text-slate-400">
      <h3 className="text-lg font-bold text-slate-700 mb-2">{t('settings.placeholder.comingSoon', { name })}</h3>
      <p className="text-sm">{t('settings.placeholder.inProgress')}</p>
    </div>
  );
};

// t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
const trf = (t, key, fallback) => { const s = t(key); return s === key ? fallback : s; };

// T3.7: eski shablonlarda `show_account_name` ham filialni, ham mijozni boshqargan —
// yangi kalitlar yo'q bo'lsa eski qiymatdan ko'chiramiz (chek oldingidek chiqadi)
const migrateAccountName = (cfg) => {
  if (!cfg || cfg.show_account_name === undefined) return cfg;
  const out = { ...cfg };
  if (out.show_branch === undefined) out.show_branch = cfg.show_account_name;
  if (out.show_customer === undefined) out.show_customer = cfg.show_account_name;
  return out;
};

// ── Default chek shablon konfiguratsiyalari ───────────────────────────────────
const defaultReceiptCfg = {
  company: '', address: '', phone: '', inn: '', logo: '', logo_size: 40,
  header: '', footer: 'Xaridingiz uchun rahmat!',
  show_number: true, show_date: true, show_status: false,
  show_branch: true, show_customer: true, show_employee: true,
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
  show_contractor_name: true, show_branch: true,
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
    }).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('error.serverError')) });

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
      setError(err.response?.data?.detail || t('error.serverError'));
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
      toast.error(err.response?.data?.detail || t('error.serverError'));
    } finally { setUpdatingId(null); }
  };

  const handleMakeDefault = async (c) => {
    if (c.is_default) return;
    setMakingDefaultId(c.id);
    try {
      await api.patch(`/currencies/${c.id}`, { is_default: true });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('error.serverError'));
    } finally { setMakingDefaultId(null); }
  };

  const handleDelete = async (id) => {
    if (!confirm(t('confirm.delete'))) return;
    try {
      await api.delete(`/currencies/${id}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('common.error'));
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
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.currencies.rateFieldLabel')}</label>
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
                    onClick={() => api.patch(`/currencies/${c.id}`, { is_active: !c.is_active }).then(() => load()).catch(e => toast.error(e.response?.data?.detail || t('common.error')))}
                    title={c.is_default ? t('settings.currencies.cannotDeactivateDefault') : (c.is_active ? t('settings.currencies.deactivate') : t('settings.currencies.activate'))}
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
                      title={t('common.delete')}
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
  // i18n kaliti hali qo'shilmagan bo'lsa (t() kalitni qaytaradi) — o'zbekcha zaxira matn
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const lastUsedLabel = tf('settings.apiKeys.lastUsed', 'Oxirgi ishlatilgan');
  const [keys, setKeys] = useState([]);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [newToken, setNewToken] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = () => api.get('/api-keys/').then(r => setKeys(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('error.serverError')) });

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
      toast.error(err.response?.data?.detail || t('error.serverError'));
    } finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!confirm(t('settings.apiKeys.confirmDelete'))) return;
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
              <p className="text-sm font-bold text-amber-800 mb-1">"{newToken.name}" — {t('settings.apiKeys.copyTokenHint')}</p>
              <p className="text-xs text-amber-700 mb-3">{t('settings.tokenWarning') || t('settings.apiKeys.tokenShownOnce')}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 bg-white border border-amber-300 rounded-lg text-xs font-mono text-amber-900 break-all">
                  {newToken.token}
                </code>
                <button
                  onClick={copyToken}
                  className={`px-3 py-2 text-xs font-semibold rounded-lg transition-colors shrink-0 ${copied ? 'bg-emerald-500 text-white' : 'bg-amber-200 hover:bg-amber-300 text-amber-800'
                    }`}
                >
                  {copied ? t('settings.apiKeys.copied') : t('settings.apiKeys.copy')}
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
        <h3 className="text-base font-bold text-slate-800 mb-4">{t('settings.apiKeys.generateTitle')}</h3>
        <form onSubmit={handleGenerate} className="flex gap-3">
          <input
            required value={name}
            onChange={e => setName(e.target.value)}
            placeholder={t('settings.apiKeys.namePlaceholder')}
            className="flex-1 px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit" disabled={saving}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            {saving ? t('settings.apiKeys.creating') : t('settings.apiKeys.create')}
          </button>
        </form>
      </div>

      {/* List */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {[t('common.name'), tf('settings.apiKeys.prefix', 'Kalit'), lastUsedLabel, ''].map(h => (
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
                    {k.key_prefix ? `${k.key_prefix}…` : '—'}
                  </code>
                </td>
                <td className="px-6 py-4 text-xs text-slate-500">
                  {k.last_used_at ? new Date(/(Z|[+-]\d\d:?\d\d)$/.test(k.last_used_at) ? k.last_used_at : `${k.last_used_at}Z`).toLocaleString() : '—'}
                </td>
                <td className="px-6 py-4 text-right">
                  <button
                    onClick={() => handleDelete(k.id)}
                    className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    title={t('common.delete')}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={4} className="px-6 py-12 text-center text-slate-400 text-sm">{t('settings.apiKeys.empty')}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Info box */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
        <h4 className="text-sm font-bold text-slate-700 mb-2">{t('settings.apiKeys.aboutTitle')}</h4>
        <ul className="space-y-1 text-xs text-slate-500">
          <li>• {t('settings.apiKeys.hint1a')} <code className="bg-slate-200 px-1.5 py-0.5 rounded font-mono">X-API-Key</code> {t('settings.apiKeys.hint1b')}</li>
          <li>• {t('settings.apiKeys.hint2')}</li>
          <li>• {t('settings.apiKeys.hint3a')} <code className="bg-slate-200 px-1.5 py-0.5 rounded font-mono">/api/reports/1c-export</code> {t('settings.apiKeys.hint3b')}</li>
          <li>• {t('settings.apiKeys.hint4')}</li>
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
    if (form.new_password.length < 6) { setErr(t('settings.password.minLength')); return; }
    if (form.new_password !== form.confirm) { setErr(t('settings.password.mismatch')); return; }
    setSaving(true);
    try {
      const me = await api.get('/auth/me');
      await api.patch(`/users/${me.data.id}/password`, { new_password: form.new_password });
      setMsg(t('settings.password.changed'));
      setForm({ new_password: '', confirm: '' });
    } catch (e) {
      setErr(e.response?.data?.detail || t('error.serverError'));
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
            <h3 className="font-bold text-slate-800">{t('settings.password.title')}</h3>
            <p className="text-xs text-slate-400">{t('settings.password.minLength')}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{t('settings.password.newPassword')}</label>
            <div className="relative">
              <input type={show.new ? 'text' : 'password'} required value={form.new_password}
                onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))}
                placeholder={t('settings.password.newPasswordPlaceholder')}
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
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{t('settings.password.confirmLabel')}</label>
            <div className="relative">
              <input type={show.confirm ? 'text' : 'password'} required value={form.confirm}
                onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
                placeholder={t('settings.password.confirmPlaceholder')}
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
              <p className="text-xs text-red-500 mt-1">{t('settings.password.mismatch')}</p>
            )}
          </div>

          {err && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">{err}</div>}
          {msg && <div className="px-4 py-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            {msg}
          </div>}

          <button type="submit" disabled={saving}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
            {saving ? t('common.saving') : t('settings.password.title')}
          </button>
        </form>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
        <h4 className="text-sm font-bold text-amber-800 mb-2">{t('settings.password.securityTipsTitle')}</h4>
        <ul className="space-y-1 text-xs text-amber-700">
          <li>• {t('settings.password.tip1')}</li>
          <li>• {t('settings.password.tip2')}</li>
          <li>• {t('settings.password.tip3')}</li>
          <li>• {t('settings.password.tip4')}</li>
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
  const { t } = useLang();
  // i18n kaliti hali qo'shilmagan bo'lsa (t() kalitni qaytaradi) — o'zbekcha zaxira matn
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const [settings, setSettings] = useState({
    notify_instant_sales: true,
    notify_instant_finance: true,
    notify_scheduled: false,
    scheduled_time: '21:00',
    notify_expired_products: true,
    expired_days_before: 7,
    notify_branch_managers: true,
    report_by_branch: true,
  });
  // Jadvalli hisobot oluvchilar — korxona sozlamasi (companies.daily_report_recipients)
  const [recipients, setRecipients] = useState('owners_and_admins');
  const [initialRecipients, setInitialRecipients] = useState('owners_and_admins');
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
          notify_branch_managers: r.data.notify_branch_managers ?? true,
          report_by_branch:       r.data.report_by_branch       ?? true,
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    api.get('/companies')
      .then(r => {
        const c = (r.data || []).find(x => x.id === companyId);
        const v = c?.daily_report_recipients || 'owners_and_admins';
        setRecipients(v);
        setInitialRecipients(v);
      })
      .catch(() => {});
  }, [companyId]);

  const upd = (key, val) => setSettings(s => ({ ...s, [key]: val }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/companies/${companyId}/admin-bot/settings`, settings);
      if (recipients !== initialRecipients) {
        await api.put(`/companies/${companyId}`, { daily_report_recipients: recipients });
        setInitialRecipients(recipients);
      }
      setSaved(true);
      setTimeout(() => { setSaved(false); }, 2500);
      toast.success(t('settings.adminBot.saved'));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error.serverError'));
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
              <h2 className="text-lg font-bold text-slate-800">{t('settings.adminBot.title')}</h2>
              <p className="text-sm text-slate-500">{t('settings.adminBot.subtitle')}</p>
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

              {/* === 0. Botga ulanish yo'riqnomasi (T0.16: faqat veb-panelda qo'shilgan rahbarlar ulanadi) === */}
              <div className="md:col-span-2 rounded-xl border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-800">
                <p className="font-semibold">{tf('settings.adminBot.linkHintTitle', 'Botga ulanish')}</p>
                <p className="text-xs mt-1 text-sky-700">
                  {tf('settings.adminBot.linkHintBranch', "Avval veb-panelda (Xodimlar) admin, direktor yoki filial menejeri sifatida qo'shilgan bo'lishingiz kerak, so'ng botda /start bosib, kontaktingizni yuboring. Korxonadan bir nechta rahbar ulana oladi. Botdan yangi foydalanuvchi yaratilmaydi.")}
                </p>
              </div>

              {/* === 1. Joyida yuborish === */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex flex-col">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-orange-50 text-orange-500 flex items-center justify-center shrink-0">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    </div>
                    <div>
                      <p className="text-sm font-bold text-slate-800">{t('settings.adminBot.instantMessagesTitle')}</p>
                      <p className="text-xs text-slate-500">{t('settings.adminBot.instantMessagesDesc')}</p>
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
                        <p className="text-sm font-semibold text-slate-700">{t('settings.adminBot.newSale')}</p>
                        <p className="text-xs text-slate-400">{t('settings.adminBot.newSaleDesc')}</p>
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
                        <p className="text-sm font-semibold text-slate-700">{t('settings.adminBot.financial')}</p>
                        <p className="text-xs text-slate-400">{t('settings.adminBot.financialDesc')}</p>
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
                        <p className="text-sm font-bold text-slate-800">{t('settings.adminBot.dailyReport')}</p>
                        <p className="text-xs text-slate-500">{t('settings.adminBot.dailyReportDesc')}</p>
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
                        {t('settings.adminBot.scheduledTimeHint')}
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
                        <p className="text-sm font-bold text-slate-800">{t('settings.adminBot.expiryTitle')}</p>
                        <p className="text-xs text-slate-500">{t('settings.adminBot.expiryDesc')}</p>
                      </div>
                    </div>
                    <PremiumToggle checked={settings.notify_expired_products} onChange={v => upd('notify_expired_products', v)} color="blue" />
                  </div>
                  
                  <div className={`transition-opacity ${settings.notify_expired_products ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
                    <p className="text-xs font-semibold text-slate-600 mb-2">{t('settings.adminBot.warnDaysBeforeLabel')}</p>
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
                            {d} {t('settings.adminBot.daysUnit')}
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
                        <span className="text-xs text-slate-400">{t('settings.adminBot.daysUnit')}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* === 4. Filial bo'yicha xabarlar (T3.16) === */}
              <div className="md:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-500 flex items-center justify-center shrink-0">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-800">{tf('settings.adminBot.branchTitle', "Filial bo'yicha xabarlar")}</p>
                    <p className="text-xs text-slate-500">{tf('settings.adminBot.branchDesc', "Ko'p filialli korxonada xabar va hisobotlar filial kesimida")}</p>
                  </div>
                </div>

                <div className="space-y-4">
                  <label className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-blue-100 hover:bg-blue-50/30 cursor-pointer transition-colors">
                    <div>
                      <p className="text-sm font-semibold text-slate-700">{tf('settings.adminBot.notifyBranchManagers', 'Filial menejerlariga yuborish')}</p>
                      <p className="text-xs text-slate-400">{tf('settings.adminBot.notifyBranchManagersDesc', "Menejer o'z filiali sotuv va xarajat xabarlarini oladi")}</p>
                    </div>
                    <PremiumToggle checked={settings.notify_branch_managers} onChange={v => upd('notify_branch_managers', v)} color="blue" />
                  </label>

                  <label className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-blue-100 hover:bg-blue-50/30 cursor-pointer transition-colors">
                    <div>
                      <p className="text-sm font-semibold text-slate-700">{tf('settings.adminBot.reportByBranch', "Hisobotda filiallar bo'limi")}</p>
                      <p className="text-xs text-slate-400">{tf('settings.adminBot.reportByBranchDesc', "Kunlik hisobotda har bir filial bo'yicha tushum")}</p>
                    </div>
                    <PremiumToggle checked={settings.report_by_branch} onChange={v => upd('report_by_branch', v)} color="blue" />
                  </label>

                  <div className="p-3 rounded-lg border border-slate-100">
                    <p className="text-sm font-semibold text-slate-700">{tf('settings.adminBot.reportRecipients', 'Hisobot oluvchilar')}</p>
                    <p className="text-xs text-slate-400 mb-2">{tf('settings.adminBot.reportRecipientsDesc', "Kunlik hisobot, qarz va muddat eslatmalarini kim oladi")}</p>
                    <select
                      value={recipients}
                      onChange={e => setRecipients(e.target.value)}
                      className="w-full px-3 py-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    >
                      <option value="owners_and_admins">{tf('settings.adminBot.recipientsOwnersAndAdmins', 'Direktor va adminlar')}</option>
                      <option value="owners">{tf('settings.adminBot.recipientsOwners', 'Faqat direktor')}</option>
                      <option value="all_managers">{tf('settings.adminBot.recipientsAllManagers', 'Direktor, adminlar va filial menejerlari')}</option>
                    </select>
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
              {t('settings.saved')}
            </span>
          ) : <span />}
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={handleSave}
              disabled={saving || loading}
              className="px-6 py-2 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2 shadow-sm"
            >
              {saving ? (
                <>
                  <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  {t('common.saving')}
                </>
              ) : t('common.save')}
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
  const { t } = useLang();
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const [userBot, setUserBot] = useState(null);
  const [adminBot, setAdminBot] = useState(null);
  const [courierBot, setCourierBot] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [botType, setBotType] = useState('user');
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [showAdminSettings, setShowAdminSettings] = useState(false);
  const [shopAllowOutOfStock, setShopAllowOutOfStock] = useState(true);
  const [shopReceiptFormat, setShopReceiptFormat] = useState('text');
  const [tgProtectContent, setTgProtectContent] = useState(false);
  const [savingShopSetting, setSavingShopSetting] = useState(false);
  // T3.13: Mini App / bot buyurtmalari uchun standart filial
  const [shopDefaultBranch, setShopDefaultBranch] = useState('');
  // T3.8: filiallar yagona hook'dan (keshlangan)
  const { branches: shopBranchesAll } = useBranches();
  const shopBranches = shopBranchesAll.filter(b => b.is_active !== false);

  const load = () => {
    api.get('/companies').then(r => {
      if (r.data?.length > 0) {
        const co = r.data[0];
        if (co.tg_bot_token) {
           setUserBot({ bot_token: co.tg_bot_token, bot_username: co.tg_bot_username });
        } else {
           setUserBot(null);
        }
        setShopAllowOutOfStock(co.shop_allow_out_of_stock_orders !== false);
        setShopReceiptFormat(co.receipt_format || 'text');
        setTgProtectContent(Boolean(co.tg_protect_content));
        setShopDefaultBranch(co.shop_default_branch_id ? String(co.shop_default_branch_id) : '');
        setCourierBot(co.courier_bot_username ? { bot_username: co.courier_bot_username } : null);
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

    if (botType === "courier") {
      setSaving(true); setErr('');
      try {
        const res = await api.put(`/companies/${companyId}`, { courier_bot_token: token });
        toast.success(t('settings.telegramBot.courierConnected'));
        setCourierBot(res.data?.courier_bot_username ? { bot_username: res.data.courier_bot_username } : null);
        setToken('');
        setShowModal(false);
      } catch (error) {
        setErr(error.response?.data?.detail || t('auth.errGeneral'));
      } finally {
        setSaving(false);
      }
    } else if (botType === "admin") {
      setSaving(true); setErr('');
      try {
        const res = await api.put(`/companies/${companyId}/admin-bot`, { bot_token: token });
        toast.success(t('settings.telegramBot.adminConnected') + ' ' + tf('settings.telegramBot.adminStartsIn30', "Bot 30 soniya ichida ishga tushadi."));
        setAdminBot(res.data);
        setToken('');
        setShowModal(false);
      } catch (error) {
        setErr(error.response?.data?.detail || t('auth.errGeneral'));
      } finally {
        setSaving(false);
      }
    } else {
      setSaving(true); setErr('');
      try {
        const res = await api.put(`/companies/${companyId}`, { tg_bot_token: token });
        toast.success(t('settings.telegramBot.userConnected'));
        setUserBot({ bot_token: res.data?.tg_bot_token, bot_username: res.data?.tg_bot_username });
        setToken('');
        setShowModal(false);
      } catch (error) {
        setErr(error.response?.data?.detail || t('auth.errGeneral'));
      } finally {
        setSaving(false);
      }
    }
  };

  const handleDelete = async (type) => {
    if (!confirm(t('settings.telegramBot.confirmDisconnect'))) return;
    try {
      if (type === 'courier') {
         await api.put(`/companies/${companyId}`, { courier_bot_token: null });
         setCourierBot(null);
         toast.success(t('settings.telegramBot.courierDisconnected'));
      } else if (type === 'admin') {
         await api.delete(`/companies/${companyId}/admin-bot`);
         setAdminBot(null);
         setShowAdminSettings(false);
         toast.success(t('settings.telegramBot.adminDisconnected'));
      } else {
         await api.put(`/companies/${companyId}`, { tg_bot_token: null });
         setUserBot(null);
         toast.success(t('settings.telegramBot.userDisconnected'));
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || t('common.error'));
    }
  };

  const handleShopSettingToggle = async (checked) => {
    if (!companyId) return;
    setShopAllowOutOfStock(checked);
    setSavingShopSetting(true);
    try {
      await api.put(`/companies/${companyId}`, { shop_allow_out_of_stock_orders: checked });
      toast.success(t('settings.saved'));
    } catch (e) {
      setShopAllowOutOfStock(!checked);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingShopSetting(false);
    }
  };

  const handleShopDefaultBranch = async (value) => {
    if (!companyId) return;
    const prev = shopDefaultBranch;
    setShopDefaultBranch(value);
    setSavingShopSetting(true);
    try {
      await api.put(`/companies/${companyId}`, { shop_default_branch_id: value ? Number(value) : null });
      toast.success(t('settings.saved'));
    } catch (e) {
      setShopDefaultBranch(prev);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingShopSetting(false);
    }
  };

  const handleShopReceiptFormat = async (val) => {
    if (!companyId) return;
    const prev = shopReceiptFormat;
    setShopReceiptFormat(val);
    setSavingShopSetting(true);
    try {
      await api.put(`/companies/${companyId}`, { receipt_format: val });
      toast.success(t('settings.saved'));
    } catch (e) {
      setShopReceiptFormat(prev);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingShopSetting(false);
    }
  };

  const handleTgProtectContent = async (checked) => {
    if (!companyId) return;
    const prev = tgProtectContent;
    setTgProtectContent(checked);
    setSavingShopSetting(true);
    try {
      await api.put(`/companies/${companyId}`, { tg_protect_content: checked });
      toast.success(t('settings.saved'));
    } catch (e) {
      setTgProtectContent(prev);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingShopSetting(false);
    }
  };

  return (
    <div className="space-y-6">
      {!companyId && (
        <div className="flex items-center justify-center py-16">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"/>
            <p className="text-sm text-slate-400">{t('common.loading')}</p>
          </div>
        </div>
      )}
      {companyId && (
      <><div>
        <h3 className="text-base font-bold text-slate-800">{t('settings.telegramBot.title')}</h3>
        <p className="text-xs text-slate-400 mt-0.5">{t('settings.telegramBot.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">

        {/* ── Mijoz boti ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h4 className="font-bold text-slate-800">{t('settings.telegramBot.userBotTitle')}</h4>
              <p className="text-xs text-slate-400 mt-0.5">{t('settings.telegramBot.userBotDesc')}</p>
            </div>
            {!userBot?.bot_username ? (
              <button
                onClick={() => { setBotType('user'); setShowModal(true); setErr(''); setToken(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 text-xs font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                {t('settings.telegramBot.connect')}
              </button>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-md">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />{t('common.active')}
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
                  className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg transition-colors">{t('settings.telegramBot.update')}</button>
                <button onClick={() => handleDelete('user')}
                  className="flex-1 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold rounded-lg transition-colors">{t('common.delete')}</button>
              </div>

              {/* ── Do'kon (Mini App) sozlamalari ── */}
              <div className="pt-3 border-t border-slate-50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-slate-700">{t('settings.telegramBot.outOfStockOrderTitle')}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                      {t('settings.telegramBot.outOfStockOrderDesc')}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={savingShopSetting}
                    onClick={() => handleShopSettingToggle(!shopAllowOutOfStock)}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${shopAllowOutOfStock ? 'bg-blue-600' : 'bg-slate-200'}`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${shopAllowOutOfStock ? 'translate-x-6' : 'translate-x-1'}`} />
                  </button>
                </div>
                {/* T3.13: onlayn buyurtmalar uchun standart filial */}
                {shopBranches.length > 1 && (
                  <div className="mt-3">
                    <p className="text-xs font-semibold text-slate-700">{tf('settings.telegramBot.defaultBranch', "Onlayn buyurtmalar uchun standart filial")}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                      {tf('settings.telegramBot.defaultBranchDesc', "Mijoz filial tanlamasa va unga filial biriktirilmagan bo'lsa, buyurtma va yangi bot mijozlari shu filialga tushadi.")}
                    </p>
                    <select
                      value={shopDefaultBranch}
                      disabled={savingShopSetting}
                      onChange={e => handleShopDefaultBranch(e.target.value)}
                      className="mt-2 w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:opacity-60"
                    >
                      <option value="">{tf('settings.telegramBot.defaultBranchAuto', 'Avtomatik (birinchi filial)')}</option>
                      {shopBranches.map(b => <option key={b.id} value={String(b.id)}>{b.name}</option>)}
                    </select>
                  </div>
                )}

                {/* Chek yuborish formati (Matn, Rasm, PDF) */}
                <div className="mt-4 pt-3 border-t border-slate-100">
                  <div className="mb-2">
                    <p className="text-xs font-semibold text-slate-700">
                      {tf('settings.telegramBot.receiptFormatTitle', "Mijozga chek yuborish formati")}
                    </p>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                      {tf('settings.telegramBot.receiptFormatDesc', "Sotuv amalga oshirilganda mijoz botiga chek qaysi ko'rinishda yuborilishini tanlang")}
                    </p>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-2">
                    {[
                      { id: 'text', icon: '📝', label: tf('settings.telegramBot.fmtText', 'Matn'), sub: tf('settings.telegramBot.fmtTextSub', 'Tezkor xabar') },
                      { id: 'image', icon: '🖼', label: tf('settings.telegramBot.fmtImage', 'Rasm (JPG)'), sub: tf('settings.telegramBot.fmtImageSub', 'Nakladnoy chek') },
                      { id: 'pdf', icon: '📄', label: tf('settings.telegramBot.fmtPdf', 'PDF fayl'), sub: tf('settings.telegramBot.fmtPdfSub', 'A4 hujjat') },
                    ].map(fmt => {
                      const active = (shopReceiptFormat || 'text') === fmt.id;
                      return (
                        <button
                          key={fmt.id}
                          type="button"
                          disabled={savingShopSetting}
                          onClick={() => handleShopReceiptFormat(fmt.id)}
                          className={`flex flex-col items-center justify-center p-2.5 rounded-xl border text-center transition-all ${
                            active
                              ? 'bg-blue-50/80 border-blue-500 text-blue-700 shadow-sm ring-2 ring-blue-500/20 font-bold'
                              : 'bg-slate-50/70 border-slate-200 text-slate-600 hover:bg-slate-100 hover:border-slate-300 font-medium'
                          } disabled:opacity-60 cursor-pointer`}
                        >
                          <span className="text-lg leading-none mb-1">{fmt.icon}</span>
                          <span className="text-xs leading-tight">{fmt.label}</span>
                          <span className={`text-[10px] mt-0.5 ${active ? 'text-blue-600 font-semibold' : 'text-slate-400'}`}>{fmt.sub}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Xabarlarni forward qilish / saqlashni cheklash (Protect Content) */}
                <div className="mt-4 pt-3 border-t border-slate-100 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm">🔒</span>
                      <p className="text-xs font-semibold text-slate-700">
                        {tf('settings.telegramBot.protectContentTitle', "Xabar va cheklarni forward qilishni cheklash")}
                      </p>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                      {tf('settings.telegramBot.protectContentDesc', "Yoqilgan bo'lsa, mijozlar botdan cheklar, rasmlar va hisobotlarni boshqalarga uzatishi (forward) yoki yuklab olishi taqiqlanadi.")}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={savingShopSetting}
                    onClick={() => handleTgProtectContent(!tgProtectContent)}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 cursor-pointer ${tgProtectContent ? 'bg-blue-600' : 'bg-slate-200'}`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${tgProtectContent ? 'translate-x-6' : 'translate-x-1'}`} />
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-6 flex flex-col items-center justify-center border-2 border-dashed border-slate-100 rounded-xl bg-slate-50/50 mt-4">
              <svg className="w-8 h-8 text-slate-300 mb-2" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
              <p className="text-sm font-medium text-slate-500">{t('settings.telegramBot.notConnected')}</p>
            </div>
          )}
        </div>

        {/* ── Admin boti ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h4 className="font-bold text-slate-800">{t('settings.telegramBot.adminBotTitle')}</h4>
              <p className="text-xs text-slate-400 mt-0.5">{t('settings.telegramBot.adminBotDesc')}</p>
            </div>
            {!adminBot?.bot_username ? (
              <button
                onClick={() => { setBotType('admin'); setShowModal(true); setErr(''); setToken(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 text-xs font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                {t('settings.telegramBot.connect')}
              </button>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-md">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />{t('common.active')}
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
                  {t('settings.telegramBot.settingsButton')}
                </button>
                <button onClick={() => { setBotType('admin'); setShowModal(true); setErr(''); setToken(''); }}
                  className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg transition-colors">{t('settings.telegramBot.update')}</button>
                <button onClick={() => handleDelete('admin')}
                  className="flex-1 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold rounded-lg transition-colors">{t('common.delete')}</button>
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
              <p className="text-sm font-medium text-slate-500">{t('settings.telegramBot.notConnected')}</p>
            </div>
          )}
        </div>

        {/* ── Dostavchik boti ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h4 className="font-bold text-slate-800">{t('settings.telegramBot.courierBotTitle')}</h4>
              <p className="text-xs text-slate-400 mt-0.5">{t('settings.telegramBot.courierBotDesc')}</p>
            </div>
            {!courierBot?.bot_username ? (
              <button
                onClick={() => { setBotType('courier'); setShowModal(true); setErr(''); setToken(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 text-xs font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                {t('settings.telegramBot.connect')}
              </button>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-md">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />{t('common.active')}
              </span>
            )}
          </div>

          {courierBot?.bot_username ? (
            <div className="space-y-0">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center text-blue-500">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
                </div>
                <div className="flex-1 min-w-0">
                  <a href={'https://t.me/' + courierBot.bot_username} target="_blank" rel="noreferrer" className="text-sm font-bold text-blue-600 hover:underline">@{courierBot.bot_username}</a>
                  <p className="text-[11px] text-slate-400 mt-0.5">{t('settings.telegramBot.courierBotHint')}</p>
                </div>
              </div>
              <div className="flex gap-2 pt-3 mt-3 border-t border-slate-50">
                <button onClick={() => { setBotType('courier'); setShowModal(true); setErr(''); setToken(''); }}
                  className="flex-1 py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg transition-colors">{t('settings.telegramBot.update')}</button>
                <button onClick={() => handleDelete('courier')}
                  className="flex-1 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold rounded-lg transition-colors">{t('common.delete')}</button>
              </div>
            </div>
          ) : (
            <div className="py-6 flex flex-col items-center justify-center border-2 border-dashed border-slate-100 rounded-xl bg-slate-50/50 mt-4">
              <svg className="w-8 h-8 text-slate-300 mb-2" fill="currentColor" viewBox="0 0 24 24"><path d={TG_PATH} /></svg>
              <p className="text-sm font-medium text-slate-500">{t('settings.telegramBot.notConnected')}</p>
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
                <h3 className="font-bold text-slate-800">{t('settings.telegramBot.connectModalTitle')} ({botType === 'admin' ? t('settings.telegramBot.typeAdmin') : botType === 'courier' ? t('settings.telegramBot.typeCourier') : t('settings.telegramBot.typeUser')})</h3>
              </div>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-[13px] font-bold text-slate-700 mb-1.5">{t('settings.telegramBot.tokenLabel')}</label>
                <input
                  type="text" required value={token}
                  onChange={e => setToken(e.target.value)}
                  placeholder="1234567890:AAH_abcxyz..."
                  className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono transition-all"
                />
                <p className="text-xs text-slate-400 mt-1.5">{t('settings.telegramBot.tokenHint')}</p>
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
                {saving ? t('common.saving') : t('common.save')}
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
      {cfg.phone && <div className="text-center mb-1.5">{t('settings.receiptPreview.tel')}: {cfg.phone}</div>}
      {cfg.inn && <div className="text-center mb-1.5">{t('settings.receiptPreview.stir')}: {cfg.inn}</div>}
      {cfg.header && <div className="text-center mb-1.5">{cfg.header}</div>}

      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.receiptNo')}:</span>
        <span>#00001</span>
      </div>
      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.cashier')}:</span>
        <span>{cfg.show_cashier ? 'Sardor' : 'Sardor'}</span>
      </div>
      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.date')}:</span>
        <span>15.06.2026 09:56</span>
      </div>

      <div style={lineDashed}></div>
      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.customer')}:</span>
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
        <span>{t('settings.receiptPreview.itemsCount')}:</span>
        <span>{t('settings.receiptPreview.itemsCountSample')}</span>
      </div>
      <div style={lineSolid}></div>

      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.totalCaps')}:</span>
        <span>80,000 so'm</span>
      </div>
      <div style={lineDashed}></div>

      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.payment')}:</span>
        <span>100,000 so'm</span>
      </div>
      <div style={lineDashed}></div>

      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.prevDebt')}:</span>
        <span>0 so'm</span>
      </div>
      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.toDebt')}:</span>
        <span>0 so'm</span>
      </div>
      <div style={lineSolid}></div>

      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.totalDebt')}:</span>
        <span>0 so'm</span>
      </div>
      <br />
      <div className="flex justify-between">
        <span>{t('settings.receiptPreview.change')}:</span>
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

      <div className="text-center mt-3">{cfg.footer || t('settings.receiptPreview.thanks')}</div>
    </div>
  );
}

// ── Nakladnoy preview ─────────────────────────────────────────────────────────
function NakladnoyPreview({ cfg }) {
  const { t } = useLang();
  const sh = (key, def = true) => cfg[key] !== undefined ? cfg[key] : def;
  const logoPos = cfg.logo_position || 'center';

  const cols = [
    { key: 'show_ordering_number', label: '№' },
    { label: t('settings.nakladnoyPreview.colProductName'), always: true, always_key: 'always_name' },
    { key: 'show_measurement', label: t('settings.nakladnoyPreview.colUnit') },
    { key: 'show_warehouse', label: t('settings.nakladnoyPreview.colWarehouse') },
    { key: 'show_sku', label: t('settings.nakladnoyPreview.colSku') },
    { key: 'show_price', label: t('settings.nakladnoyPreview.colPrice') },
    { key: 'show_discount', label: t('common.discount') },
    { key: 'show_price_with_discount', label: t('settings.nakladnoyPreview.colDiscountedPrice') },
    { key: 'show_net_price', label: t('settings.receipt.fieldNetPrice') },
    { key: 'show_currency', label: t('settings.nakladnoyPreview.colCurrencyShort') },
    { label: t('common.quantity'), always: true, always_key: 'always_qty' },
    { label: t('common.total'), always: true, always_key: 'always_total' },
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
        <div className="font-bold text-[9px]">{cfg.company || t('settings.nakladnoyPreview.companyNamePlaceholder')}</div>
        {cfg.inn && <div>{t('settings.receiptPreview.stir')}: {cfg.inn}</div>}
        {cfg.address && <div>{cfg.address}</div>}
        {cfg.phone && <div>{t('settings.receiptPreview.tel')}: {cfg.phone}</div>}
        {cfg.bank && <div>{t('settings.nakladnoy.bankNameLabel')}: {cfg.bank}{cfg.mfo ? ` | ${t('settings.nakladnoy.mfoLabel')}: ${cfg.mfo}` : ''}</div>}
      </div>

      <div className="text-center font-bold text-[8px] mb-1">
        {t('settings.nakladnoyPreview.title')} № {sh('show_number') ? '___' : ''} {sh('show_date') ? '/ 17.03.2025' : ''}
      </div>

      {/* Info satrlari */}
      <div className="text-[7px] mb-1 space-y-0.5">
        {sh('show_contractor_name') && <div><b>{t('settings.receiptPreview.customer')}:</b> Abdullayev Jasur</div>}
        {sh('show_branch') && <div><b>{t('settings.nakladnoy.branchLabel')}:</b> {trf(t, 'settings.nakladnoyPreview.branchSample', 'Chilonzor filiali')}</div>}
        {sh('show_employee') && <div><b>{t('settings.nakladnoyPreview.employee')}:</b> Sardor</div>}
        {sh('show_status') && <div><b>{t('common.status')}:</b> {t('settings.nakladnoyPreview.statusApproved')}</div>}
      </div>

      <table className="w-full border-collapse mb-1.5" style={{ borderSpacing: 0 }}>
        <thead>
          <tr>{cols.map((col, i) => <th key={i} className="border border-slate-400 px-0.5 py-0.5 text-center bg-slate-100 text-[6px]">{col.label}</th>)}</tr>
        </thead>
        <tbody>
          {sampleItems.map((item, ri) => (
            <tr key={ri}>
              {cols.map((col, ci) => {
                const allCols = ['show_ordering_number', 'always_name', 'show_measurement', 'show_warehouse', 'show_sku', 'show_price', 'show_discount', 'show_price_with_discount', 'show_net_price', 'show_currency', 'always_qty', 'always_total'];
                const origIdx = allCols.indexOf(col.key || col.always_key);
                const vkey = sampleVals[allCols[origIdx]];
                return <td key={ci} className="border border-slate-300 px-0.5 py-0.5 text-center">{item[vkey]}</td>;
              })}
            </tr>
          ))}
          <tr>
            <td colSpan={cols.length - 1} className="border border-slate-300 px-0.5 py-0.5 text-right font-bold">{t('settings.receiptPreview.totalCaps')}:</td>
            <td className="border border-slate-300 px-0.5 py-0.5 text-center font-bold">80,000</td>
          </tr>
        </tbody>
      </table>

      {/* Jami bo'lim */}
      {sh('show_totals') && (
        <div className="text-[7px] space-y-0.5 border-t border-slate-200 pt-1 mb-1">
          <div className="flex justify-between"><span>{t('settings.receiptPreview.totalCaps')}:</span><span className="font-bold">80,000 so'm</span></div>
          {sh('show_payment_amounts') && <div className="flex justify-between"><span>{t('settings.nakladnoyPreview.paid')}:</span><span>100,000 so'm</span></div>}
          {sh('show_contractor_debts') && <div className="flex justify-between text-red-600"><span>{t('common.debt')}:</span><span>0 so'm</span></div>}
          {sh('show_exact_discounts') && <div className="flex justify-between"><span>{t('common.discount')}:</span><span>-5,000 so'm</span></div>}
          {sh('show_total_quantity') && <div className="flex justify-between"><span>{t('settings.receipt.fieldTotalQty')}:</span><span>3</span></div>}
        </div>
      )}

      {/* Izoh */}
      {sh('show_note') && <div className="text-[7px] text-slate-500 italic mb-1">{t('settings.receipt.fieldNote')}: {t('settings.nakladnoyPreview.noteSample')}</div>}

      {/* Imzolar */}
      <div className="flex justify-between mt-2 pt-1.5 border-t border-slate-300 text-[7px] flex-wrap gap-1">
        {sh('show_director') && <div>{t('settings.nakladnoy.directorLabel')}: {cfg.director || '__________'}</div>}
        {sh('show_accountant') && <div>{t('settings.nakladnoy.chiefAccountantLabel')}: {cfg.accountant || '__________'}</div>}
        {sh('show_storekeeper') && <div>{t('settings.nakladnoy.storekeeperLabel')}: {cfg.storekeeper || '__________'}</div>}
      </div>
      {cfg.footer_note && <div className="mt-1 italic text-slate-500 text-center text-[7px]">{cfg.footer_note}</div>}
    </div>
  );
}

// ── Receipt field style (module-level so components don't recreate it) ─────────
const RIC = 'w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white';

const SUB_TABS = (t) => [
  { id: '58', label: t('settings.receipt.tab58'), icon: '🧾' },
  { id: '80', label: t('settings.receipt.tab80'), icon: '🧾' },
  { id: 'nak', label: t('settings.receipt.tabNak'), icon: '📄' },
];

// ── These must be module-level functions — NOT defined inside ReceiptTab ───────
function LogoUpload({ logo, size, onUpload, onRemove, onSizeChange, positionPicker, position, onPositionChange }) {
  const { t } = useLang();
  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 500 * 1024) { toast.error(t('settings.receipt.logoTooLarge')); return; }
    const reader = new FileReader();
    reader.onload = () => onUpload(reader.result);
    reader.readAsDataURL(file);
  };

  return (
    <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-3">
      <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{t('settings.receipt.logoSectionTitle')}</p>
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
              {t('settings.receipt.uploadImage')}
            </span>
          </label>
          {logo && (
            <button onClick={onRemove} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 border border-red-200 rounded-lg transition-colors">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              {t('settings.receipt.removeLogo')}
            </button>
          )}
          {/* Size slider */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-500 whitespace-nowrap">{t('settings.receipt.sizeLabel')}:</span>
            <input type="range" min={16} max={100} step={4}
              value={size || 40}
              onChange={e => onSizeChange(Number(e.target.value))}
              className="flex-1 h-1.5 accent-blue-500 cursor-pointer"
            />
            <span className="text-[11px] font-mono text-slate-600 w-8 text-right">{size || 40}px</span>
          </div>
          {positionPicker && (
            <div>
              <p className="text-[11px] text-slate-500 mb-1">{t('settings.receipt.logoPositionLabel')}:</p>
              <div className="flex gap-1">
                {[['left', `◀ ${t('settings.receipt.posLeft')}`], ['center', `▪ ${t('settings.receipt.posCenter')}`], ['right', `${t('settings.receipt.posRight')} ▶`]].map(([v, l]) => (
                  <button key={v} onClick={() => onPositionChange(v)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg border transition-all ${position === v ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:border-blue-300'
                      }`}>{l}
                  </button>
                ))}
              </div>
            </div>
          )}
          <p className="text-[10px] text-slate-400">{t('settings.receipt.logoFormatsHint')}</p>
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
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.receipt.companyNameLabel')} *</label>
          <input value={cfg.company} onChange={e => upd('company', e.target.value)} placeholder={t('settings.receipt.companyNamePlaceholder')} className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.phone') || 'Telefon'}</label>
          <input value={cfg.phone} onChange={e => upd('phone', e.target.value)} placeholder="+998 90 000 00 00" className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.address') || 'Manzil'}</label>
          <input value={cfg.address} onChange={e => upd('address', e.target.value)} placeholder={t('settings.receipt.addressPlaceholder')} className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.receipt.innLabel')}</label>
          <input value={cfg.inn} onChange={e => upd('inn', e.target.value)} placeholder="123456789" className={RIC} />
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.receipt.headerLineLabel')}</label>
        <input value={cfg.header} onChange={e => upd('header', e.target.value)} placeholder={t('settings.receipt.headerPlaceholder')} className={RIC} />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.receipt.footerLineLabel')}</label>
        <input value={cfg.footer} onChange={e => upd('footer', e.target.value)} placeholder={t('settings.receiptPreview.thanks')} className={RIC} />
      </div>
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{t('settings.receipt.fieldsSectionTitle')}</p>

        {[
          {
            label: t('settings.receipt.groupHeader'),
            fields: [
              ['show_number', t('settings.receipt.fieldNumber')],
              ['show_date', t('settings.receipt.fieldDate')],
              ['show_status', t('settings.receipt.fieldStatus')],
              ['show_branch', t('settings.receipt.fieldBranch')],
              ['show_customer', trf(t, 'settings.receipt.fieldCustomer', 'Mijoz')],
              ['show_employee', t('settings.receipt.fieldEmployee')],
            ],
          },
          {
            label: t('settings.receipt.groupItem'),
            fields: [
              ['show_ordering_number', t('settings.receipt.fieldOrderNumber')],
              ['show_unit', t('settings.receipt.fieldUnit')],
              ['show_warehouse', t('settings.receipt.fieldWarehouse')],
              ['show_package', t('settings.receipt.fieldPackage')],
              ['show_price_per_unit', t('settings.receipt.fieldUnitPrice')],
              ['show_discount', t('common.discount')],
              ['show_price_with_discount', t('settings.receipt.fieldDiscountedPrice')],
              ['show_currency', t('settings.receipt.fieldCurrencyName')],
            ],
          },
          {
            label: t('settings.receipt.groupTotal'),
            fields: [
              ['show_total', t('settings.receipt.fieldTotalSum')],
              ['show_net_price', t('settings.receipt.fieldNetPrice')],
              ['show_total_quantity', t('settings.receipt.fieldTotalQty')],
              ['show_total_national', t('settings.receipt.fieldTotalNational')],
              ['show_payment_type', t('settings.receipt.fieldPaymentType')],
            ],
          },
          {
            label: t('settings.receipt.groupDebt'),
            fields: [
              ['show_debt', t('settings.receipt.fieldCurrentDebt')],
              ['show_before_debt', t('settings.receipt.fieldPrevDebt')],
              ['show_last_payment', t('settings.receipt.fieldLastPayment')],
            ],
          },
          {
            label: t('settings.receipt.groupExtra'),
            fields: [
              ['show_note', t('settings.receipt.fieldNote')],
              ['show_contractor_contact', t('settings.receipt.fieldCustomerContact')],
              ['show_cashier', t('settings.receipt.fieldCashierSignature')],
              ['show_barcode', t('settings.receipt.fieldBarcode')],
              ['show_qr', t('settings.receipt.fieldQr')],
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
          <span className="text-xs font-semibold text-slate-500">{t('settings.receipt.copiesLabel')}:</span>
          <select value={cfg.copies} onChange={e => upd('copies', e.target.value)}
            className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
            {['1', '2', '3'].map(n => <option key={n} value={n}>{n} {t('settings.receipt.copiesUnit')}</option>)}
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
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.receipt.companyNameLabel')} *</label>
          <input value={cfg.company} onChange={e => upd('company', e.target.value)} placeholder={t('settings.nakladnoyPreview.companyNamePlaceholder')} className={RIC} /></div>
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.receipt.innLabel')}</label>
          <input value={cfg.inn} onChange={e => upd('inn', e.target.value)} placeholder="123456789" className={RIC} /></div>
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('common.address')}</label>
          <input value={cfg.address} onChange={e => upd('address', e.target.value)} className={RIC} /></div>
        <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('common.phone')}</label>
          <input value={cfg.phone} onChange={e => upd('phone', e.target.value)} className={RIC} /></div>
      </div>

      {/* Bank */}
      <div className="border-t border-slate-100 pt-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">{t('settings.nakladnoy.bankDetailsTitle')}</p>
        <div className="grid grid-cols-3 gap-3">
          <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.nakladnoy.bankNameLabel')}</label>
            <input value={cfg.bank} onChange={e => upd('bank', e.target.value)} placeholder="NBU, Kapitalbank..." className={RIC} /></div>
          <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.nakladnoy.accountNumberLabel')}</label>
            <input value={cfg.account} onChange={e => upd('account', e.target.value)} placeholder="2020..." className={RIC} /></div>
          <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.nakladnoy.mfoLabel')}</label>
            <input value={cfg.mfo} onChange={e => upd('mfo', e.target.value)} placeholder="01001" className={RIC} /></div>
        </div>
      </div>

      {/* Imzo */}
      <div className="border-t border-slate-100 pt-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">{t('settings.nakladnoy.signatoriesTitle')}</p>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-semibold text-slate-500">{t('settings.nakladnoy.directorLabel')}</label>
              <div onClick={() => upd('show_director', !cfg.show_director)}
                className={`relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0 ${cfg.show_director ? 'bg-blue-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${cfg.show_director ? 'translate-x-3' : ''}`} />
              </div>
            </div>
            <input value={cfg.director} onChange={e => upd('director', e.target.value)} placeholder={t('settings.nakladnoy.fullNamePlaceholder')} className={RIC} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-semibold text-slate-500">{t('settings.nakladnoy.chiefAccountantLabel')}</label>
              <div onClick={() => upd('show_accountant', !cfg.show_accountant)}
                className={`relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0 ${cfg.show_accountant ? 'bg-blue-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${cfg.show_accountant ? 'translate-x-3' : ''}`} />
              </div>
            </div>
            <input value={cfg.accountant} onChange={e => upd('accountant', e.target.value)} placeholder={t('settings.nakladnoy.fullNamePlaceholder')} className={RIC} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-semibold text-slate-500">{t('settings.nakladnoy.storekeeperLabel')}</label>
              <div onClick={() => upd('show_storekeeper', !cfg.show_storekeeper)}
                className={`relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0 ${cfg.show_storekeeper ? 'bg-blue-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${cfg.show_storekeeper ? 'translate-x-3' : ''}`} />
              </div>
            </div>
            <input value={cfg.storekeeper} onChange={e => upd('storekeeper', e.target.value)} placeholder={t('settings.nakladnoy.fullNamePlaceholder')} className={RIC} />
          </div>
        </div>
      </div>

      <div><label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.nakladnoy.noteLabel')}</label>
        <input value={cfg.footer_note} onChange={e => upd('footer_note', e.target.value)} placeholder={t('settings.nakladnoy.notePlaceholder')} className={RIC} /></div>

      {/* Togglelar */}
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{t('settings.nakladnoy.fieldsSectionTitle')}</p>
        <ToggleGroup title={t('settings.receipt.groupHeader')} cfg={cfg} upd={upd} fields={[
          ['show_contractor_name', t('settings.nakladnoy.fieldCustomerName')],
          ['show_branch', t('settings.receipt.fieldBranch')],
          ['show_account_username', t('settings.nakladnoy.fieldUsername')],
          ['show_employee', t('settings.nakladnoy.fieldEmployeeName')],
          ['show_status', t('settings.receipt.fieldStatus')],
          ['show_number', t('settings.nakladnoy.fieldDocNumber')],
          ['show_date', t('common.date')],
        ]} />
        <ToggleGroup title={t('settings.nakladnoy.groupColumns')} cfg={cfg} upd={upd} fields={[
          ['show_ordering_number', t('settings.receipt.fieldOrderNumber')],
          ['show_measurement', t('settings.receipt.fieldUnit')],
          ['show_package', t('settings.nakladnoy.fieldPackageName')],
          ['show_quantity_in_package', t('settings.nakladnoy.fieldPackageQty')],
          ['show_price', t('common.price')],
          ['show_discount', t('common.discount')],
          ['show_price_with_discount', t('settings.receipt.fieldDiscountedPrice')],
          ['show_currency', t('common.currency')],
          ['show_net_price', t('settings.receipt.fieldNetPrice')],
          ['show_warehouse', t('settings.receipt.fieldWarehouse')],
          ['show_sku', t('settings.nakladnoy.fieldSku')],
          ['show_image', t('settings.nakladnoy.fieldProductImage')],
          ['show_category', t('common.category')],
        ]} />
        <ToggleGroup title={t('settings.receipt.groupTotal')} cfg={cfg} upd={upd} fields={[
          ['show_totals', t('settings.receipt.fieldTotalSum')],
          ['show_total_national', t('settings.receipt.fieldTotalNational')],
          ['show_total_quantity', t('settings.receipt.fieldTotalQty')],
          ['show_total_quantity_package', t('settings.nakladnoy.fieldTotalPackageQty')],
          ['show_payment_amounts', t('settings.nakladnoy.fieldPaymentAmount')],
          ['show_exact_discounts', t('settings.nakladnoy.fieldDiscountAmount')],
          ['show_percent_discount', t('settings.nakladnoy.fieldPercentDiscount')],
        ]} />
        <ToggleGroup title={t('settings.receipt.groupDebt')} cfg={cfg} upd={upd} fields={[
          ['show_contractor_debts', t('settings.receipt.fieldCurrentDebt')],
          ['show_before_debts', t('settings.receipt.fieldPrevDebt')],
          ['show_last_payment', t('settings.receipt.fieldLastPayment')],
          ['show_debts', t('settings.nakladnoy.fieldTotalDebts')],
        ]} />
        <ToggleGroup title={t('settings.receipt.groupExtra')} cfg={cfg} upd={upd} fields={[
          ['show_contractor_contacts', t('settings.nakladnoy.fieldCustomerContacts')],
          ['show_note', t('settings.receipt.fieldNote')],
        ]} />
      </div>
    </div>
  );
}

// ── Receipt / Nakladnoy settings tab ──────────────────────────────────────────
function ReceiptTab() {
  const { t } = useLang();
  const { user } = useAuth();
  // Chek shablonlarini faqat admin/direktor saqlaydi (backend boshqa rollarga 403 qaytaradi)
  const canSaveReceipt = ['admin', 'director'].includes(user?.role);
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
        const r58 = d.r58 ? { ...defaultReceiptCfg, ...migrateAccountName(d.r58) } : undefined;
        const r80 = d.r80 ? { ...defaultReceiptCfg, show_qr: true, ...migrateAccountName(d.r80) } : undefined;
        const nak = d.nak ? { ...defaultNakladnoyCfg, ...migrateAccountName(d.nak) } : undefined;
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
    }).catch(e => toast.error(e.response?.data?.detail || t('settings.receipt.saveError')));
  };

  const currentCfg = sub === '58' ? cfg58 : sub === '80' ? cfg80 : cfgNak;
  const updFn = sub === '58' ? upd58 : sub === '80' ? upd80 : updNak;

  if (loading) return <div className="text-sm text-slate-500 animate-pulse py-10 px-4">{t('settings.receipt.templatesLoading')}</div>;

  return (
    <div className="space-y-4">
      {/* Sub-tab bar */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {SUB_TABS(t).map(st => (
          <button key={st.id} onClick={() => setSub(st.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${sub === st.id ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            <span>{st.icon}</span>{st.label}
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
              {sub === '58' ? t('settings.receipt.preview58') : sub === '80' ? t('settings.receipt.preview80') : t('settings.receipt.previewNak')}
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
            {t('settings.saved')}
          </span>
        )}
        {canSaveReceipt && (
          <button onClick={handleSave}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm rounded-xl transition-colors flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
            {t('settings.receipt.saveSettings')}
          </button>
        )}
      </div>
    </div>
  );
}

function FiskalTab() {
  const { t } = useLang();
  const { user } = useAuth();
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  // T3.18: qurilma-filial biriktirishni faqat admin/direktor boshqaradi; qolganlar faqat o'z filiali qurilmasini ishlatadi
  const canManage = ['admin', 'director'].includes(user?.role);
  const [registered, setRegistered]   = useState([]);   // serverdagi fiscal_devices (admin: hammasi, boshqalar: /mine)
  const [registryLoaded, setRegistryLoaded] = useState(false);
  const restrictedRef = useRef(false);                   // oddiy rol + ro'yxatdan o'tgan qurilma bor -> faqat shulardan
  const { branches } = useBranches();
  const [attachBranch, setAttachBranch] = useState({});  // { [factoryId]: branchId }
  const [manualId, setManualId]       = useState('');
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
      // (T3.18: serverda qurilmalar biriktirilgan oddiy rol uchun — faqat o'z qurilmasi, quyidagi effektda)
      if (!selectedId && list.length > 0 && !restrictedRef.current) {
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

  // T3.18: serverdagi biriktirilgan qurilmalar
  const loadRegistered = async () => {
    try {
      const r = await api.get(canManage ? '/fiscal-devices' : '/fiscal-devices/mine', { _suppressToast: true });
      const list = Array.isArray(r.data) ? r.data : [];
      setRegistered(list);
      restrictedRef.current = !canManage && list.length > 0;
      if (!canManage && list.length > 0) {
        // Bitta qurilma bo'lsa avtomatik tanlanadi va o'zgartirib bo'lmaydi; bir nechta bo'lsa — shulardan tanlanadi
        const cur = (() => { try { return JSON.parse(localStorage.getItem('fiskalId') || 'null'); } catch { return null; } })();
        if (list.length === 1 || !list.some(d => d.factory_id === cur)) {
          const fid = list.length === 1 ? list[0].factory_id : null;
          setSelectedId(fid);
          localStorage.setItem('fiskalId', JSON.stringify(fid));
        }
      }
    } catch { setRegistered([]); }
    finally { setRegistryLoaded(true); }
  };
  useEffect(() => {
    loadRegistered();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManage]);

  const lockedToRegistry = !canManage && registered.length > 0;
  const lockedSingle = lockedToRegistry && registered.length === 1;
  const visibleModules = lockedToRegistry
    ? registered.map(d => ({ FactoryID: d.factory_id, Description: d.label || '' }))
    : modules;
  const branchLabel = (id) => (id ? (branches.find(b => b.id === id)?.name || `#${id}`) : tf('settings.terminals.allBranches', 'Barcha filiallar'));
  const registeredFor = (fid) => registered.find(d => d.factory_id === fid);

  const attachDevice = async (fid) => {
    const bid = attachBranch[fid] || manualBranchOf(fid);
    try {
      await api.post('/fiscal-devices', { factory_id: fid, branch_id: bid ? Number(bid) : null }, { _suppressToast: true });
      toast.success(tf('settings.fiscal.attached', 'Fiskal modul filialga biriktirildi'));
      setManualId('');
      loadRegistered();
    } catch (e) { toast.error(e.response?.data?.detail || t('auth.errGeneral')); }
  };
  const manualBranchOf = (fid) => (fid === manualId.trim() ? attachBranch.__manual : '');
  const detachDevice = async (dev) => {
    try {
      await api.delete(`/fiscal-devices/${dev.id}`, { _suppressToast: true });
      loadRegistered();
    } catch (e) { toast.error(e.response?.data?.detail || t('auth.errGeneral')); }
  };

  const selectModule = (factoryId) => {
    if (lockedSingle) return;   // T3.18: bitta biriktirilgan qurilma o'zgartirilmaydi
    setSelectedId(factoryId);
    localStorage.setItem('fiskalId', JSON.stringify(factoryId));
  };

  const toggleFiskal = (val) => {
    setFiskalSend(val);
    localStorage.setItem('fiskalSend', JSON.stringify(val));
    if (val) toast.success(t('settings.fiscal.enabled'));
    else toast(t('settings.fiscal.disabled'));
  };

  const statusColor = {
    checking: 'bg-amber-400',
    online:   'bg-emerald-500',
    offline:  'bg-red-500',
  }[status];

  const statusLabel = {
    checking: t('settings.fiscal.statusChecking'),
    online:   t('settings.fiscal.statusOnline'),
    offline:  t('settings.fiscal.statusOffline'),
  }[status];

  return (
    <div className="max-w-xl space-y-4">

      {/* ── Header card ── */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-slate-800">Hippo Communicator</h2>
            <p className="text-xs text-slate-400 mt-0.5">{t('settings.fiscal.integrationDesc')}</p>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold rounded-xl transition-all disabled:opacity-50"
          >
            <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {t('common.refresh')}
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
            {t('settings.fiscal.offlineHint')}
          </p>
        )}
      </div>

      {/* ── T3.18: modullarni filial/kassaga biriktirish (admin/direktor) ── */}
      {canManage && registryLoaded && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-700 mb-1">{tf('settings.fiscal.attachTitle', 'Fiskal modullarni filialga biriktirish')}</h3>
          <p className="text-xs text-slate-400 mb-3">
            {tf('settings.fiscal.attachDesc', "Ro'yxat bo'lsa, fiskal natija faqat sotuv filialiga biriktirilgan modul bilan qabul qilinadi. Ro'yxat bo'sh bo'lsa cheklov yo'q.")}
          </p>
          <div className="space-y-2">
            {registered.map(d => (
              <div key={d.id} className="flex items-center justify-between px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 text-xs">
                <div>
                  <span className="font-black tracking-widest text-slate-800">{d.factory_id}</span>
                  <span className="ml-2 text-slate-500">{branchLabel(d.branch_id)}</span>
                </div>
                <button onClick={() => detachDevice(d)} className="text-red-500 hover:text-red-700 font-semibold">
                  {tf('common.delete', "O'chirish")}
                </button>
              </div>
            ))}
            {!registered.length && (
              <p className="text-xs text-slate-400">{tf('settings.fiscal.noAttached', "Biriktirilgan modul yo'q")}</p>
            )}
          </div>
          <div className="mt-3 space-y-2">
            {status === 'online' && modules.filter(m => !registeredFor(m.FactoryID)).map(m => (
              <div key={m.FactoryID} className="flex items-center gap-2 text-xs">
                <span className="font-black tracking-widest flex-1">{m.FactoryID}</span>
                <select value={attachBranch[m.FactoryID] || ''} onChange={e => setAttachBranch({ ...attachBranch, [m.FactoryID]: e.target.value })}
                  className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
                  <option value="">{tf('settings.terminals.allBranches', 'Barcha filiallar')}</option>
                  {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
                <button onClick={() => attachDevice(m.FactoryID)} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl">
                  {tf('settings.fiscal.attach', 'Biriktirish')}
                </button>
              </div>
            ))}
            <div className="flex items-center gap-2 text-xs">
              <input value={manualId} onChange={e => setManualId(e.target.value)} maxLength={64}
                placeholder={tf('settings.fiscal.manualId', "Factory ID (qo'lda)")}
                className="flex-1 border border-slate-200 rounded-xl px-2 py-1.5" />
              <select value={attachBranch.__manual || ''} onChange={e => setAttachBranch({ ...attachBranch, __manual: e.target.value })}
                className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
                <option value="">{tf('settings.terminals.allBranches', 'Barcha filiallar')}</option>
                {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <button disabled={!manualId.trim()} onClick={() => attachDevice(manualId.trim())}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl disabled:opacity-40">
                {tf('settings.fiscal.attach', 'Biriktirish')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Fiskal modullar ── */}
      {status === 'online' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-700 mb-3">{t('settings.fiscal.connectedDevices')}</h3>

          {lockedSingle && (
            <p className="text-xs text-slate-500 mb-2">{tf('settings.fiscal.lockedSingle', "Sizning filialingizga biriktirilgan modul avtomatik tanlangan va o'zgartirilmaydi.")}</p>
          )}
          {visibleModules.length === 0 ? (
            <div className="text-center py-6 text-slate-400">
              <svg className="w-10 h-10 mx-auto mb-2 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
              </svg>
              <p className="text-sm font-medium">{t('settings.fiscal.noDevicesFound')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {visibleModules.map((m) => {
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
                        {t('settings.fiscal.selected')}
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
              <h3 className="text-sm font-bold text-slate-800">{t('settings.fiscal.salesFiscalization')}</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                {t('settings.fiscal.salesFiscalizationDesc')}
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
                <p className="text-xs font-bold text-emerald-700">{t('settings.fiscal.fiscalizationActive')}</p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  {t('settings.fiscal.device')}: <span className="font-black tracking-widest">{selectedId}</span>
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── T4.2: filial rekvizitlari va fiskal qamrov hisoboti ── */}
      {canManage && <BranchRequisitesSection />}
      {(canManage || user?.role === 'accountant') && <FiscalCoverage />}

    </div>
  );
}


// ── T4.2: filial rekvizitlari (kod, yuridik nom, STIR, soliq rejimi, ish vaqti) va filial chek shabloni ──────
// Bo'sh qoldirilgan maydon chekda korxona shablonidan olinadi. STIR: 9 xonali (JSHSHIR — 14 xonali).
const BRANCH_WEEK_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const BRANCH_DAY_FALLBACK = { mon: 'Dushanba', tue: 'Seshanba', wed: 'Chorshanba', thu: 'Payshanba', fri: 'Juma', sat: 'Shanba', sun: 'Yakshanba' };
const defaultHours = () => Object.fromEntries(BRANCH_WEEK_DAYS.map(d => [d, { open: '09:00', close: '18:00', closed: d === 'sun' }]));

function BranchRequisitesSection() {
  const { t } = useLang();
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const { branches } = useBranches();
  const [selId, setSelId] = useState('');
  const [form, setForm] = useState(null);
  const [useHours, setUseHours] = useState(false);
  const [tplAll, setTplAll] = useState({});
  const [tplType, setTplType] = useState('r80');
  const [saving, setSaving] = useState(false);

  const select = async (id) => {
    setSelId(id);
    setForm(null);
    if (!id) return;
    const b = branches.find(x => String(x.id) === String(id));
    if (!b) return;
    setForm({
      code: b.code || '', legal_name: b.legal_name || '', stir: b.stir || '', tax_regime: b.tax_regime || '',
      address: b.address || '', phone: b.phone || '',
      hours: { ...defaultHours(), ...(b.working_hours || {}) },
    });
    setUseHours(!!b.working_hours);
    try {
      const r = await api.get(`/branches/${id}/receipt_templates`, { _suppressToast: true });
      setTplAll(r.data?.receipt_templates || {});
    } catch { setTplAll({}); }
  };

  const upd = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const updDay = (d, k, v) => setForm(f => ({ ...f, hours: { ...f.hours, [d]: { ...f.hours[d], [k]: v } } }));

  const save = async () => {
    const stir = form.stir.trim();
    if (stir && !/^(\d{9}|\d{14})$/.test(stir)) {
      toast.error(tf('branchSettings.stirInvalid', "STIR 9 xonali (JSHSHIR 14 xonali) raqam bo'lishi kerak"));
      return;
    }
    setSaving(true);
    try {
      const body = {
        code: form.code.trim() || null,
        legal_name: form.legal_name.trim() || null,
        stir: stir || null,
        tax_regime: form.tax_regime || null,
        address: form.address.trim() || null,
        phone: form.phone.trim() || null,
        working_hours: useHours ? form.hours : null,
      };
      await api.patch(`/branches/${selId}`, body, { _suppressToast: true });
      invalidateBranches();   // T3.8: boshqa sahifalardagi filial keshi ham yangilansin
      toast.success(tf('branchSettings.saved', 'Filial sozlamalari saqlandi'));
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : tf('branchSettings.saveError', "Saqlab bo'lmadi: kiritilgan qiymatlarni tekshiring"));
    } finally { setSaving(false); }
  };

  const tplCfg = tplAll[tplType] || {};
  const setTplField = (k, v) => setTplAll(a => ({ ...a, [tplType]: { ...(a[tplType] || {}), [k]: v } }));
  const saveTpl = async () => {
    setSaving(true);
    try {
      const body = { r58: tplAll.r58 || {}, r80: tplAll.r80 || {}, nak: tplAll.nak || {} };
      // Bo'sh matn maydonlari olib tashlanadi — bo'sh shablon = korxona shabloni
      Object.keys(body).forEach(k => {
        body[k] = Object.fromEntries(Object.entries(body[k]).filter(([, v]) => v !== '' && v != null));
      });
      const r = await api.put(`/branches/${selId}/receipt_templates`, body, { _suppressToast: true });
      setTplAll(r.data?.receipt_templates || {});
      toast.success(tf('branchSettings.tplSaved', 'Filial chek shabloni saqlandi'));
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : t('auth.errGeneral'));
    } finally { setSaving(false); }
  };

  const inp = 'w-full border border-slate-200 rounded-xl px-2 py-1.5 text-xs bg-white';
  const lbl = 'flex flex-col gap-1 text-xs text-slate-500';

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('branchSettings.title', 'Filial rekvizitlari')}</h3>
      <p className="text-xs text-slate-400 mt-0.5 mb-3">
        {tf('branchSettings.desc', "Yuridik nom, STIR, manzil va telefon shu filial ombori orqali qilingan sotuv chekida chiqadi. Bo'sh maydonlar korxona shablonidan olinadi.")}
      </p>
      <select value={selId} onChange={e => select(e.target.value)} className={inp}>
        <option value="">{tf('branchSettings.pick', 'Filialni tanlang')}</option>
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>

      {form && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <label className={lbl}>{tf('branchSettings.code', 'Filial kodi')}
              <input className={inp} maxLength={20} value={form.code} onChange={e => upd('code', e.target.value)} />
            </label>
            <label className={lbl}>{tf('branchSettings.stir', 'STIR / JSHSHIR')}
              <input className={inp} maxLength={14} inputMode="numeric" value={form.stir} onChange={e => upd('stir', e.target.value.replace(/\D/g, ''))} />
            </label>
            <label className={`${lbl} col-span-2`}>{tf('branchSettings.legalName', 'Yuridik nom')}
              <input className={inp} maxLength={200} value={form.legal_name} onChange={e => upd('legal_name', e.target.value)} />
            </label>
            <label className={lbl}>{tf('branchSettings.taxRegime', 'Soliq rejimi')}
              <select className={inp} value={form.tax_regime} onChange={e => upd('tax_regime', e.target.value)}>
                <option value="">{tf('branchSettings.regimeNone', 'Belgilanmagan')}</option>
                <option value="vat">{tf('branchSettings.regimeVat', "QQS to'lovchi")}</option>
                <option value="turnover">{tf('branchSettings.regimeTurnover', 'Aylanma soliq')}</option>
              </select>
            </label>
            <label className={lbl}>{tf('branchSettings.phone', 'Telefon')}
              <input className={inp} maxLength={20} value={form.phone} onChange={e => upd('phone', e.target.value)} />
            </label>
            <label className={`${lbl} col-span-2`}>{tf('branchSettings.address', 'Manzil')}
              <input className={inp} maxLength={200} value={form.address} onChange={e => upd('address', e.target.value)} />
            </label>
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs font-semibold text-slate-700">
              <input type="checkbox" checked={useHours} onChange={e => setUseHours(e.target.checked)} />
              {tf('branchSettings.hours', 'Ish vaqti')}
            </label>
            {useHours && (
              <div className="mt-2 space-y-1">
                {BRANCH_WEEK_DAYS.map(d => (
                  <div key={d} className="flex items-center gap-2 text-xs">
                    <span className="w-24 text-slate-600">{tf(`branchSettings.day.${d}`, BRANCH_DAY_FALLBACK[d])}</span>
                    <label className="flex items-center gap-1 text-slate-500">
                      <input type="checkbox" checked={!!form.hours[d].closed} onChange={e => updDay(d, 'closed', e.target.checked)} />
                      {tf('branchSettings.closed', 'Yopiq')}
                    </label>
                    <input type="time" disabled={form.hours[d].closed} value={form.hours[d].open || ''} onChange={e => updDay(d, 'open', e.target.value)} className="border border-slate-200 rounded-lg px-1.5 py-1 disabled:opacity-40" />
                    <span>–</span>
                    <input type="time" disabled={form.hours[d].closed} value={form.hours[d].close || ''} onChange={e => updDay(d, 'close', e.target.value)} className="border border-slate-200 rounded-lg px-1.5 py-1 disabled:opacity-40" />
                  </div>
                ))}
              </div>
            )}
          </div>

          <button onClick={save} disabled={saving} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl disabled:opacity-50">
            {t('common.save')}
          </button>

          <div className="pt-3 border-t border-slate-100">
            <h4 className="text-xs font-bold text-slate-700 mb-1">{tf('branchSettings.tplTitle', 'Chek shabloni (filial)')}</h4>
            <p className="text-xs text-slate-400 mb-2">{tf('branchSettings.tplDesc', "Bo'sh qoldirilsa chek korxona shabloni bilan chiqadi.")}</p>
            <div className="flex gap-1 mb-2">
              {['r58', 'r80', 'nak'].map(k => (
                <button key={k} onClick={() => setTplType(k)}
                  className={`px-3 py-1 rounded-xl text-xs font-semibold ${tplType === k ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'}`}>
                  {k === 'nak' ? tf('branchSettings.tplNak', 'Nakladnoy') : k.slice(1) + ' mm'}
                </button>
              ))}
            </div>
            <label className={lbl}>{tf('branchSettings.tplHeader', 'Sarlavha matni')}
              <input className={inp} maxLength={500} value={tplCfg.header || ''} onChange={e => setTplField('header', e.target.value)} />
            </label>
            <label className={`${lbl} mt-2`}>{tf('branchSettings.tplFooter', 'Pastki matn')}
              <input className={inp} maxLength={500} value={tplCfg.footer || ''} onChange={e => setTplField('footer', e.target.value)} />
            </label>
            <button onClick={saveTpl} disabled={saving} className="mt-3 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl disabled:opacity-50">
              {t('common.save')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


// ── T3.18: To'lov terminallari (Payme/Click/Uzum/Uzcard/Humo) — filial bo'yicha, ichki yozuv ──────────────
// Sirli kalitlar saqlanmaydi. Sotuvda click/payme/uzum to'lovi shu terminal bo'yicha tranzaksiya raqami bilan yoziladi.
const TERMINAL_PROVIDERS = ['click', 'payme', 'uzum', 'uzcard', 'humo'];

function PaymentTerminalsSection() {
  const { t } = useLang();
  const { user } = useAuth();
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const canManage = ['admin', 'director'].includes(user?.role);
  const [rows, setRows] = useState([]);
  const { branches } = useBranches();
  const [loading, setLoading] = useState(false);
  const emptyForm = { provider: 'click', branch_id: '', label: '', merchant_id: '', terminal_id: '', require_reference: true };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(canManage ? '/payment-terminals' : '/payment-terminals/mine', { _suppressToast: true });
      setRows(Array.isArray(r.data) ? r.data : []);
    } catch { setRows([]); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManage]);

  const branchName = (id) => (id ? (branches.find(b => b.id === id)?.name || `#${id}`) : tf('settings.terminals.allBranches', 'Barcha filiallar'));

  const add = async () => {
    try {
      await api.post('/payment-terminals', {
        provider: form.provider,
        branch_id: form.branch_id ? Number(form.branch_id) : null,
        label: form.label || null,
        merchant_id: form.merchant_id || null,
        terminal_id: form.terminal_id || null,
        require_reference: !!form.require_reference,
      }, { _suppressToast: true });
      toast.success(tf('settings.terminals.added', "Terminal qo'shildi"));
      setForm(emptyForm);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('auth.errGeneral')); }
  };

  const patch = async (row, body) => {
    try { await api.put(`/payment-terminals/${row.id}`, body, { _suppressToast: true }); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('auth.errGeneral')); }
  };

  const remove = async (row) => {
    if (!window.confirm(tf('settings.terminals.confirmDelete', "Terminal o'chirilsinmi?"))) return;
    try { await api.delete(`/payment-terminals/${row.id}`, { _suppressToast: true }); load(); }
    catch (e) { toast.error(e.response?.data?.detail || t('auth.errGeneral')); }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <h3 className="text-base font-bold text-slate-800">{tf('settings.terminals.title', "To'lov terminallari")}</h3>
        <p className="text-xs text-slate-400 mt-0.5 mb-3">
          {tf('settings.terminals.desc', "Filial bo'yicha Payme/Click/Uzum terminallari. Terminal bor filialda to'lovda tranzaksiya raqami majburiy bo'lishi mumkin.")}
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="py-1">{tf('settings.terminals.provider', 'Provayder')}</th>
                <th>{tf('settings.terminals.branch', 'Filial')}</th>
                <th>{tf('settings.terminals.label', 'Nomi')}</th>
                <th>{tf('settings.terminals.merchant', 'Merchant ID')}</th>
                <th>{tf('settings.terminals.terminalId', 'Terminal ID')}</th>
                <th>{tf('settings.terminals.requireRef', 'Raqam majburiy')}</th>
                <th>{tf('settings.terminals.active', 'Faol')}</th>
                {canManage && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t border-slate-100">
                  <td className="py-1.5 font-bold uppercase">{r.provider}</td>
                  <td>{branchName(r.branch_id)}</td>
                  <td>{r.label || '—'}</td>
                  <td>{r.merchant_id || '—'}</td>
                  <td>{r.terminal_id || '—'}</td>
                  <td>
                    <input type="checkbox" checked={!!r.require_reference} disabled={!canManage}
                      onChange={e => patch(r, { require_reference: e.target.checked })} />
                  </td>
                  <td>
                    <input type="checkbox" checked={r.is_active !== false} disabled={!canManage}
                      onChange={e => patch(r, { is_active: e.target.checked })} />
                  </td>
                  {canManage && (
                    <td className="text-right">
                      <button onClick={() => remove(r)} className="text-red-500 hover:text-red-700 font-semibold">
                        {tf('common.delete', "O'chirish")}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={8} className="py-6 text-center text-slate-400">
                  {loading ? '...' : tf('settings.terminals.empty', "Terminallar yo'q")}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {canManage && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-7 gap-2 items-end">
            <select value={form.provider} onChange={e => setForm({ ...form, provider: e.target.value })}
              className="border border-slate-200 rounded-xl px-2 py-2 text-xs bg-white">
              {TERMINAL_PROVIDERS.map(p => <option key={p} value={p}>{p.toUpperCase()}</option>)}
            </select>
            <select value={form.branch_id} onChange={e => setForm({ ...form, branch_id: e.target.value })}
              className="border border-slate-200 rounded-xl px-2 py-2 text-xs bg-white">
              <option value="">{tf('settings.terminals.allBranches', 'Barcha filiallar')}</option>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <input value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} maxLength={100}
              placeholder={tf('settings.terminals.label', 'Nomi')} className="border border-slate-200 rounded-xl px-2 py-2 text-xs" />
            <input value={form.merchant_id} onChange={e => setForm({ ...form, merchant_id: e.target.value })} maxLength={64}
              placeholder={tf('settings.terminals.merchant', 'Merchant ID')} className="border border-slate-200 rounded-xl px-2 py-2 text-xs" />
            <input value={form.terminal_id} onChange={e => setForm({ ...form, terminal_id: e.target.value })} maxLength={64}
              placeholder={tf('settings.terminals.terminalId', 'Terminal ID')} className="border border-slate-200 rounded-xl px-2 py-2 text-xs" />
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <input type="checkbox" checked={form.require_reference}
                onChange={e => setForm({ ...form, require_reference: e.target.checked })} />
              {tf('settings.terminals.requireRef', 'Raqam majburiy')}
            </label>
            <button onClick={add} className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl">
              {tf('settings.terminals.add', "Qo'shish")}
            </button>
          </div>
        )}
      </div>

      {canManage && (
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm">
          <PaymentReconciliation />
        </div>
      )}
    </div>
  );
}

// ── Ixtiyoriy modullar va Pullik paketlar boshqaruvi ─────────────────────────
function ModulesCard({ companyId }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const features = useCompanyFeatures();
  const [packages, setPackages] = useState([]);
  const [saving, setSaving] = useState(null);

  useEffect(() => {
    api.get('/billing/my-company/packages')
      .then(r => setPackages(r.data || []))
      .catch(() => setPackages([]));
  }, []);

  const toggle = async (key, column, value) => {
    if (!companyId) return;
    setSaving(key);
    try {
      await api.put(`/companies/${companyId}`, { [column]: value });
      await refreshCompanyFeatures();
      toast.success(t('settings.general.settingSaved') || 'Sozlama saqlandi');
    } catch (e) {
      toast.error(e.response?.data?.detail || t('auth.errGeneral') || 'Xatolik yuz berdi');
    } finally {
      setSaving(null);
    }
  };

  const MODULES = [
    {
      key: 'manufacturing',
      column: 'manufacturing_enabled',
      name: t('features.manufacturing.title') || 'Ishlab chiqarish',
      desc: t('features.manufacturing.desc') || 'Retseptlar, xom-ashyo sarfi va ishlab chiqarish buyurtmalari',
      icon: '🏭',
    },
    {
      key: 'distribution',
      column: 'distribution_enabled',
      name: t('features.distribution.title') || 'Distribyutsiya va logistika',
      desc: t('features.distribution.desc') || "Savdo agentlari, kuryerlar, marshrutlar va do'konlar monitoringi",
      icon: '🚚',
    },
    {
      key: 'delivery_automation',
      column: 'orders_auto_create_sale',
      name: 'Yetkazib berish avtomatikasi',
      desc: 'Kuryer mijozga topshirganda avtomatik kassa cheki va sotuv shakllantirish',
      icon: '⚡',
    },
  ];

  return (
    <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-bold text-slate-800">{t('features.cardTitle') || "Qo'shimcha modullar va paketlar"}</h3>
        <button
          onClick={() => navigate('/admin/tariflar?tab=paketlar')}
          className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
        >
          Paketlar do'koni <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
      <p className="text-[11px] text-slate-400 mb-4">{t('features.cardDesc') || "Biznesingiz ehtiyojiga qarab ixtiyoriy funksiyalarni yoqing yoki o'chiring."}</p>

      <div className="space-y-3.5 divide-y divide-slate-100">
        {MODULES.map(({ key, column, name, desc, icon }) => {
          const pkg = packages.find(p => p.code === key);
          const canUse = pkg ? (pkg.included_in_tariff || pkg.is_active_package) : !!features?.[key];
          const on = !!features?.[key];

          return (
            <div key={key} className="pt-3.5 first:pt-0 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm">{icon}</span>
                  <p className="text-xs font-bold text-slate-800">{name}</p>

                  {/* Status Badge */}
                  {pkg?.included_in_tariff ? (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                      <Check className="w-3 h-3" /> Tarifda mavjud
                    </span>
                  ) : pkg?.is_active_package ? (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border flex items-center gap-1 ${
                      pkg.days_left <= 3
                        ? 'bg-amber-50 text-amber-700 border-amber-300 animate-pulse'
                        : 'bg-blue-50 text-blue-700 border-blue-200'
                    }`}>
                      {pkg.days_left <= 3 ? <AlertTriangle className="w-3 h-3" /> : <Check className="w-3 h-3" />}
                      {pkg.days_left <= 3 ? `${pkg.days_left} kun qoldi!` : `Faol (${pkg.days_left} kun)`}
                    </span>
                  ) : (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 flex items-center gap-1">
                      <Lock className="w-2.5 h-2.5" /> Alohida paket
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 mt-1 leading-snug">{desc}</p>

                {!canUse && pkg && (
                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-[11px] font-bold text-slate-700">
                      {Number(pkg.price_per_month || 0).toLocaleString('uz-UZ')} so'm <span className="font-normal text-slate-400">/ oy</span>
                    </span>
                    <button
                      onClick={() => navigate('/admin/tariflar?tab=paketlar')}
                      className="text-[11px] font-bold text-blue-600 hover:text-blue-700 hover:underline flex items-center gap-1"
                    >
                      Ulash <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>

              {/* Toggle Switch */}
              <div className="shrink-0 pt-0.5">
                {canUse ? (
                  <button
                    type="button"
                    disabled={features === null || saving === key}
                    onClick={() => toggle(key, column, !on)}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${on ? 'bg-blue-600' : 'bg-slate-200'}`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${on ? 'translate-x-6' : 'translate-x-1'}`} />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => navigate('/admin/tariflar?tab=paketlar')}
                    title="Paketni xarid qilish"
                    className="p-1.5 rounded-lg bg-slate-100 hover:bg-blue-50 text-slate-400 hover:text-blue-600 transition-colors"
                  >
                    <Lock className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Sodiqlik dasturi (T2.12): ball stavkasi, ball qiymati, daraja chegaralari, filial qoidalari, kredit limit ──
function LoyaltyCard({ companyId }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [branches, setBranches] = useState([]);
  const [savingBranch, setSavingBranch] = useState(null);
  const [savingScope, setSavingScope] = useState(false);

  const errText = (e) => {
    const d = e.response?.data?.detail;
    if (Array.isArray(d)) return d.map(x => x.msg || '').filter(Boolean).join('; ') || t('auth.errGeneral');
    return d || t('auth.errGeneral');
  };

  useEffect(() => {
    api.get('/loyalty/settings').then(r => setForm(r.data)).catch(e => { if (e.response?.status !== 403) toast.error(errText(e)); });
    api.get('/loyalty/branch-rules').then(r => setBranches(r.data || [])).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const set = (key, value) => setForm(f => ({ ...f, [key]: value }));

  const save = async () => {
    setSaving(true);
    try {
      const body = {
        is_enabled: !!form.is_enabled,
        points_percent: Number(form.points_percent),
        point_value: Number(form.point_value),
        default_cashback_percent: Number(form.default_cashback_percent),
        max_redeem_percent: Number(form.max_redeem_percent),
        accrue_on_unpaid: !!form.accrue_on_unpaid,
        return_reverses_loyalty: !!form.return_reverses_loyalty,
        tier_bronze: parseInt(form.tier_bronze, 10),
        tier_silver: parseInt(form.tier_silver, 10),
        tier_gold: parseInt(form.tier_gold, 10),
      };
      const r = await api.put('/loyalty/settings', body);
      setForm(r.data);
      toast.success(tf('settings.loyalty.saved', 'Sodiqlik sozlamalari saqlandi'));
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const saveScope = async (value) => {
    if (!companyId) return;
    setSavingScope(true);
    try {
      await api.put(`/companies/${companyId}`, { credit_limit_scope: value });
      await refreshCompanyFeatures();
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSavingScope(false);
    }
  };

  const saveBranch = async (row) => {
    setSavingBranch(row.branch_id);
    try {
      const ov = row.cashback_percent_override;
      const r = await api.put(`/loyalty/branch-rules/${row.branch_id}`, {
        is_enabled: !!row.is_enabled,
        cashback_percent_override: ov === '' || ov === null || ov === undefined ? null : Number(ov),
      });
      setBranches(prev => prev.map(b => (b.branch_id === row.branch_id ? r.data : b)));
      toast.success(tf('settings.loyalty.branchSaved', 'Filial qoidasi saqlandi'));
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSavingBranch(null);
    }
  };

  const updateBranch = (id, patch) => setBranches(prev => prev.map(b => (b.branch_id === id ? { ...b, ...patch } : b)));

  const toggle = (on, onClick, disabled) => (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${on ? 'bg-blue-600' : 'bg-slate-200'}`}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${on ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  );

  const numField = (label, k, { step = '1', min = '0', max, hint } = {}) => (
    <div key={k}>
      <label className="block text-xs font-semibold text-slate-600 mb-1">{label}</label>
      <input
        type="number" step={step} min={min} max={max}
        value={form[k] ?? ''}
        onChange={e => set(k, e.target.value)}
        className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {hint && <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{hint}</p>}
    </div>
  );

  if (!form) return null;
  const scope = features?.credit_limit_scope || 'distributor';

  return (
    <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5">
      <h3 className="text-sm font-bold text-slate-800">{tf('settings.loyalty.title', 'Sodiqlik dasturi')}</h3>
      <p className="text-[11px] text-slate-400 mt-0.5 mb-4">
        {tf('settings.loyalty.desc', "Keshbek, ball va kredit limit qoidalari. Sozlama kiritilmasa: 1% ball, 1 ball = 1 so'm, daraja 1000/5000/10000.")}
      </p>

      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-700">{tf('settings.loyalty.enabled', 'Sodiqlik dasturi yoqilgan')}</p>
          <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{tf('settings.loyalty.enabledDesc', "O'chirilsa keshbek va ball yig'ilmaydi hamda sarflanmaydi")}</p>
        </div>
        {toggle(!!form.is_enabled, () => set('is_enabled', !form.is_enabled))}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        {numField(tf('settings.loyalty.pointsPercent', "Ball stavkasi (% sotuvdan)"), 'points_percent', { step: '0.1', max: '100' })}
        {numField(tf('settings.loyalty.pointValue', "1 ball qiymati (so'm)"), 'point_value', { step: '0.01', min: '0.01' })}
        {numField(tf('settings.loyalty.maxRedeemPercent', "To'lashning maksimal ulushi (%)"), 'max_redeem_percent', { step: '1', max: '100', hint: tf('settings.loyalty.maxRedeemHint', "Chekning ko'pi bilan shuncha foizini keshbek/ball bilan to'lash mumkin") })}
        {numField(tf('settings.loyalty.defaultCashback', "Yangi mijoz keshbeki (%)"), 'default_cashback_percent', { step: '0.1', max: '100' })}
        {numField(tf('settings.loyalty.tierBronze', 'Bronza daraja (ball)'), 'tier_bronze')}
        {numField(tf('settings.loyalty.tierSilver', 'Kumush daraja (ball)'), 'tier_silver')}
        {numField(tf('settings.loyalty.tierGold', 'Oltin daraja (ball)'), 'tier_gold')}
      </div>

      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-700">{tf('settings.loyalty.accrueOnUnpaid', "To'lanmagan (nasiya) qismga ham keshbek")}</p>
          <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{tf('settings.loyalty.accrueOnUnpaidDesc', "O'chirilsa keshbek va ball faqat to'langan qismga hisoblanadi")}</p>
        </div>
        {toggle(!!form.accrue_on_unpaid, () => set('accrue_on_unpaid', !form.accrue_on_unpaid))}
      </div>

      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-700">{tf('settings.loyalty.returnReverses', "Qaytarishda keshbek/ball ham qaytariladi")}</p>
          <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{tf('settings.loyalty.returnReversesDesc', "POS Vazvrat va qisman qaytarishda mijozning keshbek, ball va jami xaridi kamayadi")}</p>
        </div>
        {toggle(!!form.return_reverses_loyalty, () => set('return_reverses_loyalty', !form.return_reverses_loyalty))}
      </div>

      <button
        type="button"
        onClick={save}
        disabled={saving}
        className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl disabled:opacity-60"
      >
        {saving ? '...' : tf('settings.loyalty.save', 'Saqlash')}
      </button>

      <div className="mt-6 pt-5 border-t border-slate-100">
        <p className="text-xs font-semibold text-slate-700">{tf('settings.loyalty.creditScope', "Kredit limit kimga qo'llanadi")}</p>
        <p className="text-[11px] text-slate-400 mt-0.5 mb-2 leading-snug">{tf('settings.loyalty.creditScopeDesc', "Qarz limitdan oshsa sotuv (yakunlash va tahrir ham) bloklanadi. Limit 0 bo'lsa cheklov yo'q.")}</p>
        <select
          value={scope}
          disabled={savingScope}
          onChange={e => saveScope(e.target.value)}
          className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="distributor">{tf('settings.loyalty.creditScopeDistributor', 'Faqat distribyutorlar')}</option>
          <option value="all">{tf('settings.loyalty.creditScopeAll', 'Barcha mijozlar')}</option>
        </select>
      </div>

      {branches.length > 0 && (
        <div className="mt-6 pt-5 border-t border-slate-100">
          <p className="text-xs font-semibold text-slate-700 mb-2">{tf('settings.loyalty.branchRules', 'Filial qoidalari')}</p>
          <div className="space-y-2">
            {branches.map(b => (
              <div key={b.branch_id} className="flex items-center gap-3 flex-wrap">
                <span className="flex-1 min-w-[120px] text-sm text-slate-700 truncate">{b.branch_name}</span>
                <label className="flex items-center gap-2 text-[11px] text-slate-500">
                  {tf('settings.loyalty.branchEnabled', 'Dasturda')}
                  {toggle(!!b.is_enabled, () => updateBranch(b.branch_id, { is_enabled: !b.is_enabled }))}
                </label>
                <input
                  type="number" min="0" max="100" step="0.1"
                  value={b.cashback_percent_override ?? ''}
                  onChange={e => updateBranch(b.branch_id, { cashback_percent_override: e.target.value })}
                  placeholder={tf('settings.loyalty.branchCashback', 'Keshbek %')}
                  title={tf('settings.loyalty.branchCashbackHint', "Bo'sh — mijozning shaxsiy foizi ishlatiladi")}
                  className="w-24 px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="button"
                  disabled={savingBranch === b.branch_id}
                  onClick={() => saveBranch(b)}
                  className="px-3 py-1.5 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg disabled:opacity-60"
                >
                  {tf('settings.loyalty.save', 'Saqlash')}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Umumiy (kompaniya darajasidagi POS) sozlamalar ───────────────────────────
function GeneralTab({ companyId }) {
  const { t } = useLang();
  const [posAllowNegative, setPosAllowNegative] = useState(true);
  const [savingSetting, setSavingSetting] = useState(false);
  const [deliveryFee, setDeliveryFee] = useState('');
  const [savingFee, setSavingFee] = useState(false);
  const [autoSale, setAutoSale] = useState(false);
  const [savingAutoSale, setSavingAutoSale] = useState(false);
  // T0.36: Mir-maza buyurtmalari uchun asosiy filial (faqat marketplace_agents yoqilgan korxonada)
  const features = useCompanyFeatures();
  const mpEnabled = !!features?.marketplace_agents;
  const { branches: mpBranchesAll } = useBranches();
  const mpBranches = mpBranchesAll.filter(b => b.is_active !== false);
  const [mpBranchId, setMpBranchId] = useState('');
  const [savingMpBranch, setSavingMpBranch] = useState(false);
  // i18n kaliti hali qo'shilmagan bo'lsa (t() kalitni qaytaradi) — o'zbekcha zaxira matn
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const [stockDeductStage, setStockDeductStage] = useState('order_confirmed');
  const [savingStage, setSavingStage] = useState(false);
  const [agentGeoCheck, setAgentGeoCheck] = useState(true);
  const [savingGeoCheck, setSavingGeoCheck] = useState(false);
  const [deliveryRadius, setDeliveryRadius] = useState('250');
  const [savingRadius, setSavingRadius] = useState(false);

  useEffect(() => {
    api.get('/companies').then(r => {
      if (r.data?.length > 0) {
        setPosAllowNegative(r.data[0].pos_allow_negative_stock !== false);
        setDeliveryFee(String(r.data[0].delivery_fee ?? 0));
        setAutoSale(r.data[0].orders_auto_create_sale === true);
        setMpBranchId(r.data[0].marketplace_default_branch_id ? String(r.data[0].marketplace_default_branch_id) : '');
        setStockDeductStage(r.data[0].stock_deduct_stage || 'order_confirmed');
        setAgentGeoCheck(r.data[0].agent_order_geo_radius_check !== false);
        setDeliveryRadius(String(r.data[0].default_delivery_radius_m ?? 250));
      }
    }).catch(e => toast.error(e.response?.data?.detail || e.message));
  }, []);

  const saveMpBranch = async (value) => {
    if (!companyId) return;
    const prev = mpBranchId;
    setMpBranchId(value);
    setSavingMpBranch(true);
    try {
      await api.put(`/companies/${companyId}`, { marketplace_default_branch_id: value ? Number(value) : null });
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      setMpBranchId(prev);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingMpBranch(false);
    }
  };

  const changeStockDeductStage = async (newStage) => {
    if (!companyId) return;
    setStockDeductStage(newStage);
    setSavingStage(true);
    try {
      await api.put(`/companies/${companyId}`, { stock_deduct_stage: newStage });
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingStage(false);
    }
  };

  const toggleAgentGeoCheck = async (checked) => {
    if (!companyId) return;
    setAgentGeoCheck(checked);
    setSavingGeoCheck(true);
    try {
      await api.put(`/companies/${companyId}`, { agent_order_geo_radius_check: checked });
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      setAgentGeoCheck(!checked);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingGeoCheck(false);
    }
  };

  const saveDeliveryRadius = async () => {
    if (!companyId) return;
    setSavingRadius(true);
    try {
      await api.put(`/companies/${companyId}`, { default_delivery_radius_m: Number(deliveryRadius) || 250 });
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingRadius(false);
    }
  };

  const toggleAutoSale = async (checked) => {
    if (!companyId) return;
    setAutoSale(checked);
    setSavingAutoSale(true);
    try {
      await api.put(`/companies/${companyId}`, { orders_auto_create_sale: checked });
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      setAutoSale(!checked);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingAutoSale(false);
    }
  };

  const saveDeliveryFee = async () => {
    if (!companyId) return;
    setSavingFee(true);
    try {
      await api.put(`/companies/${companyId}`, { delivery_fee: Number(deliveryFee) || 0 });
      toast.success(t('settings.general.deliveryFeeSaved'));
    } catch (e) {
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingFee(false);
    }
  };

  const togglePosNegative = async (checked) => {
    if (!companyId) return;
    setPosAllowNegative(checked);
    setSavingSetting(true);
    try {
      await api.put(`/companies/${companyId}`, { pos_allow_negative_stock: checked });
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      setPosAllowNegative(!checked);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSavingSetting(false);
    }
  };

  return (
    <div className="p-6 space-y-4">
      <ModulesCard companyId={companyId} />
      <LoyaltyCard companyId={companyId} />

      {/* Hippo ERP — Mahsulot qoldig'iga ta'sir qilish bosqichi */}
      <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-base">📦</span>
          <h3 className="text-sm font-bold text-slate-800">{t('settings.distribution.stockDeductTitle') || "Mahsulot qoldig‘iga ta’sir qilish bosqichi"}</h3>
        </div>
        <p className="text-[11px] text-slate-400 mb-4 leading-snug">
          {t('settings.distribution.stockDeductDesc') || "Sotuv va buyurtmalarda ombordagi mahsulot qoldig‘i aynan qaysi bosqichda kamayishini belgilang."}
        </p>
        <div className="space-y-2.5">
          {[
            {
              id: 'order_confirmed',
              title: t('settings.distribution.stageOrderConfirmed') || "1️⃣ Operatsiya tasdiqlanganida (Darhol)",
              desc: t('settings.distribution.stageOrderConfirmedDesc') || "Operatsiya yaratilishi yoki tasdiqlanishi bilanoq ombordan qoldiq kamayadi."
            },
            {
              id: 'loaded',
              title: t('settings.distribution.stageLoaded') || "2️⃣ Tovarlar yuklanganda / yo‘lga chiqqanda",
              desc: t('settings.distribution.stageLoadedDesc') || "Omborchi tovarni kuryer mashinasiga yuklaganda ombordan chiqadi."
            },
            {
              id: 'delivered',
              title: t('settings.distribution.stageDelivered') || "3️⃣ Yetkazib berilganida (Mijozga topshirilganda)",
              desc: t('settings.distribution.stageDeliveredDesc') || "Mahsulot mijozga yetib borgach, kuryer topshirgandagina ombordan chiqadi."
            }
          ].map(opt => (
            <label
              key={opt.id}
              onClick={() => changeStockDeductStage(opt.id)}
              className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                stockDeductStage === opt.id
                  ? 'border-blue-600 bg-blue-50/40 text-blue-900 shadow-sm'
                  : 'border-slate-200 hover:border-slate-300 bg-slate-50/50 text-slate-700'
              }`}
            >
              <input
                type="radio"
                name="stockDeductStage"
                checked={stockDeductStage === opt.id}
                onChange={() => changeStockDeductStage(opt.id)}
                disabled={savingStage}
                className="mt-0.5 text-blue-600 focus:ring-blue-500"
              />
              <div className="min-w-0">
                <div className="text-xs font-bold">{opt.title}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{opt.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Agent va Kuryer Geo-nazorati */}
      <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-base">📍</span>
          <h3 className="text-sm font-bold text-slate-800">{t('settings.distribution.geoControlTitle') || "Agent va Kuryer Geo-joylashuv nazorati"}</h3>
        </div>
        <div className="flex items-start justify-between gap-3 mb-4 pb-4 border-b border-slate-100">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-700">{t('settings.distribution.agentGeoCheck') || "Agent radius cheklovi (Do'kondan tashqarida zakaz olmaslik)"}</p>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
              {t('settings.distribution.agentGeoCheckDesc') || "Agent do'kon koordinatasidan uzoqda bo'lsa buyurtma berish bloklanadi."}
            </p>
          </div>
          <button
            type="button"
            disabled={savingGeoCheck}
            onClick={() => toggleAgentGeoCheck(!agentGeoCheck)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${agentGeoCheck ? 'bg-blue-600' : 'bg-slate-200'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${agentGeoCheck ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-slate-700 mb-1">{t('settings.distribution.courierRadius') || "Kuryer 'Topshirdim' radiusi (metr)"}</p>
            <p className="text-[11px] text-slate-400 mb-2 leading-snug">
              {t('settings.distribution.courierRadiusDesc') || "Kuryer do'kondan ko'pi bilan shu masofada bo'lganda topshirishni tasdiqlay oladi."}
            </p>
            <input
              type="number" min="50" max="2000"
              value={deliveryRadius}
              onChange={e => setDeliveryRadius(e.target.value)}
              className="w-full h-10 px-3 border border-slate-200 rounded-xl text-sm focus:border-blue-500 outline-none"
              placeholder="250"
            />
          </div>
          <button
            onClick={saveDeliveryRadius}
            disabled={savingRadius}
            className="h-10 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold rounded-xl transition-colors"
          >
            {savingRadius ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </div>

      <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-4">{t('settings.general.posSettings')}</h3>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-700">{t('settings.general.allowNegativeStock')}</p>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
              {t('settings.general.allowNegativeStockDesc')}
            </p>
          </div>
          <button
            type="button"
            disabled={savingSetting}
            onClick={() => togglePosNegative(!posAllowNegative)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${posAllowNegative ? 'bg-blue-600' : 'bg-slate-200'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${posAllowNegative ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>
      </div>

      <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-4">{t('settings.general.deliverySettings')}</h3>
        <div className="flex items-start justify-between gap-3 mb-5 pb-5 border-b border-slate-100">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-700">{t('settings.general.autoCreateSale')}</p>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
              {t('settings.general.autoCreateSaleDesc')}
            </p>
          </div>
          <button
            type="button"
            disabled={savingAutoSale}
            onClick={() => toggleAutoSale(!autoSale)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${autoSale ? 'bg-blue-600' : 'bg-slate-200'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${autoSale ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-slate-700 mb-1.5">{t('order.deliveryFee')} (so'm)</p>
            <p className="text-[11px] text-slate-400 mb-2 leading-snug">
              {t('settings.general.deliveryFeeDesc')}
            </p>
            <input
              type="number" min="0"
              value={deliveryFee}
              onChange={e => setDeliveryFee(e.target.value)}
              className="w-full h-10 px-3 border border-slate-200 rounded-xl text-sm focus:border-blue-500 outline-none"
              placeholder="0"
            />
          </div>
          <button
            onClick={saveDeliveryFee}
            disabled={savingFee}
            className="h-10 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold rounded-xl transition-colors"
          >
            {savingFee ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </div>

      {mpEnabled && (
        <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5">
          <h3 className="text-sm font-bold text-slate-800 mb-1">{tf('settings.general.mpDefaultBranch', 'Marketplace buyurtmalari uchun asosiy filial')}</h3>
          <p className="text-[11px] text-slate-400 mb-3 leading-snug">
            {tf('settings.general.mpDefaultBranchDesc', "Mir-maza buyurtmalari mijozda filial bo'lmasa shu filialga tushadi. Tanlanmasa — korxonaning birinchi faol filiali.")}
          </p>
          <select
            value={mpBranchId}
            disabled={savingMpBranch}
            onChange={e => saveMpBranch(e.target.value)}
            className="w-full h-10 px-3 border border-slate-200 rounded-xl text-sm focus:border-blue-500 outline-none bg-white disabled:opacity-60"
          >
            <option value="">{tf('settings.general.mpDefaultBranchNone', 'Tanlanmagan (birinchi faol filial)')}</option>
            {mpBranches.map(b => (
              <option key={b.id} value={String(b.id)}>{b.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}

import Filiallar from './Filiallar';
import { getSettingsMenus } from '../../constants/settingsMenus';

// ── Main Settings Component ──────────────────────────────────────────────────
// ── Smenalar tab (T1.11) ──────────────────────────────────────────────────────
function ShiftsTab({ companyId }) {
  const { t } = useLang();
  // i18n kaliti hali qo'shilmagan bo'lsa (t() kalitni qaytaradi) — o'zbekcha zaxira matn
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const [requireShift, setRequireShift] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/companies').then(r => {
      if (r.data?.length > 0) setRequireShift(r.data[0].pos_require_shift === true);
    }).catch(e => toast.error(e.response?.data?.detail || e.message));
  }, []);

  const toggle = async (checked) => {
    if (!companyId) return;
    setRequireShift(checked);
    setSaving(true);
    try {
      await api.put(`/companies/${companyId}`, { pos_require_shift: checked });
      refreshCompanyFeatures();
      toast.success(t('settings.general.settingSaved'));
    } catch (e) {
      setRequireShift(!checked);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 space-y-4">
      <div className="max-w-xl bg-white border border-slate-200 rounded-2xl p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-4">{t('settings.tab.shifts')}</h3>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-700">{tf('shift.requireShiftSetting', 'Savdo uchun smena majburiy')}</p>
            <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
              {tf('shift.requireShiftSettingDesc', "Yoqilsa, ochiq smenasiz sotuv server tomonida ham rad etiladi (POS-desktop va API uchun). Veb-POS hozirgidek doim smena talab qiladi.")}
            </p>
          </div>
          <button
            type="button"
            disabled={saving || !companyId}
            onClick={() => toggle(!requireShift)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60 ${requireShift ? 'bg-blue-600' : 'bg-slate-200'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${requireShift ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Settings() {
  const { t } = useLang();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
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
          {/* T3.1: telefonda tablar sidebar flyout'siz ham ochiladi (flyout faqat hover bilan ishlaydi) */}
          <div className="md:hidden mb-4">
            <select
              value={tab}
              aria-label={t('settings.title')}
              onChange={e => {
                const m = MENUS.find(x => x.id === e.target.value);
                if (m?.path) navigate(m.path);
                else setSearchParams({ tab: e.target.value });
              }}
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              {MENUS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </div>
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-2xl font-bold text-slate-800">{MENUS.find(m => m.id === tab)?.label || t('settings.title')}</h1>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 min-h-[500px]">
            {tab === 'users' && <UsersTab />}
            {tab === 'promotions' && <div className="h-full bg-white"><Promotions /></div>}
            {tab === 'warehouse' && <div className="h-full bg-white"><Warehouse /></div>}
            {tab === 'roles' && <RolesTab />}
            {tab === 'branches' && <div className="p-4 md:p-6"><Filiallar embedded /></div>}
            {tab === 'currencies' && <CurrenciesTab />}
            {tab === 'api' && <ApiKeysTab />}
            {tab === 'receipt' && <ReceiptTab />}
            {tab === 'tgbot' && <TelegramBotTab companyId={companyId} />}
            {tab === 'password' && <PasswordTab />}
            {tab === 'fiskal' && (
              <>
                <FiskalTab />
                <div className="mt-6 pt-4 border-t border-slate-100"><PaymentTerminalsSection /></div>
              </>
            )}
            {tab === 'payment_terminals' && <div className="p-4"><PaymentTerminalsSection /></div>}
            
            {/* Placeholders for unfinished tabs */}
            {tab === 'tariffs' && <PlaceholderTab name={t('settings.tab.organization')} />}
            {tab === 'internet_store' && <PlaceholderTab name={t('settings.tab.onlineStore')} />}
            {tab === 'integrations' && <PlaceholderTab name={t('settings.tab.integrations')} />}
            {tab === 'references' && <PlaceholderTab name={t('settings.tab.references')} />}
            {tab === 'general' && <GeneralTab companyId={companyId} />}
            {tab === 'org_structure' && <PlaceholderTab name={t('settings.tab.orgStructure')} />}
            {tab === 'auto_reply' && <PlaceholderTab name={t('settings.tab.autoReply')} />}
            {tab === 'auto_distribute' && <PlaceholderTab name={t('settings.tab.autoDistribute')} />}
            {tab === 'forms' && <PlaceholderTab name={t('settings.tab.forms')} />}
            {tab === 'shifts' && <ShiftsTab companyId={companyId} />}
            {tab === 'warehouses' && <PlaceholderTab name={t('settings.tab.warehouseSections')} />}
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




