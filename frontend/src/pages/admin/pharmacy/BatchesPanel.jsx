import { useState, useEffect, useCallback } from 'react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';
import { toast } from '../../../utils/toast';

// D3.3: dorixona partiyalari va holatlari (faol, karantin, brak, qaytarib olingan).
// GET /pharmacy/batches (filtrlar), POST /pharmacy/batches/{id}/status (sabab majburiy).
// Sahifaga D4.6 ulaydi; komponent mustaqil (props yo'q).
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const STATUSES = ['active', 'quarantine', 'defect', 'recalled'];
const STATUS_STYLE = {
  active: 'bg-emerald-50 text-emerald-700',
  quarantine: 'bg-amber-50 text-amber-700',
  defect: 'bg-red-50 text-red-700',
  recalled: 'bg-slate-100 text-slate-600',
};

export default function BatchesPanel() {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();

  const [branches, setBranches] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [branchId, setBranchId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [status, setStatus] = useState('');
  const [lot, setLot] = useState('');
  const [expiryFrom, setExpiryFrom] = useState('');
  const [expiryTo, setExpiryTo] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [edit, setEdit] = useState(null); // { row, status, reason }
  const [saving, setSaving] = useState(false);

  const statusLabel = (s) => ({
    active: tf('pharmacyBatches.statusActive', 'Faol'),
    quarantine: tf('pharmacyBatches.statusQuarantine', 'Karantin'),
    defect: tf('pharmacyBatches.statusDefect', 'Brak'),
    recalled: tf('pharmacyBatches.statusRecalled', 'Qaytarib olingan'),
  }[s] || s);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (branchId) params.branch_id = branchId;
      if (warehouseId) params.warehouse_id = warehouseId;
      if (status) params.status = status;
      if (lot.trim()) params.lot = lot.trim();
      if (expiryFrom) params.expiry_from = expiryFrom;
      if (expiryTo) params.expiry_to = expiryTo;
      const r = await api.get('/pharmacy/batches', { params, _suppressToast: true });
      setRows(Array.isArray(r.data) ? r.data : []);
    } catch { setRows([]); }
    finally { setLoading(false); }
  }, [branchId, warehouseId, status, lot, expiryFrom, expiryTo]);

  useEffect(() => {
    api.get('/branches', { _suppressToast: true })
      .then(r => setBranches(Array.isArray(r.data) ? r.data : []))
      .catch(() => setBranches([]));
  }, []);
  useEffect(() => {
    api.get('/inventory/warehouses', { params: branchId ? { branch_id: branchId } : {}, _suppressToast: true })
      .then(r => setWarehouses(Array.isArray(r.data) ? r.data : []))
      .catch(() => setWarehouses([]));
    setWarehouseId('');
  }, [branchId]);
  useEffect(() => { if (features?.pharmacy) load(); }, [load, features?.pharmacy]);

  const openEdit = (row) => setEdit({ row, status: row.status === 'active' ? 'quarantine' : 'active', reason: '' });

  const save = async () => {
    if (!edit) return;
    if (!edit.reason.trim()) { toast.error(tf('pharmacyBatches.reasonRequired', 'Sababni kiriting')); return; }
    setSaving(true);
    try {
      await api.post(`/pharmacy/batches/${edit.row.batch_id}/status`, {
        status: edit.status, reason: edit.reason.trim(),
      });
      toast.success(tf('pharmacyBatches.saved', 'Partiya holati yangilandi'));
      setEdit(null);
      load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : tf('pharmacyBatches.saveFailed', "Holatni o'zgartirib bo'lmadi"));
    } finally { setSaving(false); }
  };

  if (features && !features.pharmacy) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm text-sm text-slate-500">
        {tf('pharmacyBatches.disabled', 'Dorixona moduli yoqilmagan (Sozlamalar → Umumiy).')}
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('pharmacyBatches.title', 'Partiyalar va holatlar')}</h3>
      <p className="text-xs text-slate-400 mt-0.5 mb-3">
        {tf('pharmacyBatches.desc', "Karantin, brak yoki qaytarib olingan partiya sotilmaydi; ta'minotchiga qaytarish mumkin.")}
      </p>

      <div className="flex flex-wrap items-end gap-2 mb-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyBatches.branch', 'Filial')}</span>
          <select value={branchId} onChange={e => setBranchId(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            <option value="">{tf('pharmacyBatches.allBranches', 'Barcha filiallar')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyBatches.warehouse', 'Ombor')}</span>
          <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            <option value="">{tf('pharmacyBatches.allWarehouses', 'Barcha omborlar')}</option>
            {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyBatches.status', 'Holat')}</span>
          <select value={status} onChange={e => setStatus(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            <option value="">{tf('pharmacyBatches.allStatuses', 'Barcha holatlar')}</option>
            {STATUSES.map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyBatches.lot', 'Seriya')}</span>
          <input
            value={lot} onChange={e => setLot(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') load(); }}
            className="border border-slate-200 rounded-xl px-2 py-1.5 w-36"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyBatches.expiryFrom', 'Muddat (dan)')}</span>
          <input type="date" value={expiryFrom} onChange={e => setExpiryFrom(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyBatches.expiryTo', 'Muddat (gacha)')}</span>
          <input type="date" value={expiryTo} onChange={e => setExpiryTo(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5" />
        </label>
        <button onClick={load} disabled={loading} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold rounded-xl disabled:opacity-50">
          {t('common.refresh')}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 pr-2">{tf('pharmacyBatches.product', 'Mahsulot')}</th>
              <th className="py-2 pr-2">{tf('pharmacyBatches.lot', 'Seriya')}</th>
              <th className="py-2 pr-2">{tf('pharmacyBatches.expiry', 'Muddat')}</th>
              <th className="py-2 pr-2">{tf('pharmacyBatches.warehouse', 'Ombor')}</th>
              <th className="py-2 pr-2 text-right">{tf('pharmacyBatches.quantity', 'Qoldiq')}</th>
              <th className="py-2 pr-2">{tf('pharmacyBatches.status', 'Holat')}</th>
              <th className="py-2 pr-2">{tf('pharmacyBatches.reason', 'Sabab')}</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.batch_id} className="border-b border-slate-100">
                <td className="py-2 pr-2 font-semibold text-slate-700">{r.product_name}{r.variant_name ? ` (${r.variant_name})` : ''}</td>
                <td className="py-2 pr-2">{r.lot_number || <span className="text-slate-400">-</span>}</td>
                <td className={`py-2 pr-2 ${r.days_left != null && r.days_left < 0 ? 'text-red-600' : 'text-slate-600'}`}>
                  {r.expiry_date || '-'}
                </td>
                <td className="py-2 pr-2">{r.warehouse_name || '-'}</td>
                <td className="py-2 pr-2 text-right">{fmt(r.quantity)}</td>
                <td className="py-2 pr-2">
                  <span className={`px-2 py-0.5 rounded-lg font-semibold ${STATUS_STYLE[r.status] || STATUS_STYLE.active}`}>
                    {statusLabel(r.status)}
                  </span>
                </td>
                <td className="py-2 pr-2 text-slate-500 max-w-[220px] truncate" title={r.status_reason || ''}>{r.status_reason || '-'}</td>
                <td className="py-2 text-right">
                  <button onClick={() => openEdit(r)} className="px-2 py-1 bg-blue-50 hover:bg-blue-100 text-blue-700 font-semibold rounded-lg">
                    {tf('pharmacyBatches.change', "Holatni o'zgartirish")}
                  </button>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={8} className="py-4 text-center text-slate-400">
                {loading ? t('common.loading') : tf('pharmacyBatches.empty', "Ma'lumot yo'q")}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {edit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => !saving && setEdit(null)}>
          <div className="bg-white rounded-2xl p-5 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
            <h4 className="text-sm font-bold text-slate-700 mb-1">{tf('pharmacyBatches.changeTitle', "Partiya holatini o'zgartirish")}</h4>
            <p className="text-xs text-slate-500 mb-3">
              {edit.row.product_name} · {tf('pharmacyBatches.lot', 'Seriya')}: {edit.row.lot_number || '-'} · {fmt(edit.row.quantity)}
            </p>
            <label className="flex flex-col gap-1 text-xs mb-3">
              <span className="text-slate-500">{tf('pharmacyBatches.newStatus', 'Yangi holat')}</span>
              <select
                value={edit.status} onChange={e => setEdit(s => ({ ...s, status: e.target.value }))}
                className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white"
              >
                {STATUSES.filter(s => s !== edit.row.status).map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs mb-4">
              <span className="text-slate-500">{tf('pharmacyBatches.reason', 'Sabab')} *</span>
              <textarea
                value={edit.reason} onChange={e => setEdit(s => ({ ...s, reason: e.target.value }))}
                rows={3} maxLength={500}
                className="border border-slate-200 rounded-xl px-2 py-1.5"
              />
            </label>
            <div className="flex justify-end gap-2 text-xs">
              <button onClick={() => setEdit(null)} disabled={saving} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold rounded-xl disabled:opacity-50">
                {tf('pharmacyBatches.cancel', 'Bekor qilish')}
              </button>
              <button onClick={save} disabled={saving} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl disabled:opacity-50">
                {tf('pharmacyBatches.save', 'Saqlash')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
