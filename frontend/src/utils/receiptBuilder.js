// frontend/src/utils/receiptBuilder.js
export const RECEIPT_KEY = 'erp_receipt_settings';

/**
 * Chekni shu brauzer oynasida iframe orqali chop etadi (yangi tab ochmaydi).
 */
export function printReceiptHtml(html) {
  const old = document.getElementById('__erp_receipt_iframe__');
  if (old) old.remove();
  const iframe = document.createElement('iframe');
  iframe.id = '__erp_receipt_iframe__';
  iframe.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;border:none;';
  document.body.appendChild(iframe);
  const doc = iframe.contentWindow.document;
  doc.open(); doc.write(html); doc.close();
  setTimeout(() => {
    try { iframe.contentWindow.focus(); iframe.contentWindow.print(); } catch (e) { console.warn('Print error:', e); }
  }, 50);
}

export function getReceiptSettings() {
  try {
    return JSON.parse(localStorage.getItem(RECEIPT_KEY) || '{}');
  } catch {
    return {};
  }
}

/**
 * Builds the HTML layout for a receipt/nakladnoy based on loaded settings templates.
 * @param {Object} sale - The sale metadata (number, created_at, cashier_name, total_amount, paid_amount, discount_amount, items)
 * @param {string} tpl - Template size: '58', '80', or 'nak'
 * @param {Object} cfg - The specific configuration template object (e.g. settings.r58) loaded from settings
 */
