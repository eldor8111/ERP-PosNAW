import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';

// D4.3: dorixona defekturasi — tugagan/tugayotgan dorilar, tavsiya etilgan miqdor, ta'minotchi bo'yicha guruh.
// GET /pharmacy/defektura (faqat o'qiydi); "Xarid qoralamasini yaratish" mavjud POST /purchase-orders ni
// status=draft bilan chaqiradi. Faqat dorixona moduli yoqilgan korxonada ko'rinadi. D4.6 sahifaga ulaydi.
// Props: branchId (ixtiyoriy) — faqat shu filial omborlari.
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });

export default function DefekturaPanel({ branchId = '' }) {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();

  const [days, setDays] = useState(30);
  const [coverDays, setCoverDays] = useState(14);
  const [whId, setWhId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [qty, setQty] = useState({});          // {product_id: tahrirlangan miqdor}
  const [creating, setCreating] = useState(null);

  const enabled = !!features?.pharmacy;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { days, cover_days: coverDays };
      if (branchId) params.branch_id = branchId;
      if (whId) params.warehouse_id = whId;
      const r = await api.get('/pharmacy/defektura', { params, _suppressToast: true });
      setData(r.data);
      setQty({});
    } catch (e) {
      setData(null);
      toast.error(e.response?.data?.detail || e.message || tf('defektura.loadFailed', "Defekturani yuklab bo'lmadi"));
    } finally { setLoading(false); }
  }, [days, coverDays, whId, branchId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (enabled) load(); }, [enabled, load]);

  if (!enabled) return null;

  const qtyOf = (it) => (qty[it.product_id] !== undefined ? qty[it.product_id] : it.recommended_qty);
  const warehouses = data?.warehouses || [];
  // Qoralama ombori: tanlangan, bo'lmasa doiradagi birinchi ombor
  const draftWh = whId || warehouses[0]?.id || '';

  const createDraft = async (g) => {
    const rows = g.items.filter(it => it.product_type !== 'parent' && Number(qtyOf(it)) > 0);
    const skipped = g.items.filter(it => it.product_type === 'parent').length;
    if (!g.supplier_id || !draftWh || rows.length === 0) {
      toast.error(tf('defektura.noItems', "Qoralama uchun mahsulot yo'q"));
      return;
    }
    setCreating(g.supplier_id);
    try {
      const r = await api.post('/purchase-orders', {
        supplier_id: g.supplier_id,
        warehouse_id: Number(draftWh),
        status: 'draft',
        note: tf('defektura.draftNote', 'Defektura bo\'yicha avtomatik qoralama'),
        items: rows.map(it => ({
          product_id: it.product_id,
          qty_ordered: Number(qtyOf(it)),
          unit_cost: Number(it.last_cost || 0),
        })),
      }, { _suppressToast: true });
      toast.success(`${tf('defektura.draftCreated', 'Xarid qoralamasi yaratildi')}: ${r.data?.number || ''}`);
      if (skipped) toast(`${tf('defektura.skippedVariants', "Variantli mahsulotlar qoralamaga qo'shilmadi")}: ${skipped}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || tf('defektura.draftFailed', "Qoralamani yaratib bo'lmadi"));
    } finally { setCreating(null); }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('defektura.title', 'Defektura')}</h3>
      <p className="text-xs text-slate-500 mt-1">
        {tf('defektura.desc', "Tugagan va tugayotgan dorilar, tavsiya etilgan buyurtma miqdori va ta'minotchi bo'yicha guruh.")}
      </p>

      <div className="flex flex-wrap items-end gap-3 mt-4 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('defektura.days', 'Sotuv davri (kun)')}</span>
          <input type="number" min="1" max="365" value={days}
            onChange={e => setDays(Math.min(365, Math.max(1, Number(e.target.value) || 1)))}
            className="border border-slate-200 rounded-lg px-2 py-1.5 w-24" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('defektura.coverDays', 'Necha kunga zaxira')}</span>
          <input type="number" min="1" max="365" value={coverDays}
            onChange={e => setCoverDays(Math.min(365, Math.max(1, Number(e.target.value) || 1)))}
            className="border border-slate-200 rounded-lg px-2 py-1.5 w-24" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('defektura.warehouse', 'Ombor')}</span>
          <select value={whId} onChange={e => setWhId(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5 min-w-[160px]">
            <option value="">{tf('defektura.allWarehouses', 'Barcha omborlar')}</option>
            {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>
        <button type="button" onClick={load} disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold disabled:opacity-50">
          {loading ? tf('defektura.loading', 'Yuklanmoqda...') : tf('defektura.refresh', 'Yangilash')}
        </button>
      </div>

      {data && data.groups.length === 0 && !loading && (
        <div className="mt-6 text-center text-sm text-slate-400">{tf('defektura.empty', "Defektura bo'sh — barcha dorilar yetarli")}</div>
      )}

      <div className="mt-4 space-y-5">
        {(data?.groups || []).map(g => (
          <div key={g.supplier_id ?? 'none'} className="border border-slate-200 rounded-xl overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 px-3 py-2">
              <div className="text-sm font-semibold text-slate-700">
                {g.supplier_name || tf('defektura.noSupplier', "Ta'minotchisiz (xarid tarixi yo'q)")}
                <span className="ml-2 text-xs font-normal text-slate-500">
                  {g.items.length} {tf('defektura.itemsCount', 'ta dori')} · {tf('defektura.totalCost', 'Taxminiy summa')}: {fmt(g.estimated_cost)}
                </span>
              </div>
              {g.supplier_id ? (
                <button type="button" onClick={() => createDraft(g)} disabled={creating === g.supplier_id}
                  className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold disabled:opacity-50">
                  {creating === g.supplier_id ? tf('defektura.creating', 'Yaratilmoqda...') : tf('defektura.createDraft', 'Xarid qoralamasini yaratish')}
                </button>
              ) : (
                <span className="text-xs text-slate-400">{tf('defektura.noSupplierHint', "Ta'minotchi tanlash uchun avval xarid qiling")}</span>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-100">
                    <th className="py-2 px-3">{tf('defektura.product', 'Dori')}</th>
                    <th className="py-2 px-2">{tf('defektura.status', 'Holat')}</th>
                    <th className="py-2 px-2 text-right">{tf('defektura.stock', 'Yaroqli qoldiq')}</th>
                    <th className="py-2 px-2 text-right">{tf('defektura.minStock', 'Minimum')}</th>
                    <th className="py-2 px-2 text-right">{tf('defektura.sold', 'Sotilgan')}</th>
                    <th className="py-2 px-2 text-right">{tf('defektura.avgDaily', "Kuniga o'rtacha")}</th>
                    <th className="py-2 px-2 text-right">{tf('defektura.recommended', 'Tavsiya')}</th>
                    <th className="py-2 px-3 text-right">{tf('defektura.lastCost', 'Oxirgi narx')}</th>
                  </tr>
                </thead>
                <tbody>
                  {g.items.map(it => (
                    <tr key={it.product_id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2 px-3 text-slate-700">
                        {it.product_name}
                        <div className="text-[10px] text-slate-400">{it.sku}</div>
                      </td>
                      <td className="py-2 px-2">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${it.status === 'out' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'}`}>
                          {it.status === 'out' ? tf('defektura.out', 'Tugagan') : tf('defektura.low', 'Tugayapti')}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right">
                        {fmt(it.current_qty)} {it.unit}
                        {it.expired_qty > 0 && (
                          <div className="text-[10px] text-red-500">{tf('defektura.expired', "Muddati o'tgan")}: {fmt(it.expired_qty)}</div>
                        )}
                      </td>
                      <td className="py-2 px-2 text-right">{fmt(it.min_stock)}</td>
                      <td className="py-2 px-2 text-right">{fmt(it.sold_qty)}</td>
                      <td className="py-2 px-2 text-right">{fmt(it.avg_daily)}</td>
                      <td className="py-2 px-2 text-right">
                        <input type="number" min="0" value={qtyOf(it)}
                          onChange={e => setQty(q => ({ ...q, [it.product_id]: e.target.value }))}
                          className="border border-slate-200 rounded-lg px-2 py-1 w-20 text-right" />
                      </td>
                      <td className="py-2 px-3 text-right">{fmt(it.last_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
