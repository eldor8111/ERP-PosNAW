import { useRef, useState, useEffect, useCallback } from 'react';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import api from '../../api/axios';
import BarcodePrintModal from '../../components/BarcodeTemplates';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

const BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8010/api').replace('/api', '');

/* ─── helpers ─────────────────────────────────────── */
// Narx inputi uchun: "60000" → "60 000", foydalanuvchi kiritayotganda formatlash
const fmtPrice = (v) => {
  if (v === '' || v === null || v === undefined) return '';
  const digits = String(v).replace(/\s/g, '');
  if (!digits || isNaN(Number(digits))) return String(v).replace(/\s/g, '');
  return Number(digits).toLocaleString('ru-RU');
};
const parsePrice = (v) => String(v).replace(/\s/g, '').replace(/[^0-9.]/g, '');

const fmt = (v) => {
  if (v === null || v === undefined || v === '') return '0';
  const n = Number(v);
  if (isNaN(n) || n === 0) return '0';
  return n.toLocaleString('ru-RU');
};
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
  extra_barcodes: [],
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

/* ─── Bulk add empty row factory ──────────────────── */
const emptyBulkRow = () => ({
  _key: Math.random().toString(36).slice(2),
  name: '',
  cost_price: '',
  wholesale_price: '',
  sale_price: '',
  barcodes: [genBarcodeByFormat('ean8')],
  unit: 'dona',
  barcode_status: null,   // null | 'checking' | 'exists' | 'new'
  barcode_product: null,
  barcode_scanned: false, // skaner orqali barkod biriktirilganmi
  category_id: '',
  initial_stock: '',
  status: 'active',
});

