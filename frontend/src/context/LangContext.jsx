import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { getStoredLang, createTranslator, LANGUAGES } from '../i18n/index.js';

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(getStoredLang);

  const setLang = useCallback((code) => {
    setLangState(code);
    try { localStorage.setItem('app_language', code); } catch {}
    // Update html lang attribute
    document.documentElement.lang = code;
  }, []);

  const t = useMemo(() => createTranslator(lang), [lang]);

  const value = useMemo(() => ({ lang, setLang, t, LANGUAGES }), [lang, setLang, t]);

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang() {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error('useLang must be used inside <LangProvider>');
  return ctx;
}

export default LangContext;
