import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { Delete, Lock, LogOut } from 'lucide-react';
import api, { setCurrentBranchId } from '../../api/axios';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';

// R6.1: ofitsiant plansheti (PWA). Menejer "Ofitsiant planshetlari" bo'limida havola yaratadi, planshet
// /waiter?t=<token> bilan ochiladi va tokenni saqlaydi. Xodimlar ismini tanlab PIN bilan almashib kiradi;
// harakatsizlikdan keyin ekran qulflanadi va keyingi xodim kiradi. Sessiya tokeni planshetga bog'langan
// (planshet o'chirilsa darhol yaroqsiz). Ish ekrani: mavjud buyurtmalar sahifasi (zal, chek, menyu, to'lov).

const RestaurantOrders = lazy(() => import('../admin/restaurant/RestaurantOrders'));
const TERM_KEY = 'waiter_terminal';
const SESSION_KEY = 'waiter_session';
const IDLE_MS = 3 * 60 * 1000;

function readTerm() {
  try { return localStorage.getItem(TERM_KEY) || ''; } catch { return ''; }
}

function usePwaManifest() {
  useEffect(() => {
    const link = document.createElement('link');
    link.rel = 'manifest';
    link.href = '/waiter.webmanifest';
    document.head.appendChild(link);
    const prevTitle = document.title;
    document.title = 'E-Code Ofitsiant';
    return () => { link.remove(); document.title = prevTitle; };
  }, []);
}

function PinPad({ person, onBack, onSubmit, error, busy, t }) {
  const [pin, setPin] = useState('');
  const press = d => setPin(p => (p.length < 6 ? p + d : p));
  useEffect(() => { if (error) setPin(''); }, [error]);
  useEffect(() => {
    const onKey = e => {
      if (/^\d$/.test(e.key)) press(e.key);
      else if (e.key === 'Backspace') setPin(p => p.slice(0, -1));
      else if (e.key === 'Enter' && pin.length >= 4) onSubmit(pin);
      else if (e.key === 'Escape') onBack();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pin, onSubmit, onBack]);
  return (
    <div className="w-full max-w-xs mx-auto text-center">
      <div className="text-lg font-bold text-slate-800">{person.name}</div>
      <div className="text-sm text-slate-500 mt-1">{t('restTerm.enterPin')}</div>
      <div className="flex justify-center gap-3 my-5">
        {Array.from({ length: Math.max(4, pin.length) }, (_, i) => (
          <span key={i} className={`w-3.5 h-3.5 rounded-full ${i < pin.length ? 'bg-slate-800' : 'bg-slate-200'}`} />
        ))}
      </div>
      {error && <div className="text-sm text-rose-700 mb-3">{error}</div>}
      <div className="grid grid-cols-3 gap-3">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(d => (
          <button key={d} onClick={() => press(d)} className="h-16 rounded-xl border border-slate-200 bg-white text-2xl font-semibold text-slate-800 active:bg-slate-100">{d}</button>
        ))}
        <button onClick={onBack} className="h-16 rounded-xl text-sm text-slate-500">{t('restTerm.back')}</button>
        <button onClick={() => press('0')} className="h-16 rounded-xl border border-slate-200 bg-white text-2xl font-semibold text-slate-800 active:bg-slate-100">0</button>
        <button onClick={() => setPin(p => p.slice(0, -1))} className="h-16 rounded-xl flex items-center justify-center text-slate-500"><Delete className="w-6 h-6" /></button>
      </div>
      <button disabled={busy || pin.length < 4} onClick={() => onSubmit(pin)}
              className="mt-4 w-full h-12 rounded-xl bg-blue-600 text-white font-semibold disabled:opacity-40">{t('restTerm.signIn')}</button>
    </div>
  );
}

