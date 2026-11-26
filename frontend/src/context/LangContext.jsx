import { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import { getStoredLang, createTranslator, LANGUAGES, loadLang, isLangLoaded } from '../i18n/index.js';

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(getStoredLang);

  const setLang = useCallback((code) => {
    try { localStorage.setItem('app_language', code); } catch {}
    // Til lug'ati alohida chunk: yuklangach almashtiriladi (yuklanguncha joriy til qoladi)
    loadLang(code).then(() => {
      setLangState(code);
      document.documentElement.lang = code;
    });
  }, []);

  // Boshqa kirish nuqtalari (mobil ilova) uchun: saqlangan til lug'ati hali yuklanmagan bo'lsa yuklab qayta chiziladi
  const [loadedTick, setLoadedTick] = useState(0);
  useEffect(() => {
    if (!isLangLoaded(lang)) loadLang(lang).then(() => setLoadedTick((n) => n + 1));
  }, [lang]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const t = useMemo(() => createTranslator(lang), [lang, loadedTick]);

  const value = useMemo(() => ({ lang, setLang, t, LANGUAGES }), [lang, setLang, t]);

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang() {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error('useLang must be used inside <LangProvider>');
  return ctx;
}

export default LangContext;
