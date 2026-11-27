import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { Plus, Copy, Trash2, Tablet } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R6.1: ofitsiant planshetlari. Menejer planshetni ulaydi: maxfiy havola bir marta ko'rsatiladi, planshetda
// ochilgach saqlanadi. Keyin xodimlar shu planshetda ismini tanlab PIN bilan kiradi. Backend: restaurant_terminal.py.

const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';
const btnPrimary = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50';
const btnGhost = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold';

const timeFmt = iso => (iso ? new Date(iso).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');

export default function RestaurantTerminals() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [rows, setRows] = useState([]);
  const [name, setName] = useState('');
  const [branchId, setBranchId] = useState(null);
  const [created, setCreated] = useState(null);   // {name, link}
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  const load = useCallback(() => {
    api.get('/restaurant/terminals').then(r => setRows(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restTerm.failed')));
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const r = await api.post('/restaurant/terminals', { name: name.trim(), branch_id: branchId });
      setCreated({ name: r.data.name, link: `${window.location.origin}/waiter?t=${encodeURIComponent(r.data.token)}` });
      setName('');
      load();
    } catch (err) { toast.error(err.response?.data?.detail || t('restTerm.failed')); }
    finally { setBusy(false); }
  };
  const revoke = async row => {
    if (!window.confirm(`${t('restTerm.confirmRevoke')}: ${row.name}?`)) return;
    try {
      await api.delete(`/restaurant/terminals/${row.id}`);
      toast.success(t('restTerm.revoked'));
      load();
    } catch (err) { toast.error(err.response?.data?.detail || t('restTerm.failed')); }
  };
  const copy = async text => {
    try { await navigator.clipboard.writeText(text); toast.success(t('restTerm.copied')); }
    catch { toast.error(t('restTerm.copyFailed')); }
  };

  return (
    <div className="space-y-4 max-w-4xl">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{t('restTerm.title')}</h1>
        <p className="text-sm text-slate-500">{t('restTerm.desc')}</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="text-sm font-bold text-slate-800">{t('restTerm.add')}</div>
        <div className="flex flex-wrap gap-2">
          <input className={`${inputCls} flex-1 min-w-[200px]`} value={name} maxLength={100} placeholder={t('restTerm.namePh')}
                 onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') create(); }} />
          {branches.length > 1 && (
            <select className="px-2 py-2 border border-slate-200 rounded-lg text-sm" value={branchId ?? ''} onChange={e => setBranchId(Number(e.target.value))}>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          )}
          <button className={btnPrimary} disabled={busy || !name.trim()} onClick={create}><Plus className="w-4 h-4" />{t('restTerm.create')}</button>
        </div>
        {created && (
          <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 space-y-2">
            <div className="text-sm font-semibold text-amber-900">{t('restTerm.linkTitle')}: {created.name}</div>
            <p className="text-xs text-amber-900">{t('restTerm.linkHint')}</p>
            <div className="flex gap-2">
              <code className="flex-1 text-xs bg-white border border-amber-200 rounded p-2 break-all">{created.link}</code>
              <button className={btnGhost} onClick={() => copy(created.link)}><Copy className="w-4 h-4" />{t('restTerm.copy')}</button>
            </div>
          </div>
        )}
        <p className="text-xs text-slate-500">{t('restTerm.pinHint')}</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 text-sm font-bold text-slate-800">{t('restTerm.list')}</div>
        <div className="divide-y divide-slate-100">
          {rows.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restTerm.none')}</div>}
          {rows.map(row => (
            <div key={row.id} className="px-4 py-2.5 flex items-center gap-3 text-sm">
              <Tablet className="w-4 h-4 text-slate-400" />
              <span className="font-semibold text-slate-800">{row.name}</span>
              <span className="text-slate-500">{row.branch_name}</span>
              <span className="ml-auto text-xs text-slate-400">
                {row.last_used_at ? `${t('restTerm.lastUsed')}: ${timeFmt(row.last_used_at)}` : t('restTerm.notUsed')}
              </span>
              <button className="p-1.5 text-slate-400 hover:text-rose-600" title={t('restTerm.revoke')} onClick={() => revoke(row)}>
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
