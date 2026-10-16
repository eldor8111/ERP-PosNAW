import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { useLang } from '../../context/LangContext';
import {
  Sparkles,
  Plus,
  ArrowUp,
  ChevronsLeft,
  ChevronsRight,
  Star,
  MoreVertical,
  Trash2,
  Edit2,
  Copy,
  Check,
  Search,
  BarChart3,
  ShieldCheck,
  TrendingUp,
  Coins,
  Warehouse,
  Zap,
  Activity,
  Layers,
  FileSpreadsheet,
  Clock,
  ChevronRight,
  Compass,
  LineChart,
  Bot
} from 'lucide-react';

// ─── Formatting & Text ──────────────────────────────────────────────────────
const fmtSom = (num) => {
  if (num === null || num === undefined || isNaN(num)) return '0';
  return Number(num).toLocaleString('ru-RU');
};

function renderMarkdown(text) {
  if (!text) return '';
  let formatted = text
    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-slate-900">$1</strong>')
    .replace(/\*(.*?)\*/g, '<em class="italic text-slate-700">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="bg-indigo-50 text-indigo-700 font-mono px-1.5 py-0.5 rounded text-xs border border-indigo-100 font-medium">$1</code>');

  // Polish bullet items into executive structured rows
  const lines = formatted.split('\n');
  const polished = lines.map((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('• ') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const content = trimmed.replace(/^[•\-\*]\s*/, '');
      return `<div class="flex items-start gap-2 my-1"><span class="w-1.5 h-1.5 rounded-full bg-indigo-500 mt-2 shrink-0"></span><div class="flex-1">${content}</div></div>`;
    }
    return line;
  });

  return polished.join('<br/>').replace(/(<br\/>\s*){3,}/g, '<br/><br/>');
}

// ─── Executive Intelligence Modes (Ultra-Premium Badges) ────────────────────
const INTELLIGENCE_MODES = [
  {
    id: 'audit',
    name: "To'liq Audit & Tahlil",
    shortName: 'Audit',
    badge: 'SQL Pro',
    desc: "Baza bo'yicha chuqur mantiqiy hisob-kitob, SQL aggregatsiya va jadvallar",
    glowColor: 'shadow-indigo-500/15 ring-2 ring-indigo-500/25 border-indigo-200/90',
    pillBg: 'bg-indigo-50 text-indigo-700 border border-indigo-200/80',
    renderIcon: (isActive) => (
      <div
        className={`w-7 h-7 rounded-xl flex items-center justify-center transition-all ${
          isActive
            ? 'bg-gradient-to-tr from-blue-600 via-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/35 ring-1 ring-white/30'
            : 'bg-slate-100 text-slate-500 group-hover:bg-indigo-50 group-hover:text-indigo-600 border border-slate-200/70'
        }`}
      >
        <BarChart3 className="w-3.5 h-3.5 stroke-[2.3]" />
      </div>
    ),
  },
  {
    id: 'tezkor',
    name: 'Tezkor Xulosa',
    shortName: 'Tezkor',
    badge: 'Ekspress',
    desc: 'Muhim raqamlar, kassa va savdo soni qisqa satrlarda',
    glowColor: 'shadow-amber-500/15 ring-2 ring-amber-500/25 border-amber-200/90',
    pillBg: 'bg-amber-50 text-amber-700 border border-amber-200/80',
    renderIcon: (isActive) => (
      <div
        className={`w-7 h-7 rounded-xl flex items-center justify-center transition-all ${
          isActive
            ? 'bg-gradient-to-tr from-amber-500 via-orange-500 to-rose-500 text-white shadow-md shadow-orange-500/35 ring-1 ring-white/30'
            : 'bg-slate-100 text-slate-500 group-hover:bg-amber-50 group-hover:text-amber-600 border border-slate-200/70'
        }`}
      >
        <Zap className={`w-3.5 h-3.5 stroke-[2.3] ${isActive ? 'fill-white/30' : ''}`} />
      </div>
    ),
  },
  {
    id: 'nazorat',
    name: 'Xatarlar Nazorati',
    shortName: 'Nazorat',
    badge: 'Radar',
    desc: 'Qarzdorlik muddati, minus qoldiqlar va tovar tanqisligi',
    glowColor: 'shadow-emerald-500/15 ring-2 ring-emerald-500/25 border-emerald-200/90',
    pillBg: 'bg-emerald-50 text-emerald-700 border border-emerald-200/80',
    renderIcon: (isActive) => (
      <div
        className={`w-7 h-7 rounded-xl flex items-center justify-center transition-all ${
          isActive
            ? 'bg-gradient-to-tr from-emerald-500 via-teal-500 to-cyan-600 text-white shadow-md shadow-emerald-500/35 ring-1 ring-white/30'
            : 'bg-slate-100 text-slate-500 group-hover:bg-emerald-50 group-hover:text-emerald-600 border border-slate-200/70'
        }`}
      >
        <ShieldCheck className="w-3.5 h-3.5 stroke-[2.3]" />
      </div>
    ),
  },
];

