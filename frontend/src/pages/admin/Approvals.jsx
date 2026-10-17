import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';
import { useBranches } from '../../hooks/useBranches';
import { tOr } from '../../utils/shiftBalances';

// T4.6: tasdiqlash so'rovlari (menejer/direktor) va limit qoidalari (admin/director).
// Shuningdek POS sahifalari uchun `useApprovalFlow` + `ApprovalModal` (kassir so'rov yuboradi va tasdiqni kutadi).
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const APPROVER_ROLES = ['admin', 'director', 'manager', 'super_admin'];
const RULE_ROLES = ['admin', 'director', 'super_admin'];
const ACTIONS = ['discount', 'price_override', 'expense', 'refund', 'sale_delete'];
const STATUSES = ['pending', 'approved', 'rejected', 'expired', 'used'];
const RULE_ROLE_OPTIONS = ['cashier', 'manager', 'accountant', 'warehouse'];
// Foizli limit faqat chegirma va narx tushirishda; qolganlarida summa
const PERCENT_ACTIONS = ['discount', 'price_override'];

const inputCls = 'w-full border-2 border-slate-200 rounded-xl px-3 py-2 text-sm font-semibold text-slate-700 outline-none focus:border-blue-500 bg-white';
const STATUS_TONE = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  used: 'bg-slate-100 text-slate-600',
  rejected: 'bg-red-100 text-red-700',
  expired: 'bg-slate-100 text-slate-500',
};

const errText = (e, fallback) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && !Array.isArray(d)) return d.message || fallback;
  return fallback;
};

const fmtDate = (v) => {
  if (!v) return '—';
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(String(v)) ? v : `${v}Z`; // server naive UTC yuboradi
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('uz-UZ', { dateStyle: 'short', timeStyle: 'short' });
};

/* ── POS uchun: tasdiq oqimi (so'rov yuborish -> kutish -> avtomatik qayta yuborish) ───────────── */

/**
 * `useApprovalFlow(onApproved)` — server 403 `approval_required` qaytarganda `begin(detail, ctx)` chaqiriladi.
 * Kassir "So'rov yuborish" ni bosadi (`send`), tasdiq 3 soniyada bir so'raladi; tasdiqlansa
 * `onApproved(requestId, ctx)` chaqiriladi (sotuv/qaytarishni `approval_id` bilan qayta yuboradi).
 */
