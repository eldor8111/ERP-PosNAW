// "Ko'p mahsulot qo'shish" oynasi uchun ovoz bilan kiritish.
// Har bir katak alohida aytiladi: joriy katak ko'k ramkada, qiymat tushgach keyingisiga o'tiladi.
// Nutq brauzerning o'zida (Chrome Web Speech API) tanib olinadi — server yuklanmaydi.
// Kataklar Products.jsx da data-voice-cell="<qator kaliti>:<maydon>" bilan belgilangan.

import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../../../api/axios';
import {
  normText, pickNumber, parseCurrency, pickUnit, pickCategory, pickCommand, cleanName,
} from '../../../utils/voiceParse';

const SR = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;

const ALL_COLS = ['name', 'sale_price', 'wholesale_price', 'cost_price', 'unit', 'category_id', 'initial_stock'];
const REQUIRED_COLS = ['name', 'sale_price'];
const NUMBER_COLS = ['sale_price', 'wholesale_price', 'cost_price', 'initial_stock'];
const PRICE_COLS = ['sale_price', 'wholesale_price', 'cost_price'];
const EMPTY_VALUE = { name: '', sale_price: '', wholesale_price: '', cost_price: '', unit: 'dona', category_id: '', initial_stock: '' };
const MAX_VALUE = 10_000_000_000;
const SETTINGS_KEY = 'bulk_voice_settings';
// autoAdvance: qiymat tushgach keyingi katakka o'zi o'tsinmi (standart — yo'q: foydalanuvchi o'zi bosadi)
const DEFAULT_SETTINGS = { cols: ALL_COLS, lang: 'uz-UZ', beep: true, autoAdvance: false };

const CURSOR_STYLE = '0 0 0 3px #3b82f6';
const FLASH = { ok: '0 0 0 3px #10b981', err: '0 0 0 3px #ef4444' };

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null');
    if (!s) return DEFAULT_SETTINGS;
    const cols = ALL_COLS.filter(c => REQUIRED_COLS.includes(c) || (s.cols || []).includes(c));
    return { cols, lang: s.lang === 'ru-RU' ? 'ru-RU' : 'uz-UZ', beep: s.beep !== false, autoAdvance: s.autoAdvance === true };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

const cellEl = (key, col) => (key ? document.querySelector(`[data-voice-cell="${key}:${col}"]`) : null);

