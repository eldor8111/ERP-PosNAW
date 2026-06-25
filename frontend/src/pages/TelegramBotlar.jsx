import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'
import { MessageCircleHeart } from 'lucide-react'

// ─── ICONS ─────────────────────────────────────────────────────────────────
const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const ArrowRight = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-[18px] h-[18px]">
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="12 5 19 12 12 19" />
  </svg>
)

// ─── MAIN COMPONENT ────────────────────────────────────────────────────────
export default function TelegramBotlar() {
  const navigate = useNavigate()
  const { t } = useLang()
  const [activeBot, setActiveBot] = useState(0)
  
  useSeo(
    "Telegram Bot Yaratish – Biznes uchun Avtomatik Botlar | E-code",
    "E-code: savdo, yetkazib berish, support va boshqa maqsadlar uchun Telegram botlar ishlab chiqamiz. O'zbekistonda professional Telegram bot yaratish xizmati."
  )

  const botTypes = [
    { icon: '🛒', color: '#10b981', bg: 'bg-emerald-500/10', borderActive: 'border-l-emerald-500 text-emerald-500 bg-emerald-500/10', gradient: 'from-emerald-500/80 to-emerald-500', btnBg: 'from-emerald-500 to-emerald-500/80', title: t('tg.b1.t') || 'E-Commerce Botlar', desc: t('tg.b1.d'), examples: [t('tg.b1.f1'), t('tg.b1.f2'), t('tg.b1.f3'), t('tg.b1.f4'), t('tg.b1.f5')], popular: false },
    { icon: '🤖', color: '#2563eb', bg: 'bg-blue-600/10', borderActive: 'border-l-blue-600 text-blue-600 bg-blue-600/10', gradient: 'from-blue-600/80 to-blue-600', btnBg: 'from-blue-600 to-blue-600/80', title: t('tg.b2.t') || 'Avtomatizatsiya Botlari', desc: t('tg.b2.d'), examples: [t('tg.b2.f1'), t('tg.b2.f2'), t('tg.b2.f3'), t('tg.b2.f4'), t('tg.b2.f5')], popular: true },
    { icon: '📢', color: '#f59e0b', bg: 'bg-amber-500/10', borderActive: 'border-l-amber-500 text-amber-500 bg-amber-500/10', gradient: 'from-amber-500/80 to-amber-500', btnBg: 'from-amber-500 to-amber-500/80', title: t('tg.b3.t') || 'Kanal va Guruh Botlari', desc: t('tg.b3.d'), examples: [t('tg.b3.f1'), t('tg.b3.f2'), t('tg.b3.f3'), t('tg.b3.f4'), t('tg.b3.f5')], popular: false },
    { icon: '📊', color: '#8b5cf6', bg: 'bg-violet-500/10', borderActive: 'border-l-violet-500 text-violet-500 bg-violet-500/10', gradient: 'from-violet-500/80 to-violet-500', btnBg: 'from-violet-500 to-violet-500/80', title: t('tg.b4.t') || 'CRM & Data Botlar', desc: t('tg.b4.d'), examples: [t('tg.b4.f1'), t('tg.b4.f2'), t('tg.b4.f3'), t('tg.b4.f4'), t('tg.b4.f5')], popular: false },
    { icon: '🎓', color: '#0891b2', bg: 'bg-cyan-600/10', borderActive: 'border-l-cyan-600 text-cyan-600 bg-cyan-600/10', gradient: 'from-cyan-600/80 to-cyan-600', btnBg: 'from-cyan-600 to-cyan-600/80', title: t('tg.b5.t') || 'Ta\'lim va Kurs Botlari', desc: t('tg.b5.d'), examples: [t('tg.b5.f1'), t('tg.b5.f2'), t('tg.b5.f3'), t('tg.b5.f4'), t('tg.b5.f5')], popular: false },
    { icon: '💼', color: '#ef4444', bg: 'bg-red-500/10', borderActive: 'border-l-red-500 text-red-500 bg-red-500/10', gradient: 'from-red-500/80 to-red-500', btnBg: 'from-red-500 to-red-500/80', title: t('tg.b6.t') || 'Shaxsiy Brend Botlari', desc: t('tg.b6.d'), examples: [t('tg.b6.f1'), t('tg.b6.f2'), t('tg.b6.f3'), t('tg.b6.f4'), t('tg.b6.f5')], popular: false },
  ]

  const features = [
    { icon: '⚡', title: t('tg.feat.1.t') || 'Yuqori tezlik', desc: t('tg.feat.1.d') || 'Web-hook tizimida ishlovchi, soniyada minglab so\'rovlarga javob beradigan botlar.' },
    { icon: '🔗', title: t('tg.feat.2.t') || 'Tizimlar integratsiyasi', desc: t('tg.feat.2.d') || 'CRM, 1C, veb-sayt va to\'lov tizimlari (Click, Payme) bilan uzviy bog\'liqlik.' },
    { icon: '📈', title: t('tg.feat.3.t') || 'Kengaytirilgan statistika', desc: t('tg.feat.3.d') || 'Foydalanuvchilar oqimi, faollik va barcha amallarni kuzatish paneli.' },
    { icon: '🛡️', title: t('tg.feat.4.t') || 'Xavfsiz server', desc: t('tg.feat.4.d') || 'Ma\'lumotlar xavfsizligi va botning 24/7 uzluksiz ishlash kafolati.' },
    { icon: '🌍', title: t('tg.feat.5.t') || 'Ko\'p tillilik', desc: t('tg.feat.5.d') || 'Istalgan tillarda mukammal va to\'g\'ri ishlovchi interfeys tizimi.' },
    { icon: '♾️', title: t('tg.feat.6.t') || 'Moslashuvchan funksiyalar', desc: t('tg.feat.6.d') || 'Sizning biznesingiz ehtiyojlaridan kelib chiqqan maxsus algoritmlar.' },
  ]

  const showcase = [
    { emoji: '🏪', name: t('tg.port.1.t') || 'E-Do\'kon Bot', desc: t('tg.port.1.d'), users: t('tg.port.1.u') || '15,000+ foydalanuvchi', color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { emoji: '🎓', name: t('tg.port.2.t') || 'LMS Ta\'lim Bot', desc: t('tg.port.2.d'), users: t('tg.port.2.u') || '45,000+ talaba', color: 'text-blue-600', bg: 'bg-blue-600/10' },
    { emoji: '🏥', name: t('tg.port.3.t') || 'Klinika Navbat Bot', desc: t('tg.port.3.d'), users: t('tg.port.3.u') || '8,000+ bemor', color: 'text-violet-500', bg: 'bg-violet-500/10' },
  ]

  const plans = [
    { name: t('tg.p1.n') || 'Startap', badge: `⚡ ${t('tg.p1.b') || 'Tezkor'}`, label: t('tg.p1.l') || 'Oddiy yechimlar', hint: t('tg.p1.h'), popular: false, color: 'text-emerald-500', border: 'hover:border-emerald-500/30 shadow-emerald-500/5', bg: 'bg-emerald-500/5', btn: 'border-emerald-500 text-emerald-500 hover:bg-emerald-500 hover:text-white', desc: t('tg.p1.d'), features: [t('tg.p1.f1'), t('tg.p1.f2'), t('tg.p1.f3'), t('tg.p1.f4'), t('tg.p1.f5')] },
    { name: t('tg.p2.n') || 'Biznes', badge: `🔥 ${t('tg.p2.b') || 'Ommabop'}`, label: t('tg.p2.l') || 'Kengaytirilgan', hint: t('tg.p2.h'), popular: true, color: 'text-blue-600', border: 'border-blue-600 shadow-blue-600/10 scale-102 z-10', bg: 'bg-blue-600/5', btn: 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg shadow-blue-600/25', desc: t('tg.p2.d'), features: [t('tg.p2.f1'), t('tg.p2.f2'), t('tg.p2.f3'), t('tg.p2.f4'), t('tg.p2.f5'), t('tg.p2.f6')] },
    { name: t('tg.p3.n') || 'Premium', badge: `🏢 ${t('tg.p3.b') || 'Eksklyuziv'}`, label: t('tg.p3.l') || 'Murakkab tizimlar', hint: t('tg.p3.h'), popular: false, color: 'text-violet-500', border: 'hover:border-violet-500/30 shadow-violet-500/5', bg: 'bg-violet-500/5', btn: 'border-violet-500 text-violet-500 hover:bg-violet-500 hover:text-white', desc: t('tg.p3.d'), features: [t('tg.p3.f1'), t('tg.p3.f2'), t('tg.p3.f3'), t('tg.p3.f4'), t('tg.p3.f5'), t('tg.p3.f6')] },
  ]

  return (
    <LandingLayout>
      {/* Hero Section */}
      <section className="relative py-24 md:py-32 flex items-center bg-gradient-to-br from-[#0f172a] via-[#064e3b] to-[#0f172a]">
        {/* Background Dots */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.08)_1px,transparent_1px)] bg-[size:28px_28px] pointer-events-none" />
        
        <div className="max-w-[1400px] mx-auto px-4 w-full relative z-10 text-center">
          {/* Breadcrumb */}
          <div className="inline-flex items-center gap-2 text-sm text-white/50 mb-6 font-medium">
            <span onClick={() => navigate('/')} className="cursor-pointer hover:opacity-100 opacity-60 transition-opacity">{t('tg.bc.home') || 'Bosh sahifa'}</span>
            <span className="opacity-60">›</span>
            <span>{t('tg.bc.current') || 'Telegram Botlar'}</span>
          </div>
          
          {/* Badge Tag */}
          <div className="inline-block ml-3 px-5 py-2 bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded-full text-sm font-bold mb-8 animate-fadeIn">
            {t('tg.tag') || 'Telegram Bot Ishlab Chiqish'}
          </div>
          
          {/* Main Title */}
          <h1 className="text-[clamp(44px,7vw,72px)] font-black leading-[1.08] tracking-tight text-white mb-7 animate-[fadeInUp_0.7s_ease-out_0.1s_both]">
            {t('tg.hero.title1') || 'Biznesingizni'}<br />
            <span className="bg-gradient-to-r from-emerald-300 to-emerald-400 bg-clip-text text-transparent inline-block">
              {t('tg.hero.title2') || 'Telegramda'}
            </span> {t('tg.hero.title3') || 'avtomatlashtiring'}
          </h1>
          
          {/* Description */}
          <p className="text-lg md:text-xl text-white/70 max-w-[660px] mx-auto mb-12 leading-relaxed animate-[fadeInUp_0.7s_ease-out_0.2s_both]">
            {t('tg.hero.desc') || 'Mijozlar bilan aloqa, avtomatik savdo, to\'lovlar qabul qilish va CRM tizimlari bilan to\'liq integratsiyalashgan aqlli botlar.'}
          </p>
          
          {/* Stats Grid */}
          <div className="flex flex-wrap items-center justify-center gap-6 lg:gap-0 mb-12 bg-white/5 border border-white/10 rounded-2xl p-7 max-w-4xl mx-auto animate-[fadeInUp_0.7s_ease-out_0.3s_both]">
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">{t('tg.hero.stat1.val') || '100+'}</span>
              <span className="text-xs text-white/55 font-medium">{t('tg.hero.stat1.lbl') || 'Muvaffaqiyatli botlar'}</span>
            </div>
            <div className="hidden lg:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">{t('tg.hero.stat2.val') || '1M+'}</span>
              <span className="text-xs text-white/55 font-medium">{t('tg.hero.stat2.lbl') || 'Aktiv foydalanuvchilar'}</span>
            </div>
            <div className="hidden lg:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">{t('tg.hero.stat3.val') || '24/7'}</span>
              <span className="text-xs text-white/55 font-medium">{t('tg.hero.stat3.lbl') || 'Uzluksiz ishlash'}</span>
            </div>
            <div className="hidden lg:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">{t('tg.hero.stat4.val') || '5-10 kun'}</span>
              <span className="text-xs text-white/55 font-medium">{t('tg.hero.stat4.lbl') || 'Tayyor bo\'lish vaqti'}</span>
            </div>
          </div>
          
          {/* Hero CTAs */}
          <div className="flex flex-wrap gap-4 justify-center animate-[fadeInUp_0.7s_ease-out_0.4s_both]">
            <button 
              className="inline-flex items-center gap-2 bg-gradient-to-r from-emerald-600 to-emerald-500 text-white font-bold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 shadow-lg shadow-emerald-600/35 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-emerald-600/40"
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
            >
              {t('tg.hero.btn1') || 'Bot buyurtma qilish'} <ArrowRight />
            </button>
            <a 
              href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" 
              className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 backdrop-blur-md hover:bg-white/15 hover:-translate-y-0.5"
            >
              <MessageCircleHeart size={20} /> {t('tg.hero.btn2') || 'Bepul konsultatsiya'}
            </a>
          </div>
        </div>
      </section>

      {/* Bot Types Section */}
      <section className="py-24 max-w-[1400px] mx-auto">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-emerald-600/10 border border-emerald-600/15 rounded-full text-xs font-bold text-emerald-600 mb-4 uppercase tracking-wider">
            {t('tg.bot.tag') || 'Turlar'}
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
            {t('tg.bot.title') || 'Har qanday maqsad uchun botlar'}
          </h2>
          <p className="text-base text-slate-500 max-w-[560px] mx-auto">
            {t('tg.bot.desc') || 'Biznesingiz ehtiyojlaridan kelib chiqqan holda mukammal Telegram yechimlari'}
          </p>
        </div>

        {/* Tabs + Preview Grid */}
        <div className="flex gap-8 items-start">
          {/* Tabs Navigation */}
          <div className="min-w-90 flex flex-col gap-3">
            {botTypes.map((bot, idx) => (
              <button
                key={idx}
                className={`flex cursor-pointer items-center gap-4 p-5 rounded-2xl text-left border-l-4 transition-all duration-300 font-semibold border-transparent bg-slate-50 hover:bg-slate-100/80 ${
                  activeBot === idx ? bot.borderActive : ''
                }`}
                onClick={() => setActiveBot(idx)}
              >
                <span className="text-xl">{bot.icon}</span>
                <span className="flex-1 text-[15px]">{bot.title}</span>
                {bot.popular && <span className="text-xs bg-red-500 text-white px-2 py-0.5 rounded-full font-bold">TOP</span>}
              </button>
            ))}
          </div>

          {/* Interactive Preview Panel */}
          <div className="w-full flex gap-8 bg-white border border-slate-100 p-4 rounded-[32px] shadow-xl shadow-slate-100 animate-fadeIn" key={activeBot}>
            
            {/* Telegram Mockup */}
            <div className="bg-[#f4f7f9] rounded-2xl h-108 overflow-hidden border border-slate-200/60 shadow-sm flex flex-col">
              {/* Header */}
              <div className={`p-4 text-white flex items-center gap-3 bg-gradient-to-r ${botTypes[activeBot].gradient}`}>
                <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center text-xl shadow-inner">{botTypes[activeBot].icon}</div>
                <div>
                  <div className="font-bold text-sm tracking-wide">{botTypes[activeBot].title}</div>
                  <div className="text-[11px] text-white/80 flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block animate-pulse"></span> bot</div>
                </div>
              </div>
              {/* Messages Body */}
              <div className="p-4 flex flex-col gap-4 flex-1 overflow-y-auto text-xs">
                <div className="self-start max-w-[85%]">
                  <div className="bg-white p-3 rounded-2xl rounded-tl-none shadow-sm text-slate-800 leading-relaxed">
                    Salom! E-code bot tizimiga xush kelibsiz. Sizga qanday yordam bera olaman? 👋
                  </div>
                  <span className="text-[10px] text-slate-400 ml-1 mt-1 block">10:00</span>
                </div>
                <div className="self-end max-w-[85%] text-right">
                  <div className="bg-[#eff6ff] p-3 rounded-2xl rounded-tr-none shadow-sm text-slate-800 text-left">
                    Xizmatlar va imkoniyatlarni ko'rish
                  </div>
                  <span className="text-[10px] text-slate-400 mr-1 mt-1 block">10:01</span>
                </div>
                <div className="self-start max-w-[85%] w-full">
                  <div className="bg-white p-3 rounded-2xl rounded-tl-none shadow-sm text-slate-800 leading-relaxed">
                    {t('tg.mock.opt') || 'Quyidagi tugmalardan birini tanlang:'}
                  </div>
                  {/* Mockup Buttons */}
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    {botTypes[activeBot].examples.slice(0, 4).map((ex, i) => (
                      <div 
                        key={i} 
                        className="p-2.5 bg-slate-50 border rounded-xl text-center text-[11px] font-bold truncate transition-all"
                        style={{ borderColor: botTypes[activeBot].color + '30', color: botTypes[activeBot].color }}
                      >
                        {ex}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Details Column */}
            <div className="flex flex-col justify-center">
              <h3 className="text-2xl font-black mb-3" style={{ color: botTypes[activeBot].color }}>
                {botTypes[activeBot].title}
              </h3>
              <p className="text-slate-500 text-[15px] leading-relaxed mb-6">
                {botTypes[activeBot].desc}
              </p>
              
              <div className="flex flex-col gap-2.5 mb-8">
                {botTypes[activeBot].examples.map((ex, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm font-medium text-slate-700">
                    <span style={{ color: botTypes[activeBot].color }}><CheckIcon /></span> {ex}
                  </div>
                ))}
              </div>
              
              <button
                className={`inline-flex items-center justify-center gap-2 bg-gradient-to-r ${botTypes[activeBot].btnBg} text-white font-bold text-sm py-4 rounded-xl transition-all duration-300 hover:shadow-lg`}
                onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
              >
                {t('tg.mock.btn') || 'Ushbu botni buyurtma qilish'} <ArrowRight />
              </button>
            </div>

          </div>
        </div>
      </section>

      {/* Features Grid Section */}
      <section className="py-24 bg-gradient-to-b from-slate-50 to-white border-y border-black/[0.04]">
        <div className="max-w-[1400px] mx-auto px-4">
          <div className="text-center mb-16">
            <div className="inline-block px-4 py-1 bg-emerald-600/10 border border-emerald-600/15 rounded-full text-xs font-bold text-emerald-600 mb-4 uppercase tracking-wider">
              {t('tg.feat.tag') || 'Ustunliklar'}
            </div>
            <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
              {t('tg.feat.title') || 'Nega aynan E-code botlari?'}
            </h2>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f, i) => (
              <div key={i} className="bg-white border border-black/5 p-8 rounded-3xl shadow-sm hover:shadow-md transition-shadow">
                <div className="w-12 h-12 bg-slate-50 rounded-xl flex items-center justify-center text-xl mb-5 shadow-sm border border-black/[0.02]">
                  {f.icon}
                </div>
                <h3 className="text-lg font-bold text-slate-800 mb-2">{f.title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Showcase / Portfolio Section */}
      <section className="py-24 max-w-[1400px] mx-auto px-4">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-indigo-600/10 border border-indigo-600/15 rounded-full text-xs font-bold text-indigo-600 mb-4 uppercase tracking-wider">
            {t('tg.port.tag') || 'Keyslar'}
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
            {t('tg.port.title') || 'Ishga tushirilgan loyihalar'}
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {showcase.map((item, i) => (
            <div key={i} className="bg-white border border-slate-100 p-8 rounded-3xl text-center shadow-sm hover:shadow-md transition-all">
              <div className={`w-14 h-14 ${item.bg} rounded-2xl flex items-center justify-center text-2xl mx-auto mb-5`}>
                {item.emoji}
              </div>
              <h3 className={`text-lg font-bold mb-2 ${item.color}`}>{item.name}</h3>
              <p className="text-slate-500 text-sm leading-relaxed mb-4">{item.desc}</p>
              <div className="inline-block bg-slate-50 border border-slate-100 text-slate-600 font-bold text-xs px-3 py-1.5 rounded-full">
                {item.users}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing Section */}
      <section className="py-24 bg-gradient-to-b from-slate-50 to-white border-y border-black/[0.04]">
        <div className="max-w-[1400px] mx-auto px-4">
          <div className="text-center mb-16">
            <div className="inline-block px-4 py-1 bg-violet-600/10 border border-violet-600/15 rounded-full text-xs font-bold text-violet-600 mb-4 uppercase tracking-wider">
              {t('tg.plan.tag') || 'Tariflar'}
            </div>
            <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
              {t('tg.plan.title') || 'Shaffof va qulay narxlar'}
            </h2>
            <p className="text-base text-slate-500 max-w-[560px] mx-auto">
              {t('tg.plan.desc') || 'Loyiha murakkabligidan kelib chiqqan holda optimal paketlar'}
            </p>
          </div>

          {/* Dynamic Notice Banner */}
          <div className="flex flex-col md:flex-row items-center gap-6 bg-white border border-slate-200/60 p-6 rounded-3xl max-w-4xl mx-auto mb-16 shadow-sm">
            <span className="text-3xl bg-slate-50 w-12 h-12 flex items-center justify-center rounded-xl shadow-inner">💬</span>
            <div className="flex-1 text-center md:text-left">
              <strong className="text-slate-800 text-base block mb-0.5">{t('tg.plan.notice.title') || 'Aniq narx loyihaga qarab belgilanadi'}</strong>
              <p className="text-slate-500 text-sm leading-relaxed">{t('tg.plan.notice.desc') || 'Har bir loyiha individual bo\'lganligi uchun, siz bilan TZ tuzib aniq narxni hisoblab beramiz.'}</p>
            </div>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="whitespace-nowrap bg-slate-900 text-white font-bold text-sm px-6 py-3.5 rounded-xl hover:bg-slate-800 transition-colors">
              💬 {t('tg.plan.notice.btn') || 'Narxni bilish'}
            </a>
          </div>

          {/* Pricing Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch max-w-6xl mx-auto">
            {plans.map(plan => (
              <div 
                key={plan.name} 
                className={`relative flex flex-col bg-white border border-black/5 p-8 rounded-3xl transition-all duration-300 ${plan.border}`}
              >
                {plan.popular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-gradient-to-r from-red-500 to-amber-500 text-white font-black text-xs uppercase px-4 py-1 rounded-full tracking-wider shadow-md">
                    🔥 {t('tg.p2.b') || 'Tavsiya etiladi'}
                  </div>
                )}
                <div className="inline-block self-start text-xs font-bold text-slate-400 bg-slate-50 border border-slate-100 px-3 py-1 rounded-full mb-4">{plan.badge}</div>
                <div className={`text-2xl font-black mb-2 ${plan.color}`}>{plan.name}</div>
                <p className="text-slate-400 text-sm leading-relaxed mb-6">{plan.desc}</p>
                
                <div className={`border rounded-2xl p-4 text-center mb-8 ${plan.bg}`} style={{ borderColor: 'currentColor' }}>
                  <span className={`text-base font-black block mb-0.5 ${plan.color}`}>{plan.label}</span>
                  <span className="text-xs text-slate-400 font-medium">{plan.hint}</span>
                </div>

                <div className="flex flex-col gap-3 flex-1 mb-8">
                  {plan.features.map((f, i) => (
                    <div key={i} className="flex items-start gap-3 text-sm font-medium text-slate-700 leading-snug">
                      <span className={`mt-0.5 ${plan.color}`}><CheckIcon /></span> {f}
                    </div>
                  ))}
                </div>

                <button
                  className={`w-full font-bold text-sm py-4 rounded-xl border transition-all duration-300 ${plan.btn}`}
                  onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
                >
                  {t('tg.plan.notice.btn') || 'Bog\'lanish'} &rarr;
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 max-w-[1400px] mx-auto px-4 mb-12" id="sp-contact">
        <div className="bg-linear-to-br from-emerald-950 via-teal-900 to-slate-900 text-white rounded-[32px] p-8 md:p-16 text-center relative overflow-hidden shadow-xl">
          <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />
          
          <div className="relative z-10 max-w-2xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-4">
              {t('tg.cta.title') || 'Avtomatlashtirishni bugundanoq boshlang'}
            </h2>
            <p className="text-white/80 text-base md:text-lg mb-10 leading-relaxed">
              {t('tg.cta.desc') || 'Bizga o\'z g\'oyangizni yozing yoki qo\'ng\'iroq qiling. Biznesingiz uchun eng to\'g\'ri yechimni taklif qilamiz.'}
            </p>
            
            <div className="flex flex-wrap gap-4 justify-center">
              <a 
                href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" 
                className="inline-flex items-center gap-2 bg-white text-emerald-950 font-bold text-base px-8 py-4 rounded-xl transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
              >
                🤖 {t('tg.cta.btn1') || 'Telegramda bog\'lanish'} <ArrowRight />
              </a>
              <a 
                href="tel:+998889118171" 
                className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl transition-all duration-300 backdrop-blur-md hover:bg-white/20 hover:-translate-y-0.5"
              >
                📞 {t('tg.cta.btn2') || 'Qo\'ng\'iroq qilish'}
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}