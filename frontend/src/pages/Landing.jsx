import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import LandingLayout from '../components/LandingLayout'
import axios from 'axios'
import './landing.css'
import { useSeo } from '../hooks/useSeo'

// ─── SVG ICONS FOR BENTO ────────────────────────────────────────────────────
const ICONS = {
  pos: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
      <rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  ),
  warehouse: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
      <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  crm: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  ),
  finance: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
      <rect x="2" y="6" width="20" height="12" rx="2" /><circle cx="12" cy="12" r="2" /><path d="M6 12h.01M18 12h.01" />
    </svg>
  ),
  lang: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8">
      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-emerald-500 drop-shadow-[0_4px_6px_rgba(16,185,129,0.2)] transition-transform duration-300 group-hover:scale-125">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  arrowRight: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  )
}

// ─── DASHBOARD MOCKUP (MINIMAL ENTERPRISE) ───────────────────────────────────
function DashboardMinimal() {
  const { t } = useLang();

  return (
    <div className="bg-white/70 backdrop-blur-xl border border-white rounded-[20px] shadow-[0_25px_50px_-12px_rgba(0,0,0,0.15),0_0_0_1px_rgba(0,0,0,0.02)] overflow-hidden transform [transform:rotateY(-8deg)_rotateX(4deg)_translateZ(0)] transition-transform duration-600 ease-[cubic-bezier(0.2,0.8,0.2,1)] hover:[transform:rotateY(0)_rotateX(0)_translateZ(30px)] hover:shadow-[0_35px_60px_-10px_rgba(0,0,0,0.2),0_0_40px_rgba(37,99,235,0.1)]">
      <div className="p-4 border-b border-black/[0.08] flex items-center gap-4 bg-slate-50/60">
        <div className="flex gap-2">
          <span className="w-3 h-3 rounded-full bg-red-500" />
          <span className="w-3 h-3 rounded-full bg-amber-500" />
          <span className="w-3 h-3 rounded-full bg-emerald-500" />
        </div>
        <div className="bg-white border border-black/[0.08] rounded-lg px-4 py-1.5 text-xs text-slate-500 flex-1">🔍 Qidiruv...</div>
      </div>
      <div className="flex h-[360px]">
        <div className="w-[70px] border-r border-black/[0.08] p-4 flex flex-col gap-4 bg-white/40">
          <div className="h-7 rounded-lg bg-gradient-to-br from-blue-600 to-purple-500 shadow-[0_4px_10px_rgba(37,99,235,0.3)] transition-all duration-300 hover:scale-105" />
          <div className="h-7 rounded-lg bg-slate-100 transition-all duration-300 hover:scale-105" />
          <div className="h-7 rounded-lg bg-slate-100 transition-all duration-300 hover:scale-105" />
          <div className="h-7 rounded-lg bg-slate-100 transition-all duration-300 hover:scale-105" />
        </div>
        <div className="flex-1 p-6 flex flex-col gap-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white border border-black/[0.08] p-4 rounded-xl shadow-sm transition-transform duration-300 hover:-translate-y-1">
              <span className="block text-[11px] text-slate-500 uppercase font-bold tracking-[1px]">{t('dashboard.income')}</span>
              <span className="block text-[22px] font-black text-slate-900 mt-1.5">12.4M</span>
            </div>
            <div className="bg-white border border-black/[0.08] p-4 rounded-xl shadow-sm transition-transform duration-300 hover:-translate-y-1">
              <span className="block text-[11px] text-slate-500 uppercase font-bold tracking-[1px]">{t('sidebar.customers')}</span>
              <span className="block text-[22px] font-black text-slate-900 mt-1.5">342</span>
            </div>
            <div className="bg-white border border-black/[0.08] p-4 rounded-xl shadow-sm transition-transform duration-300 hover:-translate-y-1">
              <span className="block text-[11px] text-slate-500 uppercase font-bold tracking-[1px]">{t('purchase.order')}</span>
              <span className="block text-[22px] font-black text-slate-900 mt-1.5">1,890</span>
            </div>
          </div>
          <div className="flex-1 bg-white border border-black/[0.08] rounded-xl p-5 flex items-end gap-3">
            <div className="flex-1 bg-slate-200 rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[40%]" />
            <div className="flex-1 bg-slate-200 rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[70%]" />
            <div className="flex-1 bg-slate-200 rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[55%]" />
            <div className="flex-1 bg-slate-200 rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[90%]" />
            <div className="flex-1 bg-slate-200 rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[65%]" />
            <div className="flex-1 bg-gradient-to-t from-emerald-500 to-teal-400 shadow-[0_4px_15px_rgba(16,185,129,0.3)] rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[100%]" />
            <div className="flex-1 bg-slate-200 rounded-t-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] hover:bg-purple-500 hover:scale-y-110 origin-bottom h-[80%]" />
          </div>
        </div>
      </div>
    </div>
  )
}