// ─── Preloaded Sessions (Business Intelligence) ─────────────────────────────
const INITIAL_SESSIONS = [
  {
    id: 'session_sales_audit',
    title: 'Savdolar va sof tushum',
    category: 'Hisobotlar',
    isPinned: true,
    mode: 'audit',
    updatedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
    messages: [
      {
        id: 1,
        role: 'user',
        content: 'Tizimda jami nechta sotuv qilingan va tushum qancha?',
        timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
      },
      {
        id: 2,
        role: 'assistant',
        content: '📊 **Savdolar bo\'yicha yakuniy ma\'lumot:**\n\n• **Haqiqiy sotuvlar soni:** 8 ta savdo hujjati\n• **Jami savdo aylanmasi:** 1,810,000 so\'m\n• **Naqd to\'langan:** 210,000 so\'m\n• **Qarzga berilgan:** 1,600,000 so\'m\n\n*(Eslatma: Qaytarilgan tovarlar sotuvlar aylanmasidan alohida hisobga olingan).*',
        timestamp: new Date(Date.now() - 3600000 * 2 + 1000).toISOString(),
      }
    ]
  },
  {
    id: 'session_debts_registry',
    title: 'Qarzdorlar reestri',
    category: 'Hisobotlar',
    isPinned: true,
    mode: 'nazorat',
    updatedAt: new Date(Date.now() - 3600000 * 5).toISOString(),
    messages: []
  },
  {
    id: 'session_stock_control',
    title: 'Ombor zaxiralari nazorati',
    category: 'Bugun',
    isPinned: false,
    mode: 'audit',
    updatedAt: new Date(Date.now() - 3600000 * 8).toISOString(),
    messages: []
  },
  {
    id: 'session_cash_summary',
    title: 'Kassa va to\'lovlar oqimi',
    category: 'Bugun',
    isPinned: false,
    mode: 'tezkor',
    updatedAt: new Date(Date.now() - 3600000 * 12).toISOString(),
    messages: []
  }
];