export default function useBulkVoice({ enabled, rows, setRows, emptyRow, categories, currencies, t }) {
  const [active, setActive] = useState(false);
  const [cursor, setCursorState] = useState(null);        // { key, col }
  const [interim, setInterim] = useState('');
  const [message, setMessage] = useState(null);           // { type: ok|warn|err|info, text }
  const [settings, setSettings] = useState(loadSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [nameChecks, setNameChecks] = useState({});       // rowKey -> { name, existing }

  // Nutq hodisalari eski render qiymatlarini ko'rmasligi uchun — ref'lar
  const rowsRef = useRef(rows);
  const cursorRef = useRef(null);
  const settingsRef = useRef(settings);
  const categoriesRef = useRef(categories);
  const currenciesRef = useRef(currencies);
  const activeRef = useRef(false);
  const recRef = useRef(null);
  const audioRef = useRef(null);
  const failsRef = useRef([]);
  const lastRowKeyRef = useRef(null);
  rowsRef.current = rows;
  settingsRef.current = settings;
  categoriesRef.current = categories;
  currenciesRef.current = currencies || [];

  const label = useCallback((col) => ({
    name: t('product.bulkColName'),
    sale_price: t('product.bulkColRetail'),
    wholesale_price: t('product.wholesalePriceLabel'),
    cost_price: t('product.costPriceLabel'),
    unit: t('product.unit'),
    category_id: t('product.category'),
    initial_stock: t('product.currentStock'),
  }[col] || col), [t]);

  const setCursor = useCallback((c) => {
    cursorRef.current = c;
    setCursorState(c);
  }, []);

  const beep = useCallback((kind) => {
    if (!settingsRef.current.beep) return;
    try {
      const ctx = audioRef.current || (audioRef.current = new (window.AudioContext || window.webkitAudioContext)());
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = kind === 'ok' ? 880 : 240;
      gain.gain.value = 0.08;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + (kind === 'ok' ? 0.08 : 0.22));
    } catch { /* ovozsiz ham ishlaydi */ }
  }, []);

  const flash = useCallback((key, col, kind) => {
    const el = cellEl(key, col);
    if (!el) return;
    el.dataset.voiceFlash = '1';
    el.style.boxShadow = FLASH[kind];
    setTimeout(() => {
      delete el.dataset.voiceFlash;
      const c = cursorRef.current;
      el.style.boxShadow = activeRef.current && c && c.key === key && c.col === col ? CURSOR_STYLE : '';
    }, 700);
  }, []);

  const say = useCallback((type, text) => setMessage({ type, text }), []);

  /* ─── Joriy katak ramkasi ─── */
  useEffect(() => {
    if (!active || !cursor) return undefined;
    const el = cellEl(cursor.key, cursor.col);
    if (!el) return undefined;
    if (!el.dataset.voiceFlash) el.style.boxShadow = CURSOR_STYLE;
    el.style.borderRadius = '0.5rem';
    el.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    return () => { if (!el.dataset.voiceFlash) el.style.boxShadow = ''; };   // yashil/qizil yonish o'z vaqtida o'chadi
  }, [active, cursor, rows]);

  /* ─── Qatorlar bilan ishlash ─── */
  const updateRow = (key, field, value) =>
    setRows(rs => rs.map(r => (r._key === key ? { ...r, [field]: value } : r)));

  const openNextRow = (fromKey) => {
    const rs = rowsRef.current;
    const idx = rs.findIndex(r => r._key === fromKey);
    const next = rs[idx + 1];
    if (next && !next.name.trim()) {
      setCursor({ key: next._key, col: 'name' });
      return;
    }
    const row = emptyRow();
    setRows(prev => {
      const i = prev.findIndex(r => r._key === fromKey);
      const copy = [...prev];
      copy.splice(i < 0 ? copy.length : i + 1, 0, row);
      return copy;
    });
    setCursor({ key: row._key, col: 'name' });
  };

  const advance = (key, col) => {
    const cols = settingsRef.current.cols;
    const i = cols.indexOf(col);
    if (i >= 0 && i < cols.length - 1) setCursor({ key, col: cols[i + 1] });
    else openNextRow(key);
  };

  const prevCell = (key, col) => {
    const cols = settingsRef.current.cols;
    const i = cols.indexOf(col);
    if (i > 0) return { key, col: cols[i - 1] };
    const rs = rowsRef.current;
    const r = rs.findIndex(x => x._key === key);
    return r > 0 ? { key: rs[r - 1]._key, col: cols[cols.length - 1] } : null;
  };

  const goBack = (key, col) => {
    const p = prevCell(key, col);
    if (p) setCursor(p);
  };

  // «xato»: oldingi katak tozalanadi va unga qaytiladi
  const undo = (key, col) => {
    const p = prevCell(key, col);
    if (!p) return;
    updateRow(p.key, p.col, EMPTY_VALUE[p.col] ?? '');
    if (PRICE_COLS.includes(p.col)) updateRow(p.key, `${p.col}_cur`, '');
    setCursor(p);
    say('info', `⟲ ${label(p.col)}`);
  };

  const deleteRow = (key) => {
    const rs = rowsRef.current;
    const idx = rs.findIndex(r => r._key === key);
    if (rs.length <= 1) {
      const row = emptyRow();
      setRows([row]);
      setCursor({ key: row._key, col: 'name' });
    } else {
      setRows(prev => prev.filter(r => r._key !== key));
      const target = rs[idx - 1] || rs[idx + 1];
      setCursor({ key: target._key, col: 'name' });
    }
    say('info', t('voice.rowDeleted'));
  };

  // Aytilgan nom bazada yoki jadvalning boshqa qatorida bormi
  const checkName = async (key, name) => {
    const n = normText(name);
    const dupInTable = rowsRef.current.some(r => r._key !== key && normText(r.name) === n);
    let existing = null;
    try {
      const { data } = await api.get('/products/', { params: { search: name, limit: 20 }, _suppressToast: true });
      const list = Array.isArray(data) ? data : (data?.items || []);
      existing = list.find(p => normText(p.name) === n)?.name || null;
    } catch { /* tekshirib bo'lmasa — saqlashda backend baribir rad etadi */ }
    setNameChecks(m => ({ ...m, [key]: { name, existing, dupInTable } }));
    if (existing) { say('warn', t('voice.existsInDb', { name: existing })); beep('err'); }
    else if (dupInTable) { say('warn', t('voice.dupInTable')); beep('err'); }
  };

  const checkPrices = (key, col, value) => {
    const row = rowsRef.current.find(r => r._key === key);
    if (!row) return;
    const sale = col === 'sale_price' ? value : Number(row.sale_price);
    const cost = col === 'cost_price' ? value : Number(row.cost_price);
    if (row.sale_price_cur || row.cost_price_cur) return;   // turli valyutadagi narxlar solishtirilmaydi
    if (sale > 0 && cost > 0 && sale < cost) say('warn', t('voice.retailBelowCost'));
  };

  /* ─── Bitta aytilgan gapni qayta ishlash ─── */
  const handleUtterance = (alts) => {
    if (!alts.length) return;
    const heard = alts[0];
    let cur = cursorRef.current;
    if (!cur || !rowsRef.current.some(r => r._key === cur.key)) {
      const first = rowsRef.current.find(r => !r.name.trim()) || rowsRef.current[rowsRef.current.length - 1];
      cur = { key: first._key, col: 'name' };
      setCursor(cur);
    }
    const { key, col } = cur;

    const cmd = pickCommand(alts);
    if (cmd) {
      if (cmd === 'skip') { advance(key, col); say('info', `↷ ${label(col)}`); }
      else if (cmd === 'back') goBack(key, col);
      else if (cmd === 'undo') undo(key, col);
      else if (cmd === 'newRow') openNextRow(key);
      else if (cmd === 'deleteRow') deleteRow(key);
      else if (cmd === 'stop') stop(t('voice.stopped'));
      beep('ok');
      return;
    }

    const fail = (text) => { say('err', text); beep('err'); flash(key, col, 'err'); };
    // Qiymat katakka tushadi; keyingi katakka faqat sozlamada yoqilgan bo'lsa o'tiladi —
    // aks holda ramka shu yerda qoladi (qayta aytilsa almashadi), keyingisini foydalanuvchi o'zi bosadi
    const done = (shown) => {
      beep('ok');
      flash(key, col, 'ok');
      if (settingsRef.current.autoAdvance) { say('ok', `✓ ${label(col)}: ${shown}`); advance(key, col); }
      else say('ok', `✓ ${label(col)}: ${shown} — ${t('voice.pickNext')}`);
    };

    if (col === 'name') {
      const name = cleanName(heard);
      if (!name) { fail(t('voice.emptyName')); return; }
      updateRow(key, 'name', name);
      done(name);
      checkName(key, name);
      return;
    }
    if (NUMBER_COLS.includes(col)) {
      const kind = col === 'initial_stock' ? 'qty' : 'price';
      const n = pickNumber(alts, { kind });
      if (n == null) { fail(t('voice.notNumber', { text: heard })); return; }
      if (n < 0 || n > MAX_VALUE) { fail(t('voice.tooBig', { value: n.toLocaleString('ru-RU') })); return; }
      let shown = n.toLocaleString('ru-RU');
      let foreign = false;
      if (kind === 'price') {
        // "o'n dollar" — katak valyutasi ham o'zgaradi (so'm — standart)
        const code = alts.map(parseCurrency).find(Boolean);
        if (code && code !== 'UZS') {
          foreign = true;
          const cur = currenciesRef.current.find(c => String(c.code || '').toUpperCase().startsWith(code));
          if (!cur) { fail(t('voice.currencyNotFound', { code })); return; }
          updateRow(key, `${col}_cur`, String(cur.id));
          shown += ` ${cur.code}`;
        } else if (code === 'UZS') {
          updateRow(key, `${col}_cur`, '');
        }
      } else {
        // "ellik kilo" — o'lchov birligi ham shu yerdan olinadi
        const unit = pickUnit(alts);
        if (unit) { updateRow(key, 'unit', unit); shown += ` ${unit}`; }
      }
      updateRow(key, col, String(n));
      done(shown);
      if ((col === 'sale_price' || col === 'cost_price') && !foreign) checkPrices(key, col, n);
      return;
    }
    if (col === 'unit') {
      const u = pickUnit(alts);
      if (!u) { fail(t('voice.notUnit', { text: heard })); return; }
      updateRow(key, 'unit', u);
      done(u);
      return;
    }
    if (col === 'category_id') {
      const c = pickCategory(alts, categoriesRef.current);
      if (!c) { fail(t('voice.notCategory', { text: heard })); return; }
      updateRow(key, 'category_id', String(c.id));
      done(c.name);
    }
  };
  const handleRef = useRef(handleUtterance);
  handleRef.current = handleUtterance;

  /* ─── Mikrofon ─── */
  const stop = useCallback((text) => {
    activeRef.current = false;
    setActive(false);
    setInterim('');
    try { recRef.current?.abort(); } catch { /* allaqachon to'xtagan */ }
    recRef.current = null;
    if (text) setMessage({ type: 'info', text });
  }, []);

  const startRecognition = useCallback(() => {
    const rec = new SR();
    rec.lang = settingsRef.current.lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 3;
    rec.onresult = (e) => {
      let live = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) {
          const alts = Array.from(res).map(a => a.transcript.trim()).filter(Boolean);
          handleRef.current(alts);
        } else {
          live += res[0].transcript;
        }
      }
      setInterim(live);
    };
    rec.onerror = (e) => {
      const fatal = {
        'not-allowed': t('voice.micDenied'),
        'service-not-allowed': t('voice.micDenied'),
        'audio-capture': t('voice.noMic'),
        'language-not-supported': t('voice.langNotSupported'),
      }[e.error];
      if (fatal) { stop(); setMessage({ type: 'err', text: fatal }); return; }
      if (e.error === 'network') setMessage({ type: 'err', text: t('voice.network') });
    };
    // Chrome uzoq jimlikdan keyin o'zi to'xtaydi — tugma yoniq bo'lsa qayta yoqiladi
    rec.onend = () => {
      if (!activeRef.current) return;
      const now = Date.now();
      failsRef.current = [...failsRef.current.filter(x => now - x < 10000), now];
      if (failsRef.current.length > 6) { stop(); setMessage({ type: 'err', text: t('voice.network') }); return; }
      setTimeout(() => {
        if (!activeRef.current) return;
        try { startRecognition(); } catch { /* keyingi onend da qayta uriniladi */ }
      }, 300);
    };
    recRef.current = rec;
    rec.start();
  }, [stop, t]);

  const start = useCallback(() => {
    if (!SR) return;
    const rs = rowsRef.current;
    let cur = cursorRef.current;
    if (!cur || !rs.some(r => r._key === cur.key)) {
      const empty = rs.find(r => !r.name.trim());
      if (empty) cur = { key: empty._key, col: 'name' };
      else {
        const row = emptyRow();
        setRows(prev => [...prev, row]);
        cur = { key: row._key, col: 'name' };
      }
      setCursor(cur);
    }
    failsRef.current = [];
    activeRef.current = true;
    setActive(true);
    setMessage({ type: 'info', text: t('voice.commandsHint') });
    beep('ok');
    try { startRecognition(); } catch { stop(); }
  }, [beep, emptyRow, setCursor, setRows, startRecognition, stop, t]);

  // Oyna yopilsa — mikrofon o'chadi
  useEffect(() => { if (!enabled) { stop(); setCursor(null); setMessage(null); setNameChecks({}); } }, [enabled, stop, setCursor]);
  useEffect(() => () => stop(), [stop]);

  // Katakni sichqoncha/klaviatura bilan tanlasa — ovoz o'sha katakdan davom etadi.
  // Ovoz o'chiq paytda ham eslab qolinadi: 🎤 bosilganda o'sha katakdan boshlanadi.
  useEffect(() => {
    if (!enabled) return undefined;
    const onFocus = (e) => {
      const cell = e.target.closest?.('[data-voice-cell]');
      if (cell) {
        const [key, col] = cell.dataset.voiceCell.split(':');
        if (settingsRef.current.cols.includes(col)) { setCursor({ key, col }); return; }
      }
      // Ovoz so'ramaydigan katak (shtrix kod, Kod...) — o'sha qatorning nomidan
      const row = e.target.closest?.('[data-voice-row]');
      if (row) setCursor({ key: row.dataset.voiceRow, col: 'name' });
    };
    document.addEventListener('focusin', onFocus);
    return () => document.removeEventListener('focusin', onFocus);
  }, [enabled, setCursor]);

  // Skaner yangi qator ochsa — ovoz o'sha qatorning nomidan davom etadi
  useEffect(() => {
    const last = rows[rows.length - 1];
    const prevKey = lastRowKeyRef.current;
    lastRowKeyRef.current = last?._key;
    if (activeRef.current && last && last._key !== prevKey && last.barcode_scanned && !last.name.trim()) {
      setCursor({ key: last._key, col: 'name' });
    }
  }, [rows, setCursor]);

  const saveSettings = (patch) => {
    setSettings(s => {
      const next = { ...s, ...patch };
      try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)); } catch { /* saqlanmasa ham ishlaydi */ }
      return next;
    });
  };
  const toggleCol = (col) => {
    const cols = settings.cols.includes(col) ? settings.cols.filter(c => c !== col) : [...settings.cols, col];
    saveSettings({ cols: ALL_COLS.filter(c => cols.includes(c)) });
  };

  /* ─── Ko'rinish ─── */
  const nameWarning = (row) => {
    const c = nameChecks[row._key];
    if (!c || normText(c.name) !== normText(row.name)) return null;
    if (c.existing) return t('voice.existsInDb', { name: c.existing });
    if (c.dupInTable) return t('voice.dupInTable');
    return null;
  };

  const button = SR ? (
    <div className="relative flex items-center gap-1">
      <button
        type="button"
        onClick={() => (active ? stop(t('voice.stopped')) : start())}
        className={`inline-flex items-center gap-2 h-9 xl:h-10 px-3 xl:px-4 rounded-lg xl:rounded-xl text-sm font-bold transition-colors ${active
          ? 'bg-red-600 hover:bg-red-700 text-white animate-pulse'
          : 'bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200'}`}
        title={t('voice.start')}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
        </svg>
        <span className="hidden md:inline">{active ? t('voice.stop') : t('voice.start')}</span>
      </button>
      <button
        type="button"
        onClick={() => setSettingsOpen(o => !o)}
        className="h-9 xl:h-10 w-9 flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100"
        title={t('voice.settings')}
        aria-label={t('voice.settings')}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <circle cx="12" cy="12" r="3" strokeWidth={2} />
        </svg>
      </button>
      {settingsOpen && (
        <div className="absolute right-0 top-full mt-2 w-72 bg-white border border-slate-200 rounded-xl shadow-xl z-[70] p-4 space-y-3 text-sm">
          <div className="font-bold text-slate-700">{t('voice.settings')}</div>
          <div>
            <div className="text-xs font-semibold text-slate-500 mb-1.5">{t('voice.askColumns')}</div>
            {ALL_COLS.map(col => (
              <label key={col} className="flex items-center gap-2 py-0.5 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 accent-blue-600"
                  checked={settings.cols.includes(col)} disabled={REQUIRED_COLS.includes(col)}
                  onChange={() => toggleCol(col)} />
                <span className={REQUIRED_COLS.includes(col) ? 'text-slate-400' : 'text-slate-700'}>{label(col)}</span>
              </label>
            ))}
          </div>
          <label className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-slate-500">{t('voice.language')}</span>
            <select value={settings.lang} disabled={active}
              onChange={e => saveSettings({ lang: e.target.value })}
              className="px-2 py-1 border border-slate-200 rounded-lg">
              <option value="uz-UZ">O'zbekcha</option>
              <option value="ru-RU">Русский</option>
            </select>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="w-4 h-4 accent-blue-600" checked={settings.beep}
              onChange={e => saveSettings({ beep: e.target.checked })} />
            <span className="text-slate-700">{t('voice.beep')}</span>
          </label>
          <label className="flex items-start gap-2 cursor-pointer">
            <input type="checkbox" className="w-4 h-4 mt-0.5 accent-blue-600" checked={settings.autoAdvance}
              onChange={e => saveSettings({ autoAdvance: e.target.checked })} />
            <span className="text-slate-700">{t('voice.autoAdvance')}</span>
          </label>
        </div>
      )}
    </div>
  ) : null;

  const rowNo = cursor ? rows.findIndex(r => r._key === cursor.key) + 1 : 0;
  const msgCls = {
    ok: 'text-emerald-700', warn: 'text-amber-700', err: 'text-red-600 font-semibold', info: 'text-slate-500',
  }[message?.type] || 'text-slate-500';

  const bar = (active || message) ? (
    <div className={`mx-6 mt-3 px-4 py-2.5 rounded-xl border shrink-0 flex flex-wrap items-center gap-x-4 gap-y-1 ${active ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-200'}`}>
      {active && cursor && rowNo > 0 && (
        <span className="font-bold text-blue-800">
          🎤 {t('voice.rowN', { n: rowNo })} → {label(cursor.col)}
        </span>
      )}
      {active && interim && <span className="italic text-slate-500">«{interim}»</span>}
      {message && <span className={`text-sm ${msgCls}`}>{message.text}</span>}
      {!active && message && (
        <button type="button" onClick={() => setMessage(null)} className="ml-auto text-slate-400 hover:text-slate-600" aria-label="×">×</button>
      )}
    </div>
  ) : null;

  return { supported: Boolean(SR), active, button, bar, nameWarning };
}
