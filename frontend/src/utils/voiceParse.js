// Ovoz bilan kiritish: tanilgan matnni katak qiymatiga aylantirish.
// O'zbekcha (lotin va kirill) hamda ruscha. Har bir katak alohida aytiladi, shuning uchun bu yerda
// kalit so'z qidirilmaydi — faqat "shu matn son / birlik / kategoriya / buyruqmi" degan savolga javob beriladi.
// Tushunilmagan matn uchun har doim null qaytadi: noto'g'ri qiymatdan ko'ra bo'sh katak yaxshi.

/* ─── Matnni tayyorlash ─────────────────────────────── */
const APOS = /[‘’ʻʼ`´']/g;

export const normText = (s) => String(s || '')
  .toLowerCase()
  .replace(APOS, "'")
  .replace(/ё/g, 'е')
  .replace(/[!?;:«»"()]/g, ' ')
  .replace(/\.(?!\d)|(?<!\d)\./g, ' ')   // nuqta faqat raqamlar orasida qoladi ("1.5", "12.500")
  .replace(/\s+/g, ' ')
  .trim();

// O'zbek kirill → lotin (ruscha so'zlar avval asl holida tekshiriladi)
const CYR = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ж: 'j', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l',
  м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'x', ц: 's', ч: 'ch',
  ш: 'sh', щ: 'sh', ё: 'yo', ъ: "'", ь: '', ы: 'i', э: 'e', ю: 'yu', я: 'ya', ў: "o'", қ: 'q', ғ: "g'", ҳ: 'h',
};
const hasCyr = (w) => /[а-яўқғҳ]/.test(w);
export function translitUz(w) {
  if (!hasCyr(w)) return w;
  let out = '';
  for (let i = 0; i < w.length; i++) {
    const ch = w[i];
    // so'z boshida yoki unlidan keyin: е → ye ("еди" → "yedi")
    if (ch === 'е' && (i === 0 || /[аеиоуўэюяъь\s]/.test(w[i - 1]))) { out += 'ye'; continue; }
    out += CYR[ch] ?? ch;
  }
  return out;
}

/* ─── Lug'atlar ─────────────────────────────────────── */
const UZ_NUM = {
  nol: 0, nul: 0, bir: 1, ikki: 2, uch: 3, "to'rt": 4, tort: 4, turt: 4, besh: 5, olti: 6,
  yetti: 7, etti: 7, sakkiz: 8, sakiz: 8, "to'qqiz": 9, toqqiz: 9, "to'qiz": 9, toqiz: 9,
  "o'n": 10, on: 10, yigirma: 20, igirma: 20, "o'ttiz": 30, ottiz: 30, qirq: 40, ellik: 50,
  oltmish: 60, yetmish: 70, etmish: 70, sakson: 80, "to'qson": 90, toqson: 90,
};
const RU_NUM = {
  ноль: 0, нуль: 0, один: 1, одна: 1, одно: 1, одну: 1, два: 2, две: 2, три: 3, четыре: 4, пять: 5,
  шесть: 6, семь: 7, восемь: 8, девять: 9, десять: 10, одиннадцать: 11, двенадцать: 12,
  тринадцать: 13, четырнадцать: 14, пятнадцать: 15, шестнадцать: 16, семнадцать: 17,
  восемнадцать: 18, девятнадцать: 19, двадцать: 20, тридцать: 30, сорок: 40, пятьдесят: 50,
  шестьдесят: 60, семьдесят: 70, восемьдесят: 80, девяносто: 90, сто: 100, двести: 200,
  триста: 300, четыреста: 400, пятьсот: 500, шестьсот: 600, семьсот: 700, восемьсот: 800,
  девятьсот: 900,
};
const MULT = {
  yuz: 100, ming: 1e3, million: 1e6, milion: 1e6, millyon: 1e6, milyon: 1e6, mln: 1e6,
  milliard: 1e9, mlrd: 1e9,
  тысяча: 1e3, тысячи: 1e3, тысяч: 1e3, тысячу: 1e3, тыс: 1e3, миллион: 1e6, миллиона: 1e6,
  миллионов: 1e6, млн: 1e6, миллиард: 1e9, миллиарда: 1e9, миллиардов: 1e9, млрд: 1e9,
};
const HALF = new Set(['yarim', 'половина', 'половиной']);
const ONE_HALF = new Set(['полтора', 'полторы']);
const POINT = new Set(['butun', 'запятая', 'точка', 'целых', 'целая', 'целой']);
const FRACTION_SCALE = { десятых: 10, десятая: 10, сотых: 100, сотая: 100, тысячных: 1000, тысячная: 1000 };

const CURRENCY_WORDS = [
  { code: 'USD', re: /^(dollar|dollor)(lik|dan|ga)?$|^(доллар|доллара|долларов|usd|\$)$/ },
  { code: 'EUR', re: /^(yevro|evro|euro|евро|eur|€)$/ },
  { code: 'RUB', re: /^(rubl|rubli|рубль|рубля|рублей|rub|₽)$/ },
  { code: 'UZS', re: /^(so'm|som|sum)(lik|dan|ga|lab)?$|^(сум|сума|сумов|uzs)$/ },
];
// Son yonida aytilsa ham qiymatga ta'sir qilmaydigan so'zlar
const FILLER = new Set([
  'narxi', 'narx', 'narxda', 'цена', 'ценой', 'по', 'и', 'va', 'dan', 'ga', 'ta', 'lik', 'c', 'с',
  'taxminan', 'faqat', 'jami',
]);

const UNITS = [
  { unit: 'kg', short: 'kg', re: /^(kilo|kg|kgs|kilogramm?|kilogrammlik|kilogramlik|kilolik|kilolab|kilosi|kilodan|кило|кг|килограмм?|килограмма|килограммов)$/ },
  { unit: 'dona', short: 'dona', re: /^(dona|donalab|donasi|donalik|donadan|ta|shtuk|shtuka|штук[аи]?|шт|штучно|штучный)$/ },
  { unit: 'litr', short: 'l', re: /^(litr|litrlik|litrlab|litri|litrdan|l|литр(?:а|ов)?|л)$/ },
  { unit: 'metr', short: 'm', re: /^(metr|metrlik|metrlab|metri|metrdan|m|метр(?:а|ов)?|м)$/ },
];
// Faqat mahsulot nomidagi o'lchamlar uchun (tizimning o'lchov birligi emas)
const NAME_MEASURES = [
  ...UNITS.filter(u => u.unit !== 'dona'),
  { short: 'g', re: /^(gramm?|gr|g|грамм?|граммов|гр|г)$/ },
  { short: 'ml', re: /^(millilitr|ml|миллилитр(?:а|ов)?|мл)$/ },
  { short: 'sm', re: /^(santimetr|sm|сантиметр(?:а|ов)?|см)$/ },
  { short: 'mm', re: /^(millimetr|mm|миллиметр(?:а|ов)?|мм)$/ },
  { short: '%', re: /^(foiz|foizli|%|процент|процента|процентов)$/ },
  { short: 'dona', re: /^(dona|ta|штук[аи]?|шт)$/ },
];

const SUFFIXES = ['tadan', 'tasi', 'dan', 'lab', 'lik', 'ga', 'ta', 'ni'];
const ORDINAL = ['inchi', 'nchi'];   // "o'n ikkinchi" — Chrome tartib son deb eshitgan bo'lsa

function lookupWord(raw, ordinal = false) {
  const forms = [raw];
  const lat = translitUz(raw);
  if (lat !== raw) forms.push(lat);
  for (const w of forms) {
    if (w in RU_NUM) return { t: 'num', v: RU_NUM[w] };
    if (w in UZ_NUM) return { t: 'num', v: UZ_NUM[w] };
    if (w in MULT) return { t: 'mult', v: MULT[w] };
    if (HALF.has(w)) return { t: 'half' };
    if (ONE_HALF.has(w)) return { t: 'onehalf' };
    if (POINT.has(w)) return { t: 'point' };
    if (w in FRACTION_SCALE) return { t: 'scale', v: FRACTION_SCALE[w] };
    // "ellikta", "mingdan", "ikkinchi" — qo'shimcha olib tashlanadi
    for (const s of ordinal ? [...SUFFIXES, ...ORDINAL] : SUFFIXES) {
      if (w.length > s.length + 1 && w.endsWith(s)) {
        const base = w.slice(0, -s.length);
        if (base in UZ_NUM) return { t: 'num', v: UZ_NUM[base] };
        if (base in MULT) return { t: 'mult', v: MULT[base] };
        if (HALF.has(base)) return { t: 'half' };
      }
    }
  }
  return null;
}

const unitOfWord = (w) => {
  const lat = translitUz(w);
  return UNITS.find(u => u.re.test(w) || u.re.test(lat)) || null;
};
const currencyOfWord = (w) => {
  const lat = translitUz(w);
  return (CURRENCY_WORDS.find(c => c.re.test(w) || c.re.test(lat)) || {}).code || null;
};
const isFiller = (w) => FILLER.has(w) || FILLER.has(translitUz(w)) || !!unitOfWord(w) || !!currencyOfWord(w) || w === ',';

/* ─── Sonlar ─────────────────────────────────────────── */
function prepareDigits(text, kind) {
  let s = normText(text).replace(/(\d)\s*-\s*(?=[a-zа-я'])/g, '$1');      // "50-ta" → "50ta"
  s = s.replace(/\b\d{1,3}(?:[  ]\d{3})+\b/g, m => m.replace(/[  ]/g, ''));   // "12 500"
  if (kind === 'price') {
    // narxda "12.500" / "12,500" — minglik ajratgich
    s = s.replace(/\b\d{1,3}(?:[.,]\d{3})+\b/g, m => m.replace(/[.,]/g, ''));
  }
  s = s.replace(/(\d),(\d)/g, '$1.$2');                                     // "1,5" → "1.5"
  s = s.replace(/(\d)([a-zа-я'%$€₽])/g, '$1 $2');                         // "50ta" → "50 ta"
  return s.replace(/,/g, ' ').replace(/\s+/g, ' ').trim();
}

// Butun son qismi (kasr qismisiz) — so'zlar ro'yxati bo'yicha
function parseIntegerWords(words, ordinal) {
  let total = 0, cur = 0, last = null, seen = false, prevDigits = false;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (/^\d+(?:\.\d+)?$/.test(w)) {
      if (prevDigits) return { ok: false };                      // "5500 100" — ikki alohida son
      cur += parseFloat(w);
      prevDigits = true; seen = true; last = 'num';
      continue;
    }
    const x = lookupWord(w, ordinal);
    if (!x) {
      if (isFiller(w)) continue;          // to'ldiruvchi raqamlarni ajratib turadi: "1 litr 3.2" — bitta son emas
      return { ok: false };
    }
    prevDigits = false;
    if (x.t === 'num') { cur += x.v; last = 'num'; seen = true; continue; }
    if (x.t === 'mult') {
      if (x.v === 100) cur = (cur || 1) * 100;
      else { total += (cur || 1) * x.v; cur = 0; }
      last = x.v; seen = true;
      continue;
    }
    if (x.t === 'half') {
      // "bir yarim" = 1.5, "ming yarim" = 1500, "yuz yarim" = 150
      if (typeof last === 'number' && cur === 0 && last >= 1000) total += last / 2;
      else if (last === 100) cur += 50;
      else cur += 0.5;
      seen = true;
      continue;
    }
    if (x.t === 'onehalf') { cur += 1.5; seen = true; continue; }
    if (x.t === 'point' || x.t === 'scale') return { ok: true, seen, value: total + cur, rest: words.slice(i) };
  }
  return { ok: true, seen, value: total + cur, rest: [] };
}

/**
 * Matn butunligicha bitta son bo'lsa — o'sha son, aks holda null.
 * kind: 'price' (minglik ajratgich: "12.500" → 12500) yoki 'qty' ("1,5" → 1.5).
 */
export function parseNumber(text, { kind = 'price', ordinal = true } = {}) {
  const s = prepareDigits(text, kind);
  if (!s) return null;
  const words = s.split(' ');
  const head = parseIntegerWords(words, ordinal);
  if (!head.ok || !head.seen) return null;
  let value = head.value;
  if (head.rest.length) {
    // Kasr: "o'n ikki butun besh" → 12.5, "две целых пять десятых" → 2.5, "два запятая двадцать пять" → 2.25
    const rest = head.rest.slice(1);
    let scale = null;
    const fracWords = rest.filter(w => {
      const x = lookupWord(w);
      if (x && x.t === 'scale') { scale = x.v; return false; }
      return true;
    });
    const frac = parseIntegerWords(fracWords, ordinal);
    if (!frac.ok || !frac.seen || frac.rest.length) return null;
    const f = Math.round(frac.value);
    value += scale ? f / scale : f / 10 ** String(f).length;
  }
  return Number.isFinite(value) ? Math.round(value * 1000) / 1000 : null;
}

/** Bir nechta tanilgan variantdan birinchi son bo'lib o'qiladiganini tanlaydi. */
export function pickNumber(alternatives, opts = {}) {
  // Avval aniq son sifatida, keyin — tartib sonni ham qabul qilib
  for (const ordinal of [false, true]) {
    for (const a of alternatives || []) {
      const n = parseNumber(a, { ...opts, ordinal });
      if (n != null) return n;
    }
  }
  return null;
}

/** Aytilgan valyuta: 'USD' | 'EUR' | 'RUB' | 'UZS' | null. */
export function parseCurrency(text) {
  for (const w of prepareDigits(text, 'price').split(' ')) {
    const c = currencyOfWord(w);
    if (c) return c;
  }
  return null;
}

/* ─── O'lchov birligi ───────────────────────────────── */
export function parseUnit(text) {
  for (const w of normText(text).split(' ')) {
    const u = unitOfWord(w);
    if (u) return u.unit;
  }
  return null;
}

export const pickUnit = (alternatives) => {
  for (const a of alternatives || []) {
    const u = parseUnit(a);
    if (u) return u;
  }
  return null;
};

/* ─── Kategoriya ────────────────────────────────────── */
function levenshtein(a, b) {
  if (a === b) return 0;
  const m = a.length, n = b.length;
  if (!m) return n;
  if (!n) return m;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[n];
}
const similarity = (a, b) => 1 - levenshtein(a, b) / Math.max(a.length, b.length, 1);

// Qo'shimchalarsiz o'zak: "mevalar" → "meva", "ichimliklari" → "ichimlik", "фрукты" → "фрукт"
function stem(w) {
  let s = translitUz(w);
  for (const suf of ['larimiz', 'lari', 'lar', 'imiz', 'ning']) {
    if (s.length > suf.length + 2 && s.endsWith(suf)) { s = s.slice(0, -suf.length); break; }
  }
  // ruscha ko'plik/rod qo'shimchalari ("фрукты" → "frukt"); qisqa so'zlarga tegilmaydi
  if (hasCyr(w) && s.length > 4) s = s.replace(/(aya|ie|oe|iy|oy|ya|i|a|y)$/, '');
  return s;
}
const words = (s) => normText(s).replace(/[,.-]/g, ' ').split(' ').filter(Boolean);

function categoryScore(spoken, name) {
  const a = normText(spoken), b = normText(name);
  if (!a || !b) return 0;
  if (a === b) return 1;
  const sa = words(a).map(stem), sb = words(b).map(stem);
  if (sa.join(' ') === sb.join(' ')) return 0.98;
  // So'zma-so'z: aytilgan har bir so'z kategoriyadagi biror so'zga mos kelishi kerak
  const wordMatch = (x, y) => x === y || (x.length >= 4 && y.startsWith(x)) || (y.length >= 4 && x.startsWith(y)) || similarity(x, y) >= 0.8;
  const covered = sa.filter(x => sb.some(y => wordMatch(x, y))).length;
  // Aytilgan hamma so'z kategoriyada bor: "sut" → "Sut mahsulotlari"
  if (covered === sa.length) return 0.75 + 0.23 * Math.min(1, sa.length / sb.length);
  return similarity(sa.join(' '), sb.join(' ')) * 0.9;
}

/** Aytilgan so'zga eng yaqin kategoriya ({id, name}) yoki null (topilmasa yoki ikki xil talqin bo'lsa). */
export function matchCategory(text, categories) {
  if (!normText(text) || !categories?.length) return null;
  const scored = categories
    .map(c => ({ c, s: categoryScore(text, c.name) }))
    .sort((x, y) => y.s - x.s);
  const [best, second] = scored;
  if (!best || best.s < 0.7) return null;
  if (second && best.s < 0.97 && best.s - second.s < 0.03) return null;   // taxmin qilinmaydi
  return best.c;
}

export const pickCategory = (alternatives, categories) => {
  for (const a of alternatives || []) {
    const c = matchCategory(a, categories);
    if (c) return c;
  }
  return null;
};

/* ─── Buyruqlar ─────────────────────────────────────── */
const COMMANDS = [
  { cmd: 'skip', re: /^(o'tkaz|otkaz|o'tkazib yubor|o'tkazvor|keyingi|keyingisi|keyingisiga|bo'sh|bosh|bo'sh qoldir|kerak emas|yo'q|yoq|дальше|далее|пропусти|пропустить|следующий|следующее|пусто|нет)$/ },
  { cmd: 'back', re: /^(orqaga|ortga|oldingi|oldingisi|назад|вернись|вернуться|предыдущий)$/ },
  { cmd: 'undo', re: /^(xato|bekor|bekor qil|noto'g'ri|notog'ri|qaytadan|ошибка|отмена|отменить|неправильно|заново)$/ },
  { cmd: 'newRow', re: /^(yangi|yangi qator|yangisi|yangi mahsulot|keyingi mahsulot|новый|новая|новая строка|новый товар|следующий товар)$/ },
  { cmd: 'deleteRow', re: /^(o'chir|ochir|o'chirish|qatorni o'chir|удали|удалить|удалить строку)$/ },
  { cmd: 'stop', re: /^(tamom|tamam|to'xta|toxta|to'xtat|bo'ldi|boldi|tugadi|yetarli|стоп|хватит|всё|все|конец|достаточно)$/ },
];

/** Butun gap buyruq bo'lsa — buyruq nomi, aks holda null ("olma o'chir" buyruq emas). */
export function parseCommand(text) {
  const t = normText(text).replace(/,/g, '').trim();
  if (!t) return null;
  const lat = t.split(' ').map(translitUz).join(' ');
  const hit = COMMANDS.find(c => c.re.test(t) || c.re.test(lat));
  return hit ? hit.cmd : null;
}

export const pickCommand = (alternatives) => {
  for (const a of alternatives || []) {
    const c = parseCommand(a);
    if (c) return c;
  }
  return null;
};

/* ─── Mahsulot nomi ─────────────────────────────────── */
const NAME_PREFIX = /^(mahsulot nomi|mahsulotning nomi|nomi|mahsulot|tovar|название товара|название|товар)\s+/i;
const measureOf = (w) => {
  const lat = translitUz(w);
  return NAME_MEASURES.find(m => m.re.test(w) || m.re.test(lat)) || null;
};

/**
 * Aytilgan nomni toza ko'rinishga keltiradi: "coca cola bir yarim litr" → "Coca cola 1.5 l",
 * "sut uch butun ikki foiz" → "Sut 3.2%". Son so'zlari faqat o'lchov oldida raqamga aylanadi
 * ("Bir martalik stakan" o'zgarmaydi).
 */
export function cleanName(text) {
  let s = String(text || '')
    .replace(APOS, "'")
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[\s.,!?-]+|[\s.,!?-]+$/g, '');
  const stripped = s.replace(NAME_PREFIX, '');
  if (stripped.trim()) s = stripped;
  if (!s) return '';

  const toks = s.split(' ');
  const out = [];
  for (let i = 0; i < toks.length; i++) {
    // eng uzun "son so'zlari + o'lchov" ketma-ketligini qidiramiz
    let done = false;
    for (let j = i + 1; j < Math.min(toks.length, i + 9); j++) {
      const m = measureOf(toks[j].toLowerCase().replace(/[.,]$/, ''));
      if (!m) continue;
      const numText = toks.slice(i, j).join(' ');
      const n = parseNumber(numText, { kind: 'qty' });
      if (n == null) continue;
      out.push(m.short === '%' ? `${n}%` : `${n} ${m.short}`);
      i = j;
      done = true;
      break;
    }
    if (!done) out.push(toks[i]);
  }
  s = out.join(' ').replace(/\s+%/g, '%');
  return s ? s[0].toLocaleUpperCase() + s.slice(1) : '';
}
