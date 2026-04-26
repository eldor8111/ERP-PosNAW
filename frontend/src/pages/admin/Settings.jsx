import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

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
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('settings.currencyCode')}</label>
            <input
              required value={form.code} maxLength={5}
              onChange={e => setForm({ ...form, code: e.target.value })}
              placeholder="USD"
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 uppercase"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">{t('common.currency')} ({t('common.sum')}ga)</label>
            <input
              required type="number" min="0.0001" step="any" value={form.rate}
              onChange={e => setForm({ ...form, rate: e.target.value })}
              placeholder="12800"
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex flex-col justify-end gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
              <input
                type="checkbox" checked={form.is_default}
                onChange={e => setForm({ ...form, is_default: e.target.checked })}
                className="w-4 h-4 accent-indigo-600"
              />
              {t('settings.primaryCurrency')}
            </label>
            <button
              type="submit" disabled={saving}
              className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
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
                      <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-[10px] font-semibold rounded">{t('settings.permanent')}</span>
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
                        className="w-28 px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-semibold"
                      />
                      <button
                        onClick={() => handleUpdateRate(c)}
                        disabled={updatingId === c.id}
                        className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-xs font-semibold rounded-lg transition-colors whitespace-nowrap"
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
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                      c.is_active ? 'bg-indigo-500' : 'bg-slate-200'
                    } ${c.is_default ? 'cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                      c.is_active ? 'translate-x-[18px]' : 'translate-x-0.5'
                    }`} />
                  </button>
                </td>

                {/* Doimiy valyuta — Asosiy qilish */}
                <td className="px-4 py-3.5">
                  {c.is_default ? (
                    <input type="checkbox" readOnly checked className="w-4 h-4 accent-indigo-600 cursor-default" />
                  ) : (
                    <button
                      onClick={() => handleMakeDefault(c)}
                      disabled={makingDefaultId === c.id}
                      className="px-3 py-1.5 bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-500 text-xs font-semibold rounded-lg border border-slate-200 hover:border-indigo-300 transition-all disabled:opacity-50 whitespace-nowrap"
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
                  className={`px-3 py-2 text-xs font-semibold rounded-lg transition-colors shrink-0 ${
                    copied ? 'bg-emerald-500 text-white' : 'bg-amber-200 hover:bg-amber-300 text-amber-800'
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
            className="flex-1 px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            type="submit" disabled={saving}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors flex items-center gap-2"
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
  const [form, setForm]   = useState({ new_password: '', confirm: '' });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg]     = useState('');
  const [err, setErr]     = useState('');
  const [show, setShow]   = useState({ new: false, confirm: false });

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

  const inputCls = 'w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';

  return (
    <div className="max-w-md space-y-6">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 space-y-5">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                {[1,2,3,4].map(i => (
                  <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${
                    form.new_password.length >= i * 3
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
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
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
function TelegramBotTab() {
  const { t } = useLang();
  const [token, setToken] = useState('');
  const [savedToken, setSavedToken] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [companyId, setCompanyId] = useState(null);

  const load = () => {
    api.get('/companies').then(r => {
      if (r.data && r.data.length > 0) {
        setSavedToken(r.data[0].tg_bot_token || null);
        setCompanyId(r.data[0].id);
      }
    }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  };

  useEffect(() => {
    load();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!companyId) return;
    setSaving(true); setErr(''); setMsg('');
    try {
      await api.put(`/companies/${companyId}`, { tg_bot_token: token });
      setMsg("Telegram bot tokeni muvaffaqiyatli saqlandi.");
      setSavedToken(token);
      setToken('');
      setTimeout(() => setMsg(''), 3000);
    } catch (error) {
      setErr(error.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Tasdiqlaysizmi? Barcha xabarlar tohtatiladi.")) return;
    setSaving(true); setErr(''); setMsg('');
    try {
      await api.put(`/companies/${companyId}`, { tg_bot_token: null });
      setSavedToken(null);
      setToken('');
      setMsg("Bot uzib qo'yildi.");
      setTimeout(() => setMsg(''), 3000);
    } catch (e) {
      setErr(e.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      {savedToken && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-full flex justify-center items-center text-xl shadow-inner">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a5.962 5.962 0 0 0-.056 0zm4.962 7.224c...l-5.694 3.447c...z"/></svg>
            </div>
            <div>
              <h3 className="font-bold text-emerald-800 text-lg">Bot ulangan va faol!</h3>
              <p className="text-sm font-mono text-emerald-600 mt-1 bg-emerald-100 px-2 py-0.5 rounded w-fit">
                {savedToken.slice(0, 8)}...{savedToken.slice(-6)}
              </p>
            </div>
          </div>
          <button 
            onClick={handleDelete} disabled={saving}
            className="px-4 py-2 bg-white border-2 border-red-200 text-red-600 hover:bg-red-50 font-bold text-sm rounded-xl transition-colors min-w-[120px]"
          >
            {saving ? '...' : "Uzib qo'yish"}
          </button>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 space-y-5">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">
            <svg className="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 24 24"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a5.962 5.962 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.699 1.201-1.22 1.28-.106.016-.215.023-.324.023-.329 0-.655-.078-.962-.23-.09-.045-2.072-1.373-2.91-2.133-.255-.23-.55-.664-.047-1.12.13-.12 2.4-2.2 4.414-4.043.203-.186.417-.384.417-.61 0-.306-.275-.417-.463-.384l-.536.09-5.694 3.447c-.382.235-.905.39-1.424.39-.17 0-.339-.022-.505-.065L4.053 12.55c-.71-.225-.71-.708.15-1.047 2.768-1.196 9.2-3.953 11.233-4.279.172-.027.35-.042.508-.042z"/></svg>
          </div>
          <div>
            <h3 className="font-bold text-slate-800">{savedToken ? 'Boshqa bot ulash (Yangilash)' : 'Mijozlar uchun Telegram Bot'}</h3>
            <p className="text-xs text-slate-400">Bot tokenini ulab qarz va keshbek bildirishnomalarini ishga tushiring</p>
          </div>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Yangi Bot Token</label>
            <input 
              value={token} required
              onChange={e => setToken(e.target.value)}
              placeholder="123456789:ABCDefghIJKlmnOPQRstUV... (BotFather-dan)"
              className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
            />
          </div>

          {err && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl">{err}</div>}
          {msg && <div className="px-4 py-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl">{msg}</div>}

          <button type="submit" disabled={saving || !companyId || !token.trim()}
            className="w-full py-2.5 bg-blue-500 hover:bg-blue-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
            {saving ? "Saqlanmoqda..." : "Saqlash va Ulash"}
          </button>
        </form>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
        <h4 className="text-sm font-bold text-slate-700 mb-2">Bu qanday ishlaydi?</h4>
        <ul className="space-y-2 text-xs text-slate-500">
          <li>1. Telegramda <b>@BotFather</b> orqali yangi bot yarating.</li>
          <li>2. Olingan tokenni yuqoriga kiriting va Saqlang.</li>
          <li>3. Qarzga savdo bo'lganda muddat oxirigacha Bot o'zi xabar berib turadi!</li>
          <li><b>Muhim:</b> Mijoz xabar olishi uchun botingizga kirib <b>/start</b> bosishi va o'zining <b>Telefon raqamini</b> (Raqamni yuborish tugmasi orqali) jo'natishi kerak. Tizim raqam bo'yicha mijozni avtomat taniydi.</li>
        </ul>
      </div>
    </div>
  );
}

// ── Receipt settings helpers ───────────────────────────────────────────────────
const RECEIPT_KEY = 'erp_receipt_settings';

const defaultReceiptCfg = {
  company: '', address: '', phone: '', inn: '',
  header: '', footer: "Xaridingiz uchun rahmat!",
  show_barcode: true, show_qr: false, show_cashier: true,
  show_date: true, show_discount: true, show_debt: true,
  show_payment_type: true, show_note: true, show_unit: true,
  copies: '1',
  logo: '', logo_size: 40,
};
const defaultNakladnoyCfg = {
  company: '', address: '', phone: '', inn: '',
  bank: '', account: '', mfo: '',
  director: '', accountant: '', storekeeper: '',
  footer_note: '',
  logo: '', logo_size: 50, logo_position: 'center',
};


// ── Receipt preview ────────────────────────────────────────────────────────────
function ReceiptPreview({ cfg, mm }) {
  const { t } = useLang();
  const narrow = mm === 58;
  return (
    <div className={`${narrow ? 'w-48' : 'w-64'} bg-white border border-slate-300 shadow-xl rounded-sm mx-auto font-mono leading-snug text-slate-800`}
      style={{ fontSize: narrow ? '8px' : '9px' }}>
      {/* Header */}
      <div className="px-3 pt-3 pb-1 text-center space-y-0.5 border-b border-dashed border-slate-300">
        {cfg.logo && <img src={cfg.logo} alt="logo" style={{ height: `${Math.round((cfg.logo_size||40) * 0.55)}px`, maxWidth: '100%', objectFit: 'contain', margin: '0 auto 3px' }} />}
        {cfg.company && <div className="font-bold" style={{ fontSize: narrow ? '10px' : '11px' }}>{cfg.company}</div>}
        {cfg.address && <div className="text-slate-500">{cfg.address}</div>}
        {cfg.phone && <div className="text-slate-500">Tel: {cfg.phone}</div>}
        {cfg.inn && <div className="text-slate-400">STIR: {cfg.inn}</div>}
        {cfg.header && <div className="italic text-slate-600 mt-1">{cfg.header}</div>}
      </div>
      {/* Meta */}
      <div className="px-3 py-1 flex justify-between text-slate-500 border-b border-dashed border-slate-300">
        <span>Chek #00001</span>
        {cfg.show_date && <span>17.03.2025</span>}
      </div>
      {/* Items */}
      <div className="px-3 py-1.5 space-y-1 border-b border-dashed border-slate-300">
        <div>
          <div className="flex justify-between"><span>Mahsulot A</span><span>50,000</span></div>
          <div className="text-slate-400 pl-2">2 x 25,000</div>
        </div>
        <div>
          <div className="flex justify-between"><span>Mahsulot B</span><span>30,000</span></div>
          <div className="text-slate-400 pl-2">1 x 30,000</div>
        </div>
      </div>
      {/* Totals */}
      <div className="px-3 py-1.5 space-y-0.5 border-b border-dashed border-slate-300">
        <div className="flex justify-between font-bold"><span>JAMI:</span><span>80,000 so'm</span></div>
        <div className="flex justify-between text-slate-500"><span>Naqd:</span><span>100,000</span></div>
        <div className="flex justify-between text-slate-500"><span>Qaytim:</span><span>20,000</span></div>
        {cfg.show_cashier && <div className="text-slate-400 mt-1">Kassir: Sardor</div>}
      </div>
      {/* Barcode */}
      {cfg.show_barcode && (
        <div className="px-3 py-1.5 text-center border-b border-dashed border-slate-300">
          <div className="inline-flex gap-px items-end">
            {Array.from({length: 28}).map((_, i) => (
              <div key={i} style={{ width: '2px', height: `${8 + (i % 3 === 0 ? 4 : i % 2 === 0 ? 2 : 0)}px`, background: '#334155' }} />
            ))}
          </div>
          <div className="text-[7px] text-slate-500 mt-0.5">0000-0001-17032025</div>
        </div>
      )}
      {/* QR */}
      {cfg.show_qr && (
        <div className="px-3 py-1.5 text-center border-b border-dashed border-slate-300">
          <div className="w-12 h-12 bg-slate-100 border border-slate-200 mx-auto grid" style={{ gridTemplateColumns: 'repeat(5,1fr)', gap: '1px', padding: '3px' }}>
            {Array.from({length:25}).map((_,i) => <div key={i} className={i % 3 === 0 ? 'bg-slate-800' : 'bg-white'} />)}
          </div>
        </div>
      )}
      {/* Footer */}
      {cfg.footer && <div className="px-3 py-2 text-center italic text-slate-500">{cfg.footer}</div>}
    </div>
  );
}

// ── Nakladnoy preview ─────────────────────────────────────────────────────────
function NakladnoyPreview({ cfg }) {
  const { t } = useLang();
  const logoPos = cfg.logo_position || 'center';
  return (
    <div className="bg-white border border-slate-300 shadow-lg rounded p-4 w-full max-w-sm mx-auto text-[8px] font-mono text-slate-700 leading-snug">
      {cfg.logo && (
        <div style={{ textAlign: logoPos, marginBottom: '6px' }}>
          <img src={cfg.logo} alt="logo" style={{ height: `${Math.round((cfg.logo_size||50) * 0.45)}px`, maxWidth: '90px', objectFit: 'contain', display: 'inline-block' }} />
        </div>
      )}
      <div className="text-center border-b border-slate-300 pb-2 mb-2">
        <div className="font-bold text-[10px]">{cfg.company || 'KORXONA NOMI'}</div>
        {cfg.inn && <div>STIR: {cfg.inn}</div>}
        {cfg.address && <div>{cfg.address}</div>}
        {cfg.phone && <div>Tel: {cfg.phone}</div>}
        {cfg.bank && <div>Bank: {cfg.bank}</div>}
        {cfg.account && <div>H/r: {cfg.account}</div>}
        {cfg.mfo && <div>MFO: {cfg.mfo}</div>}
      </div>
      <div className="text-center font-bold text-[10px] mb-2">NAKLADNOY № _____ / 17.03.2025</div>
      <table className="w-full border-collapse mb-2" style={{ borderSpacing: 0 }}>
        <thead>
          <tr>
            {['№','Nomi','Soni','Narxi','Jami'].map(h => (
              <th key={h} className="border border-slate-400 px-1 py-0.5 text-center bg-slate-100">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[['1','Mahsulot A','2','25,000','50,000'],['2','Mahsulot B','1','30,000','30,000']].map((row,i) => (
            <tr key={i}>{row.map((c,j) => <td key={j} className="border border-slate-300 px-1 py-0.5 text-center">{c}</td>)}</tr>
          ))}
          <tr>
            <td colSpan={4} className="border border-slate-300 px-1 py-0.5 text-right font-bold">JAMI:</td>
            <td className="border border-slate-300 px-1 py-0.5 text-center font-bold">80,000</td>
          </tr>
        </tbody>
      </table>
      <div className="flex justify-between mt-3 pt-2 border-t border-slate-300">
        <div>{cfg.director ? `Direktor: ${cfg.director}` : 'Direktor: __________'}</div>
        <div>{cfg.accountant ? `Buxgalter: ${cfg.accountant}` : 'Buxgalter: __________'}</div>
      </div>
      {cfg.storekeeper && <div className="mt-1">Omborchi: {cfg.storekeeper}</div>}
      {cfg.footer_note && <div className="mt-2 italic text-slate-500 text-center">{cfg.footer_note}</div>}
    </div>
  );
}

// ── Receipt field style (module-level so components don't recreate it) ─────────
const RIC = 'w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white';

const SUB_TABS = [
  { id: '58',  label: 'Chek 58mm',      icon: '🧾' },
  { id: '80',  label: 'Chek 80mm',      icon: '🧾' },
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
            <span className="inline-flex items-center gap-1.5 px-3 py-2 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700 text-xs font-semibold rounded-lg transition-colors">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
              Rasm yuklash
            </span>
          </label>
          {logo && (
            <button onClick={onRemove} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 border border-red-200 rounded-lg transition-colors">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
              Logoni olib tashlash
            </button>
          )}
          {/* Size slider */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-500 whitespace-nowrap">Hajmi:</span>
            <input type="range" min={16} max={100} step={4}
              value={size || 40}
              onChange={e => onSizeChange(Number(e.target.value))}
              className="flex-1 h-1.5 accent-indigo-500 cursor-pointer"
            />
            <span className="text-[11px] font-mono text-slate-600 w-8 text-right">{size || 40}px</span>
          </div>
          {positionPicker && (
            <div>
              <p className="text-[11px] text-slate-500 mb-1">Logo holati:</p>
              <div className="flex gap-1">
                {[['left','◀ Chap'],['center','▪ Markaz'],['right',"O'ng ▶"]].map(([v, l]) => (
                  <button key={v} onClick={() => onPositionChange(v)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg border transition-all ${
                      position === v ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-200 text-slate-600 hover:border-indigo-300'
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
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-3">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">Chekda ko'rsatiladigan maydonlar</p>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2.5">
          {[
            ['show_date',         'Sana va vaqt'],
            ['show_cashier',      "Kassir ismi"],
            ['show_unit',         "O'lchov birligi"],
            ['show_discount',     'Chegirma'],
            ['show_payment_type', "To'lov turi"],
            ['show_debt',         'Qarzdorlik'],
            ['show_note',         'Izoh'],
            ['show_barcode',      'Barkod'],
            ['show_qr',           'QR kod'],
          ].map(([key, label]) => (
            <label key={key} className="flex items-center gap-2.5 cursor-pointer select-none">
              <div onClick={() => upd(key, !cfg[key])}
                className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${cfg[key] ? 'bg-indigo-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${cfg[key] ? 'translate-x-4' : ''}`} />
              </div>
              <span className="text-sm text-slate-700">{label}</span>
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 pt-1 border-t border-slate-200">
          <span className="text-xs font-semibold text-slate-500">Nusxalar soni:</span>
          <select value={cfg.copies} onChange={e => upd('copies', e.target.value)}
            className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
            {['1','2','3'].map(n => <option key={n} value={n}>{n} ta</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}

function NakladnoyFields({ cfg, upd }) {
  const { t } = useLang();
  return (
    <div className="space-y-4">
      {/* Logo upload with position picker + size */}
      <LogoUpload
        logo={cfg.logo}
        size={cfg.logo_size || 50}
        onUpload={(v) => upd('logo', v)}
        onRemove={() => upd('logo', '')}
        onSizeChange={(v) => upd('logo_size', v)}
        positionPicker={true}
        position={cfg.logo_position || 'center'}
        onPositionChange={(v) => upd('logo_position', v)}
      />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">Korxona nomi *</label>
          <input value={cfg.company} onChange={e => upd('company', e.target.value)} placeholder="MCHJ / YaTT nomi" className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">STIR / INN</label>
          <input value={cfg.inn} onChange={e => upd('inn', e.target.value)} placeholder="123456789" className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.address') || 'Manzil'}</label>
          <input value={cfg.address} onChange={e => upd('address', e.target.value)} className={RIC} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-500 mb-1">{t('admin.dict.phone') || 'Telefon'}</label>
          <input value={cfg.phone} onChange={e => upd('phone', e.target.value)} className={RIC} />
        </div>
      </div>
      <div className="border-t border-slate-100 pt-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Bank rekvizitlari</p>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Bank nomi</label>
            <input value={cfg.bank} onChange={e => upd('bank', e.target.value)} placeholder="NBU, Kapitalbank..." className={RIC} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Hisob raqam</label>
            <input value={cfg.account} onChange={e => upd('account', e.target.value)} placeholder="2020..." className={RIC} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">MFO</label>
            <input value={cfg.mfo} onChange={e => upd('mfo', e.target.value)} placeholder="01001" className={RIC} />
          </div>
        </div>
      </div>
      <div className="border-t border-slate-100 pt-4">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Imzo egallari</p>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Direktor</label>
            <input value={cfg.director} onChange={e => upd('director', e.target.value)} placeholder="F.I.Sh." className={RIC} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Bosh buxgalter</label>
            <input value={cfg.accountant} onChange={e => upd('accountant', e.target.value)} placeholder="F.I.Sh." className={RIC} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">Omborchi</label>
            <input value={cfg.storekeeper} onChange={e => upd('storekeeper', e.target.value)} placeholder="F.I.Sh." className={RIC} />
          </div>
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1">Izoh (ixtiyoriy)</label>
        <input value={cfg.footer_note} onChange={e => upd('footer_note', e.target.value)} placeholder="Qo'shimcha eslatma..." className={RIC} />
      </div>
    </div>
  );
}

// ── Receipt / Nakladnoy settings tab ──────────────────────────────────────────
function ReceiptTab() {
  const { t } = useLang();
  const [loading, setLoading] = useState(true);
  const [sub, setSub]       = useState('58');
  const [cfg58, setCfg58]   = useState({ ...defaultReceiptCfg });
  const [cfg80, setCfg80]   = useState({ ...defaultReceiptCfg, show_qr: true });
  const [cfgNak, setCfgNak] = useState({ ...defaultNakladnoyCfg });
  const [saved, setSaved]   = useState(false);

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
          localStorage.setItem(RECEIPT_KEY, JSON.stringify(stored));
        }
      })
      .catch(e => console.error('Receipt templates load error:', e))
      .finally(() => setLoading(false));
  }, []);

  const upd58  = (k, v) => setCfg58(p => ({ ...p, [k]: v }));
  const upd80  = (k, v) => setCfg80(p => ({ ...p, [k]: v }));
  const updNak = (k, v) => setCfgNak(p => ({ ...p, [k]: v }));

  const handleSave = () => {
    api.put('/companies/me/receipt_templates', {
      receipt_templates: { r58: cfg58, r80: cfg80, nak: cfgNak }
    }).then(() => {
      // localStorage ni yangilash (barcha print funksiyalar shu yerdan o'qiydi)
      localStorage.setItem(RECEIPT_KEY, JSON.stringify({ r58: cfg58, r80: cfg80, nak: cfgNak }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    }).catch(e => alert(e.response?.data?.detail || "Saqlashda xatolik yuz berdi"));
  };

  const currentCfg = sub === '58' ? cfg58 : sub === '80' ? cfg80 : cfgNak;
  const updFn      = sub === '58' ? upd58  : sub === '80' ? upd80  : updNak;

  if (loading) return <div className="text-sm text-slate-500 animate-pulse py-10 px-4">Shablonlar serverdan yuklanmoqda...</div>;

  return (
    <div className="space-y-4">
      {/* Sub-tab bar */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {SUB_TABS.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg transition-all ${sub === t.id ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
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
          className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm rounded-xl transition-colors flex items-center gap-2">
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

  const inputCls = 'w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500';

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
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors">
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
                      className="px-2 py-1.5 border border-indigo-300 rounded-lg text-sm w-40" />
                  ) : (
                    <span className="text-sm font-semibold text-slate-800">{b.name}</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  {editId === b.id ? (
                    <input value={editForm.address ?? (b.address || '')} onChange={e => setEditForm(f => ({ ...f, address: e.target.value }))}
                      className="px-2 py-1.5 border border-indigo-300 rounded-lg text-sm w-36" />
                  ) : (
                    <span className="text-sm text-slate-500">{b.address || '—'}</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  {editId === b.id ? (
                    <input value={editForm.phone ?? (b.phone || '')} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))}
                      className="px-2 py-1.5 border border-indigo-300 rounded-lg text-sm w-32" />
                  ) : (
                    <span className="text-sm text-slate-500">{b.phone || '—'}</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                    b.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
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
                          className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="Tahrirlash">
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

// ── Main Settings page ────────────────────────────────────────────────────────
export default function Settings() {
  const { t } = useLang();
  const [tab, setTab] = useState('valyuta');

  const TABS = [
    { id:'filiyal', label:t('settings.tab.branches'), icon:<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg> },
    { id:'valyuta', label:t('settings.tab.currencies'), icon:<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
    { id:'api',     label:t('settings.tab.api'), icon:<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg> },
    { id:'chek',    label:t('settings.tab.receipt'), icon:<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg> },
    { id:'tgbot',   label:t('settings.tab.telegram'),  icon:<svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a5.962 5.962 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.699 1.201-1.22 1.28-.106.016-.215.023-.324.023-.329 0-.655-.078-.962-.23-.09-.045-2.072-1.373-2.91-2.133-.255-.23-.55-.664-.047-1.12.13-.12 2.4-2.2 4.414-4.043.203-.186.417-.384.417-.61 0-.306-.275-.417-.463-.384l-.536.09-5.694 3.447c-.382.235-.905.39-1.424.39-.17 0-.339-.022-.505-.065L4.053 12.55c-.71-.225-.71-.708.15-1.047 2.768-1.196 9.2-3.953 11.233-4.279.172-.027.35-.042.508-.042z"/></svg> },
    { id:'parol',   label:t('settings.tab.password'), icon:<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg> },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t('settings.title')}</h1>
        <p className="text-slate-500 text-sm mt-0.5">{t('settings.subtitle')}</p>
      </div>

      <div className="flex gap-1 bg-white border border-slate-200 rounded-2xl p-1.5 w-fit shadow-sm">
        {TABS.map(tab_item => (
          <button key={tab_item.id} onClick={() => setTab(tab_item.id)}
            className={`flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-xl transition-all ${
              tab === tab_item.id ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}>
            {tab_item.icon}<span>{tab_item.label}</span>
          </button>
        ))}
      </div>

      {tab === 'filiyal' && <BranchesTab />}
      {tab === 'valyuta' && <CurrenciesTab />}
      {tab === 'api'     && <ApiKeysTab />}
      {tab === 'chek'    && <ReceiptTab />}
      {tab === 'tgbot'   && <TelegramBotTab />}
      {tab === 'parol'   && <PasswordTab />}
    </div>
  );
}
