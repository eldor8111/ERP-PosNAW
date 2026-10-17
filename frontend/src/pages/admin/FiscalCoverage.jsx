import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

// T4.2: fiskal qamrov hisoboti — filial va fiskal modul bo'yicha fiskallangan / fiskallanmagan cheklar.
// Hech narsa yozilmaydi, faqat o'qiladi (GET /fiscal/coverage, GET /fiscal/unfiscalized).
const PAGE = 20;
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

export default function FiscalCoverage() {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };

  const [branches, setBranches] = useState([]);
  const [branchId, setBranchId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [list, setList] = useState(null);       // { items, total, skip } — fiskallanmagan cheklar
  const [listLoading, setListLoading] = useState(false);

  const params = useCallback(() => {
    const p = {};
    if (branchId) p.branch_id = branchId;
    if (dateFrom) p.date_from = dateFrom;
    if (dateTo) p.date_to = dateTo;
    return p;
  }, [branchId, dateFrom, dateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    setList(null);
    try {
      const r = await api.get('/fiscal/coverage', { params: params(), _suppressToast: true });
      setRows(Array.isArray(r.data) ? r.data : []);
    } catch { setRows([]); }
    finally { setLoading(false); }
  }, [params]);

  useEffect(() => {
    api.get('/branches', { _suppressToast: true })
      .then(r => setBranches(Array.isArray(r.data) ? r.data : []))
      .catch(() => setBranches([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const loadList = async (skip = 0) => {
    setListLoading(true);
    try {
      const r = await api.get('/fiscal/unfiscalized', { params: { ...params(), skip, limit: PAGE }, _suppressToast: true });
      // Jami son: header (CORS'da ko'rinmasligi mumkin), bo'lmasa qamrov jadvalidagi fiskallanmaganlar yig'indisi (bir xil filtr)
      const hdr = Number(r.headers?.['x-total-count']);
      setList({ items: Array.isArray(r.data) ? r.data : [], total: hdr > 0 ? hdr : rows.reduce((a, x) => a + (x.unfiscalized || 0), 0), skip });
    } catch { setList({ items: [], total: 0, skip: 0 }); }
    finally { setListLoading(false); }
  };

  const sum = (key) => rows.reduce((a, x) => a + (x[key] || 0), 0);
  const totalSales = sum('total_sales');
  const totalFisc = sum('fiscalized');
  const totalUnfisc = sum('unfiscalized');

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('fiscalCoverage.title', 'Fiskal qamrov')}</h3>
      <p className="text-xs text-slate-400 mt-0.5 mb-3">
        {tf('fiscalCoverage.desc', "Filial va fiskal modul bo'yicha fiskallangan va fiskallanmagan cheklar. Qaytarish hujjatlari alohida hisoblanadi.")}
      </p>

      <div className="flex flex-wrap items-end gap-2 mb-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('fiscalCoverage.branch', 'Filial')}</span>
          <select value={branchId} onChange={e => setBranchId(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5 bg-white">
            <option value="">{tf('fiscalCoverage.allBranches', 'Barcha filiallar')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('fiscalCoverage.dateFrom', 'Sanadan')}</span>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('fiscalCoverage.dateTo', 'Sanagacha')}</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="border border-slate-200 rounded-xl px-2 py-1.5" />
        </label>
        <button onClick={load} disabled={loading} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold rounded-xl disabled:opacity-50">
          {t('common.refresh')}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 pr-2">{tf('fiscalCoverage.branch', 'Filial')}</th>
              <th className="py-2 pr-2">{tf('fiscalCoverage.module', 'Fiskal modul')}</th>
              <th className="py-2 pr-2 text-right">{tf('fiscalCoverage.total', 'Jami')}</th>
              <th className="py-2 pr-2 text-right">{tf('fiscalCoverage.fiscalized', 'Fiskallangan')}</th>
              <th className="py-2 pr-2 text-right">{tf('fiscalCoverage.unfiscalized', 'Fiskallanmagan')}</th>
              <th className="py-2 text-right">{tf('fiscalCoverage.returns', 'Qaytarish')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x, i) => (
              <tr key={`${x.branch_id}-${x.factory_id}-${i}`} className="border-b border-slate-100">
                <td className="py-2 pr-2 font-semibold text-slate-700">{x.branch_name}</td>
                <td className="py-2 pr-2 tracking-widest">{x.factory_id || <span className="text-slate-400">{tf('fiscalCoverage.noModule', "modul yo'q")}</span>}</td>
                <td className="py-2 pr-2 text-right">{fmt(x.total_sales)}</td>
                <td className="py-2 pr-2 text-right text-emerald-600 font-semibold">{fmt(x.fiscalized)}</td>
                <td className={`py-2 pr-2 text-right font-semibold ${x.unfiscalized ? 'text-red-600' : 'text-slate-400'}`}>{fmt(x.unfiscalized)}</td>
                <td className="py-2 text-right text-slate-500">{fmt(x.returns)}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={6} className="py-4 text-center text-slate-400">
                {loading ? t('common.loading') : tf('fiscalCoverage.empty', "Ma'lumot yo'q")}
              </td></tr>
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr className="font-bold text-slate-800">
                <td className="py-2 pr-2" colSpan={2}>{tf('fiscalCoverage.sum', 'Jami')}</td>
                <td className="py-2 pr-2 text-right">{fmt(totalSales)}</td>
                <td className="py-2 pr-2 text-right text-emerald-600">{fmt(totalFisc)}</td>
                <td className="py-2 pr-2 text-right text-red-600">{fmt(totalUnfisc)}</td>
                <td />
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {totalUnfisc > 0 && !list && (
        <button onClick={() => loadList(0)} disabled={listLoading} className="mt-3 text-xs font-semibold text-blue-600 hover:text-blue-800">
          {tf('fiscalCoverage.showUnfiscalized', "Fiskallanmagan cheklarni ko'rsatish")}
        </button>
      )}

      {list && (
        <div className="mt-3">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-2">{tf('fiscalCoverage.number', 'Chek')}</th>
                  <th className="py-2 pr-2">{t('common.date')}</th>
                  <th className="py-2 pr-2">{tf('fiscalCoverage.branch', 'Filial')}</th>
                  <th className="py-2 pr-2">{tf('fiscalCoverage.cashier', 'Kassir')}</th>
                  <th className="py-2 text-right">{tf('fiscalCoverage.amount', 'Summa')}</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map(s => (
                  <tr key={s.id} className="border-b border-slate-100">
                    <td className="py-2 pr-2 font-semibold">{s.number}</td>
                    <td className="py-2 pr-2">{s.created_at ? new Date(s.created_at).toLocaleString('uz-UZ') : ''}</td>
                    <td className="py-2 pr-2">{s.branch_name}</td>
                    <td className="py-2 pr-2">{s.cashier_name}</td>
                    <td className="py-2 text-right">{fmt(s.total_amount)}</td>
                  </tr>
                ))}
                {!list.items.length && (
                  <tr><td colSpan={5} className="py-4 text-center text-slate-400">{listLoading ? t('common.loading') : tf('fiscalCoverage.empty', "Ma'lumot yo'q")}</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between mt-2 text-xs text-slate-500">
            <span>{Math.min(list.skip + 1, list.total)}–{Math.min(list.skip + PAGE, list.total)} / {list.total}</span>
            <span className="flex gap-2">
              <button disabled={listLoading || list.skip === 0} onClick={() => loadList(Math.max(0, list.skip - PAGE))}
                className="px-3 py-1 rounded-xl bg-slate-100 disabled:opacity-40">&lsaquo;</button>
              <button disabled={listLoading || list.skip + PAGE >= list.total} onClick={() => loadList(list.skip + PAGE)}
                className="px-3 py-1 rounded-xl bg-slate-100 disabled:opacity-40">&rsaquo;</button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
