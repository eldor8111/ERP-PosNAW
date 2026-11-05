// E-code AI: Claude asosidagi yordamchi (chat, rasm yuklash, tasdiq kartalari, ishlatilish qatori).
// Javob SSE oqimi bilan keladi: POST /ai/assistant/chat (fetch + ReadableStream).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUp, Check, ImagePlus, Loader2, Menu, MessageSquare, Pencil, Plus, Trash2, X,
} from 'lucide-react';
import api, { getCurrentBranchId } from '../../api/axios';
import { toast } from '../../utils/toast';
import { useLang } from '../../context/LangContext';

const MAX_IMAGES = 4;

const LABELS = {
  uz: {
    title: 'E-code AI',
    newChat: 'Yangi suhbat',
    conversations: 'Suhbatlar',
    empty: 'Suhbatlar yo\'q',
    placeholder: 'Savolingizni yozing...',
    hint: 'Enter yuborish, Shift+Enter yangi qator',
    attach: 'Rasm qo\'shish',
    thinking: 'O\'ylanmoqda',
    working: 'Javob yozilmoqda',
    confirm: 'Tasdiqlash',
    cancel: 'Bekor qilish',
    total: 'Jami',
    executed: 'Bajarildi',
    failed: 'Bajarilmadi',
    cancelled: 'Bekor qilindi',
    expired: 'Muddati o\'tdi',
    executing: 'Bajarilmoqda',
    month: 'Bu oy',
    today: 'Bugun',
    requests: 'so\'rov',
    until: 'gacha',
    inactiveTitle: 'AI yordamchi paketi faol emas',
    inactiveText: 'E-code AI savdo, qoldiq, qarz va foyda bo\'yicha savollarga javob beradi, nakladnoy rasmidan kirim tayyorlaydi va amallarni tasdiq bilan bajaradi.',
    inactiveBuy: 'Tariflar bo\'limida paketni ulash',
    inactiveAsk: 'Paketni ulash uchun korxona rahbariga murojaat qiling.',
    rename: 'Nomini o\'zgartirish',
    remove: 'O\'chirish',
    removeAsk: 'Suhbat o\'chirilsinmi?',
    tooMany: `Bitta xabarga ${MAX_IMAGES} tagacha rasm`,
    uploadFail: 'Rasm yuklanmadi',
    connFail: 'Ulanishda xatolik. Qayta urinib ko\'ring.',
    intro: 'Korxonangiz ma\'lumotlari bo\'yicha savol bering yoki nakladnoy rasmini yuboring.',
    images: 'rasm',
  },
  ru: {
    title: 'E-code AI',
    newChat: 'Новый чат',
    conversations: 'Чаты',
    empty: 'Чатов нет',
    placeholder: 'Напишите вопрос...',
    hint: 'Enter отправить, Shift+Enter новая строка',
    attach: 'Добавить фото',
    thinking: 'Думает',
    working: 'Пишет ответ',
    confirm: 'Подтвердить',
    cancel: 'Отменить',
    total: 'Итого',
    executed: 'Выполнено',
    failed: 'Не выполнено',
    cancelled: 'Отменено',
    expired: 'Срок истёк',
    executing: 'Выполняется',
    month: 'В этом месяце',
    today: 'Сегодня',
    requests: 'запросов',
    until: 'до',
    inactiveTitle: 'Пакет AI-ассистента не активен',
    inactiveText: 'E-code AI отвечает на вопросы о продажах, остатках, долгах и прибыли, готовит приход по фото накладной и выполняет действия с подтверждением.',
    inactiveBuy: 'Подключить в разделе Тарифы',
    inactiveAsk: 'Для подключения обратитесь к руководителю.',
    rename: 'Переименовать',
    remove: 'Удалить',
    removeAsk: 'Удалить чат?',
    tooMany: `До ${MAX_IMAGES} фото в одном сообщении`,
    uploadFail: 'Фото не загружено',
    connFail: 'Ошибка соединения. Попробуйте ещё раз.',
    intro: 'Задайте вопрос по данным вашей компании или отправьте фото накладной.',
    images: 'фото',
  },
};