export function buildReceiptHtml(sale, tpl, cfg = {}) {
  const narrow = tpl === '58';
  const isNak = tpl === 'nak' || tpl === 'A4';
  const width = isNak ? '100%' : (narrow ? '320px' : '420px');

  const debt = Number(sale.total_amount) - Number(sale.paid_amount);
  const change = Math.max(0, Number(sale.paid_amount) - Number(sale.total_amount));

  if (isNak) {
    const itemRows = (sale.items || []).map((i, idx) =>
      `<tr>
         <td>${idx + 1}</td>
         <td>${i.product_name || i.product?.name || `ID=${i.product_id}`}</td>
         <td style="text-align:right">${Number(i.quantity || i.qty_ordered || 0)}</td>
         <td style="text-align:right">${Number(i.unit_price).toLocaleString('uz-UZ')}</td>
         <td style="text-align:right">${Number(i.subtotal || ((i.unit_price * (i.quantity||i.qty_ordered)) - (i.discount||i.discount_val||0))).toLocaleString('uz-UZ')}</td>
       </tr>`
    ).join('');

    const nakLogoPos = cfg.logo_position || 'center';
    const nakLogoAlign = nakLogoPos === 'left' ? 'left' : nakLogoPos === 'right' ? 'right' : 'center';
    const nakLogoSz = cfg.logo_size || 50;
    const nakLogoHtml = cfg.logo
      ? `<div style="text-align:${nakLogoAlign};margin-bottom:6px"><img src="${cfg.logo}" style="height:${nakLogoSz}px;max-width:${Math.round(nakLogoSz*3)}px;object-fit:contain" alt="logo"/></div>`
      : '';

    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Nakladnoy ${sale.number || sale.id}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: Arial, sans-serif; font-size: 10px; padding: 15px; }
  .hdr { text-align:center; margin-bottom:10px; }
  .hdr h1 { font-size:13px; }
  .hdr p { font-size:9px; color:#555; }
  .title { text-align:center; font-size:12px; font-weight:bold; margin:8px 0; }
  table { width:100%; border-collapse:collapse; margin-bottom:6px; }
  th, td { border:1px solid #666; padding:3px 5px; font-size:9px; }
  th { background:#f0f0f0; font-weight:bold; text-align:center; }
  .totals { margin-top:4px; }
  .totals tr td { border:none; font-size:10px; padding:1px 3px; }
  .totals tr td:last-child { text-align:right; font-weight:bold; }
  .sigs { display:flex; justify-content:space-between; margin-top:14px; font-size:9px; }
  @media print { body { padding:5px; } }
</style></head><body>
  ${nakLogoHtml}
  <div class="hdr">
    <h1>${cfg.company || 'KORXONA NOMI'}</h1>
    ${cfg.address ? `<p>${cfg.address}</p>` : ''}
    ${cfg.phone ? `<p>Tel: ${cfg.phone}</p>` : ''}
    ${cfg.inn ? `<p>STIR: ${cfg.inn}</p>` : ''}
  </div>
  <div class="title">NAKLADNOY № ${sale.number || sale.id} / ${new Date(sale.created_at || Date.now()).toLocaleDateString('uz-UZ')}</div>
  <table>
    <thead><tr><th>№</th><th>Mahsulot nomi</th><th>Soni</th><th>Narxi (so'm)</th><th>Jami (so'm)</th></tr></thead>
    <tbody>${itemRows}</tbody>
    <tfoot><tr><td colspan="4" style="text-align:right;font-weight:bold">JAMI:</td><td style="text-align:right;font-weight:bold">${Number(sale.total_amount).toLocaleString('uz-UZ')}</td></tr></tfoot>
  </table>
  <table class="totals">
    <tr><td>To'langan:</td><td>${Number(sale.paid_amount).toLocaleString('uz-UZ')} so'm</td></tr>
    ${debt > 0 ? `<tr><td style="color:red">Qarz:</td><td style="color:red">${Number(debt).toLocaleString('uz-UZ')} so'm</td></tr>` : ''}
    ${change > 0 ? `<tr><td style="color:green">Qaytim:</td><td style="color:green">${Number(change).toLocaleString('uz-UZ')} so'm</td></tr>` : ''}
  </table>
  <div class="sigs">
    ${cfg.director ? `<div>Direktor: ${cfg.director} _______</div>` : '<div>Direktor: ___________</div>'}
    <div>Kassir: ${sale.cashier_name || sale.cashier?.name || 'Kassir'}</div>
    ${cfg.accountant ? `<div>Buxgalter: ${cfg.accountant} _______</div>` : ''}
  </div>
  ${cfg.footer_note ? `<div style="text-align:center;margin-top:8px;font-size:9px;color:#555;font-style:italic">${cfg.footer_note}</div>` : ''}
</body></html>`;
  }

  // Thermal Receipt (58mm or 80mm)
  const thermalSz = cfg.logo_size || 40;
  const thermalLogoHtml = cfg.logo
    ? `<div style="text-align:center;margin-bottom:3px"><img src="${cfg.logo}" style="height:${thermalSz}px;max-width:${Math.round(thermalSz*3)}px;object-fit:contain" alt="logo"/></div>`
    : '';

  const fsBig = narrow ? '13px' : '17px';
  const fsMid = narrow ? '12px' : '15px';
  const fsSmall = narrow ? '11px' : '13px';

  const rows = (sale.items || []).map(i => {
    const qty = Number(i.quantity || i.qty_ordered || 0);
    const up = Number(i.unit_price);
    const disc = Number(i.discount || (i.discount_type==='pct'?(up*qty*(i.discount_val/100)):i.discount_val) || 0);
    const sub = Number(i.subtotal || (up * qty - disc));
    return `<tr>
      <td><b>${i.product_name || i.product?.name || `ID=${i.product_id}`}</b></td>
      <td style="text-align:right">${qty} × ${up.toLocaleString('uz-UZ')}</td>
      <td style="text-align:right;white-space:nowrap"><b>${sub.toLocaleString('uz-UZ')}</b></td>
    </tr>`;
  }).join('');

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Chek ${sale.number || sale.id}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  body { font-family: 'Courier New', monospace; font-size: ${fsMid}; font-weight:bold; color:#000; width: ${width}; padding: 10px; }
  .center { text-align:center; }
  .norm { font-weight:normal; }
  .sub { font-size:${fsSmall}; color:#000; font-weight:normal; }
  hr { border:none; border-top:2px solid #000; margin:5px 0; }
  hr.dash { border-top:1px dashed #000; margin:4px 0; }
  table { width:100%; border-collapse:collapse; }
  td, th { padding:3px 0; vertical-align:top; color:#000; font-size:${fsMid}; }
  th { font-weight:bold; border-bottom:1px solid #000; }
  .tr { text-align:right; }
  .total-row td { font-weight:bold; font-size:${fsBig}; padding-top:5px; }
  @media print { body { width:auto; margin:0; padding:2px; } @page { margin:1mm; } }
</style></head><body>
  ${thermalLogoHtml}
  ${cfg.company ? `<div class="center" style="font-size:${narrow?'15px':'19px'};font-weight:bold">${cfg.company}</div>` : (!cfg.logo ? `<div class="center" style="font-size:${fsBig};font-weight:bold">SOTUV CHEKI</div>` : '')}
  ${cfg.address ? `<div class="center sub">${cfg.address}</div>` : ''}
  ${cfg.phone ? `<div class="center sub">Tel: ${cfg.phone}</div>` : ''}
  ${cfg.inn ? `<div class="center sub">STIR: ${cfg.inn}</div>` : ''}
  ${cfg.header ? `<div class="center sub">${cfg.header}</div>` : ''}
  <hr/>
  <div style="display:flex;justify-content:space-between;font-size:${fsSmall}" class="norm">
    <span><b>${sale.number || sale.id}</b></span>
    ${cfg.show_date !== false ? `<span>${new Date(sale.created_at || Date.now()).toLocaleString('uz-UZ')}</span>` : ''}
  </div>
  ${cfg.show_cashier !== false ? `<div class="sub">Kassir: <b>${sale.cashier_name || sale.cashier?.name || 'Kassir'}</b></div>` : ''}
  <hr class="dash"/>
  <table>
    <tr><th style="text-align:left">Mahsulot</th><th class="tr">Soni×Narx</th><th class="tr">Jami</th></tr>
    ${rows}
  </table>
  <hr/>
  ${Number(sale.discount_amount)>0 ? `<div style="display:flex;justify-content:space-between;font-size:${fsSmall}"><span>Chegirma:</span><span>-${Number(sale.discount_amount).toLocaleString('uz-UZ')} so'm</span></div>` : ''}
  <table>
    <tr class="total-row"><td>JAMI:</td><td class="tr">${Number(sale.total_amount).toLocaleString('uz-UZ')} so'm</td></tr>
    
    ${
       sale.payment_types_array ? 
       sale.payment_types_array.map(pt => `<tr style="font-size:${fsSmall}" class="norm"><td>To'lov (${pt.type}):</td><td class="tr"><b>${Number(pt.amount).toLocaleString('uz-UZ')} so'm</b></td></tr>`).join('') 
       : `<tr style="font-size:${fsSmall}" class="norm"><td>To'langan:</td><td class="tr"><b>${Number(sale.paid_amount).toLocaleString('uz-UZ')} so'm</b></td></tr>`
    }

    ${debt>0 ? `<tr style="font-size:${fsSmall}" class="norm"><td>Qarz:</td><td class="tr"><b>${Number(debt).toLocaleString('uz-UZ')} so'm</b></td></tr>` : ''}
    ${change>0 ? `<tr style="font-size:${fsSmall}" class="norm"><td>Qaytim:</td><td class="tr"><b>${Number(change).toLocaleString('uz-UZ')} so'm</b></td></tr>` : ''}
  </table>
  <hr class="dash"/>
  ${cfg.show_barcode !== false && (sale.number || sale.id) ? `<div class="center sub" style="margin:3px 0;letter-spacing:3px">||||||||||||||||||||||||||||<br/>${sale.number || sale.id}</div><hr class="dash"/>` : ''}
  <div class="center" style="margin-top:4px;font-size:${fsSmall};font-weight:bold">${cfg.footer || 'Xarid uchun rahmat!'}</div>
</body></html>`;
}
