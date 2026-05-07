import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

// super_admin ni dropdown dan yashiramiz — faqat DB orqali beriladi
const ROLES = ['admin', 'director', 'manager', 'accountant', 'warehouse', 'cashier'];

const getRoleLabels = (t) => ({
  super_admin: t('role.super_admin'),
  admin: t('role.admin'), director: t('role.director'), manager: t('role.manager'),
  accountant: t('role.accountant') || 'Buxgalter', warehouse: t('role.warehouseman'), cashier: t('role.cashier'),
});

const ROLE_COLORS = {
  super_admin: 'bg-purple-100 text-purple-700',
  admin: 'bg-red-100 text-red-700',
  director: 'bg-purple-100 text-purple-700',
  manager: 'bg-blue-100 text-blue-700',
  accountant: 'bg-emerald-100 text-emerald-700',
  warehouse: 'bg-amber-100 text-amber-700',
  cashier: 'bg-indigo-100 text-indigo-700',
};

const BLANK_FORM = { name: '', phone: '', email: '', password: '', role: 'cashier', branch_id: '' };

const inp = "w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500";

function StatCard({ label, value, color = 'slate' }) {
  const txt = {
    indigo: 'text-indigo-600', emerald: 'text-emerald-600',
    violet: 'text-violet-600', slate: 'text-slate-700',
  };
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${txt[color]}`}>{value}</div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1.5">{label}</label>
      {children}
    </div>
  );
}

function RoleSelect({ value, onChange, roles, roleLabels }) {
  return (
    <Field label="Rol">
      <select value={value} onChange={e => onChange(e.target.value)} className={inp}>
        {roles.map(r => <option key={r} value={r}>{roleLabels[r]}</option>)}
      </select>
    </Field>
  );
}

function BranchSelect({ value, onChange, branches }) {
  return (
    <Field label="Filial">
      <select value={value} onChange={e => onChange(e.target.value)} className={inp}>
        <option value="">— Filialsiz —</option>
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>
    </Field>
  );
}

// OTP bosqichlari: 'form' → 'otp_sent' → 'otp_verified'
export default function Users() {
  const { t } = useLang();
  const [users, setUsers] = useState([]);
  const [branches, setBranches] = useState([]);
  const [modal, setModal] = useState(null); // 'create' | 'edit' | 'password'
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(BLANK_FORM);
  const [newPwd, setNewPwd] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // OTP state
  const [otpStep, setOtpStep] = useState('form'); // 'form' | 'otp_sent' | 'verified'
  const [otpCode, setOtpCode] = useState('');
  const [otpLoading, setOtpLoading] = useState(false);
  const [otpVerifiedToken, setOtpVerifiedToken] = useState('');
  const [otpSession, setOtpSession] = useState('');  // JWT da saqlangan OTP sessiyasi
  const [devOtp, setDevOtp] = useState(''); // dev modeda konsoldan ko'rsatiladi
  const [isDevMode, setIsDevMode] = useState(false);

  const ROLE_LABELS = getRoleLabels(t);

  const load = useCallback(() => {
    api.get('/users/').then(r => setUsers(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  useEffect(() => {
    load();
    api.get('/branches').then(r => setBranches(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, [load]);

  const openCreate = () => {
    setForm(BLANK_FORM);
    setError('');
    setOtpStep('form');
    setOtpCode('');
    setOtpVerifiedToken('');
    setOtpSession('');
    setDevOtp('');
    setModal('create');
  };
  const openEdit = (u) => {
    setForm({ name: u.name, phone: u.phone, email: u.email || '', password: '', role: u.role, branch_id: u.branch_id ?? '' });
    setSelected(u); setError(''); setModal('edit');
  };
  const openPwd = (u) => { setSelected(u); setNewPwd(''); setError(''); setModal('password'); };
  const close = () => {
    setModal(null); setSelected(null); setError('');
    setOtpStep('form'); setOtpCode(''); setOtpVerifiedToken(''); setDevOtp('');
  };

  const setField = useCallback((key, val) => {
    setForm(prev => ({ ...prev, [key]: val }));
    // telefon o'zgarganda OTP holatini reset qilamiz
    if (key === 'phone') {
      setOtpStep('form');
      setOtpCode('');
      setOtpVerifiedToken('');
      setOtpSession('');
      setDevOtp('');
    }
  }, []);

  // 1-qadam: OTP yuborish
  const handleSendOtp = async () => {
    const phone = form.phone.trim();
    if (!phone) { setError('Telefon raqamini kiriting'); return; }
    setOtpLoading(true); setError('');
    try {
      const res = await api.post('/auth/send-otp', { phone, purpose: 'register' });
      if (res.data.sent) {
        setOtpStep('otp_sent');
        setIsDevMode(!!res.data.dev_mode);
        setOtpSession(res.data.otp_session || '');
        if (res.data.dev_mode) {
          // Dev modeda konsolga chiqarilgan OTP ni ko'rsatish uchun xabar
          setDevOtp('(Dev rejim: OTP serverning konsolini ko\'ring)');
        }
        toast.success('OTP Telegram orqali yuborildi');
      } else {
        setError(res.data.message || 'OTP yuborishda xato');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'OTP yuborishda xato');
    } finally {
      setOtpLoading(false);
    }
  };

  // 2-qadam: OTP tasdiqlash
  const handleVerifyOtp = async () => {
    if (!otpCode.trim()) { setError('OTP kodni kiriting'); return; }
    setOtpLoading(true); setError('');
    try {
      const res = await api.post('/auth/verify-otp', { phone: form.phone, otp: otpCode.trim(), otp_session: otpSession });
      if (res.data.verified) {
        setOtpVerifiedToken(res.data.verified_token);
        setOtpStep('verified');
        setError('');
        toast.success('Telefon tasdiqlandi ✓');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'OTP noto\'g\'ri');
    } finally {
      setOtpLoading(false);
    }
  };

  // 3-qadam: Foydalanuvchi yaratish
  const handleCreate = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email || null,
        password: form.password,
        role: form.role,
        branch_id: form.branch_id ? Number(form.branch_id) : null,
        otp_verified_token: otpVerifiedToken || null,
      };
      await api.post('/users/', payload);
      close(); load();
      toast.success('Foydalanuvchi muvaffaqiyatli qo\'shildi');
    } catch (err) {
      setError(err.response?.data?.detail || t('common.error'));
    } finally { setSaving(false); }
  };

  const handleEdit = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email || null,
        role: form.role,
        branch_id: form.branch_id ? Number(form.branch_id) : null,
      };
      await api.put(`/users/${selected.id}`, payload);
      close(); load();
    } catch (err) { setError(err.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  const handlePwd = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.patch(`/users/${selected.id}/password`, { new_password: newPwd });
      close();
    } catch (err) { setError(err.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  const handleDeactivate = async (u) => {
    if (!confirm(t('confirm.delete') || `"${u.name}" ni nofaol qilishni tasdiqlaysizmi?`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      load();
    } catch (err) { alert(err.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('user.title')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{t('user.subtitle') || 'Xodimlar va ularning rollari boshqaruvi'}</p>
        </div>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          {t('user.newUser')}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label={t('user.totalEmployees') || "Jami xodimlar"} value={users.length} color="indigo" />
        <StatCard label={t('user.cashiers') || "Kassirlar"} value={users.filter(u => u.role === 'cashier').length} color="emerald" />
        <StatCard label={t('user.managers') || "Menejerlar"} value={users.filter(u => u.role === 'manager').length} color="violet" />
        <StatCard label={t('user.admins') || "Adminlar"} value={users.filter(u => u.role === 'admin' || u.role === 'director').length} color="slate" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {[t('common.name') || 'Xodim', t('common.phone'), 'Email', t('branch.title') || 'Filial', t('user.role'), t('common.status'), ''].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-bold shrink-0">
                      {u.name?.[0]?.toUpperCase()}
                    </div>
                    <span className="text-sm font-semibold text-slate-800">{u.name}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{u.phone}</td>
                <td className="px-6 py-4 text-sm text-slate-500">{u.email || '—'}</td>
                <td className="px-6 py-4 text-sm text-slate-500">
                  {u.branch_id ? (branches.find(b => b.id === u.branch_id)?.name || '—') : '—'}
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${ROLE_COLORS[u.role] || 'bg-slate-100 text-slate-600'}`}>
                    {ROLE_LABELS[u.role] || u.role}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {u.status === 'active' ? t('common.active') : t('common.inactive')}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-1 justify-end">
                    <button onClick={() => openEdit(u)} title={t('common.edit')} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button onClick={() => openPwd(u)} title={t('user.changePassword')} className="p-1.5 text-amber-500 hover:bg-amber-50 rounded-lg transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                      </svg>
                    </button>
                    <button onClick={() => handleDeactivate(u)} title={t('common.delete')} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={7} className="px-6 py-16 text-center text-slate-400 text-sm">{t('user.noUsers')}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── CREATE MODAL ─────────────────────────────────────── */}
      {modal === 'create' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('user.newUser')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">

              {/* Ism */}
              <Field label={`${t('common.name')} *`}>
                <input
                  type="text" required value={form.name}
                  onChange={e => setField('name', e.target.value)}
                  placeholder={t('common.name')} className={inp}
                  autoFocus
                />
              </Field>

              {/* Telefon + OTP yuborish tugmasi */}
              <Field label={`${t('common.phone')} *`}>
                <div className="flex gap-2">
                  <input
                    type="text" required value={form.phone}
                    onChange={e => setField('phone', e.target.value)}
                    placeholder="+998901234567" className={inp}
                    disabled={otpStep === 'verified'}
                  />
                  {otpStep === 'form' && (
                    <button
                      type="button"
                      onClick={handleSendOtp}
                      disabled={otpLoading || !form.phone}
                      className="shrink-0 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl transition-colors whitespace-nowrap"
                    >
                      {otpLoading ? '...' : 'OTP yuborish'}
                    </button>
                  )}
                  {otpStep === 'verified' && (
                    <div className="shrink-0 px-3 py-2 bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl flex items-center gap-1">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                      </svg>
                      Tasdiqlandi
                    </div>
                  )}
                  {otpStep === 'otp_sent' && (
                    <button
                      type="button"
                      onClick={handleSendOtp}
                      disabled={otpLoading}
                      className="shrink-0 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm rounded-xl transition-colors"
                    >
                      Qayta yuborish
                    </button>
                  )}
                </div>
              </Field>

              {/* OTP kirish maydoni */}
              {otpStep === 'otp_sent' && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
                  <p className="text-sm text-blue-700 font-medium">
                    📱 Telegram botingizga OTP kod yuborildi. Kodni kiriting:
                  </p>
                  {devOtp && (
                    <p className="text-xs text-slate-500 italic">{devOtp}</p>
                  )}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={otpCode}
                      onChange={e => { setOtpCode(e.target.value); setError(''); }}
                      placeholder="123456"
                      maxLength={6}
                      className="flex-1 px-3.5 py-2.5 border border-blue-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-center tracking-widest text-lg font-bold"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={handleVerifyOtp}
                      disabled={otpLoading || otpCode.length < 6}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl transition-colors"
                    >
                      {otpLoading ? '...' : 'Tasdiqlash'}
                    </button>
                  </div>
                </div>
              )}

              {/* Qolgan formalar — faqat OTP tasdiqlangandan keyin */}
              {otpStep === 'verified' && (
                <>
                  <Field label="Email">
                    <input
                      type="email" value={form.email}
                      onChange={e => setField('email', e.target.value)}
                      placeholder="email@example.com" className={inp}
                    />
                  </Field>
                  <Field label={`${t('user.password')} *`}>
                    <input
                      type="password" required minLength={6} value={form.password}
                      onChange={e => setField('password', e.target.value)}
                      placeholder="Kamida 6 ta belgi" className={inp}
                    />
                  </Field>
                  <RoleSelect value={form.role} onChange={v => setField('role', v)} roles={ROLES} roleLabels={ROLE_LABELS} />
                  {branches.length > 0 && (
                    <BranchSelect value={form.branch_id} onChange={v => setField('branch_id', v)} branches={branches} />
                  )}
                </>
              )}

              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                {otpStep === 'verified' && (
                  <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                    {saving ? t('common.saving') : t('common.add')}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── EDIT MODAL ─────────────────────────────────────── */}
      {modal === 'edit' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('user.editUser')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleEdit} className="p-6 space-y-4">
              <Field label={`${t('common.name')} *`}>
                <input type="text" required value={form.name} onChange={e => setField('name', e.target.value)} className={inp} autoFocus />
              </Field>
              <Field label={`${t('common.phone')} *`}>
                <input type="text" required value={form.phone} onChange={e => setField('phone', e.target.value)} className={inp} />
              </Field>
              <Field label="Email">
                <input type="email" value={form.email} onChange={e => setField('email', e.target.value)} className={inp} />
              </Field>
              <RoleSelect value={form.role} onChange={v => setField('role', v)} roles={ROLES} roleLabels={ROLE_LABELS} />
              {branches.length > 0 && (
                <BranchSelect value={form.branch_id} onChange={v => setField('branch_id', v)} branches={branches} />
              )}
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? t('common.saving') : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── PASSWORD MODAL ─────────────────────────────────── */}
      {modal === 'password' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">{t('user.changePassword')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handlePwd} className="p-6 space-y-4">
              <p className="text-sm text-slate-600"><strong>{selected.name}</strong></p>
              <Field label={t('user.password')}>
                <input
                  type="password" required minLength={6} value={newPwd} autoFocus
                  onChange={e => setNewPwd(e.target.value)}
                  placeholder="Kamida 6 ta belgi" className={inp} />
              </Field>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? '...' : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
