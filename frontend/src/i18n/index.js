import uz from './uz.js';
import ru from './ru.js';
import en from './en.js';

const translations = { uz, ru, en };

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
    if (stored && translations[stored]) return stored;
  } catch {}
  return 'uz';
}

// Translate function: t('key', { name: 'John' })
export function createTranslator(lang) {
  const dict = translations[lang] || translations.uz;
  return function t(key, vars) {
    let str = dict[key] ?? translations.uz[key] ?? key;
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
