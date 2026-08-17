// Products module — shared constants and utility functions
// Extracted from Products.jsx for modularity

export const BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8010/api').replace('/api', '');

/* ─── Price formatting helpers ────────────────────── */
export const fmtPrice = (v) => {
  if (v === '' || v === null || v === undefined) return '';
  let s = String(v).replace(/\s/g, '').replace(',', '.');
  if (s === '.' || s === ',') return '.';
  if (s.endsWith('.')) {
    const intPart = s.slice(0, -1);
    const formattedInt = intPart === '' ? '' : (Number(intPart) || 0).toLocaleString('ru-RU');
    return formattedInt + '.';
  }
  const n = Number(s);
  if (isNaN(n)) return s;
  const parts = s.split('.');
  const formattedInt = Number(parts[0]).toLocaleString('ru-RU');
  if (parts.length > 1) {
    return formattedInt + '.' + parts[1];
  }
  return formattedInt;
};

export const parsePrice = (v) => {
  let s = String(v).replace(/\s/g, '').replace(',', '.').replace(/[^0-9.]/g, '');
  const parts = s.split('.');
  if (parts.length > 2) {
    return parts[0] + '.' + parts.slice(1).join('');
  }
  return s;
};

export const fmt = (v) => {
  if (v === null || v === undefined || v === '') return '0';
  const n = Number(v);
  if (isNaN(n) || n === 0) return '0';
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 4 });
};

/* ─── Barcode generators ───────────────────────────── */
export const genBarcode = () => Math.floor(10000000 + Math.random() * 90000000).toString();

export const BARCODE_FORMATS = [
  { value: 'ean8', label: 'EAN-8', len: 8 },
  { value: 'ean13', label: 'EAN-13', len: 13 },
  { value: 'upca', label: 'UPC-A', len: 12 },
  { value: 'free', label: 'Erkin', len: null },
  { value: 'skaner', label: 'Skaner', len: null },
];

export const genBarcodeByFormat = (fmtVal) => {
  const f = BARCODE_FORMATS.find(f => f.value === fmtVal) || BARCODE_FORMATS[0];
  if (f.value === 'skaner') return '';
  if (!f.len) return genBarcode();
  const min = Math.pow(10, f.len - 1);
  return String(Math.floor(min + Math.random() * (9 * Math.pow(10, f.len - 1))));
};

/* ─── Status metadata ──────────────────────────────── */
export const statusMeta = {
  active: { label: 'Faol', cls: 'bg-emerald-100 text-emerald-700' },
  inactive: { label: 'Nofaol', cls: 'bg-amber-100  text-amber-700' },
  archived: { label: 'Arxiv', cls: 'bg-slate-100   text-slate-500' },
};

export const movTypeMeta = {
  in: { label: 'Kirim', cls: 'bg-emerald-100 text-emerald-700' },
  out: { label: 'Chiqim', cls: 'bg-red-100 text-red-600' },
  adjust: { label: 'Tuzatish', cls: 'bg-amber-100 text-amber-700' },
  transfer: { label: 'Ombor', cls: 'bg-blue-100 text-blue-700' },
  sale: { label: 'Sotuv', cls: 'bg-blue-100 text-blue-700' },
  return: { label: 'Qaytarma', cls: 'bg-orange-100 text-orange-700' },
};

/* ─── Empty form factories ─────────────────────────── */
export const emptyProduct = {
  name: '', sku: '', product_code: '', extra_product_codes: [], barcode: '',
  barcode_format: 'ean8',
  extra_barcodes: [],
  brand: '',
  category_id: '', unit: 'dona',
  cost_price: '', wholesale_price: '', sale_price: '',
  cost_price_cur: '', wholesale_price_cur: '', sale_price_cur: '',
  price_currency_id: '',
  initial_stock: '',
  initial_warehouse_id: '',
  min_stock: '', max_stock: '',
  bin_location: '',
  images: [],
  weight: '',
  dimensions: '',
  status: 'active',
  product_type: 'stock',
  variants: [],
  conversion_source_id: '',
  conversion_source_name: '',
  conversion_ratio: 1,
};

export const emptyBulkRow = () => ({
  _key: Math.random().toString(36).slice(2),
  name: '',
  sku: '',
  product_code: '',
  extra_product_codes: [],
  cost_price: '',
  cost_price_cur: '',
  wholesale_price: '',
  wholesale_price_cur: '',
  sale_price: '',
  sale_price_cur: '',
  barcodes: [genBarcodeByFormat('ean8')],
  unit: 'dona',
  barcode_status: null,
  barcode_product: null,
  barcode_scanned: false,
  category_id: '',
  initial_stock: '',
  min_stock: '',
  initial_warehouse_id: '',
  status: 'active',
});

export const emptyCategory = { name: '', parent_id: '', sort_order: 0, is_perishable: false };
export const emptyBinLoc = { code: '', label: '' };

/* ─── String helpers ───────────────────────────────── */
export const normalizeApos = (s) => s
  .replace(/[''ʼ`´ʹ]/g, "'")
  .replace(/'/g, "'");

/* ─── Import price field keys ──────────────────────── */
export const PRICE_FIELD_KEYS = ['Chakana narxi', 'Ulgurji narxi', 'Tan narxi'];

/* ─── CSS class constants ──────────────────────────── */
export const inputCls = "w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white";
export const errCls = "border-red-400 ring-1 ring-red-400";
