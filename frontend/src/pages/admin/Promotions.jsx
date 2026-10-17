import React, { useState, useEffect } from 'react';
import api from '../../api/axios';
import { Tag, Percent, Hash, Calendar, Trash2, Pencil, Plus, X, Package, Search, Building2 } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useAuth } from '../../context/AuthContext';

function formatDate(dt) {
  if (!dt) return '—';
  return new Date(dt).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function PromoModal({ promo, branches, onClose, onSaved }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const isEdit = !!promo;
  const [form, setForm] = useState({
    name: promo?.name || '',
    discount_type: promo?.discount_type || 'percent',
    discount_value: promo?.discount_value || '',
    start_date: promo?.start_date ? promo.start_date.slice(0, 10) : '',
    end_date: promo?.end_date ? promo.end_date.slice(0, 10) : '',
    // Qamrov: eski javobda (applies_to yo'q) mahsulot bo'lsa "products", aks holda "all"
    applies_to: promo?.applies_to || (promo?.products?.length ? 'products' : 'all'),
  });
  // Tanlangan mahsulotlar [{ id, name }] — tahrirda promo.products dan oldindan yuklanadi
  const [picked, setPicked] = useState(
    (promo?.products || []).map(pp => ({ id: pp.product_id, name: pp.product_name || `#${pp.product_id}` }))
  );
  // T4.3: filiallar — bo'sh = hamma filial
  const [branchIds, setBranchIds] = useState(Array.isArray(promo?.branch_ids) ? promo.branch_ids : []);
  const toggleBranch = (id) => setBranchIds(list => (list.includes(id) ? list.filter(x => x !== id) : [...list, id]));
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  // Mahsulot qidirish (nomi / SKU / shtrix-kod bo'yicha), kechiktirilgan so'rov
  useEffect(() => {
    if (form.applies_to !== 'products') return undefined;
    const q = query.trim();
    if (q.length < 2) { setResults([]); return undefined; }
    let cancelled = false;
    const timer = setTimeout(() => {
      setSearching(true);
      api.get('/products/', { params: { search: q, limit: 15, status: 'active' }, _silent: true, _suppressToast: true })
        .then(r => { if (!cancelled) setResults(Array.isArray(r.data) ? r.data : (r.data?.items || [])); })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setSearching(false); });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, form.applies_to]);

  const addProduct = (p) => {
    setPicked(list => (list.some(x => x.id === p.id) ? list : [...list, { id: p.id, name: p.name }]));
    setQuery(''); setResults([]);
  };
  const removeProduct = (id) => setPicked(list => list.filter(x => x.id !== id));

  const save = async () => {
    if (!form.name.trim() || !form.discount_value) { setErr(t('promotion.nameAndDiscountRequired')); return; }
    const value = parseFloat(form.discount_value);
    if (!(value > 0)) { setErr(tf('promotion.valuePositive', "Chegirma qiymati 0 dan katta bo'lishi kerak")); return; }
    if (form.discount_type === 'percent' && value > 100) { setErr(tf('promotion.percentMax', 'Foiz chegirma 100 dan oshmasligi kerak')); return; }
    if (form.start_date && form.end_date && form.end_date < form.start_date) {
      setErr(tf('promotion.dateOrder', "Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas")); return;
    }
    if (form.applies_to === 'products' && picked.length === 0) {
      setErr(tf('promotion.pickAtLeastOne', 'Kamida bitta mahsulot tanlang')); return;
    }
    setSaving(true); setErr('');
    try {
      const payload = {
        name: form.name.trim(),
        discount_type: form.discount_type,
        discount_value: value,
        // Bo'sh sana '' emas, aniq null yuboriladi (422 bo'lmasligi va tahrirda tozalash uchun)
        start_date: form.start_date ? form.start_date + 'T00:00:00' : null,
        end_date: form.end_date ? form.end_date + 'T23:59:59' : null,
        applies_to: form.applies_to,
        products: form.applies_to === 'products' ? picked.map(p => ({ product_id: p.id })) : [],
        branch_ids: branchIds,
      };
      if (isEdit) await api.put(`/promotions/${promo.id}`, payload);
      else await api.post('/promotions', payload);
      onSaved();
    } catch(e) {
      const d = e?.response?.data?.detail;
      setErr((typeof d === 'string' && d) || (Array.isArray(d) && d[0]?.msg) || t('promotion.genericError'));
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold text-slate-800">{isEdit ? t('promotion.editPromo') : t('promotion.newPromo')}</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">{t('promotion.promoName')} *</label>
            <input
              className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder={t('promotion.promoNamePlaceholder')}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">{t('promotion.discountType')}</label>
              <select
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.discount_type} onChange={e => setForm(f => ({ ...f, discount_type: e.target.value }))}
              >
                <option value="percent">{t('promotion.percentOption')}</option>
                <option value="amount">{t('promotion.amountOption')}</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">
                {t('promotion.discountValue')} {form.discount_type === 'percent' ? '(%)' : `(${t('common.sum')})`} *
              </label>
              <input
                type="number" min="0" max={form.discount_type === 'percent' ? 100 : undefined}
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.discount_value} onChange={e => setForm(f => ({ ...f, discount_value: e.target.value }))}
                placeholder={form.discount_type === 'percent' ? '10' : '5000'}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">{t('promotion.startDate')}</label>
              <input type="date"
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">{t('promotion.endDate')}</label>
              <input type="date"
                className="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
              />
            </div>
          </div>

          {/* Qamrov: barcha mahsulotlar yoki tanlanganlar */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">{tf('promotion.scope', 'Qamrov')}</label>
            <div className="flex gap-4 text-sm text-slate-700">
              {[['all', tf('promotion.appliesAll', 'Barcha mahsulotlar')], ['products', tf('promotion.appliesProducts', 'Tanlangan mahsulotlar')]].map(([val, label]) => (
                <label key={val} className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="promo-scope" checked={form.applies_to === val}
                    onChange={() => setForm(f => ({ ...f, applies_to: val }))} />
                  {label}
                </label>
              ))}
            </div>
          </div>

          {/* T4.3: filiallar — hech biri tanlanmasa hamma filialda amal qiladi */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">{tf('promotion.branches', 'Filiallar')}</label>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setBranchIds([])}
                className={`px-3 py-1 rounded-full text-xs font-medium border ${branchIds.length === 0 ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200'}`}>
                {tf('promotion.allBranches', 'Barcha filiallar')}
              </button>
              {(branches || []).map(b => (
                <button type="button" key={b.id} onClick={() => toggleBranch(b.id)}
                  className={`px-3 py-1 rounded-full text-xs font-medium border ${branchIds.includes(b.id) ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200'}`}>
                  {b.name}
                </button>
              ))}
            </div>
          </div>

          {form.applies_to === 'products' && (
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">{tf('promotion.pickProducts', 'Mahsulotlarni tanlang')} *</label>
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={query} onChange={e => setQuery(e.target.value)}
                  placeholder={tf('promotion.searchProduct', 'Nomi, SKU yoki shtrix-kod')}
                />
                {(results.length > 0 || searching) && (
                  <div className="absolute left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-48 overflow-y-auto z-10">
                    {searching && <div className="px-3 py-2 text-xs text-slate-400">...</div>}
                    {results.map(p => (
                      <button type="button" key={p.id} onClick={() => addProduct(p)}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 flex justify-between gap-2">
                        <span className="truncate">{p.name}</span>
                        <span className="text-xs text-slate-400 shrink-0">{p.sku}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {picked.length === 0 && (
                  <span className="text-xs text-slate-400">{tf('promotion.noneSelected', 'Mahsulot tanlanmagan')}</span>
                )}
                {picked.map(p => (
                  <span key={p.id} className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-full">
                    {p.name}
                    <button type="button" onClick={() => removeProduct(p.id)} className="hover:text-red-600"><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            </div>
          )}

          {err && <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">{err}</div>}
        </div>

        <div className="flex gap-3 mt-6">
          <button onClick={onClose} className="flex-1 py-2.5 text-sm font-semibold text-slate-600 bg-slate-100 rounded-xl hover:bg-slate-200">
            {t('common.cancel')}
          </button>
          <button onClick={save} disabled={saving} className="flex-1 py-2.5 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-50">
            {saving ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Promotions() {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const [promos, setPromos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // null | 'create' | promotion object
  const { user: authUser } = useAuth();
  const [branches, setBranches] = useState([]);
  // T4.3: aksiyani serverda avtomatik qo'llash (korxona sozlamasi; faqat admin/director o'zgartiradi)
  const [autoApply, setAutoApply] = useState(false);
  const canSetAuto = ['admin', 'director', 'super_admin'].includes(authUser?.role);

  useEffect(() => {
    api.get('/branches', { _suppressToast: true }).then(r => setBranches(Array.isArray(r.data) ? r.data : [])).catch(() => setBranches([]));
    api.get('/promotions/settings', { _suppressToast: true }).then(r => setAutoApply(!!r.data?.auto_apply)).catch(() => {});
  }, []);

  const toggleAutoApply = async () => {
    const next = !autoApply;
    try {
      const r = await api.put('/promotions/settings', { auto_apply: next });
      setAutoApply(!!r.data?.auto_apply);
    } catch (e) { alert(e?.response?.data?.detail || t('promotion.genericError')); }
  };

  const load = () => {
    setLoading(true);
    api.get('/promotions').then(r => setPromos(r.data || [])).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const deletePromo = async (id) => {
    if (!window.confirm(t('promotion.confirmDelete'))) return;
    try { await api.delete(`/promotions/${id}`); load(); }
    catch(e) { alert(e?.response?.data?.detail || t('promotion.deleteFailed')); }
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
    if (s === 'active') return <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-xs font-semibold rounded-full">{t('common.active')}</span>;
    if (s === 'upcoming') return <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-semibold rounded-full">{t('promotion.upcoming')}</span>;
    return <span className="px-2 py-0.5 bg-slate-100 text-slate-500 text-xs font-semibold rounded-full">{t('promotion.expired')}</span>;
  };

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('promotion.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('promotion.subtitle')}</p>
        </div>
        <button
          onClick={() => setModal('create')}
          className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          {t('promotion.newPromo')}
        </button>
      </div>

      {/* T4.3: serverda avtomatik qo'llash */}
      <label className={`flex items-center gap-3 mb-4 p-3 bg-white rounded-xl border border-slate-200 text-sm ${canSetAuto ? 'cursor-pointer' : 'opacity-70'}`}>
        <input type="checkbox" checked={autoApply} disabled={!canSetAuto} onChange={toggleAutoApply} />
        <span>
          <span className="font-semibold text-slate-700">{tf('promotion.autoApply', "Aksiyalarni avtomatik qo'llash")}</span>
          <span className="block text-xs text-slate-500">{tf('promotion.autoApplyHint', "Yoqilsa, server sotuvda eng katta chegirmali mos aksiyani o'zi qo'llaydi")}</span>
        </span>
      </label>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: t('promotion.totalPromos'), value: promos.length, color: 'blue', icon: Tag },
          { label: t('promotion.activePromos'), value: promos.filter(p => isActive(p) === 'active').length, color: 'emerald', icon: Percent },
          { label: t('promotion.upcoming'), value: promos.filter(p => isActive(p) === 'upcoming').length, color: 'amber', icon: Calendar },
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
          <p className="font-semibold text-slate-600">{t('promotion.noPromos')}</p>
          <p className="text-sm mt-1">{t('promotion.createFirstPromo')}</p>
          <button onClick={() => setModal('create')} className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700">
            + {t('promotion.newPromo')}
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
                    {t('common.discount')}: <span className="font-medium text-slate-700">
                      {p.discount_value}{p.discount_type === 'percent' ? '%' : ` ${t('common.sum')}`}
                    </span>
                    {(p.start_date || p.end_date) && (
                      <span className="ml-3">
                        <Calendar className="w-3.5 h-3.5 inline mr-1 opacity-60" />
                        {formatDate(p.start_date)} – {formatDate(p.end_date)}
                      </span>
                    )}
                    <span className="ml-3">
                      <Building2 className="w-3.5 h-3.5 inline mr-1 opacity-60" />
                      {(p.branch_ids || []).length === 0
                        ? tf('promotion.allBranches', 'Barcha filiallar')
                        : (p.branch_ids || []).map(id => branches.find(b => b.id === id)?.name || `#${id}`).join(', ')}
                    </span>
                    {(p.applies_to === 'all' || (!p.applies_to && !(p.products?.length > 0))) ? (
                      <span className="ml-3">
                        <Package className="w-3.5 h-3.5 inline mr-1 opacity-60" />
                        {tf('promotion.appliesAll', 'Barcha mahsulotlar')}
                      </span>
                    ) : (
                      <span className="ml-3">
                        <Package className="w-3.5 h-3.5 inline mr-1 opacity-60" />
                        {p.products?.length || 0} {t('promotion.productsCount')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setModal(p)}
                  className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  title={t('common.edit')}
                >
                  <Pencil className="w-4 h-4" />
                </button>
                <button
                  onClick={() => deletePromo(p.id)}
                  className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title={t('common.delete')}
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
          branches={branches}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(); }}
        />
      )}
    </div>
  );
}
