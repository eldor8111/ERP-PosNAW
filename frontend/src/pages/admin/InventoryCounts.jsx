import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useLang } from '../../context/LangContext';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { matchesSearch } from '../../utils/translit';

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
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/categories/all').then(r => setCategories(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
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


/* ─── Product search dropdown (copied from Purchases) ─── */
import { searchVariants } from '../../utils/translit';

function ProdSearch({ products, onSelect, inputRef, placeholder = 'Mahsulot qidiring...' }) {
  const { t } = useLang();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [navIdx, setNavIdx] = useState(-1);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    const localMatches = products.filter(p =>
        matchesSearch(p.name, q) || matchesSearch(p.sku, q) || (p.barcode && p.barcode.includes(q))
    ).slice(0, 15);
    setResults(localMatches);

    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const variants = searchVariants(q);
        const reqs = variants.map(v => api.get('/products/', { params: { search: v, limit: 15, status: 'active' } }).catch(() => ({ data: [] })));
        const resps = await Promise.all(reqs);
        const seen = new Set(localMatches.map(p => p.id));
        const merged = [...localMatches];
        for (const r of resps) {
          const items = Array.isArray(r.data) ? r.data : (r.data?.items || []);
          for (const item of items) {
             if (!seen.has(item.id)) { seen.add(item.id); merged.push(item); }
          }
        }
        setResults(merged.slice(0, 15));
      } catch (err) {} finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(timerRef.current);
  }, [q, products]);

  const displayList = q.trim() ? results : products.slice(0, 15);

  const handleKeyDown = (e) => {
    if (!open) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setNavIdx(prev => (prev < displayList.length - 1 ? prev + 1 : prev)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setNavIdx(prev => (prev > 0 ? prev - 1 : -1)); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (navIdx >= 0 && navIdx < displayList.length) { onSelect(displayList[navIdx]); setQ(''); setOpen(false); setNavIdx(-1); }
      else if (displayList.length > 0) { onSelect(displayList[0]); setQ(''); setOpen(false); setNavIdx(-1); }
    }
  };
  useEffect(() => setNavIdx(-1), [q, open]);
  useEffect(() => {
    const h = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className={`flex items-center gap-2 border border-slate-200 rounded-xl px-3.5 py-2 bg-white transition-all ${open ? 'border-indigo-400 ring-2 ring-indigo-50' : 'hover:border-slate-300'}`}>
        <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)} onKeyDown={handleKeyDown} ref={inputRef} placeholder={placeholder}
          className="w-full text-sm outline-none bg-transparent" />
        {loading && <div className="w-3.5 h-3.5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin shrink-0" />}
      </div>
      {open && displayList.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-2xl z-60 overflow-hidden max-h-72 overflow-y-auto">
          {displayList.map((p, i) => (
            <button key={p.id} onMouseDown={() => { onSelect(p); setQ(''); setOpen(false); }}
              className={`w-full text-left px-4 py-2.5 hover:bg-indigo-50 border-b border-slate-100 last:border-0 flex justify-between items-center gap-3 ${navIdx === i ? 'bg-indigo-50' : ''}`}>
              <div className="min-w-0">
                <div className="font-medium text-slate-800 text-sm truncate">{p.name}</div>
                <div className="text-xs text-slate-400">{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</div>
              </div>
              <div className="text-right shrink-0 text-xs text-slate-400">Qoldiq: {p.stock_quantity}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── ReviziyaCreateView (like KirimCreateView) ─── */
function ReviziyaCreateView({ onBack, onSaved }) {
  const { t } = useLang();
  const [warehouses, setWarehouses] = useState([]);
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState({ warehouse_id: '', note: '' });
  const [cart, setCart] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const searchRef = useRef(null);
  const qtyRef = useRef(null);
  const [sel, setSel] = useState(null);
  const [countedQty, setCountedQty] = useState('');
  const [reason, setReason] = useState('');

  useEffect(() => {
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch(console.error);
    api.get('/products/', { params: { limit: 1000, status: 'active' } }).then(r => setProducts(Array.isArray(r.data) ? r.data : (r.data.items||[]))).catch(console.error);
  }, []);

  const selectProduct = (p) => {
    setSel(p);
    setCountedQty('');
    setReason('');
    setTimeout(() => { if (qtyRef.current) qtyRef.current.focus(); }, 10);
  };

  const addItem = () => {
    if (!sel || countedQty === '') return;
    setCart(prev => {
      const ex = prev.find(x => x.product.id === sel.id);
      if (ex) return prev.map(x => x.product.id === sel.id ? { ...x, counted_qty: Number(countedQty), variance_reason: reason } : x);
      return [...prev, { product: sel, counted_qty: Number(countedQty), variance_reason: reason }];
    });
    setSel(null); setCountedQty(''); setReason('');
    setTimeout(() => { if (searchRef.current) searchRef.current.focus(); }, 10);
  };

  const doSave = async () => {
    if (!form.warehouse_id) { setErr("Omborni tanlang!"); return; }
    if (!cart.length) { setErr("Kamida bitta mahsulot qo'shing!"); return; }
    setSaving(true); setErr('');
    try {
      // 1. Create count
      const { data: count } = await api.post('/inventory-counts', {
        warehouse_id: Number(form.warehouse_id),
        note: form.note || null,
        category_ids: null // Full count style prepopulation
      });
      // 2. Start count
      await api.post(`/inventory-counts/${count.id}/start`);
      // 3. Update items
      const itemsPayload = cart.map(c => ({
        product_id: c.product.id,
        counted_qty: c.counted_qty,
        variance_reason: c.variance_reason || null
      }));
      await api.post(`/inventory-counts/${count.id}/items`, itemsPayload);
      // 4. Finalize
      await api.post(`/inventory-counts/${count.id}/finalize`);
      toast.success("Inventarizatsiya yakunlandi");
      onSaved();
    } catch (e) {
      setErr(e.response?.data?.detail || "Saqlashda xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3.5 border-b border-slate-100 bg-white shrink-0 shadow-sm">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 transition-all text-sm font-semibold">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>
          Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200 shrink-0" />
        <h2 className="text-base font-bold text-slate-800 flex-1">Yangi revizya</h2>
        <div className="flex items-center gap-3">
          <select value={form.warehouse_id} onChange={e => setForm(f=>({...f, warehouse_id: e.target.value}))}
            className="border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white min-w-[200px]">
            <option value="">— Ombor tanlang —</option>
            {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <input placeholder="Izoh (ixtiyoriy)..." value={form.note} onChange={e => setForm(f=>({...f, note: e.target.value}))}
            className="border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white min-w-[200px]" />
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left */}
        <div className="w-[450px] border-r border-slate-100 p-6 flex flex-col gap-6 overflow-y-auto shrink-0 bg-white shadow-sm">
          <div>
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Mahsulot qidirish</label>
            <ProdSearch products={products} onSelect={selectProduct} inputRef={searchRef} />
          </div>

          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5 space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shrink-0 shadow-sm">{sel.name.slice(0,2).toUpperCase()}</div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-slate-800 text-base truncate">{sel.name}</div>
                  <div className="text-sm text-slate-600 mt-1">Tizim qoldig'i: <strong>{sel.stock_quantity}</strong> {sel.unit||'dona'}</div>
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Faktik qoldiq *</label>
                <div className="flex items-center gap-2">
                  <input type="number" min="0" step="any" value={countedQty} onChange={e => setCountedQty(e.target.value)}
                    ref={qtyRef} onKeyDown={e => e.key === 'Enter' && addItem()}
                    className="flex-1 border border-slate-200 rounded-xl px-3.5 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-bold" />
                  <span className="text-sm font-medium text-slate-500">{sel.unit||'dona'}</span>
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Tafovut sababi (ixtiyoriy)</label>
                <input type="text" value={reason} onChange={e => setReason(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addItem()}
                  className="w-full border border-slate-200 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <button onClick={addItem} disabled={countedQty===''} className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white rounded-xl font-bold text-sm shadow-sm transition-all active:scale-95">
                Sanoqqa qo'shish
              </button>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-300 flex-col gap-2">
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" /></svg>
              <p className="text-sm">Mahsulot tanlang</p>
            </div>
          )}
        </div>

        {/* Right */}
        <div className="flex-1 bg-white rounded-2xl border border-slate-100 flex flex-col overflow-hidden shadow-sm m-3">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-slate-50/50 shrink-0">
            <span className="text-sm font-bold text-slate-700">Sanalgan mahsulotlar ({cart.length} ta)</span>
            {cart.length > 0 && <button onClick={()=>setCart([])} className="text-xs text-red-500 font-semibold hover:bg-red-50 px-2 py-1 rounded">Tozalash</button>}
          </div>
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 w-8">№</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Mahsulot</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500">Tizim</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500">Faktik</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500">Tafovut</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Sababi</th>
                  <th></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {cart.map((c, i) => {
                  const sys = Number(c.product.stock_quantity || 0);
                  const fact = Number(c.counted_qty);
                  const variance = fact - sys;
                  const vColor = variance > 0 ? 'text-emerald-600' : variance < 0 ? 'text-red-600' : 'text-slate-400';
                  return (
                    <tr key={c.product.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-400">{i+1}</td>
                      <td className="px-4 py-3 font-medium text-slate-800">{c.product.name}</td>
                      <td className="px-4 py-3 text-right text-slate-500">{sys}</td>
                      <td className="px-4 py-3 text-right font-bold text-indigo-600">{fact}</td>
                      <td className={`px-4 py-3 text-right font-bold ${vColor}`}>{variance>0?'+':''}{variance}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{c.variance_reason}</td>
                      <td className="pr-3 text-right"><button onClick={()=>setCart(p=>p.filter((_,idx)=>idx!==i))} className="text-slate-300 hover:text-red-500 font-bold p-1">✕</button></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-t border-slate-100 shrink-0">
        <div className="flex gap-3 items-center">
          <button onClick={onBack} className="px-5 py-2.5 text-sm font-semibold border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50">Bekor</button>
          {err && <span className="text-red-500 text-sm font-medium">{err}</span>}
        </div>
        <button onClick={doSave} disabled={saving || !cart.length} className="px-8 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-sm">
          {saving ? 'Saqlanmoqda...' : 'Saqlash va Yakunlash ✓'}
        </button>
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

    // Yakunlangan reviziyada faqat sanab o'tilgan mahsulotlarni ko'rsat
    if (count.status === 'completed') {
      items = items.filter(i => i.counted_qty !== null && i.counted_qty !== undefined);
    }

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
      items = items.filter(i => matchesSearch(i.product_name, search) || (i.product_sku && matchesSearch(i.product_sku, search)));
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
function ListView({ onView, onCreate }) {
  const { t } = useLang();
const [counts,       setCounts]       = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate,   setShowCreate]   = useState(false);
  const [deleting,     setDeleting]     = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? { status: statusFilter } : {};
      const { data } = await api.get('/inventory-counts', { params });
      setCounts(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [statusFilter]);

  const handleDelete = async (e, c) => {
    e.stopPropagation();
    if (!window.confirm(`"${c.number}" revizyasini o'chirishni tasdiqlaysizmi?\nBu amalni qaytarib bo'lmaydi!`)) return;
    setDeleting(c.id);
    try {
      await api.delete(`/inventory-counts/${c.id}`);
      toast.success("Revizya o'chirildi");
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "O'chirishda xatolik");
    } finally { setDeleting(null); }
  };

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
          onClick={onCreate}
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
                    <div className="flex items-center gap-2">
                      <button
                        onClick={e => { e.stopPropagation(); onView(c.id); }}
                        className="px-3 py-1.5 text-xs font-semibold bg-indigo-50 text-indigo-600 hover:bg-indigo-100 rounded-lg transition-colors"
                      >Ko'rish →</button>
                      <button
                        onClick={e => handleDelete(e, c)}
                        disabled={deleting === c.id}
                        className="px-3 py-1.5 text-xs font-semibold bg-red-50 text-red-500 hover:bg-red-100 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {deleting === c.id ? '...' : "O'chirish"}
                      </button>
                    </div>
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
                        onClick={onCreate}
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
  const [view, setView] = useState('list');
  const [selectedId, setSelectedId] = useState(null);

  if (view === 'create') {
    return <ReviziyaCreateView onBack={() => setView('list')} onSaved={() => setView('list')} />;
  }
  if (view === 'detail' && selectedId) {
    return (
      <DetailView
        countId={selectedId}
        onBack={() => { setSelectedId(null); setView('list'); }}
      />
    );
  }
  return <ListView onView={(id) => { setSelectedId(id); setView('detail'); }} onCreate={() => setView('create')} />;
}



