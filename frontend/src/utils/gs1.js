// GS1 Data Matrix (markirovka) kodini skanerdan o'qish: GTIN, seriya va serverga yuboriladigan kod.
// Formatlar: 01 GTIN 21 seriya 91/92 (Asl belgisi, dori), 21 seriya 93 (oziq-ovqat), 17/10/21 (Yevropa dorisi),
// qavsli (01)...(21)... va GS1 Digital Link (.../01/<GTIN>/21/<seriya>). Skaner kirill klaviaturada harflarni
// almashtirib yuborsa (q -> й ...), ular lotinga qaytariladi. Server kodni o'zi qayta tahlil qiladi (parse_gs1).

export const GS = '\x1d';

const FIXED = { '00': 18, '01': 14, '02': 14, '11': 6, '12': 6, '13': 6, '15': 6, '16': 6, '17': 6, '20': 2 };
const VAR = {
  '10': 20, '21': 20, '22': 20, '30': 8, '37': 8, '240': 30, '241': 30, '242': 6,
  '250': 30, '251': 30, '253': 30, '254': 20, '255': 25,
};
for (let n = 91; n <= 99; n++) VAR[String(n)] = 90;

// Ajratgich (GS) yo'qolganda seriya oxirini kod dumi bo'yicha topamiz: 91+kalit(4) [92+imzo(44)] yoki 93+kripto(4)
const TAIL = /^(?:91[\x21-\x7e]{4}(?:92[\x21-\x7e]{44})?|92[\x21-\x7e]{44}|93[\x21-\x7e]{4})$/;

// Rus / o'zbek (kirill) klaviaturada skaner yozgan belgi -> o'sha tugmadagi lotin belgisi
const CYR = 'йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁўЎқҚғҒҳҲ';
const LAT = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~oOsS-_=+";
const SYM = { '.': '/', ',': '?', '"': '@', '№': '#', ';': '$', ':': '^', '?': '&', '/': '|' };
const KEYMAP = {};
for (let i = 0; i < CYR.length; i++) KEYMAP[CYR[i]] = LAT[i];

export function latinize(s) {
  const text = String(s || '');
  if (!/[Ѐ-ӿ]/.test(text)) return text;
  let out = '';
  for (const ch of text) out += KEYMAP[ch] ?? SYM[ch] ?? ch;
  return out;
}

// AI lar Map da: kod qayta yig'ilganda skanerdagi tartib saqlanadi ("21" kabi kalitlar obyektda saralanib ketadi)
function rawAis(s) {
  const ais = new Map();
  let i = 0;
  while (i < s.length) {
    if (s[i] === GS) { i++; continue; }
    const ai = [2, 3, 4].map(k => s.slice(i, i + k)).find(a => a in FIXED || a in VAR);
    if (!ai) break;   // noma'lum qism — GTIN baribir olingan
    const start = i + ai.length;
    if (ai in FIXED) {
      const v = s.slice(start, start + FIXED[ai]);
      if (v.length !== FIXED[ai] || !/^\d+$/.test(v)) break;
      if (!ais.has(ai)) ais.set(ai, v);
      i = start + FIXED[ai];
      continue;
    }
    const gs = s.indexOf(GS, start);
    let end = gs === -1 ? s.length : gs;
    const seg = s.slice(start, end);
    for (let j = 1; j < seg.length; j++) {
      if (TAIL.test(seg.slice(j))) { end = start + j; break; }
    }
    end = Math.min(end, start + VAR[ai]);
    const v = s.slice(start, end);
    if (!v) break;
    if (!ais.has(ai)) ais.set(ai, v);
    i = end;
  }
  return ais;
}

function parenAis(s) {
  const ais = new Map();
  const re = /\((\d{2,4})\)([^()]*)/g;
  let m;
  while ((m = re.exec(s))) if (!ais.has(m[1])) ais.set(m[1], m[2].split(GS).join('').trim());
  return ais;
}

