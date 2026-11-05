// Super admin: E-code AI paketlari (narx, oylik so'rov limiti, xodimga kunlik limit) va ishlatilish hisoboti.
import { useCallback, useEffect, useState } from 'react';
import api from '../../api/axios';
import { toast } from '../../utils/toast';

const EMPTY = {
  code: '', name: '', description: '', price_per_month: 0, is_active: false, sort_order: 90,
  ai_monthly_limit: 0, ai_daily_user_limit: 0, ai_allow_actions: true, ai_allow_vision: true,
};

const fmt = (n) => Number(n || 0).toLocaleString('ru-RU');
const thisMonth = () => new Date().toISOString().slice(0, 7);

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-semibold text-slate-500 mb-1">{label}</span>
      {children}
    </label>
  );
}

const inputCls = 'w-full px-2.5 py-1.5 border border-slate-300 rounded-lg text-[13px] focus:border-blue-500 outline-none';

function PackageForm({ initial, isNew, onSaved, onCancel }) {
  const [f, setF] = useState(initial);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const save = async () => {
    if (!f.name.trim()) { toast.warn('Nomini kiriting'); return; }
    setSaving(true);
    try {
      const body = {
        ...f,
        price_per_month: Number(f.price_per_month) || 0,
        sort_order: Number(f.sort_order) || 0,
        ai_monthly_limit: Number(f.ai_monthly_limit) || 0,
        ai_daily_user_limit: Number(f.ai_daily_user_limit) || 0,
      };
      if (isNew) await api.post('/ai/assistant/admin/packages', body);
      else await api.put(`/ai/assistant/admin/packages/${f.code}`, body);
      toast.success('Saqlandi');
      onSaved();
    } catch { /* toast axios da */ } finally { setSaving(false); }
  };
  return (
    <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/60 space-y-3">
      <div className="grid sm:grid-cols-3 gap-3">
        {isNew && (
          <Field label="Kod qo'shimchasi (masalan pro)">
            <input className={inputCls} value={f.code} onChange={(e) => set('code', e.target.value)} placeholder="pro" />
          </Field>
        )}
        <Field label="Nomi"><input className={inputCls} value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="Oylik narx, so'm"><input type="number" min="0" className={inputCls} value={f.price_per_month} onChange={(e) => set('price_per_month', e.target.value)} /></Field>
        <Field label="Oylik so'rov limiti (0 = cheklanmagan)"><input type="number" min="0" className={inputCls} value={f.ai_monthly_limit} onChange={(e) => set('ai_monthly_limit', e.target.value)} /></Field>
        <Field label="Xodimga kunlik limit (0 = cheklanmagan)"><input type="number" min="0" className={inputCls} value={f.ai_daily_user_limit} onChange={(e) => set('ai_daily_user_limit', e.target.value)} /></Field>
        <Field label="Tartib"><input type="number" className={inputCls} value={f.sort_order} onChange={(e) => set('sort_order', e.target.value)} /></Field>
      </div>
      <Field label="Tavsif">
        <textarea rows={2} className={inputCls} value={f.description || ''} onChange={(e) => set('description', e.target.value)} />
      </Field>
      <div className="flex flex-wrap gap-4 text-[13px] text-slate-700">
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)} />Faol (sotuvda)</label>
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={f.ai_allow_actions} onChange={(e) => set('ai_allow_actions', e.target.checked)} />Tasdiqli amallar</label>
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={f.ai_allow_vision} onChange={(e) => set('ai_allow_vision', e.target.checked)} />Rasm yuborish</label>
      </div>
      <div className="flex gap-2">
        <button type="button" disabled={saving} onClick={save} className="px-4 py-1.5 rounded-lg bg-blue-600 text-white text-[13px] font-semibold hover:bg-blue-700 disabled:opacity-50">Saqlash</button>
        <button type="button" onClick={onCancel} className="px-4 py-1.5 rounded-lg border border-slate-300 text-[13px] font-semibold text-slate-700 hover:bg-white">Bekor</button>
      </div>
    </div>
  );
}

