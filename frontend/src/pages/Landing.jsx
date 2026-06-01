import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import LandingLayout from '../components/LandingLayout'
import { ShieldCheck, Zap, Cloud, Globe, Bot, Laptop, BadgeCheck, ArrowBigDown, ChevronDown, LaptopMinimal, Warehouse, Users, BadgeDollarSign, ChartNoAxesCombined, Handshake, CheckIcon, ArrowRight, Lamp, ChevronsUpDownIcon, ListChevronsUpDownIcon, ChefHat, Monitor, Globe2, HelpCircle, ChevronsUpDown, GlobeIcon, Send, MailCheck } from 'lucide-react'
import axios from 'axios'
import { useSeo } from '../hooks/useSeo'
import { Label, Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'

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
      <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
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
  ),
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
  <div className="w-max h-full flex items-center justify-center animate-[floatBox_6s_ease-in-out_infinite_alternate]">
    <img src="/mockups/warehouse.png" alt="Warehouse UI" className="w-full max-w-[600px] rounded-2xl border border-blue-200 object-cover" />
  </div>
);

const VisualPOS = () => (
  <div className="w-max h-full flex items-center justify-center animate-[floatBox_6s_ease-in-out_infinite_alternate]">
    <img src="/mockups/pos.png" alt="POS UI" className="w-full max-w-[600px] rounded-2xl border border-blue-200 object-cover" />
  </div>
);

const VisualAudit = () => (
  <div className="w-max h-full flex items-center justify-center animate-[floatBox_6s_ease-in-out_infinite_alternate]">
    <img src="/mockups/audit.png" alt="Audit UI" className="w-full max-w-[600px] rounded-2xl border border-blue-200 object-cover" />
  </div>
);

