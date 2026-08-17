import { useState, useEffect, useRef } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';

const BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8010/api').replace('/api', '');

const genBarcode = () => Math.floor(10000000 + Math.random() * 90000000).toString();
const BARCODE_FORMATS = [
  { value: 'ean8',  label: 'EAN-8',  len: 8 },
  { value: 'ean13', label: 'EAN-13', len: 13 },
  { value: 'upca',  label: 'UPC-A',  len: 12 },
  { value: 'free',  label: 'Erkin',  len: null },
];
const genBarcodeByFormat = (fmtVal) => {
  const f = BARCODE_FORMATS.find(f => f.value === fmtVal) || BARCODE_FORMATS[0];
  if (!f.len) return genBarcode();
  const min = Math.pow(10, f.len - 1);
  return String(Math.floor(min + Math.random() * (9 * Math.pow(10, f.len - 1))));
};
const genSku = () => 'SKU-' + Math.random().toString(36).substring(2, 8).toUpperCase();
const fmt = (v) => { const n = Number(v); return isNaN(n) ? '0' : n.toLocaleString('ru-RU'); };

const emptyForm = {
  name: '', sku: '', product_code: '', extra_product_codes: [],
  barcode: '', barcode_format: 'ean8', extra_barcodes: [],
  brand: '', category_id: '', unit: 'dona',
  cost_price: '', wholesale_price: '', sale_price: '',
  cost_price_cur: '', wholesale_price_cur: '', sale_price_cur: '',
  initial_stock: '', min_stock: 0, max_stock: '',
  bin_location: '', images: [], weight: '', dimensions: '', status: 'active',
  product_type: 'simple', conversion_source_id: '', conversion_source_name: '', conversion_ratio: 1,
  expiry_date: '',
  variants: [], // { size: '', color: '', sku: '', barcode: '', cost_price: '', wholesale_price: '', sale_price: '' }
};

const inputCls = "w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white";
const errCls   = "border-red-400 ring-1 ring-red-400";

