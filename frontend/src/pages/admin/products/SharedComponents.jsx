// Products module — shared small components
// Extracted from Products.jsx for modularity

import { useRef, useState, useEffect, useLayoutEffect } from 'react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import toast from 'react-hot-toast';
import { EllipsisVertical } from 'lucide-react';
import { normalizeApos, fmt, inputCls } from './constants';

/* ─── ProdSearch for composite products ──────────────── */
export function ProdSearch({ value, onChange, placeholder = 'Mahsulot qidiring...', excludeId }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (value && value.name && !q) setQ(value.name);
  }, [value]);

  useEffect(() => {
    if (q.length < 2) { setResults([]); return; }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const searchQ = normalizeApos(q);
        const { data } = await api.get('/products/pos-list', { params: { search: searchQ, limit: 50 } });
        setResults((Array.isArray(data) ? data : []).filter(i => i.id !== excludeId && (i.product_type || 'stock') === 'stock'));
      } catch (e) {
        try {
          const searchQ = normalizeApos(q);
          const { data } = await api.get('/products', { params: { search: searchQ, limit: 50 } });
          setResults((Array.isArray(data) ? data : []).filter(i => i.id !== excludeId && i.product_type === 'stock'));
        } catch (e2) { }
      } finally { setLoading(false); }
    }, 400);
    return () => clearTimeout(timer);
  }, [q, excludeId]);

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="relative">
        <input
          className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          placeholder={placeholder}
          value={open ? q : (value?.name || '')}
          onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={(e) => { setOpen(true); e.target.select(); }}
        />
        {loading && <div className="absolute right-3 top-3"><span className="animate-pulse w-3 h-3 bg-blue-400 rounded-full inline-block"></span></div>}
      </div>
      {open && q.length >= 2 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-60 overflow-auto">
          {results.length > 0 ? results.map(p => (
            <div key={p.id}
              className="px-4 py-2.5 hover:bg-blue-50 cursor-pointer border-b border-slate-50 last:border-0"
              onClick={() => {
                onChange({ id: p.id, name: p.name });
                setQ(p.name);
                setOpen(false);
              }}
            >
              <div className="font-semibold text-slate-700 text-sm">{p.name}</div>
              <div className="text-xs text-slate-400 flex justify-between mt-0.5">
                <span>{p.barcode || p.sku}</span>
                <span>{p.unit}</span>
              </div>
            </div>
          )) : (
            <div className="px-4 py-3 text-sm text-slate-500 text-center">Bunday mahsulot topilmadi</div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── RowMenu (3 dots) ─────────────────────────────────── */
export function RowMenu({ onEdit, onDelete, onPrint }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0, visible: false });
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const openMenu = () => {
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setPos({ top: r.bottom + 4, right: window.innerWidth - r.right, visible: false });
    }
    setOpen(o => !o);
  };

  useLayoutEffect(() => {
    if (open && menuRef.current && btnRef.current) {
      const menuRect = menuRef.current.getBoundingClientRect();
      const btnRect = btnRef.current.getBoundingClientRect();
      if (menuRect.bottom > window.innerHeight - 8) {
        setPos({ top: btnRect.top - menuRect.height - 4, right: window.innerWidth - btnRect.right, visible: true });
      } else {
        setPos(p => ({ ...p, visible: true }));
      }
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target) && btnRef.current && !btnRef.current.contains(e.target))
        setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  return (
    <div className="relative">
      <button
        ref={btnRef}
        onClick={openMenu}
        className="w-10 cursor-pointer h-10 flex items-center justify-center rounded-xl text-blue-600 hover:text-blue-800 bg-blue-100 transition-colors"
        title="Ko'proq">
        <EllipsisVertical />
      </button>
      {open && (
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: pos.top, right: pos.right, zIndex: 9999, opacity: pos.visible ? 1 : 0, pointerEvents: pos.visible ? 'auto' : 'none' }}
          className="bg-white border border-slate-200 rounded-xl shadow-xl py-1.5 min-w-[190px]"
        >
          <button onClick={() => { onEdit(); setOpen(false); }}
            className="w-full flex items-center gap-2 xl:gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors">
            <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Tahrirlash
          </button>
          <button onClick={() => { onPrint(); setOpen(false); }}
            className="w-full flex items-center gap-2 xl:gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-blue-50 transition-colors">
            <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
            </svg>
            Shtrix-kod chop
          </button>
          <div className="mx-3 my-1 border-t border-slate-100" />
          <button onClick={() => { onDelete(); setOpen(false); }}
            className="w-full flex items-center gap-2 xl:gap-3 px-4 py-2.5 text-sm text-red-500 hover:bg-red-50 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            O'chirish
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── StatusBadge ──────────────────────────────────── */
export function StatusBadge({ status }) {
  const statusMeta = {
    active: { label: 'Faol' },
    inactive: { label: 'Nofaol' },
    archived: { label: 'Arxiv' },
  };
  const m = statusMeta[status] || { label: status };
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px] xl:text-[12px] font-semibold text-green-700">
      {m.label}
    </span>
  );
}

/* ─── Modal wrapper ────────────────────────────────── */
export function Modal({ title, onClose, children, size = 'md', z = 'z-50' }) {
  const { t } = useLang();
  const sizeMap = { sm: 'max-w-lg', md: 'max-w-2xl', lg: 'max-w-4xl', xl: 'max-w-6xl' };
  return (
    <div className={`fixed inset-0 ${z} flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm`} onClick={onClose}>
      <div
        className={`bg-white rounded-2xl shadow-2xl w-full ${sizeMap[size]} max-h-[94vh] flex flex-col`}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 md:px-7 py-4 md:py-5 border-b border-slate-100 shrink-0">
          <h3 className="text-lg md:text-xl font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  );
}

/* ─── Field wrapper ────────────────────────────────── */
export function Field({ label, required, children, hint }) {
  return (
    <div>
      <label className="block text-sm font-semibold text-slate-600 mb-1.5">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

/* ─── ImageUploadZone ──────────────────────────────── */
export function ImageUploadZone({ images, onAdd, onRemove, uploading, BASE_URL }) {
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    files.forEach(onAdd);
  };

  return (
    <div className="space-y-3">
      <div
        className="border-2 border-dashed border-slate-200 rounded-xl p-5 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-all"
        onClick={() => inputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
      >
        {uploading ? (
          <div className="flex flex-col items-center gap-2 text-blue-500">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs">Yuklanmoqda...</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-slate-400">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="text-xs font-medium">JPG, PNG rasm yuklash</span>
            <span className="text-xs">Bosing yoki shu yerga tashlang · maks 5MB</span>
          </div>
        )}
        <input ref={inputRef} type="file" multiple accept="image/jpeg,image/png,image/webp"
          className="hidden" onChange={e => Array.from(e.target.files).forEach(onAdd)} />
      </div>

      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((url, i) => (
            <div key={url + i} className="relative group w-20 h-20 rounded-xl overflow-hidden border border-slate-200 shrink-0">
              <img
                src={url.startsWith('/static') ? BASE_URL + url : url}
                alt=""
                className="w-full h-full object-cover"
              />
              {i === 0 && (
                <span className="absolute bottom-0 left-0 right-0 text-center bg-blue-600/80 text-white text-[10px] py-0.5">Asosiy</span>
              )}
              <button
                type="button"
                onClick={() => onRemove(i)}
                className="absolute top-1 right-1 w-5 h-5 bg-red-500 rounded-full text-white text-xs hidden group-hover:flex items-center justify-center"
              >×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── CurrencyDropdown ─────────────────────────────── */
export function CurrencyDropdown({ value, onChange, currencies }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    if (open) document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const selected = value ? currencies.find(c => String(c.id) === String(value)) : null;

  return (
    <div ref={ref} className="relative shrink-0 flex items-stretch">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={`px-3 text-xs font-bold border-l border-slate-200 flex items-center gap-1.5 whitespace-nowrap transition-colors rounded-r-xl ${selected ? 'bg-blue-500 text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'}`}
      >
        <span>{selected ? `${selected.code} | ${fmt(selected.rate)}` : 'UZS | 1'}</span>
        <svg className={`w-3 h-3 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] bg-white border border-slate-200 rounded-xl shadow-xl z-[200] min-w-[170px] py-1 overflow-hidden">
          <button type="button"
            onClick={() => { onChange(''); setOpen(false); }}
            className={`w-full px-4 py-2.5 text-left text-sm flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${!value ? 'text-blue-600 font-semibold bg-blue-50' : 'text-slate-700'}`}>
            <span>UZS</span>
            <span className="text-xs text-slate-400">1</span>
          </button>
          {currencies.filter(c => !c.is_default).map(c => (
            <button key={c.id} type="button"
              onClick={() => { onChange(String(c.id)); setOpen(false); }}
              className={`w-full px-4 py-2.5 text-left text-sm flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${String(value) === String(c.id) ? 'text-blue-600 font-semibold bg-blue-50' : 'text-slate-700'}`}>
              <span>{c.code}</span>
              <span className="text-xs text-slate-400">{fmt(c.rate)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── BulkStockEditModal ─────────────────────────────── */
export function BulkStockEditModal({ selectedIds, products, warehouses, onClose, onSuccess }) {
  const { t } = useLang();
  const [warehouseId, setWarehouseId] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const [items, setItems] = useState(() => {
    return products
      .filter(p => selectedIds.includes(p.id))
      .map(p => ({
        product: p,
        fact: '',
        reason: ''
      }));
  });

  const doSave = async () => {
    if (!warehouseId) { setErr("Omborni tanlang!"); return; }
    const validItems = items.filter(i => i.fact !== '');
    if (!validItems.length) { setErr("Kamida bitta mahsulot uchun yangi qoldiq kiriting!"); return; }

    setSaving(true); setErr('');
    try {
      const { data: count } = await api.post('/inventory-counts', {
        warehouse_id: Number(warehouseId),
        note: note || 'Tezkor qoldiq tahrirlash',
        category_ids: null
      });
      await api.post(`/inventory-counts/${count.id}/start`);
      const itemsPayload = validItems.map(c => ({
        product_id: c.product.id,
        counted_qty: Number(c.fact),
        variance_reason: c.reason || null
      }));
      await api.post(`/inventory-counts/${count.id}/items`, itemsPayload);
      await api.post(`/inventory-counts/${count.id}/finalize`);

      toast.success("Qoldiq muvaffaqiyatli yangilandi");
      onSuccess();
    } catch (e) {
      setErr(e.response?.data?.detail || "Saqlashda xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`Tanlangan mahsulotlar qoldig'ini tahrirlash (${selectedIds.length} ta)`} onClose={onClose} size="lg">
      <div className="p-5 flex flex-col gap-5">
        {selectedIds.length > items.length && (
          <div className="bg-amber-50 text-amber-700 p-3 rounded-xl text-sm font-medium flex items-center gap-2">
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            Siz boshqa sahifalardan ham mahsulot tanlagansiz. Hozir faqat shu sahifadagi {items.length} ta mahsulot ko'rsatilmoqda.
          </div>
        )}

        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <label className="block text-sm font-semibold text-slate-600 mb-1.5">Ombor tanlang *</label>
            <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
              <option value="">— Ombor tanlang —</option>
              {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm font-semibold text-slate-600 mb-1.5">Izoh (ixtiyoriy)</label>
            <input value={note} onChange={e => setNote(e.target.value)} placeholder="Tuzatish sababi..." className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white" />
          </div>
        </div>

        <div className="border border-slate-200 rounded-xl overflow-hidden max-h-[50vh] overflow-y-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3 font-semibold text-slate-500">Mahsulot</th>
                <th className="px-4 py-3 font-semibold text-slate-500 w-32 text-center">Tizim qoldig'i</th>
                <th className="px-4 py-3 font-semibold text-slate-500 w-40">Yangi (Faktik) qoldiq</th>
                <th className="px-4 py-3 font-semibold text-slate-500 w-48">Tafovut sababi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((it, idx) => (
                <tr key={it.product.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-800">{it.product.name}</td>
                  <td className="px-4 py-3 text-center text-slate-500 bg-slate-50/50">{it.product.stock_quantity || 0} {it.product.unit || 'dona'}</td>
                  <td className="px-4 py-2">
                    <input type="number" min="0" step="any" value={it.fact}
                      onChange={e => {
                        const val = e.target.value;
                        setItems(prev => prev.map((p, i) => i === idx ? { ...p, fact: val } : p));
                      }}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-bold"
                      placeholder="0"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input type="text" value={it.reason}
                      onChange={e => {
                        const val = e.target.value;
                        setItems(prev => prev.map((p, i) => i === idx ? { ...p, reason: val } : p));
                      }}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Sabab..."
                    />
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">Hech qanday mahsulot topilmadi</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {err && <div className="text-red-500 text-sm font-medium text-center">{err}</div>}

        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="px-5 py-2.5 text-sm font-semibold border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors">Bekor qilish</button>
          <button onClick={doSave} disabled={saving || !items.some(i => i.fact !== '')} className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-sm transition-all">
            {saving ? 'Saqlanmoqda...' : 'Saqlash va Yakunlash'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
