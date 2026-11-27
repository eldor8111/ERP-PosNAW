import { useState, useEffect, useCallback, useMemo } from 'react';
import toast from 'react-hot-toast';
import { X, CookingPot, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R7.2: yarim tayyor mahsulot tayyorlash (qiyma, bulon, sous). Tex karta bo'yicha xom ashyo filial "Oshxona"
// omboridan yechiladi, yarim tayyor shu omborga kiradi. Backend: app/routers/restaurant_production.py.

const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';
const btnPrimary = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50';
const btnWarn = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold disabled:opacity-50';
const btnGhost = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold disabled:opacity-50';
const PERIODS = ['today', '7d', '30d'];

const qtyFmt = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });
const money = v => Math.round(Number(v) || 0).toLocaleString('uz-UZ');
const timeFmt = iso => (iso ? new Date(iso).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');
const parseQty = s => Number(String(s ?? '').replace(',', '.').trim());
const errMsg = (err, fb) => {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return d?.message || fb;
};

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function ProduceModal({ semi, branchId, onClose, onDone, t }) {
  const [qty, setQty] = useState(semi.output_qty ? String(semi.output_qty) : '1');
  const [note, setNote] = useState('');
  const [plan, setPlan] = useState(null);
  const [planErr, setPlanErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmForce, setConfirmForce] = useState(false);
  const n = parseQty(qty);
  const valid = Number.isFinite(n) && n > 0;

  useEffect(() => {
    setConfirmForce(false);
    if (!valid) { setPlan(null); return undefined; }
    const h = setTimeout(() => {
      api.get('/restaurant/production/plan', { params: { branch_id: branchId, product_id: semi.id, quantity: n }, _silent: true })
        .then(r => { setPlan(r.data); setPlanErr(''); })
        .catch(err => { setPlan(null); setPlanErr(errMsg(err, t('restProd.failed'))); });
    }, 300);
    return () => clearTimeout(h);
  }, [n, valid, branchId, semi.id, t]);

  const short = plan?.short?.length > 0;

  const submit = async force => {
    setBusy(true);
    try {
      await api.post('/restaurant/production', { branch_id: branchId, product_id: semi.id, quantity: n, note: note || null, force });
      toast.success(t('restProd.done'));
      onDone();
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d?.code === 'INSUFFICIENT_STOCK') setConfirmForce(true);
      toast.error(errMsg(err, t('restProd.failed')));
    }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center overflow-y-auto p-4" onMouseDown={onClose}>
      <div className="bg-white rounded-xl border border-slate-200 w-full max-w-2xl mt-12" onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">{t('restProd.produceTitle')}: {semi.name}</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{t('restProd.quantity')} ({semi.unit || ''})</span>
              <input className={inputCls} inputMode="decimal" value={qty} autoFocus onChange={e => setQty(e.target.value)} />
              <span className="block text-[11px] text-slate-500 mt-1">
                {t('restProd.cardGives')} {qtyFmt(semi.output_qty)} {semi.unit || ''}. {t('restProd.inKitchen')}: {qtyFmt(semi.stock)} {semi.unit || ''}
              </span>
            </label>
            <label className="block">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{t('restProd.note')}</span>
              <input className={inputCls} value={note} maxLength={500} onChange={e => setNote(e.target.value)} placeholder={t('restProd.notePh')} />
            </label>
          </div>

          {planErr && <div className="text-sm text-rose-700">{planErr}</div>}
          {plan && (
            <div className="border border-slate-200 rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500">
                  <tr>
                    <th className="text-left px-3 py-2 font-semibold">{t('restProd.colIngredient')}</th>
                    <th className="text-right px-3 py-2 font-semibold">{t('restProd.colNeed')}</th>
                    <th className="text-right px-3 py-2 font-semibold">{t('restProd.colHave')}</th>
                    <th className="text-right px-3 py-2 font-semibold">{t('restProd.colCost')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {plan.lines.map(ln => (
                    <tr key={ln.product_id} className={ln.shortage > 0 ? 'bg-rose-50' : ''}>
                      <td className="px-3 py-1.5 text-slate-800">
                        {ln.name}{ln.kind === 'semi' && <span className="ml-1.5 text-[11px] text-slate-500">{t('restProd.semiMark')}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right">{qtyFmt(ln.quantity)} {ln.unit || ''}</td>
                      <td className={`px-3 py-1.5 text-right ${ln.shortage > 0 ? 'text-rose-700 font-semibold' : 'text-slate-600'}`}>
                        {qtyFmt(ln.available)}
                        {ln.shortage > 0 && <span className="block text-[11px]">{t('restProd.short')} {qtyFmt(ln.shortage)}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-600">{money(ln.cost)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="border-t border-slate-200 text-sm">
                  <tr>
                    <td className="px-3 py-2 font-semibold text-slate-800" colSpan={3}>
                      {t('restProd.total')} <span className="font-normal text-slate-500">({t('restProd.perUnit')} {semi.unit || ''}: {money(plan.unit_cost)})</span>
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-slate-800">{money(plan.total_cost)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {(short || confirmForce) && (
            <div className="flex gap-2 items-start text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{t('restProd.shortWarn')}</span>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button className={btnGhost} onClick={onClose}>{t('restProd.cancel')}</button>
            {short || confirmForce
              ? <button className={btnWarn} disabled={busy || !valid || !plan} onClick={() => submit(true)}>{t('restProd.produceAnyway')}</button>
              : <button className={btnPrimary} disabled={busy || !valid || !plan} onClick={() => submit(false)}><CookingPot className="w-4 h-4" />{t('restProd.produce')}</button>}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function RestaurantProduction() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [branchId, setBranchId] = useState(null);
  const [semis, setSemis] = useState(null);
  const [hist, setHist] = useState([]);
  const [period, setPeriod] = useState('7d');
  const [open, setOpen] = useState(null);       // tanlangan yarim tayyor (modal)
  const [expanded, setExpanded] = useState({}); // id -> lines
  const [q, setQ] = useState('');

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  const loadSemis = useCallback(() => {
    if (!branchId) return;
    api.get('/restaurant/production/semis', { params: { branch_id: branchId } })
      .then(r => setSemis(r.data))
      .catch(err => toast.error(errMsg(err, t('restProd.failed'))));
  }, [branchId, t]);

  const loadHist = useCallback(() => {
    if (!branchId) return;
    const to = new Date();
    const from = new Date();
    if (period === '7d') from.setDate(from.getDate() - 6);
    if (period === '30d') from.setDate(from.getDate() - 29);
    api.get('/restaurant/production', { params: { branch_id: branchId, date_from: isoDate(from), date_to: isoDate(to) }, _silent: true })
      .then(r => setHist(r.data.items))
      .catch(() => {});
  }, [branchId, period]);

  useEffect(() => { loadSemis(); }, [loadSemis]);
  useEffect(() => { loadHist(); }, [loadHist]);

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (semis?.items || []).filter(x => !s || x.name.toLowerCase().includes(s));
  }, [semis, q]);

  const toggle = async row => {
    if (expanded[row.id]) { setExpanded(e => ({ ...e, [row.id]: null })); return; }
    try {
      const r = await api.get(`/restaurant/production/${row.id}`, { params: { branch_id: branchId } });
      setExpanded(e => ({ ...e, [row.id]: r.data.lines }));
    } catch (err) { toast.error(errMsg(err, t('restProd.failed'))); }
  };

  const cancelRow = async row => {
    if (!window.confirm(t('restProd.cancelConfirm'))) return;
    try {
      await api.post(`/restaurant/production/${row.id}/cancel`, null, { params: { branch_id: branchId } });
      toast.success(t('restProd.cancelled'));
      loadSemis();
      loadHist();
    } catch (err) { toast.error(errMsg(err, t('restProd.failed'))); }
  };

  const canProduce = !!semis?.can_produce;

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restProd.title')}</h1>
          <p className="text-sm text-slate-500">{t('restProd.desc')}</p>
        </div>
        {branches.length > 1 && (
          <select className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm" value={branchId ?? ''} onChange={e => setBranchId(Number(e.target.value))}>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="p-3 border-b border-slate-100 flex items-center gap-2">
          <span className="text-sm font-bold text-slate-800 whitespace-nowrap">{t('restProd.semis')}</span>
          <input className={`${inputCls} max-w-xs ml-auto`} value={q} onChange={e => setQ(e.target.value)} placeholder={t('restProd.search')} />
        </div>
        {semis && semis.items.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restProd.noSemis')}</div>}
        <div className="divide-y divide-slate-100">
          {shown.map(s => {
            const low = s.min_stock > 0 && s.stock <= s.min_stock;
            return (
              <div key={s.id} className="px-4 py-2.5 flex flex-wrap items-center gap-3 text-sm">
                <span className="font-semibold text-slate-800 flex-1 min-w-[160px]">{s.name}</span>
                <span className={`text-xs ${s.stock < 0 ? 'text-rose-700 font-semibold' : low ? 'text-amber-700 font-semibold' : 'text-slate-600'}`}>
                  {t('restProd.inKitchen')}: {qtyFmt(s.stock)} {s.unit || ''}
                </span>
                <span className="text-xs text-slate-500 w-40 text-right">{money(s.unit_cost)} / {s.unit || ''}</span>
                {!s.has_card
                  ? <span className="text-xs text-slate-400 w-32 text-right">{t('restProd.noCard')}</span>
                  : canProduce && <button className={btnGhost} onClick={() => setOpen(s)}><CookingPot className="w-4 h-4" />{t('restProd.produce')}</button>}
              </div>
            );
          })}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-slate-800">{t('restProd.history')}</span>
          <div className="ml-auto flex gap-1.5">
            {PERIODS.map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                      className={`px-2.5 py-1 rounded-lg border text-xs ${period === p ? 'border-blue-600 bg-blue-50 text-blue-800 font-semibold' : 'border-slate-200 text-slate-600'}`}>
                {t(`restProd.period.${p}`)}
              </button>
            ))}
          </div>
        </div>
        {hist.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restProd.noHistory')}</div>}
        <div className="divide-y divide-slate-100">
          {hist.map(h => (
            <div key={h.id} className={`px-4 py-2 text-sm ${h.status === 'cancelled' ? 'opacity-60' : ''}`}>
              <div className="flex flex-wrap items-center gap-3">
                <button className="text-slate-400 hover:text-slate-600" onClick={() => toggle(h)}>
                  {expanded[h.id] ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
                <span className="text-xs text-slate-500 w-24">{timeFmt(h.created_at)}</span>
                <span className="font-semibold text-slate-800 flex-1 min-w-[140px]">{h.name}</span>
                <span className="text-slate-700">{qtyFmt(h.quantity)} {h.unit || ''}</span>
                <span className="text-slate-600 w-28 text-right">{money(h.total_cost)}</span>
                <span className="text-xs text-slate-500 w-28 truncate">{h.user_name}</span>
                {h.status === 'cancelled'
                  ? <span className="text-xs text-rose-700 w-24 text-right">{t('restProd.statusCancelled')}</span>
                  : semis?.can_cancel
                    ? <button className="text-xs text-rose-700 hover:underline w-24 text-right" onClick={() => cancelRow(h)}>{t('restProd.cancelRow')}</button>
                    : <span className="w-24" />}
              </div>
              {(h.note || expanded[h.id]) && (
                <div className="pl-7 pt-1 text-xs text-slate-600 space-y-0.5">
                  {h.note && <div>{h.note}</div>}
                  {expanded[h.id] && (
                    <div>{h.number}: {expanded[h.id].map(ln => `${ln.name} ${qtyFmt(ln.quantity)} ${ln.unit || ''}`).join(', ')}</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {open && (
        <ProduceModal semi={open} branchId={branchId} t={t} onClose={() => setOpen(null)}
                      onDone={() => { setOpen(null); loadSemis(); loadHist(); }} />
      )}
    </div>
  );
}
