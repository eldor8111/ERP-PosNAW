import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../api/axios';

// super_admin ni dropdown dan yashiramiz — faqat DB orqali beriladi
const ROLES = ['admin', 'director', 'manager', 'accountant', 'warehouse', 'cashier'];

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin', director: 'Direktor', manager: 'Menejer',
  accountant: 'Buxgalter', warehouse: 'Omborchi', cashier: 'Kassir',
};

const ROLE_COLORS = {
  super_admin: 'bg-purple-100 text-purple-700',
  admin: 'bg-red-100 text-red-700',
  director: 'bg-purple-100 text-purple-700',
  manager: 'bg-blue-100 text-blue-700',
  accountant: 'bg-emerald-100 text-emerald-700',
  warehouse: 'bg-amber-100 text-amber-700',
  cashier: 'bg-indigo-100 text-indigo-700',
};

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

export default function Users() {
  const [users, setUsers] = useState([]);
  const [branches, setBranches] = useState([]);
  const [modal, setModal] = useState(null); // 'edit' | 'password'
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ name: '', phone: '', email: '', role: 'cashier', branch_id: null });
  const [newPwd, setNewPwd] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = () => api.get('/users/').then(r => setUsers(r.data)).catch(() => {});
  useEffect(() => {
    load();
    api.get('/branches').then(r => setBranches(r.data)).catch(() => {});
  }, []);

  const openEdit = (u) => {
    setForm({ name: u.name, phone: u.phone, email: u.email || '', role: u.role, branch_id: u.branch_id ?? null });
    setSelected(u); setError(''); setModal('edit');
  };
  const openPwd = (u) => { setSelected(u); setNewPwd(''); setError(''); setModal('password'); };
  const close = () => { setModal(null); setSelected(null); setError(''); };

  const handleEdit = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.put(`/users/${selected.id}`, form);
      close(); load();
    } catch (err) { setError(err.response?.data?.detail || 'Xatolik yuz berdi'); }
    finally { setSaving(false); }
  };

  const handlePwd = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api.patch(`/users/${selected.id}/password`, { new_password: newPwd });
      close();
    } catch (err) { setError(err.response?.data?.detail || 'Xatolik yuz berdi'); }
    finally { setSaving(false); }
  };

  const handleDeactivate = async (u) => {
    if (!confirm(`"${u.name}" ni nofaol qilishni tasdiqlaysizmi?`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      load();
    } catch (err) { alert(err.response?.data?.detail || "O'chirib bo'lmadi"); }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Foydalanuvchilar</h1>
          <p className="text-slate-500 text-sm mt-0.5">Xodimlar va ularning rollari boshqaruvi</p>
        </div>
        <Link
          to="/admin/users/create"
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          Yangi xodim
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Jami xodimlar" value={users.length} color="indigo" />
        <StatCard label="Kassirlar" value={users.filter(u => u.role === 'cashier').length} color="emerald" />
        <StatCard label="Menejerlar" value={users.filter(u => u.role === 'manager').length} color="violet" />
        <StatCard label="Adminlar" value={users.filter(u => u.role === 'admin' || u.role === 'director').length} color="slate" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['Xodim', 'Telefon', 'Email', 'Filial', 'Rol', 'Holat', ''].map(h => (
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
                    {u.status === 'active' ? 'Faol' : 'Nofaol'}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-1 justify-end">
                    <button onClick={() => openEdit(u)} title="Tahrirlash" className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button onClick={() => openPwd(u)} title="Parolni o'zgartirish" className="p-1.5 text-amber-500 hover:bg-amber-50 rounded-lg transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                      </svg>
                    </button>
                    <button onClick={() => handleDeactivate(u)} title="Nofaol qilish" className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={6} className="px-6 py-16 text-center text-slate-400 text-sm">Foydalanuvchilar topilmadi</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── EDIT MODAL ─────────────────────────────────────── */}
      {modal === 'edit' && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={close}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-800">Xodimni tahrirlash</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleEdit} className="p-6 space-y-4">
              {[
                { label: 'Ism', key: 'name', type: 'text', required: true },
                { label: 'Telefon', key: 'phone', type: 'text', required: true },
                { label: 'Email', key: 'email', type: 'email', required: false },
              ].map(({ label, key, type, required }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">{label}</label>
                  <input
                    type={type} required={required} value={form[key]}
                    onChange={e => setForm({ ...form, [key]: e.target.value })}
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              ))}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Rol</label>
                <select
                  value={form.role}
                  onChange={e => setForm({ ...form, role: e.target.value })}
                  className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </select>
              </div>
              {branches.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Filial</label>
                  <select
                    value={form.branch_id ?? ''}
                    onChange={e => setForm({ ...form, branch_id: e.target.value ? Number(e.target.value) : null })}
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">— Filialsiz —</option>
                    {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              )}
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">Bekor</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? 'Saqlanmoqda...' : 'Saqlash'}
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
              <h3 className="text-lg font-bold text-slate-800">Parolni o'zgartirish</h3>
              <button onClick={close} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handlePwd} className="p-6 space-y-4">
              <p className="text-sm text-slate-600"><strong>{selected.name}</strong> uchun yangi parol o'rnatiladi.</p>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Yangi parol</label>
                <input
                  type="password" required minLength={6} value={newPwd} autoFocus
                  onChange={e => setNewPwd(e.target.value)}
                  placeholder="Kamida 6 ta belgi"
                  className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>
              {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}
              <div className="flex gap-3">
                <button type="button" onClick={close} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">Bekor</button>
                <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                  {saving ? '...' : 'O\'zgartirish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
