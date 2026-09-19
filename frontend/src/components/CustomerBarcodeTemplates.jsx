/**
 * CustomerBarcodeTemplates.jsx
 *
 * Mijoz loyallik kartasi uchun shtrix-kod chop etish oynasi.
 * BarcodeTemplates.jsx (mahsulot) bilan bir xil dizayn va shablon
 * tizimidan foydalanadi, lekin faqat mijozga tegishli maydonlar bilan
 * ishlaydi (narx/SKU/mahsulot kodi/valyuta yo'q).
 */

import { useState, useEffect, useRef } from 'react';

const LS_KEY = 'customer_barcode_saved_templates';
const MM_TO_PX = 3.7795;

function mmToPx(mm) {
  return Math.round(mm * MM_TO_PX);
}

const BUILT_IN_TEMPLATES = [
  {
    id: 'c-30x20-classic', size: '30×20', w: 30, h: 20,
    name: 'Klassik (30×20)',
    description: 'Ism + barcode, ixcham karta',
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'c-40x30-standard', size: '40×30', w: 40, h: 30,
    name: 'Standart (40×30)',
    description: 'Ism + barcode + do\'kon nomi',
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'c-40x30-branded', size: '40×30', w: 40, h: 30,
    name: 'Brendli (40×30)',
    description: 'Do\'kon nomi + ism + barcode',
    colors: { bg: '#fff', text: '#000', accent: '#4f46e5' },
  },
  {
    id: 'c-40x30-dark', size: '40×30', w: 40, h: 30,
    name: 'To\'q fon (40×30)',
    description: 'Qora fon, oq yozuv',
    colors: { bg: '#1a1a2e', text: '#fff', accent: '#e2e8f0' },
  },
  {
    id: 'c-50x30-standard', size: '50×30', w: 50, h: 30,
    name: 'Standart (50×30)',
    description: 'Do\'kon + ism + barcode',
    colors: { bg: '#fff', text: '#000', accent: '#000' },
  },
  {
    id: 'c-50x40-full', size: '50×40', w: 50, h: 40,
    name: 'To\'liq (50×40)',
    description: 'Do\'kon + ism + barcode + keshbek',
    colors: { bg: '#fff', text: '#000', accent: '#4f46e5' },
  },
  {
    id: 'c-60x40-premium', size: '60×40', w: 60, h: 40,
    name: 'Premium (60×40)',
    description: 'Do\'kon + ism + katta barcode + keshbek',
    colors: { bg: '#fff', text: '#000', accent: '#7c3aed' },
  },
];

const SIZE_GROUPS = ['30×20', '40×30', '50×30', '50×40', '60×40'];