const loadPersistedSessions = () => {
  try {
    const saved = localStorage.getItem('ecode_ai_sessions_v3');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (e) {
    console.warn('Failed to load sessions:', e);
  }
  return INITIAL_SESSIONS;
};

const getInitialActiveSessionId = (allSessions) => {
  try {
    const savedActive = localStorage.getItem('ecode_ai_active_session_id');
    // If user explicitly pressed "New Chat"
    if (savedActive === 'new') {
      return 'new';
    }
    // If user was previously inside an active session, stay on it!
    if (savedActive) {
      const match = allSessions.find((s) => s.id === savedActive);
      if (match) return match.id;
    }
    // Fallback: Default to most recent session with messages
    const withMessages = allSessions.find((s) => s.messages && s.messages.length > 0);
    if (withMessages) return withMessages.id;
    if (allSessions.length > 0) return allSessions[0].id;
  } catch (e) {
    console.warn('Failed to restore activeSessionId:', e);
  }
  return 'new';
};

export default function EcodeAI() {
  const { t } = useLang();
  const [sessions, setSessions] = useState(loadPersistedSessions);
  const [activeSessionId, setActiveSessionId] = useState(() => getInitialActiveSessionId(sessions));
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeMode, setActiveMode] = useState(() => {
    try {
      const savedMode = localStorage.getItem('ecode_ai_active_mode');
      if (savedMode && ['audit', 'tezkor', 'nazorat'].includes(savedMode)) {
        return savedMode;
      }
    } catch (e) {}
    return 'audit';
  });
  const [activeMenuSessionId, setActiveMenuSessionId] = useState(null);
  const [editingTitleId, setEditingTitleId] = useState(null);
  const [editTitleVal, setEditTitleVal] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedMsgId, setCopiedMsgId] = useState(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Save sessions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('ecode_ai_sessions_v3', JSON.stringify(sessions));
    } catch (e) {
      console.error('Save sessions error:', e);
    }
  }, [sessions]);

  // Persist activeSessionId across navigation (like ChatGPT / Claude)
  useEffect(() => {
    try {
      if (activeSessionId) {
        localStorage.setItem('ecode_ai_active_session_id', activeSessionId);
        localStorage.setItem('ecode_ai_active_session_time', Date.now().toString());
      }
    } catch (e) {
      console.error('Save active session error:', e);
    }
  }, [activeSessionId]);

  // Persist activeMode
  useEffect(() => {
    try {
      if (activeMode) {
        localStorage.setItem('ecode_ai_active_mode', activeMode);
      }
    } catch (e) {
      console.error('Save active mode error:', e);
    }
  }, [activeMode]);

  // Current session
  const currentSession = sessions.find((s) => s.id === activeSessionId) || null;
  const currentMessages = currentSession ? currentSession.messages : [];

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [currentMessages, loading]);

  const handleSelectSession = (id) => {
    setActiveSessionId(id);
    localStorage.setItem('ecode_ai_active_session_id', id);
    localStorage.setItem('ecode_ai_active_session_time', Date.now().toString());
    const target = sessions.find((s) => s.id === id);
    if (target?.mode) {
      setActiveMode(target.mode);
    }
  };

  const handleModeChange = (modeId) => {
    setActiveMode(modeId);
    if (activeSessionId && activeSessionId !== 'new') {
      setSessions((prev) =>
        prev.map((s) => (s.id === activeSessionId ? { ...s, mode: modeId } : s))
      );
    }
  };

  const handleNewChat = () => {
    setActiveSessionId('new');
    localStorage.setItem('ecode_ai_active_session_id', 'new');
    setInput('');
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleTogglePin = (id, e) => {
    e?.stopPropagation();
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === id) {
          const nextPinned = !s.isPinned;
          return {
            ...s,
            isPinned: nextPinned,
            category: nextPinned ? 'Hisobotlar' : 'Bugun',
          };
        }
        return s;
      })
    );
    toast.success('Hisobot saqlandi');
    setActiveMenuSessionId(null);
  };

  const handleDeleteChat = (id, e) => {
    e?.stopPropagation();
    const remaining = sessions.filter((s) => s.id !== id);
    setSessions(remaining);
    if (activeSessionId === id) {
      const nextId = remaining.length > 0 ? remaining[0].id : 'new';
      setActiveSessionId(nextId);
      localStorage.setItem('ecode_ai_active_session_id', nextId);
    }
    toast.success("Muloqot o'chirildi");
    setActiveMenuSessionId(null);
  };

  const handleStartRename = (s, e) => {
    e?.stopPropagation();
    setEditingTitleId(s.id);
    setEditTitleVal(s.title);
    setActiveMenuSessionId(null);
  };

  const handleSaveRename = (id) => {
    if (!editTitleVal.trim()) {
      setEditingTitleId(null);
      return;
    }
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title: editTitleVal.trim() } : s))
    );
    setEditingTitleId(null);
    toast.success("Nomi yangilandi");
  };

  const handleCopyMessage = (id, text) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(id);
    setTimeout(() => setCopiedMsgId(null), 2000);
    toast.success('Nusxa olindi');
  };

  const sendMessage = async (customText = null) => {
    const textToSend = (customText !== null ? customText : input).trim();
    if (!textToSend || loading) return;

    let targetSessionId = activeSessionId;
    let updatedSessions = [...sessions];

    if (activeSessionId === 'new') {
      const newId = `session_${Date.now()}`;
      const generatedTitle =
        textToSend.length > 28 ? textToSend.slice(0, 28) + '...' : textToSend;
      const newSession = {
        id: newId,
        title: generatedTitle,
        category: 'Bugun',
        isPinned: false,
        mode: activeMode,
        updatedAt: new Date().toISOString(),
        messages: [],
      };
      updatedSessions = [newSession, ...updatedSessions];
      targetSessionId = newId;
      setActiveSessionId(newId);
    }

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: textToSend,
      timestamp: new Date().toISOString(),
    };

    setSessions(
      updatedSessions.map((s) =>
        s.id === targetSessionId
          ? {
              ...s,
              messages: [...s.messages, userMsg],
              updatedAt: new Date().toISOString(),
            }
          : s
      )
    );

    setInput('');
    setLoading(true);

    try {
      const res = await api.post('/ai/chat', {
        message: textToSend,
        conversation_id: targetSessionId,
        mode: activeMode,
      });

      const data = res.data;
      const aiReply = data.reply || "Ma'lumotlar tahlili yakunlandi.";

      const aiMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: aiReply,
        action: data.action || null,
        timestamp: new Date().toISOString(),
        confirmed: false,
        cancelled: false,
      };

      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId
            ? { ...s, messages: [...s.messages, aiMsg], updatedAt: new Date().toISOString() }
            : s
        )
      );
    } catch (e) {
      const errMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `❌ So'rov bajarilmadi: ${e.response?.data?.detail || e.message}`,
        timestamp: new Date().toISOString(),
      };
      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId ? { ...s, messages: [...s.messages, errMsg] } : s
        )
      );
      toast.error("AI tahlilida xatolik");
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 80);
    }
  };

  // Distinctive Executive Intelligence Bento-Cards (NOT Hippo copy!)
  const EXECUTIVE_CARDS = [
    {
      id: 'c1',
      tag: 'Savdo & Kassa',
      title: 'Haqiqiy Savdolar Xulosasi',
      query: "Tizim ro'yxatdan o'tilgandan beri nechta haqiqiy sotuv qilingan va umumiy tushum qancha?",
      metric: '8 ta savdo',
      sub: 'Aylanma va kassa holati',
      icon: <Coins className="w-5 h-5 text-blue-600" />,
      bg: 'from-blue-50/70 to-indigo-50/40 border-blue-100 hover:border-blue-300',
    },
    {
      id: 'c2',
      tag: 'Moliyaviy Xatar',
      title: 'Qarzdorlik & Balans',
      query: "Kompaniyada jami qancha qarzdorlik bor va eng yirik qarzdorlar kimlar?",
      metric: 'Qarzlar tahlili',
      sub: 'Valyutalar va muddatlar',
      icon: <ShieldCheck className="w-5 h-5 text-emerald-600" />,
      bg: 'from-emerald-50/70 to-teal-50/40 border-emerald-100 hover:border-emerald-300',
    },
    {
      id: 'c3',
      tag: 'Ombor & Moddiy Qoldiq',
      title: 'Qoldiqlar & Defitsit',
      query: "Omborda qaysi mahsulotlar qoldig'i kam qolgan yoki minusga tushgan?",
      metric: 'Zaxira nazorati',
      sub: 'Tanqislik xavfi',
      icon: <Warehouse className="w-5 h-5 text-amber-600" />,
      bg: 'from-amber-50/70 to-orange-50/40 border-amber-100 hover:border-amber-300',
    },
    {
      id: 'c4',
      tag: 'Rentabellik',
      title: 'Top Mahsulotlar Dinamikasi',
      query: "Bu oyda eng ko'p sotilgan tovarlar va ularning sof marjasi qanday?",
      metric: 'Top-10 tovar',
      sub: 'Eng serdaromad pozitsiyalar',
      icon: <TrendingUp className="w-5 h-5 text-purple-600" />,
      bg: 'from-purple-50/70 to-fuchsia-50/40 border-purple-100 hover:border-purple-300',
    },
  ];

  const pinnedSessions = sessions.filter((s) => s.isPinned);
  const regularSessions = sessions.filter((s) => !s.isPinned);

  const filteredRegular = regularSessions.filter((s) =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const filteredPinned = pinnedSessions.filter((s) =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-[calc(100vh-68px)] w-full overflow-hidden bg-white text-slate-800 font-sans -m-3 md:-m-6">
      {/* ── LEFT SIDEBAR (Executive Muloqotlar Tarixi) ──────────────────── */}
      <aside
        className={`${
          sidebarOpen ? 'w-[290px]' : 'w-0'
        } transition-all duration-300 ease-in-out border-r border-slate-200/80 bg-slate-50/80 flex flex-col shrink-0 overflow-hidden relative select-none`}
      >
        {/* Top Header */}
        <div className="p-4 flex items-center justify-between border-b border-slate-200/60 bg-white/60 backdrop-blur-sm">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-violet-600 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="font-bold text-slate-800 text-[15px] leading-tight flex items-center gap-1.5">
                <span>E-Code AI</span>
                <span className="text-[9px] font-black tracking-widest bg-indigo-100 text-indigo-700 px-1.5 py-0.2 rounded uppercase">PRO</span>
              </div>
              <div className="text-[10px] text-slate-400 font-medium">Boshqaruv Tahlil Tizimi</div>
            </div>
          </div>

          <button
            onClick={() => setSidebarOpen(false)}
            title="Panelni yopish"
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-lg transition-colors cursor-pointer"
          >
            <ChevronsLeft className="w-4 h-4" />
          </button>
        </div>

        {/* New Session Button */}
        <div className="p-3">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold text-xs shadow-md shadow-blue-500/20 transition-all active:scale-98 cursor-pointer"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            <span>Yangi Tahlil Boshlash</span>
          </button>
        </div>

        {/* Search */}
        {sessions.length > 4 && (
          <div className="px-3 pb-2">
            <div className="relative flex items-center">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 pointer-events-none" />
              <input
                type="text"
                placeholder="Hisobotlarni qidirish..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-white border border-slate-200/90 rounded-lg outline-none focus:border-indigo-400 text-slate-700"
              />
            </div>
          </div>
        )}

        {/* Chat History List */}
        <div className="flex-1 overflow-y-auto px-2 space-y-4 py-2 scrollbar-thin scrollbar-thumb-slate-200">
          {/* Pinned Reports */}
          {filteredPinned.length > 0 && (
            <div>
              <div className="px-2 pb-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Star className="w-3 h-3 text-amber-500 fill-amber-500" />
                <span>Muhim Hisobotlar</span>
              </div>
              <div className="space-y-0.5">
                {filteredPinned.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    isActive={activeSessionId === s.id}
                    onSelect={() => handleSelectSession(s.id)}
                    isPinned={true}
                    onTogglePin={handleTogglePin}
                    onDelete={handleDeleteChat}
                    onStartRename={handleStartRename}
                    editingId={editingTitleId}
                    editVal={editTitleVal}
                    setEditVal={setEditTitleVal}
                    onSaveRename={handleSaveRename}
                    activeMenuId={activeMenuSessionId}
                    setActiveMenuId={setActiveMenuSessionId}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Recent */}
          <div>
            <div className="px-2 pb-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Clock className="w-3 h-3 text-slate-400" />
              <span>Yaqindagi Muloqotlar</span>
            </div>
            <div className="space-y-0.5">
              {filteredRegular.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  isActive={activeSessionId === s.id}
                  onSelect={() => handleSelectSession(s.id)}
                  isPinned={false}
                  onTogglePin={handleTogglePin}
                  onDelete={handleDeleteChat}
                  onStartRename={handleStartRename}
                  editingId={editingTitleId}
                  editVal={editTitleVal}
                  setEditVal={setEditTitleVal}
                  onSaveRename={handleSaveRename}
                  activeMenuId={activeMenuSessionId}
                  setActiveMenuId={setActiveMenuSessionId}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Footer Security Badge */}
        <div className="p-3 border-t border-slate-200/80 bg-white/50 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-semibold text-slate-700 text-[11px]">E-Code Analytics v2</span>
          </div>
          <span className="text-[10px] bg-slate-100 text-slate-600 font-bold px-2 py-0.5 rounded-full border border-slate-200">
            RLS Active
          </span>
        </div>
      </aside>

      {/* ── RIGHT MAIN CANVAS ───────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col h-full bg-white relative overflow-hidden">
        {/* Top Navbar */}
        <div className="h-16 border-b border-slate-200/80 flex items-center justify-between px-4 sm:px-6 shrink-0 bg-white/90 backdrop-blur-md z-10">
          <div className="flex items-center gap-3 min-w-0">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                title="Tarixni ochish"
                className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer shrink-0"
              >
                <ChevronsRight className="w-5 h-5" />
              </button>
            )}
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
              <span className="font-extrabold text-slate-900 text-sm sm:text-base tracking-tight truncate">
                {currentSession ? currentSession.title : 'Boshqaruv Tahlil Markazi'}
              </span>
              {currentSession?.isPinned && (
                <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500 shrink-0" />
              )}
            </div>
          </div>

          {/* Luxury Executive Mode Switcher Pills */}
          <div className="flex items-center gap-1.5 bg-slate-100/90 backdrop-blur-md p-1.5 rounded-2xl border border-slate-200/80 shadow-inner">
            {INTELLIGENCE_MODES.map((m) => {
              const isActive = activeMode === m.id;
              return (
                <button
                  key={m.id}
                  onClick={() => handleModeChange(m.id)}
                  title={m.desc}
                  className={`group relative flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 cursor-pointer ${
                    isActive
                      ? `bg-white text-slate-900 shadow-md ${m.glowColor}`
                      : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
                  }`}
                >
                  {m.renderIcon(isActive)}
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold tracking-tight text-[12px]">{m.shortName}</span>
                    <span
                      className={`hidden md:inline text-[9px] font-extrabold uppercase px-1.5 py-0.2 rounded-md transition-colors ${
                        isActive
                          ? m.pillBg
                          : 'bg-slate-200/60 text-slate-500'
                      }`}
                    >
                      {m.badge}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Central Viewport */}
        <div className="flex-1 overflow-y-auto relative flex flex-col">
          {/* A) UNIQUE EXECUTIVE STUDIO (When no messages) */}
          {(!currentSession || currentMessages.length === 0) && (
            <div className="flex-1 flex flex-col items-center justify-center p-6 max-w-4xl w-full mx-auto">
              {/* Brand Aura */}
              <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-100/80 px-3.5 py-1.5 rounded-full text-indigo-700 font-bold text-xs mb-4 shadow-xs">
                <Sparkles className="w-3.5 h-3.5 text-indigo-600 animate-pulse" />
                <span>E-Code Business Intelligence & Copilot</span>
              </div>

              {/* Headline */}
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight text-center mb-2">
                Korxona bo'yicha aniq ma'lumot va hisobotlar
              </h1>
              <p className="text-slate-500 text-xs sm:text-sm text-center mb-8 max-w-xl">
                Sotuvlar soni, kassa tushumlari, qarzdorlik holati va ombor qoldiqlarini bir zumda tahlil qiling.
              </p>

              {/* Main Executive Command Bar */}
              <div className="w-full max-w-2xl mb-8">
                <div className="flex items-center bg-white border-2 border-indigo-400/90 rounded-2xl p-2 shadow-xl shadow-indigo-500/10 hover:border-indigo-600 focus-within:border-indigo-600 focus-within:ring-4 focus-within:ring-indigo-100 transition-all">
                  <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0 ml-1">
                    <Bot className="w-5 h-5" />
                  </div>

                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                      }
                    }}
                    placeholder="Masalan: Tizimda jami nechta sotuv qilingan va tushum qancha?..."
                    className="flex-1 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 bg-transparent outline-none"
                  />

                  <button
                    type="button"
                    onClick={() => sendMessage()}
                    disabled={!input.trim() || loading}
                    className="w-10 h-10 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-40 text-white flex items-center justify-center shadow-md active:scale-95 transition-all cursor-pointer shrink-0"
                  >
                    <ArrowUp className="w-4 h-4 stroke-[2.5]" />
                  </button>
                </div>
              </div>

              {/* Bento Grid Executive Prompt Cards */}
              <div className="w-full max-w-2xl grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-left">
                {EXECUTIVE_CARDS.map((card) => (
                  <button
                    key={card.id}
                    onClick={() => sendMessage(card.query)}
                    className={`p-4 rounded-2xl border bg-gradient-to-br ${card.bg} transition-all hover:shadow-md active:scale-99 cursor-pointer group text-left relative overflow-hidden`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-white/70 px-2 py-0.5 rounded-md border border-slate-200/50">
                        {card.tag}
                      </span>
                      <div className="w-8 h-8 rounded-xl bg-white shadow-xs flex items-center justify-center group-hover:scale-110 transition-transform">
                        {card.icon}
                      </div>
                    </div>

                    <div className="font-bold text-slate-800 text-sm mb-1 group-hover:text-indigo-700 transition-colors">
                      {card.title}
                    </div>

                    <div className="text-xs text-slate-500 flex items-center justify-between mt-2">
                      <span>{card.sub}</span>
                      <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:translate-x-1 transition-transform" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* B) ACTIVE CHAT STREAM */}
          {currentSession && currentMessages.length > 0 && (
            <div className="flex-1 p-4 sm:p-6 space-y-6 max-w-3xl w-full mx-auto">
              {currentMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 animate-fadeIn ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-violet-600 text-white flex items-center justify-center shadow-md shadow-indigo-500/20 shrink-0 mt-0.5">
                      <Sparkles className="w-4 h-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] sm:max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-xs relative group ${
                      msg.role === 'user'
                        ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-br-xs'
                        : 'bg-slate-50 border border-slate-200/80 text-slate-800 rounded-bl-xs'
                    }`}
                  >
                    <div
                      className="prose prose-sm max-w-none break-words"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                    />

                    <div
                      className={`flex items-center justify-between gap-4 mt-2 text-[10px] ${
                        msg.role === 'user' ? 'text-blue-200' : 'text-slate-400'
                      }`}
                    >
                      <span>
                        {new Date(msg.timestamp || Date.now()).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>

                      <button
                        onClick={() => handleCopyMessage(msg.id, msg.content)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity hover:underline cursor-pointer flex items-center gap-1"
                      >
                        {copiedMsgId === msg.id ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-500" />
                            <span>Nusxalandi</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            <span>Nusxa</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex gap-3 justify-start animate-fadeIn">
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-violet-600 text-white flex items-center justify-center shadow-md shrink-0">
                    <Sparkles className="w-4 h-4 animate-spin" />
                  </div>
                  <div className="bg-slate-50 border border-slate-200/80 rounded-2xl rounded-bl-xs px-4 py-3 shadow-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                      <span className="text-xs text-slate-500 ml-2 font-medium">Baza ma'lumotlari tahlil qilinmoqda...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Bottom Input (When messages exist) */}
        {currentSession && currentMessages.length > 0 && (
          <div className="p-3 sm:p-4 border-t border-slate-100 bg-white/95 backdrop-blur-md">
            <div className="max-w-3xl mx-auto flex items-center bg-white border-2 border-indigo-400/80 rounded-2xl p-1.5 shadow-lg shadow-indigo-500/5 focus-within:border-indigo-600 focus-within:ring-4 focus-within:ring-indigo-100 transition-all">
              <button
                type="button"
                onClick={handleNewChat}
                title="Yangi tahlil"
                className="w-9 h-9 rounded-xl text-slate-400 hover:text-indigo-600 hover:bg-slate-100 flex items-center justify-center transition-colors cursor-pointer shrink-0"
              >
                <Plus className="w-5 h-5" />
              </button>

              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder="Savol yoki buyruq yozing..."
                className="flex-1 px-3 py-1.5 text-sm text-slate-800 placeholder:text-slate-400 bg-transparent outline-none"
              />

              <button
                type="button"
                onClick={() => sendMessage()}
                disabled={!input.trim() || loading}
                className="w-9 h-9 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-40 text-white flex items-center justify-center shadow-md active:scale-95 transition-all cursor-pointer shrink-0"
              >
                <ArrowUp className="w-4 h-4 stroke-[2.5]" />
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// ─── Session Row Subcomponent ───────────────────────────────────────────────
function SessionRow({
  session,
  isActive,
  onSelect,
  isPinned,
  onTogglePin,
  onDelete,
  onStartRename,
  editingId,
  editVal,
  setEditVal,
  onSaveRename,
  activeMenuId,
  setActiveMenuId,
}) {
  const isEditing = editingId === session.id;
  const isMenuOpen = activeMenuId === session.id;

  return (
    <div
      onClick={onSelect}
      className={`group relative flex items-center justify-between px-2.5 py-2 rounded-xl text-xs transition-all cursor-pointer ${
        isActive
          ? 'bg-indigo-50 border border-indigo-200/80 text-indigo-950 font-semibold shadow-xs'
          : 'text-slate-600 hover:bg-slate-200/50 hover:text-slate-900'
      }`}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        {isPinned ? (
          <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500 shrink-0" />
        ) : (
          <span className="w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-indigo-500 shrink-0" />
        )}

        {isEditing ? (
          <input
            type="text"
            value={editVal}
            onChange={(e) => setEditVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSaveRename(session.id);
              if (e.key === 'Escape') onSaveRename(session.id);
            }}
            onBlur={() => onSaveRename(session.id)}
            autoFocus
            onClick={(e) => e.stopPropagation()}
            className="w-full bg-white px-1.5 py-0.5 border border-indigo-400 rounded outline-none text-xs text-slate-800"
          />
        ) : (
          <span className="truncate flex-1 select-none">{session.title}</span>
        )}
      </div>

      {!isEditing && (
        <div className="relative shrink-0 flex items-center">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setActiveMenuId(isMenuOpen ? null : session.id);
            }}
            className={`p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors opacity-0 group-hover:opacity-100 ${
              isMenuOpen ? 'opacity-100 bg-slate-200/60 text-slate-700' : ''
            }`}
          >
            <MoreVertical className="w-3.5 h-3.5" />
          </button>

          {isMenuOpen && (
            <div
              onClick={(e) => e.stopPropagation()}
              className="absolute right-0 top-full mt-1 w-36 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-50 text-[11px]"
            >
              <button
                onClick={(e) => onTogglePin(session.id, e)}
                className="w-full text-left px-2.5 py-1.5 hover:bg-slate-50 flex items-center gap-2 text-slate-700 cursor-pointer"
              >
                <Star className="w-3.5 h-3.5 text-amber-500" />
                <span>{isPinned ? 'Olib tashlash' : 'Saqlash (Yulduzcha)'}</span>
              </button>

              <button
                onClick={(e) => onStartRename(session, e)}
                className="w-full text-left px-2.5 py-1.5 hover:bg-slate-50 flex items-center gap-2 text-slate-700 cursor-pointer"
              >
                <Edit2 className="w-3.5 h-3.5 text-indigo-500" />
                <span>Qayta nomlash</span>
              </button>

              <div className="border-t border-slate-100 my-1" />

              <button
                onClick={(e) => onDelete(session.id, e)}
                className="w-full text-left px-2.5 py-1.5 hover:bg-red-50 text-red-600 flex items-center gap-2 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5 text-red-500" />
                <span>O'chirish</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
