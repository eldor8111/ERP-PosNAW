import { useRef, useState, useEffect, useCallback, useId } from 'react';
import api from '../../api/axios';
import BarcodePrintModal from '../../components/BarcodeTemplates';

const BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace('/api', '');

/* ─── helpers ─────────────────────────────────────── */
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
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

const statusMeta = {
  active:   { label: 'Faol',   cls: 'bg-emerald-100 text-emerald-700' },
  inactive: { label: 'Nofaol', cls: 'bg-amber-100  text-amber-700' },
  archived: { label: 'Arxiv',  cls: 'bg-slate-100   text-slate-500' },
};

const movTypeMeta = {
  in:       { label: 'Kirim',    cls: 'bg-emerald-100 text-emerald-700' },
  out:      { label: 'Chiqim',   cls: 'bg-red-100 text-red-600' },
  adjust:   { label: 'Tuzatish', cls: 'bg-amber-100 text-amber-700' },
  transfer: { label: 'Ombor',    cls: 'bg-indigo-100 text-indigo-700' },
  sale:     { label: 'Sotuv',    cls: 'bg-violet-100 text-violet-700' },
  return:   { label: 'Qaytarma', cls: 'bg-orange-100 text-orange-700' },
};

const emptyProduct = {
  name: '', sku: '', barcode: '',
  barcode_format: 'ean8',
  brand: '',
  category_id: '', unit: 'dona',
  cost_price: '', wholesale_price: '', sale_price: '',
  cost_price_cur: '', wholesale_price_cur: '', sale_price_cur: '',
  price_currency_id: '',
  initial_stock: '',
  min_stock: 0, max_stock: '',
  bin_location: '',
  images: [],
  weight: '',
  dimensions: '',
  status: 'active',
};

