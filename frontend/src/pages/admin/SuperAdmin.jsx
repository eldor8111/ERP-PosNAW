import { useState, useEffect } from 'react';
import api from '../../api/axios';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';

const ROLE_LABELS = {
  super_admin: 'Super Admin', admin: 'Admin', director: 'Direktor',
  manager: 'Menejer', accountant: 'Buxgalter', warehouse: 'Omborchi', cashier: 'Kassir',
};
const ROLE_COLORS = {
  super_admin: 'bg-purple-100 text-purple-700', admin: 'bg-red-100 text-red-700',
  director: 'bg-violet-100 text-violet-700', manager: 'bg-blue-100 text-blue-700',
  accountant: 'bg-green-100 text-green-700', warehouse: 'bg-amber-100 text-amber-700',
  cashier: 'bg-indigo-100 text-indigo-700',
};

const Ic = ({ d, cls = "w-4 h-4" }) => (
  <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
  </svg>
);

/* ─── Company Detail Panel (Modal) ─────────────────── */
function CompanyDetailPanel({ companyId, companyName, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('branches');

  useEffect(() => {
    setLoading(true);
    api.get(`/super-admin/companies/${companyId}`)
      .then(r => setDetail(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [companyId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center font-black text-base">
              {companyName?.[0]?.toUpperCase()}
            </div>
            <div>
              <h3 className="font-bold text-slate-800">{companyName}</h3>
              {detail && (
                <p className="text-xs text-slate-400">
                  {detail.stats?.branches} filial · {detail.stats?.users} xodim · {detail.stats?.warehouses} ombor
                </p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
            <Ic d="M6 18L18 6M6 6l12 12" />
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center items-center py-20">
            <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : !detail ? (
          <div className="text-center text-slate-400 py-16">Ma'lumot topilmadi</div>
        ) : (
          <>
            {/* Tabs */}
            <div className="flex gap-1 px-6 pt-4 shrink-0">
              {[
                { id: 'branches', label: `Filiallar (${detail.branches?.length || 0})` },
                { id: 'users', label: `Xodimlar (${detail.branches?.reduce((s, b) => s + (b.users_count || 0), 0) || 0})` },
              ].map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-all ${tab === t.id ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {tab === 'branches' && (
                <div className="space-y-2">
                  {detail.branches?.length === 0 && (
                    <p className="text-slate-400 text-sm text-center py-8">Filiallar yo'q</p>
                  )}
                  {detail.branches?.map(b => (
                    <div key={b.id} className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                      <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm">
                        {b.name?.[0]?.toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800 text-sm truncate">{b.name}</div>
                        {b.address && <div className="text-xs text-slate-400 truncate">{b.address}</div>}
                      </div>
                      <div className="text-xs text-slate-400">{b.users_count} xodim</div>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${b.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                        {b.is_active ? 'Faol' : 'Nofaol'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {tab === 'users' && (
                <BranchUsersView branches={detail.branches || []} />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function BranchUsersView({ branches }) {
  const [branchId, setBranchId] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!branchId) { setUsers([]); return; }
    setLoading(true);
    api.get(`/super-admin/branches/${branchId}`)
      .then(r => setUsers(r.data.users || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [branchId]);

  return (
    <div className="space-y-3">
      <select value={branchId || ''} onChange={e => setBranchId(e.target.value || null)}
        className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
        <option value="">Filialni tanlang</option>
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>
      {loading && <div className="flex justify-center py-6"><div className="w-6 h-6 border-4 border-indigo-400 border-t-transparent rounded-full animate-spin" /></div>}
      {!loading && users.length === 0 && branchId && <p className="text-slate-400 text-sm text-center py-6">Xodimlar yo'q</p>}
      {!loading && !branchId && <p className="text-slate-400 text-sm text-center py-6">Filialni tanlang</p>}
      {users.map(u => (
        <div key={u.id} className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
          <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold">
            {u.name?.[0]?.toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-slate-800 text-sm">{u.name}</div>
            <div className="text-xs text-slate-400">{u.phone}</div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${ROLE_COLORS[u.role] || 'bg-slate-100 text-slate-500'}`}>
            {ROLE_LABELS[u.role] || u.role}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
            {u.status === 'active' ? 'Faol' : 'Nofaol'}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─── Agents Tab ─────────────────────────────────── */
function AgentsTab() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', code: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [newAgent, setNewAgent] = useState(null);
  const [editAgent, setEditAgent] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', phone: '' });
  const [editError, setEditError] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [pinValue, setPinValue] = useState('');
  const [pinError, setPinError] = useState('');
  const [pinDeleting, setPinDeleting] = useState(false);
  const [deletePin, setDeletePin] = useState('');

  const load = () => {
    setLoading(true);
    api.get('/agents/').then(r => setAgents(r.data)).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const openModal = () => { setForm({ name: '', phone: '', code: '' }); setError(''); setNewAgent(null); setShowModal(true); };
  const closeModal = () => { setShowModal(false); setError(''); };

  const handleCreate = async () => {
    if (!form.name.trim() || !form.phone.trim()) { setError("Ism va telefon raqam kiritilishi shart"); return; }
    setSaving(true); setError('');
    try {
      const payload = { name: form.name.trim(), phone: form.phone.trim() };
      if (form.code.trim()) payload.code = form.code.trim().toUpperCase();
      const res = await api.post('/agents/', payload);
      setNewAgent(res.data); setShowModal(false); load();
    } catch (e) { setError(e?.response?.data?.detail || "Xatolik yuz berdi"); }
    finally { setSaving(false); }
  };

  const toggleActive = async (agent) => { await api.patch(`/agents/${agent.id}`, { is_active: !agent.is_active }); load(); };

  const openEdit = (agent) => { setEditAgent(agent); setEditForm({ name: agent.name, phone: agent.phone }); setEditError(''); };
  const closeEdit = () => { setEditAgent(null); setEditError(''); };
  const handleEdit = async () => {
    if (!editForm.name.trim() || !editForm.phone.trim()) { setEditError("Ism va telefon raqam kiritilishi shart"); return; }
    setEditSaving(true); setEditError('');
    try {
      await api.patch(`/agents/${editAgent.id}`, { name: editForm.name.trim(), phone: editForm.phone.trim() });
      closeEdit(); load();
    } catch (e) { setEditError(e?.response?.data?.detail || "Xatolik yuz berdi"); }
    finally { setEditSaving(false); }
  };

  const openDelete = (agent) => { const pin = String(Math.floor(1000 + Math.random() * 9000)); setDeletePin(pin); setDeleteTarget(agent); setPinValue(''); setPinError(''); };
  const closeDelete = () => { setDeleteTarget(null); setPinValue(''); setPinError(''); };
  const confirmDelete = async () => {
    if (pinValue !== deletePin) { setPinError("PIN noto'g'ri. Iltimos, qayta kiriting."); setPinValue(''); return; }
    setPinDeleting(true);
    try { await api.delete(`/agents/${deleteTarget.id}`); closeDelete(); load(); }
    catch { setPinError("O'chirishda xatolik yuz berdi"); }
    finally { setPinDeleting(false); }
  };

  const modalInput = "w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300 transition-all";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-slate-800">Agentlar ro'yxati</h3>
          <p className="text-xs text-slate-400 mt-0.5">Har bir agent uchun unikal kod avtomatik yaratiladi</p>
        </div>
        <button onClick={openModal} className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm shadow-indigo-200 transition-all">
          <Ic d="M12 4v16m8-8H4" />
          Agent qo'shish
        </button>
      </div>

      {newAgent && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center font-black">
            <Ic d="M5 13l4 4L19 7" cls="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold text-emerald-800">Agent muvaffaqiyatli qo'shildi!</div>
            <div className="text-xs text-emerald-600 mt-0.5">{newAgent.name} — unikal kod:</div>
          </div>
          <div className="text-2xl font-black text-emerald-700 bg-white px-5 py-2 rounded-xl border border-emerald-200 tracking-widest">{newAgent.code}</div>
          <button onClick={() => setNewAgent(null)} className="text-emerald-400 hover:text-emerald-600">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center">
                  <Ic d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </div>
                <h4 className="font-bold text-slate-800">Yangi agent qo'shish</h4>
              </div>
              <button onClick={closeModal} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">Ismi *</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Masalan: Alisher Rahimov" autoFocus className={modalInput} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">Telefon raqami *</label>
                <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} placeholder="+998901234567" className={modalInput} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">
                  Kod <span className="font-normal text-slate-400">(ixtiyoriy — bo'sh qoldirsangiz avtomatik yaratiladi)</span>
                </label>
                <input value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} placeholder="Masalan: J4602" maxLength={10}
                  className={`${modalInput} font-mono tracking-widest uppercase`} />
              </div>
              {error && <div className="text-xs text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100">{error}</div>}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-2 justify-end">
              <button onClick={closeModal} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">Bekor qilish</button>
              <button onClick={handleCreate} disabled={saving} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm disabled:opacity-50 transition-all">
                {saving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center">
                  <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </div>
                <div>
                  <h4 className="font-bold text-slate-800">Agentni tahrirlash</h4>
                  <p className="text-xs text-slate-400">Kod: <span className="font-mono font-bold text-indigo-600">{editAgent.code}</span></p>
                </div>
              </div>
              <button onClick={closeEdit} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">Ismi *</label>
                <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} autoFocus
                  className={modalInput.replace('indigo-300', 'amber-300')} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 mb-1.5 block">Telefon raqami *</label>
                <input value={editForm.phone} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))}
                  className={modalInput.replace('indigo-300', 'amber-300')} />
              </div>
              {editError && <div className="text-xs text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100">{editError}</div>}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-2 justify-end">
              <button onClick={closeEdit} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">Bekor qilish</button>
              <button onClick={handleEdit} disabled={editSaving} className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-xl shadow-sm disabled:opacity-50 transition-all">
                {editSaving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PIN Delete Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-6 text-center">
              <div className="w-14 h-14 rounded-2xl bg-red-100 text-red-600 flex items-center justify-center mx-auto mb-4">
                <Ic d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" cls="w-7 h-7" />
              </div>
              <h4 className="font-black text-slate-800 text-lg mb-1">Agentni o'chirish</h4>
              <p className="text-sm text-slate-500 mb-1"><span className="font-semibold text-slate-700">{deleteTarget.name}</span> o'chirilmoqda</p>
              <p className="text-xs text-slate-400 mb-5">
                Tasdiqlash uchun <span className="font-black text-red-500 text-base tracking-widest">{deletePin}</span> kodni kiriting
              </p>
              <input
                value={pinValue}
                onChange={e => { setPinValue(e.target.value.replace(/\D/g, '').slice(0, 4)); setPinError(''); }}
                onKeyDown={e => e.key === 'Enter' && confirmDelete()}
                placeholder="• • • •"
                maxLength={4} autoFocus
                className="w-full border-2 border-slate-200 rounded-xl px-4 py-3 text-center text-2xl font-black tracking-[0.4em] focus:outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100 mb-3"
              />
              {pinError && <div className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg mb-3">{pinError}</div>}
            </div>
            <div className="px-6 pb-5 flex gap-2">
              <button onClick={closeDelete} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">Bekor qilish</button>
              <button onClick={confirmDelete} disabled={pinDeleting || pinValue.length < 4}
                className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-xl shadow-sm disabled:opacity-40 transition-all">
                {pinDeleting ? "O'chirilmoqda..." : "O'chirish"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">
            Agentlar <span className="text-indigo-600 font-black">({agents.length})</span>
          </h3>
          <button onClick={load} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg font-medium transition-all">Yangilash</button>
        </div>
        {loading ? (
          <div className="py-16 flex justify-center"><div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <table className="min-w-full">
            <thead><tr className="bg-slate-50 border-b border-slate-100">
              {['#','Kod','Ismi','Telefon','Holat','Korxonalar','Sana','Amallar'].map(h => (
                <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {agents.map((a, i) => (
                <tr key={a.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="px-5 py-4 text-xs text-slate-400">{i + 1}</td>
                  <td className="px-5 py-4">
                    <span className="font-black text-indigo-700 bg-indigo-50 px-3 py-1 rounded-lg tracking-widest text-sm border border-indigo-100">{a.code}</span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center text-xs font-bold">{a.name?.[0]?.toUpperCase()}</div>
                      <span className="text-sm font-semibold text-slate-800">{a.name}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-sm text-slate-500">{a.phone}</td>
                  <td className="px-5 py-4">
                    <button onClick={() => toggleActive(a)}
                      className={`px-2.5 py-1 text-xs font-semibold rounded-full cursor-pointer transition-all ${a.is_active ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-red-100 text-red-600 hover:bg-red-200'}`}>
                      {a.is_active ? 'Faol' : 'Nofaol'}
                    </button>
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-700 text-xs font-bold rounded-lg border border-indigo-100 shadow-sm">
                      {a.companies_count || 0} ta
                    </span>
                  </td>
                  <td className="px-5 py-4 text-sm text-slate-400">{fmtDate(a.created_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <button onClick={() => openEdit(a)} className="text-xs px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-600 rounded-lg font-medium transition-all flex items-center gap-1 border border-amber-100">
                        <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-3 h-3" />
                        Tahrirlash
                      </button>
                      <button onClick={() => openDelete(a)} className="text-xs px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-500 rounded-lg font-medium transition-all border border-red-100">
                        O'chirish
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {agents.length === 0 && (
                <tr><td colSpan={8} className="px-5 py-14 text-center">
                  <div className="w-12 h-12 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
                    <Ic d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" cls="w-6 h-6 text-slate-400" />
                  </div>
                  <p className="text-slate-400 text-sm">Agentlar topilmadi</p>
                  <p className="text-slate-300 text-xs mt-1">Yuqoridagi tugma orqali qo'shing</p>
                </td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ─── Standalone Agents Page ─────────────────────── */
export function AgentsPage() {
  return (
    <div className="space-y-5">
      <AgentsTab />
    </div>
  );
}

/* ─── Main SuperAdmin ─────────────────────────────── */
export default function SuperAdmin({ defaultTab = 'companies' }) {
  const [companies, setCompanies] = useState([]);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(defaultTab);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [topUp, setTopUp] = useState({ org_code: '', amount: '' });
  const [topUpMsg, setTopUpMsg] = useState(null);
  const [topUpLoading, setTopUpLoading] = useState(false);

  const handleTopUp = async (e) => {
    e.preventDefault();
    if (!topUp.org_code || !topUp.amount) return;
    setTopUpLoading(true);
    setTopUpMsg(null);
    try {
      const res = await api.post('/super-admin/top-up', {
        org_code: topUp.org_code.toUpperCase(),
        amount: parseFloat(topUp.amount),
      });
      setTopUpMsg({ ok: true, text: `✓ ${res.data.company_name} — yangi balans: ${res.data.new_balance.toLocaleString()} s` });
      setTopUp({ org_code: '', amount: '' });
      loadCompanies();
      window.dispatchEvent(new Event('balance-updated'));
    } catch (err) {
      setTopUpMsg({ ok: false, text: err.response?.data?.detail || 'Xatolik yuz berdi' });
    } finally {
      setTopUpLoading(false);
    }
  };

  const loadCompanies = () => {
    setLoading(true);
    api.get('/super-admin/companies').then(r => setCompanies(r.data)).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => {
    api.get('/super-admin/overview').then(r => setOverview(r.data)).catch(() => {});
    loadCompanies();
  }, []);

  const tabs = [
    { id: 'companies', label: 'Korxonalar', icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { id: 'agents', label: 'Agentlar', icon: 'M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z' },
  ];

  return (
    <div className="space-y-5">
      {/* Header Stats */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-2xl bg-linear-to-br from-purple-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-indigo-200 shrink-0">
            <Ic d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" cls="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-black text-slate-800">Super Admin Panel</h1>
            <p className="text-xs text-slate-400">Tizim bo'yicha to'liq boshqaruv</p>
          </div>
          <span className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-100 text-purple-700 text-xs font-bold rounded-full">
            <span className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-pulse" />
            Super Admin
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Korxonalar', value: overview?.companies ?? '—', color: 'text-indigo-700 bg-indigo-50' },
            { label: 'Filiallar', value: overview?.branches ?? '—', color: 'text-emerald-700 bg-emerald-50' },
            { label: 'Xodimlar', value: overview?.users ?? '—', color: 'text-blue-700 bg-blue-50' },
            { label: 'Jami sotuv', value: overview ? `${Number(overview.total_revenue||0).toLocaleString('uz-UZ')} s` : '—', color: 'text-purple-700 bg-purple-50' },
          ].map(s => (
            <div key={s.label} className={`rounded-xl p-3 ${s.color} border border-white/60`}>
              <div className="text-[10px] font-semibold uppercase tracking-wide opacity-70 mb-1">{s.label}</div>
              <div className="text-xl font-black">{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white rounded-2xl border border-slate-100 shadow-sm p-1.5 w-fit">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all
              ${tab === t.id ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' : 'text-slate-600 hover:bg-slate-100'}`}>
            <Ic d={t.icon} cls="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Companies Tab */}
      {tab === 'companies' && (
        <>
        {/* Balans to'ldirish forma */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 mb-4">
          <h3 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center">
              <Ic d="M12 6v6m0 0v6m0-6h6m-6 0H6" cls="w-4 h-4 text-emerald-600" />
            </div>
            Korxona balansi to'ldirish
          </h3>
          <form onSubmit={handleTopUp} className="flex items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500 font-medium">Tashkilot kodi</label>
              <input
                value={topUp.org_code}
                onChange={e => setTopUp(p => ({ ...p, org_code: e.target.value.toUpperCase() }))}
                placeholder="Masalan: AB1234"
                className="border border-slate-200 rounded-xl px-3 py-2 text-sm font-mono font-bold text-indigo-700 w-40 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-500 font-medium">Miqdor (so'm)</label>
              <input
                type="number"
                value={topUp.amount}
                onChange={e => setTopUp(p => ({ ...p, amount: e.target.value }))}
                placeholder="100000"
                min="1"
                className="border border-slate-200 rounded-xl px-3 py-2 text-sm w-44 focus:outline-none focus:ring-2 focus:ring-emerald-300"
              />
            </div>
            <button
              type="submit"
              disabled={topUpLoading}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl transition-all disabled:opacity-60"
            >
              {topUpLoading ? 'Yuklanmoqda...' : 'Qo\'shish'}
            </button>
          </form>
          {topUpMsg && (
            <p className={`mt-3 text-sm font-semibold px-3 py-2 rounded-xl ${topUpMsg.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
              {topUpMsg.text}
            </p>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-700">
              Korxonalar ro'yxati <span className="text-indigo-600 font-black">({companies.length})</span>
            </h3>
            <button onClick={loadCompanies} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg font-medium transition-all">Yangilash</button>
          </div>
          {loading ? (
            <div className="flex justify-center py-16"><div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>
          ) : companies.length === 0 ? (
            <div className="py-16 text-center text-slate-400 text-sm">Korxonalar topilmadi</div>
          ) : (
            <table className="min-w-full">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {['#', 'Korxona nomi', 'Kod', "Ro'yxatdan o'tgan sana", 'Holat', ''].map(h => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {companies.map((c, i) => (
                  <tr key={c.id}
                    className="hover:bg-indigo-50/40 cursor-pointer transition-colors"
                    onClick={() => setSelectedCompany(c)}>
                    <td className="px-5 py-3 text-xs text-slate-400">{i + 1}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-sm shrink-0">
                          {c.name?.[0]?.toUpperCase()}
                        </div>
                        <span className="font-semibold text-slate-800 text-sm">{c.name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span className="font-mono font-bold text-indigo-700 bg-indigo-50 px-2.5 py-1 rounded-lg text-xs border border-indigo-100 tracking-widest">
                        {c.code || '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-sm text-slate-500">{fmtDate(c.created_at)}</td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${c.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                        {c.is_active ? 'Faol' : 'Nofaol'}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-300">
                      <Ic d="M9 5l7 7-7 7" cls="w-4 h-4" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        </>
      )}

      {/* Agents Tab */}
      {tab === 'agents' && <AgentsTab />}

      {/* Company Detail Modal */}
      {selectedCompany && (
        <CompanyDetailPanel
          companyId={selectedCompany.id}
          companyName={selectedCompany.name}
          onClose={() => setSelectedCompany(null)}
        />
      )}
    </div>
  );
}
