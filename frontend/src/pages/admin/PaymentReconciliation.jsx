import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

// T3.18: provayder ko'chirmasi (CSV: date, amount, reference) bilan ichki to'lovlarni solishtirish.
// Hech narsa yozilmaydi — faqat ko'rsatiladi.
const PROVIDERS = ['click', 'payme', 'uzum', 'uzcard', 'humo'];
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

export default function PaymentReconciliation() {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };

  const [provider, setProvider] = useState('click');
  const [branchId, setBranchId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [file, setFile] = useState(null);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.get('/branches', { _suppressToast: true })
      .then(r => setBranches(Array.isArray(r.data) ? r.data : []))
      .catch(() => setBranches([]));
  }, []);

  const run = async () => {
    if (!file) { toast.error(tf('reconcile.chooseFile', 'CSV faylni tanlang')); return; }
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const params = { provider };
      if (branchId) params.branch_id = branchId;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const r = await api.post('/finance/reconciliation/import', fd, {
        params, headers: { 'Content-Type': 'multipart/form-data' }, _suppressToast: true,
      });
      setResult(r.data);
    } catch (e) {
      setResult(null);
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setLoading(false);
    }
  };

  const tot = result?.totals;

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-800">{tf('reconcile.title', "To'lovlarni solishtirish")}</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          {tf('reconcile.hint', "Provayder ko'chirmasi (CSV: date, amount, reference) ni ichki to'lovlar bilan solishtiradi. Hech narsa o'zgartirilmaydi.")}
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-4 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
        <label className="text-xs font-semibold text-slate-500">
          {tf('reconcile.provider', 'Provayder')}
          <select value={provider} onChange={e => setProvider(e.target.value)}
            className="mt-1 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm bg-white">
            {PROVIDERS.map(p => <option key={p} value={p}>{p.toUpperCase()}</option>)}
          </select>
        </label>
        <label className="text-xs font-semibold text-slate-500">
          {tf('reconcile.branch', 'Filial')}
          <select value={branchId} onChange={e => setBranchId(e.target.value)}
            className="mt-1 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm bg-white">
            <option value="">{tf('reconcile.allBranches', 'Barcha filiallar')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="text-xs font-semibold text-slate-500">
          {tf('reconcile.dateFrom', 'Sanadan')}
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="mt-1 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label className="text-xs font-semibold text-slate-500">
          {tf('reconcile.dateTo', 'Sanagacha')}
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="mt-1 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label className="text-xs font-semibold text-slate-500">
          {tf('reconcile.file', 'CSV fayl')}
          <input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] || null)}
            className="mt-1 w-full text-xs" />
        </label>
        <div className="md:col-span-5">
          <button onClick={run} disabled={loading}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl disabled:opacity-50">
            {loading ? tf('reconcile.running', 'Solishtirilmoqda...') : tf('reconcile.run', 'Solishtirish')}
          </button>
        </div>
      </div>

      {tot && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4">
              <div className="text-xs font-semibold text-emerald-700">{tf('reconcile.matched', 'Mos kelganlar')}</div>
              <div className="text-2xl font-black text-emerald-700">{tot.matched_count}</div>
              <div className="text-xs text-emerald-600">{fmt(tot.matched_amount)}</div>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
              <div className="text-xs font-semibold text-amber-700">{tf('reconcile.onlySystem', 'Faqat tizimda (provayderda yo\'q)')}</div>
              <div className="text-2xl font-black text-amber-700">{tot.only_in_system_count}</div>
              <div className="text-xs text-amber-600">{fmt(tot.only_in_system_amount)}</div>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-2xl p-4">
              <div className="text-xs font-semibold text-red-700">{tf('reconcile.onlyProvider', 'Faqat provayderda (tizimda yo\'q)')}</div>
              <div className="text-2xl font-black text-red-700">{tot.only_in_provider_count}</div>
              <div className="text-xs text-red-600">{fmt(tot.only_in_provider_amount)}</div>
            </div>
          </div>

          <Section title={tf('reconcile.onlySystem', "Faqat tizimda (provayderda yo'q)")} empty={!result.only_in_system.length}
            emptyText={tf('reconcile.none', "Yo'q")}>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400">
                <th className="py-1">{tf('reconcile.sale', 'Sotuv')}</th><th>{tf('reconcile.date', 'Sana')}</th>
                <th className="text-right">{tf('reconcile.amount', 'Summa')}</th><th>{tf('reconcile.reference', 'Tranzaksiya raqami')}</th>
              </tr></thead>
              <tbody>
                {result.only_in_system.map(s => (
                  <tr key={s.payment_id} className="border-t border-slate-100">
                    <td className="py-1 font-semibold">{s.sale_number}</td><td>{s.created_at}</td>
                    <td className="text-right">{fmt(s.amount)}</td><td>{s.reference || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title={tf('reconcile.onlyProvider', "Faqat provayderda (tizimda yo'q)")} empty={!result.only_in_provider.length}
            emptyText={tf('reconcile.none', "Yo'q")}>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400">
                <th className="py-1">#</th><th>{tf('reconcile.date', 'Sana')}</th>
                <th className="text-right">{tf('reconcile.amount', 'Summa')}</th><th>{tf('reconcile.reference', 'Tranzaksiya raqami')}</th>
              </tr></thead>
              <tbody>
                {result.only_in_provider.map(p => (
                  <tr key={p.row} className="border-t border-slate-100">
                    <td className="py-1">{p.row}</td><td>{p.date}</td>
                    <td className="text-right">{fmt(p.amount)}</td><td>{p.reference || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title={tf('reconcile.matched', 'Mos kelganlar')} empty={!result.matched.length}
            emptyText={tf('reconcile.none', "Yo'q")}>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400">
                <th className="py-1">{tf('reconcile.sale', 'Sotuv')}</th><th>{tf('reconcile.date', 'Sana')}</th>
                <th className="text-right">{tf('reconcile.amount', 'Summa')}</th><th>{tf('reconcile.reference', 'Tranzaksiya raqami')}</th>
                <th>{tf('reconcile.matchType', 'Moslik')}</th>
              </tr></thead>
              <tbody>
                {result.matched.map(m => (
                  <tr key={m.system.payment_id} className="border-t border-slate-100">
                    <td className="py-1 font-semibold">{m.system.sale_number}</td><td>{m.provider.date}</td>
                    <td className="text-right">{fmt(m.provider.amount)}</td><td>{m.provider.reference || m.system.reference || '—'}</td>
                    <td>{m.match_type === 'reference'
                      ? tf('reconcile.byReference', 'raqam bo\'yicha')
                      : tf('reconcile.byAmountTime', 'summa va vaqt bo\'yicha')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, empty, emptyText, children }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4">
      <h3 className="text-sm font-bold text-slate-700 mb-2">{title}</h3>
      {empty ? <p className="text-xs text-slate-400">{emptyText}</p> : <div className="overflow-x-auto">{children}</div>}
    </div>
  );
}
