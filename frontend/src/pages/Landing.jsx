import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import LandingLayout from '../components/LandingLayout'
import { ShieldCheck, Zap, Cloud, Globe, Bot, Laptop, BadgeCheck, ArrowBigDown, ChevronDown, LaptopMinimal, Warehouse, Users, BadgeDollarSign, ChartNoAxesCombined, Handshake, CheckIcon, ArrowRight, Lamp, ChevronsUpDownIcon, ListChevronsUpDownIcon, ChefHat, Monitor, Globe2, HelpCircle, ChevronsUpDown, GlobeIcon, Send, MailCheck } from 'lucide-react'
import axios from 'axios'
import { useSeo } from '../hooks/useSeo'
import { Label, Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'
import Reveal from '../components/Reveal'

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

// ─── UNROLLED SINGLE DB SHOWCASE (ALL FEATURES FULLY OPEN) ──────────────────────
function TabbedModules({ t }) {
  const features = [
    {
      title: t('land.tab1.title') || "Tovarlar va Nomenklatura",
      desc: t('land.tab1.desc') || "Minglab tovar pozitsiyalarini shtrix-kod kataloglari orqali yagona bazaga birlashtiring va real-vaqtda kuzating.",
      visual: <VisualWarehouse />,
      iconBg: "bg-blue-50 text-blue-600 border-blue-200"
    },
    {
      title: t('land.tab2.title') || "Sotuv va Tranzaksiyalar",
      desc: t('land.tab2.desc') || "B2B uchun shartnomaviy sotuv, kassa terminallari, cheklar va naqd/bank kartasi tranzaksiyalari oqimi.",
      visual: <VisualPOS />,
      iconBg: "bg-emerald-50 text-emerald-600 border-emerald-200"
    },
    {
      title: t('land.tab3.title') || "Audit va Xavfsizlik",
      desc: t('land.tab3.desc') || "Xodimlarning barcha harakatlari va tranzaksiya o'zgarishlari tizim loglariga muhrlanadi. To'liq ichki nazorat va ruxsatlar tizimi (RBAC).",
      visual: <VisualAudit />,
      iconBg: "bg-purple-50 text-purple-600 border-purple-200"
    }
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      {features.map((item, idx) => (
        <div
          key={idx}
          className="bg-white rounded-3xl p-8 border border-slate-200/80 shadow-xl shadow-slate-200/40 hover:shadow-2xl hover:border-blue-400/50 transition-all duration-300 flex flex-col justify-between group"
        >
          <div className="space-y-4 mb-6">
            <div className="flex items-center gap-3">
              <div className={`p-3.5 rounded-2xl border font-bold text-lg shadow-sm ${item.iconBg}`}>
                0{idx + 1}
              </div>
              <h3 className="text-xl font-extrabold text-slate-900 tracking-tight group-hover:text-blue-600 transition-colors">
                {item.title}
              </h3>
            </div>
            <p className="text-slate-600 text-sm leading-relaxed">
              {item.desc}
            </p>
          </div>

          <div className="rounded-2xl overflow-hidden border border-slate-100 bg-slate-50 p-2 shadow-inner flex justify-center items-center">
            {item.visual}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── MAIN COMPONENT ─────────────────────────────────────────────────────────
export default function Landing() {
  const { t } = useLang()
  const navigate = useNavigate()
  useSeo(
    "E-Code — ERP, POS va biznesni raqamlashtirish yechimlarini yaratuvchi kompaniya.",
    "E-Code — ERP, POS va biznesni raqamlashtirish yechimlarini yaratuvchi kompaniya."
  )

  const [leadForm, setLeadForm] = useState({ service: '', name: '', phone: '+998' })
  const [leadStatus, setLeadStatus] = useState(null) // 'loading', 'success', 'error'

  const getServiceIcon = (serviceName) => {
    switch (serviceName) {
      case 'ERP Tizim':
        return LaptopMinimal;
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
    'ERP Tizim'
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
    { id: 3, name: 'Web sayt yasash', avatar: Globe },
    { id: 4, name: 'Telegram bot', avatar: Bot },
    { id: 5, name: "Boshqa g'oya", avatar: Lamp },
  ]

  const [selected, setSelected] = useState(leadCapture[0])
  const SelectedIcon = selected.avatar

  return (
    <LandingLayout>
      {/* ── Hero ── */}
      <header className="relative pt-[100px] mt-1 pb-[120px] border-b border-black/[0.02]">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,0,0,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.03)_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_80%)] z-0" />
        <div className="max-w-[1400px] mx-auto relative z-10 grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-[60px] items-center text-center lg:text-left">
          <div className="flex flex-col items-center lg:items-start">
            <div style={{ animationDelay: '100ms' }} className="animate-slide-up inline-block px-4 py-1.5 bg-blue-600/10 border border-blue-600/20 rounded-full text-[13px] font-bold text-blue-600 mb-6">
              {t('land.b2b')}
            </div>
            <h1 style={{ animationDelay: '200ms' }} className="animate-slide-up text-[clamp(32px,9vw,55px)] lg:text-[clamp(48px,6vw,68px)] font-black leading-[1.05] tracking-[-0.04em] m-0 mb-6 text-slate-900">
              {t('land.erp')} <br />
              <span className="bg-gradient-to-r from-emerald-600 via-teal-500 to-blue-600 bg-clip-text text-transparent inline-block">
                {t('land.eco')}
              </span>
            </h1>
            <p style={{ animationDelay: '350ms' }} className="animate-slide-up text-[19px] text-slate-600 leading-[1.6] m-0 mb-10 max-w-[560px]">
              {t('land.desc1')}
            </p>
            <div style={{ animationDelay: '450ms' }} className="animate-slide-up flex flex-col lg:flex-row gap-4 mb-10 w-full lg:w-auto lg:justify-start justify-center">
              <button
                className="inline-flex mx-auto items-center w-max justify-center gap-2 bg-gradient-to-r from-blue-600 to-emerald-600 text-white border-none font-bold px-8 py-4 text-[16px] rounded-2xl cursor-pointer transition-all duration-300 shadow-[0_10px_30px_rgba(37,99,235,0.25)] relative overflow-hidden group hover:-translate-y-[3px] hover:scale-[1.02] hover:shadow-[0_15px_30px_rgba(37,99,235,0.4)]"
                onClick={() => {
                  const leadSection = document.getElementById('lead-form');
                  if (leadSection) leadSection.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                {t('land.hero.req_quote') || 'So\'rov qoldirish'} <span className="transition-transform duration-300 group-hover:translate-x-1">{ICONS.arrowRight}</span>
              </button>
            </div>

            <div style={{ animationDelay: '550ms' }} className="animate-slide-up text-[14px] border-t border-black/8 pt-6 pb-2.5 max-w-[480px]">
              <div className="flex gap-[20px] flex-wrap font-semibold flex-col lflex-row items-center lg:items-start text-xs lg:text-sm">
                <div className='flex items-center gap-1.5'>
                  <span className='text-emerald-600 animate-pulse'><ShieldCheck size={18} /></span>
                  <span className="text-slate-700">{t('land.sec1')}</span>
                </div>
                <div className='flex items-center gap-1.5'>
                  <span className='text-amber-500 animate-pulse'><Zap size={18} /></span>
                  <span className="text-slate-700">{t('land.sec2')}</span>
                </div>
                <div className='flex items-center gap-1.5'>
                  <span className='text-blue-600 animate-pulse'><Cloud size={18} /></span>
                  <span className="text-slate-700">{t('land.sec3')}</span>
                </div>
              </div>
            </div>
          </div>

          <div style={{ animationDelay: '300ms' }} className="hidden lg:block perspective-[1200px] animate-slide-up">
            <DashboardMinimal />
          </div>
        </div>
      </header>

      {/* ── Features Bento Grid ── */}
      <section id="features" className="py-[120px] relative">
        <div className="max-w-[1400px] mx-auto relative z-10">
          <Reveal direction="up" delay={100}>
            <div className="text-center mb-[70px]">
              <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-slate-900">{t('land.ecosystem')}</h2>
              <p className="text-[18px] text-slate-500 max-w-[600px] mx-auto">{t('land.arch')}</p>
            </div>
          </Reveal>

          <div className="grid grid-cols-1 lg:grid-cols-3 auto-rows-[minmax(280px,auto)] gap-6">

            {/* Box 1 - Hero Bento → ERP Tizim */}
            <Reveal direction="up" delay={150} className="lg:col-span-2">
              <div
                className="group cursor-pointer bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)] h-full"
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
            </Reveal>

            {/* Box 2 → ERP Tizim (Analitika) */}
            <Reveal direction="up" delay={250}>
              <div
                className="group cursor-pointer bg-white/70 backdrop-blur-lg border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)] h-full"
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
            </Reveal>

            {/* Box 3 → ERP Tizim (CRM) */}
            <Reveal direction="up" delay={300}>
              <div
                className="group cursor-pointer bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)] h-full"
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
            </Reveal>

            {/* Box 4 - Wide Bento → ERP Tizim (Ombor) */}
            <Reveal direction="up" delay={400} className="lg:col-span-2">
              <div
                className="group cursor-pointer bg-white/70 backdrop-blur-[16px] border border-white/80 rounded-[24px] p-10 flex flex-col relative overflow-hidden shadow-[0_10px_40px_rgba(0,0,0,0.04),inset_0_0_0_1px_rgba(255,255,255,0.5)] transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] hover:-translate-y-2 hover:scale-[1.01] hover:shadow-[0_30px_60px_rgba(0,0,0,0.08),inset_0_0_0_2px_rgba(37,99,235,0.1)] h-full"
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
            </Reveal>

          </div>
        </div>
      </section>

      {/* ── Modules Interactive ── */}
      <section className="py-[100px] max-w-[1400px] mx-auto" id="modullar">
        <div>
          <Reveal direction="up" delay={100}>
            <div className="text-center mb-[72px]">
              <div className="inline-block px-4 py-1.5 bg-blue-600/10 border border-blue-600/15 rounded-full text-[13px] font-bold text-blue-600 mb-5 uppercase tracking-wider">{t('erp.mod.tag') || 'Modullar'}</div>
              <h2 className="text-3xl md:text-[4vw] lg:text-[44px] font-black text-slate-900 tracking-tight mb-4">{t('erp.mod.title') || '6 ta kuchli modul — bitta tizim'}</h2>
              <p className="text-lg text-slate-500 max-w-[560px] mx-auto leading-relaxed">{t('erp.mod.desc') || 'Har bir biznes jarayoni uchun maxsus ishlab chiqilgan, bir-biri bilan to\'liq integratsiya qilingan modullar'}</p>
            </div>
          </Reveal>

          <Reveal direction="up" delay={200}>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {modules.map((mod) => (
                <div
                  key={mod.id}
                  className="bg-white rounded-3xl p-8 border border-slate-200/80 shadow-xl shadow-slate-200/30 hover:shadow-2xl hover:border-blue-400/50 transition-all duration-300 flex flex-col justify-between group"
                >
                  <div className="space-y-6">
                    {/* Header: Icon + Titles */}
                    <div className="flex items-center gap-4 border-b border-slate-100 pb-5">
                      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 shadow-md ${mod.colorClass} ${mod.bgClass}`}>
                        {mod.icon}
                      </div>
                      <div>
                        <h3 className="text-xl font-extrabold text-slate-900 tracking-tight group-hover:text-blue-600 transition-colors">
                          {mod.title}
                        </h3>
                        <p className="text-xs text-slate-500 font-medium mt-0.5">{mod.subtitle}</p>
                      </div>
                    </div>

                    {/* Description */}
                    <p className="text-slate-600 text-sm leading-relaxed">
                      {mod.desc}
                    </p>

                    {/* Key Stats Pills */}
                    <div className="flex gap-2 flex-wrap">
                      {mod.stats.map((s, i) => (
                        <div
                          key={i}
                          className={`flex-1 min-w-[90px] bg-slate-50 border border-slate-200/70 rounded-xl p-2.5 text-center`}
                        >
                          <span className={`block text-lg font-black tracking-tight ${mod.colorClass}`}>{s.val}</span>
                          <span className="block text-[11px] text-slate-500 font-medium">{s.label}</span>
                        </div>
                      ))}
                    </div>

                    {/* Features Checklist */}
                    <div className="space-y-2.5 pt-2">
                      {mod.features.slice(0, 4).map((f, i) => (
                        <div key={i} className="flex items-center gap-2.5 text-xs font-semibold text-slate-800">
                          <span className={`w-5 h-5 rounded-md flex items-center justify-center shrink-0 ${mod.colorClass} ${mod.bgClass}`}>
                            <CheckIcon />
                          </span>
                          <span>{f}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Action Button */}
                  <div className="pt-6 mt-6 border-t border-slate-100">
                    <button
                      className={`w-full inline-flex items-center justify-center gap-2 bg-gradient-to-r ${mod.btnBg} text-white font-bold text-sm py-3.5 px-6 rounded-xl cursor-pointer transition-all duration-300 hover:shadow-lg hover:scale-[1.02] active:scale-95`}
                      onClick={() => window.location.href = '/register'}
                    >
                      {t('erp.mod.btn') || 'Bu modul bilan boshlash'} <ArrowRight />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Modullar / How it works ── */}
      <section id="modules" className="py-[120px] relative bg-gradient-to-b from-slate-100 to-white border-y border-black/[0.08]">
        <div className="max-w-[1400px] mx-auto relative z-10">
          <Reveal direction="up" delay={100}>
            <div className="text-center mb-[70px]">
              <h2 className="text-[clamp(32px,5vw,44px)] font-extrabold tracking-[-0.04em] mb-4 text-slate-900">{t('land.singleDb')}</h2>
              <p className="text-[18px] text-slate-500 max-w-[600px] mx-auto">{t('land.noPaper')}</p>
            </div>
          </Reveal>

          <Reveal direction="up" delay={200}>
            <TabbedModules t={t} />
          </Reveal>
        </div>
      </section>



      {/* ── Lead Capture / So'rov Qoldirish ── */}
      <section id="lead-form" className="py-[140px] bg-blue-600 relative overflow-hidden">
        <div className="absolute inset-0 bg-repeat animate-[slideUp_20s_linear_infinite] opacity-40 z-0" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60' opacity='0.1'%3E%3Ccircle cx='2' cy='2' r='2' fill='%23fff'/%3E%3C/svg%3E\")" }} />
        <div className="max-w-[1400px] mx-auto relative z-10">
          <Reveal direction="zoom" delay={150}>
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
                    <label className="text-[0.9rem] text-slate-600 block mb-2">{t('land.form.service')}</label>
                    <input
                      type="text"
                      placeholder="Masalan: ERP Tizim, POS Kassa, Veb sayt..."
                      value={leadForm.service}
                      onChange={(e) => setLeadForm({ ...leadForm, service: e.target.value })}
                      className="w-full p-3 rounded-lg border border-slate-200 text-[1rem] bg-white text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                      required
                    />
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
        </Reveal>
      </div>
    </section>
    </LandingLayout>
  )
}
