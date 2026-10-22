import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { useLang } from '../../context/LangContext';
import { useBranch } from '../../context/BranchContext';
import { useBranches, invalidateBranches } from '../../hooks/useBranches';
import { WAREHOUSE_TYPES, WAREHOUSE_TYPE_BY_VALUE } from '../../constants/warehouseTypes';

const Ic = ({ d, cls = 'w-5 h-5' }) => (
  <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
  </svg>
);

const fmt = n => Number(n || 0).toLocaleString('ru-RU');

// T4.2: filial rekvizitlari (Settings.jsx > Fiskal tabdagi BranchRequisitesSection bilan bir xil maydonlar/endpoint)
const BRANCH_WEEK_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const BRANCH_DAY_FALLBACK = { mon: 'Dushanba', tue: 'Seshanba', wed: 'Chorshanba', thu: 'Payshanba', fri: 'Juma', sat: 'Shanba', sun: 'Yakshanba' };
const defaultHours = () => Object.fromEntries(BRANCH_WEEK_DAYS.map(d => [d, { open: '09:00', close: '18:00', closed: d === 'sun' }]));

function BranchModal({ branch, onSave, onClose }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const isEdit = !!branch;
  const [form, setForm] = useState({
    name: branch?.name || '',
    address: branch?.address || '',
    phone: branch?.phone || '',
    is_active: branch?.is_active ?? true,
  });
  // T4.2: rekvizitlar (bo'sh qoldirilsa chekda korxona shablonidan olinadi)
  const [req, setReq] = useState({
    code: branch?.code || '',
    legal_name: branch?.legal_name || '',
    stir: branch?.stir || '',
    tax_regime: branch?.tax_regime || '',
  });
  const [useHours, setUseHours] = useState(!!branch?.working_hours);
  const [hours, setHours] = useState({ ...defaultHours(), ...(branch?.working_hours || {}) });
  const updDay = (d, k, v) => setHours(h => ({ ...h, [d]: { ...h[d], [k]: v } }));
  // T1.4: yangi filial bilan birga ombor va kassa yaratish (standart yoqilgan)
  const [provision, setProvision] = useState({ create_warehouse: true, create_wallet: true });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error(t('branch.nameRequired'));
    const stir = req.stir.trim();
    if (stir && !/^(\d{9}|\d{14})$/.test(stir)) {
      return toast.error(tf('branchSettings.stirInvalid', "STIR 9 xonali (JSHSHIR 14 xonali) raqam bo'lishi kerak"));
    }
    const body = {
      ...form,
      code: req.code.trim() || null,
      legal_name: req.legal_name.trim() || null,
      stir: stir || null,
      tax_regime: req.tax_regime || null,
      working_hours: useHours ? hours : null,
    };
    setSaving(true);
    try {
      if (isEdit) {
        await api.patch(`/branches/${branch.id}`, body, { _suppressToast: true });
        toast.success(t('branch.updated'));
      } else {
        await api.post('/branches', { ...body, ...provision }, { _suppressToast: true });
        toast.success(t('branch.added'));
      }
      onSave();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('branch.errorOccurred'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">
            {isEdit ? t('branch.editBranch') : t('branch.addBranch')}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('branch.branchName')} *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder={t('branch.branchNamePlaceholder')}
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('common.address')}</label>
            <input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })}
              placeholder={t('branch.addressPlaceholder')}
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('common.phone')}</label>
            <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}
              placeholder="+998 90 123 45 67"
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          {/* T4.2: rekvizitlar */}
          <div className="rounded-xl border border-slate-200 p-3 space-y-3">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wide">{tf('branchSettings.title', 'Filial rekvizitlari')}</div>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-xs text-slate-500">{tf('branchSettings.code', 'Filial kodi')}
                <input maxLength={20} value={req.code} onChange={e => setReq(r => ({ ...r, code: e.target.value }))}
                  className="w-full border border-slate-200 rounded-xl px-2 py-1.5 text-xs bg-white" />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-500">{tf('branchSettings.stir', 'STIR / JSHSHIR')}
                <input maxLength={14} inputMode="numeric" value={req.stir}
                  onChange={e => setReq(r => ({ ...r, stir: e.target.value.replace(/\D/g, '') }))}
                  className="w-full border border-slate-200 rounded-xl px-2 py-1.5 text-xs bg-white" />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-500 col-span-2">{tf('branchSettings.legalName', 'Yuridik nom')}
                <input maxLength={200} value={req.legal_name} onChange={e => setReq(r => ({ ...r, legal_name: e.target.value }))}
                  className="w-full border border-slate-200 rounded-xl px-2 py-1.5 text-xs bg-white" />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-500 col-span-2">{tf('branchSettings.taxRegime', 'Soliq rejimi')}
                <select value={req.tax_regime} onChange={e => setReq(r => ({ ...r, tax_regime: e.target.value }))}
                  className="w-full border border-slate-200 rounded-xl px-2 py-1.5 text-xs bg-white">
                  <option value="">{tf('branchSettings.regimeNone', 'Belgilanmagan')}</option>
                  <option value="vat">{tf('branchSettings.regimeVat', "QQS to'lovchi")}</option>
                  <option value="turnover">{tf('branchSettings.regimeTurnover', 'Aylanma soliq')}</option>
                </select>
              </label>
            </div>
            <div>
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                <input type="checkbox" checked={useHours} onChange={e => setUseHours(e.target.checked)} />
                {tf('branchSettings.hours', 'Ish vaqti')}
              </label>
              {useHours && (
                <div className="mt-2 space-y-1">
                  {BRANCH_WEEK_DAYS.map(d => (
                    <div key={d} className="flex items-center gap-2 text-xs">
                      <span className="w-20 text-slate-600">{tf(`branchSettings.day.${d}`, BRANCH_DAY_FALLBACK[d])}</span>
                      <label className="flex items-center gap-1 text-slate-500">
                        <input type="checkbox" checked={!!hours[d].closed} onChange={e => updDay(d, 'closed', e.target.checked)} />
                        {tf('branchSettings.closed', 'Yopiq')}
                      </label>
                      <input type="time" disabled={hours[d].closed} value={hours[d].open || ''} onChange={e => updDay(d, 'open', e.target.value)} className="border border-slate-200 rounded-lg px-1 py-0.5 disabled:opacity-40" />
                      <span>–</span>
                      <input type="time" disabled={hours[d].closed} value={hours[d].close || ''} onChange={e => updDay(d, 'close', e.target.value)} className="border border-slate-200 rounded-lg px-1 py-0.5 disabled:opacity-40" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          {isEdit && (
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${form.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${form.is_active ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
              <span className="text-sm font-semibold text-slate-700">{form.is_active ? t('common.active') : t('common.inactive')}</span>
            </div>
          )}
          {!isEdit && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2">
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 cursor-pointer">
                <input type="checkbox" checked={provision.create_warehouse}
                  onChange={e => setProvision(p => ({ ...p, create_warehouse: e.target.checked }))} />
                {t('branch.createWarehouse')}
              </label>
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 cursor-pointer">
                <input type="checkbox" checked={provision.create_wallet}
                  onChange={e => setProvision(p => ({ ...p, create_wallet: e.target.checked }))} />
                {t('branch.createWallet')}
              </label>
              <p className="text-xs text-slate-400">{t('branch.provisionHint')}</p>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50">
              {t('common.cancel')}
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm disabled:opacity-50">
              {saving ? t('common.saving') : isEdit ? t('common.update') : t('common.add')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function WarehouseModal({ branches, editWh, defaultBranchId, onSave, onClose }) {
  const { t } = useLang();
  const isEdit = !!editWh;
  const [form, setForm] = useState({
    name: editWh?.name || '',
    branch_id: editWh?.branch_id ?? defaultBranchId ?? '',
    type: editWh?.type || 'main',
    is_active: editWh?.is_active ?? true,
    is_default: editWh?.is_default ?? false,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error(t('branch.warehouseNameRequired'));
    const payload = { ...form, branch_id: form.branch_id ? Number(form.branch_id) : null };
    // Filialsiz omborni asosiy qilib bo'lmaydi; asosiy ombor belgisi faqat yoqilganda yuboriladi
    if (!payload.branch_id) delete payload.is_default;
    else if (isEdit && editWh.is_default && !payload.is_default) delete payload.is_default;
    setSaving(true);
    try {
      if (isEdit) {
        const res = await api.patch(`/warehouses/${editWh.id}`, payload, { _suppressToast: true });
        // T1.4: javobdagi filial yuborilgan qiymatga mos kelmasa, jimgina "yangilandi" demaymiz
        if ((res?.data?.branch_id ?? null) !== payload.branch_id) {
          toast.error(t('branch.warehouseBranchNotSaved'));
          return;
        }
        toast.success(t('branch.warehouseUpdated'));
      } else {
        await api.post('/warehouses', payload, { _suppressToast: true });
        toast.success(t('branch.warehouseAdded'));
      }
      onSave();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('branch.errorOccurred'));
    } finally {
      setSaving(false);
    }
  };

  // T3.1: 6 ta tur — umumiy constants/warehouseTypes.js dan
  const WH_TYPES = WAREHOUSE_TYPES.map(wt => ({ value: wt.value, label: t(wt.labelKey) }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">
            {isEdit ? t('branch.editWarehouse') : t('branch.addWarehouse')}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <Ic d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('branch.warehouseName')} *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder={t('branch.warehouseNamePlaceholder')}
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('branch.title')}</label>
            <select value={form.branch_id} onChange={e => setForm({ ...form, branch_id: e.target.value })}
              className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white">
              <option value="">{t('branch.noBranchGeneral')}</option>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('branch.warehouseType')}</label>
            <div className="grid grid-cols-2 gap-2">
              {WH_TYPES.map(wt => (
                <button key={wt.value} type="button" onClick={() => setForm({ ...form, type: wt.value })}
                  className={`py-2 rounded-xl text-sm font-semibold border-2 transition-all ${form.type === wt.value ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-200 text-slate-600 hover:border-blue-300'}`}>
                  {wt.label}
                </button>
              ))}
            </div>
          </div>
          {form.branch_id && (
            <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 cursor-pointer">
              <input type="checkbox" checked={!!form.is_default}
                disabled={isEdit && !!editWh.is_default}
                onChange={e => setForm({ ...form, is_default: e.target.checked })} />
              {t('branch.setDefaultWarehouse')}
            </label>
          )}
          {isEdit && (
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${form.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}>
                <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${form.is_active ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
              <span className="text-sm font-semibold text-slate-700">{form.is_active ? t('common.active') : t('common.inactive')}</span>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50">
              {t('common.cancel')}
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm disabled:opacity-50">
              {saving ? t('common.saving') : isEdit ? t('common.update') : t('common.add')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// T4.5: mijoz / xodim / ombor / kassalarni ommaviy boshqa filialga ko'chirish (POST /branches/reassign)
const REASSIGN_ENTITIES = [
  { key: 'customers', labelKey: 'branch.reassignCustomers' },
  { key: 'users', labelKey: 'branch.reassignUsers' },
  { key: 'warehouses', labelKey: 'branch.reassignWarehouses' },
  { key: 'wallets', labelKey: 'branch.reassignWallets' },
];

function ReassignModal({ branches, warehouses, onDone, onClose }) {
  const { t } = useLang();
  const [entity, setEntity] = useState('customers');
  const [fromBranch, setFromBranch] = useState('');       // '' = barchasi, 'none' = filialsiz
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [toBranch, setToBranch] = useState('');           // '' = tanlanmagan, 'none' = filialdan ajratish (faqat ombor)
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let alive = true;
    setSelected(new Set()); setResult(null); setToBranch('');
    if (entity === 'warehouses') {
      setItems(warehouses.filter(w => w.is_active !== false).map(w => ({ id: w.id, name: w.name, branch_id: w.branch_id })));
      return () => { alive = false; };
    }
    const req = entity === 'customers' ? api.get('/customers', { params: { limit: 5000 }, _silent: true })
      : entity === 'users' ? api.get('/users/', { _silent: true })
      : api.get('/kassa', { _silent: true });
    setLoading(true);
    req.then(r => {
      if (!alive) return;
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setItems(list.filter(x => x.is_personal !== true).map(x => ({ id: x.id, name: x.name || x.full_name || x.phone || `#${x.id}`, branch_id: x.branch_id ?? null })));
    }).catch(() => { if (alive) setItems([]); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [entity, warehouses]);

  const visible = items.filter(i => fromBranch === '' ? true : fromBranch === 'none' ? !i.branch_id : String(i.branch_id) === String(fromBranch));
  const branchLabel = id => branches.find(b => b.id === id)?.name || t('branch.noBranchGeneral');
  const toggle = id => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSelected = visible.length > 0 && visible.every(i => selected.has(i.id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(visible.map(i => i.id)));

  const submit = async () => {
    if (!selected.size) return toast.error(t('branch.reassignNothingSelected'));
    if (!toBranch) return toast.error(t('branch.reassignTargetRequired'));
    if (toBranch === 'none' && entity !== 'warehouses') return toast.error(t('branch.reassignTargetRequired'));
    const ids = [...selected];
    setSaving(true);
    try {
      let updated = 0; let skipped = []; let warnings = [];
      for (let i = 0; i < ids.length; i += 1000) {
        const { data } = await api.post('/branches/reassign', {
          entity, ids: ids.slice(i, i + 1000), to_branch_id: toBranch === 'none' ? null : Number(toBranch),
        }, { _suppressToast: true });
        updated += data.updated || 0; skipped = skipped.concat(data.skipped || []); warnings = warnings.concat(data.warnings || []);
      }
      setResult({ updated, skipped, warnings });
      toast.success(t('branch.reassignDone').replace('{count}', updated));
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('branch.errorOccurred'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">{t('branch.reassignTitle')}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><Ic d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-4 overflow-y-auto">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {REASSIGN_ENTITIES.map(en => (
              <button key={en.key} type="button" onClick={() => setEntity(en.key)}
                className={`py-2 rounded-xl text-sm font-semibold border-2 transition-all ${entity === en.key ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-200 text-slate-600 hover:border-blue-300'}`}>
                {t(en.labelKey)}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('branch.reassignFrom')}</label>
              <select value={fromBranch} onChange={e => setFromBranch(e.target.value)}
                className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400">
                <option value="">{t('branch.reassignAllBranches')}</option>
                <option value="none">{t('branch.noBranchGeneral')}</option>
                {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{t('branch.reassignTo')} *</label>
              <select value={toBranch} onChange={e => setToBranch(e.target.value)}
                className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400">
                <option value="">{t('branch.reassignChooseTarget')}</option>
                {entity === 'warehouses' && <option value="none">{t('branch.noBranchGeneral')}</option>}
                {branches.filter(b => b.is_active).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
          </div>
          {entity === 'warehouses' && <p className="text-xs font-semibold text-amber-600">{t('branch.reassignWarehouseHint')}</p>}
          {entity === 'wallets' && <p className="text-xs font-semibold text-amber-600">{t('branch.reassignWalletHint')}</p>}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <label className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-b border-slate-200 text-sm font-semibold text-slate-700 cursor-pointer">
              <input type="checkbox" checked={allSelected} onChange={toggleAll} />
              {t('branch.reassignSelectAll')} ({selected.size}/{visible.length})
            </label>
            <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
              {loading ? <div className="p-4 text-sm text-slate-400">{t('common.loading')}</div>
                : visible.length === 0 ? <div className="p-4 text-sm text-slate-400">{t('branch.reassignEmpty')}</div>
                : visible.map(i => (
                  <label key={i.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-slate-50">
                    <input type="checkbox" checked={selected.has(i.id)} onChange={() => toggle(i.id)} />
                    <span className="flex-1 truncate text-slate-700">{i.name}</span>
                    <span className="text-xs text-slate-400 shrink-0">{branchLabel(i.branch_id)}</span>
                  </label>
                ))}
            </div>
          </div>
          {result && (
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-800 space-y-1">
              <div className="font-bold">{t('branch.reassignDone').replace('{count}', result.updated)}</div>
              {result.skipped.length > 0 && <div className="text-amber-700">{t('branch.reassignSkipped').replace('{count}', result.skipped.length)}: {result.skipped.slice(0, 5).map(x => `#${x.id} ${x.reason}`).join('; ')}</div>}
              {result.warnings.map((w, i) => <div key={i} className="text-amber-700">{w}</div>)}
            </div>
          )}
        </div>
        <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
          <button type="button" onClick={onClose} className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-50">{t('common.close')}</button>
          <button type="button" onClick={submit} disabled={saving || !selected.size}
            className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm disabled:opacity-50">
            {saving ? t('common.saving') : t('branch.reassignSubmit')}
          </button>
        </div>
      </div>
    </div>
  );
}

// T4.7: reja bajarilishi rangi — qizil <70%, sariq 70-100%, yashil >=100%
const planBar = (p) => (p >= 100 ? 'bg-emerald-500' : p >= 70 ? 'bg-amber-400' : 'bg-red-500');

export default function Filiallar({ embedded = false }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const navigate = useNavigate();
  const { currentBranchId } = useBranch();
  const [usage, setUsage] = useState(null);   // T3.9: GET /billing/my-company/usage (ishlatilgan / limit)
  // T3.8: filiallar yagona hook'dan (nofaollari ham); o'zgarganda invalidateBranches()
  const { branches, reload: reloadBranches } = useBranches({ includeInactive: true });
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [branchModal, setBranchModal] = useState(null); // null | 'create' | branchObj
  const [whModal, setWhModal] = useState(null);         // null | 'create' | whObj
  const [reassignOpen, setReassignOpen] = useState(false);   // T4.5: ommaviy ko'chirish modali
  const [expandedBranch, setExpandedBranch] = useState(null);
  const [loadError, setLoadError] = useState(false);     // T3.1: yuklash xatosi — "Birinchi filial" CTA chiqmasin
  const [statusFilter, setStatusFilter] = useState('active');   // 'active' | 'all' | 'inactive'
  const [branchUsers, setBranchUsers] = useState({});    // T3.1: { [branchId]: { loading, items } }
  const [plans, setPlans] = useState({});                // T4.7: { [branchId]: joriy oy reja bajarilishi }

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const [brList, wh] = await Promise.all([
        // T3.1: nofaol filiallar ham olinadi (faqat admin/director uchun; "Faollashtirish" uchun)
        // T3.8: hook keshi — invalidateBranches() dan keyin bitta so'rov, aks holda kesh ishlatiladi
        reloadBranches(false),
        // T1.3: boshqaruv sahifasi — barcha filiallar omborlari (nofaollari ham); ruxsat bo'lmasa joriy kontekst
        api.get('/warehouses', { params: { scope: 'all', include_inactive: true } }).catch(() => api.get('/warehouses')),
      ]);
      if (brList?.failed) throw new Error('branches');   // hook xatoni yutadi — yuklash xatosi sifatida ko'rsatamiz
      setWarehouses(wh.data);
      // T3.9: tarif foydalanishi (super_admin / korxonasiz foydalanuvchida 404 — nishon ko'rsatilmaydi)
      api.get('/billing/my-company/usage', { _silent: true, _suppressToast: true })
        .then(r => setUsage(r.data)).catch(() => setUsage(null));
      setBranchUsers({});
      // T4.7: joriy oy reja bajarilishi (ruxsat yo'q yoki xato bo'lsa progress-bar ko'rsatilmaydi)
      api.get('/branch-plans/progress', { _silent: true, _suppressToast: true })
        .then(r => setPlans(Object.fromEntries((r.data || []).map(x => [x.branch_id, x]))))
        .catch(() => setPlans({}));
    } catch (e) {
      setLoadError(true);
      toast.error(t('branch.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t, reloadBranches]);

  useEffect(() => { load(); }, [load]);

  const handleDeactivateBranch = async (b) => {
    if (!window.confirm(t('branch.confirmDeactivate', { name: b.name }))) return;
    try {
      await api.patch(`/branches/${b.id}`, { is_active: false }, { _suppressToast: true });
      toast.success(t('branch.deactivated'));
      invalidateBranches();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('common.error'));
    }
  };

  // T3.9: qayta yoqish limitdan oshsa backend 403 (tarif limiti matni) qaytaradi
  const handleReactivateBranch = async (b) => {
    try {
      await api.patch(`/branches/${b.id}`, { is_active: true }, { _suppressToast: true });
      toast.success(tf('branch.reactivated', 'Filial qayta yoqildi'));
      invalidateBranches();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('common.error'));
    }
  };

  // T3.1: filial xodimlari (ochiladigan bo'lim) — GET /users/?branch_id=
  const loadBranchUsers = async (branchId) => {
    setBranchUsers(m => ({ ...m, [branchId]: { loading: true, items: m[branchId]?.items || [] } }));
    try {
      const r = await api.get('/users/', { params: { branch_id: branchId }, _suppressToast: true });
      setBranchUsers(m => ({ ...m, [branchId]: { loading: false, items: r.data || [] } }));
    } catch (e) {
      setBranchUsers(m => ({ ...m, [branchId]: { loading: false, items: [], error: true } }));
    }
  };

  const toggleBranch = (branch, isExpanded) => {
    setExpandedBranch(isExpanded ? null : branch.id);
    if (!isExpanded && !branchUsers[branch.id]) loadBranchUsers(branch.id);
  };

  const unassignedWhs = warehouses.filter(w => !w.branch_id);
  const hasInactive = branches.some(b => !b.is_active);
  const visibleBranches = branches.filter(b => statusFilter === 'all' ? true : (statusFilter === 'inactive' ? !b.is_active : b.is_active));

  // T3.9: "Filiallar: N/M" nishoni va limitga yetganda "Filial qo'shish" ni o'chirish
  const brUsage = usage?.usage?.branches || null;
  const whUsage = usage?.usage?.warehouses || null;
  const branchFull = !!(brUsage && brUsage.limit != null && brUsage.used >= brUsage.limit);
  const badgeCls = (u) => u.over
    ? 'bg-red-50 text-red-700 border-red-200'
    : (u.full ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-slate-50 text-slate-600 border-slate-200');
  const limitText = (u) => `${u.used}/${u.limit == null ? '∞' : u.limit}`;

  const whTypeLabel = (type) => WAREHOUSE_TYPE_BY_VALUE[type] ? t(WAREHOUSE_TYPE_BY_VALUE[type].labelKey) : type;
  const whTypeColor = (type) => WAREHOUSE_TYPE_BY_VALUE[type]?.color || 'bg-slate-100 text-slate-500';

  return (
    <div className={embedded ? "space-y-4" : "space-y-4 max-w-7xl mx-auto"}>
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            {!embedded && <h1 className="text-xl font-black text-slate-800">{t('branch.pageTitle')}</h1>}
            {brUsage && (
              <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${badgeCls(brUsage)}`}>
                {tf('branch.limitBadge', 'Filiallar: {used}/{limit}').replace('{used}', brUsage.used).replace('{limit}', brUsage.limit == null ? '∞' : brUsage.limit)}
              </span>
            )}
            {whUsage && (
              <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${badgeCls(whUsage)}`}>
                {tf('branch.warehouseLimitBadge', 'Omborlar: {used}/{limit}').replace('{used}', whUsage.used).replace('{limit}', whUsage.limit == null ? '∞' : whUsage.limit)}
              </span>
            )}
          </div>
          {!embedded && <p className="text-sm text-slate-500 mt-0.5">{t('branch.pageSubtitle')}</p>}
        </div>
        <div className="flex gap-2">
          {/* T4.7: reja va KPI sahifasiga o'tish */}
          {branches.filter(b => b.is_active).length > 0 && (
            <button onClick={() => navigate('/admin/branch-plans')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border-2 border-slate-200 text-slate-700 hover:border-blue-300 font-semibold text-sm transition-all">
              <Ic d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" cls="w-4 h-4" />
              {tf('plan.title', 'Reja va KPI')}
            </button>
          )}
          {branches.filter(b => b.is_active).length > 0 && (
            <button onClick={() => setReassignOpen(true)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border-2 border-slate-200 text-slate-700 hover:border-blue-300 font-semibold text-sm transition-all">
              <Ic d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" cls="w-4 h-4" />
              {t('branch.reassignOpen')}
            </button>
          )}
          <button onClick={() => setWhModal(
              (expandedBranch || currentBranchId || (branches.length === 1 ? branches[0].id : null))
                ? { branchId: expandedBranch || currentBranchId || branches[0].id }
                : 'create')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border-2 border-slate-200 text-slate-700 hover:border-blue-300 font-semibold text-sm transition-all">
            <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4" />
            {t('branch.addWarehouse')}
          </button>
          <button onClick={() => setBranchModal('create')}
            disabled={branchFull}
            title={branchFull ? tf('branch.limitReached', 'Tarif bo\'yicha filial limitiga yetdingiz') : undefined}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm shadow-md shadow-blue-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-blue-600">
            <Ic d="M12 4v16m8-8H4" cls="w-4 h-4" />
            {t('branch.addBranch')}
          </button>
        </div>
      </div>

      {branchFull && (
        <div className="flex items-center justify-between gap-3 flex-wrap bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3">
          <span className="text-sm font-semibold text-amber-800">
            {tf('branch.limitReached', 'Tarif bo\'yicha filial limitiga yetdingiz')} ({limitText(brUsage)})
          </span>
          <button onClick={() => navigate('/admin/tariflar')}
            className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold">
            {tf('branch.upgradePlan', 'Tarifni oshirish')}
          </button>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: t('branch.totalBranches'), value: branches.filter(b => b.is_active).length, icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4', color: 'bg-blue-50 text-blue-700' },
          { label: t('branch.totalWarehouses'), value: warehouses.filter(w => w.is_active).length, icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4', color: 'bg-emerald-50 text-emerald-700' },
          { label: t('branch.linkedWarehouses'), value: warehouses.filter(w => w.branch_id && w.is_active).length, icon: 'M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1', color: 'bg-amber-50 text-amber-700' },
          { label: t('branch.unlinkedWarehouses'), value: unassignedWhs.filter(w => w.is_active).length, icon: 'M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636', color: 'bg-blue-50 text-blue-700' },
        ].map(c => (
          <div key={c.label} className={`rounded-2xl p-4 border border-slate-100 ${c.color}`}>
            <div className="flex items-center gap-2 mb-1">
              <Ic d={c.icon} cls="w-4 h-4 opacity-70" />
              <span className="text-xs font-semibold opacity-70">{c.label}</span>
            </div>
            {loading
              ? <div className="h-8 w-12 rounded-lg bg-current opacity-10 animate-pulse" />
              : <p className="text-2xl font-black">{c.value}</p>}
          </div>
        ))}
      </div>

      {/* T3.1: holat filtri — nofaol filiallarni ko'rish */}
      {!loadError && (hasInactive || statusFilter !== 'active') && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {[
            { id: 'active', label: tf('branch.filterActive', 'Faollar') },
            { id: 'inactive', label: tf('branch.showInactive', 'Nofaollar') },
            { id: 'all', label: t('common.all') },
          ].map(f => (
            <button key={f.id} onClick={() => setStatusFilter(f.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border transition-colors ${statusFilter === f.id ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300'}`}>
              {f.label}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center items-center py-20">
          <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : loadError ? (
        <div className="bg-white rounded-2xl border-2 border-dashed border-red-200 p-12 text-center">
          <p className="text-slate-600 font-semibold mb-3">{tf('branch.loadFailedRetry', "Yuklab bo'lmadi, qayta urinib ko'ring")}</p>
          <button onClick={load}
            className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm">
            {tf('superAdmin.retry', 'Qayta urinish')}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Branch cards */}
          {visibleBranches.map(branch => {
            const bWhs = warehouses.filter(w => w.branch_id === branch.id);
            const isExpanded = expandedBranch === branch.id;
            return (
              <div key={branch.id} className={`bg-white rounded-2xl border-2 transition-all ${branch.is_active ? 'border-slate-100 hover:border-blue-100' : 'border-slate-100 opacity-60'}`}>
                {/* Branch header */}
                <div className="flex items-center gap-3 p-4 cursor-pointer" onClick={() => toggleBranch(branch, isExpanded)}>
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${branch.is_active ? 'bg-blue-600' : 'bg-slate-300'}`}>
                    <Ic d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" cls="w-5 h-5 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-slate-800">{branch.name}</span>
                      {!branch.is_active && <span className="text-[10px] font-bold px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full">{t('common.inactive')}</span>}
                      {branch.is_main && <span className="text-[10px] font-bold px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200 rounded-full">{t('branch.mainBranch')}</span>}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-500 flex-wrap">
                      {branch.address && <span>📍 {branch.address}</span>}
                      {branch.phone && <span>📞 {branch.phone}</span>}
                      <span className="font-semibold text-blue-600">{t('branch.warehouseCount', { count: bWhs.filter(w => w.is_active).length })}</span>
                      {branch.users_count != null && (
                        <span className="font-semibold text-slate-600">{tf('branch.usersCount', 'Xodimlar: {count}').replace('{count}', branch.users_count)}</span>
                      )}
                    </div>
                    {branch.is_active && (branch.warehouse_count ?? bWhs.length) === 0 && bWhs.length === 0 && (
                      <div className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1">
                        <Ic d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" cls="w-3.5 h-3.5" />
                        {t('branch.noWarehouseWarning')}
                      </div>
                    )}
                    {branch.is_active && plans[branch.id]?.target != null && (
                      <div className="mt-2 max-w-xs">
                        <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 mb-0.5">
                          <span>{tf('plan.monthPlan', 'Oylik reja')}</span>
                          <span>{plans[branch.id].percent ?? 0}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                          <div className={`h-full ${planBar(plans[branch.id].percent ?? 0)}`}
                            style={{ width: `${Math.min(plans[branch.id].percent ?? 0, 100)}%` }} />
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={e => { e.stopPropagation(); setWhModal({ branchId: branch.id }); }}
                      className="p-2 rounded-xl text-blue-500 hover:bg-blue-50 transition-colors" title={t('branch.addWarehouse')}>
                      <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4" />
                    </button>
                    <button onClick={e => { e.stopPropagation(); setBranchModal(branch); }}
                      className="p-2 rounded-xl text-slate-400 hover:bg-slate-100 transition-colors" title={t('common.edit')}>
                      <Ic d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" cls="w-4 h-4" />
                    </button>
                    {!branch.is_active && (
                      <button onClick={e => { e.stopPropagation(); handleReactivateBranch(branch); }}
                        className="px-2.5 py-1.5 rounded-xl text-xs font-bold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors">
                        {tf('branch.reactivate', 'Faollashtirish')}
                      </button>
                    )}
                    {branch.is_active && (
                      <button onClick={e => { e.stopPropagation(); handleDeactivateBranch(branch); }}
                        className="p-2 rounded-xl text-blue-400 hover:bg-blue-50 transition-colors" title={t('branch.deactivate')}>
                        <Ic d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" cls="w-4 h-4" />
                      </button>
                    )}
                    <Ic d={isExpanded ? "M5 15l7-7 7 7" : "M19 9l-7 7-7-7"} cls="w-4 h-4 text-slate-400 ml-1" />
                  </div>
                </div>

                {/* Warehouses list */}
                {isExpanded && (
                  <div className="border-t border-slate-100 px-4 pb-4 pt-3">
                    {/* T3.1: filial xodimlari */}
                    <div className="mb-3">
                      <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-1.5">{tf('branch.usersList', 'Xodimlar')}</p>
                      {branchUsers[branch.id]?.loading ? (
                        <p className="text-xs text-slate-400">...</p>
                      ) : (branchUsers[branch.id]?.items || []).length === 0 ? (
                        <p className="text-xs text-slate-400">{tf('branch.noUsers', "Xodimlar yo'q")}</p>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {branchUsers[branch.id].items.map(u => (
                            <span key={u.id} className="text-xs font-semibold px-2 py-1 rounded-lg bg-slate-50 border border-slate-200 text-slate-700">
                              {u.name || u.phone || `#${u.id}`}
                              {u.role && <span className="text-slate-400 font-normal"> · {u.role}</span>}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    {bWhs.length === 0 ? (
                      <div className="flex flex-col items-center py-6 text-slate-400 gap-2">
                        <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-8 h-8" />
                        <p className="text-sm">{t('branch.noWarehousesInBranch')}</p>
                        <button onClick={() => setWhModal({ branchId: branch.id })}
                          className="text-sm font-bold text-blue-600 hover:text-blue-700">
                          + {t('branch.addWarehouse')}
                        </button>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                        {bWhs.map(wh => (
                          <div key={wh.id} className={`flex items-center gap-3 p-3 rounded-xl border transition-all ${wh.is_active ? 'border-slate-100 bg-slate-50 hover:border-blue-200' : 'border-slate-100 bg-slate-50 opacity-50'}`}>
                            <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center shrink-0">
                              <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4 text-slate-500" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-sm font-semibold text-slate-800 truncate">{wh.name}</span>
                                {wh.type && (
                                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${whTypeColor(wh.type)}`}>
                                    {whTypeLabel(wh.type)}
                                  </span>
                                )}
                                {wh.is_default && (
                                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full border bg-violet-50 text-violet-700 border-violet-200">
                                    {t('branch.defaultWarehouse')}
                                  </span>
                                )}
                              </div>
                              {!wh.is_active && <span className="text-[10px] text-slate-400">{t('common.inactive')}</span>}
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

          {!loadError && branches.length > 0 && visibleBranches.length === 0 && (
            <div className="text-center text-sm text-slate-400 py-8">{t('common.noData')}</div>
          )}

          {!loadError && branches.length === 0 && (
            <div className="bg-white rounded-2xl border-2 border-dashed border-slate-200 p-12 text-center">
              <Ic d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" cls="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 font-semibold mb-1">{t('branch.noBranchesYet')}</p>
              <p className="text-sm text-slate-400 mb-4">{t('branch.createBranchHint')}</p>
              <button onClick={() => setBranchModal('create')}
                className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm">
                + {t('branch.addFirstBranch')}
              </button>
            </div>
          )}

          {/* Unassigned warehouses */}
          {unassignedWhs.length > 0 && (
            <div className="bg-amber-50 border-2 border-amber-200 rounded-2xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <Ic d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" cls="w-5 h-5 text-amber-600" />
                <span className="font-bold text-amber-800">{t('branch.unassignedWarehousesTitle', { count: unassignedWhs.length })}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {unassignedWhs.map(wh => (
                  <div key={wh.id} className="flex items-center gap-3 p-3 rounded-xl border border-amber-200 bg-white">
                    <Ic d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" cls="w-4 h-4 text-amber-600" />
                    <span className="flex-1 text-sm font-semibold text-slate-700 truncate">{wh.name}</span>
                    <button onClick={() => setWhModal(wh)}
                      className="text-xs font-bold text-blue-600 hover:text-blue-700 shrink-0">
                      {t('branch.link')} →
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
          onSave={() => { setBranchModal(null); invalidateBranches(); load(); }}
          onClose={() => setBranchModal(null)}
        />
      )}
      {reassignOpen && (
        <ReassignModal
          branches={branches}
          warehouses={warehouses}
          onDone={load}
          onClose={() => setReassignOpen(false)}
        />
      )}
      {whModal && (
        <WarehouseModal
          branches={branches}
          editWh={whModal?.id ? whModal : null}
          defaultBranchId={whModal?.branchId}
          onSave={() => { setWhModal(null); load(); }}
          onClose={() => setWhModal(null)}
        />
      )}
    </div>
  );
}
