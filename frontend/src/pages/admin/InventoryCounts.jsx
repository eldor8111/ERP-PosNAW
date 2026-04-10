import { useState, useEffect, useCallback, useMemo } from 'react';
import { useLang } from '../../context/LangContext';
import api from '../../api/axios';

/* ─────────── helpers ─────────── */
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('uz-UZ') : '—';
const fmtDt   = (d) => d ? new Date(d).toLocaleString('uz-UZ') : '—';
const fmtQ    = (v) => (v !== null && v !== undefined) ? Number(v).toLocaleString('uz-UZ', { maximumFractionDigits: 3 }) : '—';

const STATUS = {
  draft:       { l: 'Qoralama',    c: 'bg-slate-100 text-slate-600',     dot: 'bg-slate-400' },
  in_progress: { l: 'Jarayonda',   c: 'bg-amber-100 text-amber-700',     dot: 'bg-amber-500' },
  completed:   { l: 'Yakunlangan', c: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-500' },
  cancelled:   { l: 'Bekor',       c: 'bg-red-100 text-red-500',         dot: 'bg-red-400' },
};

function Loader() {
  const { t } = useLang();
return (
    <div className="flex items-center justify-center py-24">
      <div className="w-9 h-9 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function StatusBadge({ status }) {
  const { t } = useLang();
const m = STATUS[status] || { l: status, c: 'bg-slate-100 text-slate-600', dot: 'bg-slate-400' };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${m.c}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {m.l}
    </span>
  );
}

/* ─────────── Print helpers ─────────── */
function doPrint(html, t) {
  const old = document.getElementById('__inv_iframe__');
  if (old) old.remove();
  const f = document.createElement('iframe');
  f.id = '__inv_iframe__';
  f.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;border:none;';
  document.body.appendChild(f);
  f.contentWindow.document.open();
  f.contentWindow.document.write(html);
  f.contentWindow.document.close();
}

function printCountSheet(count, t) {
  const rows = count.items.map((item, i) => `
    <tr>
      <td style="text-align:center;width:30px">${i + 1}</td>
      <td style="width:80px">${item.product_sku || ''}</td>
      <td>${item.product_name}</td>
      <td style="width:50px;text-align:center">${item.product_unit || 'dona'}</td>
      <td style="text-align:right;width:80px">${fmtQ(item.system_qty)}</td>
      <td style="border:1px solid #bbb;width:90px">&nbsp;</td>
      <td style="border:1px solid #bbb;min-width:120px">&nbsp;</td>
    </tr>`).join('');

  doPrint(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Sanash varaqasi - ${count.number}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:Arial,sans-serif;font-size:11px;padding:15px}
  h2{font-size:14px;text-align:center;margin-bottom:3px;font-weight:bold}
  .meta{text-align:center;font-size:10px;color:#555;margin-bottom:12px}
  table{width:100%;border-collapse:collapse}
  th,td{border:1px solid #aaa;padding:4px 6px;font-size:10px}
  th{background:#f0f0f0;font-weight:bold;text-align:center}
  .sign{display:flex;justify-content:space-between;margin-top:20px;font-size:10px;gap:20px}
  .sign div{flex:1;border-top:1px solid #aaa;padding-top:4px}
  @media print{@page{margin:8mm}}
</style></head><body onload="window.print()">
  <h2>SANASH VARAQASI</h2>
  <div class="meta">
    \u2116 ${count.number} &nbsp;|&nbsp; Ombor: ${count.warehouse_name} &nbsp;|&nbsp;
    Sana: ${fmtDate(count.created_at)}${count.note ? ` &nbsp;|&nbsp; ${count.note}` : ''}
  </div>
  <table>
    <thead><tr>
      <th>\u2116</th><th>SKU</th><th>Mahsulot nomi</th><th>O'lchov</th>
      <th>Tizim qoldig'i</th><th>Faktik soni</th><th>Izoh / Sabab</th>
    </tr></thead>
    <tbody>${rows || "<tr><td colspan='7' style='text-align:center;padding:12px'>Mahsulotlar yo'q</td></tr>"}</tbody>
  </table>
  <div class="sign">
    <div>Inventarizatsiya o'tkazuvchi: ___________________</div>
    <div>Sana: _______________________</div>
    <div>Imzo: _______________________</div>
  </div>
</body></html>`);
}

function printVarianceReport(count, t) {
  const variances = count.items.filter(i => i.variance !== null && Number(i.variance) !== 0);
  const rows = variances.map((item, i) => {
    const v = Number(item.variance);
    const vStyle = v > 0 ? 'color:#16a34a;font-weight:bold' : 'color:#dc2626;font-weight:bold';
    return `<tr>
      <td style="text-align:center;width:30px">${i + 1}</td>
      <td style="width:80px">${item.product_sku || ''}</td>
      <td>${item.product_name}</td>
      <td style="text-align:right;width:80px">${fmtQ(item.system_qty)}</td>
      <td style="text-align:right;width:80px">${fmtQ(item.counted_qty)}</td>
      <td style="text-align:right;width:90px;${vStyle}">${v > 0 ? '+' : ''}${fmtQ(v)}</td>
      <td>${item.variance_reason || ''}</td>
    </tr>`;
  }).join('');

  doPrint(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Tafovutlar - ${count.number}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:Arial,sans-serif;font-size:11px;padding:15px}
  h2{font-size:14px;text-align:center;margin-bottom:3px;font-weight:bold}
  .meta{text-align:center;font-size:10px;color:#555;margin-bottom:12px}
  .summary{display:flex;gap:16px;justify-content:center;margin-bottom:10px;font-size:10px;flex-wrap:wrap}
  .summary span{background:#f8f8f8;border:1px solid #ddd;border-radius:4px;padding:3px 10px}
  table{width:100%;border-collapse:collapse}
  th,td{border:1px solid #aaa;padding:4px 6px;font-size:10px}
  th{background:#f0f0f0;font-weight:bold;text-align:center}
  @media print{@page{margin:8mm}}
</style></head><body onload="window.print()">
  <h2>TAFOVUTLAR RO'YXATI</h2>
  <div class="meta">
    \u2116 ${count.number} &nbsp;|&nbsp; Ombor: ${count.warehouse_name} &nbsp;|&nbsp;
    Sana: ${fmtDt(count.finished_at || count.created_at)}
  </div>
  <div class="summary">
    <span>Jami: <b>${count.items.length}</b></span>
    <span>Tafovutlar: <b>${variances.length}</b></span>
    <span>Ortiqcha (+): <b>${variances.filter(i => Number(i.variance) > 0).length}</b></span>
    <span>Kamomad (\u2212): <b>${variances.filter(i => Number(i.variance) < 0).length}</b></span>
  </div>
  <table>
    <thead><tr>
      <th>\u2116</th><th>SKU</th><th>Mahsulot nomi</th>
      <th>Tizim</th><th>Faktik</th><th>Tafovut</th><th>Sababi</th>
    </tr></thead>
    <tbody>${rows || "<tr><td colspan='7' style='text-align:center;padding:12px'>Tafovutlar yo'q</td></tr>"}</tbody>
  </table>
</body></html>`);
}

/* ─────────── Create Modal ─────────── */
function CreateModal({ onClose, onCreated }) {
  const { t } = useLang();
const [warehouses, setWarehouses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [form, setForm]   = useState({ warehouse_id: '', note: '', countType: 'full', catIds: [] });
  const [saving, setSaving] = useState(false);
  const [err, setErr]     = useState('');

  useEffect(() => {
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch(() => {});
    api.get('/categories/all').then(r => setCategories(r.data)).catch(() => {});
  }, []);

  const toggleCat = (id) =>
    setForm(f => ({ ...f, catIds: f.catIds.includes(id) ? f.catIds.filter(x => x !== id) : [...f.catIds, id] }));

  const submit = async () => {
    if (!form.warehouse_id) { setErr('Ombor tanlang'); return; }
    setSaving(true); setErr('');
    try {
      const { data } = await api.post('/inventory-counts', {
        warehouse_id: Number(form.warehouse_id),
        note: form.note || null,
        category_ids: form.countType === 'partial' ? form.catIds : null,
      });
      // Keep localStorage for detail view category filter display
      if (form.countType === 'partial' && form.catIds.length > 0)
        localStorage.setItem(`inv_cats_${data.id}`, JSON.stringify(form.catIds));
      onCreated(data.id);
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-800 flex items-center gap-2.5">
            <span className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </span>
            Yangi revizya yaratish
          </h2>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg text-xl leading-none">×</button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Ombor *</label>
            <select
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              value={form.warehouse_id}
              onChange={e => setForm(f => ({ ...f, warehouse_id: e.target.value }))}
            >
              <option value="">— Ombor tanlang —</option>
              {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Sanoq turi</label>
            <div className="grid grid-cols-2 gap-2">
              {[['full', "To'liq sanoq", '📦'], ['partial', "Qisman (bo'lim)", '🗂']].map(([v, l, ic]) => (
                <button
                  key={v}
                  onClick={() => setForm(f => ({ ...f, countType: v, catIds: [] }))}
                  className={`py-2.5 rounded-xl text-xs font-semibold border transition-all flex items-center justify-center gap-1.5 ${
                    form.countType === v
                      ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm'
                      : 'bg-white border-slate-200 text-slate-600 hover:border-indigo-300'
                  }`}
                >{ic} {l}</button>
              ))}
            </div>
          </div>

          {form.countType === 'partial' && categories.length > 0 && (
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Bo'limlar (kategoriyalar)</label>
              <div className="max-h-32 overflow-y-auto border border-slate-200 rounded-xl p-2 flex flex-wrap gap-1.5 bg-slate-50">
                {categories.map(cat => (
                  <button
                    key={cat.id}
                    onClick={() => toggleCat(cat.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                      form.catIds.includes(cat.id)
                        ? 'bg-indigo-600 border-indigo-600 text-white'
                        : 'bg-white border-slate-200 text-slate-600 hover:border-indigo-300'
                    }`}
                  >{cat.name}</button>
                ))}
              </div>
              {form.catIds.length > 0 && (
                <p className="text-xs text-indigo-600 mt-1.5">{form.catIds.length} ta bo'lim tanlandi</p>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('admin.dict.comment') || 'Izoh'}</label>
            <input
              type="text"
              placeholder="Ixtiyoriy..."
              className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={form.note}
              onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
            />
          </div>

          {err && <p className="text-xs text-red-600 bg-red-50 border border-red-100 px-3 py-2 rounded-lg">{err}</p>}
        </div>

        <div className="flex gap-3 px-6 pb-6">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50">{t('common.cancel')}</button>
          <button onClick={submit} disabled={saving} className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold disabled:opacity-60 shadow-sm">
            {saving ? 'Yaratilmoqda...' : '✓ Yaratish'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────── Finalize Modal ─────────── */
function FinalizeModal({ count, onConfirm, onClose, saving }) {
  const { t } = useLang();
const variances = count.items.filter(i => i.variance !== null && Number(i.variance) !== 0);
  const uncounted = count.items.filter(i => i.counted_qty === null);
  const surplus   = variances.filter(i => Number(i.variance) > 0).length;
  const shortage  = variances.filter(i => Number(i.variance) < 0).length;

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="p-6">
          <div className="w-14 h-14 bg-amber-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-base font-bold text-slate-800 text-center mb-1.5">Inventarizatsiyani yakunlash</h3>
          <p className="text-sm text-slate-500 text-center mb-5">
            Tasdiqlasangiz, stok balanslari faktik sanoq natijalariga yangilanadi.
          </p>
          <div className="space-y-2 mb-2">
            <div className="flex justify-between items-center bg-slate-50 rounded-xl px-4 py-2.5">
              <span className="text-sm text-slate-600">Jami mahsulot:</span>
              <span className="text-sm font-bold text-slate-800">{count.items.length}</span>
            </div>
            {variances.length > 0 && (
              <div className="flex justify-between items-center bg-red-50 border border-red-100 rounded-xl px-4 py-2.5">
                <span className="text-sm text-red-700">Tafovutlar (balans o'zgaradi):</span>
                <span className="text-sm font-bold text-red-700">{variances.length} ta</span>
              </div>
            )}
            {surplus > 0 && (
              <div className="flex justify-between items-center bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-2.5">
                <span className="text-sm text-emerald-700">Ortiqcha (+):</span>
                <span className="text-sm font-bold text-emerald-700">{surplus} ta</span>
              </div>
            )}
            {shortage > 0 && (
              <div className="flex justify-between items-center bg-orange-50 border border-orange-100 rounded-xl px-4 py-2.5">
                <span className="text-sm text-orange-700">Kamomad (&minus;):</span>
                <span className="text-sm font-bold text-orange-700">{shortage} ta</span>
              </div>
            )}
            {uncounted.length > 0 && (
              <div className="flex justify-between items-center bg-amber-50 border border-amber-100 rounded-xl px-4 py-2.5">
                <span className="text-sm text-amber-700">Sanalмagan (o'zgarmaydi):</span>
                <span className="text-sm font-bold text-amber-700">{uncounted.length} ta</span>
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-3 px-6 pb-6">
          <button onClick={onClose} className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50">{t('common.back')}</button>
          <button onClick={onConfirm} disabled={saving} className="flex-1 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-60 shadow-sm">
            {saving ? 'Yakunlanmoqda...' : '✓ Ha, tasdiqlash'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────── Detail View ─────────── */
function DetailView({ countId, onBack }) {
  const { t } = useLang();
const [count,        setCount]        = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [localQtys,    setLocalQtys]    = useState({});
  const [localReasons, setLocalReasons] = useState({});
  const [saving,       setSaving]       = useState(false);
  const [finalizing,   setFinalizing]   = useState(false);
  const [starting,     setStarting]     = useState(false);
  const [showFinalize, setShowFinalize] = useState(false);
  const [filter,       setFilter]       = useState('all');
  const [search,       setSearch]       = useState('');
  const [catFilter,    setCatFilter]    = useState(null);
  const [err,          setErr]          = useState('');
  const [savedMsg,     setSavedMsg]     = useState('');
  const [page,         setPage]         = useState(1);
  const rowsPerPage = 100;

  const loadCount = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/inventory-counts/${countId}`);
      setCount(data);
      const qtys = {}, reasons = {};
      data.items.forEach(item => {
        if (item.counted_qty !== null && item.counted_qty !== undefined)
          qtys[item.product_id] = String(item.counted_qty);
        if (item.variance_reason) reasons[item.product_id] = item.variance_reason;
      });
      setLocalQtys(qtys);
      setLocalReasons(reasons);
      const stored = localStorage.getItem(`inv_cats_${countId}`);
      if (stored) setCatFilter(JSON.parse(stored));
    } catch { setErr("Ma'lumotlar yuklanmadi"); }
    finally { setLoading(false); }
  }, [countId]);

  useEffect(() => { loadCount(); }, [loadCount]);

  const handleStart = async () => {
    setStarting(true); setErr('');
    try { await api.post(`/inventory-counts/${countId}/start`); await loadCount(); }
    catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); }
    finally { setStarting(false); }
  };

  const handleSave = async (silent = false) => {
    setSaving(true); setErr(''); setSavedMsg('');
    try {
      const items = Object.entries(localQtys)
        .filter(([, v]) => v !== '')
        .map(([pid, qty]) => ({
          product_id: Number(pid),
          counted_qty: Number(qty),
          variance_reason: localReasons[pid] || null,
        }));
      if (items.length === 0) { setSaving(false); return; }
      await api.post(`/inventory-counts/${countId}/items`, items);
      await loadCount();
      if (!silent) { setSavedMsg('Saqlandi'); setTimeout(() => setSavedMsg(''), 2500); }
    } catch (e) { setErr(e.response?.data?.detail || 'Saqlashda xatolik'); }
    finally { setSaving(false); }
  };

  const handleFinalize = async () => {
    setFinalizing(true);
    try {
      await handleSave(true);
      await api.post(`/inventory-counts/${countId}/finalize`);
      await loadCount();
      setShowFinalize(false);
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); }
    finally { setFinalizing(false); }
  };

  const canEdit = count && (count.status === 'draft' || count.status === 'in_progress');

  const filteredItems = useMemo(() => {
    if (!count) return [];
    let items = count.items;
    if (catFilter?.length > 0)
      items = items.filter(i => catFilter.includes(i.product_category_id));
    if (filter === 'variance') {
      items = items.filter(i => {
        const lq = localQtys[i.product_id];
        if (lq !== undefined && lq !== '') return Number(lq) !== Number(i.system_qty);
        return i.variance !== null && Number(i.variance) !== 0;
      });
    } else if (filter === 'uncounted') {
      items = items.filter(i => (localQtys[i.product_id] === undefined || localQtys[i.product_id] === '') && i.counted_qty === null);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(i => i.product_name.toLowerCase().includes(q) || (i.product_sku && i.product_sku.toLowerCase().includes(q)));
    }
    setPage(1);
    return items;
  }, [count, filter, search, localQtys, catFilter]);

  const totalPages = Math.ceil(filteredItems.length / rowsPerPage);
  const visibleItems = filteredItems.slice((page - 1) * rowsPerPage, page * rowsPerPage);

  const stats = useMemo(() => {
    if (!count) return { total: 0, counted: 0, uncounted: 0, variances: 0, surplus: 0, shortage: 0 };
    const total = count.items.length;
    const counted = count.items.filter(i => localQtys[i.product_id] !== undefined && localQtys[i.product_id] !== '' || i.counted_qty !== null).length;
    const getVar = (i) => { const lq = localQtys[i.product_id]; if (lq !== undefined && lq !== '') return Number(lq) - Number(i.system_qty); return i.variance !== null ? Number(i.variance) : null; };
    const varItems = count.items.map(i => getVar(i)).filter(v => v !== null && v !== 0);
    return { total, counted, uncounted: total - counted, variances: varItems.length, surplus: varItems.filter(v => v > 0).length, shortage: varItems.filter(v => v < 0).length };
  }, [count, localQtys]);

  if (loading) return <Loader />;
  if (!count)  return <div className="text-center py-20 text-slate-400">{t('common.noData')}</div>;

  return (
    <div className="space-y-5">
      {/* Top bar */}
      <div className="flex items-start gap-4 flex-wrap">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600 font-medium mt-1 transition-colors shrink-0">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/>
          </svg>
          Orqaga
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-bold text-slate-800 font-mono">{count.number}</h1>
            <StatusBadge status={count.status} />
            {catFilter?.length > 0 && (
              <span className="text-xs text-violet-700 bg-violet-50 border border-violet-200 px-2.5 py-1 rounded-full font-medium">🗂 Qisman sanoq</span>
            )}
          </div>
          <p className="text-sm text-slate-500 mt-0.5">
            <span className="font-medium text-slate-700">{count.warehouse_name}</span>
            &nbsp;·&nbsp;{fmtDt(count.created_at)}&nbsp;·&nbsp;{count.creator_name}
            {count.note && <span className="italic text-slate-400"> — {count.note}</span>}
          </p>
        </div>
        {/* Actions */}
        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <button onClick={() => printCountSheet(count, t)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-semibold bg-white border border-slate-200 rounded-xl hover:bg-slate-50 text-slate-700 transition-colors">
            🖨 Sanash varaqasi
          </button>
          {count.status !== 'draft' && (
            <button onClick={() => printVarianceReport(count, t)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-semibold bg-white border border-slate-200 rounded-xl hover:bg-slate-50 text-slate-700 transition-colors">
              📋 Tafovutlar
            </button>
          )}
          {count.status === 'draft' && (
            <button onClick={handleStart} disabled={starting}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors">
              {starting ? '...' : '▶ Boshlash'}
            </button>
          )}
          {canEdit && (
            <button onClick={() => handleSave(false)} disabled={saving}
              className={`px-4 py-2 text-sm font-semibold rounded-xl shadow-sm transition-all disabled:opacity-60 ${savedMsg ? 'bg-emerald-600 text-white' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`}>
              {saving ? 'Saqlanmoqda...' : savedMsg ? '✓ Saqlandi' : 'Saqlash'}
            </button>
          )}
          {count.status === 'in_progress' && (
            <button onClick={() => setShowFinalize(true)}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors">
              ✓ Yakunlash
            </button>
          )}
        </div>
      </div>

      {err && (
        <div className="bg-red-50 border border-red-100 text-red-600 text-sm px-4 py-2.5 rounded-xl flex items-center gap-2">
          <span>⚠</span>{err}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { l: 'Jami',         v: stats.total,     c: 'text-slate-800' },
          { l: 'Sanalgan',     v: stats.counted,   c: 'text-indigo-600' },
          { l: 'Sanalмagan',   v: stats.uncounted, c: 'text-amber-600' },
          { l: 'Tafovutlar',   v: stats.variances, c: 'text-red-600' },
          { l: 'Ortiqcha (+)', v: stats.surplus,   c: 'text-emerald-600' },
          { l: 'Kamomad (−)',  v: stats.shortage,  c: 'text-orange-600' },
        ].map(s => (
          <div key={s.l} className="bg-white rounded-2xl border border-slate-100 px-4 py-3.5 shadow-sm">
            <div className={`text-2xl font-bold ${s.c}`}>{s.v}</div>
            <div className="text-xs text-slate-500 mt-0.5">{s.l}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          {[['all','Hammasi'],['variance','Tafovutlar'],['uncounted','Sanalmaganlar']].map(([v, l]) => (
            <button key={v} onClick={() => setFilter(v)}
              className={`px-4 py-2 text-sm font-semibold transition-all ${filter === v ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
              {l}
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="Qidirish: nom yoki SKU..."
            className="w-full px-3.5 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <span className="text-sm text-slate-400 ml-auto">{filteredItems.length} ta</span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider w-10">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SKU</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Mahsulot nomi</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500 uppercase tracking-wider w-20">O'lchov</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider w-28">Tizim qoldig'i</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500 uppercase tracking-wider w-32">Faktik soni</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider w-24">Tafovut</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Sababi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {visibleItems.map((item, idx) => {
                const absoluteIdx = (page - 1) * rowsPerPage + idx;
                const lqRaw   = localQtys[item.product_id];
                const dispQty = lqRaw !== undefined ? lqRaw : (item.counted_qty !== null ? String(item.counted_qty) : '');
                const sysQty  = Number(item.system_qty);
                const factQty = dispQty !== '' ? Number(dispQty) : null;
                const variance = factQty !== null
                  ? factQty - sysQty
                  : (item.variance !== null ? Number(item.variance) : null);
                const vColor = variance === null   ? 'text-slate-300'
                             : variance > 0        ? 'text-emerald-600 font-bold'
                             : variance < 0        ? 'text-red-600 font-bold'
                             : 'text-slate-400';
                const rowBg = variance !== null && variance !== 0 ? 'bg-red-50/40' : '';
                const reason = localReasons[item.product_id] || '';

                return (
                  <tr key={item.id} className={`hover:bg-slate-50/80 transition-colors ${rowBg}`}>
                    <td className="px-4 py-3 text-xs text-slate-400">{absoluteIdx + 1}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-500">{item.product_sku || '—'}</td>
                    <td className="px-4 py-3 text-sm font-medium text-slate-800">{item.product_name}</td>
                    <td className="px-4 py-3 text-xs text-slate-500 text-center">{item.product_unit}</td>
                    <td className="px-4 py-3 text-sm text-slate-700 text-right font-mono">{fmtQ(item.system_qty)}</td>
                    <td className="px-3 py-2">
                      {canEdit ? (
                        <input
                          type="number" step="0.001" min="0" placeholder="0"
                          value={dispQty}
                          onChange={e => setLocalQtys(p => ({ ...p, [item.product_id]: e.target.value }))}
                          className={`w-full px-2.5 py-1.5 border rounded-lg text-sm text-center font-mono focus:outline-none focus:ring-2 transition-colors ${
                            dispQty !== '' && Number(dispQty) !== sysQty
                              ? 'border-red-300 bg-red-50 focus:ring-red-300'
                              : dispQty !== ''
                                ? 'border-emerald-300 bg-emerald-50 focus:ring-emerald-300'
                                : 'border-slate-200 bg-white focus:ring-indigo-400'
                          }`}
                        />
                      ) : (
                        <span className="block text-center text-sm font-mono text-slate-700">{fmtQ(item.counted_qty)}</span>
                      )}
                    </td>
                    <td className={`px-4 py-3 text-sm text-right font-mono ${vColor}`}>
                      {variance !== null ? (variance > 0 ? '+' : '') + fmtQ(variance) : '—'}
                    </td>
                    <td className="px-3 py-2">
                      {canEdit && variance !== null && variance !== 0 ? (
                        <input
                          type="text" placeholder="Sababi..."
                          value={reason}
                          onChange={e => setLocalReasons(p => ({ ...p, [item.product_id]: e.target.value }))}
                          className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-white min-w-[100px]"
                        />
                      ) : (
                        <span className="text-xs text-slate-400 italic">{item.variance_reason || ''}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filteredItems.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center gap-2 text-slate-300">
                      <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                      </svg>
                      <span className="text-sm text-slate-400">Mahsulotlar topilmadi</span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50">
            <span className="text-xs text-slate-500 font-medium">Barchasi: {filteredItems.length} ta (Hozirgi sahifa: {page} / {totalPages})</span>
            <div className="flex gap-2">
              <button 
                disabled={page === 1} 
                onClick={() => setPage(page - 1)}
                className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold bg-white text-slate-600 disabled:opacity-40 hover:border-indigo-300 transition-all"
              >
                Oldingi
              </button>
              <button 
                disabled={page === totalPages} 
                onClick={() => setPage(page + 1)}
                className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold bg-white text-slate-600 disabled:opacity-40 hover:border-indigo-300 transition-all"
              >
                Keyingi
              </button>
            </div>
          </div>
        )}

        {canEdit && filteredItems.length > 0 && (
          <div className="flex items-center justify-between px-6 py-3 bg-slate-50 border-t border-slate-100">
            <span className="text-xs text-slate-500">
              {Object.values(localQtys).filter(v => v !== '').length} ta to'ldirilgan
            </span>
            <button
              onClick={() => handleSave(false)} disabled={saving}
              className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
            >
              {saving ? 'Saqlanmoqda...' : savedMsg ? '✓ Saqlandi' : '💾 Saqlash'}
            </button>
          </div>
        )}
      </div>

      {showFinalize && (
        <FinalizeModal
          count={count}
          onConfirm={handleFinalize}
          onClose={() => setShowFinalize(false)}
          saving={finalizing}
        />
      )}
    </div>
  );
}

/* ─────────── List View ─────────── */
function ListView({ onView }) {
  const { t } = useLang();
const [counts,       setCounts]       = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate,   setShowCreate]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? { status: statusFilter } : {};
      const { data } = await api.get('/inventory-counts', { params });
      setCounts(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Inventarizatsiya</h1>
          <p className="text-sm text-slate-500 mt-0.5">Faktik va tizim qoldiqlarini solishtirish va tuzatish</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/>
          </svg>
          Yangi revizya yaratish
        </button>
      </div>

      {/* Status filter pills */}
      <div className="flex gap-2 flex-wrap">
        {[['','Hammasi'],['draft','Qoralama'],['in_progress','Jarayonda'],['completed','Yakunlangan']].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setStatusFilter(v)}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold border transition-all ${
              statusFilter === v
                ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm'
                : 'bg-white border-slate-200 text-slate-600 hover:border-indigo-300'
            }`}
          >{l}</button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        {loading ? <Loader /> : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['Raqam','Ombor','Yaratilgan sana','Mahsulotlar','Holat',''].map((h, i) => (
                  <th key={i} className="px-6 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {counts.map(c => (
                <tr key={c.id} className="hover:bg-slate-50 transition-colors cursor-pointer" onClick={() => onView(c.id)}>
                  <td className="px-6 py-4 text-sm font-mono font-bold text-indigo-600">{c.number}</td>
                  <td className="px-6 py-4 text-sm font-medium text-slate-700">{c.warehouse_name}</td>
                  <td className="px-6 py-4 text-sm text-slate-500">{fmtDate(c.created_at)}</td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16"/>
                      </svg>
                      {c.item_count} ta
                    </span>
                  </td>
                  <td className="px-6 py-4"><StatusBadge status={c.status} /></td>
                  <td className="px-6 py-4">
                    <button
                      onClick={e => { e.stopPropagation(); onView(c.id); }}
                      className="px-3 py-1.5 text-xs font-semibold bg-indigo-50 text-indigo-600 hover:bg-indigo-100 rounded-lg transition-colors"
                    >Ko'rish →</button>
                  </td>
                </tr>
              ))}
              {counts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-20 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-16 h-16 bg-slate-100 rounded-2xl flex items-center justify-center">
                        <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/>
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-500">Inventarizatsiya topilmadi</p>
                        <p className="text-xs text-slate-400 mt-0.5">Birinchi revizya yaratingiz</p>
                      </div>
                      <button
                        onClick={() => setShowCreate(true)}
                        className="mt-1 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm"
                      >+ Yangi revizya</button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={(id) => { setShowCreate(false); onView(id); }}
        />
      )}
    </div>
  );
}

/* ─────────── Main export ─────────── */
export default function InventoryCounts() {
  const { t } = useLang();
const [view,       setView]       = useState('list');
  const [selectedId, setSelectedId] = useState(null);

  if (view === 'detail' && selectedId) {
    return (
      <DetailView
        countId={selectedId}
        onBack={() => { setSelectedId(null); setView('list'); }}
      />
    );
  }
  return <ListView onView={(id) => { setSelectedId(id); setView('detail'); }} />;
}



