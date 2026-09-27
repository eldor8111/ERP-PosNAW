import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { X, Search } from 'lucide-react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

/** Agentga mijozlarni ommaviy biriktirish / olib tashlash */
export default function AssignCustomersModal({ agent, onClose, onSaved }) {
  const { t } = useLang();
  const [customers, setCustomers] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [initial, setInitial] = useState(new Set());
  const [q, setQ] = useState('');
  const [onlyMine, setOnlyMine] = useState(false);
  const [days, setDays] = useState([1, 2, 3, 4, 5, 6]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/customers', { params: { limit: 2000 } }).then(r => {
      setCustomers(r.data);
      const mine = new Set(r.data.filter(c => c.agent_id === agent.id).map(c => c.id));
      setSelected(new Set(mine)); setInitial(mine);
    }).catch(() => setCustomers([]));
  }, [agent.id]);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (customers || []).filter(c =>
      (!onlyMine || selected.has(c.id)) &&
      (!s || c.name.toLowerCase().includes(s) || c.phone?.includes(s) || c.district?.toLowerCase().includes(s)));
  }, [customers, q, onlyMine, selected]);

  const toggle = (id) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const add = [...selected].filter(id => !initial.has(id));
  const remove = [...initial].filter(id => !selected.has(id));

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.post(`/field-staff/agents/${agent.id}/customers`, { add, remove, work_days: days });
      toast.success(t('fieldStaff.assignSaved', { total: data.total }));
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-line shrink-0">
          <div>
            <h3 className="text-base font-bold text-ink-900">{t('fieldStaff.assignTitle')}: {agent.name}</h3>
            <p className="text-xs text-ink-500">{t('fieldStaff.assignHint')}</p>
          </div>
          <button onClick={onClose} className="text-ink-300 hover:text-ink-500"><X className="size-5" /></button>
        </div>

        <div className="px-6 pt-4 space-y-3 shrink-0">
          <div className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 px-3 border border-line rounded-xl bg-surface">
              <Search className="size-4 text-ink-300" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('m.searchCustomer')} className="flex-1 py-2.5 text-sm bg-transparent outline-none" />
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-500 px-2 whitespace-nowrap">
              <input type="checkbox" checked={onlyMine} onChange={e => setOnlyMine(e.target.checked)} />{t('fieldStaff.onlySelected')}
            </label>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-ink-500">{t('fieldStaff.defaultDays')}:</span>
            {[1, 2, 3, 4, 5, 6, 7].map(d => {
              const on = days.includes(d);
              return (
                <button key={d} type="button" onClick={() => setDays(on ? days.filter(x => x !== d) : [...days, d].sort())}
                  className={`w-9 py-1 rounded-lg text-xs font-bold border ${on ? 'bg-brand text-white border-brand' : 'border-line text-ink-500'}`}>
                  {t(`weekday.short${d}`)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-3 space-y-1">
          {customers === null && <div className="py-10 text-center text-ink-300">…</div>}
          {list.map(c => {
            const on = selected.has(c.id);
            const other = c.agent_id && c.agent_id !== agent.id;
            return (
              <label key={c.id} className={`flex items-center gap-3 px-3 py-2 rounded-xl cursor-pointer ${on ? 'bg-brand/5' : 'hover:bg-surface-sunken'}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(c.id)} className="size-4" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-ink-900 truncate">{c.name}</div>
                  <div className="text-xs text-ink-300 truncate">{[c.phone, c.district, c.address].filter(Boolean).join(' · ') || '—'}</div>
                </div>
                {other && <span className="text-[11px] text-warning shrink-0">{t('fieldStaff.otherAgent')}</span>}
                {c.lat == null && <span className="text-[11px] text-ink-300 shrink-0">📍—</span>}
              </label>
            );
          })}
        </div>

        <div className="px-6 py-4 border-t border-line flex items-center justify-between gap-3 shrink-0">
          <span className="text-sm text-ink-500">
            {t('fieldStaff.selectedCount', { count: selected.size })}
            {(add.length > 0 || remove.length > 0) && <> · <span className="text-success">+{add.length}</span> / <span className="text-danger">−{remove.length}</span></>}
          </span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-4 py-2.5 border border-line text-ink-500 text-sm font-medium rounded-xl">{t('common.cancel')}</button>
            <button onClick={save} disabled={saving || (add.length === 0 && remove.length === 0)}
              className="px-5 py-2.5 bg-brand hover:bg-brand-deep disabled:opacity-50 text-white text-sm font-semibold rounded-xl">
              {saving ? t('common.saving') : t('common.save')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
