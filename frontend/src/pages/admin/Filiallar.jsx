import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';

const Ic = ({ d, cls = 'w-5 h-5' }) => (
  <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
  </svg>
);

const fmt = n => Number(n || 0).toLocaleString('ru-RU');

function BranchModal({ branch, warehouses, onSave, onClose }) {
  const isEdit = !!branch;
  const [form, setForm] = useState({
    name: branch?.name || '',
    address: branch?.address || '',
    phone: branch?.phone || '',
    is_active: branch?.is_active ?? true,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Filial nomi kiritilishi shart");
    setSaving(true);
    try {
      if (isEdit) {
        await api.patch(`/branches/${branch.id}`, form);
        toast.success("Filial yangilandi");
      } else {
        await api.post('/branches', form);
        toast.success("Filial qo'shildi");
      }
      onSave();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">
            {isEdit ? 'Filialni tahrirlash' : "Yangi filial qo'shish"}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">Filial nomi *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Masalan: Asosiy filial, Chilonzor bo'limi..."
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">Manzil</label>
            <input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })}
              placeholder="Ko'cha, uy raqami..."
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">Telefon</label>
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}
              placeholder="+998 90 123 45 67"
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          {isEdit && (
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${form.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${form.is_active ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
              <span className="text-sm font-semibold text-slate-700">{form.is_active ? 'Faol' : 'Nofaol'}</span>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50">
              Bekor qilish
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm disabled:opacity-50">
              {saving ? 'Saqlanmoqda...' : isEdit ? 'Yangilash' : "Qo'shish"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function WarehouseModal({ branches, editWh, onSave, onClose }) {
  const isEdit = !!editWh;
  const [form, setForm] = useState({
    name: editWh?.name || '',
    branch_id: editWh?.branch_id ?? '',
    type: editWh?.type || 'main',
    is_active: editWh?.is_active ?? true,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Ombor nomi kiritilishi shart");
    const payload = { ...form, branch_id: form.branch_id ? Number(form.branch_id) : null };
    setSaving(true);
    try {
      if (isEdit) {
        await api.patch(`/warehouses/${editWh.id}`, payload);
        toast.success("Ombor yangilandi");
      } else {
        await api.post('/warehouses', payload);
        toast.success("Ombor qo'shildi");
      }
      onSave();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  const WH_TYPES = [
    { value: 'main', label: 'Asosiy' },
    { value: 'shop', label: 'Do\'kon' },
    { value: 'transit', label: 'Tranzit' },
    { value: 'returns', label: 'Qaytarish' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">
            {isEdit ? 'Omborni tahrirlash' : "Yangi ombor qo'shish"}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">Ombor nomi *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Masalan: Asosiy sklad, Do'kon ombori..."
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">Filial *</label>
            <select value={form.branch_id} onChange={e => setForm({ ...form, branch_id: e.target.value })}
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white">
              <option value="">— Filialsiz (umumiy) —</option>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">Ombor turi</label>
            <div className="grid grid-cols-2 gap-2">
              {WH_TYPES.map(t => (
                <button key={t.value} type="button" onClick={() => setForm({ ...form, type: t.value })}
                  className={`py-2 rounded-xl text-sm font-semibold border-2 transition-all ${form.type === t.value ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-200 text-slate-600 hover:border-indigo-300'}`}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {isEdit && (
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${form.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${form.is_active ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
              <span className="text-sm font-semibold text-slate-700">{form.is_active ? 'Faol' : 'Nofaol'}</span>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50">
              Bekor qilish
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm disabled:opacity-50">
              {saving ? 'Saqlanmoqda...' : isEdit ? 'Yangilash' : "Qo'shish"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Filiallar() {
  const [branches, setBranches] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [branchModal, setBranchModal] = useState(null); // null | 'create' | branchObj
  const [whModal, setWhModal] = useState(null);         // null | 'create' | whObj
  const [expandedBranch, setExpandedBranch] = useState(null);
  const [stats, setStats] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [br, wh] = await Promise.all([
        api.get('/branches'),
        api.get('/warehouses'),
      ]);
      setBranches(br.data);
      setWarehouses(wh.data);

      // Per-branch stats from warehouse stock
      const statsMap = {};
      for (const b of br.data) {
        const bWhs = wh.data.filter(w => w.branch_id === b.id);
        statsMap[b.id] = { whCount: bWhs.length, whIds: bWhs.map(w => w.id) };
      }
      setStats(statsMap);
    } catch (e) {
      toast.error("Ma'lumotlarni yuklashda xatolik");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDeactivateBranch = async (b) => {
    if (!window.confirm(`"${b.name}" filialini nofaol qilmoqchimisiz?`)) return;
    try {
      await api.patch(`/branches/${b.id}`, { is_active: false });
      toast.success("Filial nofaol qilindi");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Xatolik");
    }
  };

  const unassignedWhs = warehouses.filter(w => !w.branch_id);

  const WH_TYPE_LABEL = { main: 'Asosiy', shop: "Do'kon", transit: 'Tranzit', returns: 'Qaytarish' };
  const WH_TYPE_COLOR = {
    main: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    shop: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    transit: 'bg-amber-50 text-amber-700 border-amber-200',
    returns: 'bg-rose-50 text-rose-700 border-rose-200',
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-black text-slate-800">Filiallar va Omborlar</h1>
          <p className="text-sm text-slate-500 mt-0.5">Har bir filialdagi omborlar va ularning bog'liqligini boshqaring</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setWhModal('create')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border-2 border-slate-200 text-slate-700 hover:border-indigo-300 font-semibold text-sm transition-all">
            <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4" />
            Ombor qo'shish
          </button>
          <button onClick={() => setBranchModal('create')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm shadow-md shadow-indigo-200 transition-all">
            <Ic d="M12 4v16m8-8H4" cls="w-4 h-4" />
            Filial qo'shish
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Jami filiallar', value: branches.filter(b => b.is_active).length, icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4', color: 'bg-indigo-50 text-indigo-700' },
          { label: 'Jami omborlar', value: warehouses.filter(w => w.is_active).length, icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4', color: 'bg-emerald-50 text-emerald-700' },
          { label: 'Bog\'liq omborlar', value: warehouses.filter(w => w.branch_id && w.is_active).length, icon: 'M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1', color: 'bg-amber-50 text-amber-700' },
          { label: "Bog'liqsiz omborlar", value: unassignedWhs.filter(w => w.is_active).length, icon: 'M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636', color: 'bg-rose-50 text-rose-700' },
        ].map(c => (
          <div key={c.label} className={`rounded-2xl p-4 border border-slate-100 ${c.color}`}>
            <div className="flex items-center gap-2 mb-1">
              <Ic d={c.icon} cls="w-4 h-4 opacity-70" />
              <span className="text-xs font-semibold opacity-70">{c.label}</span>
            </div>
            <p className="text-2xl font-black">{c.value}</p>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-20">
          <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-3">
          {/* Branch cards */}
          {branches.map(branch => {
            const bWhs = warehouses.filter(w => w.branch_id === branch.id);
            const isExpanded = expandedBranch === branch.id;
            return (
              <div key={branch.id} className={`bg-white rounded-2xl border-2 transition-all ${branch.is_active ? 'border-slate-100 hover:border-indigo-100' : 'border-slate-100 opacity-60'}`}>
                {/* Branch header */}
                <div className="flex items-center gap-3 p-4 cursor-pointer" onClick={() => setExpandedBranch(isExpanded ? null : branch.id)}>
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${branch.is_active ? 'bg-indigo-600' : 'bg-slate-300'}`}>
                    <Ic d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" cls="w-5 h-5 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-slate-800">{branch.name}</span>
                      {!branch.is_active && <span className="text-[10px] font-bold px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full">Nofaol</span>}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-500 flex-wrap">
                      {branch.address && <span>📍 {branch.address}</span>}
                      {branch.phone && <span>📞 {branch.phone}</span>}
                      <span className="font-semibold text-indigo-600">{bWhs.length} ta ombor</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={e => { e.stopPropagation(); setWhModal({ branchId: branch.id }); }}
                      className="p-2 rounded-xl text-indigo-500 hover:bg-indigo-50 transition-colors" title="Ombor qo'shish">
                      <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4" />
                    </button>
                    <button onClick={e => { e.stopPropagation(); setBranchModal(branch); }}
                      className="p-2 rounded-xl text-slate-400 hover:bg-slate-100 transition-colors" title="Tahrirlash">
                      <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-4 h-4" />
                    </button>
                    {branch.is_active && (
                      <button onClick={e => { e.stopPropagation(); handleDeactivateBranch(branch); }}
                        className="p-2 rounded-xl text-rose-400 hover:bg-rose-50 transition-colors" title="Nofaol qilish">
                        <Ic d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" cls="w-4 h-4" />
                      </button>
                    )}
                    <Ic d={isExpanded ? "M5 15l7-7 7 7" : "M19 9l-7 7-7-7"} cls="w-4 h-4 text-slate-400 ml-1" />
                  </div>
                </div>

                {/* Warehouses list */}
                {isExpanded && (
                  <div className="border-t border-slate-100 px-4 pb-4 pt-3">
                    {bWhs.length === 0 ? (
                      <div className="flex flex-col items-center py-6 text-slate-400 gap-2">
                        <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-8 h-8" />
                        <p className="text-sm">Bu filialda hali ombor yo'q</p>
                        <button onClick={() => setWhModal({ branchId: branch.id })}
                          className="text-sm font-bold text-indigo-600 hover:text-indigo-700">
                          + Ombor qo'shish
                        </button>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                        {bWhs.map(wh => (
                          <div key={wh.id} className={`flex items-center gap-3 p-3 rounded-xl border transition-all ${wh.is_active ? 'border-slate-100 bg-slate-50 hover:border-indigo-200' : 'border-slate-100 bg-slate-50 opacity-50'}`}>
                            <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center shrink-0">
                              <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4 text-slate-500" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-sm font-semibold text-slate-800 truncate">{wh.name}</span>
                                {wh.type && (
                                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${WH_TYPE_COLOR[wh.type] || 'bg-slate-100 text-slate-500'}`}>
                                    {WH_TYPE_LABEL[wh.type] || wh.type}
                                  </span>
                                )}
                              </div>
                              {!wh.is_active && <span className="text-[10px] text-slate-400">Nofaol</span>}
                            </div>
                            <button onClick={() => setWhModal(wh)}
                              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-200 transition-colors shrink-0">
                              <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {branches.length === 0 && (
            <div className="bg-white rounded-2xl border-2 border-dashed border-slate-200 p-12 text-center">
              <Ic d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" cls="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 font-semibold mb-1">Hali filial qo'shilmagan</p>
              <p className="text-sm text-slate-400 mb-4">Filial yaratib, unga omborlarni bog'lang</p>
              <button onClick={() => setBranchModal('create')}
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm">
                + Birinchi filial qo'shish
              </button>
            </div>
          )}

          {/* Unassigned warehouses */}
          {unassignedWhs.length > 0 && (
            <div className="bg-amber-50 border-2 border-amber-200 rounded-2xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <Ic d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" cls="w-5 h-5 text-amber-600" />
                <span className="font-bold text-amber-800">Filialsiz omborlar ({unassignedWhs.length} ta)</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {unassignedWhs.map(wh => (
                  <div key={wh.id} className="flex items-center gap-3 p-3 rounded-xl border border-amber-200 bg-white">
                    <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4 text-amber-600" />
                    <span className="flex-1 text-sm font-semibold text-slate-700 truncate">{wh.name}</span>
                    <button onClick={() => setWhModal(wh)}
                      className="text-xs font-bold text-indigo-600 hover:text-indigo-700 shrink-0">
                      Bog'lash →
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {branchModal && (
        <BranchModal
          branch={branchModal === 'create' ? null : branchModal}
          warehouses={warehouses}
          onSave={() => { setBranchModal(null); load(); }}
          onClose={() => setBranchModal(null)}
        />
      )}
      {whModal && (
        <WarehouseModal
          branches={branches}
          editWh={whModal === 'create' ? null : (typeof whModal === 'object' && whModal.branchId ? null : whModal)}
          onSave={() => { setWhModal(null); load(); }}
          onClose={() => setWhModal(null)}
        />
      )}
    </div>
  );
}
