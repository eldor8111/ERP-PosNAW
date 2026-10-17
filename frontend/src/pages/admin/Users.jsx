import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';
import { PERMISSIONS } from '../../constants/permissions';
import RoleSelect from '../../components/users/RoleSelect';
import BranchSelect, { branchLabel } from '../../components/users/BranchSelect';
import { formatBalances } from '../../utils/money';
import { useBranches } from '../../hooks/useBranches';

// super_admin ni dropdown dan yashiramiz — faqat DB orqali beriladi
// courier/agent — faqat E-code Mobile ilovasi orqali ishlaydi (veb-panelga kira olmaydi)
const ROLES = ['admin', 'director', 'manager', 'accountant', 'warehouse', 'cashier', 'courier', 'agent'];

const getRoleLabels = (t) => ({
  super_admin: t('role.super_admin'),
  admin: t('role.admin'), director: t('role.director'), manager: t('role.manager'),
  accountant: t('role.accountant') || 'Buxgalter', warehouse: t('role.warehouseman'), cashier: t('role.cashier'),
  courier: t('role.courier'), agent: t('role.agent'),
});

const ROLE_COLORS = {
  super_admin: 'bg-blue-100 text-blue-700',
  admin: 'bg-red-100 text-red-700',
  director: 'bg-blue-100 text-blue-700',
  manager: 'bg-blue-100 text-blue-700',
  accountant: 'bg-emerald-100 text-emerald-700',
  warehouse: 'bg-amber-100 text-amber-700',
  cashier: 'bg-blue-100 text-blue-700',
  courier: 'bg-orange-100 text-orange-700',
  agent: 'bg-violet-100 text-violet-700',
};

const BLANK_FORM = { name: '', phone: '', email: '', password: '', role: 'cashier', role_id: null, branch_id: '', branch_ids: [], permissions: {} };

const inp = "w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed";

