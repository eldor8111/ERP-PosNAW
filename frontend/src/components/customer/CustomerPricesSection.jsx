import { useState, useEffect, useCallback } from 'react';
import { Search, Trash2, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';

const fmt = (n) => Number(n || 0).toLocaleString('uz-UZ');

/**
 * T3.19 — Mijozning maxsus (individual) narxlari.
 * GET/POST/DELETE /customers/{id}/prices; sotuvda server bu narxni ro'yxat narxi sifatida qo'llaydi.
 */
export default function CustomerPricesSection({ customerId, canEdit = true }) {
  const { t } = useLang();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [picked, setPicked] = useState(null);
  const [price, setPrice] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    if (!customerId) return;
    setLoading(true);
    api.get(`/customers/${customerId}/prices`, { _silent: true, _suppressToast: true })
      .then(r => setRows(Array.isArray(r.data) ? r.data : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [customerId]);

  useEffect(() => { load(); }, [load]);

  // Mahsulot qidirish (nomi / SKU / shtrix-kod), kechiktirilgan so'rov
  useEffect(() => {
    const q = query.trim();
    if (picked || q.length < 2) { setResults([]); return undefined; }
    let cancelled = false;
    const timer = setTimeout(() => {
      api.get('/products/', { params: { search: q, limit: 10, status: 'active' }, _silent: true, _suppressToast: true })
        .then(r => { if (!cancelled) setResults(Array.isArray(r.data) ? r.data : (r.data?.items || [])); })
        .catch(() => { if (!cancelled) setResults([]); });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, picked]);

  const pick = (p) => {
    setPicked(p); setQuery(p.name); setResults([]);
    setPrice(String(p.sale_price || ''));
  };

  const add = async () => {
    const value = parseFloat(price);
    if (!picked) { toast.error(tf('customer.specialPriceNeedProduct', 'Mahsulotni tanlang')); return; }
    if (!(value > 0)) { toast.error(tf('customer.specialPriceNeedValue', "Narx 0 dan katta bo'lishi kerak")); return; }
    setSaving(true);
    try {
      await api.post(`/customers/${customerId}/prices`, { product_id: picked.id, price: value });
      setPicked(null); setQuery(''); setPrice('');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || tf('common.error', 'Xatolik'));
    } finally { setSaving(false); }
  };

  const remove = async (productId) => {
    try {
      await api.delete(`/customers/${customerId}/prices/${productId}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || tf('common.error', 'Xatolik'));
    }
  };

  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1">{tf('customer.specialPrices', 'Maxsus narxlar')}</label>
      <p className="text-[11px] text-slate-400 mb-2">
        {tf('customer.specialPricesHint', "Bu mijozga sotuvda mahsulot narxi shu yerdagi narx bilan hisoblanadi")}
      </p>

      {canEdit && (
        <div className="flex flex-col sm:flex-row gap-2 mb-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={query}
              onChange={e => { setQuery(e.target.value); setPicked(null); }}
              placeholder={tf('customer.specialPriceSearch', 'Mahsulot nomi, SKU yoki shtrix-kod')}
            />
            {results.length > 0 && (
              <div className="absolute left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-48 overflow-y-auto z-10">
                {results.map(p => (
                  <button type="button" key={p.id} onClick={() => pick(p)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 flex justify-between gap-2">
                    <span className="truncate">{p.name}</span>
                    <span className="text-xs text-slate-400 shrink-0">{fmt(p.sale_price)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <input
            type="number" min="0"
            className="w-full sm:w-32 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={price} onChange={e => setPrice(e.target.value)}
            placeholder={tf('customer.specialPricePlaceholder', 'Narx')}
          />
          <button type="button" onClick={add} disabled={saving}
            className="flex items-center justify-center gap-1 px-3 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50">
            <Plus className="w-4 h-4" />
            {tf('customer.specialPriceAdd', "Qo'shish")}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-xs text-slate-400">...</div>
      ) : rows.length === 0 ? (
        <div className="text-xs text-slate-400">{tf('customer.specialPricesEmpty', "Maxsus narxlar yo'q")}</div>
      ) : (
        <div className="border border-slate-200 rounded-xl divide-y divide-slate-100 max-h-56 overflow-y-auto">
          {rows.map(r => (
            <div key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <div className="min-w-0">
                <div className="truncate font-medium text-slate-700">{r.product_name}</div>
                <div className="text-[11px] text-slate-400">{r.sku} · {tf('customer.specialPriceList', "Ro'yxat narxi")}: {fmt(r.sale_price)}</div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="font-bold text-slate-800">{fmt(r.price)}</span>
                {canEdit && (
                  <button type="button" onClick={() => remove(r.product_id)}
                    className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg" title={t('common.delete')}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
