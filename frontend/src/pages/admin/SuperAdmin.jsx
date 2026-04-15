import { useState, useEffect } from 'react';
import { useLang } from '../../context/LangContext';
import api from '../../api/axios';
import toast from 'react-hot-toast';

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

/* ─── Company Detail Drawer (o'ng tomondan siljib chiqadigan katta panel) ─── */
function CompanyDetailPanel({ companyId, companyName, onClose }) {
  const { t } = useLang();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [tab, setTab] = useState('branches');
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setTimeout(() => setVisible(true), 10);
    setLoading(true);
    setLoadError(false);
    api.get(`/super-admin/companies/${companyId}`)
      .then(r => setDetail(r.data))
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [companyId]);

  const handleClose = () => {
    setVisible(false);
    setTimeout(onClose, 280);
  };

  const totalUsers = detail?.branches?.reduce((s, b) => s + (b.users_count || 0), 0) || 0;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className={`flex-1 bg-black/30 backdrop-blur-sm transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'}`}
        onClick={handleClose}
      />
      {/* Drawer */}
      <div className={`w-full max-w-2xl bg-white h-full flex flex-col shadow-2xl transition-transform duration-300 ease-out ${visible ? 'translate-x-0' : 'translate-x-full'}`}>

        {/* ── Header ── */}
        <div className="shrink-0 bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-5 text-white">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center font-black text-xl">
                {companyName?.[0]?.toUpperCase()}
              </div>
              <div>
                <h2 className="text-lg font-black leading-tight">{companyName}</h2>
                {detail && (
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    {detail.region && (
                      <span className="flex items-center gap-1 text-xs bg-white/20 px-2 py-0.5 rounded-full">
                        <Ic d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" cls="w-3 h-3" />
                        {detail.region}
                        {detail.district && ` · ${detail.district}`}
                      </span>
                    )}
                    {detail.phone && (
                      <span className="text-xs text-white/70">{detail.phone}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
            <button onClick={handleClose} className="w-8 h-8 flex items-center justify-center rounded-xl bg-white/20 hover:bg-white/30 text-white shrink-0">
              <Ic d="M6 18L18 6M6 6l12 12" />
            </button>
          </div>

          {/* Stats row */}
          {detail && (
            <div className="grid grid-cols-4 gap-2 mt-4">
              {[
                { label: 'Filiallar', value: detail.stats?.branches ?? 0, icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16' },
                { label: 'Xodimlar', value: detail.stats?.users ?? 0, icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0' },
                { label: 'Omborlar', value: detail.stats?.warehouses ?? 0, icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
                { label: 'Balans', value: `${Number(detail.balance || 0).toLocaleString('uz-UZ')} s`, icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
              ].map(s => (
                <div key={s.label} className="bg-white/15 rounded-xl px-3 py-2 text-center">
                  <div className="text-lg font-black">{s.value}</div>
                  <div className="text-xs text-white/70 mt-0.5">{s.label}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Tabs ── */}
        <div className="shrink-0 flex gap-1 px-5 pt-4 pb-2 border-b border-slate-100">
          {[
            { id: 'branches', label: `Filiallar (${detail?.branches?.length || 0})`, icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16' },
            { id: 'users',    label: `Xodimlar (${totalUsers})`,                    icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0' },
            { id: 'tariff',   label: 'Tarif hisoboti',                               icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
          ].map(tb => (
            <button key={tb.id} onClick={() => setTab(tb.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${tab === tb.id ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100'}`}>
              <Ic d={tb.icon} cls="w-3.5 h-3.5" />
              {tb.label}
            </button>
          ))}
        </div>

        {/* ── Body ── */}
        {loading ? (
          <div className="flex-1 flex justify-center items-center">
            <div className="w-9 h-9 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loadError ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-400 px-6">
            <div className="w-14 h-14 rounded-2xl bg-red-100 text-red-500 flex items-center justify-center">
              <Ic d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-7 h-7" />
            </div>
            <p className="text-sm font-semibold text-slate-600">Ma'lumotlarni yuklashda xatolik</p>
            <button
              onClick={() => { setLoadError(false); setLoading(true); api.get(`/super-admin/companies/${companyId}`).then(r => setDetail(r.data)).catch(() => setLoadError(true)).finally(() => setLoading(false)); }}
              className="text-xs px-4 py-2 bg-indigo-100 hover:bg-indigo-200 text-indigo-700 rounded-xl font-semibold transition-all"
            >
              Qayta urinish
            </button>
          </div>
        ) : !detail ? (
          <div className="flex-1 flex items-center justify-center text-slate-400">{t('common.noData')}</div>
        ) : (
          <div className="flex-1 overflow-y-auto px-5 py-4">

            {/* ── FILIALLAR ── */}
            {tab === 'branches' && (
              <div className="space-y-2">
                {detail.branches?.length === 0 && (
                  <div className="text-center text-slate-400 py-16">Filiallar yo'q</div>
                )}
                {detail.branches?.map((b) => (
                  <div key={b.id} className="flex items-center gap-3 p-4 bg-slate-50 hover:bg-indigo-50/50 rounded-2xl border border-slate-100 transition-colors">
                    <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm shrink-0">
                      {b.name?.[0]?.toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-800 text-sm">{b.name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold shrink-0 ${b.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                          {b.is_active ? 'Faol' : 'Nofaol'}
                        </span>
                      </div>
                      {b.address && (
                        <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-400">
                          <Ic d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" cls="w-3 h-3 shrink-0" />
                          {b.address}
                        </div>
                      )}
                      {b.phone && (
                        <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-400">
                          <Ic d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" cls="w-3 h-3 shrink-0" />
                          {b.phone}
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-bold text-indigo-700">{b.users_count}</div>
                      <div className="text-xs text-slate-400">xodim</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ── XODIMLAR ── */}
            {tab === 'users' && (
              <DrawerBranchUsers branches={detail.branches || []} />
            )}

            {/* ── TARIF HISOBOTI ── */}
            {tab === 'tariff' && (
              <DrawerTariffReport detail={detail} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DrawerBranchUsers({ branches }) {
  const [branchId, setBranchId] = useState('');
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    if (!branchId) { setUsers([]); setFetchError(false); return; }
    setLoading(true);
    setFetchError(false);
    api.get(`/super-admin/branches/${branchId}`)
      .then(r => setUsers(r.data.users || []))
      .catch(() => setFetchError(true))
      .finally(() => setLoading(false));
  }, [branchId]);

  return (
    <div className="space-y-3">
      <select value={branchId} onChange={e => setBranchId(e.target.value)}
        className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-slate-50">
        <option value="">— Filialni tanlang —</option>
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>

      {!branchId && (
        <div className="flex flex-col items-center justify-center py-16 text-slate-400">
          <Ic d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0" cls="w-10 h-10 mb-2 opacity-30" />
          <p className="text-sm">Filialni tanlang</p>
        </div>
      )}
      {loading && <div className="flex justify-center py-10"><div className="w-7 h-7 border-4 border-indigo-400 border-t-transparent rounded-full animate-spin" /></div>}
      {!loading && fetchError && (
        <div className="flex flex-col items-center justify-center py-10 gap-2">
          <div className="w-10 h-10 rounded-xl bg-red-100 text-red-500 flex items-center justify-center">
            <Ic d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-5 h-5" />
          </div>
          <p className="text-sm text-red-500 font-semibold">Xodimlarni yuklab bo'lmadi</p>
          <button onClick={() => { const id = branchId; setBranchId(''); setTimeout(() => setBranchId(id), 50); }}
            className="text-xs px-3 py-1.5 bg-indigo-100 hover:bg-indigo-200 text-indigo-700 rounded-lg font-semibold">
            Qayta urinish
          </button>
        </div>
      )}
      {!loading && !fetchError && branchId && users.length === 0 && (
        <p className="text-slate-400 text-sm text-center py-10">Bu filialda xodimlar yo'q</p>
      )}
      {!loading && users.map(u => (
        <div key={u.id} className="flex items-center gap-3 p-4 bg-slate-50 hover:bg-indigo-50/50 rounded-2xl border border-slate-100 transition-colors">
          <div className="w-10 h-10 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-sm font-bold shrink-0">
            {u.name?.[0]?.toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-bold text-slate-800 text-sm">{u.name}</div>
            <div className="text-xs text-slate-400 mt-0.5">{u.phone}</div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${ROLE_COLORS[u.role] || 'bg-slate-100 text-slate-500'}`}>
              {ROLE_LABELS[u.role] || u.role}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
              {u.status === 'active' ? 'Faol' : 'Nofaol'}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function DrawerTariffReport({ detail }) {
  const fmtMon = v => Number(v || 0).toLocaleString('uz-UZ');
  const fmtDt = d => d ? new Date(d).toLocaleDateString('uz-UZ', { year: 'numeric', month: 'long', day: 'numeric' }) : '—';

  const subActive = detail.subscription_active;
  const daysLeft = detail.days_left ?? 0;
  const daysColor = daysLeft > 14 ? 'text-emerald-600' : daysLeft > 3 ? 'text-amber-500' : 'text-red-500';

  return (
    <div className="space-y-4">
      {/* Tarif kartasi */}
      <div className="bg-gradient-to-br from-indigo-50 to-violet-50 rounded-2xl border border-indigo-100 p-5">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-bold text-slate-700 text-sm">Joriy tarif</h4>
          {detail.is_trial && (
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-semibold">Sinov muddati</span>
          )}
        </div>
        <div className="text-2xl font-black text-indigo-700 mb-1">
          {detail.tariff_name || 'Tarif belgilanmagan'}
        </div>
        <div className="flex items-center gap-2 mt-3">
          <span className={`w-2 h-2 rounded-full ${subActive ? 'bg-emerald-500' : 'bg-red-400'}`} />
          <span className={`text-sm font-semibold ${subActive ? 'text-emerald-600' : 'text-red-500'}`}>
            {subActive ? 'Obuna faol' : 'Obuna tugagan'}
          </span>
        </div>
      </div>

      {/* Ma'lumotlar grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4">
          <div className="text-xs text-slate-400 mb-1">Balans</div>
          <div className="text-xl font-black text-slate-800">{fmtMon(detail.balance)} <span className="text-sm font-semibold text-slate-400">so'm</span></div>
        </div>
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4">
          <div className="text-xs text-slate-400 mb-1">Qolgan kunlar</div>
          <div className={`text-xl font-black ${daysColor}`}>{daysLeft} <span className="text-sm font-semibold text-slate-400">kun</span></div>
        </div>
        <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 col-span-2">
          <div className="text-xs text-slate-400 mb-1">Obuna tugash sanasi</div>
          <div className="text-base font-bold text-slate-700">{fmtDt(detail.subscription_ends_at)}</div>
        </div>
      </div>

      {/* Qo'shimcha ma'lumotlar */}
      <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 space-y-2.5">
        <h4 className="font-bold text-slate-600 text-xs uppercase tracking-wider mb-3">Korxona ma'lumotlari</h4>
        {[
          { label: "Ro'yxatdan o'tgan", value: fmtDt(detail.created_at) },
          { label: 'Viloyat', value: detail.region || '—' },
          { label: 'Tuman', value: detail.district || '—' },
          { label: 'Manzil', value: detail.address || '—' },
          { label: 'Telefon', value: detail.phone || '—' },
          { label: 'Email', value: detail.email || '—' },
        ].map(row => (
          <div key={row.label} className="flex items-start justify-between gap-3">
            <span className="text-xs text-slate-400 shrink-0">{row.label}</span>
            <span className="text-xs font-semibold text-slate-700 text-right">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Agents Tab ─────────────────────────────────── */
function AgentsTab() {
  const { t } = useLang();
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
    api.get('/agents/').then(r => setAgents(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") }).finally(() => setLoading(false));
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
              <button onClick={closeModal} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">{t('common.cancel')}</button>
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
              <button onClick={closeEdit} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">{t('common.cancel')}</button>
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
              <button onClick={closeDelete} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-semibold rounded-xl transition-all">{t('common.cancel')}</button>
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
          <button onClick={load} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg font-medium transition-all">{t('common.refresh')}</button>
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
  const { t } = useLang();
const [companies, setCompanies] = useState([]);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(defaultTab);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [topUp, setTopUp] = useState({ org_code: '', amount: '' });
  const [topUpMsg, setTopUpMsg] = useState(null);
  const [topUpLoading, setTopUpLoading] = useState(false);
  const [foundCompany, setFoundCompany] = useState(null);   // { id, name, org_code }
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErr, setSearchErr] = useState('');

  const handleSearchCompany = async (e) => {
    e.preventDefault();
    if (!topUp.org_code.trim()) return;
    setSearchLoading(true);
    setSearchErr('');
    setFoundCompany(null);
    try {
      const res = await api.get(`/super-admin/companies?search=${topUp.org_code.trim().toUpperCase()}`);
      const match = res.data.find(c => (c.code || '').toUpperCase() === topUp.org_code.trim().toUpperCase());
      if (match) {
        setFoundCompany(match);
      } else {
        setSearchErr(`"${topUp.org_code.toUpperCase()}" kodi bilan korxona topilmadi`);
      }
    } catch {
      setSearchErr('Qidirishda xatolik yuz berdi');
    } finally {
      setSearchLoading(false);
    }
  };

  const handleTopUp = async (e) => {
    e.preventDefault();
    if (!foundCompany || !topUp.amount) return;
    setTopUpLoading(true);
    setTopUpMsg(null);
    try {
      const res = await api.post('/super-admin/top-up', {
        org_code: foundCompany.code,
        amount: parseFloat(topUp.amount),
      });
      setTopUpMsg({ ok: true, text: `✓ ${res.data.company_name} — yangi balans: ${res.data.new_balance.toLocaleString()} s` });
      setTopUp({ org_code: '', amount: '' });
      setFoundCompany(null);
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
    api.get('/super-admin/companies').then(r => setCompanies(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") }).finally(() => setLoading(false));
  };

  useEffect(() => {
    api.get('/super-admin/overview').then(r => setOverview(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    loadCompanies();
  }, []);

  const tabs = [
    { id: 'companies', label: 'Korxonalar', icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
    { id: 'billing',   label: 'Billing',    icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z' },
    { id: 'tariffs',   label: 'Tariflar',   icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
    { id: 'settings',  label: 'Sozlamalar', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  ];

  return (
    <div className="space-y-5">
      {/* Header Stats */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-purple-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-indigo-200 shrink-0">
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
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: 'Korxonalar',  value: overview?.companies ?? '—',  color: 'text-indigo-700 bg-indigo-50' },
            { label: 'Filiallar',   value: overview?.branches  ?? '—',  color: 'text-emerald-700 bg-emerald-50' },
            { label: 'Xodimlar',    value: overview?.users     ?? '—',  color: 'text-blue-700 bg-blue-50' },
            { label: 'Jami sotuv',  value: overview ? `${Number(overview.total_revenue||0).toLocaleString('uz-UZ')} s` : '—', color: 'text-purple-700 bg-purple-50' },
            {
              label: "Bugun tariflar",
              value: overview ? `${overview.today_subscriptions ?? 0} ta` : '—',
              color: 'text-amber-700 bg-amber-50',
              sub: overview ? `${Number(overview.today_sub_revenue || 0).toLocaleString('uz-UZ')} s` : null,
            },
            {
              label: "Bugun tushum",
              value: overview ? `${Number(overview.today_sub_revenue || 0).toLocaleString('uz-UZ')} s` : '—',
              color: 'text-rose-700 bg-rose-50',
            },
          ].map(s => (
            <div key={s.label} className={`rounded-xl p-3 ${s.color} border border-white/60`}>
              <div className="text-[10px] font-semibold uppercase tracking-wide opacity-70 mb-1">{s.label}</div>
              <div className="text-lg font-black leading-tight">{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      {(
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
      )}

      {/* Companies Tab */}
      {tab === 'companies' && (
        <>
        {/* Balans to'ldirish forma — 2 bosqich */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 mb-4">
          <h3 className="text-sm font-bold text-slate-700 mb-4 flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center">
              <Ic d="M12 6v6m0 0v6m0-6h6m-6 0H6" cls="w-4 h-4 text-emerald-600" />
            </div>
            Korxona balansi to'ldirish
          </h3>

          {/* Step 1 — search */}
          {!foundCompany ? (
            <form onSubmit={handleSearchCompany} className="flex items-end gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-slate-500 font-medium">Tashkilot kodi</label>
                <input
                  value={topUp.org_code}
                  onChange={e => { setTopUp(p => ({ ...p, org_code: e.target.value.toUpperCase() })); setSearchErr(''); }}
                  placeholder="Masalan: 12345678"
                  className="border border-slate-200 rounded-xl px-3 py-2 text-sm font-mono font-bold text-indigo-700 w-44 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  autoFocus
                />
              </div>
              <button
                type="submit"
                disabled={searchLoading || !topUp.org_code.trim()}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-xl transition-all disabled:opacity-60 flex items-center gap-2"
              >
                {searchLoading
                  ? <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/></svg>Qidirilmoqda...</>
                  : <><Ic d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" cls="w-4 h-4" />Qidirish</>
                }
              </button>
            </form>
          ) : (
            /* Step 2 — confirm & enter amount */
            <div className="space-y-4">
              {/* Company confirmation card */}
              <div className="flex items-center gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3">
                <div className="w-9 h-9 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-black text-base shrink-0">
                  {foundCompany.name?.[0]?.toUpperCase()}
                </div>
                <div className="flex-1">
                  <div className="font-bold text-slate-800 text-sm">{foundCompany.name}</div>
                  <div className="text-xs text-indigo-500 font-mono font-bold mt-0.5">Kod: {foundCompany.code}</div>
                </div>
                <button
                  onClick={() => { setFoundCompany(null); setTopUp(p => ({ ...p, amount: '' })); setTopUpMsg(null); }}
                  className="text-slate-400 hover:text-red-500 transition-colors"
                  title="Bekor qilish"
                >
                  <Ic d="M6 18L18 6M6 6l12 12" cls="w-4 h-4" />
                </button>
              </div>

              {/* Amount form */}
              <form onSubmit={handleTopUp} className="flex items-end gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-slate-500 font-medium">Miqdor (so'm)</label>
                  <input
                    type="number"
                    value={topUp.amount}
                    onChange={e => setTopUp(p => ({ ...p, amount: e.target.value }))}
                    placeholder="100000"
                    min="1"
                    autoFocus
                    className="border border-slate-200 rounded-xl px-3 py-2 text-sm w-48 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                </div>
                <button
                  type="submit"
                  disabled={topUpLoading || !topUp.amount}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl transition-all disabled:opacity-60"
                >
                  {topUpLoading ? 'Yuklanmoqda...' : 'Balansni to\'ldirish'}
                </button>
              </form>
            </div>
          )}

          {/* Messages */}
          {searchErr && (
            <p className="mt-3 text-sm font-semibold px-3 py-2 rounded-xl bg-red-50 text-red-600">{searchErr}</p>
          )}
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
            <button onClick={loadCompanies} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg font-medium transition-all">{t('common.refresh')}</button>
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

      {/* ── BILLING TAB ── */}
      {tab === 'billing' && <BillingTab />}

      {/* ── TARIFLAR TAB ── */}
      {tab === 'tariffs' && <TariffsTab />}

      {/* ── SETTINGS TAB ── */}
      {tab === 'settings' && <SettingsTab />}

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

/* ─── fmt helper ─────────────────────────────────── */
const fmtMoney = (v) => Number(v || 0).toLocaleString('uz-UZ');

/* ─── BILLING TAB ───────────────────────────────────── */
function BillingTab() {
  const { t } = useLang();
const [list, setList] = useState([]);
  const [tariffs, setTariffs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionModal, setActionModal] = useState(null); // { company, type: 'trial'|'subscribe'|'topup' }
  const [subForm, setSubForm] = useState({ tariff_id: '', months: 1 });
  const [topupForm, setTopupForm] = useState({ amount: '', note: '' });
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get('/billing/companies'),
      api.get('/billing/tariffs'),
    ]).then(([r1, r2]) => {
      setList(r1.data);
      setTariffs(r2.data);
    }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") }).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const activateTrial = async (c) => {
    setSaving(true);
    try {
      const r = await api.post(`/billing/companies/${c.id}/activate-trial`);
      alert(r.data.message);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); setActionModal(null); }
  };

  const doTopUp = async () => {
    const amount = Number(topupForm.amount);
    if (!amount || amount <= 0) return alert('Miqdor kiriting!');
    setSaving(true);
    try {
      const r = await api.post(`/billing/companies/${actionModal.company.id}/top-up`, {
        amount,
        note: topupForm.note || undefined,
      });
      alert(r.data.message);
      load();
      setActionModal(null);
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); }
  };

  const activateSubscription = async () => {
    if (!subForm.tariff_id) return alert('Tarif tanlang!');
    setSaving(true);
    try {
      const r = await api.post(`/billing/companies/${actionModal.company.id}/subscribe`, {
        tariff_id: Number(subForm.tariff_id),
        months: Number(subForm.months),
      });
      alert(r.data.message + `\nBalansdan yechildi: ${fmtMoney(r.data.charged)} so'm`);
      load();
      setActionModal(null);
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); }
  };

  const statusBadge = (c) => {
    if (!c.subscription_active) return <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-600">Tugagan</span>;
    if (c.is_trial) return <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700">Sinov ({c.days_left}k)</span>;
    return <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700">Faol ({c.days_left}k)</span>;
  };

  const filtered = list.filter(c => {
    const q = search.toLowerCase();
    if (q && !c.name?.toLowerCase().includes(q) && !c.org_code?.toLowerCase().includes(q)) return false;
    if (dateFrom && c.created_at && c.created_at < dateFrom) return false;
    if (dateTo && c.created_at && c.created_at.slice(0, 10) > dateTo) return false;
    return true;
  });

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-slate-800 flex items-center gap-2">
          <span className="w-7 h-7 bg-blue-100 rounded-lg flex items-center justify-center">
            <Ic d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" cls="w-4 h-4 text-blue-600" />
          </span>
          Korxonalar Billing
          <span className="text-xs font-normal text-slate-400">({filtered.length}/{list.length})</span>
        </h3>
        <button onClick={load} className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg font-semibold text-slate-600 transition-all">
          Yangilash
        </button>
      </div>

      {/* Filter qatori */}
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder="Korxona nomi yoki kodi..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-[180px] text-sm border border-slate-200 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-blue-300 bg-white"
        />
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>Dan:</span>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-blue-300 bg-white" />
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>Gacha:</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-blue-300 bg-white" />
        </div>
        {(search || dateFrom || dateTo) && (
          <button onClick={() => { setSearch(''); setDateFrom(''); setDateTo(''); }}
            className="text-xs px-2.5 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg font-semibold border border-red-100 transition-all">
            Tozalash
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-100">
              <tr>
                {['Korxona', 'Yaratilgan', 'Balans', 'Tarif', 'Obuna holati', 'Tugash sanasi', 'Amallar'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.length === 0 && (
                <tr><td colSpan={7} className="text-center py-10 text-slate-400 text-sm">Hech narsa topilmadi</td></tr>
              )}
              {filtered.map(c => (
                <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-800">{c.name}</div>
                    <div className="text-xs text-slate-400 font-mono">{c.org_code}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {c.created_at ? new Date(c.created_at).toLocaleDateString('uz-UZ') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-black text-sm ${c.balance < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                      {fmtMoney(c.balance)} s
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">{c.tariff_name || '—'}</td>
                  <td className="px-4 py-3">{statusBadge(c)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {c.subscription_ends_at ? new Date(c.subscription_ends_at).toLocaleDateString('uz-UZ') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => { setActionModal({ company: c, type: 'trial' }); }}
                        className="text-xs px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-700 rounded-lg font-semibold border border-amber-100 transition-all"
                      >
                        7kun sinov
                      </button>
                      <button
                        onClick={() => { setActionModal({ company: c, type: 'subscribe' }); setSubForm({ tariff_id: c.tariff_id || '', months: 1 }); }}
                        className="text-xs px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg font-semibold border border-blue-100 transition-all"
                      >
                        Obuna
                      </button>
                      <button
                        onClick={() => { setActionModal({ company: c, type: 'topup' }); setTopupForm({ amount: '', note: '' }); }}
                        className="text-xs px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-lg font-semibold border border-emerald-100 transition-all"
                      >
                        + Pul
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Action Modal */}
      {actionModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-slate-800">
                {actionModal.type === 'trial' ? '7 kunlik sinov' : actionModal.type === 'topup' ? 'Balansni to\'ldirish' : 'Obunani faollashtirish'}
              </h3>
              <button onClick={() => setActionModal(null)} className="text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>

            <div className="bg-slate-50 rounded-xl p-3 mb-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center font-black text-sm">
                {actionModal.company.name?.[0]?.toUpperCase()}
              </div>
              <div>
                <div className="font-semibold text-slate-800 text-sm">{actionModal.company.name}</div>
                <div className="text-xs text-slate-400">Balans: <span className="font-bold text-emerald-700">{fmtMoney(actionModal.company.balance)} s</span></div>
              </div>
            </div>

            {actionModal.type === 'trial' ? (
              <div className="mb-5">
                <p className="text-sm text-slate-600">Bu korxonaga <span className="font-bold text-amber-600">7 kunlik bepul sinov muddati</span> beriladi. Hozirgi obuna muddatiga qo'shiladi.</p>
              </div>
            ) : actionModal.type === 'topup' ? (
              <div className="space-y-3 mb-5">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">Miqdor (so'm)</label>
                  <input
                    type="number" min="1" placeholder="Masalan: 150000"
                    value={topupForm.amount}
                    onChange={e => setTopupForm(p => ({ ...p, amount: e.target.value }))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">Izoh (ixtiyoriy)</label>
                  <input
                    type="text" placeholder="To'lov sababi..."
                    value={topupForm.note}
                    onChange={e => setTopupForm(p => ({ ...p, note: e.target.value }))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-3 mb-5">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">Tarif</label>
                  <select value={subForm.tariff_id} onChange={e => setSubForm(p => ({...p, tariff_id: e.target.value}))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-300 bg-white">
                    <option value="">— Tarif tanlang —</option>
                    {tariffs.filter(t => t.price_per_month > 0).map(t => (
                      <option key={t.id} value={t.id}>{t.name} — {fmtMoney(t.price_per_month)} s/oy</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1.5">Muddat (oy)</label>
                  <select value={subForm.months} onChange={e => setSubForm(p => ({...p, months: Number(e.target.value)}))}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-300 bg-white">
                    {[1,2,3,6,12].map(m => <option key={m} value={m}>{m} oy</option>)}
                  </select>
                </div>
                {subForm.tariff_id && (
                  <div className="bg-blue-50 rounded-xl p-3 text-sm">
                    <span className="text-slate-500">Jami yechiladi: </span>
                    <span className="font-black text-blue-700">
                      {fmtMoney((tariffs.find(t => String(t.id) === String(subForm.tariff_id))?.price_per_month || 0) * subForm.months)} so'm
                    </span>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <button onClick={() => setActionModal(null)} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm transition-all">{t('common.cancel')}</button>
              <button
                onClick={actionModal.type === 'trial' ? () => activateTrial(actionModal.company) : actionModal.type === 'topup' ? doTopUp : activateSubscription}
                disabled={saving}
                className={`flex-1 py-2.5 text-white font-bold rounded-xl text-sm transition-all disabled:opacity-50 ${actionModal.type === 'topup' ? 'bg-emerald-600 hover:bg-emerald-700 shadow-lg shadow-emerald-200' : 'bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-200'}`}
              >
                {saving ? 'Saqlanmoqda...' : actionModal.type === 'trial' ? 'Sinov berish' : actionModal.type === 'topup' ? 'Balans qo\'shish' : 'Obunani yoqish'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Settings Tab ───────────────────────────────── */
function SettingsTab() {
  const { t } = useLang();
const FIELDS = [
    { key: 'card_number', label: "To'lov karta raqami",       placeholder: '8600 0000 0000 0000', icon: 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z' },
    { key: 'card_owner',  label: 'Karta egasining ismi',       placeholder: 'Abdualimov Eldorbek', icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { key: 'tg_username', label: 'Telegram username (@ siz)', placeholder: 'eldorservices',       icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z' },
    { key: 'phone',       label: "Telefon (ko'rsatish uchun)", placeholder: '+998 88 911 81 71',   icon: 'M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z' },
    { key: 'phone_raw',   label: 'Telefon (tel: link uchun)', placeholder: '+998889118171',        icon: 'M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1' },
  ];

  const [saved, setSaved]         = useState({});     // DB dagi haqiqiy qiymatlar
  const [draft, setDraft]         = useState({});     // Modal ichidagi tahrir
  const [loading, setLoading]     = useState(true);
  const [editOpen, setEditOpen]   = useState(false);
  const [saving, setSaving]       = useState(false);
  const [saveOk, setSaveOk]       = useState(false);
  const [error, setError]         = useState('');

  const load = () => {
    setLoading(true);
    api.get('/super-admin/platform-settings')
      .then(r => {
        const map = {};
        r.data.forEach(({ key, value }) => { map[key] = value || ''; });
        setSaved(map);
      })
      .catch(() => setError("Sozlamalarni yuklab bo'lmadi"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const openEdit = () => { setDraft({ ...saved }); setSaveOk(false); setError(''); setEditOpen(true); };
  const closeEdit = () => setEditOpen(false);

  const handleSave = async () => {
    setSaving(true); setSaveOk(false); setError('');
    try {
      await api.put('/super-admin/platform-settings', { values: draft });
      setSaved({ ...draft });
      setSaveOk(true);
      setTimeout(() => { setSaveOk(false); setEditOpen(false); }, 1500);
    } catch {
      setError("Saqlashda xatolik yuz berdi");
    } finally { setSaving(false); }
  };

  return (
    <>
      {/* ── Read-only view ── */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 max-w-2xl">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-md shadow-indigo-200">
              <Ic d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" cls="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="font-black text-slate-800">Platform Sozlamalari</h2>
              <p className="text-xs text-slate-400">Karta, Telegram va telefon raqamlari</p>
            </div>
          </div>
          <button
            onClick={openEdit}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl shadow-sm shadow-indigo-200 transition-all"
          >
            <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-3.5 h-3.5" />
            Tahrirlash
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-10">
            <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Karta preview */}
            <div className="bg-slate-900 rounded-2xl p-5 mb-4">
              <div className="text-slate-400 text-[10px] font-semibold uppercase tracking-widest mb-3">To'lov kartasi</div>
              <div className="text-white font-mono text-xl font-bold tracking-[0.2em] mb-1">
                {saved.card_number || '— — — —'}
              </div>
              <div className="text-slate-400 text-sm">{saved.card_owner || '—'}</div>
            </div>
            {/* Aloqa */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[#eaf6fd] rounded-xl px-4 py-3">
                <div className="text-[10px] text-slate-400 font-semibold uppercase mb-1">Telegram</div>
                <div className="text-[#2AABEE] font-bold text-sm">@{saved.tg_username || '—'}</div>
              </div>
              <div className="bg-emerald-50 rounded-xl px-4 py-3">
                <div className="text-[10px] text-slate-400 font-semibold uppercase mb-1">{t('admin.dict.phone') || 'Telefon'}</div>
                <div className="text-emerald-700 font-bold text-sm">{saved.phone || '—'}</div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Edit Modal ── */}
      {editOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-black text-slate-800">Sozlamalarni tahrirlash</h3>
              <button onClick={closeEdit} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                <Ic d="M6 18L18 6M6 6l12 12" />
              </button>
            </div>

            {/* Fields */}
            <div className="px-6 py-5 space-y-4 max-h-[60vh] overflow-y-auto">
              {FIELDS.map(f => (
                <div key={f.key}>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">{f.label}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Ic d={f.icon} cls="w-4 h-4" />
                    </div>
                    {f.key === 'card_number' ? (
                      <input
                        value={draft[f.key] || ''}
                        onChange={e => {
                          const raw = e.target.value.replace(/\D/g, '').slice(0, 16);
                          const formatted = raw.replace(/(.{4})/g, '$1 ').trim();
                          setDraft(v => ({ ...v, card_number: formatted }));
                        }}
                        placeholder={f.placeholder}
                        maxLength={19}
                        inputMode="numeric"
                        className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent font-mono tracking-widest"
                      />
                    ) : (
                      <input
                        value={draft[f.key] || ''}
                        onChange={e => setDraft(v => ({ ...v, [f.key]: e.target.value }))}
                        placeholder={f.placeholder}
                        className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent font-mono"
                      />
                    )}
                  </div>
                </div>
              ))}
              {error && <div className="text-xs text-red-600 bg-red-50 px-4 py-2.5 rounded-xl border border-red-100">{error}</div>}
              {saveOk && <div className="text-xs text-emerald-700 bg-emerald-50 px-4 py-2.5 rounded-xl border border-emerald-200 font-semibold">✓ Saqlandi!</div>}
            </div>

            {/* Footer */}
            <div className="px-6 pb-5 flex gap-3">
              <button onClick={closeEdit} className="flex-1 py-2.5 border border-slate-200 text-slate-600 hover:bg-slate-50 font-semibold rounded-xl text-sm transition-all">
                Bekor
              </button>
              <button onClick={handleSave} disabled={saving}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-indigo-200 text-sm transition-all">
                {saving ? 'Saqlanmoqda...' : '💾 Saqlash'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
/* ─── TARIFLAR TAB ───────────────────────────────────── */
function TariffsTab() {
  const { t } = useLang();
const [tariffs, setTariffs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [form, setForm] = useState({ name:'', description:'', price_per_month:0, duration_days:30, max_users:10, max_branches:2, sort_order:0 });
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api.get('/billing/tariffs').then(r => setTariffs(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const openNew = () => {
    setEditItem(null);
    setForm({ name:'', description:'', price_per_month:0, duration_days:30, max_users:10, max_branches:2, sort_order:0 });
    setShowForm(true);
  };

  const openEdit = (tariff) => {
    setEditItem(tariff);
    setForm({ name:tariff.name, description:tariff.description||'', price_per_month:tariff.price_per_month, duration_days:tariff.duration_days, max_users:tariff.max_users, max_branches:tariff.max_branches, sort_order:tariff.sort_order });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.name.trim()) return alert('Tarif nomini kiriting!');
    setSaving(true);
    try {
      if (editItem) {
        await api.put(`/billing/tariffs/${editItem.id}`, form);
      } else {
        await api.post('/billing/tariffs', form);
      }
      load();
      setShowForm(false);
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik');
    } finally { setSaving(false); }
  };

  const deactivate = async (id) => {
    if (!confirm("Tarifni o'chirishni tasdiqlaysizmi?")) return;
    await api.delete(`/billing/tariffs/${id}`).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    load();
  };

  const inp = "w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-indigo-300";

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-bold text-slate-800 flex items-center gap-2">
            <span className="w-7 h-7 bg-indigo-100 rounded-lg flex items-center justify-center">
              <Ic d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" cls="w-4 h-4 text-indigo-600" />
            </span>
            Tariflar
          </h3>
          <button onClick={openNew} className="text-xs px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold transition-all flex items-center gap-1.5">
            <Ic d="M12 4v16m8-8H4" cls="w-3.5 h-3.5" /> Yangi tarif
          </button>
        </div>
        {loading ? (
          <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 p-5">
            {tariffs.map(tariff => (
              <div key={tariff.id} className="border border-slate-200 rounded-2xl p-5 flex flex-col gap-3 hover:border-indigo-300 hover:shadow-md transition-all">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="font-black text-slate-800 text-base">{tariff.name}</h4>
                    {tariff.description && <p className="text-xs text-slate-400 mt-1">{tariff.description}</p>}
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${tariff.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                    {tariff.is_active ? 'Faol' : 'Nofaol'}
                  </span>
                </div>
                <div className="text-2xl font-black text-indigo-700">
                  {tariff.price_per_month === 0 ? 'Bepul' : `${fmtMoney(tariff.price_per_month)} s`}
                  {tariff.price_per_month > 0 && <span className="text-sm font-semibold text-slate-400">/oy</span>}
                </div>
                <div className="space-y-1 text-xs text-slate-500">
                  <div>⏱ Muddat: <span className="font-bold text-slate-700">{tariff.duration_days} kun</span></div>
                  <div>👤 Max xodim: <span className="font-bold text-slate-700">{tariff.max_users >= 9999 ? 'Cheksiz' : tariff.max_users}</span></div>
                  <div>🏢 Max filial: <span className="font-bold text-slate-700">{tariff.max_branches >= 9999 ? 'Cheksiz' : tariff.max_branches}</span></div>
                </div>
                <div className="flex gap-2 mt-auto pt-2 border-t border-slate-100">
                  <button onClick={() => openEdit(tariff)} className="flex-1 py-1.5 text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-all">{t('common.edit')}</button>
                  <button onClick={() => deactivate(tariff.id)} className="flex-1 py-1.5 text-xs font-bold bg-red-50 hover:bg-red-100 text-red-500 rounded-lg transition-all">{t('common.delete')}</button>
                </div>
              </div>
            ))}
            {tariffs.length === 0 && (
              <div className="col-span-full py-14 text-center text-slate-400 text-sm font-semibold">
                Hali tariflar yo'q — yuqoridagi "Yangi tarif" tugmasi orqali qo'shing
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tarif Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-bold text-slate-800">{editItem ? 'Tarifni tahrirlash' : 'Yangi tarif'}</h3>
              <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600"><Ic d="M6 18L18 6M6 6l12 12" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1">Nomi *</label>
                <input value={form.name} onChange={e => setForm(p=>({...p,name:e.target.value}))} className={inp} placeholder="Boshlang'ich, Pro, Enterprise..." />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1">Tavsif</label>
                <input value={form.description} onChange={e => setForm(p=>({...p,description:e.target.value}))} className={inp} placeholder="Qisqacha tavsif..." />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">Narx (so'm/oy)</label>
                  <input type="number" value={form.price_per_month} onChange={e=>setForm(p=>({...p,price_per_month:Number(e.target.value)}))} className={inp} min="0" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">Muddat (kun)</label>
                  <input type="number" value={form.duration_days} onChange={e=>setForm(p=>({...p,duration_days:Number(e.target.value)}))} className={inp} min="1" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">Max xodim</label>
                  <input type="number" value={form.max_users} onChange={e=>setForm(p=>({...p,max_users:Number(e.target.value)}))} className={inp} min="1" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-500 mb-1">Max filial</label>
                  <input type="number" value={form.max_branches} onChange={e=>setForm(p=>({...p,max_branches:Number(e.target.value)}))} className={inp} min="1" />
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setShowForm(false)} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl text-sm transition-all">{t('common.cancel')}</button>
              <button onClick={save} disabled={saving} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl text-sm shadow-lg shadow-indigo-200 transition-all disabled:opacity-50">
                {saving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


