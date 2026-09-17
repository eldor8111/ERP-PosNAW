import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';

// ─── Markdown-light renderer ──────────────────────────────────────────────
function renderText(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br/>');
}

// ─── Typing Indicator ──────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 mb-4">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-md">
        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      </div>
      <div className="bg-white border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center">
          <div className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, color, loading }) {
  const colorMap = {
    blue: 'from-blue-500 to-blue-600',
    green: 'from-emerald-500 to-emerald-600',
    amber: 'from-amber-500 to-amber-600',
    violet: 'from-violet-500 to-violet-600',
  };
  return (
    <div className="bg-white rounded-xl border border-slate-100 px-4 py-3 flex items-center gap-3 shadow-sm hover:shadow-md transition-shadow">
      <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${colorMap[color] || colorMap.blue} flex items-center justify-center shadow-sm flex-shrink-0`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">{label}</div>
        {loading ? (
          <div className="h-5 w-24 bg-slate-100 rounded animate-pulse mt-1" />
        ) : (
          <div className="font-bold text-slate-800 text-sm truncate">{value}</div>
        )}
        {sub && !loading && <div className="text-[10px] text-slate-400 truncate">{sub}</div>}
      </div>
    </div>
  );
}

const fmtSom = (num) => {
  if (!num) return '0';
  return Number(num).toLocaleString('ru-RU');
};

// ─── Purchase Order draft panel ───────────────────────────────────────────
function PurchaseOrderDraftPanel({ action, msgId, onDone }) {
  const [items, setItems] = useState(() => (action.items || []).map(it => ({ ...it })));
  const [warehouseId, setWarehouseId] = useState('');
  const [warehouses, setWarehouses] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get('/warehouses').then(r => setWarehouses(r.data || [])).catch(() => {});
    api.get('/suppliers').then(r => setSuppliers(r.data || [])).catch(() => {});
  }, []);

  const setItemSupplier = (idx, supplierId) => {
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, supplier_id: supplierId ? Number(supplierId) : null } : it));
  };

  const allHaveSupplier = items.every(it => it.supplier_id);
  const totalCost = items.reduce((s, it) => s + (Number(it.unit_cost) || 0) * (Number(it.suggested_qty) || 0), 0);

  const submit = async () => {
    if (!warehouseId) { toast.error('Omborni tanlang'); return; }
    if (!allHaveSupplier) { toast.error('Barcha mahsulotlarga yetkazib beruvchi tanlang'); return; }
    setSubmitting(true);
    try {
      const res = await api.post('/ai/actions/purchase-order', {
        warehouse_id: Number(warehouseId),
        items: items.map(it => ({
          product_id: it.product_id,
          quantity: it.suggested_qty,
          unit_cost: it.unit_cost,
          supplier_id: it.supplier_id,
        })),
      });
      onDone(msgId, res.data.reply);
      toast.success('Xarid buyurtmasi yaratildi!');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-blue-50 border-2 border-blue-200 rounded-2xl px-4 py-3 w-full animate-fadeIn">
      <div className="font-bold text-blue-700 text-xs mb-2">📋 Zayavka qoralamasi ({items.length} ta mahsulot)</div>
      <div className="max-h-56 overflow-y-auto space-y-1.5 mb-3">
        {items.map((it, idx) => (
          <div key={it.product_id} className="bg-white rounded-lg border border-slate-200 px-2.5 py-2 flex items-center gap-2">
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-slate-700 truncate">{it.product_name}</div>
              <div className="text-[10px] text-slate-400">{it.suggested_qty} dona × {fmtSom(it.unit_cost)} so'm</div>
            </div>
            {it.supplier_name ? (
              <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-md shrink-0">{it.supplier_name}</span>
            ) : (
              <select
                value={it.supplier_id || ''}
                onChange={e => setItemSupplier(idx, e.target.value)}
                className="text-[10px] border border-red-300 rounded-md px-1.5 py-1 shrink-0 max-w-28 outline-none"
              >
                <option value="">Yetk. beruvchi...</option>
                {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            )}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 mb-3">
        <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="flex-1 text-xs border border-slate-200 rounded-lg px-2 py-1.5 outline-none">
          <option value="">Ombor tanlang...</option>
          {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <span className="text-xs font-bold text-slate-600 whitespace-nowrap">≈{fmtSom(totalCost)} so'm</span>
      </div>
      <button
        onClick={submit}
        disabled={submitting}
        className="w-full py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg transition-all active:scale-95 disabled:opacity-50"
      >
        {submitting ? 'Yaratilmoqda...' : '✅ Xarid buyurtmasini yaratish'}
      </button>
    </div>
  );
}

// ─── SMS campaign draft panel ──────────────────────────────────────────────
function SmsCampaignDraftPanel({ action, msgId, onDone }) {
  const [message, setMessage] = useState(action.message || '');
  const [submitting, setSubmitting] = useState(false);
  const recipients = action.recipients || [];

  const submit = async () => {
    if (!message.trim()) { toast.error('Xabar matnini kiriting'); return; }
    setSubmitting(true);
    try {
      const res = await api.post('/ai/actions/sms-campaign', {
        recipients: recipients.map(r => ({ id: r.id, name: r.name, phone: r.phone })),
        message: message.trim(),
      });
      onDone(msgId, res.data.reply);
      toast.success('SMS kampaniya yuborildi!');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-violet-50 border-2 border-violet-200 rounded-2xl px-4 py-3 w-full animate-fadeIn">
      <div className="font-bold text-violet-700 text-xs mb-2">📱 SMS kampaniya qoralamasi ({recipients.length} ta mijoz)</div>
      <textarea
        value={message}
        onChange={e => setMessage(e.target.value)}
        rows={2}
        className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 mb-2 outline-none focus:border-violet-400 resize-none"
      />
      <div className="max-h-28 overflow-y-auto mb-3 flex flex-wrap gap-1">
        {recipients.slice(0, 20).map(r => (
          <span key={r.id} className="text-[10px] font-semibold text-violet-600 bg-white border border-violet-100 px-2 py-0.5 rounded-md">{r.name}</span>
        ))}
        {recipients.length > 20 && (
          <span className="text-[10px] text-slate-400">+{recipients.length - 20} ta yana</span>
        )}
      </div>
      <button
        onClick={submit}
        disabled={submitting}
        className="w-full py-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold rounded-lg transition-all active:scale-95 disabled:opacity-50"
      >
        {submitting ? 'Yuborilmoqda...' : `✅ ${recipients.length} ta mijozga yuborish`}
      </button>
    </div>
  );
}

// ─── Message Bubble ───────────────────────────────────────────────────────
function MessageBubble({ msg, onConfirm, onCancel, onDraftActionDone }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`flex items-end gap-2 mb-4 ${isUser ? 'flex-row-reverse' : 'flex-row'} animate-fadeIn`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-md">
          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
      )}
      <div className={`max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
          isUser
            ? 'bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-br-sm'
            : 'bg-white border border-slate-100 text-slate-700 rounded-bl-sm'
        }`}>
          <span dangerouslySetInnerHTML={{ __html: renderText(msg.content) }} />
        </div>

        {/* HIGH RISK tasdiqlash paneli */}
        {msg.action?.type === 'confirm_action' && !msg.confirmed && !msg.cancelled && (
          <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl px-4 py-3 w-full animate-fadeIn">
            <div className="flex items-center gap-2 mb-2">
              <svg className="w-4 h-4 text-amber-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span className="font-bold text-amber-700 text-xs">Tasdiqlash talab qilinadi!</span>
            </div>
            <p className="text-xs text-amber-600 mb-3">Bu amal ma'lumotlarni o'zgartiradi. Davom etishni tasdiqlaysizmi?</p>
            <div className="flex gap-2">
              <button
                onClick={() => onConfirm(msg.action.confirmation_id, msg.id)}
                className="flex-1 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold rounded-lg transition-all active:scale-95"
              >
                ✅ Tasdiqlash
              </button>
              <button
                onClick={() => onCancel(msg.id)}
                className="flex-1 py-1.5 bg-white hover:bg-slate-50 text-slate-600 text-xs font-bold rounded-lg border border-slate-200 transition-all active:scale-95"
              >
                ❌ Bekor qilish
              </button>
            </div>
          </div>
        )}
        {msg.action?.type === 'draft_purchase_order' && !msg.confirmed && !msg.cancelled && (
          <PurchaseOrderDraftPanel action={msg.action} msgId={msg.id} onDone={onDraftActionDone} />
        )}
        {msg.action?.type === 'draft_sms_campaign' && !msg.confirmed && !msg.cancelled && (
          <SmsCampaignDraftPanel action={msg.action} msgId={msg.id} onDone={onDraftActionDone} />
        )}
        {msg.confirmed && (
          <div className="text-[10px] text-emerald-600 font-bold px-1">✅ Tasdiqlandi va bajarildi</div>
        )}
        {msg.cancelled && (
          <div className="text-[10px] text-slate-400 px-1">❌ Bekor qilindi</div>
        )}

        <div className="text-[10px] text-slate-400 px-1">
          {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : ''}
        </div>
      </div>
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-600 to-slate-800 flex items-center justify-center flex-shrink-0 shadow-md">
          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      )}
    </div>
  );
}

// ─── Quick Prompts ────────────────────────────────────────────────────────
const QUICK_PROMPTS = [
  { icon: '📊', text: "Bugungi savdo xulosasi", prompt: "Bugungi savdo xulosasini ko'rsat" },
  { icon: '💰', text: "Bugungi foyda", prompt: "Bugungi foydani hissobla" },
  { icon: '⚠️', text: "Tugayotgan mahsulotlar", prompt: "Zaxirasi tugayotgan mahsulotlarni ko'rsat" },
  { icon: '📋', text: "Qarzdorlar", prompt: "Eng yirik qarzdorlar ro'yxatini ko'rsat" },
  { icon: '🏆', text: "Eng ko'p sotilgan", prompt: "Eng ko'p sotilgan 5 ta mahsulotni ko'rsat" },
  { icon: '👥', text: "Yangi mijozlar", prompt: "Bu haftada yangi qo'shilgan mijozlar sonini ko'rsat" },
];

// ─── Main Component ───────────────────────────────────────────────────────
export default function AICopilot() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [stats, setStats] = useState(null);
  const [debtStats, setDebtStats] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [statsLoading, setStatsLoading] = useState(true);
  const [conversationId] = useState(() => Date.now().toString());

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, loading]);

  // Load stats on mount
  useEffect(() => {
    const loadStats = async () => {
      try {
        const [summaryRes, debtRes, recRes] = await Promise.all([
          api.get('/ai/daily-summary').catch(() => null),
          api.get('/ai/debt-analytics').catch(() => null),
          api.get('/ai/recommendations').catch(() => null),
        ]);
        if (summaryRes) setStats(summaryRes.data);
        if (debtRes) setDebtStats(debtRes.data);
        if (recRes) setRecommendations(recRes.data.recommendations || []);
      } catch (e) {
        console.error('Stats load error:', e);
      } finally {
        setStatsLoading(false);
      }
    };
    loadStats();
  }, []);

  // Send message
  const sendMessage = async (text) => {
    const trimmed = (text || input).trim();
    if (!trimmed || loading) return;

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.post('/ai/chat', {
        message: trimmed,
        conversation_id: conversationId,
      });
      const data = res.data;

      const aiMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.reply || 'Javob olindi.',
        action: data.action || null,
        timestamp: new Date().toISOString(),
        confirmed: false,
        cancelled: false,
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (e) {
      const errMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '❌ Xatolik yuz berdi. Internet aloqasini tekshiring.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errMsg]);
      toast.error("AI bilan ulanishda xatolik");
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };

  // PO / SMS qoralamasi haqiqiy amalga aylantirilgandan keyin chaqiriladi
  const handleDraftActionDone = (msgId, replyText) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, confirmed: true } : m
    ));
    const resultMsg = {
      id: Date.now(),
      role: 'assistant',
      content: replyText || 'Amal muvaffaqiyatli bajarildi.',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, resultMsg]);
  };

  // Confirm HIGH risk action
  const handleConfirm = async (confirmationId, msgId) => {
    setLoading(true);
    try {
      const res = await api.post('/ai/confirm', { confirmation_id: confirmationId });
      const data = res.data;

      setMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, confirmed: true } : m
      ));

      const resultMsg = {
        id: Date.now(),
        role: 'assistant',
        content: data.reply || 'Amal muvaffaqiyatli bajarildi.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, resultMsg]);
      toast.success("Amal tasdiqlandi!");
    } catch (e) {
      toast.error("Tasdiqlashda xatolik");
    } finally {
      setLoading(false);
    }
  };

  // Cancel HIGH risk action
  const handleCancel = (msgId) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, cancelled: true } : m
    ));
    const cancelMsg = {
      id: Date.now(),
      role: 'assistant',
      content: 'Amal bekor qilindi.',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, cancelMsg]);
  };

  // Voice recording
  const toggleRecording = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(t => t.stop());
        const formData = new FormData();
        formData.append('file', blob, 'voice.webm');
        setLoading(true);
        try {
          const res = await api.post('/ai/voice', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
          const data = res.data;
          if (data.transcription) {
            const userMsg = { id: Date.now(), role: 'user', content: `🎤 ${data.transcription}`, timestamp: new Date().toISOString() };
            setMessages(prev => [...prev, userMsg]);
          }
          if (data.reply) {
            const aiMsg = { id: Date.now() + 1, role: 'assistant', content: data.reply, action: data.action || null, timestamp: new Date().toISOString(), confirmed: false, cancelled: false };
            setMessages(prev => [...prev, aiMsg]);
          }
        } catch (e) {
          if (e.response?.status === 500) {
            toast.error("Ovozli xizmat vaqtincha o'chirilgan");
          } else {
            toast.error("Ovozni qayta ishlashda xatolik");
          }
        } finally {
          setLoading(false);
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      toast.success("Yozib olinmoqda... To'xtatish uchun qayta bosing", { duration: 2000 });
    } catch (e) {
      toast.error("Mikrofonga ruxsat yo'q");
    }
  };

  // Clear chat
  const clearChat = () => {
    setMessages([]);
    toast.success("Suhbat tozalandi");
  };

  const fmt = (num) => {
    if (!num) return '0';
    return Number(num).toLocaleString('ru-RU');
  };

  return (
    <div className="flex-1 bg-slate-50 flex flex-col overflow-hidden h-full">
      {/* CSS Animation */}
      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fadeIn { animation: fadeIn 0.25s ease-out; }
      `}</style>

      {/* ─── Header ─────────────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200 px-6 py-3.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center shadow-md">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div>
            <h1 className="font-bold text-slate-800 text-base">AI Copilot</h1>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[11px] text-emerald-600 font-semibold">Online · Gemini Flash</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={clearChat}
            className="text-xs text-slate-500 hover:text-red-500 bg-slate-50 hover:bg-red-50 px-3 py-1.5 rounded-lg border border-slate-200 font-medium transition-all flex items-center gap-1.5"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Tozalash
          </button>
        </div>
      </div>

      {/* ─── Stats Bar ───────────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-100 px-6 py-3 flex-shrink-0">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            color="blue"
            loading={statsLoading}
            label="Bugungi tushum"
            value={stats ? `${fmt(stats.stats?.total_sales)} so'm` : '—'}
            sub={stats ? `${stats.stats?.total_orders || 0} ta buyurtma` : ''}
            icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          />
          <StatCard
            color="green"
            loading={statsLoading}
            label="Naqd / Karta"
            value={stats ? `${fmt(stats.stats?.cash)} / ${fmt(stats.stats?.card)}` : '—'}
            sub="so'm"
            icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" /></svg>}
          />
          <StatCard
            color="amber"
            loading={statsLoading}
            label="Jami qarzlar"
            value={debtStats ? `${fmt(debtStats.total_debt)} so'm` : '—'}
            sub={debtStats ? `${debtStats.total_debtors || 0} ta qarzdor` : ''}
            icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          />
          <StatCard
            color="violet"
            loading={statsLoading}
            label="AI tavsiyalar"
            value={!statsLoading ? `${recommendations.length} ta` : '—'}
            sub="muhim xabar"
            icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          />
        </div>
      </div>

      {/* ─── Main Content ─────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">

        {/* ─── Chat Area ────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-0">
            {messages.length === 0 && !loading && (
              <div className="h-full flex flex-col items-center justify-center py-8">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center shadow-lg mb-4">
                  <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <h3 className="font-bold text-slate-700 text-lg mb-1">AI Copilot tayyor!</h3>
                <p className="text-slate-400 text-sm text-center max-w-xs mb-6">Savdo, qarz, mahsulot haqida so'rang yoki quyidagi tezkor tugmalardan birini tanlang</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 w-full max-w-lg">
                  {QUICK_PROMPTS.map((qp, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(qp.prompt)}
                      className="flex items-center gap-2 bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50 rounded-xl px-3 py-2.5 text-left transition-all group shadow-sm hover:shadow-md"
                    >
                      <span className="text-lg">{qp.icon}</span>
                      <span className="text-xs font-semibold text-slate-600 group-hover:text-blue-700">{qp.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(msg => (
              <MessageBubble
                key={msg.id}
                msg={msg}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                onDraftActionDone={handleDraftActionDone}
              />
            ))}

            {loading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>

          {/* ─── Input Area ───────────────────────────────────────── */}
          <div className="bg-white border-t border-slate-200 px-4 py-3 flex-shrink-0">
            {/* Quick prompts bar */}
            {messages.length > 0 && (
              <div className="flex gap-2 overflow-x-auto pb-2 mb-2 scrollbar-hide">
                {QUICK_PROMPTS.map((qp, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(qp.prompt)}
                    className="flex-shrink-0 text-[11px] font-semibold text-slate-500 hover:text-blue-600 bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-200 rounded-lg px-2.5 py-1 transition-all whitespace-nowrap"
                  >
                    {qp.icon} {qp.text}
                  </button>
                ))}
              </div>
            )}

            <div className="flex gap-2 items-end">
              <div className="flex-1 bg-slate-50 border border-slate-200 rounded-2xl px-4 py-2.5 focus-within:ring-2 focus-within:ring-blue-300 focus-within:border-blue-400 transition-all">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder="Savolingizni yozing... (Enter — yuborish, Shift+Enter — yangi qator)"
                  rows={1}
                  className="w-full bg-transparent outline-none text-sm text-slate-700 placeholder:text-slate-400 resize-none max-h-32 overflow-y-auto"
                  style={{ scrollbarWidth: 'none' }}
                  disabled={loading}
                />
              </div>

              {/* Mic button */}
              <button
                onClick={toggleRecording}
                disabled={loading}
                className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${
                  isRecording
                    ? 'bg-red-500 hover:bg-red-600 animate-pulse shadow-lg shadow-red-200'
                    : 'bg-slate-100 hover:bg-slate-200 text-slate-500 hover:text-slate-700'
                }`}
              >
                <svg className={`w-5 h-5 ${isRecording ? 'text-white' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </button>

              {/* Send button */}
              <button
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white flex items-center justify-center shadow-lg shadow-blue-200 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-5 h-5 rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* ─── Recommendations Panel ────────────────────────────── */}
        <div className="w-72 border-l border-slate-200 bg-white flex flex-col flex-shrink-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
            <svg className="w-4 h-4 text-violet-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="font-bold text-slate-700 text-sm">AI Tavsiyalar</h3>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {statsLoading && (
              <>
                {[1, 2, 3].map(i => (
                  <div key={i} className="bg-slate-50 rounded-xl p-3 animate-pulse">
                    <div className="h-3 bg-slate-200 rounded w-3/4 mb-2" />
                    <div className="h-2 bg-slate-100 rounded w-full mb-1" />
                    <div className="h-2 bg-slate-100 rounded w-5/6" />
                  </div>
                ))}
              </>
            )}

            {!statsLoading && recommendations.length === 0 && (
              <div className="text-center py-8">
                <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-6 h-6 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <p className="text-sm font-semibold text-slate-600">Hammasi yaxshi!</p>
                <p className="text-xs text-slate-400 mt-1">Hozircha maxsus tavsiyalar yo'q</p>
              </div>
            )}

            {recommendations.map((rec, i) => {
              const typeColors = {
                inactive_customers: { bg: 'bg-blue-50', border: 'border-blue-200', icon: '👥', dot: 'bg-blue-500' },
                low_stock: { bg: 'bg-amber-50', border: 'border-amber-200', icon: '📦', dot: 'bg-amber-500' },
                debtors: { bg: 'bg-red-50', border: 'border-red-200', icon: '💸', dot: 'bg-red-500' },
              };
              const style = typeColors[rec.type] || { bg: 'bg-slate-50', border: 'border-slate-200', icon: '💡', dot: 'bg-slate-400' };

              return (
                <div key={i} className={`${style.bg} border ${style.border} rounded-xl p-3 animate-fadeIn`}>
                  <div className="flex items-start gap-2 mb-2">
                    <span className="text-base">{style.icon}</span>
                    <div className="flex-1 min-w-0">
                      <p className="font-bold text-slate-700 text-xs leading-snug">{rec.title}</p>
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-relaxed mb-2">{rec.description}</p>
                  {rec.suggested_prompt && (
                    <button
                      onClick={() => sendMessage(rec.suggested_prompt)}
                      className="w-full text-[11px] font-bold text-blue-600 bg-white hover:bg-blue-50 border border-blue-200 rounded-lg py-1.5 transition-all active:scale-95"
                    >
                      AI ga yuborish →
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* Bottom info */}
          <div className="p-3 border-t border-slate-100">
            <div className="bg-gradient-to-br from-violet-50 to-blue-50 rounded-xl p-3 border border-violet-100">
              <p className="text-[10px] font-bold text-violet-700 mb-1">💡 Maslahat</p>
              <p className="text-[10px] text-slate-500 leading-relaxed">
                "Ali 500 000 so'm to'ladi" deb yozing — AI avtomatik qarzni yechib oladi.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
