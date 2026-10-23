import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';

// D4.5: dorixona tahlili — sotuvni modda / ishlab chiqaruvchi / mamlakat bo'yicha guruhlash (tushum, tannarx, marja)
// va qisqa ko'rsatkichlar. GET /pharmacy/analytics/sales va /pharmacy/analytics/summary (faqat o'qiydi).
// Faqat dorixona moduli yoqilgan korxonada ko'rinadi. D4.6 sahifaga ulaydi.
// Props: branchId (ixtiyoriy) — faqat shu filial omborlari.
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 2 });
const pct = (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('uz-UZ', { maximumFractionDigits: 1 })}%`);
const GROUPS = ['substance', 'manufacturer', 'country'];

const isoDate = (d) => {
  const z = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
};

export default function AnalyticsPanel({ branchId = '' }) {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();

  const [group, setGroup] = useState('substance');
  const [dateTo, setDateTo] = useState(() => isoDate(new Date()));
  const [dateFrom, setDateFrom] = useState(() => { const d = new Date(); d.setDate(d.getDate() - 29); return isoDate(d); });
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  const enabled = !!features?.pharmacy;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const base = branchId ? { branch_id: branchId } : {};
      const [s, sm] = await Promise.all([
        api.get('/pharmacy/analytics/sales', { params: { ...base, group, from: dateFrom, to: dateTo }, _suppressToast: true }),
        api.get('/pharmacy/analytics/summary', { params: base, _suppressToast: true }),
      ]);
      setData(s.data);
      setSummary(sm.data);
    } catch (e) {
      setData(null);
      setSummary(null);
      toast.error(e.response?.data?.detail || e.message || tf('pharmAnalytics.loadFailed', "Tahlilni yuklab bo'lmadi"));
    } finally { setLoading(false); }
  }, [group, dateFrom, dateTo, branchId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (enabled) load(); }, [enabled, load]);

  if (!enabled) return null;

  const groupLabel = {
    substance: tf('pharmAnalytics.bySubstance', "Modda bo'yicha"),
    manufacturer: tf('pharmAnalytics.byManufacturer', "Ishlab chiqaruvchi bo'yicha"),
    country: tf('pharmAnalytics.byCountry', "Mamlakat bo'yicha"),
  };
  const cards = summary ? [
    { k: 'expiring', label: `${tf('pharmAnalytics.expiring', 'Muddati yaqin partiyalar')} (${summary.expiry_warn_days} ${tf('pharmAnalytics.days', 'kun')})`, v: summary.expiring_batches, cls: 'text-amber-600' },
    { k: 'expired', label: tf('pharmAnalytics.expired', "Muddati o'tgan partiyalar"), v: summary.expired_batches, cls: 'text-red-600' },
    { k: 'defektura', label: tf('pharmAnalytics.defektura', 'Defektura'), v: summary.defektura_count, cls: 'text-slate-700' },
    { k: 'rx', label: tf('pharmAnalytics.rxToday', 'Bugungi retseptli sotuvlar'), v: summary.rx_sales_today, cls: 'text-emerald-600' },
  ] : [];

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('pharmAnalytics.title', 'Dorixona tahlili')}</h3>
      <p className="text-xs text-slate-500 mt-1">
        {tf('pharmAnalytics.desc', "Sotuvni modda, ishlab chiqaruvchi va mamlakat bo'yicha guruhlash: tushum, tannarx va marja.")}
      </p>

      {cards.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {cards.map(c => (
            <div key={c.k} className="border border-slate-200 rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-500">{c.label}</div>
              <div className={`text-xl font-bold ${c.cls}`}>{fmt(c.v)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3 mt-4 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmAnalytics.group', 'Guruhlash')}</span>
          <select value={group} onChange={e => setGroup(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5 min-w-[180px]">
            {GROUPS.map(g => <option key={g} value={g}>{groupLabel[g]}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmAnalytics.from', 'Dan')}</span>
          <input type="date" value={dateFrom} max={dateTo} onChange={e => setDateFrom(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmAnalytics.to', 'Gacha')}</span>
          <input type="date" value={dateTo} min={dateFrom} onChange={e => setDateTo(e.target.value)}
            className="border border-slate-200 rounded-lg px-2 py-1.5" />
        </label>
        <button type="button" onClick={load} disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold disabled:opacity-50">
          {loading ? tf('pharmAnalytics.loading', 'Yuklanmoqda...') : tf('pharmAnalytics.refresh', 'Yangilash')}
        </button>
      </div>

      {data && data.groups.length === 0 && !loading && (
        <div className="mt-6 text-center text-sm text-slate-400">{tf('pharmAnalytics.empty', "Tanlangan davrda sotuv yo'q")}</div>
      )}

      {data && data.groups.length > 0 && (
        <div className="mt-4 overflow-x-auto border border-slate-200 rounded-xl">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 bg-slate-50 border-b border-slate-100">
                <th className="py-2 px-3">{groupLabel[data.group]}</th>
                <th className="py-2 px-2 text-right">{tf('pharmAnalytics.products', 'Dorilar')}</th>
                <th className="py-2 px-2 text-right">{tf('pharmAnalytics.qty', 'Miqdor')}</th>
                <th className="py-2 px-2 text-right">{tf('pharmAnalytics.revenue', 'Tushum')}</th>
                <th className="py-2 px-2 text-right">{tf('pharmAnalytics.cost', 'Tannarx')}</th>
                <th className="py-2 px-2 text-right">{tf('pharmAnalytics.margin', 'Marja')}</th>
                <th className="py-2 px-2 text-right">{tf('pharmAnalytics.marginPct', 'Marja %')}</th>
                <th className="py-2 px-3 text-right">{tf('pharmAnalytics.markupPct', 'Ustama %')}</th>
              </tr>
            </thead>
            <tbody>
              {data.groups.map(g => (
                <tr key={g.key ?? 'none'} className="border-b border-slate-50 last:border-0">
                  <td className="py-2 px-3 text-slate-700">
                    {g.name || <span className="text-slate-400">{tf('pharmAnalytics.unspecified', "Ko'rsatilmagan")}</span>}
                  </td>
                  <td className="py-2 px-2 text-right">{fmt(g.products_count)}</td>
                  <td className="py-2 px-2 text-right">{fmt(g.quantity)}</td>
                  <td className="py-2 px-2 text-right">{fmt(g.revenue)}</td>
                  <td className="py-2 px-2 text-right">{fmt(g.cost)}</td>
                  <td className={`py-2 px-2 text-right font-semibold ${g.margin < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmt(g.margin)}</td>
                  <td className="py-2 px-2 text-right">{pct(g.margin_pct)}</td>
                  <td className="py-2 px-3 text-right">{pct(g.markup_pct)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-slate-50 font-semibold text-slate-700">
                <td className="py-2 px-3">{tf('pharmAnalytics.total', 'Jami')}</td>
                <td className="py-2 px-2" />
                <td className="py-2 px-2 text-right">{fmt(data.total.quantity)}</td>
                <td className="py-2 px-2 text-right">{fmt(data.total.revenue)}</td>
                <td className="py-2 px-2 text-right">{fmt(data.total.cost)}</td>
                <td className="py-2 px-2 text-right">{fmt(data.total.margin)}</td>
                <td className="py-2 px-2 text-right">{pct(data.total.margin_pct)}</td>
                <td className="py-2 px-3 text-right">{pct(data.total.markup_pct)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      {data?.overlap && data.groups.length > 0 && (
        <p className="text-[11px] text-slate-400 mt-2">
          {tf('pharmAnalytics.overlapNote', "Bir necha moddali dori har bir moddaga to'liq yoziladi, shuning uchun qatorlar yig'indisi jamidan katta bo'lishi mumkin.")}
        </p>
      )}
    </div>
  );
}
