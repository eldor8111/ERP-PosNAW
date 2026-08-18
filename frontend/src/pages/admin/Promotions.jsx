import React, { useState, useEffect } from 'react';
import api from '../../api/axios';
import { Tag, Percent, Hash, Calendar, Trash2, Pencil, Plus, X, Package } from 'lucide-react';

function formatDate(dt) {
  if (!dt) return '—';
  return new Date(dt).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function PromoModal({ promo, onClose, onSaved }) {
  const isEdit = !!promo;
  const [form, setForm] = useState({
    name: promo?.name || '',
    discount_type: promo?.discount_type || 'percent',
    discount_value: promo?.discount_value || '',
    start_date: promo?.start_date ? promo.start_date.slice(0, 10) : '',
    end_date: promo?.end_date ? promo.end_date.slice(0, 10) : '',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const save = async () => {
    if (!form.name.trim() || !form.discount_value) { setErr('Nom va chegirma kiritilishi shart'); return; }
    setSaving(true); setErr('');
    try {
      const payload = { ...form, discount_value: parseFloat(form.discount_value) };
      if (isEdit) await api.put(`/promotions/${promo.id}`, payload);
      else await api.post('/promotions', payload);
      onSaved();
    } catch(e) {
      setErr(e?.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold text-slate-800">{isEdit ? 'Aksiyani tahrirlash' : 'Yangi aksiya'}</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Aksiya nomi *</label>
            <input
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Masalan: Yozgi chegirma"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Chegirma turi</label>
              <select
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.discount_type} onChange={e => setForm(f => ({ ...f, discount_type: e.target.value }))}
              >
                <option value="percent">Foiz (%)</option>
                <option value="amount">Summa (so'm)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                Chegirma miqdori {form.discount_type === 'percent' ? '(%)' : '(so\'m)'} *
              </label>
              <input
                type="number" min="0"
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.discount_value} onChange={e => setForm(f => ({ ...f, discount_value: e.target.value }))}
                placeholder={form.discount_type === 'percent' ? '10' : '5000'}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Boshlanish sanasi</label>
              <input type="date"
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Tugash sanasi</label>
              <input type="date"
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
              />
            </div>
          </div>

          {err && <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">{err}</div>}
        </div>

        <div className="flex gap-3 mt-6">
          <button onClick={onClose} className="flex-1 py-2.5 text-sm font-semibold text-slate-600 bg-slate-100 rounded-xl hover:bg-slate-200">
            Bekor qilish
          </button>
          <button onClick={save} disabled={saving} className="flex-1 py-2.5 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Saqlanmoqda...' : 'Saqlash'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Promotions() {
  const [promos, setPromos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // null | 'create' | promotion object

  const load = () => {
    setLoading(true);
    api.get('/promotions').then(r => setPromos(r.data || [])).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const deletePromo = async (id) => {
    if (!window.confirm('Aksiyani o\'chirishni tasdiqlaysizmi?')) return;
    try { await api.delete(`/promotions/${id}`); load(); }
    catch(e) { alert(e?.response?.data?.detail || 'O\'chirib bo\'lmadi'); }
  };

  const isActive = (p) => {
    const now = new Date();
    const start = p.start_date ? new Date(p.start_date) : null;
    const end = p.end_date ? new Date(p.end_date) : null;
    if (start && now < start) return 'upcoming';
    if (end && now > end) return 'expired';
    return 'active';
  };

  const statusBadge = (p) => {
    const s = isActive(p);
    if (s === 'active') return <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-xs font-semibold rounded-full">Faol</span>;
    if (s === 'upcoming') return <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-semibold rounded-full">Kutilmoqda</span>;
    return <span className="px-2 py-0.5 bg-slate-100 text-slate-500 text-xs font-semibold rounded-full">Tugagan</span>;
  };

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Aksiyalar</h1>
          <p className="text-sm text-slate-500 mt-0.5">Chegirma va aksiyalarni boshqarish</p>
        </div>
        <button
          onClick={() => setModal('create')}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          Yangi aksiya
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: 'Jami aksiyalar', value: promos.length, color: 'blue', icon: Tag },
          { label: 'Faol aksiyalar', value: promos.filter(p => isActive(p) === 'active').length, color: 'emerald', icon: Percent },
          { label: 'Kutilmoqda', value: promos.filter(p => isActive(p) === 'upcoming').length, color: 'amber', icon: Calendar },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className={`p-4 bg-${color}-50 rounded-xl border border-${color}-100`}>
            <div className="flex items-center gap-2 mb-2">
              <Icon className={`w-4 h-4 text-${color}-600`} />
              <span className={`text-sm font-medium text-${color}-700`}>{label}</span>
            </div>
            <div className={`text-2xl font-bold text-${color}-700`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : promos.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <Tag className="w-12 h-12 mb-3 opacity-30" />
          <p className="font-semibold text-slate-600">Aksiyalar yo'q</p>
          <p className="text-sm mt-1">Birinchi aksiyani yarating</p>
          <button onClick={() => setModal('create')} className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700">
            + Yangi aksiya
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {promos.map(p => (
            <div key={p.id} className="flex items-center justify-between p-4 bg-white rounded-xl border border-slate-200 hover:border-blue-200 hover:shadow-sm transition-all">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
                  {p.discount_type === 'percent'
                    ? <Percent className="w-5 h-5 text-white" />
                    : <Hash className="w-5 h-5 text-white" />}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-800">{p.name}</span>
                    {statusBadge(p)}
                  </div>
                  <div className="text-sm text-slate-500 mt-0.5">
                    Chegirma: <span className="font-medium text-slate-700">
                      {p.discount_value}{p.discount_type === 'percent' ? '%' : ' so\'m'}
                    </span>
                    {(p.start_date || p.end_date) && (
                      <span className="ml-3">
                        <Calendar className="w-3.5 h-3.5 inline mr-1 opacity-60" />
                        {formatDate(p.start_date)} – {formatDate(p.end_date)}
                      </span>
                    )}
                    {p.products?.length > 0 && (
                      <span className="ml-3">
                        <Package className="w-3.5 h-3.5 inline mr-1 opacity-60" />
                        {p.products.length} ta mahsulot
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setModal(p)}
                  className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  title="Tahrirlash"
                >
                  <Pencil className="w-4 h-4" />
                </button>
                <button
                  onClick={() => deletePromo(p.id)}
                  className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title="O'chirish"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {modal && (
        <PromoModal
          promo={modal === 'create' ? null : modal}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(); }}
        />
      )}
    </div>
  );
}