// ─── TABBED MODULE (HOW IT WORKS) ───────────────────────────────────────────
function TabbedModules({ t }) {
  const [activeTab, setActiveTab] = useState(0)

  const oneDbIcons = [
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill={activeTab === 0 ? "#0000FF" : "#808080"} viewBox="0 0 256 256"><path d="M232,48V88a8,8,0,0,1-16,0V56H184a8,8,0,0,1,0-16h40A8,8,0,0,1,232,48ZM72,200H40V168a8,8,0,0,0-16,0v40a8,8,0,0,0,8,8H72a8,8,0,0,0,0-16Zm152-40a8,8,0,0,0-8,8v32H184a8,8,0,0,0,0,16h40a8,8,0,0,0,8-8V168A8,8,0,0,0,224,160ZM32,96a8,8,0,0,0,8-8V56H72a8,8,0,0,0,0-16H32a8,8,0,0,0-8,8V88A8,8,0,0,0,32,96ZM80,80a8,8,0,0,0-8,8v80a8,8,0,0,0,16,0V88A8,8,0,0,0,80,80Zm104,88V88a8,8,0,0,0-16,0v80a8,8,0,0,0,16,0ZM144,80a8,8,0,0,0-8,8v80a8,8,0,0,0,16,0V88A8,8,0,0,0,144,80Zm-32,0a8,8,0,0,0-8,8v80a8,8,0,0,0,16,0V88A8,8,0,0,0,112,80Z"></path></svg>
    ,
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill={activeTab === 1 ? "#0000FF" : "#808080"} viewBox="0 0 256 256"><path d="M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40Zm0,160H40V56H216V200ZM176,88a48,48,0,0,1-96,0,8,8,0,0,1,16,0,32,32,0,0,0,64,0,8,8,0,0,1,16,0Z"></path></svg>
    ,
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill={activeTab === 2 ? "#0000FF" : "#808080"} viewBox="0 0 256 256"><path d="M208,40H48A16,16,0,0,0,32,56v56c0,52.72,25.52,84.67,46.93,102.19,23.06,18.86,46,25.26,47,25.53a8,8,0,0,0,4.2,0c1-.27,23.91-6.67,47-25.53C198.48,196.67,224,164.72,224,112V56A16,16,0,0,0,208,40Zm0,72c0,37.07-13.66,67.16-40.6,89.42A129.3,129.3,0,0,1,128,223.62a128.25,128.25,0,0,1-38.92-21.81C61.82,179.51,48,149.3,48,112l0-56,160,0ZM82.34,141.66a8,8,0,0,1,11.32-11.32L112,148.69l50.34-50.35a8,8,0,0,1,11.32,11.32l-56,56a8,8,0,0,1-11.32,0Z"></path></svg>
    ,
  ]

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
    <div className="flex gap-10 bg-white/80 backdrop-blur-2xl border border-white rounded-3xl p-10 shadow-[0_20px_50px_rgba(0,0,0,0.05)]">
      <div className="flex flex-col gap-4">
        {tabs.map((tab, idx) => (
          <button
            key={idx}
            className={`text-left w-full bg-white overflow-hidden border p-6 rounded-[20px] cursor-pointer transition-all duration-300 shadow-sm group ${activeTab === idx
              ? 'border-blue-600/30 h-40 shadow-[0_10px_30px_rgba(37,99,235,0.1),inset_3px_0_0_#2563eb]'
              : 'border-black/8 h-20 hover:bg-slate-50'
              }`}
            onClick={() => { setActiveTab(idx) }}
          >
            <div className='flex justify-between items-center'>
              <h3 className={`m-0 mb-2 text-[20px] font-bold flex items-center gap-2 transition-all duration-300 ${activeTab === idx ? 'text-blue-600' : 'text-slate-500'}`}>
                {oneDbIcons[idx]}
                {tab.title}
              </h3>

              <ChevronDown className={`-translate-y-0.75 transition-all duration-300 ease-in-out ${activeTab === idx ? 'rotate-180 text-blue-600' : 'rotate-0 text-slate-500'}`} />
            </div>
            <p className={`m-0 text-[15px] transition-all duration-300 leading-[1.6] ${activeTab === idx ? 'text-slate-500' : 'text-white'}`}>{tab.desc}</p>
          </button>
        ))}
      </div>
      <div className="flex w-full justify-end overflow-hidden">
        <div className="animate-[fadeInUp_0.5s_cubic-bezier(0.2,0.8,0.2,1)]" key={activeTab}>
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

  const getServiceIcon = (serviceName) => {
    switch (serviceName) {
      case 'ERP Tizim':
        return LaptopMinimal;
      case 'Chaqqon Pro (Restoran POS)':
        return ChefHat;
      case 'Web sayt yasash':
        return GlobeIcon;
      case 'Telegram Bot':
        return Bot;
      case "Boshqa g'oya":
        return Lamp;
      default:
        return HelpCircle; // Agar topilmasa, standart belgi
    }
  }

  // Sizdagi oddiy massiv (faqat string nomlar bilan)
  const serviceOptions = [
    'ERP Tizim',
    'Chaqqon Pro (Restoran POS)',
    'Web sayt yasash',
    'Telegram Bot',
    "Boshqa g'oya"
  ]

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

  const [activeModule, setActiveModule] = useState(0)

  const modules = [
    {
      id: 'pos',
      icon: <LaptopMinimal size={25} />,
      colorClass: 'text-[#2563eb]',
      bgClass: 'bg-[#2563eb]/10',
      borderClass: 'border-[#2563eb]',
      btnBg: 'from-[#2563eb] to-[#2563eb]/80',
      title: t('erp.m1.t') || 'POS Kassa',
      subtitle: t('erp.m1.s') || 'Tezkor sotuv terminali',
      desc: t('erp.m1.d') || 'Bir nechta kassa punktlarini yagona tizimga ulang. Shtrix-kod, skanerlash, naqd va bank kartasi to\'lovlari.',
      features: [
        t('erp.m1.f1') || 'Tezkor mahsulot qidirish va skanerlash',
        t('erp.m1.f2') || 'Naqd, karta, nasiya to\'lov usullari',
        t('erp.m1.f3') || 'Bir vaqtda bir nechta kassa',
        t('erp.m1.f4') || 'Smena ochish/yopish hisobotlari',
        t('erp.m1.f5') || 'Chek chiqarish (termal printer)',
        t('erp.m1.f6') || 'Qaytarish (return) boshqaruvi',
      ],
      stats: [{ val: t('erp.stats.2son.val') || '< 2 son', label: t('erp.stats.sotuvqay.label') || 'Sotuv qayta ishlash' }, { val: t('erp.stats.item.val') || '∞', label: t('erp.stats.mahsulot.label') || 'Mahsulot soni' }, { val: t('erp.stats.999.val') || '99.9%', label: t('erp.hero.stat3.lbl') || 'Uptime kafolat' }]
    },
    {
      id: 'ombor',
      icon: <Warehouse size={25} />,
      colorClass: 'text-[#10b981]',
      bgClass: 'bg-[#10b981]/10',
      borderClass: 'border-[#10b981]',
      btnBg: 'from-[#10b981] to-[#10b981]/80',
      title: t('erp.m2.t') || 'Ombor Boshqaruvi',
      subtitle: t('erp.m2.s') || 'WMS — Warehouse Management System',
      desc: t('erp.m2.d') || 'Real-vaqtda tovar harakatini kuzating. Kirim, chiqim, ko\'chirish va inventarizatsiya to\'liq avtomatlashtirilgan.',
      features: [
        t('erp.m2.f1') || 'Tovar kirim/chiqim/ko\'chirish',
        t('erp.m2.f2') || 'Bir nechta omborxona boshqaruvi',
        t('erp.m2.f3') || 'FIFO / LIFO hisobi',
        t('erp.m2.f4') || 'Minimal qoldiq ogohlantirish',
        t('erp.m2.f5') || 'Shtrix-kod va QR kod yetkazib berish',
        t('erp.m2.f6') || 'Inventarizatsiya (reviziya)',
      ],
      stats: [{ val: t('erp.stats.10.val') || '10+', label: t('erp.stats.omborxon.label') || 'Omborxona parallel' }, { val: t('erp.stats.fifo.val') || 'FIFO', label: t('erp.stats.hisobmet.label') || 'Hisob metodi' }, { val: t('erp.stats.realvaqt.val') || 'Real-vaqt', label: t('erp.stats.qoldiqku.label') || 'Qoldiq kuzatuvi' }]
    },
    {
      id: 'crm',
      icon: <Users size={25} />,
      colorClass: 'text-[#8b5cf6]',
      bgClass: 'bg-[#8b5cf6]/10',
      borderClass: 'border-[#8b5cf6]',
      btnBg: 'from-[#8b5cf6] to-[#8b5cf6]/80',
      title: t('erp.m3.t') || 'CRM — Mijozlar',
      subtitle: t('erp.m3.s') || 'Mijozlar munosabatlari boshqaruvi',
      desc: t('erp.m3.d') || 'Har bir mijozning sotib olish tarixi, qarzi, shartnomalari va muloqotlarini bir joyda saqlang.',
      features: [
        t('erp.m3.f1') || 'Mijoz profili va kontakt ma\'lumotlari',
        t('erp.m3.f2') || 'Qarzdorlik va nasiya hisobi',
        t('erp.m3.f3') || 'Sotuv tarixi va statistika',
        t('erp.m3.f4') || 'B2B: Shartnomaviy sotuv',
        t('erp.m3.f5') || 'Telegram xabarnoma yuborish',
        t('erp.m3.f6') || 'Mijoz segmentatsiyasi',
      ],
      stats: [{ val: t('erp.stats.100k.val') || '100K+', label: t('erp.stats.mijozbaz.label') || 'Mijoz bazasi' }, { val: t('erp.stats.b2bb2c.val') || 'B2B+B2C', label: t('erp.stats.sotuvmod.label') || 'Sotuv modeli' }, { val: t('erp.stats.telegram.val') || 'Telegram', label: t('erp.stats.xabarnom.label') || 'Xabarnoma kanal' }]
    },
    {
      id: 'moliya',
      icon: <BadgeDollarSign size={25} />,
      colorClass: 'text-[#f59e0b]',
      bgClass: 'bg-[#f59e0b]/10',
      borderClass: 'border-[#f59e0b]',
      btnBg: 'from-[#f59e0b] to-[#f59e0b]/80',
      title: t('erp.m4.t') || 'Moliya va Kassa',
      subtitle: t('erp.m4.s') || 'To\'liq moliyaviy nazorat',
      desc: t('erp.m4.d') || 'Har kungi kassa harakati, xarajatlar, daromadlar va foyda/zarar hisobotini real-vaqtda kuzating.',
      features: [
        t('erp.m4.f1') || 'Kassa kirim/chiqim operatsiyalari',
        t('erp.m4.f2') || 'Xarajatlar kategoriyasi',
        t('erp.m4.f3') || 'Foyda/zarar P&L hisoboti',
        t('erp.m4.f4') || 'Valyuta konvertatsiyasi',
        t('erp.m4.f5') || 'Bank hisobvaraqlari integratsiyasi',
        t('erp.m4.f6') || 'Soliq hisobot eksport',
      ],
      stats: [{ val: t('erp.stats.pl.val') || 'P&L', label: t('erp.stats.foydazar.label') || 'Foyda/zarar' }, { val: t('erp.stats.3.val') || '3+', label: t('erp.stats.valyutaq.label') || 'Valyuta qo\'llab quvvatlash' }, { val: t('erp.stats.excel.val') || 'Excel', label: t('erp.stats.eksportf.label') || 'Eksport format' }]
    },
    {
      id: 'hisobot',
      icon: <ChartNoAxesCombined size={25} />,
      colorClass: 'text-[#ef4444]',
      bgClass: 'bg-[#ef4444]/10',
      borderClass: 'border-[#ef4444]',
      btnBg: 'from-[#ef4444] to-[#ef4444]/80',
      title: t('erp.m5.t') || 'Analitika va Hisobotlar',
      subtitle: t('erp.m5.s') || 'Business Intelligence Dashboard',
      desc: t('erp.m5.d') || 'Savdoni, omborni, moliyani va xodimlarni tahlil qiling. Vizual grafiklar va chuqur insight\'lar.',
      features: [
        t('erp.m5.f1') || 'Sotuv dinamikasi grafigi',
        t('erp.m5.f2') || 'ABC tovar tahlili',
        t('erp.m5.f3') || 'Xodim unumdorligi hisoboti',
        t('erp.m5.f4') || 'Mijoz faoliyati tahlili',
        t('erp.m5.f5') || 'Daromad prognozi',
        t('erp.m5.f6') || 'PDF / Excel eksport',
      ],
      stats: [{ val: t('erp.stats.20.val') || '20+', label: t('erp.stats.hisobott.label') || 'Hisobot turi' }, { val: t('erp.stats.abc.val') || 'ABC', label: t('erp.stats.tovartah.label') || 'Tovar tahlil metodi' }, { val: t('erp.stats.pdfexcel.val') || 'PDF/Excel', label: t('erp.stats.eksportf.label') || 'Eksport format' }]
    },
    {
      id: 'users',
      icon: <Handshake size={25} />,
      colorClass: 'text-[#0891b2]',
      bgClass: 'bg-[#0891b2]/10',
      borderClass: 'border-[#0891b2]',
      btnBg: 'from-[#0891b2] to-[#0891b2]/80',
      title: t('erp.m6.t') || 'Foydalanuvchi & Huquqlar',
      subtitle: t('erp.m6.s') || 'Rol asosida kirish nazorati',
      desc: t('erp.m6.d') || 'Kassir, menejer, ombordor, direktor — har bir xodimga alohida huquqlar bering. Audit log to\'liq.',
      features: [
        t('erp.m6.f1') || 'Rol asosida huquq tizimi (RBAC)',
        t('erp.m6.f2') || 'Har bir operatsiya audit logi',
        t('erp.m6.f3') || 'Telegram orqali OTP kirish',
        t('erp.m6.f4') || 'Ko\'p filial boshqaruvi',
        t('erp.m6.f5') || 'Super admin panel',
        t('erp.m6.f6') || 'Smena va navbat boshqaruvi',
      ],
      stats: [{ val: t('erp.stats.10.val') || '10+', label: t('erp.stats.rolturi.label') || 'Rol turi' }, { val: t('erp.stats.100.val') || '100%', label: t('erp.stats.auditlog.label') || 'Audit log' }, { val: t('erp.stats.otp.val') || 'OTP', label: t('erp.stats.ikkifakt.label') || 'Ikki faktorli kirish' }]
    },
  ]

  const leadCapture = [
    { id: 1, name: 'ERP Tizim', avatar: LaptopMinimal },
    { id: 2, name: 'Chaqqon Pro (Restoran POS)', avatar: ChefHat },
    { id: 3, name: 'Web sayt yasash', avatar: Globe },
    { id: 4, name: 'Telegram bot', avatar: Bot },
    { id: 5, name: "Boshqa g'oya", avatar: Lamp },
  ]

  const [selected, setSelected] = useState(leadCapture[0])
  const SelectedIcon = selected.avatar

  return (
    <LandingLayout>
      {/* ── Hero ── */}
      <header className="relative pt-[100px] mt-20 pb-[120px] border-b border-black/[0.02]">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,0,0,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.03)_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_80%)] z-0" />
        <div className="max-w-[1400px] mx-auto px-6 relative z-10 grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-[60px] items-center text-center lg:text-left">
          <div className="flex flex-col items-center lg:items-start">
            <div className="animate-[slideUp_0.8s_ease-out_0.1s_backwards] inline-block px-4 py-1.5 bg-blue-600/10 border border-blue-600/20 rounded-full text-[13px] font-bold text-blue-600 mb-6">
              {t('land.b2b')}
            </div>
            <h1 className="animate-[slideUp_0.8s_ease-out_0.2s_backwards] text-[clamp(32px,9vw,48px)] lg:text-[clamp(48px,6vw,68px)] font-black leading-[1.05] tracking-[-0.04em] m-0 mb-6 text-slate-900">
              {t('land.erp')} <br />
              <span className="bg-linear-to-br from-emerald-600 to-blue-600 bg-clip-text text-transparent inline-block animate-[bgPan_4s_linear_infinite_alternate]">
                {t('land.eco')}
              </span>
            </h1>
            <p className="animate-[slideUp_0.8s_ease-out_0.3s_backwards] text-[19px] text-slate-500 leading-[1.6] m-0 mb-10 max-w-[560px]">
              {t('land.desc1')}
            </p>
            <div className="animate-[slideUp_0.8s_ease-out_0.4s_backwards] flex flex-col lg:flex-row gap-4 mb-10 w-full lg:w-auto lg:justify-start justify-center">
              <button
                className="inline-flex items-center justify-center gap-2 bg-linear-to-br from-blue-600 to-blue-500 text-white border-none font-bold px-8 py-4 text-[16px] rounded-2xl cursor-pointer transition-all duration-[400ms] ease-[cubic-bezier(0.175,0.885,0.32,1.275)] shadow-[0_10px_30px_rgba(37,99,235,0.15)] relative overflow-hidden group hover:-translate-y-[3px] hover:scale-[1.02] hover:shadow-[0_15px_30px_rgba(37,99,235,0.3)] w-full lg:w-auto"
                onClick={() => {
                  const leadSection = document.getElementById('lead-form');
                  if (leadSection) leadSection.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                {t('land.hero.req_quote') || 'So\'rov qoldirish'} <span className="transition-transform duration-300 group-hover:translate-x-1">{ICONS.arrowRight}</span>
              </button>
            </div>

            <div className="animate-[slideUp_0.8s_ease-out_0.5s_backwards] text-[14px] border-t border-black/8 pt-6 pb-2.5 max-w-[480px]">
              <div className="flex gap-[20px] flex-wrap font-semibold flex-col lg:flex-row items-center lg:items-start text-xs lg:text-sm">
                <div className='flex items-center gap-1.5'>
                  <span className='text-green-600 animate-pulse'><ShieldCheck size={18} /></span>
                  <span className="text-blue-600">{t('land.sec1')}</span>
                </div>
                <div className='flex items-center gap-1.5'>
                  <span className='text-yellow-500 animate-pulse'><Zap size={18} /></span>
                  <span className="text-blue-600">{t('land.sec2')}</span>
                </div>
                <div className='flex items-center gap-1.5'>
                  <span className='text-gray-600 animate-pulse'><Cloud size={18} /></span>
                  <span className="text-blue-600">{t('land.sec3')}</span>
                </div>
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
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
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
                <div className="w-14 h-14 bg-white border border-black/8 rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">
                  {ICONS.pos}
                </div>
                <h3 className="m-0 mb-4 text-[24px] font-extrabold tracking-[-0.02em] text-slate-900">{t('land.omni')}</h3>
                <p className="m-0 text-slate-500 leading-[1.7] text-[16px]">{t('land.omniDesc')}</p>
                <span className="inline-flex items-center gap-1.5 text-[14px] font-bold text-blue-600 mt-5 opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0">{t('land.chaqqon.box_more') || 'Batafsil ko\'rish'} {ICONS.arrowRight}</span>
              </div>
              <div className="absolute -right-[30px] -bottom-[30px] w-[65%] h-[110%] z-[1] opacity-30 transition-opacity duration-[800ms] group-hover:opacity-60" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100' opacity='0.1'%3E%3Crect x='10' y='10' width='80' height='80' rx='12' stroke='%232563eb' stroke-width='3' fill='none'/%3E%3C/svg%3E\")", backgroundRepeat: "repeat" }} />
            </div>

            {/* Box 2 → ERP Tizim (Analitika) */}
            <div
              className="group cursor-pointer bg-white/70 backdrop-blur-lg border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] animate-[slideUp_0.8s_backwards_0.2s] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)]"
              onClick={() => navigate('/erp-tizim')}
              title="Analitika va hisobotlar"
            >
              <div className="relative z-10 flex flex-col h-full transition-transform duration-300 group-hover:-translate-y-1">
                <div className="w-14 h-14 bg-white border border-black/8 rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">{ICONS.chart}</div>
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
                <div className="w-14 h-14 bg-white border border-black/8 rounded-2xl flex items-center justify-center mb-6 text-blue-600 shadow-sm transition-all duration-400 ease-[cubic-bezier(0.175,0.885,0.32,1.275)] group-hover:scale-[1.15] group-hover:rotate-[5deg] group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 group-hover:shadow-[0_10px_20px_rgba(37,99,235,0.3)]">{ICONS.crm}</div>
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

      {/* ── Modules Interactive ── */}
      <section className="py-[100px] max-w-[1400px] mx-auto" id="modullar">
        <div>
          <div className="text-center mb-[72px]">
            <div className="inline-block px-4 py-1.5 bg-blue-600/10 border border-blue-600/15 rounded-full text-[13px] font-bold text-blue-600 mb-5 uppercase tracking-wider">{t('erp.mod.tag') || 'Modullar'}</div>
            <h2 className="text-3xl md:text-[4vw] lg:text-[44px] font-black text-slate-900 tracking-tight mb-4">{t('erp.mod.title') || '6 ta kuchli modul — bitta tizim'}</h2>
            <p className="text-lg text-slate-500 max-w-[560px] mx-auto leading-relaxed">{t('erp.mod.desc') || 'Har bir biznes jarayoni uchun maxsus ishlab chiqilgan, bir-biri bilan to\'liq integratsiya qilingan modullar'}</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 bg-white rounded-3xl border border-black/5 overflow-hidden shadow-2xl shadow-black/5">
            {/* Sidebar */}
            <div className="border-r border-black/5 flex flex-col bg-slate-50/50 p-2 gap-1">
              {modules.map((mod, idx) => (
                <button
                  key={mod.id}
                  className={`flex cursor-pointer items-center gap-4 p-5 rounded-xl border-1.5 border-transparent transition-all text-left font-sans ${activeModule === idx
                    ? `border-l-3 font-bold ${mod.borderClass} ${mod.colorClass} ${mod.bgClass}`
                    : 'text-slate-500 hover:bg-black/5 hover:text-slate-900'
                    }`}
                  onClick={() => setActiveModule(idx)}
                >
                  <span className="text-2xl shrink-0">{mod.icon}</span>
                  <div>
                    <div className="text-[16px] font-bold text-inherit">{mod.title}</div>
                    <div className="text-[14px] leading-5 text-inherit opacity-70 mt-0.5">{mod.subtitle}</div>
                  </div>
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="p-10 animate-fadeInUp" key={activeModule}>
              <div className={`flex items-center gap-5 mb-6 pb-6 border-b-2 ${modules[activeModule].borderClass}`}>
                <div className={`text-[36px] w-[78px] h-[78px] rounded-2xl flex items-center justify-center shrink-0 ${modules[activeModule].colorClass} ${modules[activeModule].bgClass}`}>
                  {modules[activeModule].icon}
                </div>
                <div>
                  <h3 className="text-2xl font-black text-slate-900 tracking-tight">{modules[activeModule].title}</h3>
                  <p className="text-sm text-slate-500 mt-1">{modules[activeModule].subtitle}</p>
                </div>
              </div>
              <p className="text-[17px] leading-relaxed text-slate-600 mb-8">{modules[activeModule].desc}</p>

              <div className="flex gap-4 mb-8 flex-wrap">
                {modules[activeModule].stats.map((s, i) => (
                  <div key={i} className={`flex-1 min-w-[140px] bg-slate-50 border border-black/5 border-t-3 rounded-xl p-4 text-center ${modules[activeModule].borderClass}`}>
                    <span className={`block text-2xl font-black tracking-tight ${modules[activeModule].colorClass}`}>{s.val}</span>
                    <span className="block text-xs text-slate-500 mt-1 font-semibold">{s.label}</span>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-8">
                {modules[activeModule].features.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 text-[15px] font-semibold text-slate-800">
                    <span className={`w-7 h-7 animate-pulse rounded-lg flex items-center justify-center shrink-0 ${modules[activeModule].colorClass} ${modules[activeModule].bgClass}`}>
                      <CheckIcon />
                    </span>
                    <span>{f}</span>
                  </div>
                ))}
              </div>

              <button
                className={`inline-flex items-center gap-2 bg-gradient-to-r ${modules[activeModule].btnBg} text-white font-bold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg`}
                onClick={() => window.location.href = '/register'}
              >
                {t('erp.mod.btn') || 'Bu modul bilan boshlash'} <ArrowRight />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Modullar / How it works ── */}
      <section id="modules" className="py-[120px] relative bg-gradient-to-b from-slate-100 to-white border-y border-black/[0.08]">
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
          <div className="text-center mb-[70px] animate-[fadeInUp_0.8s_ease-out_both]">
            <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-slate-900">{t('land.singleDb')}</h2>
            <p className="text-[18px] text-slate-500 max-w-[600px] mx-auto">{t('land.noPaper')}</p>
          </div>
          <TabbedModules t={t} />
        </div>
      </section>

      {/* ── Chaqqon Pro ── */}
      <section className="py-[120px] w-full flex justify-center relative bg-linear-to-br from-amber-50 to-orange-100 border-y border-orange-200">
        <div className="w-max px-6 relative z-10">
          <div className="text-center mb-[70px] animate-[fadeInUp_0.8s_ease-out_both]">
            <div className="text-orange-600 bg-orange-600/10 inline-block px-3 py-1 rounded-xl font-bold mb-4">🍽️ {t('land.chaqqon.badge') || 'Yangi tizim'}</div>
            <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-orange-900">{t('land.chaqqon.title') || 'Chaqqon Pro'}</h2>
            <p className="text-[18px] text-orange-700 max-w-[600px] mx-auto">{t('land.chaqqon.sub') || 'Restoran POS'}</p>
          </div>
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
                <li className="flex items-center gap-3 text-[15px] font-semibold group/item"><BadgeCheck /> {t('land.chaqqon.l2')}</li>
                <li className="flex items-center gap-3 text-[15px] font-semibold group/item"><BadgeCheck /> {t('land.chaqqon.l3')}</li>
                <li className="flex items-center gap-3 text-[15px] font-semibold group/item"><BadgeCheck /> {t('land.chaqqon.l1')}</li>
                <li className="flex items-center gap-3 text-[15px] font-semibold group/item"><BadgeCheck /> {t('land.chaqqon.l4')}</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ── Boshqa Xizmatlar / IT Agency ── */}
      <section className="py-[120px] relative bg-slate-50 border-t border-slate-200">
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
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
                <div className="text-blue-600 mb-4">
                  <svg xmlns="http://www.w3.org/2000/svg" width="55" height="55" fill="#0000FF" viewBox="0 0 256 256"><path d="M128,24h0A104,104,0,1,0,232,128,104.12,104.12,0,0,0,128,24Zm88,104a87.61,87.61,0,0,1-3.33,24H174.16a157.44,157.44,0,0,0,0-48h38.51A87.61,87.61,0,0,1,216,128ZM102,168H154a115.11,115.11,0,0,1-26,45A115.27,115.27,0,0,1,102,168Zm-3.9-16a140.84,140.84,0,0,1,0-48h59.88a140.84,140.84,0,0,1,0,48ZM40,128a87.61,87.61,0,0,1,3.33-24H81.84a157.44,157.44,0,0,0,0,48H43.33A87.61,87.61,0,0,1,40,128ZM154,88H102a115.11,115.11,0,0,1,26-45A115.27,115.27,0,0,1,154,88Zm52.33,0H170.71a135.28,135.28,0,0,0-22.3-45.6A88.29,88.29,0,0,1,206.37,88ZM107.59,42.4A135.28,135.28,0,0,0,85.29,88H49.63A88.29,88.29,0,0,1,107.59,42.4ZM49.63,168H85.29a135.28,135.28,0,0,0,22.3,45.6A88.29,88.29,0,0,1,49.63,168Zm98.78,45.6a135.28,135.28,0,0,0,22.3-45.6h35.66A88.29,88.29,0,0,1,148.41,213.6Z"></path></svg>
                </div>
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
                <div className="text-green-600 mb-4">
                  <svg xmlns="http://www.w3.org/2000/svg" width="55" height="55" fill="#22c55e" viewBox="0 0 256 256"><path d="M200,48H136V16a8,8,0,0,0-16,0V48H56A32,32,0,0,0,24,80V192a32,32,0,0,0,32,32H200a32,32,0,0,0,32-32V80A32,32,0,0,0,200,48Zm16,144a16,16,0,0,1-16,16H56a16,16,0,0,1-16-16V80A16,16,0,0,1,56,64H200a16,16,0,0,1,16,16Zm-52-56H92a28,28,0,0,0,0,56h72a28,28,0,0,0,0-56Zm-24,16v24H116V152ZM80,164a12,12,0,0,1,12-12h8v24H92A12,12,0,0,1,80,164Zm84,12h-8V152h8a12,12,0,0,1,0,24ZM72,108a12,12,0,1,1,12,12A12,12,0,0,1,72,108Zm88,0a12,12,0,1,1,12,12A12,12,0,0,1,160,108Z"></path></svg>
                </div>
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
                <div className="text-red-500 mb-4">
                  <svg xmlns="http://www.w3.org/2000/svg" width="55" height="55" fill="#ef4444" viewBox="0 0 256 256"><path d="M232,168h-8V72a24,24,0,0,0-24-24H56A24,24,0,0,0,32,72v96H24a8,8,0,0,0-8,8v16a24,24,0,0,0,24,24H216a24,24,0,0,0,24-24V176A8,8,0,0,0,232,168ZM48,72a8,8,0,0,1,8-8H200a8,8,0,0,1,8,8v96H48ZM224,192a8,8,0,0,1-8,8H40a8,8,0,0,1-8-8v-8H224ZM152,88a8,8,0,0,1-8,8H112a8,8,0,0,1,0-16h32A8,8,0,0,1,152,88Z"></path></svg>
                </div>
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
        <div className="absolute inset-0 bg-repeat animate-[slideUp_20s_linear_infinite] opacity-40 z-0" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60' opacity='0.1'%3E%3Ccircle cx='2' cy='2' r='2' fill='%23fff'/%3E%3C/svg%3E\")" }} />
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
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
                <form onSubmit={handleLeadSubmit} className="flex w-full flex-col gap-[15px] text-left">
                  <h3 className="text-[1.4rem] mb-2.5 font-bold m-0">{t('land.form.title')}</h3>

                  <div className="flex flex-col">
                    <Listbox
                      value={leadForm.service}
                      onChange={(value) => setLeadForm({ ...leadForm, service: value })}
                    >
                      <label className="text-[0.9rem] text-slate-600 block mb-2">{t('land.form.service')}</label>

                      <div className="relative">
                        <ListboxButton className="w-full cursor-pointer flex items-center p-3 justify-between rounded-lg border border-slate-200 text-[1rem] bg-white text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors">
                          <span className="flex items-center gap-3">
                            {/* Tanlangan matnga qarab ikonkani komponent sifatida yaratamiz */}
                            {(() => {
                              const SelectedIcon = getServiceIcon(leadForm.service);
                              return <SelectedIcon className="size-5 shrink-0 text-slate-500" />;
                            })()}
                            <span className="block truncate">{leadForm.service}</span>
                          </span>
                          <ChevronsUpDown
                            aria-hidden="true"
                            className="size-5 text-gray-400"
                          />
                        </ListboxButton>

                        <ListboxOptions
                          transition
                          className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md outline-0 bg-white text-base border border-slate-200 transition duration-100 ease-in data-[closed]:opacity-0 sm:text-sm shadow-lg"
                        >
                          {serviceOptions.map((optionName, index) => {
                            const OptionIcon = getServiceIcon(optionName);

                            return (
                              <ListboxOption
                                key={index}
                                value={optionName}
                                className="group relative py-2.5 pr-9 pl-3 select-none cursor-pointer text-slate-800 data-[focus]:bg-blue-500 data-[focus]:text-white outline-hidden"
                              >
                                <div className="flex items-center gap-3">
                                  <OptionIcon className="size-5 shrink-0 text-gray-400 group-data-[focus]:text-white" />
                                  <span className="block truncate font-normal group-data-[selected]:font-semibold">
                                    {optionName}
                                  </span>
                                </div>

                                <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-blue-500 group-not-data-[selected]:hidden group-data-[focus]:text-white">
                                  <CheckIcon aria-hidden="true" className="size-5" />
                                </span>
                              </ListboxOption>
                            )
                          })}
                        </ListboxOptions>
                      </div>
                    </Listbox>
                  </div>

                  <div className="flex flex-col">
                    <label className="text-[0.9rem] text-slate-600 mb-2 block">{t('land.form.name')}</label>
                    <input
                      type="text"
                      required
                      value={leadForm.name}
                      onChange={e => setLeadForm({ ...leadForm, name: e.target.value })}
                      placeholder="Alisher"
                      className="w-full p-3 rounded-lg border border-slate-200 text-[1rem] bg-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                    />
                  </div>

                  <div className="flex flex-col">
                    <label className="text-[0.9rem] text-slate-600 mb-2 block">{t('land.form.phone')}</label>
                    <input
                      type="text"
                      required
                      value={leadForm.phone}
                      onChange={e => setLeadForm({ ...leadForm, phone: e.target.value })}
                      placeholder="+998"
                      className="w-full p-3 rounded-lg border border-slate-200 text-[1rem] bg-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={leadStatus === 'loading'}
                    className="bg-blue-600 text-white p-[14px] flex justify-center items-center gap-2 rounded-lg text-[1.1rem] font-semibold border-none cursor-pointer mt-2.5 transition-colors hover:bg-blue-700 disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    <MailCheck size={21} /> {leadStatus === 'loading' ? t('land.form.loading') : t('land.form.submit')}
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
