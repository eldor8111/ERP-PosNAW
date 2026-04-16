import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ');
const fmtDate = (s) =>
  s
    ? new Date(s).toLocaleString('ru-RU', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      }).replace(',', '')
    : '—';

// ─── STATUS BADGE ──────────────────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const map = {
    pending:   { label: "Kutilmoqda", cls: "bg-amber-100 text-amber-700"  },
    completed: { label: "Bajarildi",  cls: "bg-emerald-100 text-emerald-700" },
    cancelled: { label: "Bekor",      cls: "bg-red-100 text-red-600"       },
    in:        { label: "Kirim",      cls: "bg-emerald-100 text-emerald-700" },
    out:       { label: "Chiqim",     cls: "bg-rose-100 text-rose-700"     },
    adjust:    { label: "Tuzatish",   cls: "bg-blue-100 text-blue-700"     },
  };
  const m = map[status] || { label: status, cls: "bg-slate-100 text-slate-600" };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${m.cls}`}>
      {m.label}
    </span>
  );
};

// ─── TABS (will be rendered inside component with t()) ────────────────────────────
const TABS = [
  { id: 'qoldiq',    label: 'Qoldiqlar',   icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
  { id: 'kirim',     label: 'Kirim',        icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12' },
  { id: 'chiqim',    label: "Chiqim",       icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4' },
  { id: 'kochirish', label: "Ko'chirish",   icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
  { id: 'omborlar',  label: 'Omborlar',     icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' },
];

// ─── QOLDIQLAR TAB ─────────────────────────────────────────────────────────
function QoldiqlarTab() {
  const { t } = useLang();
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState('');
  const [lowOnly, setLowOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/inventory/stock', {
        params: { search: search || undefined, low_stock_only: lowOnly, limit: 200 },
      });
      setItems(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [search, lowOnly]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      {/* filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Mahsulot nomi, SKU yoki shtrix-kod..."
            className="w-full pl-9 pr-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" checked={lowOnly} onChange={e => setLowOnly(e.target.checked)} className="w-4 h-4 rounded text-indigo-600" />
          <span className="text-sm text-slate-600 font-medium">{t('product.lowStock')}</span>
        </label>
        <button onClick={load} className="px-4 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-colors">
          {t('common.refresh')}
        </button>
      </div>

      {/* summary cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: t('dashboard.totalProducts'), value: items.length, color: "indigo" },
          { label: t('product.lowStock'),         value: items.filter(i => i.is_low_stock).length, color: "amber" },
          { label: t('product.active'),            value: items.filter(i => !i.is_low_stock).length, color: "emerald" },
        ].map(c => (
          <div key={c.label} className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
            <p className="text-xs text-slate-500 font-medium">{c.label}</p>
            <p className={`text-2xl font-bold mt-1 text-${c.color}-600`}>{c.value}</p>
          </div>
        ))}
      </div>

      {/* table */}
      <div className="bg-white rounded-xl border border-slate-100 overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.product') || 'Mahsulot'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SKU</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.balance') || 'Qoldiq'}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Min</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.status') || 'Holat'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Yangilangan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map((it, i) => (
                <tr key={it.product_id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-400">{i + 1}</td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{it.product_name}</td>
                  <td className="px-4 py-3 text-sm text-slate-500 font-mono">{it.product_sku || '—'}</td>
                  <td className="px-4 py-3 text-sm text-right font-bold text-slate-800">{fmt(it.quantity)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{fmt(it.min_stock)}</td>
                  <td className="px-4 py-3">
                    {it.is_low_stock
                      ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-100 text-red-600">⚠ {t('product.lowStock')}</span>
                      : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">✓ {t('common.active')}</span>
                    }
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(it.updated_at)}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── HARAKATLAR (Kirim / Chiqim) TAB ──────────────────────────────────────
function MovementsTab({ type }) {
  const { t } = useLang();
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/inventory/movements', { params: { type, limit: 100 } });
      setItems(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [type]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {type === 'in' ? t('ops.incoming') : t('ops.outgoing')}
        </p>
        <button onClick={load} className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-colors">
          {t('common.refresh')}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.product') || 'Mahsulot'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Tur</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.qty') || 'Miqdor'}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Oldin</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Keyin</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Sabab</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.date') || 'Sana'}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map((it, i) => (
                <tr key={it.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-400">{i + 1}</td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{it.product_name}</td>
                  <td className="px-4 py-3"><StatusBadge status={it.type} /></td>
                  <td className="px-4 py-3 text-sm text-right font-bold text-slate-800">{fmt(it.quantity)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{fmt(it.qty_before)}</td>
                  <td className="px-4 py-3 text-sm text-right text-slate-500">{fmt(it.qty_after)}</td>
                  <td className="px-4 py-3 text-sm text-slate-500 max-w-[160px] truncate">{it.reason || '—'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(it.created_at)}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── KO'CHIRISH TAB ────────────────────────────────────────────────────────
function KochirTab() {
  const { t } = useLang();
  const [transfers, setTransfers]       = useState([]);
  const [warehouses, setWarehouses]     = useState([]);
  const [products, setProducts]         = useState([]);
  const [loading, setLoading]           = useState(true);
  const [showModal, setShowModal]       = useState(false);
  const [form, setForm]                 = useState({ from_warehouse_id: '', to_warehouse_id: '', note: '', items: [{ product_id: '', quantity: '' }] });
  const [saving, setSaving]             = useState(false);
  const [err, setErr]                   = useState('');
  /* detail state reserved for future transfer detail view */

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tr, wh, pr] = await Promise.all([
        api.get('/transfers', { params: { limit: 50 } }),
        api.get('/inventory/warehouses'),
        api.get('/products/', { params: { limit: 300 } }),
      ]);
      setTransfers(tr.data);
      setWarehouses(wh.data);
      setProducts(pr.data?.items || pr.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addItem = () => setForm(f => ({ ...f, items: [...f.items, { product_id: '', quantity: '' }] }));
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const setItem = (idx, key, val) => setForm(f => {
    const items = [...f.items];
    items[idx] = { ...items[idx], [key]: val };
    return { ...f, items };
  });

  const submit = async () => {
    if (!form.from_warehouse_id || !form.to_warehouse_id) { setErr("Omborlarni tanlang"); return; }
    if (form.from_warehouse_id === form.to_warehouse_id) { setErr("Bir xil ombor tanlanmasin"); return; }
    const validItems = form.items.filter(i => i.product_id && Number(i.quantity) > 0);
    if (!validItems.length) { setErr("Kamida 1 ta mahsulot kiriting"); return; }
    setSaving(true); setErr('');
    try {
      await api.post('/transfers', {
        from_warehouse_id: Number(form.from_warehouse_id),
        to_warehouse_id: Number(form.to_warehouse_id),
        note: form.note,
        items: validItems.map(i => ({ product_id: Number(i.product_id), quantity: Number(i.quantity) })),
      });
      setShowModal(false);
      setForm({ from_warehouse_id: '', to_warehouse_id: '', note: '', items: [{ product_id: '', quantity: '' }] });
      load();
    } catch (e) { setErr(e.response?.data?.detail || "Xatolik yuz berdi"); }
    finally { setSaving(false); }
  };

  const confirm = async (id) => {
    try { await api.post(`/transfers/${id}/confirm`); load(); }
    catch (e) { alert(e.response?.data?.detail || "Xatolik"); }
  };
  const cancel = async (id) => {
    if (!window.confirm("Transferni bekor qilasizmi?")) return;
    try { await api.post(`/transfers/${id}/cancel`); load(); }
    catch (e) { alert(e.response?.data?.detail || "Xatolik"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">Omborlar o'rtasida tovar ko'chirish</p>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('warehouse.newTransfer')}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">№</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Kimdan</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Kimga</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.status') || 'Holat'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.date') || 'Sana'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {transfers.map((tr) => (
                <tr key={tr.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm font-mono text-slate-700 font-semibold">{tr.number}</td>
                  <td className="px-4 py-3 text-sm text-slate-700">{tr.from_warehouse_name}</td>
                  <td className="px-4 py-3 text-sm text-slate-700">{tr.to_warehouse_name}</td>
                  <td className="px-4 py-3"><StatusBadge status={tr.status} /></td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(tr.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      {tr.status === 'pending' && (
                        <>
                          <button onClick={() => confirm(tr.id)}
                            className="px-2.5 py-1 text-xs font-semibold bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors">
                            {t('common.confirm')}
                          </button>
                          <button onClick={() => cancel(tr.id)}
                            className="px-2.5 py-1 text-xs font-semibold bg-red-100 text-red-600 rounded-lg hover:bg-red-200 transition-colors">
                            {t('common.cancel')}
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {transfers.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Create Transfer Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-800">{t('warehouse.newTransfer')}</h3>
              <button onClick={() => { setShowModal(false); setErr(''); }} className="text-slate-400 hover:text-slate-600">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Kimdan (ombor)</label>
                  <select value={form.from_warehouse_id} onChange={e => setForm(f => ({...f, from_warehouse_id: e.target.value}))}
                    className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="">Tanlang...</option>
                    {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Kimga (ombor)</label>
                  <select value={form.to_warehouse_id} onChange={e => setForm(f => ({...f, to_warehouse_id: e.target.value}))}
                    className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="">Tanlang...</option>
                    {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Izoh (ixtiyoriy)</label>
                <input value={form.note} onChange={e => setForm(f => ({...f, note: e.target.value}))}
                  placeholder="Sabab yoki izoh..."
                  className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Mahsulotlar</label>
                  <button onClick={addItem} className="text-xs text-indigo-600 font-semibold hover:text-indigo-800">+ Qo'shish</button>
                </div>
                {form.items.map((it, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <select value={it.product_id} onChange={e => setItem(idx, 'product_id', e.target.value)}
                      className="flex-1 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="">Mahsulot tanlang...</option>
                      {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <input type="number" min="1" value={it.quantity} onChange={e => setItem(idx, 'quantity', e.target.value)}
                      placeholder={t('admin.dict.qty') || 'Miqdor'}
                      className="w-24 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    {form.items.length > 1 && (
                      <button onClick={() => removeItem(idx)} className="text-red-400 hover:text-red-600">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {err && <p className="text-sm text-red-500 font-medium">{err}</p>}
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
              <button onClick={() => { setShowModal(false); setErr(''); }}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
              <button onClick={submit} disabled={saving}
                className="px-5 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('warehouse.transfer')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── OMBORLAR TAB ──────────────────────────────────────────────────────────
function OmborlarTab() {
  const { t } = useLang();
  const [warehouses, setWarehouses] = useState([]);
  const [branches, setBranches]     = useState([]);
  const [loading, setLoading]       = useState(true);
  const [modal, setModal]           = useState(null);
  const [name, setName]             = useState('');
  const [branchId, setBranchId]     = useState('');
  const [saving, setSaving]         = useState(false);
  const [err, setErr]               = useState('');
  const [delConfirm, setDelConfirm] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [wh, br] = await Promise.all([
        api.get('/warehouses'),
        api.get('/branches').catch(() => ({ data: [] })),
      ]);
      setWarehouses(wh.data);
      setBranches(br.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!name.trim()) { setErr("Nomi bo'sh bo'lmasin"); return; }
    setSaving(true); setErr('');
    try {
      const payload = { name: name.trim(), branch_id: branchId ? Number(branchId) : null };
      if (modal.mode === 'create') await api.post('/warehouses', payload);
      else await api.patch(`/warehouses/${modal.wh.id}`, payload);
      setModal(null); load();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik yuz berdi'); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    try { await api.delete(`/warehouses/${delConfirm.id}`); setDelConfirm(null); load(); }
    catch (e) { alert(e.response?.data?.detail || 'Xatolik'); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">Barcha omborlar ro'yxati</p>
        <button
          onClick={() => { setName(''); setBranchId(''); setErr(''); setModal({ mode: 'create' }); }}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('warehouse.newTransfer')}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Nomi</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Filial</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Yaratilgan</th>
                <th className="px-4 py-3 w-24" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {warehouses.map((wh, i) => (
                <tr key={wh.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-400">{i + 1}</td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{wh.name}</td>
                  <td className="px-4 py-3 text-sm text-slate-500">{branches.find(b => b.id === wh.branch_id)?.name || '—'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(wh.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => { setName(wh.name); setBranchId(wh.branch_id ?? ''); setErr(''); setModal({ mode: 'edit', wh }); }}
                        className="p-1.5 bg-indigo-100 text-indigo-600 hover:bg-indigo-200 rounded-lg transition-colors" title="Tahrirlash">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536M9 13l6.5-6.5a2 2 0 012.828 0l.172.172a2 2 0 010 2.828L12 16H9v-3z" />
                        </svg>
                      </button>
                      <button onClick={() => setDelConfirm(wh)}
                        className="p-1.5 bg-red-100 text-red-500 hover:bg-red-200 rounded-lg transition-colors" title="O'chirish">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {warehouses.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-12 text-center text-sm text-slate-400">{t('warehouse.noStocks')}</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Ombor Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-800">
                {modal.mode === 'create' ? t('warehouse.newTransfer') : t('common.edit')}
              </h3>
              <button onClick={() => setModal(null)} className="text-slate-400 hover:text-slate-600">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Nomi *</label>
                <input autoFocus value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && save()}
                  placeholder="Ombor nomi..."
                  className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              {branches.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Filial (ixtiyoriy)</label>
                  <select value={branchId} onChange={e => setBranchId(e.target.value)}
                    className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="">— Filialsiz —</option>
                    {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              )}
              {err && <p className="text-sm text-red-500">{err}</p>}
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
              <button onClick={() => setModal(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
              <button onClick={save} disabled={saving}
                className="px-5 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {delConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-5">
              <h3 className="text-base font-bold text-slate-800 mb-2">O'chirishni tasdiqlang</h3>
              <p className="text-sm text-slate-500">
                <span className="font-semibold text-slate-700">"{delConfirm.name}"</span> omborini o'chirishni xohlaysizmi?
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
              <button onClick={() => setDelConfirm(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                {t('common.cancel')}
              </button>
              <button onClick={remove}
                className="px-4 py-2 bg-red-500 text-white text-sm font-semibold rounded-xl hover:bg-red-600 transition-colors">
                {t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── MAIN OMBOR PAGE ────────────────────────────────────────────────────────
export default function Ombor() {
  const { t } = useLang();
  const [activeTab, setActiveTab] = useState('qoldiq');

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-linear-to-br from-indigo-500 to-indigo-700 flex items-center justify-center shadow-lg shadow-indigo-900/20">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-800">{t('warehouse.title')}</h2>
          <p className="text-xs text-slate-500">{t('warehouse.inventory')}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-2xl">
        {[
          { id: 'qoldiq',    label: t('warehouse.stockLevel') || 'Остатки',   icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
          { id: 'kirim',     label: t('ops.incoming') || 'Приход',        icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12' },
          { id: 'chiqim',    label: t('ops.outgoing') || 'Расход',       icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4' },
          { id: 'kochirish', label: t('warehouse.transfer') || 'Перемещение',   icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
          { id: 'omborlar',  label: t('nav.warehouse') || 'Склады',     icon: 'M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4' },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 ${
              activeTab === tab.id
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
            </svg>
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'qoldiq'    && <QoldiqlarTab />}
      {activeTab === 'kirim'     && <MovementsTab type="in" />}
      {activeTab === 'chiqim'    && <MovementsTab type="out" />}
      {activeTab === 'kochirish' && <KochirTab />}
      {activeTab === 'omborlar'  && <OmborlarTab />}
    </div>
  );
}