function buildLabelHTML(tpl, customer, opts = {}) {
  const { w, h, colors } = tpl;

  const showCompanyName = opts.showCompanyName !== undefined ? opts.showCompanyName : true;
  const showCustomerName = opts.showCustomerName !== undefined ? opts.showCustomerName : true;
  const showCashback = opts.showCashback !== undefined ? opts.showCashback : true;
  const showBarcode = opts.showBarcode !== undefined ? opts.showBarcode : true;
  const showCardNumber = opts.showCardNumber !== undefined ? opts.showCardNumber : true;

  const companyNamePos = opts.companyNamePos || 'up';
  const customerNamePos = opts.customerNamePos || 'up';
  const cashbackPos = opts.cashbackPos || 'down';

  const companyNameSize = opts.fontSize || 8;
  const customerNameSize = opts.customerNameSize || 8;
  const cashbackSize = opts.cashbackSize || 8;
  const cardNumberSize = opts.cardNumberSize || 6;
  const barcodeSize = opts.barcodeSize || 10;

  const name = customer.name || '';
  const cardNumber = customer.card_number || '';
  const cashback = Number(customer.cashback_percent || 0);
  const companyNameText = opts.companyName || '';

  const base = `
    width:${w}mm; height:${h}mm;
    background:${colors.bg || '#fff'}; color:${colors.text || '#000'};
    display:inline-flex; flex-direction:column; align-items:center; justify-content:space-between;
    padding:1mm 1.5mm; box-sizing:border-box;
    border:0.3mm solid #ccc; page-break-inside:avoid; overflow:hidden;
    font-family:Arial,sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact;
  `;

  const companyHtml = (showCompanyName && companyNameText)
    ? `<div style="font-size:${companyNameSize}px; font-weight:700; text-align:center; word-break:break-word; width:100%; line-height:1.1;">${companyNameText}</div>`
    : '';

  const customerNameHtml = showCustomerName
    ? `<div style="font-size:${customerNameSize}px; font-weight:700; text-align:center; line-height:1.2; width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${name}</div>`
    : '';

  const cashbackHtml = (showCashback && cashback > 0)
    ? `<div style="font-size:${cashbackSize}px; font-weight:900; color:${colors.accent || colors.text || '#000'}; text-align:center; width:100%;">Keshbek: ${cashback}%</div>`
    : '';

  const cardNumberHtml = (showCardNumber && cardNumber)
    ? `<div style="font-size:${cardNumberSize}px; color:#555; font-family:monospace; text-align:center; width:100%; line-height:1.1;">${cardNumber}</div>`
    : '';

  const barcodeHtml = (showBarcode && cardNumber)
    ? `<svg class="bc" data-val="${cardNumber}" data-linecolor="${colors.text || '#000'}" data-height="${barcodeSize * 2.4}" data-fontsize="${barcodeSize * 0.7}" data-barwidth="${(barcodeSize * 0.1).toFixed(2)}" style="width:100%; max-height:${h * 0.55}mm; margin:0.5mm 0;"></svg>`
    : '';

  const upElements = [];
  const downElements = [];

  if (companyHtml) {
    if (companyNamePos === 'up') upElements.push(companyHtml);
    else downElements.push(companyHtml);
  }

  if (customerNameHtml) {
    if (customerNamePos === 'up') upElements.push(customerNameHtml);
    else downElements.push(customerNameHtml);
  }

  if (cashbackHtml) {
    if (cashbackPos === 'up') upElements.push(cashbackHtml);
    else downElements.push(cashbackHtml);
  }

  if (cardNumberHtml) downElements.push(cardNumberHtml);

  const inner = `
    <div style="width:100%; display:flex; flex-direction:column; align-items:center; gap:0.4mm; overflow:hidden;">
      ${upElements.join('')}
    </div>
    ${barcodeHtml}
    <div style="width:100%; display:flex; flex-direction:column; align-items:center; gap:0.4mm; overflow:hidden;">
      ${downElements.join('')}
    </div>
  `;

  return `<div style="${base}">${inner}</div>`;
}

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