function Field({ label, required, hint, children }) {
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

function ImageUploadZone({ images, onAdd, onRemove, uploading }) {
  const inputRef = useRef(null);
  const handleDrop = (e) => {
    e.preventDefault();
    Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/')).forEach(onAdd);
  };
  return (
    <div className="space-y-3">
      <div className="border-2 border-dashed border-slate-200 rounded-xl p-5 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-all"
        onClick={() => inputRef.current?.click()} onDragOver={e => e.preventDefault()} onDrop={handleDrop}>
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
              <img src={url.startsWith('/static') ? BASE_URL + url : url} alt="" className="w-full h-full object-cover" />
              {i === 0 && <span className="absolute bottom-0 left-0 right-0 text-center bg-blue-600/80 text-white text-[10px] py-0.5">Asosiy</span>}
              <button type="button" onClick={() => onRemove(i)}
                className="absolute top-1 right-1 w-5 h-5 bg-red-500 rounded-full text-white text-xs hidden group-hover:flex items-center justify-center">×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CurrencyDropdown({ value, onChange, currencies }) {
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
      <button type="button" onClick={() => setOpen(o => !o)}
        className={`px-3 text-xs font-bold border-l border-slate-200 flex items-center gap-1.5 whitespace-nowrap transition-colors rounded-r-xl ${selected ? 'bg-blue-500 text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'}`}>
        <span>{selected ? `${selected.code} | ${fmt(selected.rate)}` : 'UZS | 1'}</span>
        <svg className={`w-3 h-3 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] bg-white border border-slate-200 rounded-xl shadow-xl z-[200] min-w-[170px] py-1 overflow-hidden">
          <button type="button" onClick={() => { onChange(''); setOpen(false); }}
            className={`w-full px-4 py-2.5 text-left text-sm flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${!value ? 'text-blue-600 font-semibold bg-blue-50' : 'text-slate-700'}`}>
            <span>UZS</span><span className="text-xs text-slate-400">1</span>
          </button>
          {currencies.filter(c => !c.is_default).map(c => (
            <button key={c.id} type="button" onClick={() => { onChange(String(c.id)); setOpen(false); }}
              className={`w-full px-4 py-2.5 text-left text-sm flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${String(value) === String(c.id) ? 'text-blue-600 font-semibold bg-blue-50' : 'text-slate-700'}`}>
              <span>{c.code}</span><span className="text-xs text-slate-400">{fmt(c.rate)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ProdSearch({ value, onChange, placeholder = 'Asosiy mahsulotni qidiring...' }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
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
      try {
        const { data } = await api.get('/products/pos-list', { params: { search: q.replace(/['`’‘]/g, "'").toLowerCase(), limit: 50 } });
        setResults((Array.isArray(data) ? data : []).filter(i => (i.product_type || 'stock') === 'stock'));
      } catch (e) {}
    }, 400);
    return () => clearTimeout(timer);
  }, [q]);

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="relative">
        <input
          className={inputCls}
          placeholder={placeholder}
          value={q}
          onChange={e => { setQ(e.target.value); setOpen(true); if(!e.target.value) onChange({ id: '', name: '' }); }}
          onFocus={() => setOpen(true)}
        />
        {value?.id && (
          <button type="button" onClick={() => { onChange({ id: '', name: '' }); setQ(''); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-red-500 bg-white p-1 rounded-full">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        )}
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-[200] left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-60 overflow-y-auto overflow-x-hidden">
          {results.map(r => (
            <div key={r.id} onClick={() => { onChange(r); setQ(r.name); setOpen(false); }}
              className="px-4 py-3 hover:bg-blue-50 cursor-pointer border-b border-slate-50 last:border-0 flex justify-between items-center transition-colors">
              <span className="font-semibold text-slate-700 text-sm">{r.name}</span>
              <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded">{r.sku}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ProductAddModal({ onClose, onSaved }) {
  const [form, setForm] = useState({ ...emptyForm, barcode: genBarcodeByFormat('ean8') });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [imgUploading, setImgUploading] = useState(false);

  const [categories, setCategories] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [binLocations, setBinLocations] = useState([]);

  const [catModal, setCatModal] = useState(false);
  const [catForm, setCatForm] = useState({ name: '', parent_id: '', sort_order: 0 });
  const [catSaving, setCatSaving] = useState(false);

  useEffect(() => {
    api.get('/categories/all').then(r => setCategories(r.data)).catch(() => {});
    api.get('/currencies/').then(r => setCurrencies(r.data)).catch(() => {});
    api.get('/bin-locations').then(r => setBinLocations(r.data)).catch(() => {});
  }, []);

  const handleImageFile = async (file) => {
    setImgUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/uploads/product-image', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setForm(prev => ({ ...prev, images: [...prev.images, r.data.url] }));
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Rasm yuklashda xatolik');
    } finally { setImgUploading(false); }
  };

  const rateFor = (curId) => {
    if (!curId) return 1;
    const c = currencies.find(c => String(c.id) === String(curId));
    return c ? Number(c.rate) : 1;
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.name?.trim())    { setError("Mahsulot nomini kiriting"); return; }
    if (!form.barcode?.trim()) { setError("Barkodni kiriting"); return; }
    if (form.sale_price === '' || form.sale_price === null) { setError("Chakana (sotuv) narxini kiriting"); return; }
    
    const hasConversion = Boolean(form.conversion_source_id && Number(form.conversion_source_id) > 0);
    const effectiveType = hasConversion ? 'sell' : form.product_type;

    if (effectiveType === 'sell') {
      if (!hasConversion) { setError("Tarkibiy mahsulot uchun asosiy mahsulotni tanlang (masalan: Butun qo'y)"); return; }
      if (!form.conversion_ratio || Number(form.conversion_ratio) <= 0) { setError("Virtual mahsulot uchun nisbatni to'g'ri kiriting"); return; }
    }

    setSaving(true); setError('');
    try {
      const payload = {
        name:             form.name.trim(),
        sku:              form.sku?.trim() || genSku(),
        product_code:     form.product_code?.trim() || null,
        extra_product_codes: (form.extra_product_codes || []).filter(c => c.trim()),
        barcode:          form.barcode.trim(),
        extra_barcodes:   (form.extra_barcodes || []).filter(b => b.trim()),
        brand:            form.brand?.trim() || null,
        category_id:      form.category_id ? Number(form.category_id) : null,
        unit:             form.unit,
        cost_price:       Math.round((Number(form.cost_price) || 0) * rateFor(form.cost_price_cur)),
        wholesale_price:  form.wholesale_price !== '' ? Math.round(Number(form.wholesale_price) * rateFor(form.wholesale_price_cur)) : null,
        sale_price:       Math.round(Number(form.sale_price) * rateFor(form.sale_price_cur)),
        min_stock:        Number(form.min_stock) || 0,
        max_stock:        form.max_stock ? Number(form.max_stock) : null,
        bin_location:     form.bin_location?.trim() || null,
        images:           form.images.length ? form.images : null,
        image_url:        form.images[0] || null,
        weight:           form.weight !== '' ? Number(form.weight) : null,
        dimensions:       form.dimensions?.trim() || null,
        status:           form.status,
        initial_stock:    form.initial_stock !== '' ? Number(form.initial_stock) : 0,
        product_type:     effectiveType === 'stock' ? 'simple' : effectiveType,
        expiry_date:      form.expiry_date || null,
        attributes: [
          ...(form.size ? [{ name: "O'lcham", value: form.size }] : []),
          ...(form.color ? [{ name: 'Rang', value: form.color }] : [])
        ].length > 0 ? [
          ...(form.size ? [{ name: "O'lcham", value: form.size }] : []),
          ...(form.color ? [{ name: 'Rang', value: form.color }] : [])
        ] : null,
        variants:         form.product_type === 'variant' ? form.variants.map(v => ({
          ...v,
          cost_price: v.cost_price ? Number(v.cost_price) : null,
          wholesale_price: v.wholesale_price ? Number(v.wholesale_price) : null,
          sale_price: v.sale_price ? Number(v.sale_price) : null
        })) : null
      };

      if (effectiveType === 'sell') {
        payload.conversion = {
          source_product_id: Number(form.conversion_source_id),
          ratio: Number(form.conversion_ratio),
        };
      }
      const res = await api.post('/products', payload);
      toast.success("Mahsulot qo'shildi");
      onSaved?.(res.data);
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map(d => d.msg).join(' | ') : (String(detail || "Xatolik yuz berdi")));
    } finally { setSaving(false); }
  };

  const saveCat = async (e) => {
    e.preventDefault();
    if (!catForm.name.trim()) return;
    setCatSaving(true);
    try {
      const r = await api.post('/categories', { name: catForm.name.trim(), parent_id: catForm.parent_id ? Number(catForm.parent_id) : null, sort_order: Number(catForm.sort_order) || 0 });
      setCategories(prev => [...prev, r.data]);
      setForm(f => ({ ...f, category_id: String(r.data.id) }));
      setCatModal(false);
      toast.success("Kategoriya qo'shildi");
    } catch { toast.error("Xatolik"); }
    finally { setCatSaving(false); }
  };

  const priceCur = form.cost_price_cur || form.wholesale_price_cur || form.sale_price_cur;
  const priceCurSelected = priceCur ? currencies.find(c => String(c.id) === priceCur) : null;
  const priceRate = priceCurSelected ? Number(priceCurSelected.rate) : 1;
  const priceCurCode = priceCurSelected ? priceCurSelected.code : 'so\'m';

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[94vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 md:px-7 py-4 md:py-5 border-b border-slate-100 shrink-0">
          <h3 className="text-lg md:text-xl font-bold text-slate-800">Yangi mahsulot qo'shish</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1">
          <form onSubmit={handleSave} className="p-4 md:p-7">
            {error && (
              <div className="flex items-start gap-2.5 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl mb-6">
                <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-8">
              {/* LEFT */}
              <div className="md:col-span-2 space-y-5">
                <Field label="Mahsulot nomi" required>
                  <input autoFocus className={`${inputCls} text-base ${!form.name?.trim() && error ? errCls : ''}`}
                    value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Masalan: Coca-Cola 0.5L" />
                </Field>

                <Field label="Mahsulot turi">
                  <div className="bg-slate-50 p-2 rounded-2xl border border-slate-200 flex flex-col sm:flex-row gap-2">
                    <button
                      type="button"
                      onClick={() => setForm(f => ({ ...f, product_type: 'simple', conversion_source_id: '', conversion_source_name: '', conversion_ratio: 1 }))}
                      className={`flex-1 py-3 px-2 rounded-xl font-bold text-xs md:text-sm flex flex-col items-center justify-center gap-1 transition-all duration-300 ${form.product_type === 'simple' || form.product_type === 'stock' ? 'bg-blue-600 text-white shadow-md shadow-blue-200 ring-2 ring-blue-600 ring-offset-2' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'}`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
                      Oddiy mahsulot
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm(f => ({ ...f, product_type: 'variant', conversion_source_id: '', conversion_source_name: '', conversion_ratio: 1 }))}
                      className={`flex-1 py-3 px-2 rounded-xl font-bold text-xs md:text-sm flex flex-col items-center justify-center gap-1 transition-all duration-300 ${form.product_type === 'variant' ? 'bg-emerald-500 text-white shadow-md shadow-emerald-200 ring-2 ring-emerald-500 ring-offset-2' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'}`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
                      Variantli mahsulot
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm(f => ({ ...f, product_type: 'sell' }))}
                      className={`flex-1 py-3 px-2 rounded-xl font-bold text-xs md:text-sm flex flex-col items-center justify-center gap-1 transition-all duration-300 ${form.product_type === 'sell' ? 'bg-orange-500 text-white shadow-md shadow-orange-200 ring-2 ring-orange-500 ring-offset-2' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'}`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                      Tarkibiy (Kalk.)
                    </button>
                  </div>
                </Field>

                {form.product_type === 'sell' && (
                  <div className="bg-orange-50/50 p-5 rounded-2xl border border-orange-100 space-y-4 animate-fadeIn">
                    <h4 className="text-sm font-black text-orange-900 flex items-center gap-2">
                      <svg className="w-5 h-5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                      Kalkulyatsiya sozlamalari
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <Field label="Qaysi mahsulotdan yechiladi?" required>
                        <ProdSearch 
                          value={{ id: form.conversion_source_id, name: form.conversion_source_name }}
                          onChange={v => setForm(f => ({ ...f, conversion_source_id: v.id, conversion_source_name: v.name }))}
                        />
                      </Field>
                      <Field label="Nisbat (1 dona uchun)" required hint="Masalan: 1 kg go'sht uchun = 1">
                        <input type="number" step="0.001" min="0" className={inputCls}
                          value={form.conversion_ratio} onChange={e => setForm(f => ({ ...f, conversion_ratio: e.target.value }))}
                          placeholder="1" />
                      </Field>
                    </div>
                  </div>
                )}
                {/* Maxsus Sozlamalar (Kiyim, Dorixona) */}
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" /></svg>
                    </div>
                    <div>
                      <h4 className="text-sm font-black text-slate-800">Qo'shimcha parametrlar</h4>
                      <p className="text-[11px] text-slate-500">Kiyim-kechak, Dorixona va Maxsus mahsulotlar uchun</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Yaroqlilik muddati */}
                    <div>
                      <label className="block text-xs font-semibold text-amber-700 mb-1.5 flex items-center gap-1.5">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                        Yaroqlilik muddati
                      </label>
                      <input type="date" className={`${inputCls} border-amber-200 focus:ring-amber-500`}
                        value={form.expiry_date || ''} onChange={e => setForm({ ...form, expiry_date: e.target.value })} />
                    </div>
                    {/* Kiyim do'kon uchun - agar oddiy mahsulot bo'lsa umumiy o'lcham va rang */}
                    {form.product_type !== 'variant' && (
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-xs font-semibold text-emerald-700 mb-1.5">O'lcham (Razmer)</label>
                          <input type="text" className={`${inputCls} border-emerald-200 focus:ring-emerald-500`} placeholder="Masalan: XL, 42"
                            value={form.size || ''} onChange={e => setForm({ ...form, size: e.target.value })} />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-emerald-700 mb-1.5">Rang (Color)</label>
                          <input type="text" className={`${inputCls} border-emerald-200 focus:ring-emerald-500`} placeholder="Masalan: Qora"
                            value={form.color || ''} onChange={e => setForm({ ...form, color: e.target.value })} />
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {form.product_type === 'variant' && (
                  <div className="bg-emerald-50/50 p-5 rounded-2xl border border-emerald-100 space-y-4 animate-fadeIn">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-black text-emerald-900 flex items-center gap-2">
                        <svg className="w-5 h-5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                        Variantlar ro'yxati (Razmer, Rang, narxlar)
                      </h4>
                      <button type="button" 
                        onClick={() => setForm(f => ({ ...f, variants: [...(f.variants || []), { size: '', color: '', sku: genSku(), barcode: genBarcodeByFormat(form.barcode_format || 'ean8'), cost_price: '', wholesale_price: '', sale_price: '' }] }))}
                        className="px-3 py-1.5 bg-emerald-100 hover:bg-emerald-200 text-emerald-700 text-xs font-bold rounded-lg transition-colors flex items-center gap-1">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
                        Yangi variant
                      </button>
                    </div>

                    {(form.variants || []).length === 0 ? (
                      <div className="text-center py-4 text-emerald-600 text-sm border-2 border-dashed border-emerald-200 rounded-xl">
                        Hozircha variantlar yo'q. "Yangi variant" tugmasini bosing.
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm whitespace-nowrap">
                          <thead>
                            <tr className="text-emerald-800 border-b border-emerald-200">
                              <th className="pb-2 font-semibold w-24">Razmer</th>
                              <th className="pb-2 font-semibold w-24">Rang</th>
                              <th className="pb-2 font-semibold w-32">SKU</th>
                              <th className="pb-2 font-semibold w-32">Barkod</th>
                              <th className="pb-2 font-semibold w-32">Tan narx</th>
                              <th className="pb-2 font-semibold w-32">Sotuv narxi</th>
                              <th className="pb-2 font-semibold w-10"></th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-emerald-100">
                            {form.variants.map((v, i) => (
                              <tr key={i}>
                                <td className="py-2 pr-2">
                                  <input className="w-full px-2 py-1.5 border border-emerald-200 rounded-lg text-xs" placeholder="M, L, 42..." value={v.size} onChange={e => { const u = [...form.variants]; u[i].size = e.target.value; setForm({...form, variants: u}); }} />
                                </td>
                                <td className="py-2 pr-2">
                                  <input className="w-full px-2 py-1.5 border border-emerald-200 rounded-lg text-xs" placeholder="Qora, Oq..." value={v.color} onChange={e => { const u = [...form.variants]; u[i].color = e.target.value; setForm({...form, variants: u}); }} />
                                </td>
                                <td className="py-2 pr-2">
                                  <input className="w-full px-2 py-1.5 border border-emerald-200 rounded-lg text-xs font-mono" placeholder="SKU" value={v.sku} onChange={e => { const u = [...form.variants]; u[i].sku = e.target.value; setForm({...form, variants: u}); }} />
                                </td>
                                <td className="py-2 pr-2">
                                  <input className="w-full px-2 py-1.5 border border-emerald-200 rounded-lg text-xs font-mono" placeholder="Barkod" value={v.barcode} onChange={e => { const u = [...form.variants]; u[i].barcode = e.target.value; setForm({...form, variants: u}); }} />
                                </td>
                                <td className="py-2 pr-2">
                                  <input type="number" className="w-full px-2 py-1.5 border border-emerald-200 rounded-lg text-xs" placeholder="0" value={v.cost_price} onChange={e => { const u = [...form.variants]; u[i].cost_price = e.target.value; setForm({...form, variants: u}); }} />
                                </td>
                                <td className="py-2 pr-2">
                                  <input type="number" className="w-full px-2 py-1.5 border border-emerald-200 rounded-lg text-xs font-bold" placeholder="0" value={v.sale_price} onChange={e => { const u = [...form.variants]; u[i].sale_price = e.target.value; setForm({...form, variants: u}); }} />
                                </td>
                                <td className="py-2 text-right">
                                  <button type="button" onClick={() => setForm({...form, variants: form.variants.filter((_, idx) => idx !== i)})} className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                <Field label="Brend (ishlab chiqaruvchi)" hint="Masalan: Coca-Cola, Samsung, Nestle">
                  <input className={inputCls} value={form.brand}
                    onChange={e => setForm({ ...form, brand: e.target.value })} placeholder="Brend nomi (ixtiyoriy)" />
                </Field>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <Field label="SKU (Artikul)" hint="Bo'sh qolsa avtomatik yaratiladi">
                    <input className={inputCls} value={form.sku}
                      onChange={e => setForm({ ...form, sku: e.target.value })} placeholder="avtomatik" />
                  </Field>
                  <Field label="Birlamchi maxsus kod" hint="O'zingizning maxsus kodingiz">
                    <input className={inputCls} value={form.product_code}
                      onChange={e => setForm({ ...form, product_code: e.target.value })} placeholder="Ixtiyoriy" />
                  </Field>
                  <Field label="Birlamchi shtrix kod" required>
                    <div className="flex gap-2">
                      <select className="px-2 py-3 border border-slate-200 rounded-xl text-xs font-semibold bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-700 shrink-0"
                        value={form.barcode_format}
                        onChange={e => setForm({ ...form, barcode_format: e.target.value, barcode: genBarcodeByFormat(e.target.value) })}>
                        {BARCODE_FORMATS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                      </select>
                      <input className={`${inputCls} flex-1 font-mono ${!form.barcode?.trim() && error ? errCls : ''}`}
                        value={form.barcode} onChange={e => setForm({ ...form, barcode: e.target.value })} placeholder="12345678" />
                      <button type="button" onClick={() => setForm({ ...form, barcode: genBarcodeByFormat(form.barcode_format) })}
                        className="px-3 py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition-colors shrink-0">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                      </button>
                    </div>
                  </Field>
                </div>

                {/* Extra barcodes */}
                <div className="border border-slate-200 rounded-xl p-4 space-y-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold text-slate-600">Qo'shimcha shtrix kodlar</span>
                    <button type="button"
                      onClick={() => setForm(f => ({ ...f, extra_barcodes: [...(f.extra_barcodes || []), ''] }))}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 text-xs font-semibold rounded-lg transition-colors">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                      Barcode qo'shish
                    </button>
                  </div>
                  {(form.extra_barcodes || []).length === 0
                    ? <p className="text-xs text-slate-400 py-1">Hozircha qo'shimcha shtrix kod yo'q</p>
                    : (form.extra_barcodes || []).map((bc, idx) => (
                      <div key={idx} className="flex gap-2 items-center">
                        <span className="text-xs text-slate-400 font-mono w-5 shrink-0">{idx + 2}.</span>
                        <input id={`pam-bc-${idx}`} className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                          value={bc} autoFocus={idx === (form.extra_barcodes || []).length - 1 && bc === ''}
                          onChange={e => { const u = [...(form.extra_barcodes||[])]; u[idx]=e.target.value; setForm(f=>({...f,extra_barcodes:u})); }}
                          onKeyDown={e => { if(e.key==='Enter'&&bc.trim()){e.preventDefault();setForm(f=>{const n=[...(f.extra_barcodes||[])];if(idx===n.length-1)n.push('');return{...f,extra_barcodes:n}});setTimeout(()=>document.getElementById(`pam-bc-${idx+1}`)?.focus(),30);} }}
                          placeholder="Shtrix kod skanerlang..." />
                        <button type="button" onClick={() => setForm(f=>({...f,extra_barcodes:f.extra_barcodes.filter((_,i)=>i!==idx)}))}
                          className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </div>
                    ))
                  }
                </div>

                {/* Extra product codes */}
                <div className="border border-blue-100 rounded-xl p-4 space-y-2 bg-blue-50/30">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold text-slate-600">Qo'shimcha maxsus kodlar</span>
                    <button type="button"
                      onClick={() => setForm(f => ({ ...f, extra_product_codes: [...(f.extra_product_codes || []), ''] }))}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 text-xs font-semibold rounded-lg transition-colors border border-blue-200">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                      Kod qo'shish
                    </button>
                  </div>
                  {(form.extra_product_codes || []).length === 0
                    ? <p className="text-xs text-slate-400 py-1">Hozircha qo'shimcha kod yo'q</p>
                    : (form.extra_product_codes || []).map((pc, idx) => (
                      <div key={idx} className="flex gap-2 items-center">
                        <span className="text-xs text-slate-400 font-mono w-5 shrink-0">{idx + 1}.</span>
                        <input id={`pam-pc-${idx}`} className="flex-1 px-3 py-2 border border-blue-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                          value={pc} autoFocus={idx === (form.extra_product_codes || []).length - 1 && pc === ''}
                          onChange={e => { const u=[...(form.extra_product_codes||[])];u[idx]=e.target.value;setForm(f=>({...f,extra_product_codes:u})); }}
                          onKeyDown={e => { if(e.key==='Enter'&&pc.trim()){e.preventDefault();setForm(f=>{const n=[...(f.extra_product_codes||[])];if(idx===n.length-1)n.push('');return{...f,extra_product_codes:n}});setTimeout(()=>document.getElementById(`pam-pc-${idx+1}`)?.focus(),30);} }}
                          placeholder="Maxsus kod kiriting..." />
                        <button type="button" onClick={() => setForm(f=>({...f,extra_product_codes:f.extra_product_codes.filter((_,i)=>i!==idx)}))}
                          className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </div>
                    ))
                  }
                </div>

                {/* Category + Unit */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field label="Kategoriya">
                    <div className="flex gap-2">
                      <select className={`${inputCls} flex-1`} value={form.category_id}
                        onChange={e => setForm({ ...form, category_id: e.target.value })}>
                        <option value="">Kategoriyasiz</option>
                        {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                      <button type="button" onClick={() => setCatModal(true)}
                        className="shrink-0 w-11 h-11 flex items-center justify-center bg-blue-50 hover:bg-blue-100 text-blue-600 font-bold text-xl rounded-xl border-2 border-blue-100 hover:border-blue-300 transition-all">+</button>
                    </div>
                  </Field>
                  <Field label="O'lchov birligi">
                    <select className={inputCls} value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })}>
                      {['dona', 'kg', 'g', 'litr', 'ml', 'metr', 'sm', 'quti', 'paket', 'juft'].map(u => (
                        <option key={u} value={u}>{u}</option>
                      ))}
                    </select>
                  </Field>
                </div>

                {/* Prices */}
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-semibold text-slate-600 mb-1.5">Tan narxi</label>
                      <div className="flex rounded-xl border border-slate-200 focus-within:ring-2 focus-within:ring-blue-500 bg-white">
                        <input type="number" min="0" step="0.01" className="flex-1 min-w-0 px-3 py-3 text-base focus:outline-none bg-transparent rounded-l-xl"
                          value={form.cost_price} onChange={e => setForm({ ...form, cost_price: e.target.value })} placeholder="0" />
                        <CurrencyDropdown value={form.cost_price_cur} onChange={v => setForm({...form,cost_price_cur:v})} currencies={currencies} />
                      </div>
                      {form.cost_price_cur && (() => { const cur=currencies.find(c=>String(c.id)===form.cost_price_cur); return cur&&form.cost_price ? <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.cost_price)*Number(cur.rate)))} so'm</p> : null; })()}
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-slate-600 mb-1.5">Ulgurji narxi</label>
                      <div className="flex rounded-xl border border-slate-200 focus-within:ring-2 focus-within:ring-blue-500 bg-white">
                        <input type="number" min="0" step="0.01" className="flex-1 min-w-0 px-3 py-3 text-base focus:outline-none bg-transparent rounded-l-xl"
                          value={form.wholesale_price} onChange={e => setForm({ ...form, wholesale_price: e.target.value })} placeholder="—" />
                        <CurrencyDropdown value={form.wholesale_price_cur} onChange={v => setForm({...form,wholesale_price_cur:v})} currencies={currencies} />
                      </div>
                      {form.wholesale_price_cur && (() => { const cur=currencies.find(c=>String(c.id)===form.wholesale_price_cur); return cur&&form.wholesale_price ? <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.wholesale_price)*Number(cur.rate)))} so'm</p> : null; })()}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-600 mb-1.5">
                      Chakana (sotuv) narxi <span className="text-red-500">*</span>
                      <span className="ml-2 text-xs font-normal text-slate-400">Asosiy sotuv narxi</span>
                    </label>
                    <div className={`flex rounded-xl border focus-within:ring-2 focus-within:ring-blue-500 bg-white ${(form.sale_price===''||form.sale_price===null)&&error?'border-red-400 ring-1 ring-red-400':'border-slate-200'}`}>
                      <input type="number" min="0" step="0.01" className="flex-1 min-w-0 px-3 py-3 text-lg font-semibold focus:outline-none bg-transparent rounded-l-xl"
                        value={form.sale_price} onChange={e => setForm({ ...form, sale_price: e.target.value })} placeholder="0" />
                      <CurrencyDropdown value={form.sale_price_cur} onChange={v => setForm({...form,sale_price_cur:v})} currencies={currencies} />
                    </div>
                    {form.sale_price_cur && (() => { const cur=currencies.find(c=>String(c.id)===form.sale_price_cur); return cur&&form.sale_price ? <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.sale_price)*Number(cur.rate)))} so'm</p> : null; })()}
                  </div>
                </div>

                {priceCurSelected && (form.cost_price || form.sale_price) && (
                  <div className="px-4 py-3 bg-amber-50 border border-amber-100 rounded-xl text-sm text-amber-700 flex flex-wrap gap-x-5 gap-y-1">
                    <span className="font-semibold">UZS ekvivalenti:</span>
                    {form.cost_price && <span>Tan: <strong>{fmt(Math.round(Number(form.cost_price)*priceRate))}</strong></span>}
                    {form.wholesale_price && <span>Ulgurji: <strong>{fmt(Math.round(Number(form.wholesale_price)*priceRate))}</strong></span>}
                    {form.sale_price && <span>Chakana: <strong>{fmt(Math.round(Number(form.sale_price)*priceRate))}</strong></span>}
                  </div>
                )}

                {form.cost_price && form.sale_price && Number(form.sale_price) > 0 && (
                  <div className="px-4 py-3 bg-blue-50 rounded-xl text-sm text-blue-700">
                    Margin: <strong>{(((Number(form.sale_price)-Number(form.cost_price))/Number(form.sale_price))*100).toFixed(1)}%</strong>
                    &nbsp;|&nbsp; Foyda: <strong>{fmt(Number(form.sale_price)-Number(form.cost_price))} {priceCurCode}</strong>
                  </div>
                )}

                {/* Stock */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  <Field label="Boshlang'ich qoldiq">
                    <input type="number" min="0" step="0.01" className={`${inputCls} text-base`}
                      value={form.initial_stock} onChange={e => setForm({ ...form, initial_stock: e.target.value })} placeholder="0" />
                  </Field>
                  <Field label="Min qoldiq">
                    <input type="number" min="0" className={`${inputCls} text-base`}
                      value={form.min_stock} onChange={e => setForm({ ...form, min_stock: e.target.value })} />
                  </Field>
                  <Field label="Maks qoldiq">
                    <input type="number" min="0" className={`${inputCls} text-base`}
                      value={form.max_stock} onChange={e => setForm({ ...form, max_stock: e.target.value })} placeholder="Cheksiz" />
                  </Field>
                </div>
              </div>

              {/* RIGHT */}
              <div className="md:col-span-1 space-y-5">
                <Field label="Mahsulot rasmlari (JPG/PNG)">
                  <ImageUploadZone images={form.images} onAdd={handleImageFile} onRemove={i => setForm(f=>({...f,images:f.images.filter((_,j)=>j!==i)}))} uploading={imgUploading} />
                </Field>

                <Field label="Ombor joylashuvi" hint="Mahsulot saqlanadigan joyni tanlang">
                  <div className="flex gap-2">
                    <select className={`${inputCls} flex-1`} value={form.bin_location}
                      onChange={e => setForm({ ...form, bin_location: e.target.value })}>
                      <option value="">— Tanlang —</option>
                      {binLocations.map(b => <option key={b.id} value={b.code}>{b.code}{b.label ? ` — ${b.label}` : ''}</option>)}
                    </select>
                  </div>
                </Field>

                <div className="grid grid-cols-2 sm:grid-cols-2 gap-3">
                  <Field label="Vazn (kg)">
                    <input type="number" min="0" step="0.001" className={inputCls}
                      value={form.weight} onChange={e => setForm({ ...form, weight: e.target.value })} placeholder="0.000" />
                  </Field>
                  <Field label="O'lchamlar (sm)">
                    <input className={inputCls} value={form.dimensions}
                      onChange={e => setForm({ ...form, dimensions: e.target.value })} placeholder="UxBxH" />
                  </Field>
                </div>

                  {/* Yaroqlilik muddati endi maxsus bo'limga ko'chirildi */}

                  <Field label="Holat">
                    <select className={inputCls} value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
                      <option value="active">Faol</option>
                      <option value="inactive">Nofaol</option>
                      <option value="archived">Arxiv</option>
                    </select>
                  </Field>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-8 pt-6 border-t border-slate-100">
              <button type="button" onClick={onClose}
                className="flex-1 py-3 border border-slate-200 text-slate-600 font-semibold text-base rounded-xl hover:bg-slate-50 transition-colors">
                Bekor qilish
              </button>
              <button type="submit" disabled={saving}
                className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-bold text-base rounded-xl transition-colors">
                {saving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Kategoriya qo'shish mini-modal */}
      {catModal && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/40" onClick={() => setCatModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <span className="font-black text-slate-800">Yangi kategoriya</span>
              <button onClick={() => setCatModal(false)} className="text-slate-400 hover:text-red-400">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <form onSubmit={saveCat} className="p-5 space-y-3">
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase mb-1 block">Nomi *</label>
                <input autoFocus required value={catForm.name} onChange={e => setCatForm({...catForm,name:e.target.value})}
                  placeholder="Kategoriya nomi..."
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-xs font-bold text-slate-500 uppercase mb-1 block">Yuqori kategoriya</label>
                <select value={catForm.parent_id} onChange={e => setCatForm({...catForm,parent_id:e.target.value})}
                  className="w-full border-2 border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                  <option value="">Asosiy kategoriya</option>
                  {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setCatModal(false)}
                  className="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm">Bekor</button>
                <button type="submit" disabled={catSaving}
                  className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm disabled:opacity-50">
                  {catSaving ? 'Saqlanmoqda...' : "Qo'shish"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
