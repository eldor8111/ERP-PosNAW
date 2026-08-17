import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'
import { Clock, Mail, MessageCircleHeart, Send } from 'lucide-react'

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
export default function NoyobDasturlar() {
  const navigate = useNavigate()
  const { t } = useLang()
  const [activeType, setActiveType] = useState(0)

  useSeo(
    "Noyob Dasturlar – Maxsus Dasturiy Yechimlar | E-code",
    "E-code: sizning biznesingiz uchun maxsus ishlab chiqilgan noyob dasturlar va avtomatlashtirish yechimlari. O'zbekistonda professional dastur yaratish."
  )

  const solutionTypes = [
    {
      icon: '🏭',
      color: 'text-red-500',
      borderColor: 'border-l-red-500',
      bg: 'bg-red-500/10',
      gradient: 'from-red-500 to-red-500/80',
      title: t('nd.erptizim.t') || 'ERP Tizimlar',
      desc: t('nd.kichikbi.d') || 'Kichik biznesdan yirik korxonagacha — to\'liq avtomatlashtirilgan boshqaruv tizimi.',
      features: ['Savdo va ombor boshqaruvi', 'CRM va mijozlar tizimi', 'Moliya va buxgalteriya', 'HR va xodimlar', 'Ko\'p omborxona va filial', 'Rol asosida huquq tizimi'],
    },
    {
      icon: '📱',
      color: 'text-violet-500',
      borderColor: 'border-l-violet-500',
      bg: 'bg-violet-500/10',
      gradient: 'from-violet-500 to-violet-500/80',
      title: t('nd.mobililo.t') || 'Mobil Ilovalar',
      desc: t('nd.iosvaand.d') || 'iOS va Android uchun native yoki cross-platform mobil ilovalar.',
      features: ['React Native/Flutter', 'App Store / Google Play', 'Push bildirishnomalar', 'Offline ishlash rejimi', 'Biometrik autentifikatsiya', 'Native kamera/GPS'],
    },
    {
      icon: '🏥',
      color: 'text-cyan-600',
      borderColor: 'border-l-cyan-600',
      bg: 'bg-cyan-600/10',
      gradient: 'from-cyan-600 to-cyan-600/80',
      title: t('nd.tibbiyti.t') || 'Tibbiy Tizimlar',
      desc: t('nd.klinikal.d') || 'Klinikalar, laboratoriyalar va tibbiyot markazlari uchun maxsus tizimlar.',
      features: ['Bemor qabul tizimi', 'Tibbiy tarix (EHR)', 'Laboratoriya natijalari', 'Navbat boshqaruvi', 'To\'lov integratsiyasi', 'Hisobot va analitika'],
    },
    {
      icon: '🏫',
      color: 'text-amber-500',
      borderColor: 'border-l-amber-500',
      bg: 'bg-amber-500/10',
      gradient: 'from-amber-500 to-amber-500/80',
      title: t('nd.ta.t') || 'Ta\'lim Platformalari',
      desc: t('nd.onlinema.d') || 'Online maktablar,Axborot texnologiyalari va o\'quv markazlari uchun LMS tizimlar.',
      features: ['Kurs yaratish vositasi', 'Video darslar', 'Test va baholash', 'Sertifikat berish', 'To\'lov tizimi', 'Telegram integratsiya'],
    },
    {
      icon: '📦',
      color: 'text-emerald-500',
      borderColor: 'border-l-emerald-500',
      bg: 'bg-emerald-500/10',
      gradient: 'from-emerald-500 to-emerald-500/80',
      title: t('nd.logistik.t') || 'Logistika & Yetkazib Berish',
      desc: t('nd.buyurtma.d') || 'Buyurtmalarni kuzatish, kuryer boshqaruvi va omborxona avtomatlash.',
      features: ['Real-vaqt buyurtma kuzatuvi', 'Kuryer mobil ilovasi', 'Marshrut optimallashtirish', 'Mijoz bildirishnomasi', 'Ombor boshqaruvi', 'Hisobot va tahlil'],
    },
    {
      icon: '🏗️',
      color: 'text-blue-600',
      borderColor: 'border-l-blue-600',
      bg: 'bg-blue-600/10',
      gradient: 'from-blue-600 to-blue-600/80',
      title: t('nd.construc.t') || 'Construction & Loyiha',
      desc: t('nd.qurilish.d') || 'Qurilish kompaniyalari va loyiha boshqaruvi uchun maxsus yechimlar.',
      features: ['Loyiha boshqaruvi', 'Resurs rejalashtirish', 'Xarajat nazorati', 'Xodimlar grafigi', 'Hujjat boshqaruvi', 'Mijoz hisobotlari'],
    },
  ]

  const devProcess = [
    { num: '01', icon: '🔍', title: t('nd.chuqurta.t') || 'Chuqur Tahlil', desc: t('nd.biznesin.d') || 'Biznesingiz, jarayonlar, muammolar va maqsadlarni batafsil o\'rganamiz. Raqobatchilar tahlili.', time: '1-2 kun' },
    { num: '02', icon: '📐', title: t('nd.arxitekt.t') || 'Arxitektura', desc: t('nd.texnikar.d') || 'Texnik arxitektura, ma\'lumotlar bazasi dizayni va tizim xavfsizligi rejasini ishlab chiqamiz.', time: '3-5 kun' },
    { num: '03', icon: '🎨', title: t('nd.uiuxdiza.t') || 'UI/UX Dizayn', desc: t('nd.figma.d') || 'Figma\'da to\'liq prototip va foydalanuvchi tajribasi loyihasini yaratamiz.', time: '1-2 hafta' },
    { num: '04', icon: '⚙️', title: t('nd.backendi.t') || 'Backend Ishlab Chiqish', desc: t('nd.serverto.d') || 'Server tomoni logika, API, ma\'lumotlar bazasi va xavfsizlik integratsiyasi.', time: '2-4 hafta' },
    { num: '05', icon: '💻', title: t('nd.frontend.t') || 'Frontend Ishlab Chiqish', desc: t('nd.interakt.d') || 'Interaktiv va responsive UI, animatsiyalar va foydalanuvchi funksionalligi.', time: '2-3 hafta' },
    { num: '06', icon: '🧪', title: t('nd.testqa.t') || 'Test & QA', desc: t('nd.unittest.d') || 'Unit testlar, integratsiya testlar, performance va xavfsizlik tekshiruvlari.', time: '1 hafta' },
    { num: '07', icon: '🚀', title: t('nd.deployis.t') || 'Deploy & Ishga Tushirish', desc: t('nd.serverso.d') || 'Server sozlash, CI/CD pipeline, monitoring va backup tizimini o\'rnatish.', time: '2-3 kun' },
    { num: '08', icon: '📊', title: t('nd.monitori.t') || 'Monitoring & Qo\'llab-Quvvatlash', desc: t('nd.doimiymo.d') || 'Doimiy monitoring, hotfix, yangi xususiyatlar va texnik qo\'llab-quvvatlash.', time: 'Doimiy' },
  ]

  const techStack = [
    { category: t('nd.frontend.c') || 'Frontend', techs: ['React', 'Next.js', 'TypeScript', 'TailwindCSS'] },
    { category: t('nd.backend.c') || 'Backend', techs: ['Python/Django', 'Node.js', 'FastAPI', 'Go'] },
    { category: t('nd.database.c') || 'Database', techs: ['PostgreSQL', 'MongoDB', 'Redis', 'Elasticsearch'] },
    { category: t('nd.mobile.c') || 'Mobile', techs: ['React Native', 'Flutter', 'Expo'] },
    { category: t('nd.infrastr.c') || 'Infrastructure', techs: ['Docker', 'Kubernetes', 'AWS', 'Nginx'] },
    { category: t('nd.integrat.c') || 'Integrations', techs: ['Telegram API', 'Payme', 'Click', 'Stripe'] },
  ]

  const projects = [
    { icon: '🛒', title: t('nd.ecodeerp.t') || 'E-code ERP POS', tags: ['ERP', 'SaaS', 'Multi-tenant'], desc: t('nd.ko.d') || 'Ko\'p foydalanuvchili savdo boshqaruv tizimi. 500+ aktiv kompaniya foydalanadi.', stats: ['500+ kompaniya', '6 modul', '3 yil bozorda'], color: 'text-blue-600', bg: 'bg-blue-600/10', border: 'border-blue-600/20' },
    { icon: '🏥', title: t('nd.medcrm.t') || 'MedCRM', tags: ['Healthcare', 'CRM', 'Mobile'], desc: t('nd.xususiyk.d') || 'Xususiy klinikalar uchun to\'liq tibbiy boshqaruv tizimi.', stats: ['12 klinika', '15K+ bemor', 'iOS & Android'], color: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
    { icon: '📚', title: t('nd.eduplatf.t') || 'EduPlatform', tags: ['EdTech', 'LMS', 'Telegram Bot'], desc: t('nd.onlineta.d') || 'Online ta\'lim markazi uchun kurs tizimi, test va sertifikatlash.', stats: ['8 maktab', '3K+ talaba', 'Telegram bot'], color: 'text-violet-500', bg: 'bg-violet-500/10', border: 'border-violet-500/20' },
  ]

  return (
    <LandingLayout>
      {/* Hero Section */}
      <section className="relative py-24 md:py-32 overflow-hidden flex items-center bg-gradient-to-br from-[#0f172a] via-[#3b0764] to-[#0f172a]">
        {/* Background Dots */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.08)_1px,transparent_1px)] bg-[size:28px_28px] pointer-events-none" />

        <div className="max-w-[1400px] mx-auto px-4 w-full relative z-10 text-center">
          {/* Breadcrumb */}
          <div className="inline-flex items-center gap-2 text-sm text-white/50 mb-6 font-medium">
            <span onClick={() => navigate('/')} className="cursor-pointer hover:opacity-100 opacity-60 transition-opacity">{t('nd.bc.home') || 'Bosh sahifa'}</span>
            <span className="opacity-60">›</span>
            <span>{t('nd.bc.current') || 'Noyob Dasturlar'}</span>
          </div>

          {/* Tag Badge */}
          <div
            className="inline-block px-5 ml-3 py-2 bg-violet-500/30 text-purple-200 border border-violet-500/40 rounded-full text-sm font-bold mb-8 animate-fadeIn"
            dangerouslySetInnerHTML={{ __html: t('nd.tag') || '💻 &nbsp;Custom Software Development' }}
          />

          {/* Title */}
          <h1 className="text-[clamp(44px,7vw,72px)] font-black leading-[1.08] tracking-tight text-white mb-7 animate-[fadeInUp_0.7s_ease-out_0.1s_both]">
            {t('nd.hero.title1') || 'G\'oyangizni'}<br />
            <span className="bg-gradient-to-r from-purple-200 to-purple-400 bg-clip-text text-transparent inline-block">
              {t('nd.hero.title2') || 'kuchli dasturga'}
            </span> {t('nd.hero.title3') || 'aylantiramiz'}
          </h1>

          {/* Description */}
          <p className="text-lg md:text-xl text-white/72 max-w-[660px] mx-auto mb-12 leading-relaxed animate-[fadeInUp_0.7s_ease-out_0.2s_both]">
            {t('nd.hero.desc') || 'ERP, mobil ilova, tibbiy tizim yoki maxsus platform — qanday murakkab bo\'lmasin, sifatli va o\'lchamli dasturlar yaratamiz.'}
          </p>

          {/* Stats Grid */}
          <div className="flex flex-wrap items-center justify-center gap-6 md:gap-0 mb-12 bg-white/5 border border-white/10 rounded-2xl p-7 max-w-4xl mx-auto animate-[fadeInUp_0.7s_ease-out_0.3s_both]">
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">20+</span>
              <span className="text-xs text-white/55 font-medium">{t('nd.hero.stat1.lbl') || 'Yaratilgan tizimlar'}</span>
            </div>
            <div className="hidden md:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">5+</span>
              <span className="text-xs text-white/55 font-medium">{t('nd.hero.stat2.lbl') || 'Soha tajribasi'}</span>
            </div>
            <div className="hidden md:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">100%</span>
              <span className="text-xs text-white/55 font-medium">{t('nd.hero.stat3.lbl') || 'Kodga egalik'}</span>
            </div>
            <div className="hidden md:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">NDA</span>
              <span className="text-xs text-white/55 font-medium">{t('nd.hero.stat4.lbl') || 'Maxfiylik kafolati'}</span>
            </div>
          </div>

          {/* CTAs */}
          <div className="flex flex-wrap gap-4 justify-center animate-[fadeInUp_0.7s_ease-out_0.4s_both]">
            <button
              className="inline-flex items-center gap-2 bg-gradient-to-r from-purple-600 to-violet-500 text-white font-bold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 shadow-lg shadow-purple-600/35 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-purple-600/40"
              onClick={() => { const el = document.getElementById('sp-contact'); if (el) el.scrollIntoView({ behavior: 'smooth' }); }}
            >
              {t('nd.hero.btn1') || 'Loyiha muhokamasi'} <ArrowRight />
            </button>
            <a
              href="https://t.me/ecode_uz" target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 backdrop-blur-md hover:bg-white/15 hover:-translate-y-0.5"
            >
              <MessageCircleHeart size={20} /> {t('nd.hero.btn2') || 'Bepul maslahat'}
            </a>
          </div>
        </div>
      </section>

      {/* Solutions Section */}
      <section className="py-24 max-w-[1400px] mx-auto">
        <div className="text-center mb-16">
          <div className="inline-block py-1 bg-purple-600/10 border border-purple-600/15 rounded-full text-xs font-bold text-purple-600 mb-4 uppercase tracking-wider">
            {t('nd.sol.tag') || 'Yechim turlari'}
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
            {t('nd.sol.title') || 'Qanday dasturlar yaratamiz?'}
          </h2>
          <p className="text-base text-slate-500 max-w-[560px] mx-auto">
            {t('nd.sol.desc') || 'Har bir sohaga maxsus yondashuv bilan'}
          </p>
        </div>

        {/* Tab Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Sidebar Tabs */}
          <div className="lg:col-span-4 flex flex-col gap-3">
            {solutionTypes.map((sol, idx) => (
              <button
                key={idx}
                className={`flex cursor-pointer items-center gap-4 p-5 rounded-2xl text-left border-l-4 transition-all duration-300 font-semibold bg-slate-5 hover:bg-slate-100/80 border-transparent ${activeType === idx ? `${sol.borderColor} ${sol.color} ${sol.bg}` : ''
                  }`}
                onClick={() => setActiveType(idx)}
              >
                <span className="text-xl">{sol.icon}</span>
                <span className="text-[15px]">{sol.title}</span>
              </button>
            ))}
          </div>

          {/* Active Tab Content */}
          <div className="lg:col-span-8 bg-white border border-slate-100 p-6 md:p-8 rounded-[32px] shadow-xl shadow-slate-100/70 animate-fadeIn" key={activeType}>
            <div className="flex items-center gap-4 pb-6 mb-6 border-b border-slate-100">
              <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl shadow-inner ${solutionTypes[activeType].bg} ${solutionTypes[activeType].color}`}>
                {solutionTypes[activeType].icon}
              </div>
              <h3 className="text-2xl font-black text-slate-900">
                {solutionTypes[activeType].title}
              </h3>
            </div>

            <p className="text-slate-500 text-[15px] leading-relaxed mb-8">
              {solutionTypes[activeType].desc}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 mb-8">
              {solutionTypes[activeType].features.map((f, i) => (
                <div key={i} className="flex items-center gap-3 text-sm font-medium text-slate-700">
                  <span className={`w-6 h-6 rounded-lg flex items-center justify-center p-1 ${solutionTypes[activeType].bg} ${solutionTypes[activeType].color}`}>
                    <CheckIcon />
                  </span>
                  <span>{f}</span>
                </div>
              ))}
            </div>

            <button
              className={`inline-flex cursor-pointer items-center justify-center gap-2 bg-gradient-to-r ${solutionTypes[activeType].gradient} text-white font-bold text-sm px-6 py-4 rounded-xl transition-all duration-300 hover:shadow-lg`}
              onClick={() => { const el = document.getElementById('sp-contact'); if (el) el.scrollIntoView({ behavior: 'smooth' }); }}
            >
              {t('nd.sol.discuss') || 'Muhokama qilish'} <ArrowRight />
            </button>
          </div>
        </div>
      </section>

      {/* Projects Showcase */}
      <section className="py-24 bg-gradient-to-b from-slate-50 to-white border-y border-black/[0.04]">
        <div className="max-w-[1400px] mx-auto">
          <div className="text-center mb-16">
            <div className="inline-block px-4 py-1 bg-blue-600/10 border border-blue-600/15 rounded-full text-xs font-bold text-blue-600 mb-4 uppercase tracking-wider">
              Portfolio
            </div>
            <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
              Muvaffaqiyatli loyihalar
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {projects.map((proj, i) => (
              <div key={i} className="bg-white border flex flex-col justify-between border-slate-100 p-8 rounded-3xl shadow-sm hover:shadow-md transition-shadow">
                <div>
                  <div className={`w-14 h-14 ${proj.bg} ${proj.color} rounded-2xl flex items-center justify-center text-2xl mb-5`}>
                    {proj.icon}
                  </div>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {proj.tags.map(tag => (
                      <span key={tag} className={`text-xs font-bold px-2.5 py-1 rounded-full border ${proj.color} ${proj.bg} ${proj.border}`}>
                        {tag}
                      </span>
                    ))}
                  </div>
                  <h3 className={`text-xl font-black mb-3 ${proj.color}`}>{proj.title}</h3>
                  <p className="text-slate-500 text-sm leading-relaxed mb-6">{proj.desc}</p>
                </div>
                <div className="flex flex-wrap gap-2 pt-4 border-t border-slate-50">
                  {proj.stats.map((s, si) => (
                    <span key={si} className="bg-slate-50 text-slate-600 text-xs font-bold px-3 py-1.5 rounded-full border border-slate-100">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Development Process */}
      <section className="py-24 max-w-[1400px] mx-auto">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-purple-600/10 border border-purple-600/15 rounded-full text-xs font-bold text-purple-600 mb-4 uppercase tracking-wider">
            Jarayon
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
            Professionallar metodologiyasi
          </h2>
          <p className="text-base text-slate-500 max-w-[560px] mx-auto">
            Agile yondashuv bilan sifatli va vaqtida yetkazib bermiz
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {devProcess.map((step, i) => (
            <div key={i} className="relative group flex flex-col justify-between bg-white border border-slate-100 p-6 rounded-3xl shadow-sm hover:shadow-md transition-all">
              <div>
                <div className="absolute top-4 right-6 text-4xl font-black text-slate-100 group-hover:text-purple-100/70 transition-colors pointer-events-none">
                  {step.num}
                </div>
                <div className="w-12 h-12 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-center text-xl mb-5 shadow-inner">
                  {step.icon}
                </div>
                <h3 className="text-base font-bold text-slate-800 mb-2">{step.title}</h3>
                <p className="text-slate-500 text-xs leading-relaxed mb-4">{step.desc}</p>
              </div>
              <div className="inline-flex w-max items-center gap-1.5 text-xs font-bold text-purple-600 bg-purple-50 px-2.5 py-1 rounded-md">
                <Clock size={16} /> {step.time}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Tech Stack */}
      <section className="py-24 bg-gradient-to-b from-slate-50 to-white border-y border-black/[0.04]">
        <div className="max-w-[1400px] mx-auto">
          <div className="text-center mb-16">
            <div className="inline-block px-4 py-1 bg-indigo-600/10 border border-indigo-600/15 rounded-full text-xs font-bold text-indigo-600 mb-4 uppercase tracking-wider">
              Texnologiyalar
            </div>
            <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
              Enterprise darajali texnologiyalar
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {techStack.map((cat, i) => (
              <div key={i} className="bg-white border border-slate-100 p-6 rounded-3xl shadow-sm">
                <h3 className="text-base font-black text-slate-800 mb-4 pb-2 border-b border-slate-50">
                  {cat.category}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {cat.techs.map((t, ti) => (
                    <span key={ti} className="bg-slate-50 border border-slate-200/60 text-slate-700 font-semibold text-xs px-3 py-1.5 rounded-xl shadow-sm">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why Us Section */}
      <section className="py-24 max-w-[1400px] mx-auto">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-emerald-600/10 border border-emerald-600/15 rounded-full text-xs font-bold text-emerald-600 mb-4 uppercase tracking-wider">
            Kafolatlar
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
            Nima uchun E-code LLC?
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            { icon: '🔐', title: t('nd.ndashart.t') || 'NDA Shartnoma', desc: t('nd.loyihava.d') || 'Loyiha va ma\'lumotlaringiz 100% maxfiy. Notarial tasdiqlangan NDA imzolaymiz.' },
            { icon: '📅', title: t('nd.vaqtkafo.t') || 'Vaqt kafolati', desc: t('nd.kelishil.d') || 'Kelishilgan muddatda yetkazamiz. Kechikish bo\'lsa — chegirma beramiz.' },
            { icon: '🧩', title: t('nd.kodegato.t') || 'Kodega to\'liq egalik', desc: t('nd.loyihatu.d') || 'Loyiha tugagach barcha kod, server va resurslar sizga o\'tadi.' },
            { icon: '🔧', title: t('nd.texnikqo.t') || 'Texnik qo\'llab-quvvatlash', desc: t('nd.xatobo.d') || 'Xato bo\'lsa 24 soat ichida tuzatamiz. Uzoq muddatli hamkorlik.' },
            { icon: '📈', title: t('nd.o.t') || 'O\'lchamli arxitektura', desc: t('nd.tizimo.d') || 'Tizim o\'sgan sari ishlaydi. 100 yoki 100,000 foydalanuvchi — farq qilmaydi.' },
            { icon: '💡', title: t('nd.qo.t') || 'Qo\'shimcha maslahat', desc: t('nd.faqatkod.d') || 'Faqat kod emas — biznes jarayonlarini yaxshilash bo\'yicha ham maslahatlashamiz.' },
          ].map((w, i) => (
            <div key={i} className="bg-white border border-black/5 p-8 rounded-3xl shadow-sm hover:shadow-md transition-shadow">
              <div className="w-12 h-12 bg-slate-50 rounded-xl flex items-center justify-center text-xl mb-5 border border-slate-100 shadow-sm">
                {w.icon}
              </div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">{w.title}</h3>
              <p className="text-slate-500 text-sm leading-relaxed">{w.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 max-w-[1400px] mx-auto px-4 mb-12" id="sp-contact">
        <div className="bg-gradient-to-br from-purple-950 via-violet-900 to-slate-900 text-white rounded-[32px] p-8 md:p-16 text-center relative overflow-hidden shadow-xl">
          <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />

          <div className="relative z-10 max-w-2xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-4">
              {t('nd.cta.title') || 'G\'oyangiz bormi? Gaplashamiz.'}
            </h2>
            <p className="text-white/80 text-base md:text-lg mb-10 leading-relaxed">
              {t('nd.cta.desc') || 'Bepul konsultatsiya va loyiha narxini aniqlash uchun bog\'laning. NDA imzolaymiz.'}
            </p>

            <div className="flex flex-wrap gap-4 justify-center">
              <a
                href="https://t.me/ecode_uz" target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-2 bg-white text-violet-950 font-bold text-base px-8 py-4 rounded-xl transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
              >
                <Send size={20} /> {t('nd.cta.btn1') || 'Telegram orqali bog\'lanish'} <ArrowRight />
              </a>
              <a
                href="mailto:ecode.uz@gmail.com"
                className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl transition-all duration-300 backdrop-blur-md hover:bg-white/20 hover:-translate-y-0.5"
              >
                <Mail size={20} /> {t('nd.cta.btn2') || 'Email yozish'}
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}