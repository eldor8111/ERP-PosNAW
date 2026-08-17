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

import { useState, useEffect, useRef } from 'react';
import api from '../api/axios';

const LS_KEY = 'barcode_saved_templates';

const MM_TO_PX = 3.7795;

function mmToPx(mm) {
  return Math.round(mm * MM_TO_PX);
}

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

  // ── 60×30 mm ──────────────────────────────────────────────
  {
    id: 'b-60x30-premium', size: '60×30', w: 60, h: 30,
    name: 'Premium (60×30)',
    description: 'Brend + nomi + narx + barcode',
    variant: 'premium',
    show: { name: true, brand: true, price: true, sku: false, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#7c3aed' },
  },
  {
    id: 'b-60x30-warehouse', size: '60×30', w: 60, h: 30,
    name: 'Ombor (60×30)',
    description: 'Katta barcode + nomi + SKU',
    variant: 'warehouse',
    show: { name: true, brand: false, price: false, sku: true, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'b-60x30-full', size: '60×30', w: 60, h: 30,
    name: 'To\'liq (60×30)',
    description: 'Hamma malumotlar + katta barcode',
    variant: 'full',
    show: { name: true, brand: true, price: true, sku: true, barcode: true },
    colors: { bg: '#fff', text: '#000', accent: '#059669' },
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

const SIZE_GROUPS = ['30×20', '40×30', '50×30', '50×40', '60×30', '60×40'];

function buildLabelHTML(tpl, product, opts = {}) {
  const { w, h, colors } = tpl;

  // Extract option states or default fallback options
  const showCompanyName = opts.showCompanyName !== undefined ? opts.showCompanyName : true;
  const showProductName = opts.showProductName !== undefined ? opts.showProductName : true;
  const showPrice = opts.showPrice !== undefined ? opts.showPrice : true;
  const showBarcode = opts.showBarcode !== undefined ? opts.showBarcode : true;
  const showSku = opts.showSku !== undefined ? opts.showSku : true;
  const showCode = opts.showCode !== undefined ? opts.showCode : true;
  const showDate = opts.showDate !== undefined ? opts.showDate : true;

  const companyNamePos = opts.companyNamePos || 'up';
  const productNamePos = opts.productNamePos || 'up';
  const productPricePos = opts.productPricePos || 'down';
  const productSkuPos = opts.productSkuPos || 'up';
  const productCodePos = opts.productCodePos || 'up';

  const companyNameSize = opts.fontSize || 8;
  const productNameSize = opts.productNameSize || 8;
  const productPriceSize = opts.productPriceSize || 8;
  const productCurrencySize = opts.productCurrencySize || 6;
  const productSkuSize = opts.productSkuSize || 6;
  const productCodeSize = opts.productCodeSize || 6;
  const barcodeSize = opts.barcodeSize || 10;
  const dateVal = opts.date || '';

  // Get and convert pricing
  const currencies = opts.currencies || [];
  const selectedCurrencyCode = (opts.currencyVal || product.sale_currency || "UZS").toUpperCase();
  const productCurrencyCode = (product.sale_currency || "UZS").toUpperCase();

  const origCur = currencies.find(c => c.code?.toUpperCase() === productCurrencyCode);
  const origRate = origCur ? Number(origCur.rate) : 1;

  const targetCur = currencies.find(c => c.code?.toUpperCase() === selectedCurrencyCode);
  const targetRate = targetCur ? Number(targetCur.rate) : 1;

  const priceInBase = Number(product.sale_price || 0) * (origRate || 1);
  const convertedPriceValue = priceInBase / (targetRate || 1);

  // Format currency display:
  const currencyDisp = selectedCurrencyCode === 'UZS' ? "" : selectedCurrencyCode;

  // If the converted value is a positive fraction under 0.1, we increase decimal precision up to 5 digits so it won't display as 0.
  const maxDigits = (convertedPriceValue > 0 && convertedPriceValue < 0.1) ? 5 : 2;

  const price = Number(convertedPriceValue).toLocaleString('uz-UZ', {
    minimumFractionDigits: 0,
    maximumFractionDigits: maxDigits
  });

  const name = product.name || '';
  const sku = product.sku || '';
  const productCode = product.product_code || '';
  const barcode = product.barcode || '';
  const companyNameText = opts.companyName || '';

  const base = `
    width:${w}mm; height:${h}mm;
    background:${colors.bg || '#fff'}; color:${colors.text || '#000'};
    display:inline-flex; flex-direction:column; align-items:center; justify-content:space-between;
    padding:1mm 1.5mm; box-sizing:border-box;
    border:0.3mm solid #ccc; page-break-inside:avoid; overflow:hidden;
    font-family:Arial,sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact;
  `;

  // Dynamic content building blocks
  const companyHtml = (showCompanyName && companyNameText)
    ? `<div style="font-size:${companyNameSize}px; font-weight:700; text-align:center; word-break:break-word; width:100%; line-height:1.1;">${companyNameText}</div>`
    : '';

  const productNameHtml = showProductName
    ? `<div style="font-size:${productNameSize}px; font-weight:700; text-align:center; line-height:1.2; width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${name}</div>`
    : '';

  const priceHtml = showPrice
    ? `<div style="font-size:${productPriceSize}px; font-weight:900; color:${colors.accent || colors.text || '#000'}; display:inline-flex; align-items:baseline; justify-content:center; width:100%;">
         ${price}
         <span style="font-size:${productCurrencySize}px; font-weight:500; color:#666; margin-left:1.5px; opacity:0.85;">${currencyDisp}</span>
       </div>`
    : '';

  const skuHtml = (showSku && sku)
    ? `<div style="font-size:${productSkuSize}px; color:#555; font-family:monospace; text-align:center; width:100%; line-height:1.1;">${sku}</div>`
    : '';

  const codeHtml = (showCode && productCode)
    ? `<div style="font-size:${productCodeSize}px; color:#000; font-family:monospace; text-align:center; width:100%; line-height:1.1;">${productCode}</div>`
    : '';

  const dateHtml = (showDate && dateVal)
    ? `<div style="font-size:6px; color:#888; text-align:center; width:100%; line-height:1;">${dateVal}</div>`
    : '';

  const barcodeHtml = (showBarcode && barcode)
    ? `<svg class="bc" data-val="${barcode}" data-linecolor="${colors.text || '#000'}" data-height="${barcodeSize * 2.4}" data-fontsize="${barcodeSize * 0.7}" data-barwidth="${(barcodeSize * 0.1).toFixed(2)}" style="width:100%; max-height:${h * 0.55}mm; margin:0.5mm 0;"></svg>`
    : '';

  const upElements = [];
  const downElements = [];

  // Detect if code is the ONLY visible element (auto-center)
  const otherHtmlPresent = companyHtml || productNameHtml || skuHtml || priceHtml || dateHtml || barcodeHtml;
  const codeIsAlone = codeHtml && !otherHtmlPresent;
  const codeIsCenter = productCodePos === 'middle' || codeIsAlone;

  if (companyHtml) {
    if (companyNamePos === 'up') upElements.push(companyHtml);
    else downElements.push(companyHtml);
  }

  if (productNameHtml) {
    if (productNamePos === 'up') upElements.push(productNameHtml);
    else downElements.push(productNameHtml);
  }

  if (skuHtml) {
    if (productSkuPos === 'up') upElements.push(skuHtml);
    else downElements.push(skuHtml);
  }

  if (codeHtml && !codeIsCenter) {
    if (productCodePos === 'up') upElements.push(codeHtml);
    else downElements.push(codeHtml);
  }

  if (priceHtml) {
    if (productPricePos === 'up') upElements.push(priceHtml);
    else downElements.push(priceHtml);
  }

  if (dateHtml) {
    downElements.push(dateHtml);
  }

  // Center code element (shown between up/barcode/down sections)
  const centerCodeHtml = codeIsCenter
    ? `<div style="flex:1; width:100%; display:flex; align-items:center; justify-content:center;">${codeHtml}</div>`
    : '';

  const inner = `
    <div style="width:100%; display:flex; flex-direction:column; align-items:center; gap:0.4mm; overflow:hidden;">
      ${upElements.join('')}
    </div>
    ${centerCodeHtml}
    ${barcodeHtml}
    <div style="width:100%; display:flex; flex-direction:column; align-items:center; gap:0.4mm; overflow:hidden;">
      ${downElements.join('')}
    </div>
  `;

  return `<div style="${base}">${inner}</div>`;
}

/* ── Barcode render helper (browser) ─────────── */
function renderBarcodes(container) {
  if (!window.JsBarcode) return;
  container.querySelectorAll('svg.bc').forEach(el => {
    const val = el.dataset.val;
    if (!val) return;
    const lineColor = el.dataset.linecolor || '#000';
    const bh = Number(el.dataset.height || 28);
    const fs = Number(el.dataset.fontsize || 7);
    const bw = Number(el.dataset.barwidth || 1.1);
    try {
      window.JsBarcode(el, val, {
        format: 'CODE128',
        width: bw,
        height: bh,
        displayValue: true,
        fontSize: fs,
        margin: 1,
        lineColor,
        fontOptions: '',
        font: 'Arial',
        textAlign: 'center',
        textPosition: 'bottom',
      });
    } catch {
      el.innerHTML = `<text y="15" style="font-size:8px;fill:${lineColor}">${val}</text>`;
    }
  });
}

/* ── LabelPreview component ─────────────────── */
// Renders the label at actual mm size then scales to 'scale' factor.
// Uses a fixed-size outer div so it never overflows its container.
function LabelPreview({ tpl, product, scale = 1, options = {} }) {
  const ref = useRef(null);
  const wPx = mmToPx(tpl.w);
  const hPx = mmToPx(tpl.h);

  useEffect(() => {
    if (ref.current) renderBarcodes(ref.current);
  });

  const html = buildLabelHTML(tpl, product, options);

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
      className={`flex flex-col items-start gap-2 p-3 rounded-xl border-2 text-left transition-all w-full ${selected ? 'border-blue-500 bg-blue-50 shadow-md' : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
        }`}
    >
      {/* badge */}
      <div className="flex items-center gap-1.5 w-full">
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${isSaved ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'
          }`}>
          {tpl.size} mm
        </span>
        {isSaved && <span className="text-xs text-amber-500">⭐ Saqlangan</span>}
        {selected && <span className="ml-auto text-blue-600">✓</span>}
      </div>
      {/* name */}
      <div className="text-sm font-semibold text-slate-800">{tpl.name}</div>
      <div className="text-xs text-slate-400 leading-tight">{tpl.description}</div>

      {/* Thumbnail preview — fixed size, no overflow */}
      <div
        className="overflow-hidden rounded bg-white border border-slate-200"
        style={{ width: THUMB_W, height: thumbH }}
      >
        <LabelPreview tpl={tpl} product={product} scale={scale} options={{ fontSize: 7 }} />
      </div>
    </button>
  );
}

/* ══════════════════════════════════════════════
   Main export: BarcodePrintModal
══════════════════════════════════════════════ */
export default function BarcodePrintModal({ product, onClose }) {
  const [selectedTpl, setSelectedTpl] = useState(BUILT_IN_TEMPLATES[3]); // 50×30 default
  const [qty, setQty] = useState(1);

  const [fontSize, setFontSize] = useState(8);
  const [productNameSize, setProductNameSize] = useState(8);
  const [productPriceSize, setProductPriceSize] = useState(8);
  const [productCurrencySize, setProductCurrencySize] = useState(6);
  const [productSkuSize, setProductSkuSize] = useState(6);
  const [productCodeSize, setProductCodeSize] = useState(6);
  const [barcodeSize, setBarcodeSize] = useState(10);

  const [companyName, setCompanyName] = useState("");

  const [savedTemplates, setSavedTemplates] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch { return []; }
  });
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [currencies, setCurrencies] = useState([]);
  const [currencyVal, setCurrencyVal] = useState(() => (product.sale_currency || "UZS").toUpperCase());

  const [showCompanyName, setShowCompanyName] = useState(true);
  const [showProductName, setShowProductName] = useState(true);
  const [showPrice, setShowPrice] = useState(true);
  const [showBarcode, setShowBarcode] = useState(true);
  const [showSku, setShowSku] = useState(true);
  const [showCode, setShowCode] = useState(true);
  const [showDate, setShowDate] = useState(true);

  const [companyNamePos, setCompanyNamePos] = useState("up");
  const [productNamePos, setProductNamePos] = useState("up");
  const [productPricePos, setProductPricePos] = useState("down");
  const [productSkuPos, setProductSkuPos] = useState("up");
  const [productCodePos, setProductCodePos] = useState("up");

  // Load JsBarcode CDN
  useEffect(() => {
    api.get('/currencies').then(res => {
      setCurrencies(res.data);
      // Ensure the initial product sale currency exists in currency list, otherwise default.
      const hasOriginal = res.data.some(c => c.code?.toUpperCase() === (product.sale_currency || "UZS").toUpperCase());
      if (!hasOriginal && res.data.length > 0) {
        // Find default or first currency
        const defCur = res.data.find(c => c.is_default) || res.data[0];
        setCurrencyVal(defCur.code.toUpperCase());
      }
    });

    if (window.JsBarcode) return;
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js';
    s.async = true;
    document.head.appendChild(s);
  }, [product.sale_currency]);

  const previewOptions = {
    companyName,
    currencyVal,
    currencies,
    fontSize,
    productNameSize,
    productPriceSize,
    productCurrencySize,
    barcodeSize,
    productSkuSize,
    productCodeSize,
    showCompanyName,
    showProductName,
    showPrice,
    showBarcode,
    showSku,
    showCode,
    showDate,
    companyNamePos,
    productNamePos,
    productPricePos,
    productSkuPos,
    productCodePos,
    date: new Date().toLocaleDateString('uz-UZ'),
  };

  /* Save current template customization — persists ALL settings */
  const handleSave = () => {
    if (!saveName.trim()) return;
    const newTpl = {
      ...selectedTpl,
      id: `saved-${Date.now()}`,
      name: saveName.trim(),
      description: `${selectedTpl.size} mm — saqlangan shablon`,
      // persist all customisation options
      _opts: {
        fontSize,
        productNameSize,
        productPriceSize,
        productCurrencySize,
        productSkuSize,
        productCodeSize,
        barcodeSize,
        companyName,
        currencyVal,
        showCompanyName,
        showProductName,
        showPrice,
        showBarcode,
        showSku,
        showCode,
        showDate,
        companyNamePos,
        productNamePos,
        productPricePos,
        productSkuPos,
        productCodePos,
      },
    };
    const updated = [...savedTemplates, newTpl];
    setSavedTemplates(updated);
    localStorage.setItem(LS_KEY, JSON.stringify(updated));
    setSaveModalOpen(false);
    setSaveName('');
  };

  /* Delete a saved template by id */
  const handleDeleteSaved = (id, e) => {
    e.stopPropagation();
    const updated = savedTemplates.filter(t => t.id !== id);
    setSavedTemplates(updated);
    localStorage.setItem(LS_KEY, JSON.stringify(updated));
  };

  /* Load a saved template — restore ALL its settings */
  const handleLoadSaved = (id) => {
    const tpl = savedTemplates.find(t => t.id === id);
    if (!tpl) return;
    setSelectedTpl(tpl);
    const o = tpl._opts || {};
    if (o.fontSize !== undefined) setFontSize(o.fontSize);
    if (o.productNameSize !== undefined) setProductNameSize(o.productNameSize);
    if (o.productPriceSize !== undefined) setProductPriceSize(o.productPriceSize);
    if (o.productCurrencySize !== undefined) setProductCurrencySize(o.productCurrencySize);
    if (o.productSkuSize !== undefined) setProductSkuSize(o.productSkuSize);
    if (o.productCodeSize !== undefined) setProductCodeSize(o.productCodeSize);
    if (o.barcodeSize !== undefined) setBarcodeSize(o.barcodeSize);
    if (o.companyName !== undefined) setCompanyName(o.companyName);
    if (o.currencyVal !== undefined) setCurrencyVal(o.currencyVal);
    if (o.showCompanyName !== undefined) setShowCompanyName(o.showCompanyName);
    if (o.showProductName !== undefined) setShowProductName(o.showProductName);
    if (o.showPrice !== undefined) setShowPrice(o.showPrice);
    if (o.showBarcode !== undefined) setShowBarcode(o.showBarcode);
    if (o.showSku !== undefined) setShowSku(o.showSku);
    if (o.showCode !== undefined) setShowCode(o.showCode);
    if (o.showDate !== undefined) setShowDate(o.showDate);
    if (o.companyNamePos !== undefined) setCompanyNamePos(o.companyNamePos);
    if (o.productNamePos !== undefined) setProductNamePos(o.productNamePos);
    if (o.productPricePos !== undefined) setProductPricePos(o.productPricePos);
    if (o.productSkuPos !== undefined) setProductSkuPos(o.productSkuPos);
    if (o.productCodePos !== undefined) setProductCodePos(o.productCodePos);
  };

  /* Print — uses a hidden iframe so no new tab is opened */
  const handlePrint = () => {
    const { w, h } = selectedTpl;
    const singleLabel = buildLabelHTML(selectedTpl, product, previewOptions);
    const labelItems = Array.from({ length: qty }, (_, i) =>
      `<div class="lbl-wrap${i < qty - 1 ? ' page-break' : ''}">${singleLabel}</div>`
    ).join('');

    const iframeId = '__barcode_print_frame__';
    const old = document.getElementById(iframeId);
    if (old) old.remove();

    const iframe = document.createElement('iframe');
    iframe.id = iframeId;
    iframe.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;border:none;';
    document.body.appendChild(iframe);

    const doc = iframe.contentWindow.document;
    doc.open();
    doc.write(`
      <!DOCTYPE html>
        <html>
          <head><title>Chop: ${product.name}</title>
            <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></scr` + `ipt>
            <style>
              @page {
                margin: 0;
                size: ${w}mm ${h}mm;
              }
              * { box-sizing: border-box; }
              body {
                margin: 0;
                padding: 0;
                background: #fff;
                font-family: Arial, sans-serif;
              }
              .lbl-wrap {
                display: block;
                width: ${w}mm;
                height: ${h}mm;
                overflow: hidden;
              }
              .lbl-wrap > div {
                border: none !important;
              }
              .page-break {
                page-break-after: always;
              }
            </style>
          </head>
          <body>
            ${labelItems}
            <script>
              window.onload = function() {
                document.querySelectorAll('svg.bc').forEach(function(el) {
                  var v = el.dataset.val; if (!v) return;
                  var lc = el.dataset.linecolor || '#000';
                  var bh = Number(el.dataset.height || 28);
                  var fs = Number(el.dataset.fontsize || 7);
                  try {
                    JsBarcode(el, v, {
                      format: 'CODE128',
                      width: 1.1,
                      height: bh,
                      displayValue: true,
                      fontSize: fs,
                      margin: 1,
                      lineColor: lc,
                      fontOptions: '',
                      font: 'Arial',
                      textAlign: 'center',
                      textPosition: 'bottom'
                    });
                  } catch(e) {}
                });
                setTimeout(function() {
                  window.focus();
                  window.print();
                }, 500);
              };
            </script>
          </body>
        </html>`);
    doc.close();
  };

  return (
    <div
      className="fixed inset-0 z-70 flex items-center w-full h-full justify-center"
    >
      <div
        className="bg-white flex flex-col overflow-hidden"
        style={{ width: '100%', maxWidth: '100%', height: '100%' }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-100 shrink-0">
          <div>
            <h3 className="text-lg font-bold text-slate-800">Shtrix-kod</h3>
            <p className="text-xs text-slate-400 truncate max-w-sm">
              {product.name} · <span className="font-mono">{product.barcode}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">

            {/* ── Saved templates selector ── */}
            {savedTemplates.length > 0 && (
              <div className="relative flex items-center gap-1 bg-amber-50 border border-amber-200 rounded-xl px-1 py-1">
                <svg className="w-4 h-4 text-amber-500 ml-1 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                <div className="relative">
                  <select
                    defaultValue=""
                    onChange={e => { if (e.target.value) handleLoadSaved(e.target.value); e.target.value = ''; }}
                    className="pl-2 pr-6 py-1.5 text-sm font-semibold text-amber-700 bg-transparent border-0 outline-none cursor-pointer appearance-none"
                    title="Saqlangan shablonni yuklash"
                  >
                    <option value="" disabled>Saqlangan shablonlar</option>
                    {savedTemplates.map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                  <svg className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
                {/* Per-option delete buttons rendered as a floating panel — handled inline via select onChange; individual deletes shown below */}
              </div>
            )}

            {/* Saved templates delete list (compact chips) */}
            {savedTemplates.length > 0 && (
              <div className="flex flex-wrap gap-1 max-w-xs">
                {savedTemplates.map(t => (
                  <span
                    key={t.id}
                    className="inline-flex items-center gap-1 text-xs font-medium bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5 rounded-full"
                  >
                    <button
                      type="button"
                      onClick={() => handleLoadSaved(t.id)}
                      className="hover:underline max-w-[90px] truncate cursor-pointer"
                      title={`"${t.name}" shablonini yuklash`}
                    >
                      {t.name}
                    </button>
                    <button
                      type="button"
                      onClick={e => handleDeleteSaved(t.id, e)}
                      className="ml-0.5 text-amber-400 hover:text-red-500 transition-colors cursor-pointer leading-none"
                      title="O'chirish"
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}

            <button
              onClick={() => setSaveModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-semibold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-xl transition-colors border border-amber-200"
              title="Joriy sozlamalarni shablon sifatida saqlash"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
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
          {/* LEFT: Settings */}
          <div className="min-w-70 max-w-170 w-full border-r border-slate-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Sozlamalar</div>
            </div>
            <div className='overflow-y-auto pb-10'>
              <div className="px-3 py-1 mt-2 shrink-0">
                <div className="text-xs font-semibold text-slate-500 uppercase mb-1">O'lcham</div>
                <div className="flex flex-wrap gap-1.5">
                  <select
                    value={selectedTpl?.size || '50×30'}
                    onChange={(e) => {
                      const selectedSize = e.target.value;
                      const found = BUILT_IN_TEMPLATES.find(t => t.size === selectedSize);
                      if (found) {
                        setSelectedTpl(found);
                      } else {
                        const [w, h] = selectedSize.split('×').map(Number);
                        setSelectedTpl({
                          id: `custom-${selectedSize}`,
                          name: selectedSize,
                          size: selectedSize,
                          w,
                          h,
                          colors: { bg: '#fff', text: '#000', accent: '#000' }
                        });
                      }
                    }}
                    className="px-4 py-3 w-full rounded-lg text-sm font-semibold transition-colors cursor-pointer border border-slate-300 outline-0"
                  >
                    {SIZE_GROUPS.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="px-3 py-2 shrink-0">
                <div className="text-xs font-semibold text-slate-500 uppercase mb-1">Valyuta</div>
                <div className="flex flex-wrap gap-1.5">
                  <select
                    value={currencyVal}
                    onChange={(e) => setCurrencyVal(e.target.value)}
                    className="px-4 py-3 w-full rounded-lg text-sm font-semibold transition-colors cursor-pointer border border-slate-300 outline-0"
                  >
                    {currencies.map(s => (
                      <option key={s.id || s.code || String(s)} value={s.code || s}>{s.code || s}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="px-3 py-2 border-b border-slate-100 shrink-0">
                <div className="text-xs font-semibold text-slate-500 uppercase mb-1">Korxona nomi</div>
                <div className="">
                  <input
                    type="text"
                    placeholder="Korxona nomi"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    className="px-4 py-3 w-full rounded-lg text-sm transition-colors border border-slate-300 outline-0"
                  />
                </div>
              </div>

              <div className="p-4 flex flex-col gap-3">
                {/* Korxona nomi */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Korxona nomi: {fontSize}px</div>
                  <input
                    type="range"
                    min="6"
                    max="22"
                    value={fontSize}
                    onChange={e => setFontSize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>6</span><span>22</span>
                  </div>
                </div>

                {/* Maxsulot nomi */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Maxsulot nomi: {productNameSize}px</div>
                  <input
                    type="range"
                    min="6"
                    max="30"
                    value={productNameSize}
                    onChange={e => setProductNameSize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>6</span><span>30</span>
                  </div>
                </div>

                {/* Kod */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Mahsulot kodi: {productCodeSize}px</div>
                  <input
                    type="range"
                    min="6"
                    max="65"
                    value={productCodeSize}
                    onChange={e => setProductCodeSize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>6</span><span>65</span>
                  </div>
                </div>

                {/* Narxi */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Narxi: {productPriceSize}px</div>
                  <input
                    type="range"
                    min="6"
                    max="65"
                    value={productPriceSize}
                    onChange={e => setProductPriceSize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>6</span><span>65</span>
                  </div>
                </div>

                {/* Valyuta */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Valyuta: {productCurrencySize}px</div>
                  <input
                    type="range"
                    min="4"
                    max="22"
                    value={productCurrencySize}
                    onChange={e => setProductCurrencySize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>4</span><span>22</span>
                  </div>
                </div>

                {/* Shtrix */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Shtrix: {barcodeSize}px</div>
                  <input
                    type="range"
                    min="10"
                    max="30"
                    value={barcodeSize}
                    onChange={e => setBarcodeSize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>10</span><span>30</span>
                  </div>
                </div>

                {/* Artikul */}
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Artikul: {productSkuSize}px</div>
                  <input
                    type="range"
                    min="6"
                    max="30"
                    value={productSkuSize}
                    onChange={e => setProductSkuSize(+e.target.value)}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>6</span><span>30</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* CENTER: Preview */}
          <div className="flex-1 min-w-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Ko'rinish</div>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-slate-50 flex items-start justify-center">
              {selectedTpl ? (
                <div className="flex">
                  <div>
                    <div className="bg-white shadow-md inline-flex items-center justify-center">
                      <LabelPreview tpl={selectedTpl} product={product} scale={2} options={previewOptions} />
                    </div>
                    <div className="text-xs text-slate-400 mt-2 text-center">
                      {selectedTpl.w}×{selectedTpl.h} mm · {selectedTpl.name}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-slate-400 text-sm mt-12">Shablon tanlang</div>
              )}
            </div>
          </div>

          {/* RIGHT: Controls */}
          <div className="max-w-90 min-w-80 w-full border-l border-slate-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Sozlamalar</div>
            </div>
            <div className="flex-1 flex flex-col overflow-y-auto">
              <div className="space-y-5 border-b p-4 border-b-slate-100">
                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showCompanyName}
                      onChange={e => setShowCompanyName(e.target.checked)}
                      id="switch-show-company"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-company" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Korxona nomini ko'rsatish</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showProductName}
                      onChange={e => setShowProductName(e.target.checked)}
                      id="switch-show-product-name"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-product-name" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Mahsulot nomini ko'rsatish</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showPrice}
                      onChange={e => setShowPrice(e.target.checked)}
                      id="switch-show-price"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-price" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Mahsulot narxini ko'rsatish</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showBarcode}
                      onChange={e => setShowBarcode(e.target.checked)}
                      id="switch-show-barcode"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-barcode" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Shtrix kodni ko'rsatish</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showSku}
                      onChange={e => setShowSku(e.target.checked)}
                      id="switch-show-sku"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-sku" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Mahsulot artikulini ko'rsatish</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showCode}
                      onChange={e => setShowCode(e.target.checked)}
                      id="switch-show-code"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-code" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Mahsulot kodini ko'rsatish</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative inline-block w-11 h-5">
                    <input
                      checked={showDate}
                      onChange={e => setShowDate(e.target.checked)}
                      id="switch-show-date"
                      type="checkbox"
                      className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                    />
                    <label htmlFor="switch-show-date" className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer">
                    </label>
                  </div>
                  <span>Sanani ko'rsatish</span>
                </div>
              </div>

              <div className="flex flex-col gap-4 p-4 border-b border-b-slate-100">
                <div className="flex justify-between items-center">
                  <span>Mahsulot nomi:</span>
                  <select
                    value={productNamePos}
                    onChange={e => setProductNamePos(e.target.value)}
                    className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded"
                  >
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>

                <div className="flex justify-between items-center">
                  <span>Mahsulot narxi:</span>
                  <select
                    value={productPricePos}
                    onChange={e => setProductPricePos(e.target.value)}
                    className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded"
                  >
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>

                <div className="flex justify-between items-center">
                  <span>Korxona nomi:</span>
                  <select
                    value={companyNamePos}
                    onChange={e => setCompanyNamePos(e.target.value)}
                    className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded"
                  >
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>

                <div className="flex justify-between items-center">
                  <span>Artikul:</span>
                  <select
                    value={productSkuPos}
                    onChange={e => setProductSkuPos(e.target.value)}
                    className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded"
                  >
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>

                <div className="flex justify-between items-center">
                  <span>Mahsulot kodi:</span>
                  <select
                    value={productCodePos}
                    onChange={e => setProductCodePos(e.target.value)}
                    className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded"
                  >
                    <option value="up">tepada</option>
                    <option value="middle">o'rtada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Print button */}
            <div className="p-4 border-t border-slate-100 space-y-2 shrink-0">
              {/* Quantity */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setQty(q => Math.max(1, q - 1))}
                  className="w-10 h-10 bg-slate-100 cursor-pointer hover:bg-slate-200 rounded-md font-bold text-slate-700 flex items-center justify-center"
                >
                  −
                </button>
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={qty}
                  onChange={e => setQty(Math.max(1, Math.min(500, +e.target.value)))}
                  className="flex-1 text-center border border-slate-200 rounded-md py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="button"
                  onClick={() => setQty(q => Math.min(500, q + 1))}
                  className="w-10 h-10 bg-slate-100 cursor-pointer hover:bg-slate-200 rounded-md font-bold text-slate-700 flex items-center justify-center"
                >
                  +
                </button>
              </div>

              <button
                type="button"
                onClick={handlePrint}
                disabled={!selectedTpl}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-md cursor-pointer transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                </svg>
                {qty} ta chop et
              </button>
              <button
                type="button"
                onClick={onClose}
                className="w-full py-2 border border-slate-300 text-slate-600 font-semibold text-sm rounded-md hover:bg-slate-100 cursor-pointer transition-colors"
              >
                Yopish
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Save Template Modal ── */}
      {saveModalOpen && (
        <div className="fixed inset-0 flex items-center justify-center p-4 bg-black/40" style={{ zIndex: 80 }}>
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm">
            <h4 className="text-base font-bold text-slate-800 mb-1">Shablonni saqlash</h4>
            <p className="text-xs text-slate-400 mb-4">"{selectedTpl?.name}" asosida yangi shablon</p>
            <input
              autoFocus
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4"
              placeholder="Shablon nomi..."
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
            />
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setSaveModalOpen(false)}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-semibold rounded-xl hover:bg-slate-50"
              >
                Bekor
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={!saveName.trim()}
                className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold rounded-xl transition-colors"
              >
                ⭐ Saqlash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
