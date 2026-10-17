// T3.12: tarozi fayllarini qurish (toza funksiyalar). Uchala format ham bir xil PLU dan (pluNumber) foydalanadi.
// items — GET /products/export/scale javobi: [{id, name, sku, plu_code, barcode, product_code, sale_price, unit}]
import { pluNumber } from './scale';

const priceInt = (p) => (p.sale_price ? Math.round(parseFloat(p.sale_price)) : 0);

// Shtrix-M: PLU;NOM;GURUH;NARX;TARA;YAROQLILIK;TUR;SHTRIX-KOD;0;0;0;01.01.01;0;
export function buildShtrixM(items) {
  let txt = '';
  (items || []).forEach(prod => {
    const plu = String(pluNumber(prod));
    const name = prod.name ? prod.name.replace(/;/g, ' ') : 'Nomsiz';
    const group = '';
    const price = priceInt(prod);
    const barcode = plu;
    const tara = 0;
    const yaroqlilik_muddati = 0;
    const maxsulot_turi = 0; // 0 - tarozibop
    txt += `${plu};${name};${group};${price};${tara};${yaroqlilik_muddati};${maxsulot_turi};${barcode};0;0;0;01.01.01;0;\r\n`;
  });
  return txt;
}

// TM-A (TMS): 69 ustunli PLU qatorlari
export function buildTma(items) {
  const lines = [];
  // Tarozi sozlamalari (Print=1100, Barcode=10) har bir mahsulot qatorida (8, 9 ustunlar) yuboriladi
  lines.push('ECS\tVER\t100\t');
  lines.push('DWL\tPLU\t');

  (items || []).forEach((prod) => {
    // Ism (bo'shliq, enterni tozalash)
    const name = (prod.name || 'Nomsiz')
      .replace(/[\t\r\n]/g, ' ')
      .trim()
      .substring(0, 28);

    // Narx (TMS formatida vergul bilan)
    const priceRaw = prod.sale_price ? parseFloat(prod.sale_price) : 0;
    const priceStr = priceRaw.toFixed(1).replace('.', ',');

    // ItemCode = PLU raqami (Barcode-10 aynan shu yerdan kodni oladi)
    const itemCodeStr = String(pluNumber(prod));

    const row = [
      'PLU', // 0
      itemCodeStr, // 1 (PLU Number)
      '0', // 2
      '', // 3
      '3', // 4 (Unit: kg)
      priceStr, // 5
      '0,0', '0,0', // 6,7
      '1100', // 8 (Print format)
      '10', // 9 (Barcode format)
      '0', '0', '0', '0', // 10-13
      itemCodeStr, // 14 (Item Code)
      name, // 15 (Name)
      '', '', '', '', '', '', '', // 16-22
      '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', '0', // 23-34
      '0,0', '0,0', // 35,36
      '0', '127', '0,0', '0,0', '0,0', // 37-41
      '0', '127', '0,0', '0,0', '0,0', // 42-46
      '0', '127', '0,0', '0,0', '0,0', // 47-51
      '0', '127', '0,0', '0,0', '0,0', // 52-56
      '0', '0', '0', '0', '0', '0', '0', // 57-63
      name, // 64 (Name 2)
      '0', '0', '0', '' // 65-68
    ];

    lines.push(row.join('\t'));
  });

  lines.push('END\tPLU\t');
  lines.push('END\tECS\t');
  return lines.join('\r\n');
}

// Rongta 13-ustunli format: CODE;NAME;;PRICE;0;0;0;CODE;0;0;0;01.01.01;0
export function buildRongta(items) {
  const lines = [];
  (items || []).forEach((prod) => {
    const code = String(pluNumber(prod));
    const name = (prod.name || 'NOMSIZ').toUpperCase().trim();
    const price = priceInt(prod);
    lines.push(`${code};${name};;${price};0;0;0;${code};0;0;0;01.01.01;0`);
  });
  return lines.join('\r\n');
}