function LabelPreview({ tpl, customer, scale = 1, options = {} }) {
  const ref = useRef(null);
  const wPx = mmToPx(tpl.w);
  const hPx = mmToPx(tpl.h);

  useEffect(() => {
    if (ref.current) renderBarcodes(ref.current);
  });

  const html = buildLabelHTML(tpl, customer, options);

  return (
    <div style={{ width: wPx * scale, height: hPx * scale, flexShrink: 0, overflow: 'hidden', position: 'relative' }}>
      <div
        ref={ref}
        style={{ transform: `scale(${scale})`, transformOrigin: 'top left', position: 'absolute', top: 0, left: 0 }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}

export default function CustomerBarcodePrintModal({ customer, onClose }) {
  const [selectedTpl, setSelectedTpl] = useState(BUILT_IN_TEMPLATES[4]); // 50×30 default
  const [qty, setQty] = useState(1);

  const [fontSize, setFontSize] = useState(8);
  const [customerNameSize, setCustomerNameSize] = useState(8);
  const [cashbackSize, setCashbackSize] = useState(8);
  const [cardNumberSize, setCardNumberSize] = useState(6);
  const [barcodeSize, setBarcodeSize] = useState(10);

  const [companyName, setCompanyName] = useState('');

  const [savedTemplates, setSavedTemplates] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch { return []; }
  });
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');

  const [showCompanyName, setShowCompanyName] = useState(true);
  const [showCustomerName, setShowCustomerName] = useState(true);
  const [showCashback, setShowCashback] = useState(true);
  const [showBarcode, setShowBarcode] = useState(true);
  const [showCardNumber, setShowCardNumber] = useState(true);

  const [companyNamePos, setCompanyNamePos] = useState('up');
  const [customerNamePos, setCustomerNamePos] = useState('up');
  const [cashbackPos, setCashbackPos] = useState('down');

  useEffect(() => {
    if (window.JsBarcode) return;
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js';
    s.async = true;
    document.head.appendChild(s);
  }, []);

  const previewOptions = {
    companyName,
    fontSize,
    customerNameSize,
    cashbackSize,
    cardNumberSize,
    barcodeSize,
    showCompanyName,
    showCustomerName,
    showCashback,
    showBarcode,
    showCardNumber,
    companyNamePos,
    customerNamePos,
    cashbackPos,
  };

  const handleSave = () => {
    if (!saveName.trim()) return;
    const newTpl = {
      ...selectedTpl,
      id: `saved-${Date.now()}`,
      name: saveName.trim(),
      description: `${selectedTpl.size} mm — saqlangan shablon`,
      _opts: {
        fontSize, customerNameSize, cashbackSize, cardNumberSize, barcodeSize,
        companyName, showCompanyName, showCustomerName, showCashback, showBarcode, showCardNumber,
        companyNamePos, customerNamePos, cashbackPos,
      },
    };
    const updated = [...savedTemplates, newTpl];
    setSavedTemplates(updated);
    localStorage.setItem(LS_KEY, JSON.stringify(updated));
    setSaveModalOpen(false);
    setSaveName('');
  };

  const handleDeleteSaved = (id, e) => {
    e.stopPropagation();
    const updated = savedTemplates.filter(t => t.id !== id);
    setSavedTemplates(updated);
    localStorage.setItem(LS_KEY, JSON.stringify(updated));
  };

  const handleLoadSaved = (id) => {
    const tpl = savedTemplates.find(t => t.id === id);
    if (!tpl) return;
    setSelectedTpl(tpl);
    const o = tpl._opts || {};
    if (o.fontSize !== undefined) setFontSize(o.fontSize);
    if (o.customerNameSize !== undefined) setCustomerNameSize(o.customerNameSize);
    if (o.cashbackSize !== undefined) setCashbackSize(o.cashbackSize);
    if (o.cardNumberSize !== undefined) setCardNumberSize(o.cardNumberSize);
    if (o.barcodeSize !== undefined) setBarcodeSize(o.barcodeSize);
    if (o.companyName !== undefined) setCompanyName(o.companyName);
    if (o.showCompanyName !== undefined) setShowCompanyName(o.showCompanyName);
    if (o.showCustomerName !== undefined) setShowCustomerName(o.showCustomerName);
    if (o.showCashback !== undefined) setShowCashback(o.showCashback);
    if (o.showBarcode !== undefined) setShowBarcode(o.showBarcode);
    if (o.showCardNumber !== undefined) setShowCardNumber(o.showCardNumber);
    if (o.companyNamePos !== undefined) setCompanyNamePos(o.companyNamePos);
    if (o.customerNamePos !== undefined) setCustomerNamePos(o.customerNamePos);
    if (o.cashbackPos !== undefined) setCashbackPos(o.cashbackPos);
  };

  const handlePrint = () => {
    const { w, h } = selectedTpl;
    const singleLabel = buildLabelHTML(selectedTpl, customer, previewOptions);
    const labelItems = Array.from({ length: qty }, (_, i) =>
      `<div class="lbl-wrap${i < qty - 1 ? ' page-break' : ''}">${singleLabel}</div>`
    ).join('');

    const iframeId = '__customer_barcode_print_frame__';
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
          <head><title>Chop: ${customer.name}</title>
            <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></scr` + `ipt>
            <style>
              @page { margin: 0; size: ${w}mm ${h}mm; }
              * { box-sizing: border-box; }
              body { margin: 0; padding: 0; background: #fff; font-family: Arial, sans-serif; }
              .lbl-wrap { display: block; width: ${w}mm; height: ${h}mm; overflow: hidden; }
              .lbl-wrap > div { border: none !important; }
              .page-break { page-break-after: always; }
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
                      format: 'CODE128', width: 1.1, height: bh, displayValue: true,
                      fontSize: fs, margin: 1, lineColor: lc, fontOptions: '',
                      font: 'Arial', textAlign: 'center', textPosition: 'bottom'
                    });
                  } catch(e) {}
                });
                setTimeout(function() { window.focus(); window.print(); }, 500);
              };
            </script>
          </body>
        </html>`);
    doc.close();
  };

  return (
    <div className="fixed inset-0 z-70 flex items-center w-full h-full justify-center">
      <div className="bg-white flex flex-col overflow-hidden" style={{ width: '100%', maxWidth: '100%', height: '100%' }} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-100 shrink-0">
          <div>
            <h3 className="text-lg font-bold text-slate-800">Mijoz kartasi — shtrix-kod</h3>
            <p className="text-xs text-slate-400 truncate max-w-sm">
              {customer.name} · <span className="font-mono">{customer.card_number}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            {savedTemplates.length > 0 && (
              <div className="relative flex items-center gap-1 bg-amber-50 border border-amber-200 rounded-xl px-1 py-1">
                <svg className="w-4 h-4 text-amber-500 ml-1 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                <select
                  defaultValue=""
                  onChange={e => { if (e.target.value) handleLoadSaved(e.target.value); e.target.value = ''; }}
                  className="pl-2 pr-6 py-1.5 text-sm font-semibold text-amber-700 bg-transparent border-0 outline-none cursor-pointer appearance-none"
                  title="Saqlangan shablonni yuklash"
                >
                  <option value="" disabled>Saqlangan shablonlar</option>
                  {savedTemplates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
            )}
            {savedTemplates.length > 0 && (
              <div className="flex flex-wrap gap-1 max-w-xs">
                {savedTemplates.map(t => (
                  <span key={t.id} className="inline-flex items-center gap-1 text-xs font-medium bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5 rounded-full">
                    <button type="button" onClick={() => handleLoadSaved(t.id)} className="hover:underline max-w-[90px] truncate cursor-pointer" title={`"${t.name}" shablonini yuklash`}>{t.name}</button>
                    <button type="button" onClick={e => handleDeleteSaved(t.id, e)} className="ml-0.5 text-amber-400 hover:text-red-500 transition-colors cursor-pointer leading-none" title="O'chirish">✕</button>
                  </span>
                ))}
              </div>
            )}
            <button onClick={() => setSaveModalOpen(true)} className="flex items-center gap-1.5 px-3 py-2 text-sm font-semibold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-xl transition-colors border border-amber-200" title="Joriy sozlamalarni shablon sifatida saqlash">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
              Saqlash
            </button>
            <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* LEFT: font sizes */}
          <div className="min-w-70 max-w-170 w-full border-r border-slate-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Sozlamalar</div>
            </div>
            <div className="overflow-y-auto pb-10">
              <div className="px-3 py-1 mt-2 shrink-0">
                <div className="text-xs font-semibold text-slate-500 uppercase mb-1">O'lcham</div>
                <select
                  value={selectedTpl?.size || '50×30'}
                  onChange={(e) => {
                    const selectedSize = e.target.value;
                    const found = BUILT_IN_TEMPLATES.find(t => t.size === selectedSize);
                    if (found) setSelectedTpl(found);
                    else {
                      const [w, h] = selectedSize.split('×').map(Number);
                      setSelectedTpl({ id: `custom-${selectedSize}`, name: selectedSize, size: selectedSize, w, h, colors: { bg: '#fff', text: '#000', accent: '#000' } });
                    }
                  }}
                  className="px-4 py-3 w-full rounded-lg text-sm font-semibold transition-colors cursor-pointer border border-slate-300 outline-0"
                >
                  {SIZE_GROUPS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              <div className="px-3 py-2 border-b border-slate-100 shrink-0">
                <div className="text-xs font-semibold text-slate-500 uppercase mb-1">Do'kon nomi</div>
                <input
                  type="text"
                  placeholder="Do'kon nomi"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="px-4 py-3 w-full rounded-lg text-sm transition-colors border border-slate-300 outline-0"
                />
              </div>

              <div className="p-4 flex flex-col gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Do'kon nomi: {fontSize}px</div>
                  <input type="range" min="6" max="22" value={fontSize} onChange={e => setFontSize(+e.target.value)} className="w-full accent-blue-600" />
                  <div className="flex justify-between text-xs text-slate-400"><span>6</span><span>22</span></div>
                </div>
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Mijoz ismi: {customerNameSize}px</div>
                  <input type="range" min="6" max="30" value={customerNameSize} onChange={e => setCustomerNameSize(+e.target.value)} className="w-full accent-blue-600" />
                  <div className="flex justify-between text-xs text-slate-400"><span>6</span><span>30</span></div>
                </div>
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Keshbek: {cashbackSize}px</div>
                  <input type="range" min="6" max="30" value={cashbackSize} onChange={e => setCashbackSize(+e.target.value)} className="w-full accent-blue-600" />
                  <div className="flex justify-between text-xs text-slate-400"><span>6</span><span>30</span></div>
                </div>
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Karta raqami: {cardNumberSize}px</div>
                  <input type="range" min="4" max="22" value={cardNumberSize} onChange={e => setCardNumberSize(+e.target.value)} className="w-full accent-blue-600" />
                  <div className="flex justify-between text-xs text-slate-400"><span>4</span><span>22</span></div>
                </div>
                <div>
                  <div className="text-sm font-medium text-slate-600 mb-1">Shtrix: {barcodeSize}px</div>
                  <input type="range" min="10" max="30" value={barcodeSize} onChange={e => setBarcodeSize(+e.target.value)} className="w-full accent-blue-600" />
                  <div className="flex justify-between text-xs text-slate-400"><span>10</span><span>30</span></div>
                </div>
              </div>
            </div>
          </div>

          {/* CENTER: preview */}
          <div className="flex-1 min-w-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Ko'rinish</div>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-slate-50 flex items-start justify-center">
              {selectedTpl ? (
                <div className="flex">
                  <div>
                    <div className="bg-white shadow-md inline-flex items-center justify-center">
                      <LabelPreview tpl={selectedTpl} customer={customer} scale={2} options={previewOptions} />
                    </div>
                    <div className="text-xs text-slate-400 mt-2 text-center">{selectedTpl.w}×{selectedTpl.h} mm · {selectedTpl.name}</div>
                  </div>
                </div>
              ) : (
                <div className="text-slate-400 text-sm mt-12">Shablon tanlang</div>
              )}
            </div>
          </div>

          {/* RIGHT: toggles + positions */}
          <div className="max-w-90 min-w-80 w-full border-l border-slate-100 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-100 shrink-0">
              <div className="text-xs font-semibold text-slate-500 uppercase">Sozlamalar</div>
            </div>
            <div className="flex-1 flex flex-col overflow-y-auto">
              <div className="space-y-5 border-b p-4 border-b-slate-100">
                {[
                  ['showCompanyName', showCompanyName, setShowCompanyName, "Do'kon nomini ko'rsatish"],
                  ['showCustomerName', showCustomerName, setShowCustomerName, "Mijoz ismini ko'rsatish"],
                  ['showCashback', showCashback, setShowCashback, "Keshbekni ko'rsatish"],
                  ['showBarcode', showBarcode, setShowBarcode, "Shtrix kodni ko'rsatish"],
                  ['showCardNumber', showCardNumber, setShowCardNumber, "Karta raqamini ko'rsatish"],
                ].map(([id, val, setter, label]) => (
                  <div key={id} className="flex items-center gap-2">
                    <div className="relative inline-block w-11 h-5">
                      <input
                        checked={val}
                        onChange={e => setter(e.target.checked)}
                        id={`switch-${id}`}
                        type="checkbox"
                        className="peer appearance-none w-11 h-5 bg-slate-100 rounded-full checked:bg-blue-600 cursor-pointer transition-colors duration-300"
                      />
                      <label htmlFor={`switch-${id}`} className="absolute top-0 left-0 w-5 h-5 bg-white rounded-full border border-slate-300 shadow-sm transition-transform duration-300 peer-checked:translate-x-6 peer-checked:border-blue-600 cursor-pointer"></label>
                    </div>
                    <span>{label}</span>
                  </div>
                ))}
              </div>

              <div className="flex flex-col gap-4 p-4 border-b border-b-slate-100">
                <div className="flex justify-between items-center">
                  <span>Mijoz ismi:</span>
                  <select value={customerNamePos} onChange={e => setCustomerNamePos(e.target.value)} className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded">
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>
                <div className="flex justify-between items-center">
                  <span>Do'kon nomi:</span>
                  <select value={companyNamePos} onChange={e => setCompanyNamePos(e.target.value)} className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded">
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>
                <div className="flex justify-between items-center">
                  <span>Keshbek:</span>
                  <select value={cashbackPos} onChange={e => setCashbackPos(e.target.value)} className="py-2 px-3 border border-slate-200 outline-0 cursor-pointer rounded">
                    <option value="up">tepada</option>
                    <option value="down">pastda</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="p-4 border-t border-slate-100 space-y-2 shrink-0">
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setQty(q => Math.max(1, q - 1))} className="w-10 h-10 bg-slate-100 cursor-pointer hover:bg-slate-200 rounded-md font-bold text-slate-700 flex items-center justify-center">−</button>
                <input type="number" min="1" max="500" value={qty} onChange={e => setQty(Math.max(1, Math.min(500, +e.target.value)))} className="flex-1 text-center border border-slate-200 rounded-md py-2 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-blue-500" />
                <button type="button" onClick={() => setQty(q => Math.min(500, q + 1))} className="w-10 h-10 bg-slate-100 cursor-pointer hover:bg-slate-200 rounded-md font-bold text-slate-700 flex items-center justify-center">+</button>
              </div>
              <button type="button" onClick={handlePrint} disabled={!selectedTpl} className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold rounded-md cursor-pointer transition-colors flex items-center justify-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" /></svg>
                {qty} ta chop et
              </button>
              <button type="button" onClick={onClose} className="w-full py-2 border border-slate-300 text-slate-600 font-semibold text-sm rounded-md hover:bg-slate-100 cursor-pointer transition-colors">Yopish</button>
            </div>
          </div>
        </div>
      </div>

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
              <button type="button" onClick={() => setSaveModalOpen(false)} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-semibold rounded-xl hover:bg-slate-50">Bekor</button>
              <button type="button" onClick={handleSave} disabled={!saveName.trim()} className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold rounded-xl transition-colors">⭐ Saqlash</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