/* ─── RowMenu (3 dots) ─────────────────────────────────── */
function RowMenu({ product, onEdit, onDelete, onPrint }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-10 h-10 flex items-center justify-center rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
        title="Ko'proq">
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
          <circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-1.5 min-w-[190px]">
          <button onClick={() => { onEdit(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors">
            <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Tahrirlash
          </button>
          <button onClick={() => { onPrint(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-indigo-50 transition-colors">
            <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
            </svg>
            Shtrix-kod chop
          </button>
          <div className="mx-3 my-1 border-t border-slate-100" />
          <button onClick={() => { onDelete(); setOpen(false); }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-500 hover:bg-red-50 transition-colors">
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

const emptyCategory = { name: '', parent_id: '', sort_order: 0 };
const emptyBinLoc   = { code: '', label: '' };

/* ─── StatusBadge ──────────────────────────────────── */
function StatusBadge({ status }) {
  const m = statusMeta[status] || { label: status, cls: 'bg-slate-100 text-slate-500' };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${m.cls}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {m.label}
    </span>
  );
}

/* ─── Modal wrapper ────────────────────────────────── */
function Modal({ title, onClose, children, size = 'md', z = 'z-50' }) {
  const sizeMap = { sm: 'max-w-lg', md: 'max-w-2xl', lg: 'max-w-4xl', xl: 'max-w-6xl' };
  return (
    <div className={`fixed inset-0 ${z} flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm`} onClick={onClose}>
      <div
        className={`bg-white rounded-2xl shadow-2xl w-full ${sizeMap[size]} max-h-[94vh] flex flex-col`}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-7 py-5 border-b border-slate-100 shrink-0">
          <h3 className="text-xl font-bold text-slate-800">{title}</h3>
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
function Field({ label, required, children, hint }) {
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

const inputCls = "w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white";
const errCls   = "border-red-400 ring-1 ring-red-400";

/* ─── ImageUploadZone ──────────────────────────────── */
function ImageUploadZone({ images, onAdd, onRemove, uploading }) {
  const inputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    files.forEach(onAdd);
  };

  return (
    <div className="space-y-3">
      {/* Upload area */}
      <div
        className="border-2 border-dashed border-slate-200 rounded-xl p-5 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/30 transition-all"
        onClick={() => inputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
      >
        {uploading ? (
          <div className="flex flex-col items-center gap-2 text-indigo-500">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
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

      {/* Thumbnails */}
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
                <span className="absolute bottom-0 left-0 right-0 text-center bg-indigo-600/80 text-white text-[10px] py-0.5">Asosiy</span>
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
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={`px-3 text-xs font-bold border-l border-slate-200 flex items-center gap-1.5 whitespace-nowrap transition-colors rounded-r-xl ${
          selected ? 'bg-indigo-500 text-white' : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
        }`}
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
            className={`w-full px-4 py-2.5 text-left text-sm flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${
              !value ? 'text-indigo-600 font-semibold bg-indigo-50' : 'text-slate-700'
            }`}>
            <span>UZS</span>
            <span className="text-xs text-slate-400">1</span>
          </button>
          {currencies.filter(c => !c.is_default).map(c => (
            <button key={c.id} type="button"
              onClick={() => { onChange(String(c.id)); setOpen(false); }}
              className={`w-full px-4 py-2.5 text-left text-sm flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${
                String(value) === String(c.id) ? 'text-indigo-600 font-semibold bg-indigo-50' : 'text-slate-700'
              }`}>
              <span>{c.code}</span>
              <span className="text-xs text-slate-400">{fmt(c.rate)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════ */
export default function Products() {
  const [printProduct, setPrintProduct] = useState(null);
  const [activeTab, setActiveTab] = useState('products');

  /* products state */
  const [products, setProducts]     = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [search, setSearch]         = useState('');
  const [filterCat, setFilterCat]   = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterWarehouse, setFilterWarehouse] = useState('');
  const [warehouses, setWarehouses]   = useState([]);

  /* currencies + bin locations */
  const [currencies, setCurrencies]     = useState([]);
  const [binLocations, setBinLocations] = useState([]);

  /* product modal */
  const [modal, setModal]       = useState(null);
  const [selected, setSelected] = useState(null);
  const [form, setForm]         = useState(emptyProduct);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');
  const [imgUploading, setImgUploading] = useState(false);

  /* history modal */
  const [histProduct, setHistProduct] = useState(null);
  const [history, setHistory]         = useState([]);
  const [histLoading, setHistLoading] = useState(false);

  /* category state */
  const [catModal, setCatModal]       = useState(null);
  const [catSelected, setCatSelected] = useState(null);
  const [catForm, setCatForm]         = useState(emptyCategory);
  const [catSaving, setCatSaving]     = useState(false);
  const [catError, setCatError]       = useState('');

  /* bin location state */
  const [blModal, setBlModal]       = useState(null);
  const [blSelected, setBlSelected] = useState(null);
  const [blForm, setBlForm]         = useState(emptyBinLoc);
  const [blSaving, setBlSaving]     = useState(false);
  const [blError, setBlError]       = useState('');

  /* ── loaders ────────────────────────────────────── */
  const loadCategories = useCallback(() => {
    api.get('/categories/all').then(r => setCategories(r.data)).catch(() => {});
  }, []);

  const loadBinLocations = useCallback(() => {
    api.get('/bin-locations').then(r => setBinLocations(r.data)).catch(() => {});
  }, []);

  const loadProducts = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (search)          params.append('search', search);
    if (filterCat)       params.append('category_id', filterCat);
    if (filterStatus)    params.append('status', filterStatus);
    if (filterWarehouse) params.append('warehouse_id', filterWarehouse);
    params.append('limit', '200');
    api.get('/products?' + params.toString())
      .then(r => setProducts(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [search, filterCat, filterStatus, filterWarehouse]);

  useEffect(() => {
    loadCategories();
    loadBinLocations();
    api.get('/currencies/').then(r => setCurrencies(r.data)).catch(() => {});
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (activeTab === 'products')   loadProducts();
    if (activeTab === 'categories') { loadCategories(); loadBinLocations(); }
  }, [activeTab, loadProducts]);

  useEffect(() => {
    const t = setTimeout(() => { if (activeTab === 'products') loadProducts(); }, 400);
    return () => clearTimeout(t);
  }, [search]);

  /* ── product CRUD ───────────────────────────────── */
  const openAdd = () => {
    setForm({ ...emptyProduct, barcode: genBarcodeByFormat('ean8') });
    setError('');
    setModal('add');
  };
  const openEdit = (p) => {
    setSelected(p);
    setForm({
      name: p.name, sku: p.sku, barcode: p.barcode,
      barcode_format: 'ean8',
      brand: p.brand || '',
      category_id: p.category_id || '', unit: p.unit,
      cost_price: p.cost_price, wholesale_price: p.wholesale_price ?? '',
      sale_price: p.sale_price,
      cost_price_cur: '', wholesale_price_cur: '', sale_price_cur: '',
      price_currency_id: '',
      initial_stock: '',
      min_stock: p.min_stock, max_stock: p.max_stock || '',
      bin_location: p.bin_location || '',
      images: Array.isArray(p.images) ? p.images : (p.image_url ? [p.image_url] : []),
      weight: p.weight ?? '',
      dimensions: p.dimensions || '',
      status: p.status,
    });
    setError('');
    setModal('edit');
  };
  const closeModal = () => { setModal(null); setSelected(null); setError(''); };

  /* ── image upload ─────────────────────────────── */
  const handleImageFile = async (file) => {
    setImgUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/uploads/product-image', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setForm(prev => ({ ...prev, images: [...prev.images, r.data.url] }));
    } catch (e) {
      alert(e.response?.data?.detail || 'Rasm yuklashda xatolik');
    } finally {
      setImgUploading(false);
    }
  };

  const removeImage = (idx) => {
    setForm(prev => ({ ...prev, images: prev.images.filter((_, i) => i !== idx) }));
  };

  /* ── history ─────────────────────────────────────── */
  const openHistory = async (p) => {
    setHistProduct(p);
    setHistory([]);
    setHistLoading(true);
    try {
      const r = await api.get(`/inventory/movements?product_id=${p.id}&limit=50`);
      setHistory(r.data);
    } catch {
      setHistory([]);
    } finally {
      setHistLoading(false);
    }
  };
  const closeHistory = () => { setHistProduct(null); setHistory([]); };

  /* ── save ────────────────────────────────────────── */
  const parseError = (err) => {
    const detail = err.response?.data?.detail;
    if (!detail) return "Server bilan bog'lanishda xatolik";
    if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join(' | ');
    return String(detail);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.name?.trim())    { setError("Mahsulot nomini kiriting"); return; }
    if (!form.barcode?.trim()) { setError("Barkodni kiriting"); return; }
    if (form.sale_price === '' || form.sale_price === null || form.sale_price === undefined) {
      setError("Chakana (sotuv) narxini kiriting"); return;
    }

    setSaving(true); setError('');
    try {
      // Per-field currency rate helpers
      const rateFor = (curId) => {
        if (!curId) return 1;
        const c = currencies.find(c => String(c.id) === String(curId));
        return c ? Number(c.rate) : 1;
      };

      const payload = {
        name:             form.name.trim(),
        sku:              form.sku?.trim() || genSku(),
        barcode:          form.barcode.trim(),
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
      };
      if (modal === 'add') {
        payload.initial_stock = form.initial_stock !== '' ? Number(form.initial_stock) : 0;
        await api.post('/products', payload);
      } else {
        await api.put(`/products/${selected.id}`, payload);
      }
      closeModal();
      loadProducts();
    } catch (err) {
      setError(parseError(err));
    } finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!confirm("Mahsulot o'chirilsinmi? (Arxivlanadi)")) return;
    await api.delete(`/products/${id}`).catch(() => {});
    loadProducts();
  };

  /* ── category CRUD ──────────────────────────────── */
  const openAddCat = () => { setCatForm(emptyCategory); setCatError(''); setCatModal('add'); };
  const openEditCat = (c) => {
    setCatSelected(c);
    setCatForm({ name: c.name, parent_id: c.parent_id || '', sort_order: c.sort_order });
    setCatError('');
    setCatModal('edit');
  };
  const closeCatModal = () => { setCatModal(null); setCatSelected(null); setCatError(''); };

  const handleSaveCat = async (e) => {
    e.preventDefault();
    setCatSaving(true); setCatError('');
    try {
      const payload = {
        name: catForm.name,
        parent_id: catForm.parent_id ? Number(catForm.parent_id) : null,
        sort_order: Number(catForm.sort_order),
      };
      if (catModal === 'add') await api.post('/categories', payload);
      else await api.put(`/categories/${catSelected.id}`, payload);
      closeCatModal();
      loadCategories();
    } catch (err) {
      setCatError(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setCatSaving(false); }
  };

  const handleDeleteCat = async (id) => {
    if (!confirm("Kategoriya o'chirilsinmi?")) return;
    try {
      await api.delete(`/categories/${id}`);
      loadCategories();
    } catch (err) {
      alert(err.response?.data?.detail || "O'chirib bo'lmadi");
    }
  };

  /* ── bin location CRUD ──────────────────────────── */
  const openAddBl  = () => { setBlForm(emptyBinLoc); setBlError(''); setBlModal('add'); };
  const openEditBl = (b) => {
    setBlSelected(b);
    setBlForm({ code: b.code, label: b.label || '' });
    setBlError('');
    setBlModal('edit');
  };
  const closeBlModal = () => { setBlModal(null); setBlSelected(null); setBlError(''); };

  const handleSaveBl = async (e) => {
    e.preventDefault();
    setBlSaving(true); setBlError('');
    try {
      const payload = { code: blForm.code.trim(), label: blForm.label?.trim() || null };
      if (blModal === 'add') await api.post('/bin-locations', payload);
      else await api.put(`/bin-locations/${blSelected.id}`, payload);
      closeBlModal();
      loadBinLocations();
    } catch (err) {
      setBlError(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally { setBlSaving(false); }
  };

  const handleDeleteBl = async (id) => {
    if (!confirm("Joylashuv o'chirilsinmi?")) return;
    try {
      await api.delete(`/bin-locations/${id}`);
      loadBinLocations();
    } catch (err) {
      alert(err.response?.data?.detail || "O'chirib bo'lmadi");
    }
  };

  /* ── derived ─────────────────────────────────────── */
  const totalActive = products.filter(p => p.status === 'active').length;
  const lowStock    = products.filter(p => Number(p.stock_quantity) <= 0).length;
  const catName     = (id) => categories.find(c => c.id === id)?.name || '—';

  // Price currency helpers
  const priceCurSelected = currencies.find(c => String(c.id) === String(form.price_currency_id)) || null;
  const priceRate        = priceCurSelected ? Number(priceCurSelected.rate) : 1;
  const priceCurCode     = priceCurSelected?.code || "so'm";

  /* ════════════════════════════════════════════════ */
  return (
    <div className="space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Mahsulotlar</h1>
          <p className="text-slate-500 text-sm mt-0.5">Mahsulotlar va kategoriyalar boshqaruvi</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={activeTab === 'products' ? openAdd : activeTab === 'categories' ? openAddCat : openAddBl}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            {activeTab === 'products' ? "Mahsulot qo'shish" : activeTab === 'categories' ? "Kategoriya qo'shish" : "Joylashuv qo'shish"}
          </button>
          <div className="flex bg-slate-100 rounded-xl p-1 gap-1">
            {[['products', 'Mahsulotlar'], ['categories', 'Kategoriyalar'], ['binloc', 'Joylashuvlar']].map(([key, label]) => (
              <button key={key} onClick={() => setActiveTab(key)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === key ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── PRODUCTS TAB ─────────────────────────────── */}
      {activeTab === 'products' && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Jami Mahsulot', val: products.length,  icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4', bg: 'bg-indigo-100',  ic: 'text-indigo-600',  vl: 'text-slate-800' },
              { label: 'Faol',          val: totalActive,       icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',                        bg: 'bg-emerald-100', ic: 'text-emerald-600', vl: 'text-emerald-600' },
              { label: "Qoldiq yo'q",   val: lowStock,          icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z', bg: 'bg-red-100', ic: 'text-red-500', vl: 'text-red-500' },
            ].map(s => (
              <div key={s.label} className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 flex items-center gap-4">
                <div className={`w-12 h-12 rounded-xl ${s.bg} flex items-center justify-center shrink-0`}>
                  <svg className={`w-6 h-6 ${s.ic}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={s.icon} />
                  </svg>
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{s.label}</div>
                  <div className={`text-2xl font-bold mt-0.5 ${s.vl}`}>{s.val}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-52">
              <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm"
                value={search} onChange={e => setSearch(e.target.value)} placeholder="Nomi, SKU yoki barkod..." />
            </div>
            <select className="px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm text-slate-700"
              value={filterCat} onChange={e => setFilterCat(e.target.value)}>
              <option value="">Barcha kategoriyalar</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm text-slate-700"
              value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">Barcha holat</option>
              <option value="active">Faol</option>
              <option value="inactive">Nofaol</option>
              <option value="archived">Arxiv</option>
            </select>
            {warehouses.length > 0 && (
              <select className={`px-3.5 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm text-slate-700 ${
                filterWarehouse ? 'border-indigo-400 ring-1 ring-indigo-300 text-indigo-700 font-semibold' : 'border-slate-200'
              }`}
                value={filterWarehouse} onChange={e => setFilterWarehouse(e.target.value)}>
                <option value="">🏭 Barcha omborlar</option>
                {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            )}
            <button onClick={loadProducts}
              className="px-4 py-2.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-sm font-semibold rounded-xl transition-colors">
              Qidirish
            </button>
          </div>

          {/* Products Table */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            {loading ? (
              <div className="flex justify-center py-20">
                <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <>
                <table className="w-full table-fixed">
                  <colgroup>
                    <col style={{width:'120px'}} />
                    <col style={{width:'52px'}} />
                    <col style={{width:'auto'}} />
                    <col style={{width:'100px'}} />
                    <col style={{width:'60px'}} />
                    <col style={{width:'90px'}} />
                    <col style={{width:'80px'}} />
                    <col style={{width:'110px'}} />
                    <col style={{width:'70px'}} />
                    <col style={{width:'70px'}} />
                    <col style={{width:'44px'}} />
                  </colgroup>
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      {['Barkod / SKU', 'Rasm', 'Mahsulot / Brend', 'Kategoriya', 'Birlik', 'Tan narxi', 'Ulgurji', 'Chakana', 'Qoldiq', 'Holat', ''].map(h => (
                        <th key={h} className="px-2 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap overflow-hidden">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {products.map(p => {
                      const thumb = (Array.isArray(p.images) && p.images[0]) || p.image_url;
                      return (
                        <tr key={p.id} className="hover:bg-indigo-50/30 transition-colors">
                          <td className="px-2 py-3">
                            <div className="text-xs font-mono font-bold text-slate-800 truncate">{p.barcode}</div>
                            <div className="text-xs text-indigo-500 mt-0.5 truncate">{p.sku}</div>
                          </td>
                          <td className="px-1 py-3">
                            {thumb ? (
                              <img src={thumb.startsWith('/static') ? BASE_URL + thumb : thumb}
                                alt="" className="w-11 h-11 object-cover rounded-lg border border-slate-200 shadow-sm" />
                            ) : (
                              <div className="w-11 h-11 rounded-lg bg-linear-to-br from-slate-100 to-slate-200 flex items-center justify-center">
                                <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01" />
                                </svg>
                              </div>
                            )}
                          </td>
                          <td className="px-2 py-3 min-w-0">
                            <button onClick={() => openHistory(p)}
                              className="text-sm font-bold text-indigo-600 hover:text-indigo-800 hover:underline text-left w-full truncate block">
                              {p.name}
                            </button>
                            {p.brand && <div className="text-xs font-semibold text-amber-600 mt-0.5 uppercase tracking-wide truncate">{p.brand}</div>}
                            {p.bin_location && <div className="text-xs text-slate-400 mt-0.5 truncate">📍 {p.bin_location}</div>}
                          </td>
                          <td className="px-2 py-3 text-xs text-slate-600 font-medium truncate">{catName(p.category_id)}</td>
                          <td className="px-2 py-3">
                            <span className="inline-flex px-2 py-1 bg-slate-100 text-slate-700 text-xs font-semibold rounded-md">{p.unit}</span>
                          </td>
                          <td className="px-2 py-3 text-xs text-slate-500 font-medium">{fmt(p.cost_price)}</td>
                          <td className="px-2 py-3 text-xs text-slate-500">
                            {p.wholesale_price ? fmt(p.wholesale_price) : <span className="text-slate-300">—</span>}
                          </td>
                          <td className="px-2 py-3">
                            <span className="text-sm font-black text-slate-900">{fmt(p.sale_price)}</span>
                            <span className="text-xs text-slate-400 ml-0.5">so'm</span>
                          </td>
                          <td className="px-2 py-3">
                            <div className="flex flex-col gap-1">
                              {/* Jami qoldiq */}
                              <span className={`text-sm font-black ${
                                Number(p.stock_quantity) <= 0 ? 'text-red-500' :
                                Number(p.stock_quantity) <= Number(p.min_stock) ? 'text-amber-500' : 'text-emerald-600'
                              }`}>
                                {fmt(p.stock_quantity)}
                                {filterWarehouse && <span className="ml-1 text-[10px] font-normal text-slate-400">{p.unit}</span>}
                              </span>
                              {/* Per-ombor breakdown */}
                              {!filterWarehouse && p.warehouse_stocks?.length > 0 && (
                                <div className="flex flex-col gap-0.5 mt-0.5">
                                  {p.warehouse_stocks.map((ws, idx) => {
                                    const colors = [
                                      'bg-indigo-50 text-indigo-700 border-indigo-100',
                                      'bg-emerald-50 text-emerald-700 border-emerald-100',
                                      'bg-violet-50 text-violet-700 border-violet-100',
                                      'bg-amber-50 text-amber-700 border-amber-100',
                                    ];
                                    const cls = colors[idx % colors.length];
                                    const qty = Number(ws.quantity);
                                    return (
                                      <div key={ws.warehouse_id}
                                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[10px] font-semibold ${cls} ${qty <= 0 ? 'opacity-40' : ''}`}>
                                        <svg className="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                                        </svg>
                                        <span className="truncate max-w-[52px]" title={ws.warehouse_name}>{ws.warehouse_name}</span>
                                        <span className="font-black ml-0.5">{fmt(ws.quantity)}</span>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          </td>

                          <td className="px-2 py-3"><StatusBadge status={p.status} /></td>
                          <td className="px-1 py-3">
                            <RowMenu
                              product={p}
                              onEdit={() => openEdit(p)}
                              onDelete={() => handleDelete(p.id)}
                              onPrint={() => setPrintProduct(p)}
                            />
                          </td>
                        </tr>
                      );
                    })}
                    {products.length === 0 && (
                      <tr>
                        <td colSpan={11} className="px-6 py-20 text-center">
                          <div className="flex flex-col items-center gap-3 text-slate-400">
                            <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                            </svg>
                            <span className="text-sm font-medium">Mahsulotlar topilmadi</span>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
                {products.length > 0 && (
                  <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500 bg-slate-50">
                    <span>Jami <strong className="text-slate-700">{products.length}</strong> ta mahsulot</span>
                    <span>Faol: <strong className="text-emerald-600">{totalActive}</strong> &nbsp;|&nbsp; Qoldiqsiz: <strong className="text-red-500">{lowStock}</strong></span>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}

      {/* ── CATEGORIES TAB ───────────────────────────── */}
      {activeTab === 'categories' && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">Barcha kategoriyalar ({categories.length})</span>
            <button onClick={openAddCat}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-xs font-semibold rounded-lg transition-colors">
              + Kategoriya
            </button>
          </div>
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['#', 'Nomi', 'Ota kategoriya', 'Tartib', 'Yaratilgan', ''].map(h => (
                  <th key={h} className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {categories.map(c => (
                <tr key={c.id} className="hover:bg-slate-50 transition-colors group">
                  <td className="px-6 py-4 text-sm text-slate-400">#{c.id}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-indigo-400" />
                      <span className="text-sm font-medium text-slate-800">{c.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500">
                    {c.parent_id ? catName(c.parent_id) : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500">{c.sort_order}</td>
                  <td className="px-6 py-4 text-sm text-slate-400">
                    {new Date(c.created_at).toLocaleDateString('uz-UZ')}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => openEditCat(c)} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button onClick={() => handleDeleteCat(c.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {categories.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-14 text-center text-sm text-slate-400">Kategoriyalar topilmadi</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── BIN LOCATIONS TAB ─────────────────────────── */}
      {activeTab === 'binloc' && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">Ombor joylashuvlari ({binLocations.length})</span>
            <button onClick={openAddBl}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-xs font-semibold rounded-lg transition-colors">
              + Joylashuv
            </button>
          </div>
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['Kod', 'Nomi / Tavsif', ''].map(h => (
                  <th key={h} className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {binLocations.map(b => (
                <tr key={b.id} className="hover:bg-slate-50 transition-colors group">
                  <td className="px-6 py-4">
                    <span className="inline-flex px-3 py-1 bg-indigo-50 text-indigo-700 text-sm font-mono font-semibold rounded-lg">{b.code}</span>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-600">{b.label || <span className="text-slate-300">—</span>}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => openEditBl(b)} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button onClick={() => handleDeleteBl(b.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {binLocations.length === 0 && (
                <tr><td colSpan={3} className="px-6 py-14 text-center text-sm text-slate-400">Joylashuvlar topilmadi. "Joylashuv qo'shish" tugmasini bosing.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ════ PRODUCT ADD / EDIT MODAL ════ */}
      {modal && (
        <Modal
          title={modal === 'add' ? "Yangi mahsulot qo'shish" : 'Mahsulotni tahrirlash'}
          onClose={closeModal}
          size="xl"
        >
          <form onSubmit={handleSave} className="p-7">

            {/* Error banner */}
            {error && (
              <div className="flex items-start gap-2.5 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl mb-6">
                <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            {/* 2-column grid */}
            <div className="grid grid-cols-3 gap-8">

              {/* ── LEFT: main info (2/3) ── */}
              <div className="col-span-2 space-y-5">

                {/* Name */}
                <Field label="Mahsulot nomi" required>
                  <input
                    className={`${inputCls} text-base ${!form.name?.trim() && error ? errCls : ''}`}
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Masalan: Coca-Cola 0.5L"
                  />
                </Field>

                {/* Brand */}
                <Field label="Brend (ishlab chiqaruvchi)" hint="Masalan: Coca-Cola, Samsung, Nestle">
                  <input
                    className={inputCls}
                    value={form.brand}
                    onChange={e => setForm({ ...form, brand: e.target.value })}
                    placeholder="Brend nomi (ixtiyoriy)"
                  />
                </Field>

                {/* Barcode + SKU */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Barkod" required>
                    <div className="flex gap-2">
                      <select
                        className="px-2 py-3 border border-slate-200 rounded-xl text-xs font-semibold bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-700 shrink-0"
                        value={form.barcode_format}
                        onChange={e => setForm({ ...form, barcode_format: e.target.value, barcode: genBarcodeByFormat(e.target.value) })}
                      >
                        {BARCODE_FORMATS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                      </select>
                      <input
                        className={`${inputCls} flex-1 font-mono ${!form.barcode?.trim() && error ? errCls : ''}`}
                        value={form.barcode}
                        onChange={e => setForm({ ...form, barcode: e.target.value })}
                        placeholder="12345678"
                      />
                      <button type="button" onClick={() => setForm({ ...form, barcode: genBarcodeByFormat(form.barcode_format) })}
                        title="Yangi barkod yaratish"
                        className="px-3 py-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl transition-colors shrink-0">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                      </button>
                    </div>
                  </Field>
                  <Field label="SKU (Artikul)" hint="Bo'sh qolsa avtomatik yaratiladi">
                    <input className={inputCls} value={form.sku}
                      onChange={e => setForm({ ...form, sku: e.target.value })} placeholder="avtomatik" />
                  </Field>
                </div>

                {/* Category + Unit */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Kategoriya">
                    <div className="flex gap-2">
                      <select className={`${inputCls} flex-1`} value={form.category_id}
                        onChange={e => setForm({ ...form, category_id: e.target.value })}>
                        <option value="">Kategoriyasiz</option>
                        {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                      <button
                        type="button"
                        title="Yangi kategoriya qo'shish"
                        onClick={() => { openAddCat(); }}
                        className="shrink-0 w-11 h-11 flex items-center justify-center bg-indigo-50 hover:bg-indigo-100 text-indigo-600 font-bold text-xl rounded-xl border-2 border-indigo-100 hover:border-indigo-300 transition-all"
                      >+</button>
                    </div>
                  </Field>
                  <Field label="O'lchov birligi">
                    <select className={inputCls} value={form.unit}
                      onChange={e => setForm({ ...form, unit: e.target.value })}>
                      {['dona', 'kg', 'g', 'litr', 'ml', 'metr', 'sm', 'quti', 'paket', 'juft'].map(u => (
                        <option key={u} value={u}>{u}</option>
                      ))}
                    </select>
                  </Field>
                </div>

                {/* Prices — each field has its own currency dropdown */}
                <div className="space-y-3">
                  {/* Row 1: Tan + Ulgurji */}
                  <div className="grid grid-cols-2 gap-4">
                    {/* Tan narxi */}
                    <div>
                      <label className="block text-sm font-semibold text-slate-600 mb-1.5">Tan narxi</label>
                      <div className="flex rounded-xl border border-slate-200 focus-within:ring-2 focus-within:ring-indigo-500 bg-white">
                        <input type="number" min="0" step="0.01"
                          className="flex-1 min-w-0 px-3 py-3 text-base focus:outline-none bg-transparent rounded-l-xl"
                          value={form.cost_price} onChange={e => setForm({ ...form, cost_price: e.target.value })} placeholder="0" />
                        <CurrencyDropdown
                          value={form.cost_price_cur}
                          onChange={v => setForm({ ...form, cost_price_cur: v })}
                          currencies={currencies}
                        />
                      </div>
                      {form.cost_price_cur && (() => {
                        const cur = currencies.find(c => String(c.id) === form.cost_price_cur);
                        return cur && form.cost_price ? (
                          <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.cost_price) * Number(cur.rate)))} so'm</p>
                        ) : null;
                      })()}
                    </div>

                    {/* Ulgurji narxi */}
                    <div>
                      <label className="block text-sm font-semibold text-slate-600 mb-1.5">Ulgurji narxi</label>
                      <div className="flex rounded-xl border border-slate-200 focus-within:ring-2 focus-within:ring-indigo-500 bg-white">
                        <input type="number" min="0" step="0.01"
                          className="flex-1 min-w-0 px-3 py-3 text-base focus:outline-none bg-transparent rounded-l-xl"
                          value={form.wholesale_price} onChange={e => setForm({ ...form, wholesale_price: e.target.value })} placeholder="—" />
                        <CurrencyDropdown
                          value={form.wholesale_price_cur}
                          onChange={v => setForm({ ...form, wholesale_price_cur: v })}
                          currencies={currencies}
                        />
                      </div>
                      {form.wholesale_price_cur && (() => {
                        const cur = currencies.find(c => String(c.id) === form.wholesale_price_cur);
                        return cur && form.wholesale_price ? (
                          <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.wholesale_price) * Number(cur.rate)))} so'm</p>
                        ) : null;
                      })()}
                    </div>
                  </div>

                  {/* Row 2: Chakana (full width — most important price) */}
                  <div>
                    <label className="block text-sm font-semibold text-slate-600 mb-1.5">
                      Chakana narxi <span className="text-red-500">*</span>
                      <span className="ml-2 text-xs font-normal text-slate-400">Asosiy sotuv narxi</span>
                    </label>
                    <div className={`flex rounded-xl border focus-within:ring-2 focus-within:ring-indigo-500 bg-white ${
                      (form.sale_price === '' || form.sale_price === null) && error ? 'border-red-400 ring-1 ring-red-400' : 'border-slate-200'
                    }`}>
                      <input type="number" min="0" step="0.01"
                        className="flex-1 min-w-0 px-3 py-3 text-lg font-semibold focus:outline-none bg-transparent rounded-l-xl"
                        value={form.sale_price} onChange={e => setForm({ ...form, sale_price: e.target.value })} placeholder="0" />
                      <CurrencyDropdown
                        value={form.sale_price_cur}
                        onChange={v => setForm({ ...form, sale_price_cur: v })}
                        currencies={currencies}
                      />
                    </div>
                    {form.sale_price_cur && (() => {
                      const cur = currencies.find(c => String(c.id) === form.sale_price_cur);
                      return cur && form.sale_price ? (
                        <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.sale_price) * Number(cur.rate)))} so'm</p>
                      ) : null;
                    })()}
                  </div>
                </div>

                {/* UZS preview */}
                {priceCurSelected && (form.cost_price || form.sale_price) && (
                  <div className="px-4 py-3 bg-amber-50 border border-amber-100 rounded-xl text-sm text-amber-700 flex flex-wrap gap-x-5 gap-y-1">
                    <span className="font-semibold">UZS da saqlanganda:</span>
                    {form.cost_price && <span>Tan: <strong>{fmt(Math.round(Number(form.cost_price) * priceRate))}</strong></span>}
                    {form.wholesale_price && <span>Ulgurji: <strong>{fmt(Math.round(Number(form.wholesale_price) * priceRate))}</strong></span>}
                    {form.sale_price && <span>Chakana: <strong>{fmt(Math.round(Number(form.sale_price) * priceRate))}</strong></span>}
                  </div>
                )}

                {/* Margin hint */}
                {form.cost_price && form.sale_price && Number(form.sale_price) > 0 && (
                  <div className="px-4 py-3 bg-indigo-50 rounded-xl text-sm text-indigo-700">
                    Margin: <strong>{(((Number(form.sale_price) - Number(form.cost_price)) / Number(form.sale_price)) * 100).toFixed(1)}%</strong>
                    &nbsp;|&nbsp; Foyda: <strong>{fmt(Number(form.sale_price) - Number(form.cost_price))} {priceCurCode}</strong>
                  </div>
                )}

                {/* Stock */}
                <div className="grid grid-cols-3 gap-4">
                  {modal === 'add' && (
                    <Field label="Boshlang'ich qoldiq">
                      <input type="number" min="0" step="0.01" className={`${inputCls} text-base`}
                        value={form.initial_stock} onChange={e => setForm({ ...form, initial_stock: e.target.value })} placeholder="0" />
                    </Field>
                  )}
                  <Field label="Min. qoldiq">
                    <input type="number" min="0" className={`${inputCls} text-base`}
                      value={form.min_stock} onChange={e => setForm({ ...form, min_stock: e.target.value })} />
                  </Field>
                  <Field label="Maks. qoldiq">
                    <input type="number" min="0" className={`${inputCls} text-base`}
                      value={form.max_stock} onChange={e => setForm({ ...form, max_stock: e.target.value })} placeholder="Cheksiz" />
                  </Field>
                  {modal !== 'add' && <div />}
                </div>

              </div>

              {/* ── RIGHT: details (1/3) ── */}
              <div className="col-span-1 space-y-5">

                {/* Images */}
                <Field label="Mahsulot rasmlari (JPG/PNG)">
                  <ImageUploadZone
                    images={form.images}
                    onAdd={handleImageFile}
                    onRemove={removeImage}
                    uploading={imgUploading}
                  />
                </Field>

                {/* Bin location */}
                <Field label="Ombor joylashuvi" hint="Mahsulot saqlanadigan joyni tanlang">
                  <div className="flex gap-2">
                    <select className={`${inputCls} flex-1`} value={form.bin_location}
                      onChange={e => setForm({ ...form, bin_location: e.target.value })}>
                      <option value="">— Tanlang —</option>
                      {binLocations.map(b => (
                        <option key={b.id} value={b.code}>{b.code}{b.label ? ` — ${b.label}` : ''}</option>
                      ))}
                    </select>
                    <button type="button" onClick={openAddBl}
                      title="Yangi joylashuv qo'shish"
                      className="px-3 py-3 bg-slate-100 hover:bg-indigo-100 text-slate-600 hover:text-indigo-600 rounded-xl transition-colors shrink-0">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                  </div>
                </Field>

                {/* Weight + Dimensions */}
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Vazn (kg)">
                    <input type="number" min="0" step="0.001" className={inputCls}
                      value={form.weight} onChange={e => setForm({ ...form, weight: e.target.value })} placeholder="0.000" />
                  </Field>
                  <Field label="O'lchamlar (sm)">
                    <input className={inputCls} value={form.dimensions}
                      onChange={e => setForm({ ...form, dimensions: e.target.value })} placeholder="UxBxH" />
                  </Field>
                </div>

                {/* Status */}
                <Field label="Holat">
                  <select className={inputCls} value={form.status}
                    onChange={e => setForm({ ...form, status: e.target.value })}>
                    <option value="active">Faol</option>
                    <option value="inactive">Nofaol</option>
                    <option value="archived">Arxiv</option>
                  </select>
                </Field>

              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-8 pt-6 border-t border-slate-100">
              <button type="button" onClick={closeModal}
                className="flex-1 py-3 border border-slate-200 text-slate-600 font-semibold text-base rounded-xl hover:bg-slate-50 transition-colors">
                Bekor qilish
              </button>
              <button type="submit" disabled={saving}
                className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-bold text-base rounded-xl transition-colors">
                {saving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ════ CATEGORY MODAL ════ */}
      {catModal && (
        <Modal title={catModal === 'add' ? 'Yangi kategoriya' : 'Kategoriyani tahrirlash'} onClose={closeCatModal} size="sm" z="z-60">
          <form onSubmit={handleSaveCat} className="p-6 space-y-4">
            <Field label="Kategoriya nomi" required>
              <input required className={inputCls} value={catForm.name}
                onChange={e => setCatForm({ ...catForm, name: e.target.value })} placeholder="Masalan: Ichimliklar" />
            </Field>
            <Field label="Ota kategoriya (ixtiyoriy)">
              <select className={inputCls} value={catForm.parent_id}
                onChange={e => setCatForm({ ...catForm, parent_id: e.target.value })}>
                <option value="">Yo'q (asosiy kategoriya)</option>
                {categories.filter(c => !catSelected || c.id !== catSelected.id).map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Tartib raqami">
              <input type="number" min="0" className={inputCls} value={catForm.sort_order}
                onChange={e => setCatForm({ ...catForm, sort_order: e.target.value })} />
            </Field>
            {catError && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{catError}</div>}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={closeCatModal}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">Bekor</button>
              <button type="submit" disabled={catSaving}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                {catSaving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ════ BIN LOCATION MODAL ════ */}
      {blModal && (
        <Modal title={blModal === 'add' ? "Yangi joylashuv qo'shish" : 'Joylashuvni tahrirlash'} onClose={closeBlModal} size="sm" z="z-60">
          <form onSubmit={handleSaveBl} className="p-6 space-y-4">
            <Field label="Joylashuv kodi" required hint="Masalan: A-01, B-12, Shkaf-3">
              <input required className={inputCls} value={blForm.code}
                onChange={e => setBlForm({ ...blForm, code: e.target.value.toUpperCase() })}
                placeholder="A-01" />
            </Field>
            <Field label="Tavsif (ixtiyoriy)">
              <input className={inputCls} value={blForm.label}
                onChange={e => setBlForm({ ...blForm, label: e.target.value })}
                placeholder="Masalan: 1-qator, 1-javon" />
            </Field>
            {blError && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{blError}</div>}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={closeBlModal}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">Bekor</button>
              <button type="submit" disabled={blSaving}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                {blSaving ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ════ HISTORY MODAL ════ */}
      {histProduct && (
        <Modal title={`Tarix: ${histProduct.name}`} onClose={closeHistory} size="lg">
          <div className="p-6">
            <div className="flex items-center gap-4 p-4 bg-slate-50 rounded-xl mb-5">
              {((Array.isArray(histProduct.images) && histProduct.images[0]) || histProduct.image_url) ? (
                <img
                  src={(histProduct.images?.[0] || histProduct.image_url).startsWith('/static')
                    ? BASE_URL + (histProduct.images?.[0] || histProduct.image_url)
                    : (histProduct.images?.[0] || histProduct.image_url)}
                  alt="" className="w-14 h-14 rounded-xl object-cover shrink-0 border border-slate-200" />
              ) : (
                <div className="w-14 h-14 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
                  <svg className="w-7 h-7 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 truncate">{histProduct.name}</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  Barkod: <span className="font-mono">{histProduct.barcode}</span>
                  &nbsp;·&nbsp; SKU: {histProduct.sku}
                  {histProduct.bin_location && <>&nbsp;·&nbsp; Joylashuv: <span className="font-medium">{histProduct.bin_location}</span></>}
                  &nbsp;·&nbsp; Qoldiq: <span className="font-bold text-indigo-600">{fmt(histProduct.stock_quantity)} {histProduct.unit}</span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-xs text-slate-400">Chakana</div>
                <div className="text-lg font-bold text-slate-800">{fmt(histProduct.sale_price)} so'm</div>
              </div>
            </div>

            {histLoading ? (
              <div className="flex justify-center py-10">
                <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : history.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-sm">Harakatlar tarixi topilmadi</div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Qoldiq harakati — so'nggi {history.length} ta operatsiya
                  </div>
                  <div className="text-xs text-slate-400 font-semibold">
                    Joriy qoldiq: <span className="text-indigo-600 font-bold">{fmt(histProduct.stock_quantity)} {histProduct.unit}</span>
                  </div>
                </div>
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        {['Sana va Vaqt','Operatsiya','Avvalgi qoldiq','O\'zgarish','Yangi qoldiq','Sabab / Ma\'lumot'].map(h => (
                          <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {history.map((m, i) => {
                        const meta = movTypeMeta[m.type] || { label: m.type, cls: 'bg-slate-100 text-slate-600' };
                        const delta = Number(m.qty_after) - Number(m.qty_before);
                        const isPos = delta >= 0;

                        // Human-readable reference label
                        const refLabels = {
                          sale: 'Sotuv',
                          sale_refund: 'Sotuv bekor',
                          purchase: 'Kirim',
                          manual_receive: 'Qo\'lda qabul',
                          transfer: 'Ombor ko\'chirish',
                          inventory_count: 'Inventarizatsiya',
                          adjustment: 'Tuzatish',
                          revision: 'Reviziya',
                        };
                        const refLabel = refLabels[m.reference_type] || m.reference_type || '';

                        return (
                          <tr key={m.id || i} className={`transition-colors ${isPos ? 'hover:bg-emerald-50/30' : 'hover:bg-red-50/30'}`}>
                            <td className="px-3 py-2.5 whitespace-nowrap">
                              <div className="text-xs font-semibold text-slate-700">{new Date(m.created_at).toLocaleDateString('uz-UZ')}</div>
                              <div className="text-xs text-slate-400">{new Date(m.created_at).toLocaleTimeString('uz-UZ', {hour:'2-digit',minute:'2-digit',second:'2-digit'})}</div>
                            </td>
                            <td className="px-3 py-2.5">
                              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${meta.cls}`}>{meta.label}</span>
                            </td>
                            <td className="px-3 py-2.5 font-mono text-sm text-slate-600 text-right whitespace-nowrap">
                              {Number(m.qty_before)} {histProduct.unit}
                            </td>
                            <td className="px-3 py-2.5 text-right whitespace-nowrap">
                              <span className={`text-sm font-bold font-mono ${isPos ? 'text-emerald-600' : 'text-red-500'}`}>
                                {isPos ? '+' : ''}{delta} {histProduct.unit}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 font-mono text-sm font-bold text-slate-800 text-right whitespace-nowrap">
                              {Number(m.qty_after)} {histProduct.unit}
                            </td>
                            <td className="px-3 py-2.5 text-xs text-slate-500 max-w-xs">
                              {refLabel && <span className="font-medium text-slate-600 mr-1">[{refLabel}]</span>}
                              {m.reason || '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
      {/* BARCODE PRINT MODAL */}
      {printProduct && (
        <BarcodePrintModal product={printProduct} onClose={() => setPrintProduct(null)} />
      )}
    </div>
  );
}