/* ─── RowMenu (3 dots) ─────────────────────────────────── */
function RowMenu({ onEdit, onDelete, onPrint }) {
  const { t } = useLang();
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
        <div className="absolute right-0 top-[calc(100%+4px)] bg-white border border-slate-200 rounded-xl shadow-xl z-[999] py-1.5 min-w-[190px]">
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
  const { t } = useLang();
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
  const { t } = useLang();
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
  const { t } = useLang();
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
  const { t } = useLang();
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
  const { t } = useLang();
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
  const { t } = useLang();
  const [printProduct, setPrintProduct] = useState(null);
  const [activeTab, setActiveTab] = useState('products');

  /* products state */
  const [products, setProducts]       = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [limit, setLimit]             = useState(() => Number(localStorage.getItem('products_limit') || 50));
  const [page, setPage]               = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [totalActive, setTotalActive]   = useState(0);
  const [outOfStock, setOutOfStock]     = useState(0);
  const [deleteProgress, setDeleteProgress] = useState(null);
  const [categories, setCategories]   = useState([]);
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
    api.get('/categories/all').then(r => setCategories(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const loadBinLocations = useCallback(() => {
    api.get('/bin-locations').then(r => setBinLocations(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const loadProducts = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (search)          params.append('search', search);
    if (filterCat)       params.append('category_id', filterCat);
    if (filterStatus)    params.append('status', filterStatus);
    if (filterWarehouse) params.append('warehouse_id', filterWarehouse);
    params.append('limit', String(limit));
    params.append('skip', String((page - 1) * limit));
    api.get('/products/paginated?' + params.toString())
      .then(r => {
        setProducts(r.data.items);
        setTotalRecords(r.data.total);
        setTotalActive(r.data.total_active || 0);
        setOutOfStock(r.data.out_of_stock || 0);
        setSelectedIds([]);
      })
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
      .finally(() => setLoading(false));
  }, [search, filterCat, filterStatus, filterWarehouse, limit, page]);

  useEffect(() => { setPage(1); }, [search, filterCat, filterStatus, filterWarehouse, limit]);

  useEffect(() => {
    loadCategories();
    loadBinLocations();
    api.get('/currencies/').then(r => setCurrencies(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    api.get('/inventory/warehouses').then(r => setWarehouses(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeTab === 'products')   loadProducts();
    if (activeTab === 'categories') { loadCategories(); loadBinLocations(); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, page, filterCat, filterStatus, filterWarehouse, limit]);

  useEffect(() => {
    if (activeTab !== 'products') return;
    const t = setTimeout(() => loadProducts(), 400);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      extra_barcodes: Array.isArray(p.extra_barcodes) ? p.extra_barcodes : [],
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
    if (!confirm(t('product.deleteConfirm'))) return;
    await api.delete(`/products/${id}`).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
    loadProducts();
  };

  const handleSelectAll = async (e) => {
    if (e.target.checked) {
      if (!confirm(`Barcha sahifalardagi (jami ${totalRecords} ta) mahsulotlarni tanlamoqchimisiz?`)) return;
      try {
        const params = new URLSearchParams();
        if (search)          params.append('search', search);
        if (filterCat)       params.append('category_id', filterCat);
        if (filterStatus)    params.append('status', filterStatus);
        if (filterWarehouse) params.append('warehouse_id', filterWarehouse);
        const r = await api.get('/products/ids?' + params.toString());
        setSelectedIds(r.data);
      } catch {
        alert("Server bilan ishlashda xatolik yuz berdi");
      }
    } else {
      setSelectedIds([]);
    }
  };

  const [deletePercent, setDeletePercent] = useState(0);
  const [bulkDeleteModal, setBulkDeleteModal] = useState(null); // { code, entered }

  const handleBulkDelete = () => {
    if (!selectedIds.length) return;
    const code = Math.floor(1000 + Math.random() * 9000);
    setBulkDeleteModal({ code, entered: '' });
  };

  const confirmBulkDelete = async () => {
    if (!bulkDeleteModal || bulkDeleteModal.entered !== String(bulkDeleteModal.code)) return;
    setBulkDeleteModal(null);
    try {
      const CHUNK_SIZE = 200;
      const total = selectedIds.length;
      let deleted = 0;
      setDeletePercent(0);
      setDeleteProgress('deleting');

      for (let i = 0; i < total; i += CHUNK_SIZE) {
        const chunk = selectedIds.slice(i, i + CHUNK_SIZE);
        await api.post('/products/bulk-delete', { product_ids: chunk }, { timeout: 120000 });
        deleted += chunk.length;
        setDeletePercent(Math.round((deleted / total) * 100));
        setDeleteProgress('deleting');
        await new Promise(r => setTimeout(r, 30));
      }

      setDeleteProgress(null);
      setDeletePercent(0);
      setSelectedIds([]);
      loadProducts();
    } catch (err) {
      setDeleteProgress(null);
      setDeletePercent(0);
      const errDetail = err.response?.data?.detail;
      const msg = typeof errDetail === 'string' ? errDetail :
                  (Array.isArray(errDetail) ? errDetail.map(e => e.msg).join(', ') : err.message);
      alert(`O'chirib bo'lmadi: ${msg || "Xatolik"}`);
    }
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
    if (!confirm(t('confirm.delete'))) return;
    try {
      await api.delete(`/categories/${id}`);
      loadCategories();
    } catch (err) {
      alert(err.response?.data?.detail || t('common.error'));
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
    if (!confirm(t('confirm.delete'))) return;
    try {
      await api.delete(`/bin-locations/${id}`);
      loadBinLocations();
    } catch (err) {
      alert(err.response?.data?.detail || t('common.error'));
    }
  };

  /* ── derived ─────────────────────────────────────── */
  const catName     = (id) => categories.find(c => c.id === id)?.name || '—';

  // Price currency helpers
  const priceCurSelected = currencies.find(c => String(c.id) === String(form.price_currency_id)) || null;
  const priceRate        = priceCurSelected ? Number(priceCurSelected.rate) : 1;
  const priceCurCode     = priceCurSelected?.code || "so'm";

  /* ────────────────────── Excel Import (Advanced) ─────────────────────── */
  const IMPORT_FIELDS = [
    { key: '',                label: '— Tanlang —' },
    { key: 'Nomi',           label: 'Mahsulot nomi *' },
    { key: 'Barkod',         label: 'Barkod (Shtrix kod)' },
    { key: 'SKU',            label: 'Artikul (SKU)' },
    { key: "O'lchov",        label: "O'lchov birligi" },
    { key: 'Tan narxi',      label: 'Tan narxi' },
    { key: 'Chakana narxi',  label: 'Chakana narxi' },
    { key: 'Ulgurji narxi',  label: 'Ulgurji narxi' },
    { key: 'Qoldiq',         label: 'Qoldiq' },
    { key: 'Min. qoldiq',    label: 'Min. qoldiq' },
    { key: 'Holat',          label: 'Holat' },
    { key: 'Brand',          label: 'Brand' },
    { key: 'Kategoriya',     label: 'Kategoriya nomi' },
    { key: '__SKIP__',       label: '— O\'tkazib yuborish —' },
  ];

  const [importOpen,     setImportOpen]     = useState(false);
  const [importRows,     setImportRows]     = useState([]);
  const [importFile,     setImportFile]     = useState(null);
  const [importLoading,  setImportLoading]  = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [importResult,   setImportResult]   = useState(null);
  const [importError,    setImportError]    = useState('');
  const [colMap,         setColMap]         = useState({});   // { excelColName: fieldKey }
  const [skipRows,       setSkipRows]       = useState(1);   // how many header rows to skip (already parsed, so 0 = no skip)
  const [searchBySku,    setSearchBySku]    = useState(false);
  const [allowUpdate,    setAllowUpdate]    = useState(false);
  const [importPage,     setImportPage]     = useState(1);
  const IMPORT_LIMIT = 10;

  const excelCols = importRows.length > 0 ? Object.keys(importRows[0]) : [];

  // Auto-map columns by matching excel header to known field label/key
  const autoMap = (rows) => {
    if (!rows.length) return;
    const cols = Object.keys(rows[0]);
    const map = {};
    cols.forEach(col => {
      const lc = col.trim().toLowerCase();
      const found = IMPORT_FIELDS.find(f => f.label.toLowerCase().includes(lc) || f.key.toLowerCase() === lc || lc.includes(f.key.toLowerCase() || '__NEVER__'));
      map[col] = found?.key && found.key !== '__SKIP__' ? found.key : '';
    });
    setColMap(map);
  };

  const parseExcel = (file) => {
    setImportFile(file); setImportResult(null); setImportError(''); setImportPage(1);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { defval: '', raw: false });
        setImportRows(rows);
        autoMap(rows);
      } catch {
        setImportError('Fayl o\'qishda xatolik. Iltimos .xlsx formatdagi faylni tanlang.');
      }
    };
    reader.readAsArrayBuffer(file);
  };

  // Build payload from colMap
  const buildPayload = () => {
    const actualRows = skipRows > 0 ? importRows.slice(skipRows - 1) : importRows;
    return actualRows.map((row, idx) => {
      const obj = {};
      Object.entries(colMap).forEach(([excelCol, fieldKey]) => {
        if (fieldKey && fieldKey !== '__SKIP__') {
          obj[fieldKey] = row[excelCol];
        }
      });
      obj.__row_index = (skipRows > 0 ? skipRows - 1 : 0) + idx + 2;
      return obj;
    }).filter(r => r['Nomi'] || r['Barkod'] || r['SKU']);
  };

  // Pre-check stats: how many rows match existing products
  const foundCount = (() => {
    if (!importRows.length || !products.length) return 0;
    const payload = buildPayload();
    return payload.filter(r => {
      const name = (r['Nomi'] || '').toLowerCase();
      const barcode = String(r['Barkod'] || '');
      const sku = String(r['SKU'] || '');
      return products.some(p =>
        (name && p.name?.toLowerCase() === name) ||
        (barcode && p.barcode === barcode) ||
        (searchBySku && sku && p.sku === sku)
      );
    }).length;
  })();

  const notFoundCount = buildPayload().length - foundCount;

  const downloadTemplate = () => {
    const ws = XLSX.utils.json_to_sheet([{
      'Nomi': 'Coca-Cola 0.5L', 'Barkod': '12345678', 'SKU': '',
      "O'lchov": 'dona', 'Tan narxi': 5000, 'Chakana narxi': 8000,
      'Ulgurji narxi': 7000, 'Qoldiq': 100, 'Min. qoldiq': 10, 'Holat': 'Faol'
    }]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Mahsulotlar');
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), 'mahsulot_shablon.xlsx');
  };

  const handleImport = async () => {
    const payload = buildPayload();
    if (!payload.length) return;
    setImportLoading(true); setImportResult(null); setImportError('');
    try {
      let totC = 0, totU = 0, totS = 0;
      let errs = [];
      const CHUNK_SIZE = 500;

      for (let i = 0; i < payload.length; i += CHUNK_SIZE) {
        const chunk = payload.slice(i, i + CHUNK_SIZE);
        const { data } = await api.post(`/products/bulk-import?allow_update=${allowUpdate}&search_by_sku=${searchBySku}`, chunk);
        totC += data.created || 0;
        totU += data.updated || 0;
        totS += data.skipped || 0;
        // Xatolarni max 300 ta saqlash (xotira muammosini oldini olish)
        if (data.errors?.length && errs.length < 300) {
          errs = [...errs, ...data.errors].slice(0, 300);
        }
        setImportProgress(Math.round(((i + chunk.length) / payload.length) * 100));
      }

      setImportResult({ created: totC, updated: totU, skipped: totS, errors: errs });
      if (totC > 0 || totU > 0) loadProducts();
    } catch (err) {
      setImportError(err.response?.data?.detail || 'Server xatosi');
    } finally { setImportLoading(false); }
  };

  const resetImport = () => {
    setImportOpen(false); setImportRows([]); setImportFile(null);
    setImportResult(null); setImportError(''); setColMap({}); setImportPage(1);
    setSkipRows(1); setSearchBySku(false); setAllowUpdate(false); setImportProgress(0);
  };
  const openImport = () => { resetImport(); setImportOpen(true); };

  /* ════ BULK ADD (donalab qo'shish) ════ */
  const [bulkAddOpen, setBulkAddOpen] = useState(false);
  const [bulkRows, setBulkRows] = useState([emptyBulkRow()]);
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState('');

  const openBulkAdd = () => {
    setBulkRows([emptyBulkRow()]);
    setBulkResult(null);
    setBulkError('');
    setBulkAddOpen(true);
  };

  // Bulk add: global scanner — tezlik asosida aniqlash (< 60ms = scanner, >= 60ms = qo'l)
  const bulkScanBufferRef = useRef('');
  const bulkScanLastKeyRef = useRef(0);
  // checkBulkBarcode va setBulkRows ni ref orqali ushlash (closure muammosini hal qiladi)
  const checkBulkBarcodeRef = useRef(null);
  const setBulkRowsRef = useRef(null);

  const updateBulkRow = (key, field, value) =>
    setBulkRows(rows => rows.map(r => r._key === key ? { ...r, [field]: value } : r));

  const checkBulkBarcode = async (key, barcode) => {
    if (!barcode?.trim()) return;
    setBulkRows(rows => rows.map(r => r._key === key ? { ...r, barcode_status: 'checking', barcode_product: null } : r));
    try {
      const res = await api.get(`/products/barcode/${barcode.trim()}`);
      setBulkRows(rows => rows.map(r =>
        r._key === key ? { ...r, barcode_status: 'exists', barcode_product: res.data } : r
      ));
    } catch {
      setBulkRows(rows => rows.map(r =>
        r._key === key ? { ...r, barcode_status: 'new', barcode_product: null } : r
      ));
    }
  };

  // Ref larni har render da yangilab turish (stale closure muammosidan qochish)
  checkBulkBarcodeRef.current = checkBulkBarcode;
  setBulkRowsRef.current = setBulkRows;

  // Global scanner listener
  useEffect(() => {
    if (!bulkAddOpen) { bulkScanBufferRef.current = ''; return; }
    const handleKey = (e) => {
      const now = Date.now();
      const gap = now - bulkScanLastKeyRef.current;
      bulkScanLastKeyRef.current = now;
      // Barcode inputi focused bo'lsa — o'sha input o'zi hal qiladi
      const ae = document.activeElement;
      if (ae && ae.dataset && ae.dataset.bulkBarcodeInput === 'true') return;
      if (e.key === 'Enter') {
        const code = bulkScanBufferRef.current.trim();
        bulkScanBufferRef.current = '';
        if (code.length >= 4) {
          e.preventDefault();
          let targetKey = null;
          setBulkRowsRef.current(prev => {
            const last = prev[prev.length - 1];
            if (last && !last.name.trim() && !last.barcode_scanned) {
              targetKey = last._key;
              return prev.map((r, i) => i === prev.length - 1
                ? { ...r, barcodes: [code], barcode_status: null, barcode_product: null, barcode_scanned: true }
                : r
              );
            } else {
              const newRow = emptyBulkRow();
              newRow.barcodes = [code];
              newRow.barcode_scanned = true;
              targetKey = newRow._key;
              return [...prev, newRow];
            }
          });
          setTimeout(() => { if (targetKey) checkBulkBarcodeRef.current(targetKey, code); }, 0);
        }
      } else if (e.key.length === 1) {
        if (gap < 60) {
          bulkScanBufferRef.current += e.key;
        } else {
          bulkScanBufferRef.current = e.key;
        }
      }
    };
    window.addEventListener('keydown', handleKey, true);
    return () => window.removeEventListener('keydown', handleKey, true);
  }, [bulkAddOpen]);

  const addBulkBarcode = (key) =>
    setBulkRows(rows => rows.map(r =>
      r._key === key ? { ...r, barcodes: [...r.barcodes, genBarcodeByFormat('ean8')] } : r
    ));

  const removeBulkBarcode = (key, idx) =>
    setBulkRows(rows => rows.map(r =>
      r._key === key ? { ...r, barcodes: r.barcodes.filter((_, i) => i !== idx) } : r
    ));

  const updateBulkBarcode = (key, idx, val) =>
    setBulkRows(rows => rows.map(r =>
      r._key === key ? { ...r, barcodes: r.barcodes.map((b, i) => i === idx ? val : b) } : r
    ));

  const removeBulkRow = (key) =>
    setBulkRows(rows => rows.length > 1 ? rows.filter(r => r._key !== key) : rows);

  const handleBulkAddSave = async () => {
    const validRows = bulkRows.filter(r => r.name.trim() && String(r.sale_price).trim());
    if (!validRows.length) { setBulkError("Kamida bitta mahsulot nomi va chakana narxi kiritilishi kerak"); return; }
    setBulkSaving(true); setBulkError(''); setBulkResult(null);
    let created = 0, errors = [];
    for (const row of validRows) {
      try {
        const [primary, ...extras] = row.barcodes.filter(b => b.trim());
        await api.post('/products', {
          name:            row.name.trim(),
          barcode:         primary || genBarcodeByFormat('ean8'),
          extra_barcodes:  extras,
          cost_price:      Number(row.cost_price) || 0,
          wholesale_price: row.wholesale_price !== '' ? Number(row.wholesale_price) : null,
          sale_price:      Number(row.sale_price) || 0,
          unit:            row.unit || 'dona',
          category_id:     row.category_id ? Number(row.category_id) : null,
          initial_stock:   Number(row.initial_stock) || 0,
          status:          row.status || 'active',
        });
        created++;
      } catch (err) {
        const detail = err.response?.data?.detail;
        errors.push({ name: row.name, error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
      }
    }
    setBulkResult({ created, errors });
    setBulkSaving(false);
    if (created > 0) loadProducts();
  };


  /* ════════════════════════════════════════════════ */
  return (
    <div className="space-y-6">

      {/* Bulk Delete Confirmation Modal */}
      {bulkDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 border border-red-100">
            <div className="w-12 h-12 bg-red-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </div>
            <h3 className="text-slate-800 font-bold text-lg text-center mb-1">Mahsulotlarni o'chirish</h3>
            <p className="text-slate-500 text-sm text-center mb-4">
              <span className="font-bold text-red-600">{selectedIds.length} ta</span> mahsulot arxivlanadi. Tasdiqlash uchun
              quyidagi kodni kiriting:
            </p>
            <div className="bg-slate-50 border border-slate-200 rounded-xl py-3 text-center mb-4">
              <span className="text-3xl font-black tracking-[0.3em] text-slate-800">{bulkDeleteModal.code}</span>
            </div>
            <input
              type="text"
              maxLength={4}
              placeholder="Kodni kiriting..."
              value={bulkDeleteModal.entered}
              onChange={e => setBulkDeleteModal(m => ({ ...m, entered: e.target.value }))}
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-center text-lg font-bold tracking-widest
                focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent mb-4"
              autoFocus
              onKeyDown={e => e.key === 'Enter' && confirmBulkDelete()}
            />
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setBulkDeleteModal(null)}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 text-sm font-semibold transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={confirmBulkDelete}
                disabled={bulkDeleteModal.entered !== String(bulkDeleteModal.code)}
                className="flex-1 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
              >
                {t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t('product.title')}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{t('product.title')} {t('common.list').toLowerCase()}</p>
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'products' && (
            <>
              <button
                onClick={downloadTemplate}
                title="Shablonni yuklab oling va to'ldiring"
                className="inline-flex items-center gap-2 px-4 py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-xl transition-colors border border-slate-200"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                {t('common.download')}
              </button>
              <button
                onClick={openBulkAdd}
                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl transition-colors shadow-sm"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
                Ko'p mahsulot qo'shish
              </button>
              <button
                onClick={openImport}
                className="inline-flex items-center gap-2 px-4 py-2 bg-violet-50 hover:bg-violet-100 text-violet-700 text-sm font-semibold rounded-xl transition-colors border border-violet-200"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                {t('product.import')}
              </button>
              <button
                onClick={() => {
                  // ── Professional multi‑header Excel export ──────────────
                  const wb = XLSX.utils.book_new();
                  const ws = {};

                  // Helper to set a cell value + style
                  const cell = (addr, v, s) => { ws[addr] = { v, t: typeof v === 'number' ? 'n' : 's', s }; };

                  // Styles
                  const hdr1 = { font: { bold: true, color: { rgb: 'FFFFFF' }, sz: 10 }, fill: { fgColor: { rgb: '4F46E5' } }, alignment: { horizontal: 'center', vertical: 'center', wrapText: true }, border: { bottom: { style: 'thin', color: { rgb: 'E2E8F0' } } } };
                  const hdr2 = { font: { bold: true, sz: 9 }, fill: { fgColor: { rgb: 'EEF2FF' } }, alignment: { horizontal: 'center', vertical: 'center' }, border: { bottom: { style: 'thin', color: { rgb: 'C7D2FE' } } } };
                  const numCell = { alignment: { horizontal: 'right' } };
                  const ctrCell = { alignment: { horizontal: 'center' } };

                  // Row 1 — group headers (some span 3 cols, some span 1)
                  // Columns: A=№, B=Товар нomi, C=Qoldiq склад, D=Jami, E-G=Chakana(Narx/Val/Sum), H-J=Ulgurji(Narx/Val/Sum), K-M=Tan narxi(Narx/Val/Sum), N=Birligi, O=Kategoriya, P=Barkod, Q=Artikul, R=Brand, S=Min. qoldiq, T=Holat, U=ID
                  cell('A1', '№', hdr1); cell('B1', 'Mahsulot nomi', hdr1);
                  cell('C1', 'Qoldiq (sklad)', hdr1); cell('D1', 'Jami qoldiq', hdr1);
                  cell('E1', 'Chakana narxi', hdr1); cell('F1', '', hdr1); cell('G1', '', hdr1);
                  cell('H1', 'Ulgurji narxi', hdr1); cell('I1', '', hdr1); cell('J1', '', hdr1);
                  cell('K1', 'Tan narxi', hdr1); cell('L1', '', hdr1); cell('M1', '', hdr1);
                  cell('N1', 'Birligi', hdr1); cell('O1', 'Kategoriya', hdr1);
                  cell('P1', 'Barkod', hdr1); cell('Q1', 'Artikul', hdr1);
                  cell('R1', 'Brand', hdr1); cell('S1', 'Min. qoldiq', hdr1);
                  cell('T1', 'Holat', hdr1); cell('U1', 'ID', hdr1);

                  // Row 2 — sub-headers
                  cell('A2', '№', hdr2); cell('B2', 'Nomi', hdr2);
                  cell('C2', 'Sklad', hdr2); cell('D2', 'Jami', hdr2);
                  cell('E2', 'Narx', hdr2); cell('F2', 'Valyuta', hdr2); cell('G2', 'Summa', hdr2);
                  cell('H2', 'Narx', hdr2); cell('I2', 'Valyuta', hdr2); cell('J2', 'Summa', hdr2);
                  cell('K2', 'Narx', hdr2); cell('L2', 'Valyuta', hdr2); cell('M2', 'Summa', hdr2);
                  cell('N2', 'Birlik', hdr2); cell('O2', 'Kategoriya', hdr2);
                  cell('P2', 'Barkod', hdr2); cell('Q2', 'SKU', hdr2);
                  cell('R2', 'Brand', hdr2); cell('S2', 'Min.', hdr2);
                  cell('T2', 'Holat', hdr2); cell('U2', 'ID', hdr2);

                  // Merges for row 1 group headers (E-G, H-J, K-M span 3 columns)
                  ws['!merges'] = [
                    { s: { r: 0, c: 4 }, e: { r: 0, c: 6 } },   // E1:G1 Chakana
                    { s: { r: 0, c: 7 }, e: { r: 0, c: 9 } },   // H1:J1 Ulgurji
                    { s: { r: 0, c: 10 }, e: { r: 0, c: 12 } }, // K1:M1 Tan narxi
                  ];

                  // Data rows starting at row 3
                  const cols = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U'];
                  products.forEach((p, i) => {
                    const r = i + 3;
                    const qty = Number(p.stock_quantity || 0);
                    const saleP = Number(p.sale_price || 0);
                    const whoP = Number(p.wholesale_price || 0);
                    const costP = Number(p.cost_price || 0);
                    const status = p.status === 'active' ? 'Faol' : p.status === 'inactive' ? 'Nofaol' : 'Arxiv';
                    const rowBg = i % 2 === 0 ? { fill: { fgColor: { rgb: 'FAFBFF' } } } : {};
                    const vals = [
                      i + 1, p.name,
                      qty, qty,
                      saleP, "UZS", saleP * qty,
                      whoP, "UZS", whoP * qty,
                      costP, "UZS", costP * qty,
                      p.unit, catName(p.category_id),
                      p.barcode, p.sku,
                      p.brand || '—', Number(p.min_stock || 0),
                      status, p.id,
                    ];
                    vals.forEach((v, j) => {
                      const isNum = typeof v === 'number';
                      ws[`${cols[j]}${r}`] = { v, t: isNum ? 'n' : 's', s: { ...rowBg, ...(isNum ? numCell : j === 0 || j === 20 ? ctrCell : {}) } };
                    });
                  });

                  // Set sheet range
                  ws['!ref'] = `A1:U${products.length + 2}`;

                  // Column widths
                  ws['!cols'] = [
                    {wch:4},{wch:28},{wch:8},{wch:8},
                    {wch:10},{wch:7},{wch:12},
                    {wch:10},{wch:7},{wch:12},
                    {wch:10},{wch:7},{wch:12},
                    {wch:7},{wch:14},{wch:14},{wch:12},{wch:12},{wch:8},{wch:8},{wch:5}
                  ];
                  // Freeze top 2 rows
                  ws['!freeze'] = { xSplit: 2, ySplit: 2, topLeftCell: 'C3', activeCell: 'C3', sqref: 'C3' };

                  XLSX.utils.book_append_sheet(wb, ws, 'Mahsulotlar');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx', cellStyles: true })]), `mahsulotlar_${new Date().toISOString().slice(0,10)}.xlsx`);
                }}
                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors border border-emerald-200"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                {t('product.excelExport')}
              </button>
            </>
          )}
          <button
            onClick={activeTab === 'products' ? openAdd : activeTab === 'categories' ? openAddCat : openAddBl}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            {activeTab === 'products' ? t('product.addProduct') : activeTab === 'categories' ? t('product.addCategory') : t('product.addLocation')}
          </button>
          <div className="flex bg-slate-100 rounded-xl p-1 gap-1">
            {[['products', t('product.title')], ['categories', t('product.categories')], ['binloc', t('product.locations')]].map(([key, label]) => (
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
              { label: t('product.totalProducts'), val: totalRecords,  icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4', bg: 'bg-indigo-100',  ic: 'text-indigo-600',  vl: 'text-slate-800' },
              { label: t('product.active'),        val: totalActive,   icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',                        bg: 'bg-emerald-100', ic: 'text-emerald-600', vl: 'text-emerald-600' },
              { label: t('product.outOfStockStat'),val: outOfStock,    icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z', bg: 'bg-red-100', ic: 'text-red-500', vl: 'text-red-500' },
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
              <option value="">{t('product.allCategories')}</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm text-slate-700"
              value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">{t('product.allStatus')}</option>
              <option value="active">{t('admin.dict.active') || 'Faol'}</option>
              <option value="inactive">{t('admin.dict.inactive') || 'Nofaol'}</option>
              <option value="archived">{t('product.archived')}</option>
            </select>
            {warehouses.length > 0 && (
              <select className={`px-3.5 py-2.5 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm text-slate-700 ${
                filterWarehouse ? 'border-indigo-400 ring-1 ring-indigo-300 text-indigo-700 font-semibold' : 'border-slate-200'
              }`}
                value={filterWarehouse} onChange={e => setFilterWarehouse(e.target.value)}>
                <option value="">🏭 {t('common.allWarehouses')}</option>
                {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            )}
            {deleteProgress === 'deleting' ? (
              <div className="flex items-center gap-3 px-4 py-2 bg-red-50 border border-red-200 rounded-xl min-w-[220px]">
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-red-600">{t('product.deleting')}</span>
                    <span className="text-xs font-bold text-red-700">{deletePercent}%</span>
                  </div>
                  <div className="w-full bg-red-200 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-red-500 h-2 rounded-full transition-all duration-200"
                      style={{ width: `${deletePercent}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : selectedIds.length > 0 && (
              <button onClick={handleBulkDelete} className="px-4 py-2.5 bg-red-50 hover:bg-red-100 text-red-600 text-sm font-semibold rounded-xl transition-colors inline-flex items-center gap-2 shrink-0">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                {selectedIds.length} {t('common.delete')}
              </button>
            )}
            
            <select className="px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white shadow-sm text-slate-700 font-medium"
              value={limit} onChange={e => { const v = Number(e.target.value); localStorage.setItem('products_limit', v); setLimit(v); }}>
              {[10,20,50,100,200,500,1000,5000].map(n => (
                <option key={n} value={n}>{n} {t('common.item')}</option>
              ))}
            </select>
            <button onClick={loadProducts}
              className="px-4 py-2.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-sm font-semibold rounded-xl transition-colors">
              {t('common.search').replace('...','')}
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
                    <col style={{width:'44px'}} />
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
                      <th className="px-3 py-3 w-10">
                        <input type="checkbox"
                          checked={totalRecords > 0 && selectedIds.length === totalRecords}
                          onChange={handleSelectAll}
                          className="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500 cursor-pointer"
                        />
                      </th>
                      {[t('product.thBarcode'), t('product.thImage'), t('product.thProduct'), t('product.category'), t('product.thUnit'), t('product.thCost'), t('product.thWholesale'), t('product.thRetail'), t('product.stock'), t('common.status'), ''].map(h => (
                        <th key={h} className="px-2 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap overflow-hidden">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {products.map(p => {
                      const thumb = (Array.isArray(p.images) && p.images[0]) || p.image_url;
                      return (
                        <tr key={p.id} className={`hover:bg-indigo-50/30 transition-colors ${selectedIds.includes(p.id) ? 'bg-indigo-50/50' : ''}`}>
                          <td className="px-3 py-3">
                            <input type="checkbox"
                              checked={selectedIds.includes(p.id)}
                              onChange={e => {
                                if (e.target.checked) setSelectedIds(s => [...s, p.id]);
                                else setSelectedIds(s => s.filter(id => id !== p.id));
                              }}
                              className="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500 cursor-pointer"
                            />
                          </td>
                          <td className="px-2 py-3">
                            <div className="text-xs font-mono font-bold text-slate-800 truncate">{p.barcode}</div>
                            {Array.isArray(p.extra_barcodes) && p.extra_barcodes.length > 0 && (
                              <div className="flex flex-col gap-0.5 mt-0.5">
                                {p.extra_barcodes.slice(0, 2).map((b, i) => (
                                  <div key={i} className="text-[10px] font-mono text-slate-500 truncate">+ {b}</div>
                                ))}
                                {p.extra_barcodes.length > 2 && (
                                  <div className="text-[10px] text-indigo-400">+{p.extra_barcodes.length - 2} ta</div>
                                )}
                              </div>
                            )}
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
                            <span className="text-xs text-slate-400 ml-0.5">{t('common.sum')}</span>
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
                            <span className="text-sm font-medium">{t('product.noProducts')}</span>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
                {products.length > 0 && (
                  <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500 bg-slate-50">
                    <div className="flex gap-4">
                      <span>{t('common.total')} <strong className="text-slate-700">{totalRecords}</strong> {t('common.item')} {t('product.title').toLowerCase()}</span>
                      <span>{t('product.currentPage')} <strong className="text-slate-700">{products.length}</strong></span>
                    </div>

                    <div className="flex items-center gap-1">
                      <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                        className={`p-1.5 rounded-lg border ${page === 1 ? 'border-transparent text-slate-300' : 'border-slate-200 text-slate-700 hover:bg-white bg-slate-50'} transition-colors`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
                      </button>
                      <span className="px-3 text-sm font-semibold text-slate-700">{page} / {Math.ceil(totalRecords / limit) || 1}</span>
                      <button disabled={page >= (Math.ceil(totalRecords / limit) || 1)} onClick={() => setPage(p => p + 1)}
                        className={`p-1.5 rounded-lg border ${page >= (Math.ceil(totalRecords / limit) || 1) ? 'border-transparent text-slate-300' : 'border-slate-200 text-slate-700 hover:bg-white bg-slate-50'} transition-colors`}>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                      </button>
                    </div>

                    <span>Faol: <strong className="text-emerald-600">{totalActive}</strong> &nbsp;|&nbsp; Qoldiqsiz: <strong className="text-red-500">{outOfStock}</strong></span>
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
            <span className="text-sm font-semibold text-slate-700">{t('product.allCategoriesLabel')} ({categories.length})</span>
            <button onClick={openAddCat}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-xs font-semibold rounded-lg transition-colors">
              + {t('product.addCategory')}
            </button>
          </div>
          <table className="min-w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['#', t('common.name'), t('product.parentCategory'), t('product.sortOrder'), t('common.created'), t('product.productsCount') || 'Mahsulotlar', ''].map(h => (
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
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${(c.products_count || 0) > 0 ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-400'}`}>
                      {c.products_count || 0} ta
                    </span>
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
                <tr><td colSpan={7} className="px-6 py-14 text-center text-sm text-slate-400">{t('product.noCategories')}</td></tr>
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
                <tr><td colSpan={3} className="px-6 py-14 text-center text-sm text-slate-400">{t('product.noLocations')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ════ PRODUCT ADD / EDIT MODAL ════ */}
      {modal && (
        <Modal
          title={modal === 'add' ? t('product.addNewProduct') : t('product.editProduct')}
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
                <Field label={t('product.productName')} required>
                  <input
                    className={`${inputCls} text-base ${!form.name?.trim() && error ? errCls : ''}`}
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder={t('product.productNamePlaceholder')}
                  />
                </Field>

                {/* Brand */}
                <Field label={t('product.brandLabel')} hint={t('product.brandHint')}>
                  <input
                    className={inputCls}
                    value={form.brand}
                    onChange={e => setForm({ ...form, brand: e.target.value })}
                    placeholder={t('product.brandPlaceholder')}
                  />
                </Field>

                {/* Barcode + SKU */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label={t('product.skuLabel')} hint={t('product.skuHint')}>
                    <input className={inputCls} value={form.sku}
                      onChange={e => setForm({ ...form, sku: e.target.value })} placeholder={t('product.skuPlaceholder')} />
                  </Field>
                  <Field label="Birlamchi shtrix kod" required>
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
                        title="Yangi barcode"
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
                    <button
                      type="button"
                      onClick={() => setForm(f => ({ ...f, extra_barcodes: [...(f.extra_barcodes || []), genBarcodeByFormat(f.barcode_format)] }))}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 text-xs font-semibold rounded-lg transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      Barcode qo'shish
                    </button>
                  </div>
                  {(form.extra_barcodes || []).length === 0 ? (
                    <p className="text-xs text-slate-400 py-1">Hozircha qo'shimcha shtrix kod yo'q</p>
                  ) : (
                    (form.extra_barcodes || []).map((bc, idx) => (
                      <div key={idx} className="flex gap-2 items-center">
                        <span className="text-xs text-slate-400 font-mono w-5 shrink-0">{idx + 2}.</span>
                        <input
                          className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          value={bc}
                          onChange={e => {
                            const updated = [...(form.extra_barcodes || [])];
                            updated[idx] = e.target.value;
                            setForm(f => ({ ...f, extra_barcodes: updated }));
                          }}
                          placeholder="Shtrix kod..."
                        />
                        <button
                          type="button"
                          onClick={() => setForm(f => ({ ...f, extra_barcodes: f.extra_barcodes.filter((_, i) => i !== idx) }))}
                          className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const updated = [...(form.extra_barcodes || [])];
                            updated[idx] = genBarcodeByFormat(form.barcode_format);
                            setForm(f => ({ ...f, extra_barcodes: updated }));
                          }}
                          className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors shrink-0"
                          title="Yangi barcode"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                        </button>
                      </div>
                    ))
                  )}
                </div>

                {/* Category + Unit */}
                <div className="grid grid-cols-2 gap-4">
                  <Field label={t('admin.dict.category') || 'Kategoriya'}>
                    <div className="flex gap-2">
                      <select className={`${inputCls} flex-1`} value={form.category_id}
                        onChange={e => setForm({ ...form, category_id: e.target.value })}>
                        <option value="">{t('product.noCategory')}</option>
                        {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                      <button
                        type="button"
                        title={t('product.addCategoryTitle')}
                        onClick={() => { openAddCat(); }}
                        className="shrink-0 w-11 h-11 flex items-center justify-center bg-indigo-50 hover:bg-indigo-100 text-indigo-600 font-bold text-xl rounded-xl border-2 border-indigo-100 hover:border-indigo-300 transition-all"
                      >+</button>
                    </div>
                  </Field>
                  <Field label={t('product.unit')}>
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
                      <label className="block text-sm font-semibold text-slate-600 mb-1.5">{t('product.costPriceLabel')}</label>
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
                          <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.cost_price) * Number(cur.rate)))} {t('common.sum')}</p>
                        ) : null;
                      })()}
                    </div>

                    {/* Ulgurji narxi */}
                    <div>
                      <label className="block text-sm font-semibold text-slate-600 mb-1.5">{t('product.wholesalePriceLabel')}</label>
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
                          <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.wholesale_price) * Number(cur.rate)))} {t('common.sum')}</p>
                        ) : null;
                      })()}
                    </div>
                  </div>

                  {/* Row 2: Chakana (full width — most important price) */}
                  <div>
                    <label className="block text-sm font-semibold text-slate-600 mb-1.5">
                      {t('product.retailPriceLabel')} <span className="text-red-500">*</span>
                      <span className="ml-2 text-xs font-normal text-slate-400">{t('product.mainSalePrice')}</span>
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
                        <p className="text-xs text-amber-600 mt-1">≈ {fmt(Math.round(Number(form.sale_price) * Number(cur.rate)))} {t('common.sum')}</p>
                      ) : null;
                    })()}
                  </div>
                </div>

                {/* UZS preview */}
                {priceCurSelected && (form.cost_price || form.sale_price) && (
                  <div className="px-4 py-3 bg-amber-50 border border-amber-100 rounded-xl text-sm text-amber-700 flex flex-wrap gap-x-5 gap-y-1">
                    <span className="font-semibold">{t('product.uzsPreview')}</span>
                    {form.cost_price && <span>{t('product.costShort')} <strong>{fmt(Math.round(Number(form.cost_price) * priceRate))}</strong></span>}
                    {form.wholesale_price && <span>{t('product.wholesaleShort')} <strong>{fmt(Math.round(Number(form.wholesale_price) * priceRate))}</strong></span>}
                    {form.sale_price && <span>{t('product.retailShort')} <strong>{fmt(Math.round(Number(form.sale_price) * priceRate))}</strong></span>}
                  </div>
                )}

                {/* Margin hint */}
                {form.cost_price && form.sale_price && Number(form.sale_price) > 0 && (
                  <div className="px-4 py-3 bg-indigo-50 rounded-xl text-sm text-indigo-700">
                    Margin: <strong>{(((Number(form.sale_price) - Number(form.cost_price)) / Number(form.sale_price)) * 100).toFixed(1)}%</strong>
                    &nbsp;|&nbsp; {t('product.profit')} <strong>{fmt(Number(form.sale_price) - Number(form.cost_price))} {priceCurCode}</strong>
                  </div>
                )}

                {/* Stock */}
                <div className="grid grid-cols-3 gap-4">
                  {modal === 'add' && (
                    <Field label={t('product.initialStock')}>
                      <input type="number" min="0" step="0.01" className={`${inputCls} text-base`}
                        value={form.initial_stock} onChange={e => setForm({ ...form, initial_stock: e.target.value })} placeholder="0" />
                    </Field>
                  )}
                  <Field label={t('product.minStockLabel')}>
                    <input type="number" min="0" className={`${inputCls} text-base`}
                      value={form.min_stock} onChange={e => setForm({ ...form, min_stock: e.target.value })} />
                  </Field>
                  <Field label={t('product.maxStock')}>
                    <input type="number" min="0" className={`${inputCls} text-base`}
                      value={form.max_stock} onChange={e => setForm({ ...form, max_stock: e.target.value })} placeholder={t('product.maxStockPlaceholder')} />
                  </Field>
                  {modal !== 'add' && <div />}
                </div>

              </div>

              {/* ── RIGHT: details (1/3) ── */}
              <div className="col-span-1 space-y-5">

                {/* Images */}
                <Field label={t('product.images')}>
                  <ImageUploadZone
                    images={form.images}
                    onAdd={handleImageFile}
                    onRemove={removeImage}
                    uploading={imgUploading}
                  />
                </Field>

                {/* Bin location */}
                <Field label={t('product.binLocationLabel')} hint={t('product.binLocationHint')}>
                  <div className="flex gap-2">
                    <select className={`${inputCls} flex-1`} value={form.bin_location}
                      onChange={e => setForm({ ...form, bin_location: e.target.value })}>
                      <option value="">{t('product.selectOption')}</option>
                      {binLocations.map(b => (
                        <option key={b.id} value={b.code}>{b.code}{b.label ? ` — ${b.label}` : ''}</option>
                      ))}
                    </select>
                    <button type="button" onClick={openAddBl}
                      title={t('product.addBinTitle')}
                      className="px-3 py-3 bg-slate-100 hover:bg-indigo-100 text-slate-600 hover:text-indigo-600 rounded-xl transition-colors shrink-0">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                  </div>
                </Field>

                {/* Weight + Dimensions */}
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t('product.weight')}>
                    <input type="number" min="0" step="0.001" className={inputCls}
                      value={form.weight} onChange={e => setForm({ ...form, weight: e.target.value })} placeholder="0.000" />
                  </Field>
                  <Field label={t('product.dimensions')}>
                    <input className={inputCls} value={form.dimensions}
                      onChange={e => setForm({ ...form, dimensions: e.target.value })} placeholder="UxBxH" />
                  </Field>
                </div>

                {/* Status */}
                <Field label={t('admin.dict.status') || 'Holat'}>
                  <select className={inputCls} value={form.status}
                    onChange={e => setForm({ ...form, status: e.target.value })}>
                    <option value="active">{t('admin.dict.active') || 'Faol'}</option>
                    <option value="inactive">{t('admin.dict.inactive') || 'Nofaol'}</option>
                    <option value="archived">{t('product.archived')}</option>
                  </select>
                </Field>

              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-8 pt-6 border-t border-slate-100">
              <button type="button" onClick={closeModal}
                className="flex-1 py-3 border border-slate-200 text-slate-600 font-semibold text-base rounded-xl hover:bg-slate-50 transition-colors">
                {t('product.cancelAction')}
              </button>
              <button type="submit" disabled={saving}
                className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-bold text-base rounded-xl transition-colors">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ════ CATEGORY MODAL ════ */}
      {catModal && (
        <Modal title={catModal === 'add' ? t('product.newCategory') : t('product.editCategory')} onClose={closeCatModal} size="sm" z="z-60">
          <form onSubmit={handleSaveCat} className="p-6 space-y-4">
            <Field label={t('product.categoryName')} required>
              <input required className={inputCls} value={catForm.name}
                onChange={e => setCatForm({ ...catForm, name: e.target.value })} placeholder={t('product.categoryNamePlaceholder')} />
            </Field>
            <Field label={t('product.parentCategoryOpt')}>
              <select className={inputCls} value={catForm.parent_id}
                onChange={e => setCatForm({ ...catForm, parent_id: e.target.value })}>
                <option value="">{t('product.noParentCategory')}</option>
                {categories.filter(c => !catSelected || c.id !== catSelected.id).map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </Field>
            <Field label={t('product.sortNumber')}>
              <input type="number" min="0" className={inputCls} value={catForm.sort_order}
                onChange={e => setCatForm({ ...catForm, sort_order: e.target.value })} />
            </Field>
            {catError && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{catError}</div>}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={closeCatModal}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
              <button type="submit" disabled={catSaving}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                {catSaving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ════ BIN LOCATION MODAL ════ */}
      {blModal && (
        <Modal title={blModal === 'add' ? t('product.newBinLocation') : t('product.editBinLocation')} onClose={closeBlModal} size="sm" z="z-60">
          <form onSubmit={handleSaveBl} className="p-6 space-y-4">
            <Field label={t('product.binCode')} required hint={t('product.binCodeHint')}>
              <input required className={inputCls} value={blForm.code}
                onChange={e => setBlForm({ ...blForm, code: e.target.value.toUpperCase() })}
                placeholder="A-01" />
            </Field>
            <Field label={t('product.binDescLabel')}>
              <input className={inputCls} value={blForm.label}
                onChange={e => setBlForm({ ...blForm, label: e.target.value })}
                placeholder={t('product.binDescPlaceholder')} />
            </Field>
            {blError && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{blError}</div>}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={closeBlModal}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
              <button type="submit" disabled={blSaving}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
                {blSaving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ════ HISTORY MODAL ════ */}
      {histProduct && (
        <Modal title={`${t('product.historyTitle')} ${histProduct.name}`} onClose={closeHistory} size="lg">
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
                <div className="text-xs text-slate-400">{t('product.retailShortLabel')}</div>
                <div className="text-lg font-bold text-slate-800">{fmt(histProduct.sale_price)} {t('common.sum')}</div>
              </div>
            </div>

            {histLoading ? (
              <div className="flex justify-center py-10">
                <div className="w-7 h-7 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : history.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-sm">{t('common.noData')}</div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    {t('product.historyMovement')} {history.length} {t('product.historyOperations')}
                  </div>
                  <div className="text-xs text-slate-400 font-semibold">
                    {t('product.currentStock')} <span className="text-indigo-600 font-bold">{fmt(histProduct.stock_quantity)} {histProduct.unit}</span>
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

      {/* ════ BULK ADD MODAL ════ */}
      {bulkAddOpen && (
        <div className="fixed inset-0 z-[60] bg-white flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shadow-sm shrink-0">
            <div className="flex items-center gap-3">
              <button onClick={() => setBulkAddOpen(false)} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div>
                <h2 className="text-2xl font-bold text-slate-800">Ko'p mahsulot qo'shish</h2>
                <p className="text-sm text-slate-400 mt-0.5">Bir vaqtda bir nechta mahsulot qo'shish — har bir qatorda birnechta shtrix kod kiritish mumkin</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-base text-slate-500 font-semibold">{bulkRows.length} ta qator</span>
              <button
                onClick={handleBulkAddSave}
                disabled={bulkSaving}
                className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-base font-bold rounded-xl transition-colors"
              >
                {bulkSaving ? (
                  <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />Saqlanmoqda...</>
                ) : (
                  <><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>Saqlash</>
                )}
              </button>
            </div>
          </div>

          {/* Error / Result */}
          {bulkError && (
            <div className="mx-6 mt-3 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-base font-medium rounded-xl shrink-0">{bulkError}</div>
          )}
          {bulkResult && (
            <div className="mx-6 mt-3 px-4 py-3 bg-emerald-50 border border-emerald-200 text-base rounded-xl shrink-0 flex items-center gap-6">
              <span className="font-bold text-emerald-700 text-lg">{bulkResult.created} ta mahsulot saqlandi</span>
              {bulkResult.errors.length > 0 && (
                <div className="text-red-600">
                  {bulkResult.errors.slice(0, 3).map((e, i) => (
                    <div key={i}><strong>{e.name}</strong>: {e.error}</div>
                  ))}
                  {bulkResult.errors.length > 3 && <div>+{bulkResult.errors.length - 3} ta xato...</div>}
                </div>
              )}
            </div>
          )}

          {/* Table */}
          <div className="flex-1 overflow-auto p-5">
            <div className="min-w-[1100px]">
              {/* Column headers */}
              <div className="grid gap-3 mb-3 text-sm font-extrabold text-slate-600 uppercase tracking-wide px-3"
                style={{ gridTemplateColumns: '40px 1fr 130px 120px 120px 1fr 90px 170px 90px 40px' }}>
                <span>#</span>
                <span>Mahsulot nomi *</span>
                <span>Chakana *</span>
                <span>Ulgurji</span>
                <span>Tan narxi</span>
                <span>Shtrix kodlar (birlamchi + qo'shimcha)</span>
                <span>O'lchov</span>
                <span>Kategoriya</span>
                <span>Qoldiq</span>
                <span></span>
              </div>

              {/* Rows */}
              <div className="space-y-3">
                {bulkRows.map((row, rowIdx) => (
                  <div key={row._key} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
                    <div className="grid gap-3 items-start"
                      style={{ gridTemplateColumns: '40px 1fr 130px 120px 120px 1fr 90px 170px 90px 40px' }}>
                      {/* # */}
                      <div className="flex items-center justify-center h-11 text-base font-bold text-slate-400">{rowIdx + 1}</div>

                      {/* Name */}
                      <input
                        className="h-12 px-3 border border-slate-200 rounded-lg text-base font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                        value={row.name}
                        onChange={e => updateBulkRow(row._key, 'name', e.target.value)}
                        placeholder="Mahsulot nomi..."
                      />

                      {/* Sale price (Chakana) — birinchi */}
                      <input
                        className="h-11 px-3 border border-emerald-300 rounded-lg text-base font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full bg-emerald-50"
                        value={fmtPrice(row.sale_price)}
                        onChange={e => updateBulkRow(row._key, 'sale_price', parsePrice(e.target.value))}
                        placeholder="0"
                        inputMode="numeric"
                      />

                      {/* Wholesale (Ulgurji) — ikkinchi */}
                      <input
                        className="h-11 px-3 border border-slate-200 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                        value={fmtPrice(row.wholesale_price)}
                        onChange={e => updateBulkRow(row._key, 'wholesale_price', parsePrice(e.target.value))}
                        placeholder="—"
                        inputMode="numeric"
                      />

                      {/* Cost price (Tan narxi) — uchinchi */}
                      <input
                        className="h-11 px-3 border border-slate-200 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                        value={fmtPrice(row.cost_price)}
                        onChange={e => updateBulkRow(row._key, 'cost_price', parsePrice(e.target.value))}
                        placeholder="0"
                        inputMode="numeric"
                      />

                      {/* Barcodes */}
                      <div className="space-y-2">
                        {row.barcodes.map((bc, bcIdx) => (
                          <div key={bcIdx} className="flex gap-1.5 items-center">
                            <span className={`text-sm font-bold px-1.5 py-1 rounded shrink-0 ${
                              bcIdx === 0 ? 'text-indigo-600 bg-indigo-50' : 'text-slate-400 bg-slate-100'
                            }`}>{bcIdx + 1}</span>
                            <input
                              data-bulk-barcode-input="true"
                              className={`flex-1 h-10 px-3 border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 ${
                                bcIdx === 0
                                  ? row.barcode_status === 'exists'
                                    ? 'border-red-300 bg-red-50/50 focus:ring-red-400'
                                    : row.barcode_status === 'new'
                                    ? 'border-emerald-300 bg-emerald-50/50 focus:ring-emerald-400'
                                    : 'border-indigo-200 bg-indigo-50/50 focus:ring-indigo-500'
                                  : 'border-slate-200 focus:ring-indigo-500'
                              }`}
                              value={bc}
                              onChange={e => {
                                updateBulkBarcode(row._key, bcIdx, e.target.value);
                                if (bcIdx === 0) updateBulkRow(row._key, 'barcode_status', null);
                              }}
                              onKeyDown={e => {
                                if (e.key === 'Enter' && bcIdx === 0) {
                                  e.preventDefault();
                                  checkBulkBarcode(row._key, bc);
                                }
                              }}
                              onBlur={() => bcIdx === 0 && bc.trim() && checkBulkBarcode(row._key, bc)}
                              placeholder={bcIdx === 0 ? "Skaner qiling yoki kiriting..." : "Barcode..."}
                            />
                            <button type="button"
                              onClick={() => {
                                const nb = genBarcodeByFormat('ean8');
                                updateBulkBarcode(row._key, bcIdx, nb);
                                if (bcIdx === 0) updateBulkRow(row._key, 'barcode_status', null);
                              }}
                              className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors shrink-0"
                              title="Yangi barcode">
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                              </svg>
                            </button>
                            {bcIdx > 0 && (
                              <button type="button"
                                onClick={() => removeBulkBarcode(row._key, bcIdx)}
                                className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            )}
                          </div>
                        ))}

                        {/* Barcode check status */}
                        {row.barcode_status === 'checking' && (
                          <div className="flex items-center gap-1.5 text-sm text-slate-400">
                            <div className="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
                            Tekshirilmoqda...
                          </div>
                        )}
                        {row.barcode_status === 'exists' && row.barcode_product && (
                          <div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg">
                            <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <span className="text-sm font-semibold text-red-600">Allaqachon mavjud:</span>
                            <span className="text-sm text-red-700 font-bold truncate">{row.barcode_product.name}</span>
                          </div>
                        )}
                        {row.barcode_status === 'new' && (
                          <div className="flex items-center gap-1.5 text-sm text-emerald-600 font-medium">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Yangi mahsulot — qo'shiladi
                          </div>
                        )}

                        <button type="button"
                          onClick={() => addBulkBarcode(row._key)}
                          className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-500 hover:text-indigo-700 transition-colors mt-1">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                          </svg>
                          Barcode qo'shish
                        </button>
                      </div>

                      {/* Unit */}
                      <select
                        className="h-11 px-2 border border-slate-200 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                        value={row.unit}
                        onChange={e => updateBulkRow(row._key, 'unit', e.target.value)}
                      >
                        {['dona', 'kg', 'g', 'litr', 'ml', 'metr', 'sm', 'quti', 'paket', 'juft'].map(u => (
                          <option key={u} value={u}>{u}</option>
                        ))}
                      </select>

                      {/* Category */}
                      <select
                        className="h-11 px-2 border border-slate-200 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                        value={row.category_id}
                        onChange={e => updateBulkRow(row._key, 'category_id', e.target.value)}
                      >
                        <option value="">Kategoriya</option>
                        {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>

                      {/* Initial stock */}
                      <input type="number" min="0"
                        className="h-11 px-3 border border-slate-200 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full"
                        value={row.initial_stock}
                        onChange={e => updateBulkRow(row._key, 'initial_stock', e.target.value)}
                        placeholder="0"
                      />

                      {/* Remove row */}
                      <button type="button"
                        onClick={() => removeBulkRow(row._key)}
                        className="h-11 w-10 flex items-center justify-center text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        title="Qatorni o'chirish">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Manual add */}
              <div className="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setBulkRows(rows => [...rows, emptyBulkRow()])}
                  className="h-11 px-5 border-2 border-dashed border-slate-200 hover:border-indigo-400 hover:bg-indigo-50/30 text-slate-400 hover:text-indigo-600 text-sm font-semibold rounded-xl transition-all flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Qo'lda qo'shish
                </button>
                <span className="text-xs text-slate-400 flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m0 14v1m8-8h-1M5 12H4m13.657-6.343l-.707.707M7.05 16.95l-.707.707m9.9 0l-.707-.707M7.757 7.757l-.707-.707"/><circle cx="12" cy="12" r="3"/></svg>
                  Bo'sh joyga bosib skaner qiling — avtomatik qo'shiladi
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ════ ADVANCED EXCEL IMPORT FULLSCREEN ════ */}
      {importOpen && (
        <div className="fixed inset-0 z-[60] bg-white flex flex-col">
          {/* Top Bar */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-white shadow-sm shrink-0">
            <div className="flex items-center gap-3">
              <button onClick={() => resetImport()} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
              <h2 className="text-xl font-bold text-slate-800">Mahsulotlarni Exceldan yuklash</h2>
              {importFile && <span className="text-sm text-slate-400 font-medium">{importFile.name}</span>}
            </div>
            <div className="flex items-center gap-3">
              <button onClick={downloadTemplate} className="inline-flex items-center gap-1.5 px-3 py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-lg border border-slate-200">
                Shablon
              </button>
              <label className="inline-flex items-center gap-1.5 px-3 py-2 bg-slate-50 hover:bg-slate-100 text-slate-600 text-sm font-semibold rounded-lg border border-slate-200 cursor-pointer">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                Fayl tanlash
                <input type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { if (e.target.files[0]) parseExcel(e.target.files[0]); }} />
              </label>
              <button
                onClick={handleImport}
                disabled={!buildPayload().length || importLoading || !(Object.values(colMap).includes('Nomi') || (allowUpdate && (Object.values(colMap).includes('Barkod') || Object.values(colMap).includes('SKU'))))}
                className="inline-flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
                {importLoading ? 'Saqlanmoqda...' : 'Saqlash'}
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto flex flex-col">
            {/* Stats & options row */}
            <div className="px-6 py-4 bg-slate-50 border-b border-slate-100 shrink-0">
              <div className="flex flex-wrap items-center gap-4">
                {/* Stats */}
                <div className="flex items-center gap-3">
                  <div className="px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm">
                    <span className="text-slate-500 text-sm">Bazadan topilgan mahsulotlar soni:</span>
                    <span className="font-bold text-emerald-600 ml-2 text-base">{importRows.length > 0 ? foundCount : 0} шт</span>
                  </div>
                  <div className="px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm">
                    <span className="text-slate-500 text-sm">Bazadan topilmagan mahsulotlar soni:</span>
                    <span className="font-bold text-violet-600 ml-2 text-base">{importRows.length > 0 ? notFoundCount : 0} шт</span>
                  </div>
                </div>

                {/* Skip rows counter */}
                <div className="ml-auto flex items-center gap-2 border border-slate-200 bg-white rounded-xl px-3 py-2">
                  <span className="text-sm text-slate-500 font-medium">Belgilangan qatorlarni yuklamaslik</span>
                  <button onClick={() => setSkipRows(s => Math.max(0, s-1))} className="w-7 h-7 flex items-center justify-center text-xl text-slate-500 hover:text-red-500 transition-colors">−</button>
                  <span className="w-9 text-center text-base font-bold text-slate-700">{skipRows}</span>
                  <button onClick={() => setSkipRows(s => s+1)} className="w-7 h-7 flex items-center justify-center text-xl text-slate-500 hover:text-indigo-500 transition-colors">+</button>
                </div>
              </div>

              {/* Toggles */}
              <div className="flex items-center gap-8 mt-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <button
                    onClick={() => setSearchBySku(v => !v)}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${searchBySku ? 'bg-indigo-600' : 'bg-slate-300'}`}
                  >
                    <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${searchBySku ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                  <span className="text-base text-slate-700">Mahsulotni artikul bo'yicha ham qidirish</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <button
                    onClick={() => setAllowUpdate(v => !v)}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${allowUpdate ? 'bg-indigo-600' : 'bg-slate-300'}`}
                  >
                    <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${allowUpdate ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                  <span className="text-base text-slate-700">Mahsulotlarni tahrirlash</span>
                </label>
              </div>
            </div>

            {!importFile ? (
              /* Upload zone */
              <div className="flex-1 flex flex-col items-center justify-center p-12">
                <label
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) parseExcel(f); }}
                  className="flex flex-col items-center justify-center w-full max-w-lg h-56 border-2 border-dashed border-slate-300 rounded-2xl cursor-pointer hover:border-violet-400 hover:bg-violet-50/20 transition-all group"
                >
                  <svg className="w-16 h-16 text-slate-200 group-hover:text-violet-300 mb-4 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  <p className="text-slate-500 text-base font-medium group-hover:text-violet-600">Excel faylni bu yerga tashlang yoki bosing</p>
                  <p className="text-slate-300 text-sm mt-1">.xlsx, .xls formati qabul qilinadi</p>
                  <input type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { if (e.target.files[0]) parseExcel(e.target.files[0]); }} />
                </label>
              </div>
            ) : (
              /* Data table */
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Table header info */}
                <div className="px-6 py-2.5 flex items-center justify-between border-b border-slate-100 shrink-0">
                  <span className="text-sm text-slate-600 font-medium">
                    Yuklanayotgan mahsulotlar soni: <strong>{buildPayload().length} шт</strong>
                  </span>
                  {!(Object.values(colMap).includes('Nomi') || (allowUpdate && (Object.values(colMap).includes('Barkod') || Object.values(colMap).includes('SKU')))) && (
                    <span className="text-sm font-semibold text-red-500">
                      * {allowUpdate ? 'Mahsulot nomi, Barkod yoki SKU' : 'Mahsulot nomi'} ustunini tanlash majburiy
                    </span>
                  )}
                </div>

                {/* Scrollable table */}
                <div className="flex-1 overflow-auto">
                  <table className="min-w-full text-sm border-collapse">
                    {/* Row 1: Column mapping dropdowns */}
                    <thead>
                      <tr className="bg-slate-100">
                        <th className="px-3 py-2.5 text-left font-bold text-slate-500 border-b border-slate-200 w-12 text-sm">#</th>
                        {excelCols.map(col => (
                          <th key={col} className="px-2 py-2 border-b border-slate-200 min-w-[160px]">
                            <select
                              value={colMap[col] || ''}
                              onChange={e => setColMap(m => ({ ...m, [col]: e.target.value }))}
                              className={`w-full px-2 py-2 text-sm font-semibold rounded-lg border outline-none cursor-pointer ${
                                colMap[col] && colMap[col] !== '__SKIP__'
                                  ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                                  : 'border-slate-200 bg-white text-slate-500'
                              }`}
                            >
                              {IMPORT_FIELDS.map(f => (
                                <option key={f.key} value={f.key}>{f.label}</option>
                              ))}
                            </select>
                          </th>
                        ))}
                      </tr>
                      {/* Row 2: Excel column names (original headers) */}
                      <tr className="bg-slate-700 text-white">
                        <th className="px-3 py-2.5 text-left text-sm font-bold">№</th>
                        {excelCols.map(col => (
                          <th key={col} className="px-3 py-2.5 text-left text-sm font-semibold whitespace-nowrap">{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {importRows
                        .slice((importPage-1)*IMPORT_LIMIT, importPage*IMPORT_LIMIT)
                        .map((row, i) => {
                          const absIdx = (importPage-1)*IMPORT_LIMIT + i;
                          const isSkip = absIdx < skipRows - 1;
                          return (
                            <tr key={i} className={`${isSkip ? 'opacity-30 bg-slate-50' : i%2===0 ? 'bg-white' : 'bg-slate-50/40'} hover:bg-indigo-50/30 transition-colors`}>
                              <td className="px-3 py-3 text-slate-400 font-mono text-sm">{absIdx + 1}</td>
                              {excelCols.map(col => (
                                <td key={col} className="px-3 py-3 whitespace-nowrap text-slate-700 text-sm max-w-[200px] truncate">
                                  {String(row[col] ?? '')}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between bg-white shrink-0">
                  <span className="text-sm text-slate-500">
                    {importRows.length} ta ma'lumotdan {Math.min((importPage-1)*IMPORT_LIMIT+1, importRows.length)} dan {Math.min(importPage*IMPORT_LIMIT, importRows.length)} gacha ko'rsatildi
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setImportPage(p => Math.max(1, p-1))}
                      disabled={importPage === 1}
                      className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors"
                    >{t('admin.dict.prev') || 'Oldingi'}</button>
                    {Array.from({length: Math.ceil(importRows.length/IMPORT_LIMIT)}, (_, i) => i+1).slice(
                      Math.max(0, importPage-3), Math.min(Math.ceil(importRows.length/IMPORT_LIMIT), importPage+2)
                    ).map(p => (
                      <button key={p} onClick={() => setImportPage(p)}
                        className={`w-9 h-9 rounded-lg text-sm font-semibold transition-colors ${
                          p === importPage ? 'bg-indigo-600 text-white' : 'border border-slate-200 text-slate-600 hover:bg-slate-50'
                        }`}>{p}</button>
                    ))}
                    <button
                      onClick={() => setImportPage(p => Math.min(Math.ceil(importRows.length/IMPORT_LIMIT), p+1))}
                      disabled={importPage >= Math.ceil(importRows.length/IMPORT_LIMIT)}
                      className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors"
                    >{t('admin.dict.next') || 'Keyingi'}</button>
                    <span className="text-sm text-slate-400 ml-2">{t('admin.dict.limit') || 'Limit'}</span>
                    <span className="px-2 py-1 border border-slate-200 rounded-lg text-sm font-bold text-slate-600">{IMPORT_LIMIT}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Progress bar */}
            {importLoading && (
              <div className="px-6 py-4 border-t border-slate-100 bg-white shrink-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-slate-600">Yuklanmoqda...</span>
                  <span className="text-sm font-bold text-indigo-600">{importProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
                  <div
                    className="bg-indigo-500 h-3 rounded-full transition-all duration-300"
                    style={{ width: `${importProgress}%` }}
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1.5">
                  {Math.round(buildPayload().length * importProgress / 100).toLocaleString()} / {buildPayload().length.toLocaleString()} ta mahsulot
                </p>
              </div>
            )}

            {/* Result panel */}
            {importResult && (
              <div className="px-6 py-4 bg-white border-t border-slate-100">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="px-5 py-3 bg-emerald-50 rounded-xl text-center min-w-[120px]">
                    <div className="text-3xl font-black text-emerald-600">{importResult.created}</div>
                    <div className="text-sm font-semibold text-emerald-500">Yangi qo'shildi</div>
                  </div>
                  {importResult.updated > 0 && (
                    <div className="px-5 py-3 bg-indigo-50 rounded-xl text-center min-w-[120px]">
                      <div className="text-3xl font-black text-indigo-600">{importResult.updated}</div>
                      <div className="text-sm font-semibold text-indigo-500">Yangilandi</div>
                    </div>
                  )}
                  <div className={`px-5 py-3 rounded-xl text-center min-w-[120px] ${importResult.skipped > 0 ? 'bg-amber-50' : 'bg-slate-50'}`}>
                    <div className={`text-3xl font-black ${importResult.skipped > 0 ? 'text-amber-600' : 'text-slate-400'}`}>{importResult.skipped}</div>
                    <div className={`text-sm font-semibold ${importResult.skipped > 0 ? 'text-amber-500' : 'text-slate-400'}`}>O'tkazib yuborildi</div>
                  </div>
                  <div className="flex-1 min-w-0">
                    {importResult.errors?.length > 0 && (
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {importResult.errors.map((e, i) => (
                          <div key={i} className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-100 rounded-lg text-sm">
                            <span className="font-bold text-amber-600 shrink-0">#{e.row}</span>
                            <span className="text-amber-700">{e.name && <span className="font-semibold">{e.name}: </span>}{e.error}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            {importError && (
              <div className="mx-6 mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{importError}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