export default function WaiterApp() {
  const { t } = useLang();
  const { user, applyAuthResponse, logout } = useAuth();
  const [term, setTerm] = useState(readTerm);
  const [info, setInfo] = useState(null);         // {terminal, company, branch, branch_id, staff}
  const [loadError, setLoadError] = useState('');
  const [person, setPerson] = useState(null);
  const [pinError, setPinError] = useState('');
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState(() => {
    try { return !!sessionStorage.getItem(SESSION_KEY) && !!localStorage.getItem('access_token'); } catch { return false; }
  });
  const idle = useRef(null);
  usePwaManifest();

  // havoladagi tokenni saqlab, manzildan olib tashlash
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const fromUrl = p.get('t');
    if (fromUrl) {
      try { localStorage.setItem(TERM_KEY, fromUrl); } catch { /* saqlab bo'lmadi */ }
      setTerm(fromUrl);
      window.history.replaceState(null, '', '/waiter');
    }
  }, []);

  const loadStaff = useCallback(() => {
    if (!term) return;
    api.get('/restaurant/terminal/staff', { headers: { 'X-Terminal-Token': term }, _silent: true, _noBranch: true })
      .then(r => { setInfo(r.data); setLoadError(''); })
      .catch(err => {
        if (err.response?.status === 401) {
          try { localStorage.removeItem(TERM_KEY); } catch { /* */ }
          setTerm('');
        }
        setLoadError(err.response?.data?.detail || t('restTerm.failed'));
      });
  }, [term, t]);
  useEffect(() => { if (!working) loadStaff(); }, [loadStaff, working]);

  const lock = useCallback(() => {
    try { sessionStorage.removeItem(SESSION_KEY); } catch { /* */ }
    logout();
    setWorking(false);
    setPerson(null);
    setPinError('');
  }, [logout]);

  // harakatsizlikda qulflash
  useEffect(() => {
    if (!working) return undefined;
    const reset = () => {
      clearTimeout(idle.current);
      idle.current = setTimeout(lock, IDLE_MS);
    };
    const events = ['pointerdown', 'keydown', 'touchstart', 'wheel'];
    events.forEach(e => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => { clearTimeout(idle.current); events.forEach(e => window.removeEventListener(e, reset)); };
  }, [working, lock]);

  const signIn = async pin => {
    setBusy(true);
    setPinError('');
    try {
      const r = await api.post('/restaurant/terminal/login', { user_id: person.id, pin },
                               { headers: { 'X-Terminal-Token': term }, _silent: true, _noBranch: true });
      applyAuthResponse({ access_token: r.data.access_token, user: r.data.user });
      try { localStorage.removeItem('refresh_token'); } catch { /* */ }
      setCurrentBranchId(r.data.branch_id);
      try { sessionStorage.setItem(SESSION_KEY, String(r.data.branch_id)); } catch { /* */ }
      setWorking(true);
    } catch (err) {
      setPinError(err.response?.data?.detail || t('restTerm.failed'));
    } finally { setBusy(false); }
  };

  if (working && user) {
    let branchId = null;
    try { branchId = Number(sessionStorage.getItem(SESSION_KEY)) || null; } catch { /* */ }
    return (
      <div className="min-h-screen bg-slate-50">
        <div className="sticky top-0 z-40 bg-slate-800 text-white px-3 py-2 flex items-center gap-3">
          <span className="font-semibold truncate">{user.name}</span>
          <span className="text-xs text-slate-300 truncate">{info?.terminal}</span>
          <button onClick={lock} className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 text-sm">
            <Lock className="w-4 h-4" />{t('restTerm.lock')}
          </button>
        </div>
        <div className="p-2 sm:p-4">
          <Suspense fallback={<div className="p-8 text-center text-slate-400">...</div>}>
            <RestaurantOrders fixedBranchId={branchId} />
          </Suspense>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <div className="px-4 py-3 bg-slate-800 text-white flex items-center gap-3">
        <span className="font-bold">E-Code</span>
        {info && <span className="text-sm text-slate-300 truncate">{info.company} · {info.branch} · {info.terminal}</span>}
      </div>
      <div className="flex-1 flex items-start justify-center p-4 sm:p-8">
        {!term ? (
          <div className="max-w-md text-center mt-10">
            <div className="text-lg font-bold text-slate-800">{t('restTerm.notConnected')}</div>
            <p className="text-sm text-slate-500 mt-2">{t('restTerm.notConnectedHint')}</p>
            {loadError && <p className="text-sm text-rose-700 mt-3">{loadError}</p>}
          </div>
        ) : person ? (
          <PinPad person={person} busy={busy} error={pinError} t={t} onSubmit={signIn}
                  onBack={() => { setPerson(null); setPinError(''); }} />
        ) : (
          <div className="w-full max-w-3xl">
            <div className="text-center text-sm text-slate-500 mb-4">{t('restTerm.whoAreYou')}</div>
            {loadError && <p className="text-center text-sm text-rose-700 mb-3">{loadError}</p>}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {(info?.staff || []).map(s => (
                <button key={s.id} onClick={() => setPerson(s)}
                        className="h-20 rounded-xl border border-slate-200 bg-white px-3 text-base font-semibold text-slate-800 active:bg-slate-100">
                  {s.name}
                </button>
              ))}
            </div>
            {info && info.staff.length === 0 && <p className="text-center text-sm text-slate-500 mt-6">{t('restTerm.noStaff')}</p>}
            {user && !working && (
              <div className="text-center mt-8">
                <button onClick={lock} className="inline-flex items-center gap-1.5 text-xs text-slate-400"><LogOut className="w-3.5 h-3.5" />{t('restTerm.signOutOther')}</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
