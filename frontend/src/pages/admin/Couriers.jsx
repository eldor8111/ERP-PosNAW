import { useState, useEffect } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { Truck, Plus, X, Phone, Pencil, Power } from 'lucide-react';

const TRANSPORTS = ['Piyoda', 'Velosiped', 'Moto', 'Avto'];

export default function Couriers() {
  const [couriers, setCouriers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  const [modal, setModal] = useState(null); // null | {mode:'add'} | {mode:'edit', courier}
  const [form, setForm] = useState({ name: '', phone: '', transport: '' });
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api.get('/couriers', { params: { include_inactive: showInactive } })
      .then(r => setCouriers(r.data || []))
      .catch(e => toast.error(e.response?.data?.detail || 'Yuklashda xatolik'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [showInactive]); // eslint-disable-line react-hooks/exhaustive-deps

  const openAdd = () => { setForm({ name: '', phone: '', transport: '' }); setModal({ mode: 'add' }); };
  const openEdit = (c) => { setForm({ name: c.name, phone: c.phone, transport: c.transport || '' }); setModal({ mode: 'edit', courier: c }); };

  const save = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.phone.trim()) { toast.error('Ism va telefon majburiy'); return; }
    setSaving(true);
    try {
      if (modal.mode === 'add') {
        await api.post('/couriers', { name: form.name, phone: form.phone, transport: form.transport || null });
        toast.success('Dostavchik qo\'shildi');
      } else {
        await api.put(`/couriers/${modal.courier.id}`, { name: form.name, phone: form.phone, transport: form.transport || null });
        toast.success('Saqlandi');
      }
      setModal(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (c) => {
    try {
      await api.put(`/couriers/${c.id}`, { is_active: !c.is_active });
      toast.success(c.is_active ? 'Nofaol qilindi' : 'Faollashtirildi');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Xatolik');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <label className="flex items-center gap-2 text-xs font-medium text-slate-500 cursor-pointer select-none">
          <input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)}
            className="w-4 h-4 rounded border-slate-300" />
          Nofaollarni ham ko'rsatish
        </label>
        <button onClick={openAdd}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl transition-colors">
          <Plus className="w-4 h-4" /> Dostavchik qo'shish
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
        </div>
      ) : couriers.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-16 text-slate-400 bg-white rounded-2xl border border-slate-100">
          <Truck className="w-10 h-10" />
          <p className="text-sm">Hozircha dostavchik yo'q</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {couriers.map(c => (
            <div key={c.id} className={`bg-white border rounded-2xl p-4 ${c.is_active ? 'border-slate-100' : 'border-slate-100 opacity-60'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-800 truncate">{c.name}</p>
                    {!c.is_active && <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-semibold">Nofaol</span>}
                    {c.tg_connected && <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 font-semibold">TG ✓</span>}
                  </div>
                  <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-0.5">
                    <Phone className="w-3 h-3" /> {c.phone}
                  </a>
                  {c.transport && <p className="text-[11px] text-slate-400 mt-0.5">🛵 {c.transport}</p>}
                </div>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => openEdit(c)} title="Tahrirlash"
                    className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-500">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => toggleActive(c)} title={c.is_active ? 'Nofaol qilish' : 'Faollashtirish'}
                    className={`w-8 h-8 flex items-center justify-center rounded-lg ${c.is_active ? 'bg-red-50 hover:bg-red-100 text-red-500' : 'bg-green-50 hover:bg-green-100 text-green-600'}`}>
                    <Power className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex gap-4 mt-3 pt-3 border-t border-slate-50">
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-semibold">Faol buyurtma</p>
                  <p className="text-sm font-bold text-slate-700">{c.active_orders ?? 0}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-semibold">Bugun yetkazdi</p>
                  <p className="text-sm font-bold text-green-600">{c.delivered_today ?? 0}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => !saving && setModal(null)} />
          <form onSubmit={save} className="relative w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-800">
                {modal.mode === 'add' ? "Dostavchik qo'shish" : 'Tahrirlash'}
              </h3>
              <button type="button" onClick={() => !saving && setModal(null)}
                className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 block mb-1">Ism *</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full h-10 px-3 border border-slate-200 rounded-xl text-sm focus:border-blue-500 outline-none" />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 block mb-1">Telefon *</label>
              <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                placeholder="+998 90 123 45 67" inputMode="tel"
                className="w-full h-10 px-3 border border-slate-200 rounded-xl text-sm focus:border-blue-500 outline-none" />
              <p className="text-[10px] text-slate-400 mt-1">Kuryer botda shu raqam bilan ro'yxatdan o'tadi</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 block mb-1">Transport</label>
              <select value={form.transport} onChange={e => setForm(f => ({ ...f, transport: e.target.value }))}
                className="w-full h-10 px-3 border border-slate-200 rounded-xl text-sm bg-white focus:border-blue-500 outline-none">
                <option value="">Tanlanmagan</option>
                {TRANSPORTS.map(tr => <option key={tr} value={tr}>{tr}</option>)}
              </select>
            </div>
            <button type="submit" disabled={saving}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-xl font-semibold text-sm transition-colors">
              {saving ? 'Saqlanmoqda...' : 'Saqlash'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