function StatCard({ label, value, color = 'slate' }) {
  const txt = {
    indigo: 'text-blue-600', emerald: 'text-emerald-600',
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

// T1.2: filial tanlash — manager/accountant uchun bir nechta (branch_ids), boshqa rollar uchun bitta
const MULTI_BRANCH_ROLES = ['manager', 'accountant'];

// Foydalanuvchining filial id'lari (jadval uchun): branch_ids, bo'lmasa branch_id
function userBranchIds(u) {
  if (Array.isArray(u.branch_ids) && u.branch_ids.length) return u.branch_ids;
  return u.branch_id ? [u.branch_id] : [];
}

// Formadagi tanlov -> API: multi rollar branch_ids (birinchisi asosiy branch_id), boshqalar bitta branch_id
function branchPayload(form) {
  if (MULTI_BRANCH_ROLES.includes(form.role)) {
    const ids = (form.branch_ids && form.branch_ids.length ? form.branch_ids : (form.branch_id ? [form.branch_id] : [])).map(Number);
    return { branch_id: ids.length ? ids[0] : null, branch_ids: ids };
  }
  return { branch_id: form.branch_id ? Number(form.branch_id) : null, branch_ids: [] };
}

// OTP bosqichlari: 'form' → 'otp_sent' → 'otp_verified'
export default function Users() {
  const { t } = useLang();
  const [users, setUsers] = useState([]);
  const { branches } = useBranches({ includeInactive: true });   // T3.8: yagona filial hooki
  const [wallets, setWallets] = useState([]);
  const [dynamicRoles, setDynamicRoles] = useState([]);
  const [userWallets, setUserWallets] = useState([]); // {wallet_id, is_default}
  const [modal, setModal] = useState(null); // 'create' | 'edit' | 'password' | 'kassa'
  const [selected, setSelected] = useState(null);
  const [activeMenu, setActiveMenu] = useState(null); // 3-dots action menu
  const [form, setForm] = useState(BLANK_FORM);
  const [newPwd, setNewPwd] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const ROLE_LABELS = getRoleLabels(t);

  // i18n kaliti hali qo'shilmagan bo'lsa (t() kalitni qaytaradi) — o'zbekcha zaxira matn
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const currentUser = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
  })();
  // Bir nechta korxonada ishlaydigan xodimning shaxsiy ma'lumotlarini faqat o'zi o'zgartiradi (T0.38)
  const sharedLocked = !!selected?.is_shared && selected.id !== currentUser?.id && currentUser?.role !== 'super_admin';
  // Filialsiz eski xodimni tahrirlashda filial majburiy emas (T3.4: backend ham faqat yuborilgan branch_id ni tekshiradi)
  const editHadBranch = !!(selected && (selected.branch_id || (selected.branch_ids || []).length));

  const load = useCallback(() => {
    api.get('/users/').then(r => setUsers(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || t('auth.errGeneral')) });
  }, [t]);

  useEffect(() => {
    const handleClick = () => setActiveMenu(null);
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, []);

  useEffect(() => {
    load();
    api.get('/kassa').then(r => setWallets(r.data)).catch(() => { });
    api.get('/roles/').then(r => setDynamicRoles(r.data)).catch(() => { });
  }, [load]);

  const openCreate = () => {
    // Bitta faol filial bo'lsa shu filial oldindan tanlanadi ("Filialsiz" standart bo'lib qolmasin)
    const activeBranches = branches.filter(b => b.is_active !== false);
    setForm({ ...BLANK_FORM, branch_id: activeBranches.length === 1 ? String(activeBranches[0].id) : '' });
    setError('');
    setModal('create');
  };
  const openEdit = (u) => {
    setForm({ name: u.name, phone: u.phone, email: u.email || '', password: '', role: u.role, role_id: u.role_id || null, branch_id: u.branch_id ?? '', branch_ids: u.branch_ids || (u.branch_id ? [u.branch_id] : []), permissions: u.permissions || {} });
    setSelected(u); setError(''); setModal('edit');
  };
  const openKassa = async (u) => {
    setSelected(u);
    try {
      const [walletsRes, uwRes] = await Promise.all([
        api.get('/kassa'),
        api.get(`/users/${u.id}/wallets`).catch(() => ({ data: [] }))
      ]);
      // T1.10: xodim filiali (va umumiy) kassalari yuqorida; boshqa filial kassalari pastda, "boshqa filial" belgisi bilan
      const ub = u.branch_id ?? null;
      const isOwn = (w) => ub == null || w.branch_id == null || w.branch_id === ub;
      setWallets([...(walletsRes.data || [])].sort((a, b) => Number(isOwn(b)) - Number(isOwn(a))));
      setUserWallets((uwRes.data || []).map(w => ({ wallet_id: w.id, is_default: w.is_default })));
    } catch { setUserWallets([]); }
    setModal('kassa');
  };
  const openPwd = (u) => {
    setSelected(u);
    setNewPwd('');
    setError('');
    setModal('password');
  };

  const toggleWallet = async (walletId, checked) => {
    try {
      if (checked) {
        const res = await api.post(`/users/${selected.id}/wallets`, {
          wallet_id: walletId,
          is_default: userWallets.length === 0
        });
        setUserWallets(prev => [...prev, { wallet_id: walletId, is_default: prev.length === 0 }]);
        if (res?.data?.warning) toast(res.data.warning, { icon: '⚠️' }); // T1.10: kassa filiali xodim filialiga mos emas
      } else {
        await api.delete(`/users/${selected.id}/wallets/${walletId}`);
        setUserWallets(prev => prev.filter(w => w.wallet_id !== walletId));
      }
      toast.success(checked ? t('user.walletAssigned') : t('user.walletRemoved'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('auth.errGeneral'));
    }
  };

  const setDefaultWallet = async (walletId) => {
    try {
      const res = await api.post(`/users/${selected.id}/wallets/${walletId}/set-default`);
      if (res?.data?.warning) toast(res.data.warning, { icon: '⚠️' });
      setUserWallets(prev => prev.map(w => ({ ...w, is_default: w.wallet_id === walletId })));
      toast.success(t('user.defaultWalletSet'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('auth.errGeneral'));
    }
  };

  const close = () => {
    setModal(null); setSelected(null); setError('');
  };

  const setField = useCallback((key, val) => {
    setForm(prev => ({ ...prev, [key]: val }));
  }, []);

  // Foydalanuvchi yaratish
  const handleCreate = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email || null,
        password: form.password,
        role: form.role,
        role_id: form.role_id,
        permissions: form.permissions,
        ...branchPayload(form),
      };
      await api.post('/users/', payload);
      close(); load();
      toast.success(t('user.createdSuccess'));
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
        role_id: form.role_id,
        permissions: form.permissions,
        ...branchPayload(form),
      };
      if (sharedLocked) {
        // Umumiy xodim: shaxsiy maydonlar yuborilmaydi (filial esa korxona bo'yicha — T1.2, yuboriladi)
        delete payload.name; delete payload.phone; delete payload.email;
        delete payload.role_id;
      }
      // Filialsiz eski xodim va filial tanlanmagan — branch_id yuborilmaydi (majburiylik tekshiruvi ishga tushmasin)
      if (!editHadBranch && !form.branch_id && !(form.branch_ids || []).length) {
        delete payload.branch_id; delete payload.branch_ids;
      }
      await api.put(`/users/${selected.id}`, payload);
      close(); load();
    } catch (err) {
      const msg = err.response?.data?.detail || t('common.error');
      setError(msg); toast.error(msg);
    }
    finally { setSaving(false); }
  };

  const handlePwd = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.patch(`/users/${selected.id}/password`, { new_password: newPwd });
      close();
    } catch (err) {
      const msg = err.response?.data?.detail || t('common.error');
      setError(msg); toast.error(msg);
    }
    finally { setSaving(false); }
  };

  const handleDeactivate = async (u) => {
    if (!confirm(t('confirm.delete') || t('user.deactivateConfirm'))) return;
    try {
      await api.delete(`/users/${u.id}`);
      load();
    } catch (err) { alert(err.response?.data?.detail || t('common.error')); }
  };

  // Admin-bot Telegram bog'lanishini uzish (xodim botda /start + kontakt bilan qayta ulanadi)
  const handleUnlinkTelegram = async (u) => {
    if (!confirm(tf('user.unlinkTelegramConfirm', `${u.name}: Telegram bog'lanishini uzishni tasdiqlaysizmi?`))) return;
    try {
      await api.post(`/users/${u.id}/unlink-telegram`);
      toast.success(tf('user.unlinkTelegramDone', 'Telegram bog\'lanishi uzildi'));
    } catch (err) { toast.error(err.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('user.staffTitle')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{t('user.staffSubtitle')}</p>
        </div>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          {t('user.newStaff')}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t('user.totalEmployees') || "Jami xodimlar"} value={users.length} color="indigo" />
        <StatCard label={t('user.cashiers') || "Kassirlar"} value={users.filter(u => u.role === 'cashier').length} color="emerald" />
        <StatCard label={t('user.managers') || "Menejerlar"} value={users.filter(u => u.role === 'manager').length} color="violet" />
        <StatCard label={t('user.admins') || "Adminlar"} value={users.filter(u => u.role === 'admin' || u.role === 'director').length} color="slate" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-x-auto" style={{ minHeight: users.length < 5 ? '350px' : 'auto' }}>
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {[t('common.name') || 'Xodim', t('common.phone'), t('user.email'), t('branch.title') || 'Filial', t('user.role'), t('common.status'), ''].map(h => (
                <th key={h} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold shrink-0">
                      {u.name?.[0]?.toUpperCase()}
                    </div>
                    <span className="text-sm font-semibold text-slate-800">{u.name}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-500">{u.phone}</td>
                <td className="px-6 py-4 text-sm text-slate-500">{u.email || '—'}</td>
                <td className="px-6 py-4 text-sm text-slate-500">
                  {userBranchIds(u).length ? userBranchIds(u).map(id => branchLabel(branches, id, tf)).join(', ') : '—'}
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${u.role_id ? 'bg-blue-50 text-blue-700' : (ROLE_COLORS[u.role] || 'bg-slate-100 text-slate-600')}`}>
                    {u.role_id ? (dynamicRoles.find(r => r.id === u.role_id)?.name || t('user.customRole')) : (ROLE_LABELS[u.role] || u.role)}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {u.status === 'active' ? t('common.active') : t('common.inactive')}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="relative inline-block text-left" onClick={e => e.stopPropagation()}>
                    <button 
                      onClick={() => setActiveMenu(activeMenu === u.id ? null : u.id)}
                      className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                      </svg>
                    </button>
                    
                    {activeMenu === u.id && (
                      <div className="absolute right-0 mt-2 w-52 bg-white border border-slate-100 rounded-2xl shadow-xl py-2 z-50">
                        <button onClick={() => { setActiveMenu(null); openEdit(u); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-blue-600 transition-colors">
                          <svg className="w-5 h-5 text-slate-400 group-hover:text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                          {t('common.edit')}
                        </button>
                        <button onClick={() => { setActiveMenu(null); openKassa(u); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-emerald-600 transition-colors">
                          <svg className="w-5 h-5 text-slate-400 group-hover:text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                          </svg>
                          {t('user.assignWallet')}
                        </button>
                        <button onClick={() => { setActiveMenu(null); openPwd(u); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-amber-600 transition-colors">
                          <svg className="w-5 h-5 text-slate-400 group-hover:text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                          </svg>
                          {t('user.changePassword')}
                        </button>
                        <button onClick={() => { setActiveMenu(null); handleUnlinkTelegram(u); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-sky-600 transition-colors">
                          <svg className="w-5 h-5 text-slate-400 group-hover:text-sky-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1M6 18L18 6" />
                          </svg>
                          {tf('user.unlinkTelegram', 'Telegramni uzish')}
                        </button>
                        <div className="h-px bg-slate-100 my-1 mx-2"></div>
                        <button onClick={() => { setActiveMenu(null); handleDeactivate(u); }} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors">
                          <svg className="w-5 h-5 text-red-400 group-hover:text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                          {t('common.delete')}
                        </button>
                      </div>
                    )}
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
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">{t('user.newUser')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 overflow-y-auto flex flex-col gap-6" style={{ scrollbarWidth: 'thin' }}>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Ism */}
                <Field label={`${t('common.name')} *`}>
                  <input
                    type="text" required value={form.name}
                    onChange={e => setField('name', e.target.value)}
                    placeholder={t('common.name')} className={inp}
                    autoFocus
                  />
                </Field>

                {/* Telefon */}
                <Field label={`${t('common.phone')} *`}>
                  <input
                    type="text" required value={form.phone}
                    onChange={e => setField('phone', e.target.value)}
                    placeholder="+998901234567" className={inp}
                  />
                </Field>

                <Field label={t('user.email')}>
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
                    placeholder={t('user.minCharsHint')} className={inp}
                  />
                </Field>

                <RoleSelect role={form.role} roleId={form.role_id} roles={ROLES} roleLabels={ROLE_LABELS} dynamicRoles={dynamicRoles} onChange={({ role, role_id }) => { setField('role', role); setField('role_id', role_id); }} />
                
                {branches.length > 0 && (
                  <BranchSelect role={form.role} multi={MULTI_BRANCH_ROLES.includes(form.role)} value={form.branch_id} onChange={v => { setField('branch_id', v); setField('branch_ids', []); }} values={form.branch_ids && form.branch_ids.length ? form.branch_ids : (form.branch_id ? [form.branch_id] : [])} onChangeMany={ids => { setField('branch_ids', ids); setField('branch_id', ids.length ? ids[0] : ''); }} branches={branches} />
                )}
              </div>
              


              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? t('common.saving') : t('common.add')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── EDIT MODAL ─────────────────────────────────────── */}
      {modal === 'edit' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[95vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
              <h3 className="text-lg font-bold text-slate-800">{t('user.editUser')}</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleEdit} className="p-6 overflow-y-auto flex flex-col gap-6" style={{ scrollbarWidth: 'thin' }}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {sharedLocked && <div className="sm:col-span-2"><div className="px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-xl">{tf('user.sharedNote', "Bu xodim boshqa korxonalarda ham ishlaydi, shaxsiy ma'lumotlarni faqat o'zi o'zgartiradi")}</div></div>}
                <Field label={`${t('common.name')} *`}>
                  <input type="text" required value={form.name} onChange={e => setField('name', e.target.value)} className={inp} autoFocus={!sharedLocked} disabled={sharedLocked} />
                </Field>
                <Field label={`${t('common.phone')} *`}>
                  <input type="text" required value={form.phone} onChange={e => setField('phone', e.target.value)} className={inp} disabled={sharedLocked} />
                </Field>
                <Field label={t('user.email')}>
                  <input type="email" value={form.email} onChange={e => setField('email', e.target.value)} className={inp} disabled={sharedLocked} />
                </Field>
                <RoleSelect role={form.role} roleId={form.role_id} roles={ROLES} roleLabels={ROLE_LABELS} dynamicRoles={dynamicRoles} onChange={({ role, role_id }) => { setField('role', role); setField('role_id', role_id); }} />
                {branches.length > 0 && (
                  <BranchSelect role={form.role} required={editHadBranch ? undefined : false} multi={MULTI_BRANCH_ROLES.includes(form.role)} value={form.branch_id} onChange={v => { setField('branch_id', v); setField('branch_ids', []); }} values={form.branch_ids && form.branch_ids.length ? form.branch_ids : (form.branch_id ? [form.branch_id] : [])} onChangeMany={ids => { setField('branch_ids', ids); setField('branch_id', ids.length ? ids[0] : ''); }} branches={branches} />
                )}
              </div>
              


              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
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
              {sharedLocked && <div className="px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-xl">{tf('user.sharedNote', "Bu xodim boshqa korxonalarda ham ishlaydi, shaxsiy ma'lumotlarni faqat o'zi o'zgartiradi")}</div>}
              <Field label={t('user.password')}>
                <input
                  type="password" required minLength={6} value={newPwd} autoFocus={!sharedLocked}
                  onChange={e => setNewPwd(e.target.value)} disabled={sharedLocked}
                  placeholder={t('user.minCharsHint')} className={inp} />
              </Field>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
                <button type="submit" disabled={saving || sharedLocked} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? '...' : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── KASSA MODAL ─────────────────────────────────────── */}
      {modal === 'kassa' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div>
                <h3 className="text-lg font-bold text-slate-800">{t('user.assignWallet')}</h3>
                <p className="text-xs text-slate-500 mt-0.5">{selected.name}</p>
              </div>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-3 max-h-80 overflow-y-auto">
              {wallets.length === 0 && <p className="text-slate-400 text-sm text-center py-4">{t('user.noWalletsHint')}</p>}
              {wallets.map(w => {
                const assigned = userWallets.find(uw => uw.wallet_id === w.id);
                const isDefault = assigned?.is_default;
                const otherBranch = selected.branch_id != null && w.branch_id != null && w.branch_id !== selected.branch_id;
                return (
                  <div key={w.id} className={`flex items-center gap-3 p-3 rounded-xl border transition-all ${assigned ? 'border-emerald-200 bg-emerald-50' : 'border-slate-100 bg-slate-50'}`}>
                    <input
                      type="checkbox"
                      checked={!!assigned}
                      onChange={e => toggleWallet(w.id, e.target.checked)}
                      className="w-4 h-4 text-emerald-600 rounded"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-800">{w.name}</div>
                      <div className="text-xs text-slate-400">
                        {w.type} • {formatBalances(w.balances?.total, t)}
                        {w.branch_name && <span className={`ml-1.5 px-1.5 py-0.5 rounded ${otherBranch ? 'bg-amber-100 text-amber-700' : 'bg-sky-50 text-sky-700'}`}>{w.branch_name}{otherBranch ? ` · ${t('user.otherBranchWallet')}` : ''}</span>}
                      </div>
                    </div>
                    {assigned && (
                      <button
                        onClick={() => setDefaultWallet(w.id)}
                        className={`text-xs px-2 py-1 rounded-lg font-medium transition-colors ${isDefault ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-600 hover:bg-emerald-100'}`}
                      >
                        {isDefault ? `✓ ${t('user.defaultBadge')}` : t('user.defaultBadge')}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="px-6 pb-6">
              <button onClick={close} className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium text-sm rounded-xl transition-colors">{t('common.close')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