const VisualWarehouse = () => (
  <div className="w-full h-full flex items-center justify-center p-5 animate-[floatBox_6s_ease-in-out_infinite_alternate]">
    <img src="/mockups/warehouse.png" alt="Warehouse UI" className="w-full max-w-[500px] rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] border border-black/[0.05] object-cover" />
  </div>
);

const VisualPOS = () => (
  <div className="w-full h-full flex items-center justify-center p-5 animate-[floatBox_6s_ease-in-out_infinite_alternate]">
    <img src="/mockups/pos.png" alt="POS UI" className="w-full max-w-[500px] rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] border border-black/[0.05] object-cover" />
  </div>
);

const VisualAudit = () => (
  <div className="w-full h-full flex items-center justify-center p-5 animate-[floatBox_6s_ease-in-out_infinite_alternate]">
    <img src="/mockups/audit.png" alt="Audit UI" className="w-full max-w-[500px] rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] border border-black/[0.05] object-cover" />
  </div>
);

// ─── TABBED MODULE (HOW IT WORKS) ───────────────────────────────────────────
function TabbedModules({ t }) {
  const [activeTab, setActiveTab] = useState(0)

  const tabs = [
    {
      title: t('land.tab1.title') || "Tovarlar va Nomenklatura",
      desc: t('land.tab1.desc') || "Minglab tovar pozitsiyalarini shtrix-kod kataloglari orqali yagona bazaga birlashtiring...",
      visual: <VisualWarehouse />
    },
    {
      title: t('land.tab2.title') || "Sotuv va Tranzaksiyalar",
      desc: t('land.tab2.desc') || "B2B uchun shartnomaviy sotuv...",
      visual: <VisualPOS />
    },
    {
      title: t('land.tab3.title') || "Audit va Xavfsizlik",
      desc: t('land.tab3.desc') || "Xodimlarning barcha harakatlari va tranzaksiya o'zgarishlari tizim loglariga muhrlanadi...",
      visual: <VisualAudit />
    }
  ]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr] gap-10 bg-white/80 backdrop-blur-2xl border border-white rounded-3xl p-10 shadow-[0_20px_50px_rgba(0,0,0,0.05)]">
      <div className="flex flex-col gap-4">
        {tabs.map((tab, idx) => (
          <button 
            key={idx} 
            className={`text-left bg-white border p-6 rounded-[20px] cursor-pointer transition-all duration-300 shadow-sm group ${
              activeTab === idx 
                ? 'border-blue-600/30 shadow-[0_10px_30px_rgba(37,99,235,0.1),inset_3px_0_0_#2563eb] translate-x-2' 
                : 'border-black/[0.08] hover:bg-slate-50 hover:translate-x-1'
            }`}
            onClick={() => setActiveTab(idx)}
          >
            <h3 className={`m-0 mb-2 text-[20px] font-bold transition-colors duration-300 ${activeTab === idx ? 'text-blue-600' : 'text-slate-500'}`}>{tab.title}</h3>
            <p className={`m-0 text-[15px] text-slate-500 leading-[1.6] ${activeTab === idx ? 'block animate-[fadeDown_0.4s_ease]' : 'hidden'}`}>{tab.desc}</p>
          </button>
        ))}
      </div>
      <div className="bg-slate-50 rounded-[20px] border border-black/[0.08] flex items-center justify-center relative overflow-hidden min-h-[380px] shadow-[inset_0_4px_20px_rgba(0,0,0,0.02)]">
        <div className="w-full h-full animate-[fadeInUp_0.5s_cubic-bezier(0.2,0.8,0.2,1)]" key={activeTab}>
           {tabs[activeTab].visual}
        </div>
      </div>
    </div>
  )
}

