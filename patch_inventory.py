import re

with open(r"d:\ERP-PosNAW\frontend\src\pages\admin\InventoryCounts.jsx", "r", encoding="utf-8") as f:
    content = f.read()

# Add ProdSearch
prod_search_code = """
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
"""

if "import { useRef" not in content:
    content = content.replace("import { useState, useEffect, useCallback, useMemo } from 'react';", "import { useState, useEffect, useCallback, useMemo, useRef } from 'react';")

content = content.replace("/* ─────────── Finalize Modal ─────────── */", prod_search_code + "\n/* ─────────── Finalize Modal ─────────── */")

# Add searchVariants import if missing
if "searchVariants" not in content:
    content = content.replace("import api from '../../api/axios';", "import api from '../../api/axios';\nimport { searchVariants } from '../../utils/translit';")

# Add view === 'create' to main render
main_export_orig = """/* ─────────── Main export ─────────── */
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
}"""

main_export_new = """/* ─────────── Main export ─────────── */
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
}"""

content = content.replace(main_export_orig, main_export_new)

# Update ListView to take onCreate and use it
list_view_orig = "function ListView({ onView }) {"
list_view_new = "function ListView({ onView, onCreate }) {"
content = content.replace(list_view_orig, list_view_new)

# Update ListView's "+ Yangi revizya yaratish" button
content = content.replace("onClick={() => setShowCreate(true)}", "onClick={onCreate}")

with open(r"d:\ERP-PosNAW\frontend\src\pages\admin\InventoryCounts.jsx", "w", encoding="utf-8") as f:
    f.write(content)

