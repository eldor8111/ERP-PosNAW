import uz from './uz.js';

// Tezlik: faqat sukut til (uz) asosiy bundle'da. ru/en (~700 KB) alohida chunk bo'lib, shu til
// tanlanganda yuklanadi (main.jsx saqlangan tilni ilova chizilishidan oldin yuklaydi).
const translations = { uz };
const LOADERS = {
  ru: () => import('./ru.js'),
  en: () => import('./en.js'),
};
const _pending = {};

export function isLangLoaded(code) {
  return Boolean(translations[code]);
}

/** Til lug'atini yuklaydi (bir marta). Noma'lum til yoki xato — uz ishlatiladi (rad etilmaydi). */
export function loadLang(code) {
  if (translations[code] || !LOADERS[code]) return Promise.resolve();
  if (!_pending[code]) {
    _pending[code] = LOADERS[code]()
      .then((m) => { translations[code] = m.default; })
      .catch(() => {})
      .finally(() => { delete _pending[code]; });
  }
  return _pending[code];
}

// Supported languages
export const LANGUAGES = [
  { code: 'uz', label: "O'zbek", flag: '🇺🇿', short: 'UZ' },
  { code: 'ru', label: 'Русский', flag: '🇷🇺', short: 'RU' },
  { code: 'en', label: 'English', flag: '🇬🇧', short: 'EN' },
];

// Get stored lang or default to 'uz'
export function getStoredLang() {
  try {
    const stored = localStorage.getItem('app_language');
    if (stored && (translations[stored] || LOADERS[stored])) return stored;
  } catch {}
  return 'uz';
}

// Translate function: t('key', { name: 'John' })
// Ko'plik (T3.5): vars.count uzatilsa `key.one/few/many/other` qidiriladi (Intl.PluralRules);
// topilmasa eski `key` ishlatiladi.
const _pluralRules = {};
function pluralRule(lang, count) {
  try {
    const pr = _pluralRules[lang] || (_pluralRules[lang] = new Intl.PluralRules(lang));
    return pr.select(Number(count));
  } catch {
    return 'other';
  }
}

export function createTranslator(lang) {
  const dict = translations[lang] || translations.uz;
  return function t(key, vars) {
    let str;
    if (vars && vars.count !== undefined && vars.count !== null) {
      str = dict[`${key}.${pluralRule(lang, vars.count)}`];
    }
    str = str ?? dict[key] ?? translations.uz[key] ?? key;
    if (vars) {
      Object.entries(vars).forEach(([k, v]) => {
        str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), v ?? '');
      });
    }
    return str;
  };
}

export default translations;

// Re-export context hooks so pages can use:
//   import { useLang } from '../i18n'
export { useLang, LangProvider } from '../context/LangContext.jsx';