// ─── MAIN COMPONENT ─────────────────────────────────────────────────────────
export default function Landing() {
  const { t } = useLang()
  const navigate = useNavigate()
  useSeo(
    "E-code – ERP, POS, Veb Sayt va Telegram Bot Yechimlari | O'zbekiston",
    "E-code — O'zbekiston uchun ERP tizimi, POS kassa, veb sayt yaratish, Telegram botlar va noyob dasturiy yechimlar. Biznesingizni raqamlashtiring."
  )

  const [leadForm, setLeadForm] = useState({ service: 'ERP Tizim', name: '', phone: '+998' })
  const [leadStatus, setLeadStatus] = useState(null) // 'loading', 'success', 'error'

  const handleLeadSubmit = async (e) => {
    e.preventDefault()
    setLeadStatus('loading')
    try {
      await axios.post('/api/leads', leadForm)
      setLeadStatus('success')
    } catch (err) {
      setLeadStatus('success')
    }
  }

  return (
    <LandingLayout>
      {/* ── Hero ── */}
      <header className="relative pt-[100px] pb-[120px] border-b border-black/[0.02]">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,0,0,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.03)_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_80%)] z-0" />
        <div className="max-w-[1200px] mx-auto px-6 relative z-10 grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-[60px] items-center text-center lg:text-left">
          <div className="flex flex-col items-center lg:items-start">
            <div className="animate-[slideUp_0.8s_ease-out_0.1s_backwards] inline-block px-4 py-1.5 bg-blue-600/10 border border-blue-600/20 rounded-full text-[13px] font-bold text-blue-600 mb-6">
              {t('land.b2b')}
            </div>
            <h1 className="animate-[slideUp_0.8s_ease-out_0.2s_backwards] text-[clamp(32px,9vw,48px)] lg:text-[clamp(48px,6vw,68px)] font-black leading-[1.05] tracking-[-0.04em] m-0 mb-6 text-slate-900">
              {t('land.erp')} <br/>
              <span className="bg-gradient-to-br from-emerald-600 to-blue-600 bg-clip-text text-transparent inline-block animate-[bgPan_4s_linear_infinite_alternate]">
                {t('land.eco')}
              </span>
            </h1>
            <p className="animate-[slideUp_0.8s_ease-out_0.3s_backwards] text-[19px] text-slate-500 leading-[1.6] m-0 mb-10 max-w-[520px]">
              {t('land.desc1')}
            </p>
            <div className="animate-[slideUp_0.8s_ease-out_0.4s_backwards] flex flex-col lg:flex-row gap-4 mb-10 w-full lg:w-auto lg:justify-start justify-center">
              <button 
                className="inline-flex items-center justify-center gap-2 bg-gradient-to-br from-blue-600 to-blue-500 text-white border-none font-bold px-8 py-4 text-[16px] rounded-2xl cursor-pointer transition-all duration-[400ms] ease-[cubic-bezier(0.175,0.885,0.32,1.275)] shadow-[0_10px_30px_rgba(37,99,235,0.15)] relative overflow-hidden group hover:-translate-y-[3px] hover:scale-[1.02] hover:shadow-[0_15px_30px_rgba(37,99,235,0.3)] w-full lg:w-auto"
                onClick={() => {
                  const leadSection = document.getElementById('lead-form');
                  if(leadSection) leadSection.scrollIntoView({behavior: 'smooth'});
                }}
              >
                {t('land.hero.req_quote') || 'So\'rov qoldirish'} <span className="transition-transform duration-300 group-hover:translate-x-1">{ICONS.arrowRight}</span>
              </button>
            </div>
            
            <div className="animate-[slideUp_0.8s_ease-out_0.5s_backwards] text-[14px] border-t border-black/[0.08] pt-6 pb-2.5 max-w-[480px]">
              <div className="flex gap-[20px] flex-wrap font-semibold text-blue-600 flex-col lg:flex-row items-center lg:items-start">
                <span className="flex items-center gap-1.5">{t('land.sec1')}</span>
                <span className="flex items-center gap-1.5">{t('land.sec2')}</span>
                <span className="flex items-center gap-1.5">{t('land.sec3')}</span>
              </div>
            </div>
          </div>
          
          <div className="hidden lg:block perspective-[1200px] animate-[slideUp_1s_ease-out_0.2s_backwards]">
            <DashboardMinimal />
          </div>
        </div>
      </header>

      {/* ── Features Bento Grid ── */}
      <section id="features" className="py-[120px] relative">
        <div className="max-w-[1200px] mx-auto px-6 relative z-10">
          <div className="text-center mb-[70px] animate-[fadeInUp_0.8s_ease-out_both]">
            <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-slate-900">{t('land.ecosystem')}</h2>
            <p className="text-[18px] text-slate-500 max-w-[600px] mx-auto">{t('land.arch')}</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 auto-rows-[minmax(280px,auto)] gap-6">
            
            {/* Box 1 - Hero Bento → ERP Tizim */}
            <div
              className="group cursor-pointer lg:col-span-2 bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] animate-[slideUp_0.8s_backwards_0.1s] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)]"
              onClick={() => navigate('/erp-tizim')}
              title="ERP Tizim haqida batafsil"
            >
              <div className="relative z-10 flex flex-col h-full transition-transform duration-300 group-hover:-translate-y-1">
                <div className="w-14 h-14 bg-white border border-black/[0.08] rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">
                  {ICONS.pos}
                </div>
                <h3 className="m-0 mb-4 text-[24px] font-extrabold tracking-[-0.02em] text-slate-900">{t('land.omni')}</h3>
                <p className="m-0 text-slate-500 leading-[1.7] text-[16px]">{t('land.omniDesc')}</p>
                <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-blue-600 mt-5 opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0">{t('land.chaqqon.box_more') || 'Batafsil ko\'rish'} {ICONS.arrowRight}</span>
              </div>
              <div className="absolute -right-[30px] -bottom-[30px] w-[65%] h-[110%] z-[1] opacity-30 transition-opacity duration-[800ms] group-hover:opacity-60" style={{backgroundImage:"url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100' opacity='0.1'%3E%3Crect x='10' y='10' width='80' height='80' rx='12' stroke='%232563eb' stroke-width='3' fill='none'/%3E%3C/svg%3E\")", backgroundRepeat:"repeat"}} />
            </div>

            {/* Box 2 → ERP Tizim (Analitika) */}
            <div
              className="group cursor-pointer bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] animate-[slideUp_0.8s_backwards_0.2s] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)]"
              onClick={() => navigate('/erp-tizim')}
              title="Analitika va hisobotlar"
            >
              <div className="relative z-10 flex flex-col h-full transition-transform duration-300 group-hover:-translate-y-1">
                <div className="w-14 h-14 bg-white border border-black/[0.08] rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">{ICONS.chart}</div>
                <h3 className="m-0 mb-4 text-[24px] font-extrabold tracking-[-0.02em] text-slate-900">{t('land.bi')}</h3>
                <p className="m-0 text-slate-500 leading-[1.7] text-[16px]">{t('land.biDesc')}</p>
                <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-blue-600 mt-5 opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0">{t('land.chaqqon.box_more') || 'Batafsil'} {ICONS.arrowRight}</span>
              </div>
            </div>

            {/* Box 3 → ERP Tizim (CRM) */}
            <div
              className="group cursor-pointer bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] animate-[slideUp_0.8s_backwards_0.3s] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)]"
              onClick={() => navigate('/erp-tizim')}
              title="CRM — Mijozlar boshqaruvi"
            >
              <div className="relative z-10 flex flex-col h-full transition-transform duration-300 group-hover:-translate-y-1">
                <div className="w-14 h-14 bg-white border border-black/[0.08] rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">{ICONS.crm}</div>
                <h3 className="m-0 mb-4 text-[24px] font-extrabold tracking-[-0.02em] text-slate-900">{t('land.crm')}</h3>
                <p className="m-0 text-slate-500 leading-[1.7] text-[16px]">{t('land.crmDesc')}</p>
                <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-blue-600 mt-5 opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0">{t('land.chaqqon.box_more') || 'Batafsil'} {ICONS.arrowRight}</span>
              </div>
            </div>

            {/* Box 4 - Wide Bento → ERP Tizim (Ombor) */}
            <div
              className="group cursor-pointer lg:col-span-2 bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] animate-[slideUp_0.8s_backwards_0.4s] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)]"
              onClick={() => navigate('/erp-tizim')}
              title="Ombor boshqaruvi — WMS"
            >
              <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-[30px] lg:gap-[40px] h-full transition-transform duration-300 group-hover:-translate-y-1">
                <div>
                  <div className="w-14 h-14 bg-white border border-black/[0.08] rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">{ICONS.warehouse}</div>
                  <h3 className="m-0 mb-4 text-[24px] font-extrabold tracking-[-0.02em] text-slate-900">{t('land.wms')}</h3>
                  <p className="m-0 text-slate-500 leading-[1.7] text-[16px]">{t('land.wmsDesc')}</p>
                  <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-blue-600 mt-4 opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0">{t('land.chaqqon.box_more') || 'Batafsil ko\'rish'} {ICONS.arrowRight}</span>
                </div>
                <ul className="list-none p-0 m-0 flex flex-col gap-4 bg-white p-8 rounded-[20px] border border-black/[0.08] min-w-0 lg:min-w-[300px] w-full lg:w-auto shadow-sm transform translate-z-0 transition-all duration-300 group-hover:scale-[1.02] group-hover:shadow-md">
                  <li className="flex items-center gap-3 text-[15px] font-semibold text-slate-900 group/item">{ICONS.check} {t('land.check1')}</li>
                  <li className="flex items-center gap-3 text-[15px] font-semibold text-slate-900 group/item">{ICONS.check} {t('land.check2')}</li>
                  <li className="flex items-center gap-3 text-[15px] font-semibold text-slate-900 group/item">{ICONS.check} {t('land.check3')}</li>
                </ul>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ── Modullar / How it works ── */}
      <section id="modules" className="py-[120px] relative bg-gradient-to-b from-slate-100 to-white border-y border-black/[0.08]">
        <div className="max-w-[1200px] mx-auto px-6 relative z-10">
          <div className="text-center mb-[70px] animate-[fadeInUp_0.8s_ease-out_both]">
            <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-slate-900">{t('land.singleDb')}</h2>
            <p className="text-[18px] text-slate-500 max-w-[600px] mx-auto">{t('land.noPaper')}</p>
          </div>
          <TabbedModules t={t} />
        </div>
      </section>

      {/* ── Chaqqon Pro ── */}
      <section className="py-[120px] relative bg-gradient-to-br from-amber-50 to-orange-100 border-y border-orange-200">
        <div className="max-w-[1200px] mx-auto px-6 relative z-10">
          <div className="text-center mb-[70px] animate-[fadeInUp_0.8s_ease-out_both]">
            <div className="text-orange-600 bg-orange-600/10 inline-block px-3 py-1 rounded-xl font-bold mb-4">🍽️ {t('land.chaqqon.badge') || 'Yangi tizim'}</div>
            <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-orange-900">{t('land.chaqqon.title') || 'Chaqqon Pro'}</h2>
            <p className="text-[18px] text-orange-700 max-w-[600px] mx-auto">{t('land.chaqqon.sub') || 'Restoran POS'}</p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 auto-rows-[minmax(280px,auto)] gap-6">
            <div
              className="group cursor-pointer lg:col-span-2 bg-white border border-orange-300 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_25px_-5px_rgba(234,88,12,0.1)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(234,88,12,0.1)]"
              onClick={() => navigate('/chaqqon-pro')}
            >
              <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-[30px] lg:gap-[40px] h-full transition-transform duration-300 group-hover:-translate-y-1">
                <div>
                  <div className="w-14 h-14 bg-orange-100 text-orange-600 text-2xl border border-orange-200 rounded-2xl flex items-center justify-center mb-6 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-orange-500 group-hover:text-white group-hover:shadow-[0_10px_20px_rgba(234,88,12,0.3)]">🍔</div>
                  <h3 className="m-0 mt-4 mb-2 text-[24px] font-extrabold tracking-[-0.02em] text-orange-900">{t('land.chaqqon.box_title') || 'Maxsus Restoran POS'}</h3>
                  <p className="m-0 mt-2 text-amber-900 leading-[1.7] text-[16px]">{t('land.chaqqon.box_desc') || 'Kassalar, ofitsiantlar va h.k'}</p>
                  <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-orange-600 mt-4 opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0">{t('land.chaqqon.box_more') || 'Batafsil'} {ICONS.arrowRight}</span>
                </div>
                <ul className="list-none p-0 m-0 flex flex-col gap-4 bg-orange-50/50 p-8 rounded-[20px] border border-orange-200 min-w-0 lg:min-w-[300px] w-full lg:w-auto shadow-sm transform translate-z-0 transition-all duration-300 text-orange-900 group-hover:scale-[1.02] group-hover:shadow-md">
                  <li className="flex items-center gap-3 text-[15px] font-semibold group/item">{ICONS.check} {t('land.chaqqon.l1')}</li>
                  <li className="flex items-center gap-3 text-[15px] font-semibold group/item">{ICONS.check} {t('land.chaqqon.l2')}</li>
                  <li className="flex items-center gap-3 text-[15px] font-semibold group/item">{ICONS.check} {t('land.chaqqon.l3')}</li>
                  <li className="flex items-center gap-3 text-[15px] font-semibold group/item">{ICONS.check} {t('land.chaqqon.l4')}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Boshqa Xizmatlar / IT Agency ── */}
      <section className="py-[120px] relative bg-slate-50 border-t border-slate-200">
        <div className="max-w-[1200px] mx-auto px-6 relative z-10">
          <div className="text-center mb-[70px] animate-[fadeInUp_0.8s_ease-out_both]">
            <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-slate-900">{t('land.agency.title') || 'Biz bilan faqat ERP emas...'}</h2>
            <p className="text-[18px] text-slate-500 max-w-[600px] mx-auto">{t('land.agency.sub')}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">

            {/* Veb-saytlar */}
            <div
              className="group cursor-pointer bg-white text-slate-900 border border-slate-200 rounded-2xl p-7 shadow-[0_4px_6px_rgba(0,0,0,0.02)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_24px_rgba(0,0,0,0.08)] hover:border-blue-600"
              onClick={() => navigate('/veb-saytlar')}
            >
              <div className="flex flex-col h-full relative z-10">
                <div className="text-[2.5rem] mb-4">🌐</div>
                <h3 className="text-[1.3rem] font-bold mb-2.5">{t('land.agency.w_title')}</h3>
                <p className="text-slate-600 text-[1rem] leading-[1.5]">{t('land.agency.w_desc')}</p>
                <span className="inline-block text-[14px] font-bold text-blue-600 mt-3.5 opacity-0 translate-y-1.5 transition-all duration-300 group-hover:opacity-100 group-hover:translate-y-0">{t('land.chaqqon.box_more')} →</span>
              </div>
            </div>

            {/* Telegram Botlar */}
            <div
              className="group cursor-pointer bg-white text-slate-900 border border-slate-200 rounded-2xl p-7 shadow-[0_4px_6px_rgba(0,0,0,0.02)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_24px_rgba(0,0,0,0.08)] hover:border-blue-600"
              onClick={() => navigate('/telegram-botlar')}
            >
              <div className="flex flex-col h-full relative z-10">
                <div className="text-[2.5rem] mb-4">🤖</div>
                <h3 className="text-[1.3rem] font-bold mb-2.5">{t('land.agency.b_title')}</h3>
                <p className="text-slate-600 text-[1rem] leading-[1.5]">{t('land.agency.b_desc')}</p>
                <span className="inline-block text-[14px] font-bold text-blue-600 mt-3.5 opacity-0 translate-y-1.5 transition-all duration-300 group-hover:opacity-100 group-hover:translate-y-0">{t('land.chaqqon.box_more')} →</span>
              </div>
            </div>

            {/* Noyob Dasturlar */}
            <div
              className="group cursor-pointer bg-white text-slate-900 border border-slate-200 rounded-2xl p-7 shadow-[0_4px_6px_rgba(0,0,0,0.02)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_24px_rgba(0,0,0,0.08)] hover:border-blue-600"
              onClick={() => navigate('/noyob-dasturlar')}
            >
              <div className="flex flex-col h-full relative z-10">
                <div className="text-[2.5rem] mb-4">💻</div>
                <h3 className="text-[1.3rem] font-bold mb-2.5">{t('land.agency.s_title')}</h3>
                <p className="text-slate-600 text-[1rem] leading-[1.5]">{t('land.agency.s_desc')}</p>
                <span className="inline-block text-[14px] font-bold text-blue-600 mt-3.5 opacity-0 translate-y-1.5 transition-all duration-300 group-hover:opacity-100 group-hover:translate-y-0">{t('land.chaqqon.box_more')} →</span>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ── Lead Capture / So'rov Qoldirish ── */}
      <section id="lead-form" className="py-[140px] bg-blue-600 relative overflow-hidden">
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;utf8,<svg_xmlns=\"http://www.w3.org/2000/svg\"_width=\"60\"_height=\"60\"_opacity=\"0.1\"><circle_cx=\"2\"_cy=\"2\"_r=\"2\"_fill=\"%23fff\"/></svg>')] bg-repeat animate-[slideUp_20s_linear_infinite] opacity-40 z-0" />
        <div className="max-w-[1200px] mx-auto px-6 relative z-10">
          <div className="bg-white/10 text-white backdrop-blur-[20px] border border-white/20 rounded-[24px] shadow-[0_30px_60px_rgba(0,0,0,0.2)] relative z-[1] grid grid-cols-1 lg:grid-cols-2 gap-10 text-center lg:text-left p-[30px] lg:p-[60px]">
            <div className="flex flex-col">
              <h2 className="text-[2rem] lg:text-[2.5rem] mb-5 text-white tracking-[-0.02em] font-black">{t('land.lead.title')}</h2>
              <p className="text-white/80 text-[1.2rem] mb-[30px] leading-[1.6] max-w-[640px] lg:mx-0 mx-auto">{t('land.lead.sub')}</p>
              <ul className="list-none p-0 text-white/90 flex flex-col gap-4 items-center lg:items-start">
                <li className="flex items-center gap-3 text-[1.1rem]">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 shrink-0 text-emerald-400">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  {t('land.lead.l1')}
                </li>
                <li className="flex items-center gap-3 text-[1.1rem]">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 shrink-0 text-emerald-400">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  {t('land.lead.l2')}
                </li>
                <li className="flex items-center gap-3 text-[1.1rem]">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 shrink-0 text-emerald-400">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  {t('land.lead.l3')}
                </li>
              </ul>
            </div>

            <div className="bg-white rounded-2xl p-[30px] text-slate-900 self-center h-fit w-full">
              {leadStatus === 'success' ? (
                <div className="text-center py-10">
                  <div className="text-[4rem] text-emerald-500 mb-5">✓</div>
                  <h3 className="text-[1.5rem] mb-2.5 font-bold">{t('land.form.success')}</h3>
                  <p className="text-slate-600 mb-5">{t('land.form.successDesc')}</p>
                  <button className="inline-flex items-center justify-center gap-2 bg-white/80 text-slate-900 border border-black/[0.08] font-semibold px-6 py-3 rounded-xl cursor-pointer transition-all duration-300 backdrop-blur-[10px] hover:bg-white hover:border-black/15 hover:-translate-y-0.5 hover:shadow-sm" onClick={() => setLeadStatus(null)}>{t('land.form.newReq')}</button>
                </div>
              ) : (
                <form onSubmit={handleLeadSubmit} className="flex flex-col gap-[15px] text-left">
                  <h3 className="text-[1.4rem] mb-2.5 font-bold m-0">{t('land.form.title')}</h3>
                  
                  <div className="flex flex-col">
                    <label className="text-[0.9rem] text-slate-600 mb-[5px] block">{t('land.form.service')}</label>
                    <select 
                      value={leadForm.service} 
                      onChange={e => setLeadForm({...leadForm, service: e.target.value})}
                      className="w-full p-3 rounded-lg border border-slate-200 text-[1rem] bg-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                    >
                      <option>ERP Tizim</option>
                      <option>Chaqqon Pro (Restoran POS)</option>
                      <option>Veb-sayt yasash</option>
                      <option>Telegram Bot</option>
                      <option>Boshqa g'oya</option>
                    </select>
                  </div>

                  <div className="flex flex-col">
                    <label className="text-[0.9rem] text-slate-600 mb-[5px] block">{t('land.form.name')}</label>
                    <input 
                      type="text" 
                      required 
                      value={leadForm.name}
                      onChange={e => setLeadForm({...leadForm, name: e.target.value})}
                      placeholder="Alisher"
                      className="w-full p-3 rounded-lg border border-slate-200 text-[1rem] bg-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                    />
                  </div>

                  <div className="flex flex-col">
                    <label className="text-[0.9rem] text-slate-600 mb-[5px] block">{t('land.form.phone')}</label>
                    <input 
                      type="text" 
                      required 
                      value={leadForm.phone}
                      onChange={e => setLeadForm({...leadForm, phone: e.target.value})}
                      placeholder="+998"
                      className="w-full p-3 rounded-lg border border-slate-200 text-[1rem] bg-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                    />
                  </div>

                  <button 
                    type="submit" 
                    disabled={leadStatus === 'loading'}
                    className="bg-blue-600 text-white p-[14px] rounded-lg text-[1.1rem] font-semibold border-none cursor-pointer mt-2.5 transition-colors hover:bg-blue-700 disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    {leadStatus === 'loading' ? t('land.form.loading') : t('land.form.submit')}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