export default function SuperAdminAiTab() {
  const [pkgs, setPkgs] = useState([]);
  const [editing, setEditing] = useState(null);   // code | 'new' | null
  const [month, setMonth] = useState(thisMonth());
  const [report, setReport] = useState(null);

  const loadPkgs = useCallback(async () => {
    try { const r = await api.get('/ai/assistant/admin/packages'); setPkgs(r.data || []); } catch { /* toast */ }
  }, []);
  const loadReport = useCallback(async () => {
    try { const r = await api.get('/ai/assistant/admin/usage', { params: { month } }); setReport(r.data); } catch { /* toast */ }
  }, [month]);

  useEffect(() => { loadPkgs(); }, [loadPkgs]);
  useEffect(() => { loadReport(); }, [loadReport]);

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h2 className="text-[15px] font-bold text-slate-900">E-code AI paketlari</h2>
            <p className="text-xs text-slate-500">Korxona admini paketni Tariflar bo'limida balansdan 1, 3, 6 yoki 12 oyga sotib oladi. Bir vaqtda bitta AI darajasi faol bo'ladi.</p>
          </div>
          <button type="button" onClick={() => setEditing('new')} className="shrink-0 px-3 py-1.5 rounded-lg border border-slate-300 text-[13px] font-semibold text-slate-700 hover:bg-slate-50">Yangi daraja</button>
        </div>
        {editing === 'new' && (
          <div className="mb-3"><PackageForm initial={EMPTY} isNew onSaved={() => { setEditing(null); loadPkgs(); }} onCancel={() => setEditing(null)} /></div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase text-slate-400 border-b border-slate-200">
                <th className="py-2 pr-3">Kod</th><th className="py-2 pr-3">Nomi</th><th className="py-2 pr-3">Narx / oy</th>
                <th className="py-2 pr-3">Oylik limit</th><th className="py-2 pr-3">Kunlik (xodim)</th><th className="py-2 pr-3">Amallar</th>
                <th className="py-2 pr-3">Rasm</th><th className="py-2 pr-3">Holati</th><th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {pkgs.map((p) => (
                editing === p.code ? (
                  <tr key={p.code}><td colSpan={9} className="py-2">
                    <PackageForm initial={p} onSaved={() => { setEditing(null); loadPkgs(); }} onCancel={() => setEditing(null)} />
                  </td></tr>
                ) : (
                  <tr key={p.code} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-mono text-[12px] text-slate-500">{p.code}</td>
                    <td className="py-2 pr-3 font-semibold text-slate-800">{p.name}</td>
                    <td className="py-2 pr-3">{fmt(p.price_per_month)} so'm</td>
                    <td className="py-2 pr-3">{p.ai_monthly_limit ? fmt(p.ai_monthly_limit) : 'cheklanmagan'}</td>
                    <td className="py-2 pr-3">{p.ai_daily_user_limit ? fmt(p.ai_daily_user_limit) : 'cheklanmagan'}</td>
                    <td className="py-2 pr-3">{p.ai_allow_actions ? 'Ha' : "Yo'q"}</td>
                    <td className="py-2 pr-3">{p.ai_allow_vision ? 'Ha' : "Yo'q"}</td>
                    <td className="py-2 pr-3">
                      <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${p.is_active ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : 'text-slate-500 bg-slate-50 border-slate-200'}`}>
                        {p.is_active ? 'Faol' : 'Nofaol'}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <button type="button" onClick={() => setEditing(p.code)} className="px-2.5 py-1 rounded-lg border border-slate-300 text-[12px] font-semibold text-slate-700 hover:bg-slate-50">Tahrirlash</button>
                    </td>
                  </tr>
                )
              ))}
              {pkgs.length === 0 && <tr><td colSpan={9} className="py-4 text-slate-400">AI paketlari yo'q (migratsiya bajarilganini tekshiring)</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <div>
            <h2 className="text-[15px] font-bold text-slate-900">Ishlatilish hisoboti</h2>
            <p className="text-xs text-slate-500">So'rov = foydalanuvchining bitta xabari. Xarajat Claude API narxlari bo'yicha (USD).</p>
          </div>
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="px-2.5 py-1.5 border border-slate-300 rounded-lg text-[13px]" />
        </div>
        {report && (
          <>
            <div className="flex gap-6 mb-3 text-[13px]">
              <div><span className="text-slate-500">So'rovlar: </span><span className="font-semibold">{fmt(report.total_prompts)}</span></div>
              <div><span className="text-slate-500">Xarajat: </span><span className="font-semibold">${Number(report.total_cost_usd || 0).toFixed(2)}</span></div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase text-slate-400 border-b border-slate-200">
                    <th className="py-2 pr-3">Korxona</th><th className="py-2 pr-3">Paket</th><th className="py-2 pr-3">So'rovlar</th>
                    <th className="py-2 pr-3">Kirish</th><th className="py-2 pr-3">Chiqish</th><th className="py-2 pr-3">Kesh o'qish</th>
                    <th className="py-2 pr-3">Kesh yozish</th><th className="py-2">Xarajat</th>
                  </tr>
                </thead>
                <tbody>
                  {report.items.map((r) => (
                    <tr key={r.company_id} className="border-b border-slate-100">
                      <td className="py-2 pr-3 font-semibold text-slate-800">{r.company_name}</td>
                      <td className="py-2 pr-3">{r.package || '-'}{r.monthly_limit ? ` (${fmt(r.monthly_limit)})` : ''}</td>
                      <td className="py-2 pr-3">{fmt(r.prompts)}</td>
                      <td className="py-2 pr-3">{fmt(r.input_tokens)}</td>
                      <td className="py-2 pr-3">{fmt(r.output_tokens)}</td>
                      <td className="py-2 pr-3">{fmt(r.cache_read_tokens)}</td>
                      <td className="py-2 pr-3">{fmt(r.cache_write_tokens)}</td>
                      <td className="py-2 font-semibold">${Number(r.cost_usd || 0).toFixed(3)}</td>
                    </tr>
                  ))}
                  {report.items.length === 0 && <tr><td colSpan={8} className="py-4 text-slate-400">Bu oyda so'rovlar yo'q</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