const SUGGESTIONS = [
  'Bugungi savdo qancha?',
  'Qaysi tovarlar tugab qolyapti?',
  'Eng katta qarzdor mijozlar kimlar?',
  'Ta\'minotchilarga qancha qarzimiz bor?',
];

// ─── Xavfsiz markdown (HTML ishlatilmaydi) ──────────────────────────────────
function inline(text, keyBase) {
  const out = [];
  const rx = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = rx.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith('**')) out.push(<strong key={`${keyBase}-${i++}`} className="font-semibold text-slate-900">{tok.slice(2, -2)}</strong>);
    else out.push(<code key={`${keyBase}-${i++}`} className="px-1 py-0.5 rounded bg-slate-100 text-[0.85em] font-mono">{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function splitRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

function Markdown({ text }) {
  const lines = (text || '').replace(/\r/g, '').split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    if (line.trim().startsWith('```')) {
      const buf = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith('```')) { buf.push(lines[i]); i += 1; }
      i += 1;
      blocks.push(<pre key={`b${blocks.length}`} className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs overflow-x-auto font-mono whitespace-pre">{buf.join('\n')}</pre>);
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[i + 1])) {
      const head = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(splitRow(lines[i])); i += 1; }
      blocks.push(
        <div key={`b${blocks.length}`} className="overflow-x-auto">
          <table className="min-w-full text-xs border border-slate-200 rounded-lg">
            <thead className="bg-slate-50"><tr>{head.map((h, k) => <th key={k} className="px-2.5 py-1.5 text-left font-semibold text-slate-700 border-b border-slate-200">{inline(h, `h${k}`)}</th>)}</tr></thead>
            <tbody>{rows.map((r, ri) => <tr key={ri} className="border-b border-slate-100 last:border-0">{r.map((c, k) => <td key={k} className="px-2.5 py-1.5 text-slate-700 align-top">{inline(c, `c${ri}-${k}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      blocks.push(<div key={`b${blocks.length}`} className={`font-semibold text-slate-900 ${h[1].length <= 2 ? 'text-[15px]' : 'text-sm'}`}>{inline(h[2], `t${i}`)}</div>);
      i += 1;
      continue;
    }
    if (/^\s*([-*]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+[.)])\s+/, ''));
        i += 1;
      }
      const ListTag = ordered ? 'ol' : 'ul';
      blocks.push(
        <ListTag key={`b${blocks.length}`} className={`${ordered ? 'list-decimal' : 'list-disc'} pl-5 space-y-0.5`}>
          {items.map((it, k) => <li key={k}>{inline(it, `l${i}-${k}`)}</li>)}
        </ListTag>,
      );
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^\s*([-*]|\d+[.)])\s+/.test(lines[i]) && !/^#{1,4}\s/.test(lines[i])
      && !lines[i].trim().startsWith('```') && !/^\s*\|.*\|\s*$/.test(lines[i])) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={`b${blocks.length}`} className="whitespace-pre-wrap">{para.map((p, k) => <span key={k}>{k > 0 && <br />}{inline(p, `p${i}-${k}`)}</span>)}</p>);
  }
  return <div className="space-y-2 text-[14px] leading-relaxed text-slate-800 break-words">{blocks}</div>;
}

// ─── Tasdiq kartasi ─────────────────────────────────────────────────────────
function ActionCard({ action, L, onDecide }) {
  const [busy, setBusy] = useState(false);
  const status = action.status || 'pending';
  const decide = async (kind) => {
    setBusy(true);
    try { await onDecide(action, kind); } finally { setBusy(false); }
  };
  const badge = {
    executed: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    failed: 'text-red-700 bg-red-50 border-red-200',
    cancelled: 'text-slate-600 bg-slate-50 border-slate-200',
    expired: 'text-slate-600 bg-slate-50 border-slate-200',
    executing: 'text-blue-700 bg-blue-50 border-blue-200',
  }[status];
  return (
    <div className="mt-2 border border-slate-200 rounded-xl bg-white">
      <div className="px-3.5 py-2.5 border-b border-slate-100 flex items-start justify-between gap-3">
        <div className="text-[13px] font-semibold text-slate-900">{action.summary || action.title}</div>
        {status !== 'pending' && badge && (
          <span className={`shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-md border ${badge}`}>{L[status] || status}</span>
        )}
      </div>
      {(action.lines || []).length > 0 && (
        <ul className="px-3.5 py-2 space-y-1 text-[13px] text-slate-700">
          {action.lines.map((ln, k) => <li key={k} className="break-words">{ln}</li>)}
        </ul>
      )}
      {action.total && (
        <div className="px-3.5 py-2 border-t border-slate-100 flex justify-between text-[13px]">
          <span className="text-slate-500">{L.total}</span>
          <span className="font-semibold text-slate-900">{action.total}</span>
        </div>
      )}
      {action.result && status !== 'pending' && (
        <div className="px-3.5 py-2 border-t border-slate-100 text-[12px] text-slate-600 break-words">{action.result}</div>
      )}
      {status === 'pending' && (
        <div className="px-3.5 py-2.5 border-t border-slate-100 flex gap-2">
          <button type="button" disabled={busy} onClick={() => decide('confirm')}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 text-white text-[13px] font-semibold hover:bg-blue-700 disabled:opacity-50">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}{L.confirm}
          </button>
          <button type="button" disabled={busy} onClick={() => decide('cancel')}
            className="px-3.5 py-1.5 rounded-lg border border-slate-300 text-slate-700 text-[13px] font-semibold hover:bg-slate-50 disabled:opacity-50">
            {L.cancel}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── SSE so'rovi ────────────────────────────────────────────────────────────
function authHeaders() {
  const h = {};
  const token = localStorage.getItem('access_token');
  if (token) h.Authorization = `Bearer ${token}`;
  const br = getCurrentBranchId();
  if (br) h['X-Branch-Id'] = String(br);
  return h;
}

async function authFetch(path, init) {
  const url = `${api.defaults.baseURL}${path}`;
  let res = await fetch(url, { ...init, headers: { ...(init.headers || {}), ...authHeaders() } });
  if (res.status === 401) {
    // Token eskirgan: axios interceptor yangilaydi, keyin bir marta qayta urinamiz
    try { await api.get('/ai/assistant/status'); } catch { /* e'tiborsiz */ }
    res = await fetch(url, { ...init, headers: { ...(init.headers || {}), ...authHeaders() } });
  }
  return res;
}

async function errorText(res, fallback) {
  try {
    const j = await res.json();
    const d = j?.detail;
    if (typeof d === 'string') return d;
    if (d?.message) return d.message;
  } catch { /* matn emas */ }
  return fallback;
}

export default function EcodeAI() {
  const { lang } = useLang();
  const L = LABELS[lang] || LABELS.uz;
  const [status, setStatus] = useState(null);
  const [convs, setConvs] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [images, setImages] = useState([]);   // {key, preview, file_id, uploading}
  const [streaming, setStreaming] = useState(false);
  const [toolLabel, setToolLabel] = useState('');
  const [listOpen, setListOpen] = useState(false);
  const scrollRef = useRef(null);
  const fileRef = useRef(null);
  const abortRef = useRef(null);

  const loadStatus = useCallback(async () => {
    try { const r = await api.get('/ai/assistant/status'); setStatus(r.data); } catch { setStatus({ active: false }); }
  }, []);
  const loadConvs = useCallback(async () => {
    try { const r = await api.get('/ai/assistant/conversations'); setConvs(r.data || []); } catch { /* toast axios da */ }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);
  useEffect(() => { if (status?.can_chat) loadConvs(); }, [status?.can_chat, loadConvs]);
  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, toolLabel]);

  const openConv = async (id) => {
    if (streaming) return;
    setListOpen(false);
    try {
      const r = await api.get(`/ai/assistant/conversations/${id}`);
      setActiveId(id);
      setMessages(r.data.messages || []);
    } catch { /* toast axios da */ }
  };

  const newChat = () => {
    if (streaming) return;
    setActiveId(null);
    setMessages([]);
    setInput('');
    setImages([]);
    setListOpen(false);
  };

  const renameConv = async (c) => {
    const title = window.prompt(L.rename, c.title);
    if (!title || !title.trim()) return;
    try {
      await api.patch(`/ai/assistant/conversations/${c.id}`, { title: title.trim() });
      setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, title: title.trim() } : x)));
    } catch { /* toast */ }
  };

  const removeConv = async (c) => {
    if (!window.confirm(L.removeAsk)) return;
    try {
      await api.delete(`/ai/assistant/conversations/${c.id}`);
      setConvs((cs) => cs.filter((x) => x.id !== c.id));
      if (activeId === c.id) newChat();
    } catch { /* toast */ }
  };

  const addImages = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f.type.startsWith('image/'));
    if (!files.length) return;
    if (images.length + files.length > MAX_IMAGES) { toast.warn(L.tooMany); return; }
    for (const f of files) {
      const key = `${Date.now()}-${Math.random()}`;
      const preview = URL.createObjectURL(f);
      setImages((xs) => [...xs, { key, preview, uploading: true }]);
      try {
        const fd = new FormData();
        fd.append('file', f, f.name);
        const res = await authFetch('/ai/assistant/upload', { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await errorText(res, L.uploadFail));
        const meta = await res.json();
        setImages((xs) => xs.map((x) => (x.key === key ? { ...x, file_id: meta.file_id, uploading: false } : x)));
      } catch (e) {
        toast.error(e.message || L.uploadFail);
        setImages((xs) => xs.filter((x) => x.key !== key));
        URL.revokeObjectURL(preview);
      }
    }
  };

  const patchLast = (fn) => setMessages((ms) => {
    const copy = ms.slice();
    const last = copy[copy.length - 1];
    if (last && last.role === 'assistant') copy[copy.length - 1] = fn({ ...last });
    return copy;
  });

  const send = async (textArg) => {
    const text = (textArg ?? input).trim();
    const ready = images.filter((x) => x.file_id);
    if (streaming || images.some((x) => x.uploading) || (!text && !ready.length)) return;
    setInput('');
    setImages([]);
    setStreaming(true);
    setToolLabel(L.thinking);
    setMessages((ms) => [...ms,
      { id: `u${Date.now()}`, role: 'user', text, images: ready.length, previews: ready.map((x) => x.preview) },
      { id: `a${Date.now()}`, role: 'assistant', text: '', actions: [], pending: true }]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await authFetch('/ai/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: activeId, message: text, file_ids: ready.map((x) => x.file_id) }),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const msg = await errorText(res, L.connFail);
        patchLast((m) => ({ ...m, text: msg, error: true, pending: false }));
        if (res.status === 402 || res.status === 429) loadStatus();
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.split('\n').find((l) => l.startsWith('data: '));
          if (!line) continue;
          let ev;
          try { ev = JSON.parse(line.slice(6)); } catch { continue; }
          if (ev.type === 'start') {
            if (!activeId) {
              setActiveId(ev.conversation_id);
              setConvs((cs) => [{ id: ev.conversation_id, title: ev.title, turns: 1 }, ...cs.filter((c) => c.id !== ev.conversation_id)]);
            }
          } else if (ev.type === 'delta') {
            setToolLabel(L.working);
            patchLast((m) => ({ ...m, text: (m.text || '') + ev.text }));
          } else if (ev.type === 'tool') {
            setToolLabel(ev.label || L.working);
          } else if (ev.type === 'status') {
            if (ev.status === 'thinking') setToolLabel(L.thinking);
          } else if (ev.type === 'action') {
            patchLast((m) => ({ ...m, actions: [...(m.actions || []), ev.action] }));
          } else if (ev.type === 'error') {
            patchLast((m) => ({ ...m, text: `${m.text ? `${m.text}\n\n` : ''}${ev.message}`, error: true }));
          } else if (ev.type === 'done') {
            patchLast((m) => ({ ...m, pending: false }));
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') patchLast((m) => ({ ...m, text: m.text || L.connFail, error: !m.text }));
    } finally {
      patchLast((m) => ({ ...m, pending: false }));
      setStreaming(false);
      setToolLabel('');
      abortRef.current = null;
      loadStatus();
      loadConvs();
    }
  };

  const decide = async (action, kind) => {
    const setCard = (patch) => setMessages((ms) => ms.map((m) => ({
      ...m,
      actions: (m.actions || []).map((a) => (a.confirmation_id === action.confirmation_id ? { ...a, ...patch } : a)),
    })));
    try {
      const r = await api.post(`/ai/assistant/actions/${action.confirmation_id}/${kind}`);
      setCard({ status: r.data.status, result: r.data.message });
      if (kind === 'confirm') (r.data.ok ? toast.success : toast.error)(r.data.message);
    } catch (e) {
      const st = e?.response?.status;
      if (st === 409 || st === 410) setCard({ status: st === 410 ? 'expired' : action.status });
    }
  };

  const usage = useMemo(() => {
    if (!status?.active) return null;
    const parts = [];
    parts.push(`${L.month}: ${status.month_used}${status.monthly_limit ? ` / ${status.monthly_limit}` : ''} ${L.requests}`);
    if (status.daily_user_limit) parts.push(`${L.today}: ${status.day_used} / ${status.daily_user_limit}`);
    if (status.ends_at) parts.push(`${status.package_name}: ${new Date(status.ends_at).toLocaleDateString('ru-RU')} ${L.until}`);
    return parts.join('  |  ');
  }, [status, L]);

  if (status === null) {
    return <div className="flex items-center justify-center h-[60vh] text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>;
  }

  if (!status.can_chat) {
    return (
      <div className="max-w-xl mx-auto mt-16 px-4">
        <div className="border border-slate-200 rounded-2xl bg-white p-6">
          <div className="text-[15px] font-semibold text-slate-900">{L.inactiveTitle}</div>
          <p className="mt-2 text-sm text-slate-600 leading-relaxed">{L.inactiveText}</p>
          {status.can_buy
            ? <Link to="/admin/tariflar" className="inline-block mt-4 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700">{L.inactiveBuy}</Link>
            : <p className="mt-4 text-sm text-slate-500">{L.inactiveAsk}</p>}
        </div>
      </div>
    );
  }

  const list = (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-slate-200">
        <button type="button" onClick={newChat} disabled={streaming}
          className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 text-[13px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          <Plus className="w-4 h-4" />{L.newChat}
        </button>
      </div>
      <div className="px-3 pt-3 pb-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wide">{L.conversations}</div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
        {convs.length === 0 && <div className="px-2 py-3 text-[13px] text-slate-400">{L.empty}</div>}
        {convs.map((c) => (
          <div key={c.id}
            className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 cursor-pointer ${c.id === activeId ? 'bg-blue-50 text-blue-700' : 'text-slate-700 hover:bg-slate-100'}`}
            onClick={() => openConv(c.id)}>
            <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
            <span className="flex-1 truncate text-[13px]">{c.title || L.newChat}</span>
            <button type="button" title={L.rename} onClick={(e) => { e.stopPropagation(); renameConv(c); }}
              className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-white"><Pencil className="w-3.5 h-3.5" /></button>
            <button type="button" title={L.remove} onClick={(e) => { e.stopPropagation(); removeConv(c); }}
              className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-white text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
          </div>
        ))}
      </div>
    </div>
  );

  const uploading = images.some((x) => x.uploading);

  return (
    <div className="flex h-[calc(100vh-65px)] bg-slate-50">
      <aside className="hidden md:block w-64 shrink-0 border-r border-slate-200 bg-white">{list}</aside>
      {listOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex">
          <div className="w-72 max-w-[80vw] bg-white border-r border-slate-200">{list}</div>
          <button type="button" aria-label="close" className="flex-1 bg-slate-900/30" onClick={() => setListOpen(false)} />
        </div>
      )}

      <section className="flex-1 flex flex-col min-w-0">
        <header className="h-12 shrink-0 border-b border-slate-200 bg-white px-3 sm:px-4 flex items-center gap-2">
          <button type="button" className="md:hidden p-1.5 rounded-lg hover:bg-slate-100" onClick={() => setListOpen(true)}><Menu className="w-4 h-4" /></button>
          <div className="text-[14px] font-semibold text-slate-900 truncate">
            {activeId ? (convs.find((c) => c.id === activeId)?.title || L.title) : L.title}
          </div>
          {usage && <div className="ml-auto hidden sm:block text-[12px] text-slate-500 truncate">{usage}</div>}
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-3 sm:px-4 py-4 space-y-4">
            {messages.length === 0 && (
              <div className="pt-10">
                <div className="text-lg font-semibold text-slate-900">{L.title}</div>
                <p className="mt-1 text-sm text-slate-500">{L.intro}</p>
                <div className="mt-4 grid sm:grid-cols-2 gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" onClick={() => send(s)}
                      className="text-left px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white text-[13px] text-slate-700 hover:border-blue-300 hover:bg-blue-50/40">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (m.role === 'user' ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md bg-blue-600 text-white px-3.5 py-2 text-[14px] whitespace-pre-wrap break-words">
                  {(m.previews || []).length > 0 && (
                    <div className="flex gap-1.5 mb-1.5 flex-wrap">
                      {m.previews.map((p) => <img key={p} src={p} alt="" className="w-16 h-16 object-cover rounded-lg border border-white/30" />)}
                    </div>
                  )}
                  {!m.previews?.length && m.images > 0 && <div className="text-[12px] opacity-80 mb-1">{m.images} {L.images}</div>}
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex">
                <div className="max-w-[92%] w-full">
                  {m.text && (
                    <div className={`rounded-2xl rounded-bl-md border px-3.5 py-2.5 ${m.error ? 'bg-red-50 border-red-200 text-red-700 text-[14px]' : 'bg-white border-slate-200'}`}>
                      {m.error ? <div className="whitespace-pre-wrap">{m.text}</div> : <Markdown text={m.text} />}
                    </div>
                  )}
                  {(m.actions || []).filter((a) => a.type === 'confirm').map((a) => (
                    <ActionCard key={a.confirmation_id} action={a} L={L} onDecide={decide} />
                  ))}
                  {m.pending && (
                    <div className="mt-1.5 inline-flex items-center gap-1.5 text-[12px] text-slate-500">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />{toolLabel || L.thinking}
                    </div>
                  )}
                </div>
              </div>
            )))}
          </div>
        </div>

        <div className="shrink-0 border-t border-slate-200 bg-white">
          <div className="max-w-3xl mx-auto px-3 sm:px-4 py-3">
            {images.length > 0 && (
              <div className="flex gap-2 mb-2 flex-wrap">
                {images.map((x) => (
                  <div key={x.key} className="relative w-16 h-16 rounded-lg overflow-hidden border border-slate-200">
                    <img src={x.preview} alt="" className="w-full h-full object-cover" />
                    {x.uploading && <div className="absolute inset-0 bg-white/60 flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin text-slate-600" /></div>}
                    {!x.uploading && (
                      <button type="button" onClick={() => setImages((xs) => xs.filter((y) => y.key !== x.key))}
                        className="absolute top-0.5 right-0.5 p-0.5 rounded bg-white/90 border border-slate-200"><X className="w-3 h-3" /></button>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2 border border-slate-300 rounded-xl bg-white px-2 py-1.5 focus-within:border-blue-500">
              {status.allow_vision && (
                <>
                  <input ref={fileRef} type="file" accept="image/*" multiple className="hidden"
                    onChange={(e) => { addImages(e.target.files); e.target.value = ''; }} />
                  <button type="button" title={L.attach} disabled={streaming || images.length >= MAX_IMAGES}
                    onClick={() => fileRef.current?.click()}
                    className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 disabled:opacity-40"><ImagePlus className="w-[18px] h-[18px]" /></button>
                </>
              )}
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                onPaste={(e) => { const f = Array.from(e.clipboardData?.files || []); if (f.length && status.allow_vision) addImages(f); }}
                rows={1}
                maxLength={4000}
                placeholder={L.placeholder}
                className="flex-1 resize-none outline-none text-[14px] leading-6 py-1.5 max-h-40 bg-transparent"
                style={{ height: 'auto' }}
                onInput={(e) => { e.target.style.height = 'auto'; e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`; }}
              />
              <button type="button" onClick={() => send()} disabled={streaming || uploading || (!input.trim() && !images.some((x) => x.file_id))}
                className="p-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40">
                {streaming ? <Loader2 className="w-[18px] h-[18px] animate-spin" /> : <ArrowUp className="w-[18px] h-[18px]" />}
              </button>
            </div>
            <div className="mt-1.5 flex justify-between gap-3 text-[11px] text-slate-400">
              <span className="hidden sm:inline">{L.hint}</span>
              {usage && <span className="sm:hidden truncate">{usage}</span>}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
