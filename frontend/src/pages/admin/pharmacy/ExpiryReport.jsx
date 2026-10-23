import { useState, useEffect, useCallback } from 'react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';
import { loadXLSX, loadSaveAs } from '../../../utils/excelLazy';
import { toast } from '../../../utils/toast';

// D4.1: dorixona yaroqlilik muddati hisoboti (seriya bo'yicha qoldiq) va hisobdan chiqarish dalolatnomasi.
// Faqat o'qiydi: GET /pharmacy/reports/expiry, GET /pharmacy/reports/write-off-act (PDF).
// Sahifaga D4.6 ulaydi; komponent mustaqil (props yo'q).
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const PERIODS = ['30', '60', '90', 'expired'];

export default function ExpiryReport() {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();

  const [branches, setBranches] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [branchId, setBranchId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [days, setDays] = useState('30');
  const [search, setSearch] = useState('');
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState({});
  const [commission, setCommission] = useState('');
  const [reason, setReason] = useState('');

  const periodLabel = (p) => ({
    '30': tf('pharmacyExpiry.d30', '30 kun ichida'),
    '60': tf('pharmacyExpiry.d60', '60 kun ichida'),
    '90': tf('pharmacyExpiry.d90', '90 kun ichida'),
    expired: tf('pharmacyExpiry.expired', "Muddati o'tgan"),
  }[p]);

  const params = useCallback(() => {
    const p = { days };
    if (branchId) p.branch_id = branchId;
    if (warehouseId) p.warehouse_id = warehouseId;
    if (search.trim()) p.search = search.trim();
    return p;
  }, [days, branchId, warehouseId, search]);

  const load = useCallback(async () => {
    setLoading(true);
    setSelected({});
    try {
      const r = await api.get('/pharmacy/reports/expiry', { params: params(), _suppressToast: true });
      setRows(Array.isArray(r.data?.rows) ? r.data.rows : []);
      setSummary(r.data?.summary || null);
    } catch { setRows([]); setSummary(null); }
    finally { setLoading(false); }
  }, [params]);

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

  const selectedIds = rows.filter(r => selected[r.batch_id]).map(r => r.batch_id);
  const allChecked = rows.length > 0 && selectedIds.length === rows.length;

  const exportExcel = async () => {
    const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
    const ws = XLSX.utils.json_to_sheet(rows.map(r => ({
      [tf('pharmacyExpiry.product', 'Mahsulot')]: r.product_name + (r.variant_name ? ` (${r.variant_name})` : ''),
      [tf('pharmacyExpiry.lot', 'Seriya')]: r.lot_number || '',
      [tf('pharmacyExpiry.expiry', 'Muddat')]: r.expiry_date,
      [tf('pharmacyExpiry.daysLeft', 'Qolgan kun')]: r.days_left,
      [tf('pharmacyExpiry.warehouse', 'Ombor')]: r.warehouse_name || '',
      [tf('pharmacyExpiry.branch', 'Filial')]: r.branch_name || '',
      [tf('pharmacyExpiry.quantity', 'Miqdor')]: r.quantity,
      [tf('pharmacyExpiry.unitCost', 'Kirim narxi')]: r.unit_cost,
      [tf('pharmacyExpiry.amount', 'Summa')]: r.amount,
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, tf('pharmacyExpiry.title', 'Yaroqlilik muddati hisoboti').slice(0, 31));
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `muddat_hisoboti_${days}_${new Date().toISOString().slice(0, 10)}.xlsx`);
  };

  const downloadAct = async () => {
    if (!rows.length) { toast.error(tf('pharmacyExpiry.noActRows', "Dalolatnoma uchun partiya yo'q")); return; }
    const p = new URLSearchParams(params());
    if (selectedIds.length) p.set('batch_ids', selectedIds.join(','));
    commission.split(',').map(s => s.trim()).filter(Boolean).forEach(m => p.append('commission', m));
    if (reason.trim()) p.set('reason', reason.trim());
    try {
      const [r, saveAs] = await Promise.all([
        api.get(`/pharmacy/reports/write-off-act?${p}`, { responseType: 'blob', _suppressToast: true }),
        loadSaveAs(),
      ]);
      saveAs(new Blob([r.data], { type: 'application/pdf' }), `dalolatnoma_${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch {
      toast.error(tf('pharmacyExpiry.downloadFailed', "Faylni yuklab bo'lmadi"));
    }
  };

  if (features && !features.pharmacy) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm text-sm text-slate-500">
        {tf('pharmacyExpiry.disabled', 'Dorixona moduli yoqilmagan (Sozlamalar → Umumiy).')}
      </div>
    );
  }

  const statusClass = (r) => (r.status === 'expired' ? 'text-red-600' : r.days_left <= 30 ? 'text-amber-600' : 'text-slate-600');

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('pharmacyExpiry.title', 'Yaroqlilik muddati hisoboti')}</h3>
      <p className="text-xs text-slate-400 mt-0.5 mb-3">
        {tf('pharmacyExpiry.desc', "Seriya va muddat bo'yicha qoldiq: 30/60/90 kun ichida tugaydigan va muddati o'tgan dorilar.")}
      </p>

      <div className="flex flex-wrap items-end gap-2 mb-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyExpiry.branch', 'Filial')}</span>
          <select value={branchId} onChange={e => setBranchId(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            <option value="">{tf('pharmacyExpiry.allBranches', 'Barcha filiallar')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyExpiry.warehouse', 'Ombor')}</span>
          <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            <option value="">{tf('pharmacyExpiry.allWarehouses', 'Barcha omborlar')}</option>
            {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyExpiry.period', 'Muddat')}</span>
          <select value={days} onChange={e => setDays(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            {PERIODS.map(p => <option key={p} value={p}>{periodLabel(p)}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyExpiry.search', 'Qidirish')}</span>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') load(); }}
            placeholder={tf('pharmacyExpiry.searchPlaceholder', 'Dori, shtrix-kod yoki seriya')}
            className="border border-slate-200 rounded-xl px-2 py-1.5 w-48"
          />
        </label>
        <button onClick={load} disabled={loading} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold rounded-xl disabled:opacity-50">
          {t('common.refresh')}
        </button>
        <button onClick={exportExcel} disabled={!rows.length} className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-semibold rounded-xl disabled:opacity-50">
          {tf('pharmacyExpiry.exportExcel', 'Excel')}
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-2 mb-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyExpiry.commission', "Komissiya a'zolari")} ({tf('pharmacyExpiry.commissionHint', 'Vergul bilan ajrating')})</span>
          <input value={commission} onChange={e => setCommission(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 w-72" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyExpiry.reason', 'Sabab')}</span>
          <input
            value={reason} onChange={e => setReason(e.target.value)}
            placeholder={tf('pharmacyExpiry.reasonDefault', "Yaroqlilik muddati o'tgan")}
            className="border border-slate-200 rounded-xl px-2 py-1.5 w-56"
          />
        </label>
        <button onClick={downloadAct} disabled={!rows.length} className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 font-semibold rounded-xl disabled:opacity-50">
          {selectedIds.length ? `${tf('pharmacyExpiry.actSelected', 'Tanlanganlar uchun dalolatnoma')} (${selectedIds.length})` : tf('pharmacyExpiry.act', 'Dalolatnoma (PDF)')}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 pr-2">
                <input
                  type="checkbox" checked={allChecked} title={tf('pharmacyExpiry.selectAll', 'Hammasini tanlash')}
                  onChange={e => setSelected(e.target.checked ? Object.fromEntries(rows.map(r => [r.batch_id, true])) : {})}
                />
              </th>
              <th className="py-2 pr-2">{tf('pharmacyExpiry.product', 'Mahsulot')}</th>
              <th className="py-2 pr-2">{tf('pharmacyExpiry.lot', 'Seriya')}</th>
              <th className="py-2 pr-2">{tf('pharmacyExpiry.expiry', 'Muddat')}</th>
              <th className="py-2 pr-2 text-right">{tf('pharmacyExpiry.daysLeft', 'Qolgan kun')}</th>
              <th className="py-2 pr-2">{tf('pharmacyExpiry.warehouse', 'Ombor')}</th>
              <th className="py-2 pr-2">{tf('pharmacyExpiry.branch', 'Filial')}</th>
              <th className="py-2 pr-2 text-right">{tf('pharmacyExpiry.quantity', 'Miqdor')}</th>
              <th className="py-2 pr-2 text-right">{tf('pharmacyExpiry.unitCost', 'Kirim narxi')}</th>
              <th className="py-2 text-right">{tf('pharmacyExpiry.amount', 'Summa')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.batch_id} className="border-b border-slate-100">
                <td className="py-2 pr-2">
                  <input type="checkbox" checked={!!selected[r.batch_id]} onChange={e => setSelected(s => ({ ...s, [r.batch_id]: e.target.checked }))} />
                </td>
                <td className="py-2 pr-2 font-semibold text-slate-700">{r.product_name}{r.variant_name ? ` (${r.variant_name})` : ''}</td>
                <td className="py-2 pr-2">{r.lot_number || <span className="text-slate-400">-</span>}</td>
                <td className={`py-2 pr-2 ${statusClass(r)}`}>{r.expiry_date}</td>
                <td className={`py-2 pr-2 text-right font-semibold ${statusClass(r)}`}>{r.days_left}</td>
                <td className="py-2 pr-2">{r.warehouse_name || '-'}</td>
                <td className="py-2 pr-2">{r.branch_name || '-'}</td>
                <td className="py-2 pr-2 text-right">{fmt(r.quantity)}</td>
                <td className="py-2 pr-2 text-right">{fmt(r.unit_cost)}</td>
                <td className="py-2 text-right">{fmt(r.amount)}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={10} className="py-4 text-center text-slate-400">
                {loading ? t('common.loading') : tf('pharmacyExpiry.empty', "Ma'lumot yo'q")}
              </td></tr>
            )}
          </tbody>
          {rows.length > 0 && summary && (
            <tfoot>
              <tr className="font-bold text-slate-800">
                <td className="py-2 pr-2" colSpan={7}>{tf('pharmacyExpiry.total', 'Jami')}</td>
                <td className="py-2 pr-2 text-right">{fmt(summary.quantity)}</td>
                <td />
                <td className="py-2 text-right">{fmt(summary.amount)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
