/**
 * BarcodeTemplates.jsx
 * 
 * Professional barcode label template printing system.
 * - 5 paper sizes: 30×20, 40×30, 50×30, 50×40, 60×40 mm
 * - Multiple style variants per size
 * - Template persistence via localStorage
 * - Live SVG barcode preview (JsBarcode CDN)
 * - Quantity selector + print window generation
 */

import { useState, useEffect, useRef, useCallback } from 'react';

/* ── Constants ───────────────────────────────── */
const LS_KEY = 'barcode_saved_templates';

const MM_TO_PX = 3.7795; // approximate, for screen preview only

function mmToPx(mm) {
  return Math.round(mm * MM_TO_PX);
}

/* ── Built-in template definitions ───────────── */
// Each template: { id, name, w, h, variant, description }
// variant determines JS render function
const BUILT_IN_TEMPLATES = [
  // ── 30×20 mm ──────────────────────────────────────────────
  {
    id: 'b-30x20-classic', size: '30×20', w: 30, h: 20,
    name: 'Klassik (30×20)',
    description: 'Barcode + narx, ixcham shelves uchun',
    variant: 'classic',
    show: { name: true, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'b-30x20-mini', size: '30×20', w: 30, h: 20,
    name: 'Mini (30×20)',
    description: 'Faqat barcode + narx raqami',
    variant: 'price-big',
    show: { name: false, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#1a1a1a' },
  },

  // ── 40×30 mm ──────────────────────────────────────────────
  {
    id: 'b-40x30-standard', size: '40×30', w: 40, h: 30,
    name: 'Standart (40×30)',
    description: 'Nomi + barcode + narx',
    variant: 'classic',
    show: { name: true, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'b-40x30-branded', size: '40×30', w: 40, h: 30,
    name: 'Brendli (40×30)',
    description: 'Brend + nomi + barcode + narx',
    variant: 'branded',
    show: { name: true, brand: true, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#4f46e5' },
  },
  {
    id: 'b-40x30-dark', size: '40×30', w: 40, h: 30,
    name: 'To\'q fon (40×30)',
    description: 'Qora fon, oq yozuv',
    variant: 'dark',
    show: { name: true, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#1a1a2e', text: '#fff', accent: '#e2e8f0' },
  },

  // ── 50×30 mm ──────────────────────────────────────────────
  {
    id: 'b-50x30-standard', size: '50×30', w: 50, h: 30,
    name: 'Standart (50×30)',
    description: 'Barcode + nomi + narx',
    variant: 'classic',
    show: { name: true, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'b-50x30-sku', size: '50×30', w: 50, h: 30,
    name: 'SKU bilan (50×30)',
    description: 'Nomi + SKU + barcode + narx',
    variant: 'with-sku',
    show: { name: true, brand: false, price: true, sku: true, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#6366f1' },
  },
  {
    id: 'b-50x30-price-tag', size: '50×30', w: 50, h: 30,
    name: 'Narx etiketi (50×30)',
    description: 'Katta narx + nomi + barcode',
    variant: 'price-big',
    show: { name: true, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#111', accent: '#dc2626' },
  },

  // ── 50×40 mm ──────────────────────────────────────────────
  {
    id: 'b-50x40-full', size: '50×40', w: 50, h: 40,
    name: 'To\'liq (50×40)',
    description: 'Brend + nomi + narx + SKU + barcode',
    variant: 'full',
    show: { name: true, brand: true, price: true, sku: true, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#4f46e5' },
  },
  {
    id: 'b-50x40-retail', size: '50×40', w: 50, h: 40,
    name: 'Retail (50×40)',
    description: 'Katta narx + barcode + sana',
    variant: 'retail',
    show: { name: true, brand: false, price: true, sku: false, barcode: true },
    colors: { bg: '#f8fafc', text: '#0f172a', accent: '#0369a1' },
  },

  // ── 60×40 mm ──────────────────────────────────────────────
  {
    id: 'b-60x40-premium', size: '60×40', w: 60, h: 40,
    name: 'Premium (60×40)',
    description: 'Brend + nomi + narx + barcode',
    variant: 'premium',
    show: { name: true, brand: true, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#7c3aed' },
  },
  {
    id: 'b-60x40-warehouse', size: '60×40', w: 60, h: 40,
    name: 'Ombor (60×40)',
    description: 'Katta barcode + nomi + SKU',
    variant: 'warehouse',
    show: { name: true, brand: false, price: false, sku: true, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'b-60x40-full', size: '60×40', w: 60, h: 40,
    name: 'To\'liq (60×40)',
    description: 'Hamma malumotlar + katta barcode',
    variant: 'full',
    show: { name: true, brand: true, price: true, sku: true, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#059669' },
  },
];

const SIZE_GROUPS = ['30×20', '40×30', '50×30', '50×40', '60×40'];

/* ── Generate HTML for a single label ──────── */
function buildLabelHTML(tpl, product, opts = {}) {
  const { fontSize = 8, date = '' } = opts;
  const { w, h, colors, show, variant } = tpl;
  const name = product.name || '';
  const brand = product.brand || '';
  const price = Number(product.sale_price || 0).toLocaleString('uz-UZ');
  const sku = product.sku || '';
  const barcode = product.barcode || '';

  const base = `
    width:${w}mm; height:${h}mm;
    background:${colors.bg}; color:${colors.text};
    display:inline-flex; flex-direction:column; align-items:center; justify-content:space-between;
    padding:1mm 1.5mm; box-sizing:border-box;
    border:0.3mm solid #ccc; page-break-inside:avoid; overflow:hidden;
    font-family:Arial,sans-serif;
  `;

  let inner = '';

  if (variant === 'warehouse') {
    inner = `
      ${show.name ? `<div style="font-size:${fontSize + 1}px;font-weight:700;text-align:center;word-break:break-word;width:100%">${name}</div>` : ''}
      ${show.sku ? `<div style="font-size:${fontSize - 1}px;color:#666">${sku}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%;max-height:${h * 0.6}mm"></svg>` : ''}
    `;
  } else if (variant === 'price-big') {
    inner = `
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:600;text-align:center;line-height:1.1;width:100%;overflow:hidden">${name}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 5}px;font-weight:900;color:${colors.accent};letter-spacing:-0.5px;line-height:1">${price}</div>
      <div style="font-size:${fontSize - 1}px;color:#999">so'm</div>` : ''}
    `;
  } else if (variant === 'dark') {
    inner = `
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:700;text-align:center;color:${colors.text};width:100%">${name}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%" data-linecolor="${colors.text}" data-fontcolor="${colors.text}"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 3}px;font-weight:900;color:${colors.accent}">${price} <span style="font-size:${fontSize - 1}px;font-weight:400">so'm</span></div>` : ''}
    `;
  } else if (variant === 'branded') {
    inner = `
      ${show.brand && brand ? `<div style="font-size:${fontSize - 1}px;font-weight:700;color:${colors.accent};text-transform:uppercase;letter-spacing:0.5px">${brand}</div>` : ''}
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:600;text-align:center;width:100%;overflow:hidden">${name}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 2}px;font-weight:800;color:${colors.accent}">${price} <span style="font-size:${fontSize - 1}px;font-weight:400;color:#666">so'm</span></div>` : ''}
    `;
  } else if (variant === 'with-sku') {
    inner = `
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:700;text-align:center;width:100%">${name}</div>` : ''}
      ${show.sku ? `<div style="font-size:${fontSize - 2}px;color:${colors.accent};font-family:monospace">${sku}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 2}px;font-weight:800">${price} <span style="font-size:${fontSize - 1}px;color:#777">so'm</span></div>` : ''}
    `;
  } else if (variant === 'full') {
    inner = `
      ${show.brand && brand ? `<div style="font-size:${fontSize - 1}px;font-weight:700;color:${colors.accent};text-transform:uppercase">${brand}</div>` : ''}
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:700;text-align:center;width:100%;line-height:1.2">${name}</div>` : ''}
      ${show.sku ? `<div style="font-size:${fontSize - 2}px;color:#999;font-family:monospace">${sku}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 3}px;font-weight:900;color:${colors.accent}">${price} <span style="font-size:${fontSize - 1}px;font-weight:400;color:#666">so'm</span></div>` : ''}
    `;
  } else if (variant === 'retail') {
    inner = `
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:600;text-align:center;width:100%">${name}</div>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 6}px;font-weight:900;color:${colors.accent};line-height:1">
        ${price}<span style="font-size:${fontSize}px;font-weight:500"> so'm</span>
      </div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${date ? `<div style="font-size:${fontSize - 2}px;color:#aaa">${date}</div>` : ''}
    `;
  } else if (variant === 'premium') {
    inner = `
      <div style="width:100%;border-bottom:0.5mm solid ${colors.accent};padding-bottom:0.5mm;margin-bottom:0.5mm">
        ${show.brand && brand ? `<div style="font-size:${fontSize - 1}px;font-weight:700;color:${colors.accent};text-transform:uppercase;letter-spacing:0.5px">${brand}</div>` : ''}
        ${show.name ? `<div style="font-size:${fontSize}px;font-weight:700;line-height:1.2">${name}</div>` : ''}
      </div>
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 4}px;font-weight:900;color:${colors.accent}">${price} <span style="font-size:${fontSize - 1}px;font-weight:400;color:#999">so'm</span></div>` : ''}
    `;
  } else {
    // classic
    inner = `
      ${show.name ? `<div style="font-size:${fontSize}px;font-weight:700;text-align:center;width:100%;line-height:1.2;overflow:hidden">${name}</div>` : ''}
      ${show.barcode ? `<svg class="bc" data-val="${barcode}" style="width:100%"></svg>` : ''}
      ${show.price ? `<div style="font-size:${fontSize + 2}px;font-weight:800">${price} <span style="font-size:${fontSize - 1}px;color:#777;font-weight:400">so'm</span></div>` : ''}
    `;
  }

  return `<div style="${base}">${inner}</div>`;
}

/* ── Barcode render helper (browser) ─────────── */
function renderBarcodes(container) {
  if (!window.JsBarcode) return;
  container.querySelectorAll('svg.bc').forEach(el => {
    const val = el.dataset.val;
    if (!val) return;
    const lineColor = el.dataset.linecolor || '#000';
    const fontColor = el.dataset.fontcolor || '#000';
    try {
      window.JsBarcode(el, val, {
        format: 'CODE128',
        width: 1.2,
        height: 28,
        displayValue: true,
        fontSize: 7,
        margin: 1,
        lineColor,
        fontOptions: '',
        font: 'Arial',
        textAlign: 'center',
        textPosition: 'bottom',
      });
    } catch (_) {
      el.innerHTML = `<text y="15" style="font-size:8px;fill:${lineColor}">${val}</text>`;
    }
  });
}

/* ── LabelPreview component ─────────────────── */
// Renders the label at actual mm size then scales to 'scale' factor.
// Uses a fixed-size outer div so it never overflows its container.
function LabelPreview({ tpl, product, scale = 1, fontSize = 8 }) {
  const ref = useRef(null);
  const wPx = mmToPx(tpl.w);
  const hPx = mmToPx(tpl.h);

  useEffect(() => {
    if (ref.current) renderBarcodes(ref.current);
  });

  const html = buildLabelHTML(tpl, product, { fontSize });

  return (
    // Outer div: reserves exactly the scaled pixel space
    <div style={{ width: wPx * scale, height: hPx * scale, flexShrink: 0, overflow: 'hidden', position: 'relative' }}>
      {/* Inner div: actual label at 1:1, then scaled up */}
      <div
        ref={ref}
        style={{
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          position: 'absolute',
          top: 0,
          left: 0,
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}

/* ── TemplateCard ────────────────────────────── */
function TemplateCard({ tpl, product, selected, onSelect, isSaved }) {
  const wPx = mmToPx(tpl.w);
  const hPx = mmToPx(tpl.h);
  const THUMB_W = 110;
  const scale = THUMB_W / wPx;
  const thumbH = Math.round(hPx * scale);

  return (
    <button
      onClick={() => onSelect(tpl)}
      className={`flex flex-col items-start gap-2 p-3 rounded-xl border-2 text-left transition-all w-full ${
        selected ? 'border-indigo-500 bg-indigo-50 shadow-md' : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50'
      }`}
    >
      {/* badge */}
      <div className="flex items-center gap-1.5 w-full">
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
          isSaved ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'
        }`}>
          {tpl.size} mm
        </span>
        {isSaved && <span className="text-xs text-amber-500">⭐ Saqlangan</span>}
        {selected && <span className="ml-auto text-indigo-600">✓</span>}
      </div>
      {/* name */}
      <div className="text-sm font-semibold text-slate-800">{tpl.name}</div>
      <div className="text-xs text-slate-400 leading-tight">{tpl.description}</div>

      {/* Thumbnail preview — fixed size, no overflow */}
      <div
        className="overflow-hidden rounded bg-white border border-slate-200"
        style={{ width: THUMB_W, height: thumbH }}
      >
        <LabelPreview tpl={tpl} product={product} scale={scale} fontSize={7} />
      </div>
    </button>
  );
}

/* ══════════════════════════════════════════════
   Main export: BarcodePrintModal
══════════════════════════════════════════════ */
export default function BarcodePrintModal({ product, onClose }) {
  const [sizeFilter, setSizeFilter] = useState('all');
  const [selectedTpl, setSelectedTpl] = useState(BUILT_IN_TEMPLATES[3]); // 50×30 default
  const [qty, setQty] = useState(1);
  const [fontSize, setFontSize] = useState(8);
  const [savedTemplates, setSavedTemplates] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch { return []; }
  });
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');

  // Load JsBarcode CDN
  useEffect(() => {
    if (window.JsBarcode) return;
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js';
    s.async = true;
    document.head.appendChild(s);
  }, []);

  const allTemplates = [...BUILT_IN_TEMPLATES, ...savedTemplates];
  const filteredTemplates = sizeFilter === 'all'
    ? allTemplates
    : allTemplates.filter(t => t.size === sizeFilter);

  /* Save current template customization */
  const handleSave = () => {
    if (!saveName.trim()) return;
    const newTpl = {
      ...selectedTpl,
      id: `saved-${Date.now()}`,
      name: saveName.trim(),
      description: `${selectedTpl.size} mm — saqlangan shablon`,
      _fontSize: fontSize,
    };
    const updated = [...savedTemplates, newTpl];
    setSavedTemplates(updated);
    localStorage.setItem(LS_KEY, JSON.stringify(updated));
    setSaveModalOpen(false);
    setSaveName('');
  };

  const handleDeleteSaved = (id) => {
    const updated = savedTemplates.filter(t => t.id !== id);
    setSavedTemplates(updated);
    localStorage.setItem(LS_KEY, JSON.stringify(updated));
  };

  /* Print — uses a hidden iframe so no new tab is opened */
  const handlePrint = () => {
    const singleLabel = buildLabelHTML(selectedTpl, product, { fontSize });
    const labels = Array(qty).fill(`<div class="lbl-wrap">${singleLabel}</div>`).join('');

    const iframeId = '__barcode_print_frame__';
    // Remove old frame if exists
    const old = document.getElementById(iframeId);
    if (old) old.remove();

    const iframe = document.createElement('iframe');
    iframe.id = iframeId;
    iframe.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;border:none;';
    document.body.appendChild(iframe);

    const doc = iframe.contentWindow.document;
    doc.open();
    doc.write(`<!DOCTYPE html>
<html><head><title>Chop: ${product.name}</title>
<script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></scr` + `ipt>
<style>
  @page { margin: 5mm; size: auto; }
  * { box-sizing: border-box; }
  body { font-family: Arial, sans-serif; display:flex; flex-wrap:wrap; gap:2mm; padding:2mm; margin:0; background:#fff; }
  .lbl-wrap { display:inline-block; }
</style>
</head>
<body>
${labels}
<script>
  window.onload = function() {
    document.querySelectorAll('svg.bc').forEach(function(el) {
      var v = el.dataset.val; if (!v) return;
      var lc = el.dataset.linecolor || '#000';
      try {
        JsBarcode(el, v, {format:'CODE128', width:1.2, height:28, displayValue:true, fontSize:7, margin:1, lineColor:lc});
      } catch(e) {}
    });
    setTimeout(function() {
      window.focus();
      window.print();
    }, 500);
  };
</scr` + `ipt>
</body></html>`);
    doc.close();
  };

  const isSavedTpl = (id) => savedTemplates.some(t => t.id === id);

  return (
    <div
      className="fixed inset-0 z-70 flex items-center justify-center p-3 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        style={{ width: '92vw', maxWidth: 1100, height: '92vh' }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
          <div>
            <h3 className="text-lg font-bold text-slate-800">Shtrix-kod shablonlari</h3>
            <p className="text-xs text-slate-400 mt-0.5 truncate max-w-sm">
              {product.name} · <span className="font-mono">{product.barcode}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSaveModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-semibold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-xl transition-colors"
              title="Tanlangan shablonni saqlash"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
              </svg>
              Saqlash
            </button>
            <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Body: 3 columns ── */}
        <div className="flex flex-1 overflow-hidden">

          {/* LEFT: Template selector */}
          <div className="w-72 shrink-0 border-r border-slate-100 flex flex-col overflow-hidden">
            {/* Size filter */}
            <div className="p-3 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase mb-2">O'lcham</div>
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setSizeFilter('all')}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                    sizeFilter === 'all' ? 'bg-indigo-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >Barchasi</button>
                {SIZE_GROUPS.map(s => (
                  <button key={s}
                    onClick={() => setSizeFilter(s)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                      sizeFilter === s ? 'bg-indigo-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >{s}</button>
                ))}
              </div>
            </div>

            {/* Template list */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {filteredTemplates.map(tpl => (
                <div key={tpl.id} className="relative">
                  <TemplateCard
                    tpl={tpl}
                    product={product}
                    selected={selectedTpl?.id === tpl.id}
                    onSelect={setSelectedTpl}
                    isSaved={isSavedTpl(tpl.id)}
                  />
                  {isSavedTpl(tpl.id) && (
                    <button
                      onClick={() => handleDeleteSaved(tpl.id)}
                      className="absolute top-2 right-2 w-5 h-5 flex items-center justify-center bg-red-100 hover:bg-red-200 text-red-500 rounded-full text-xs transition-colors"
                      title="O'chirish"
                    >×</button>
                  )}
                </div>
              ))}
              {filteredTemplates.length === 0 && (
                <div className="text-center py-8 text-slate-400 text-xs">Shablon topilmadi</div>
              )}
            </div>
          </div>

          {/* CENTER: Preview */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Ko'rinish</div>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-slate-50 flex items-start justify-center">
              {selectedTpl ? (
                <div className="flex flex-col items-center gap-5 py-4">
                  {/* Main preview — label at 3× */}
                  <div>
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 text-center">Katta ko'rinish</div>
                    <div className="bg-white shadow-md rounded-xl p-5 inline-flex items-center justify-center">
                      <LabelPreview tpl={selectedTpl} product={product} scale={3} fontSize={fontSize} />
                    </div>
                    <div className="text-xs text-slate-400 mt-2 text-center">
                      {selectedTpl.w}×{selectedTpl.h} mm · {selectedTpl.name}
                    </div>
                  </div>

                  {/* Chop preview — 4 labels at 1.5× */}
                  <div className="w-full">
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 text-center">Chop ko'rinishi (4 ta)</div>
                    <div className="bg-white rounded-xl p-4 shadow-sm border border-dashed border-slate-200 flex flex-wrap gap-3 justify-center">
                      {[0, 1, 2, 3].map(i => (
                        <LabelPreview key={i} tpl={selectedTpl} product={product} scale={1.5} fontSize={fontSize} />
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-slate-400 text-sm mt-12">Shablon tanlang</div>
              )}
            </div>
          </div>

          {/* RIGHT: Controls */}
          <div className="w-56 shrink-0 border-l border-slate-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Sozlamalar</div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-5">

              {/* Font size */}
              <div>
                <div className="text-xs font-semibold text-slate-600 mb-2">Shrift: {fontSize}px</div>
                <input type="range" min="6" max="12" value={fontSize}
                  onChange={e => setFontSize(+e.target.value)}
                  className="w-full accent-indigo-500" />
                <div className="flex justify-between text-xs text-slate-400 mt-0.5">
                  <span>6</span><span>12</span>
                </div>
              </div>

              {/* Quantity */}
              <div>
                <div className="text-xs font-semibold text-slate-600 mb-2">Nusxalar soni</div>
                <div className="flex items-center gap-2">
                  <button onClick={() => setQty(q => Math.max(1, q - 1))}
                    className="w-8 h-8 bg-slate-100 hover:bg-slate-200 rounded-lg font-bold text-slate-700 flex items-center justify-center">−</button>
                  <input
                    type="number" min="1" max="500" value={qty}
                    onChange={e => setQty(Math.max(1, Math.min(500, +e.target.value)))}
                    className="flex-1 text-center border border-slate-200 rounded-lg py-1.5 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <button onClick={() => setQty(q => Math.min(500, q + 1))}
                    className="w-8 h-8 bg-slate-100 hover:bg-slate-200 rounded-lg font-bold text-slate-700 flex items-center justify-center">+</button>
                </div>
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {[1, 5, 10, 20, 50, 100].map(n => (
                    <button key={n} onClick={() => setQty(n)}
                      className={`px-2 py-0.5 rounded text-xs font-semibold border transition-colors ${
                        qty === n ? 'border-indigo-500 bg-indigo-50 text-indigo-600' : 'border-slate-200 text-slate-500 hover:border-indigo-300'
                      }`}>{n}</button>
                  ))}
                </div>
              </div>

              {/* Template info */}
              {selectedTpl && (
                <div className="p-3 bg-slate-50 rounded-xl space-y-1 text-xs text-slate-600">
                  <div className="font-semibold text-slate-700">{selectedTpl.name}</div>
                  <div>{selectedTpl.w}×{selectedTpl.h} mm</div>
                  <div className="text-slate-400">{selectedTpl.description}</div>
                </div>
              )}
            </div>

            {/* Print button */}
            <div className="p-4 border-t border-slate-100 space-y-2 shrink-0">
              <button
                onClick={handlePrint}
                disabled={!selectedTpl}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                    d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                </svg>
                {qty} ta chop et
              </button>
              <button onClick={onClose}
                className="w-full py-2 border border-slate-200 text-slate-600 font-semibold text-sm rounded-xl hover:bg-slate-50 transition-colors">
                Yopish
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Save Template Modal ── */}
      {saveModalOpen && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/40">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm">
            <h4 className="text-base font-bold text-slate-800 mb-1">Shablonni saqlash</h4>
            <p className="text-xs text-slate-400 mb-4">"{selectedTpl?.name}" asosida yangi shablon</p>
            <input
              autoFocus
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-4"
              placeholder="Shablon nomi..."
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
            />
            <div className="flex gap-3">
              <button onClick={() => setSaveModalOpen(false)}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-semibold rounded-xl hover:bg-slate-50">Bekor</button>
              <button onClick={handleSave} disabled={!saveName.trim()}
                className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold rounded-xl transition-colors">
                ⭐ Saqlash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