export function useApprovalFlow(onApproved) {
  const { t } = useLang();
  const [approval, setApproval] = useState(null);
  const cbRef = useRef(onApproved);
  cbRef.current = onApproved;

  const begin = useCallback((detail, ctx = {}) => {
    setApproval({ detail, ctx, requestId: null, status: 'ask', reason: '' });
  }, []);
  const close = useCallback(() => setApproval(null), []);
  const setReason = useCallback((reason) => setApproval(a => (a ? { ...a, reason } : a)), []);

  const send = useCallback(async () => {
    const d = approval?.detail;
    if (!d) return;
    setApproval(a => (a ? { ...a, status: 'requesting' } : a));
    try {
      const r = await api.post('/approvals/requests', {
        action_type: d.request_action_type || d.action_type,
        amount: d.amount,
        payload: d.payload,
        branch_id: d.branch_id || undefined,
        reason: approval.reason || undefined,
      }, { _suppressToast: true });
      setApproval(a => (a ? { ...a, requestId: r.data.id, status: 'waiting' } : a));
    } catch (e) {
      toast.error(errText(e, tOr(t, 'auth.errGeneral', 'Xatolik yuz berdi')));
      setApproval(a => (a ? { ...a, status: 'ask' } : a));
    }
  }, [approval, t]);

  useEffect(() => {
    if (approval?.status !== 'waiting' || !approval.requestId) return undefined;
    const timer = setInterval(async () => {
      try {
        const r = await api.get(`/approvals/requests/${approval.requestId}`, { _silent: true, _suppressToast: true });
        const st = r.data?.status;
        if (st === 'approved') setApproval(a => (a ? { ...a, status: 'approved' } : a));
        else if (st === 'rejected' || st === 'expired') {
          setApproval(a => (a ? { ...a, status: st, note: r.data?.decision_note } : a));
        }
      } catch { /* keyingi urinishda */ }
    }, 3000);
    return () => clearInterval(timer);
  }, [approval?.status, approval?.requestId]);

  useEffect(() => {
    if (approval?.status !== 'approved') return;
    const { requestId, ctx } = approval;
    setApproval(a => (a ? { ...a, status: 'resubmitting' } : a));
    Promise.resolve(cbRef.current?.(requestId, ctx))
      .catch(() => {})
      .finally(() => setApproval(a => (a && a.status === 'resubmitting' ? null : a)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approval?.status]);

  return { approval, begin, close, send, setReason };
}

export function ApprovalModal({ flow }) {
  const { t } = useLang();
  const tf = (k, fb) => tOr(t, k, fb);
  const { approval, close, send, setReason } = flow;
  if (!approval) return null;
  const st = approval.status;
  const d = approval.detail || {};
  const suffix = d.unit === 'percent' ? '%' : '';
  const canSend = ['ask', 'requesting', 'rejected', 'expired'].includes(st);
  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-sm flex flex-col overflow-hidden">
        <div className="bg-amber-500 px-6 py-4">
          <h2 className="text-xl font-black text-white">{tf('approvals.pos.title', "Menejer tasdig'i kerak")}</h2>
        </div>
        <div className="p-6 space-y-4">
          <div className="text-sm font-bold text-slate-700">{d.message}</div>
          {d.limit != null && (
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 flex justify-between items-center">
              <span className="font-bold text-slate-500 uppercase text-xs">{tf('approvals.pos.limit', 'Limit')}</span>
              <span className="font-black text-lg text-amber-600">{d.actual}{suffix} / {d.limit}{suffix}</span>
            </div>
          )}
          {(st === 'ask' || st === 'requesting') && (
            <input
              type="text" value={approval.reason || ''} onChange={e => setReason(e.target.value)}
              placeholder={tf('approvals.pos.reason', 'Sabab (ixtiyoriy)')} className={inputCls}
            />
          )}
          {st === 'waiting' && (
            <div className="text-sm font-bold text-blue-600 animate-pulse">{tf('approvals.pos.waiting', "Menejer tasdig'i kutilmoqda...")}</div>
          )}
          {st === 'resubmitting' && (
            <div className="text-sm font-bold text-emerald-600">{tf('approvals.pos.resubmitting', 'Amal yuborilmoqda...')}</div>
          )}
          {st === 'rejected' && (
            <div className="text-sm font-bold text-red-600">
              {tf('approvals.pos.rejected', "So'rov rad etildi")}{approval.note ? `: ${approval.note}` : ''}
            </div>
          )}
          {st === 'expired' && (
            <div className="text-sm font-bold text-red-600">{tf('approvals.pos.expired', "So'rov muddati o'tdi")}</div>
          )}
        </div>
        <div className="p-6 pt-0 flex gap-3">
          <button onClick={close} disabled={st === 'resubmitting'} className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-600 font-bold rounded-xl active:scale-95 transition-all">
            {tf('approvals.pos.cancel', 'Bekor qilish')}
          </button>
          {canSend && (
            <button onClick={send} disabled={st === 'requesting'} className="flex-1 py-3 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-black rounded-xl active:scale-95 transition-all text-sm uppercase tracking-widest">
              {tf('approvals.pos.send', "So'rov yuborish")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── So'rovlar jadvali (menejer/direktor) ───────────────────────────────────────────────────── */

function RequestsTab({ user }) {
  const { t } = useLang();
  const tf = (k, fb) => tOr(t, k, fb);
  const { branches } = useBranches();
  const isApprover = APPROVER_ROLES.includes(user?.role);
  const [status, setStatus] = useState(isApprover ? 'pending' : '');
  const [branchId, setBranchId] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [decision, setDecision] = useState(null); // { row, approve, note }
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const params = {};
    if (status) params.status = status;
    if (branchId) params.branch_id = branchId;
    if (!isApprover) params.mine = true;
    return api.get('/approvals/requests', { params, _silent: true, _suppressToast: true })
      .then(r => setRows(Array.isArray(r.data) ? r.data : []))
      .catch(() => toast.error(tf('approvals.loadError', "So'rovlarni yuklab bo'lmadi")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, branchId, isApprover]);

  useEffect(() => {
    setLoading(true);
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const submitDecision = async () => {
    if (!decision) return;
    setBusy(true);
    try {
      await api.post(`/approvals/requests/${decision.row.id}/${decision.approve ? 'approve' : 'reject'}`,
        { note: decision.note || undefined }, { _suppressToast: true });
      toast.success(tf('approvals.decided', 'Qaror qabul qilindi'));
      setDecision(null);
      load();
    } catch (e) {
      toast.error(errText(e, tf('approvals.decideError', 'Qarorni saqlab bo‘lmadi')));
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-3 mb-4">
        <select value={status} onChange={e => setStatus(e.target.value)} className={`${inputCls} !w-auto`}>
          <option value="">{tf('approvals.filter.all', 'Barcha holatlar')}</option>
          {STATUSES.map(s => <option key={s} value={s}>{tf(`approvals.status.${s}`, s)}</option>)}
        </select>
        {isApprover && (
          <select value={branchId} onChange={e => setBranchId(e.target.value)} className={`${inputCls} !w-auto`}>
            <option value="">{tf('approvals.filter.allBranches', 'Barcha filiallar')}</option>
            {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-3">{tf('approvals.col.date', 'Sana')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.col.action', 'Amal')}</th>
              <th className="text-right px-4 py-3">{tf('approvals.col.amount', 'Summa')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.col.requester', "So'radi")}</th>
              <th className="text-left px-4 py-3">{tf('approvals.col.branch', 'Filial')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.col.reason', 'Sabab')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.col.status', 'Holat')}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">{tf('approvals.empty', "So'rovlar yo'q")}</td></tr>
            )}
            {rows.map(r => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDate(r.created_at)}</td>
                <td className="px-4 py-3 font-semibold text-slate-800">{tf(`approvals.action.${r.action_type}`, r.action_type)}</td>
                <td className="px-4 py-3 text-right font-bold text-slate-800 whitespace-nowrap">{fmt(r.amount)}</td>
                <td className="px-4 py-3 text-slate-600">{r.requested_by_name || '—'}</td>
                <td className="px-4 py-3 text-slate-600">{r.branch_name || '—'}</td>
                <td className="px-4 py-3 text-slate-500 max-w-[16rem] truncate" title={r.reason || ''}>{r.reason || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${STATUS_TONE[r.status] || STATUS_TONE.expired}`}>
                    {tf(`approvals.status.${r.status}`, r.status)}
                  </span>
                  {r.decided_by_name && <div className="text-[11px] text-slate-400 mt-0.5">{r.decided_by_name}</div>}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {isApprover && r.status === 'pending' && r.requested_by !== user?.id && (
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => setDecision({ row: r, approve: true, note: '' })} className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-bold rounded-lg">
                        {tf('approvals.approve', 'Tasdiqlash')}
                      </button>
                      <button onClick={() => setDecision({ row: r, approve: false, note: '' })} className="px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white text-xs font-bold rounded-lg">
                        {tf('approvals.reject', 'Rad etish')}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {decision && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-4">
            <h3 className="font-black text-slate-800">
              {decision.approve ? tf('approvals.approve', 'Tasdiqlash') : tf('approvals.reject', 'Rad etish')}
              {' — '}{tf(`approvals.action.${decision.row.action_type}`, decision.row.action_type)} · {fmt(decision.row.amount)}
            </h3>
            <textarea
              rows={3} value={decision.note} onChange={e => setDecision(d => ({ ...d, note: e.target.value }))}
              placeholder={tf('approvals.notePlaceholder', 'Izoh (ixtiyoriy)')} className={inputCls}
            />
            <div className="flex gap-3">
              <button onClick={() => setDecision(null)} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl">
                {tf('approvals.pos.cancel', 'Bekor qilish')}
              </button>
              <button onClick={submitDecision} disabled={busy} className={`flex-1 py-2.5 text-white font-bold rounded-xl disabled:opacity-50 ${decision.approve ? 'bg-emerald-500 hover:bg-emerald-600' : 'bg-red-500 hover:bg-red-600'}`}>
                {busy ? '...' : tf('approvals.confirm', 'Tasdiqlayman')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Qoidalar (Sozlamalar: "Tasdiqlash qoidalari") ──────────────────────────────────────────── */

const emptyRule = () => ({
  id: null, action_type: 'discount', role: 'cashier', branch_id: '', threshold_percent: '', threshold_amount: '',
  mode: 'require_approval', is_active: true,
});

function RulesTab() {
  const { t } = useLang();
  const tf = (k, fb) => tOr(t, k, fb);
  const { branches } = useBranches();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.get('/approvals/rules', { _silent: true, _suppressToast: true })
      .then(r => setRules(Array.isArray(r.data) ? r.data : []))
      .catch(() => toast.error(tf('approvals.rules.loadError', "Qoidalarni yuklab bo'lmadi")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { load(); }, [load]);

  const openEdit = (r) => setForm({
    id: r.id, action_type: r.action_type, role: r.role || '', branch_id: r.branch_id ? String(r.branch_id) : '',
    threshold_percent: r.threshold_percent ?? '', threshold_amount: r.threshold_amount ?? '',
    mode: r.mode, is_active: !!r.is_active,
  });

  const save = async (e) => {
    e.preventDefault();
    const body = {
      action_type: form.action_type,
      role: form.role || null,
      branch_id: form.branch_id ? Number(form.branch_id) : null,
      threshold_percent: PERCENT_ACTIONS.includes(form.action_type) && form.threshold_percent !== '' ? Number(form.threshold_percent) : null,
      threshold_amount: form.threshold_amount !== '' ? Number(form.threshold_amount) : null,
      mode: form.mode,
      is_active: form.is_active,
    };
    setSaving(true);
    try {
      if (form.id) await api.patch(`/approvals/rules/${form.id}`, body, { _suppressToast: true });
      else await api.post('/approvals/rules', body, { _suppressToast: true });
      toast.success(tf('approvals.rules.saved', 'Qoida saqlandi'));
      setForm(null);
      load();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(Array.isArray(d) ? (d[0]?.msg || tf('approvals.rules.saveError', "Qoidani saqlab bo'lmadi")) : errText(err, tf('approvals.rules.saveError', "Qoidani saqlab bo'lmadi")));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (r) => {
    if (!window.confirm(tf('approvals.rules.confirmDelete', "Qoida o'chirilsinmi?"))) return;
    try {
      await api.delete(`/approvals/rules/${r.id}`, { _suppressToast: true });
      toast.success(tf('approvals.rules.deleted', "Qoida o'chirildi"));
      load();
    } catch (err) {
      toast.error(errText(err, tf('approvals.rules.saveError', "Qoidani saqlab bo'lmadi")));
    }
  };

  const limitText = (r) => {
    const parts = [];
    if (r.threshold_percent != null) parts.push(`${r.threshold_percent}%`);
    if (r.threshold_amount != null) parts.push(fmt(r.threshold_amount));
    return parts.length ? parts.join(' / ') : tf('approvals.rules.always', 'Har doim');
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-slate-500 max-w-2xl">
          {tf('approvals.rules.hint', "Qoida bo'lmasa, limit ishlamaydi. Admin va direktor qoidalardan ozod (limitdan oshgan amallari audit'ga yoziladi).")}
        </p>
        <button onClick={() => setForm(emptyRule())} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl whitespace-nowrap">
          + {tf('approvals.rules.add', "Qoida qo'shish")}
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-3">{tf('approvals.col.action', 'Amal')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.rules.role', 'Rol')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.col.branch', 'Filial')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.rules.limit', 'Limit')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.rules.mode', 'Rejim')}</th>
              <th className="text-left px-4 py-3">{tf('approvals.rules.active', 'Faol')}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">…</td></tr>}
            {!loading && rules.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">{tf('approvals.rules.empty', "Qoidalar yo'q")}</td></tr>
            )}
            {rules.map(r => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className="px-4 py-3 font-semibold text-slate-800">{tf(`approvals.action.${r.action_type}`, r.action_type)}</td>
                <td className="px-4 py-3 text-slate-600">{r.role || tf('approvals.rules.allRoles', 'Barcha rollar')}</td>
                <td className="px-4 py-3 text-slate-600">{r.branch_name || tf('approvals.filter.allBranches', 'Barcha filiallar')}</td>
                <td className="px-4 py-3 text-slate-800 font-bold">{limitText(r)}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${r.mode === 'block' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                    {tf(`approvals.rules.mode.${r.mode}`, r.mode)}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{r.is_active ? '✓' : '—'}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <button onClick={() => openEdit(r)} className="px-3 py-1.5 text-blue-600 hover:bg-blue-50 text-xs font-bold rounded-lg">{tf('common.edit', 'Tahrirlash')}</button>
                  <button onClick={() => remove(r)} className="px-3 py-1.5 text-red-600 hover:bg-red-50 text-xs font-bold rounded-lg">{tf('common.delete', "O'chirish")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <form onSubmit={save} className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-5 space-y-3">
            <h3 className="font-black text-slate-800">
              {form.id ? tf('approvals.rules.edit', 'Qoidani tahrirlash') : tf('approvals.rules.add', "Qoida qo'shish")}
            </h3>
            <label className="block text-xs font-bold text-slate-500">
              {tf('approvals.col.action', 'Amal')}
              <select value={form.action_type} onChange={e => setForm(f => ({ ...f, action_type: e.target.value }))} className={inputCls}>
                {ACTIONS.map(a => <option key={a} value={a}>{tf(`approvals.action.${a}`, a)}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs font-bold text-slate-500">
                {tf('approvals.rules.role', 'Rol')}
                <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} className={inputCls}>
                  <option value="">{tf('approvals.rules.allRoles', 'Barcha rollar')}</option>
                  {RULE_ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
              <label className="block text-xs font-bold text-slate-500">
                {tf('approvals.col.branch', 'Filial')}
                <select value={form.branch_id} onChange={e => setForm(f => ({ ...f, branch_id: e.target.value }))} className={inputCls}>
                  <option value="">{tf('approvals.filter.allBranches', 'Barcha filiallar')}</option>
                  {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {PERCENT_ACTIONS.includes(form.action_type) && (
                <label className="block text-xs font-bold text-slate-500">
                  {tf('approvals.rules.percent', 'Limit, %')}
                  <input type="number" min="0" max="100" step="0.01" value={form.threshold_percent}
                    onChange={e => setForm(f => ({ ...f, threshold_percent: e.target.value }))} className={inputCls} />
                </label>
              )}
              <label className="block text-xs font-bold text-slate-500">
                {tf('approvals.rules.amount', 'Limit, summa')}
                <input type="number" min="0" step="1" value={form.threshold_amount}
                  onChange={e => setForm(f => ({ ...f, threshold_amount: e.target.value }))} className={inputCls} />
              </label>
            </div>
            <p className="text-[11px] text-slate-400">{tf('approvals.rules.limitHint', "Limit kiritilmasa, qoida shu amalning har biriga qo'llanadi.")}</p>
            <label className="block text-xs font-bold text-slate-500">
              {tf('approvals.rules.mode', 'Rejim')}
              <select value={form.mode} onChange={e => setForm(f => ({ ...f, mode: e.target.value }))} className={inputCls}>
                <option value="require_approval">{tf('approvals.rules.mode.require_approval', "Tasdiq talab qilinadi")}</option>
                <option value="block">{tf('approvals.rules.mode.block', 'Taqiqlash')}</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <input type="checkbox" checked={form.is_active} onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} />
              {tf('approvals.rules.active', 'Faol')}
            </label>
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={() => setForm(null)} className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl">
                {tf('approvals.pos.cancel', 'Bekor qilish')}
              </button>
              <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-xl">
                {saving ? '...' : tf('common.save', 'Saqlash')}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

/* ── Sahifa ─────────────────────────────────────────────────────────────────────────────────── */

export default function Approvals() {
  const { t } = useLang();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const canRules = RULE_ROLES.includes(user?.role);
  const tab = params.get('tab') === 'rules' && canRules ? 'rules' : 'requests';
  const tf = (k, fb) => tOr(t, k, fb);

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-800 mb-1">{tf('approvals.title', 'Tasdiqlashlar')}</h1>
      <p className="text-sm text-slate-500 mb-5">{tf('approvals.subtitle', "Chegirma, narx tushirish, xarajat va qaytarish uchun tasdiq so'rovlari")}</p>

      <div className="flex gap-2 mb-5">
        <button
          onClick={() => setParams({})}
          className={`px-4 py-2 rounded-xl text-sm font-bold ${tab === 'requests' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}
        >{tf('approvals.tabRequests', "So'rovlar")}</button>
        {canRules && (
          <button
            onClick={() => setParams({ tab: 'rules' })}
            className={`px-4 py-2 rounded-xl text-sm font-bold ${tab === 'rules' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}
          >{tf('approvals.tabRules', 'Qoidalar')}</button>
        )}
      </div>

      {tab === 'rules' ? <RulesTab /> : <RequestsTab user={user} />}
    </div>
  );
}