// Qat'iy uzunlikdagi maydondan keyin ajratgich qo'yilmaydi, o'zgaruvchandan keyin GS (oxirgisidan tashqari)
function build(ais) {
  const keys = [...ais.keys()];
  let code = '';
  keys.forEach((ai, k) => {
    code += ai + ais.get(ai);
    if (!(ai in FIXED) && k < keys.length - 1) code += GS;
  });
  return { gtin: ais.get('01'), serial: ais.get('21') || null, lot: ais.get('10') || null, expiry: ais.get('17') || null, code };
}

/** Skanerlangan matn GS1 kodi bo'lsa { gtin, serial, lot, expiry, code }, aks holda null.
 *  `serial` bo'lsa bu markirovka kodi (bitta qadoq), bo'lmasa faqat tovar shtrix-kodi (GTIN). */
export function parseGs1Scan(raw) {
  let s = String(raw || '').trim();
  if (!s) return null;
  if (/%[0-9A-Fa-f]{2}/.test(s)) { try { s = decodeURIComponent(s); } catch { /* xom matn */ } }
  s = latinize(s);
  if (/^https?:\/\//i.test(s)) {
    const dl = /\/01\/(\d{14})(?:\/21\/([^/?#]+))?/.exec(s);
    return dl ? build(new Map([['01', dl[1]], ...(dl[2] ? [['21', dl[2]]] : [])])) : null;
  }
  s = s.replace(/^\][A-Za-z][0-9A-Za-z]/, '').replace(/␝/g, GS).replace(/[\r\n\t]+/g, GS)
    .replace(/^[\x1d ]+|[\x1d ]+$/g, '');
  let ais;
  if (/^\(01\)\d{14}/.test(s)) ais = parenAis(s);
  else if (/^01\d{14}./.test(s)) ais = rawAis(s);
  else return null;
  if (!/^\d{14}$/.test(ais.get('01') || '')) return null;
  return build(ais);
}

const noZeros = (v) => String(v || '').replace(/\D/g, '').replace(/^0+/, '');

/** GTIN-14 mahsulot shtrix-kodiga mosmi (EAN-13 = GTIN-14 boshidagi 0 siz) */
export function gtinMatches(gtin, barcode) {
  const g = noZeros(gtin);
  return !!g && g === noZeros(barcode);
}

/** Serverdan shtrix-kod bo'yicha qidirish uchun variantlar: EAN-13, GTIN-14 */
export function gtinVariants(gtin) {
  const g = String(gtin || '');
  return [...new Set([g.replace(/^0/, ''), g, noZeros(g)])].filter(Boolean);
}

/** Mahsulot shu GTIN ga tegishlimi: asosiy, qo'shimcha yoki qadoq (quti/blister) shtrix-kodi */
export function productMatchesGtin(p, gtin) {
  if (!p) return false;
  if (gtinMatches(gtin, p.barcode)) return true;
  if (Array.isArray(p.extra_barcodes) && p.extra_barcodes.some(b => gtinMatches(gtin, b && (b.barcode ?? b)))) return true;
  return Array.isArray(p.units) && p.units.some(u => u && u.barcode && gtinMatches(gtin, u.barcode));
}

/** Klaviatura rejimidagi skaner GS ajratgichini Ctrl+] yoki Alt+0029 (numpad) bilan yuboradi.
 *  Har keydown/keyup hodisasi uchun: 'gs' — buferga GS qo'shish, 'skip' — tugmani buferga yozmaslik, null — oddiy tugma. */
export function createGsDetector() {
  let alt = '';
  return (e) => {
    if (e.type === 'keydown' && e.ctrlKey && (e.key === ']' || e.code === 'BracketRight')) return 'gs';
    if (e.type === 'keydown' && e.altKey && /^\d$/.test(e.key)) { alt += e.key; return 'skip'; }
    if (e.type === 'keyup' && e.key === 'Alt') {
      const n = alt === '' ? -1 : Number(alt);
      alt = '';
      return n === 29 ? 'gs' : null;
    }
    return null;
  };
}
