/**
 * Uzbek Kirill ↔ Lotin transliteratsiya utility
 * Kiril yozib izlasa Lotin topadi, Lotin yozib izlasa Kiril topadi.
 */

const CYR_TO_LAT = {
  'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'j','з':'z',
  'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
  'с':'s','т':'t','у':'u','ф':'f','х':'x','ц':'ts','ч':'ch','ш':'sh',
  'щ':'sh','ъ':"'",'ы':'i','ь':'','э':'e','ю':'yu','я':'ya',
  'қ':'q','ғ':"g'",'ҳ':'h','ў':"o'",
};

// Uzunroq juftlar oldin tekshirilsin (ch, sh, o', g' ...)
const LAT_TO_CYR = [
  ["o'", 'ў'], ["g'", 'ғ'],
  ['ch', 'ч'], ['sh', 'ш'],
  ['yo', 'ё'], ['yu', 'ю'], ['ya', 'я'], ['ts', 'ц'],
  ['a','а'], ['b','б'], ['d','д'], ['e','е'], ['f','ф'], ['g','г'],
  ['h','х'], ['i','и'], ['j','ж'], ['k','к'], ['l','л'], ['m','м'],
  ['n','н'], ['o','о'], ['p','п'], ['q','қ'], ['r','р'], ['s','с'],
  ['t','т'], ['u','у'], ['v','в'], ['x','х'], ['y','й'], ['z','з'],
];

function cyrToLat(text) {
  return text.toLowerCase().split('').map(c => CYR_TO_LAT[c] ?? c).join('');
}

function latToCyr(text) {
  let s = text.toLowerCase();
  for (const [from, to] of LAT_TO_CYR) {
    s = s.split(from).join(to);
  }
  return s;
}

const RE_CYR = /[а-яёА-ЯЁқғҳўҚҒҲЎ]/u;
const RE_LAT = /[a-zA-Z]/;

/** Berilgan so'zning barcha variantlarini qaytaradi (asl + transliteratsiya) */
export function searchVariants(query) {
  const q = (query || '').toLowerCase().trim();
  if (!q) return [];
  const set = new Set([q]);
  if (RE_CYR.test(q)) set.add(cyrToLat(q));
  if (RE_LAT.test(q)) set.add(latToCyr(q));
  return [...set];
}

/**
 * haystack ichida query (yoki uning transliteratsiyasi) bor-yo'qligini tekshiradi.
 * @param {string} haystack - izlanadigan matn
 * @param {string} query    - foydalanuvchi kiritgan so'z
 */
export function matchesSearch(haystack, query) {
  if (!haystack || !query) return false;
  const h = haystack.toLowerCase();
  return searchVariants(query).some(v => h.includes(v));
}
