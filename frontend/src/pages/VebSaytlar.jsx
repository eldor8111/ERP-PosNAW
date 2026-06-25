import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'
import { MessageCircleHeart, Phone, Send } from 'lucide-react'

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
export default function VebSaytlar() {
  const navigate = useNavigate()
  const { t } = useLang()
  
  useSeo(
    "Veb Sayt Yaratish – Professional Dizayn va Ishlab Chiqish | E-code",
    "E-code: biznes uchun zamonaviy veb saytlar yaratish. Landing page, korporativ sayt, onlayn do'kon. O'zbekistondagi professional veb dizayn studiyasi."
  )

  const services = [
    {
      icon: '🏢',
      color: '#2563eb',
      bg: 'rgba(37,99,235,0.08)',
      // Tailwind uchun dinamik rang sinflari:
      borderColor: 'hover:border-blue-600/30 shadow-blue-600/10',
      textColor: 'text-blue-600',
      btnBg: 'from-blue-600 to-blue-500',
      title: t('web.korporat.t') || 'Korporativ Saytlar',
      desc: t('web.kompaniy.d') || 'Kompaniyangizni professional taqdim eting. Brendingizni aks ettiruvchi zamonaviy dizayn.',
      features: ['Brend identifikatsiya', 'Ko\'p tilli sahifalar', 'SEO optimallashtirish', 'Admin panel', 'Tez yuklash tezligi'],
      price: '3,000,000 so\'mdan',
    },
    {
      icon: '🛒',
      color: '#10b981',
      borderColor: 'hover:border-emerald-500/30 shadow-emerald-500/10',
      textColor: 'text-emerald-500',
      btnBg: 'from-emerald-500 to-emerald-400',
      bg: 'rgba(16,185,129,0.08)',
      title: t('web.ecommerc.t') || 'E-Commerce Do\'konlar',
      desc: t('web.to.d') || 'To\'liq onlayn savdo tizimi. To\'lov integratsiyasi, buyurtma boshqaruvi va inventar nazorati.',
      features: ['Mahsulotlar katalogi', 'Online to\'lov', 'Buyurtma kuzatuvi', 'Mobil moslashuvchan', 'Payme/Click integratsiya'],
      price: '7,000,000 so\'mdan',
    },
    {
      icon: '🎨',
      color: '#8b5cf6',
      borderColor: 'hover:border-violet-500/30 shadow-violet-500/10',
      textColor: 'text-violet-500',
      btnBg: 'from-violet-500 to-violet-400',
      bg: 'rgba(139,92,246,0.08)',
      title: t('web.muallifl.t') || 'Mualliflik Loyihalari',
      desc: t('web.portfoli.d') || 'Portfolio, blog, shaxsiy brend yoki ijodiy loyihalar uchun noyob dizayn va funksionallik.',
      features: ['Noyob dizayn konsepsiya', 'Animatsiyalar', 'Blog tizimi', 'Ko\'p media format', 'Ijtimoiy tarmoq integratsiya'],
      price: '2,000,000 so\'mdan',
    },
    {
      icon: '💻',
      color: '#f59e0b',
      borderColor: 'hover:border-amber-500/30 shadow-amber-500/10',
      textColor: 'text-amber-500',
      btnBg: 'from-amber-500 to-amber-400',
      bg: 'rgba(245,158,11,0.08)',
      title: t('web.landingp.t') || 'Landing Page',
      desc: t('web.xizmatyo.d') || 'Xizmat yoki mahsulotni sotish uchun maxsus bir sahifali sayt. Konversiya uchun optimallashtirilgan.',
      features: ['Konversiya optimallashtirish', 'A/B testing', 'Lead capture forma', 'Analytics integratsiya', 'Tez yetkazib berish'],
      price: '1,500,000 so\'mdan',
    },
    {
      icon: '⚙️',
      color: '#0891b2',
      borderColor: 'hover:border-cyan-600/30 shadow-cyan-600/10',
      textColor: 'text-cyan-600',
      btnBg: 'from-cyan-600 to-cyan-500',
      bg: 'rgba(8,145,178,0.08)',
      title: t('web.vebilova.t') || 'Veb Ilovalar',
      desc: t('web.murakkab.d') || 'Murakkab biznes logikali veb ilovalar. SaaS, dashboard va boshqaruv tizimlar.',
      features: ['React / Next.js', 'REST API yoki GraphQL', 'Real-vaqt ma\'lumot', 'Autentifikatsiya tizimi', 'Cloud deployment'],
      price: '10,000,000 so\'mdan',
    },
    {
      icon: '🔧',
      color: '#ef4444',
      borderColor: 'hover:border-red-500/30 shadow-red-500/10',
      textColor: 'text-red-500',
      btnBg: 'from-red-500 to-red-400',
      bg: 'rgba(239,68,68,0.08)',
      title: t('web.texnikqo.t') || 'Texnik Qo\'llab-Quvvatlash',
      desc: t('web.mavjudsa.d') || 'Mavjud saytingizni yangilash, xatolarni tuzatish, tezligini oshirish va xavfsizligini ta\'minlash.',
      features: ['Sayt tezligini oshirish', 'Xavfsizlik tekshiruvi', 'Server sozlamalari', 'Backup tizimi', 'SSL sertifikat'],
      price: '500,000 so\'mdan/oy',
    },
  ]

  const process = [
    { step: '01', icon: '💬', title: t('web.murojaat.t') || 'Murojaat', desc: t('web.telegram.d') || 'Telegram yoki telefon orqali bog\'laning. Loyiha haqida batafsil suhbatlashtiren.' },
    { step: '02', icon: '📋', title: t('web.tahliltz.t') || 'Tahlil & TZ', desc: t('web.biznesta.d') || 'Biznes talablarini tahlil qilamiz va texnik topshiriq (TZ) tayyorlaymiz.' },
    { step: '03', icon: '🎨', title: t('web.dizayn.t') || 'Dizayn', desc: t('web.figma.d') || 'Figma\'da professional dizayn yaratamiz va tasdiqlash uchun taqdim etamiz.' },
    { step: '04', icon: '💻', title: t('web.ishlabch.t') || 'Ishlab chiqish', desc: t('web.zamonavi.d') || 'Zamonaviy texnologiyalarda saytni kod qilamiz, test qilamiz.' },
    { step: '05', icon: '🚀', title: t('web.yetkazib.t') || 'Yetkazib berish', desc: t('web.saytnise.d') || 'Saytni serverga joylashtiramiz, domen ulaymiiz va topshiramiz.' },
    { step: '06', icon: '🛡️', title: t('web.qo.t') || 'Qo\'llab-quvvatlash', desc: t('web.1oylikbe.d') || '1 oylik bepul qo\'llab-quvvatlash va keyingi yangilanishlar.' },
  ]

  const techStack = [
    { name: 'React', icon: 'https://img.icons8.com/?size=100&id=bzf0DqjXFHIW&format=png&color=000000', desc: t('web.frontend.d') || 'Frontend' },
    { name: 'Next.js', icon: 'https://img.icons8.com/?size=100&id=MWiBjkuHeMVq&format=png&color=000000', desc: t('web.ssrssg.d') || 'SSR/SSG' },
    { name: 'Node.js', icon: 'https://img.icons8.com/?size=100&id=54087&format=png&color=000000', desc: t('web.backend.d') || 'Backend' },
    { name: 'PostgreSQL', icon: 'https://img.icons8.com/?size=100&id=JRnxU7ZWP4mi&format=png&color=000000', desc: t('web.database.d') || 'Database' },
    { name: 'Python/Django', icon: 'https://img.icons8.com/?size=100&id=13441&format=png&color=000000', desc: t('web.server.d') || 'Backend' },
    { name: 'Docker', icon: 'https://img.icons8.com/?size=100&id=22813&format=png&color=000000', desc: t('web.devops.d') || 'DevOps' },
    { name: 'Figma', icon: 'https://img.icons8.com/?size=100&id=zfHRZ6i1Wg0U&format=png&color=000000', desc: t('web.dizayn.d') || 'Dizayn' },
    { name: 'AWS/VPS', icon: 'https://img.icons8.com/?size=100&id=33039&format=png&color=000000', desc: t('web.hosting.d') || 'Hosting' },
  ]

  return (
    <LandingLayout>
      {/* Hero Section */}
      <section className="relative py-24 md:py-32 overflow-hidden min-h-[620px] flex items-center bg-gradient-to-br from-[#0f172a] via-[#1e1b4b] to-[#0f172a]">
        {/* Background Dots */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.08)_1px,transparent_1px)] bg-[size:28px_28px] pointer-events-none" />
        
        <div className="max-w-[1400px] mx-auto px-4 w-full relative z-10 text-center">
          {/* Breadcrumb */}
          <div className="inline-flex items-center gap-2 text-sm text-white/50 mb-6 font-medium">
            <span onClick={() => navigate('/')} className="cursor-pointer hover:opacity-100 opacity-60 transition-opacity">{t('web.bc.home') || 'Bosh sahifa'}</span>
            <span className="opacity-60">›</span>
            <span>{t('web.bc.current') || 'Maxsus Veb-saytlar'}</span>
          </div>
          
          {/* Badge Tag */}
          <div 
            className="inline-block px-5 py-2 ml-3 bg-violet-500/30 text-violet-300 border border-violet-500/40 rounded-full text-sm font-bold mb-8 animate-fadeInUp"
            dangerouslySetInnerHTML={{ __html: t('web.tag') || '🌐 &nbsp;Professional Veb Ishlab Chiqish' }} 
          />
          
          {/* Main Title */}
          <h1 className="text-[clamp(44px,7vw,72px)] font-black leading-[1.08] tracking-tight text-white mb-7 animate-[fadeInUp_0.7s_ease-out_0.1s_both]">
            {t('web.hero.title1') || 'Sizning g\'oyangizni'}<br />
            <span className="bg-gradient-to-r from-violet-300 to-indigo-400 bg-clip-text text-transparent inline-block">
              {t('web.hero.title2') || 'veb reallikka'}
            </span> {t('web.hero.title3') || 'aylantiramiz'}
          </h1>
          
          {/* Description */}
          <p className="text-lg md:text-xl text-white/70 max-w-[660px] mx-auto mb-12 leading-relaxed animate-[fadeInUp_0.7s_ease-out_0.2s_both]">
            {t('web.hero.desc') || 'Korporativ saytlardan tortib, murakkab e-commerce platformalarigacha — zamonaviy texnologiyalar va premium dizayn bilan quramiz.'}
          </p>
          
          {/* Stats Grid */}
          <div className="flex flex-wrap items-center justify-center gap-6 lg:gap-0 mb-12 bg-white/5 border border-white/10 rounded-2xl p-7 max-w-4xl mx-auto animate-[fadeInUp_0.7s_ease-out_0.3s_both]">
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">50+</span>
              <span className="text-xs text-white/55 font-medium">{t('web.hero.stat1.lbl') || 'Yaratilgan saytlar'}</span>
            </div>
            <div className="hidden lg:block w-[1px] height h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">3 yil</span>
              <span className="text-xs text-white/55 font-medium">{t('web.hero.stat2.lbl') || 'Tajriba'}</span>
            </div>
            <div className="hidden lg:block w-[1px] height h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">100%</span>
              <span className="text-xs text-white/55 font-medium">{t('web.hero.stat3.lbl') || 'Mijoz mamnuniyati'}</span>
            </div>
            <div className="hidden lg:block w-[1px] height h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7 flex-1 min-w-[150px]">
              <span className="text-3xl font-black text-white tracking-tight">2-4 hafta</span>
              <span className="text-xs text-white/55 font-medium">{t('web.hero.stat4.lbl') || 'O\'rtacha vaqt'}</span>
            </div>
          </div>
          
          {/* Hero CTAs */}
          <div className="flex flex-wrap gap-4 justify-center animate-[fadeInUp_0.7s_ease-out_0.4s_both]">
            <button 
              className="inline-flex items-center gap-2 bg-gradient-to-r from-violet-600 to-violet-500 text-white font-bold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 shadow-lg shadow-violet-600/35 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-violet-600/40"
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
            >
              {t('web.hero.btn1') || 'Loyiha boshlash'} <ArrowRight />
            </button>
            <a 
              href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" 
              className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 backdrop-blur-md hover:bg-white/15 hover:-translate-y-0.5"
            >
              <MessageCircleHeart size={20} /> {t('web.hero.btn2') || 'Maslahat olish'}
            </a>
          </div>
        </div>
      </section>

      {/* Services Grid Section */}
      <section className="py-24 max-w-[1400px] mx-auto px-4">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-blue-600/10 border border-blue-600/15 rounded-full text-xs font-bold text-blue-600 mb-4 uppercase tracking-wider">
            {t('web.svc.tag') || 'Xizmatlar'}
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
            {t('web.svc.title') || 'Qanday saytlar yaratamiz?'}
          </h2>
          <p className="text-base text-slate-500 max-w-[560px] mx-auto">
            {t('web.svc.desc') || 'Har xil biznes uchun moslashtirilgan veb yechimlar'}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {services.map((svc, idx) => (
            <div
              key={idx}
              className={`flex flex-col bg-white border border-black/5 p-8 rounded-3xl cursor-pointer transition-all duration-300 shadow-sm group ${svc.borderColor}`}
            >
              <div 
                className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl mb-6 transition-all duration-300"
                style={{ color: svc.color, backgroundColor: svc.bg }}
              >
                {svc.icon}
              </div>
              <h3 className="text-xl font-bold text-slate-800 mb-3">{svc.title}</h3>
              <p className="text-slate-500 text-[15px] leading-relaxed mb-6 flex-1">{svc.desc}</p>
              <div className={`text-lg font-black ${svc.textColor} mb-2`}>{svc.price}</div>
              
              {/* Expandable Features Area */}
              <div className={`grid transition-all duration-300 ease-in-out`}>
                <div className="overflow-hidden border-t border-slate-100 pt-4">
                  <div className="flex flex-col gap-2.5 mb-6">
                    {svc.features.map((f, i) => (
                      <div key={i} className="flex items-center gap-3 text-sm font-medium text-slate-700">
                        <span style={{ color: svc.color }}><CheckIcon /></span> {f}
                      </div>
                    ))}
                  </div>
                  <button
                    className={`w-full animate-pulse cursor-pointer inline-flex items-center justify-center gap-2 bg-gradient-to-r ${svc.btnBg} text-white font-bold text-sm py-3.5 rounded-xl transition-all duration-300 hover:shadow-md`}
                    onClick={e => { 
                      e.stopPropagation(); 
                      const el = document.getElementById('sp-contact'); 
                      if(el) el.scrollIntoView({behavior:'smooth'}); 
                    }}
                  >
                    {t('web.svc.order') || 'Buyurtma berish'} <ArrowRight />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Process Section */}
      <section className="py-24 bg-gradient-to-b from-slate-50 to-white border-y border-black/[0.04]">
        <div className="max-w-[1400px] mx-auto px-4">
          <div className="text-center mb-16">
            <div className="inline-block px-4 py-1 bg-violet-600/10 border border-violet-600/15 rounded-full text-xs font-bold text-violet-600 mb-4 uppercase tracking-wider">
              {t('web.proc.tag') || 'Jarayon'}
            </div>
            <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
              {t('web.proc.title') || 'Qanday ishlaymiz?'}
            </h2>
            <p className="text-base text-slate-500 max-w-[560px] mx-auto">
              {t('web.proc.desc') || '6 bosqichli samarali ishlab chiqish jarayoni'}
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {process.map((step, idx) => (
              <div key={idx} className="relative bg-white border border-black/5 p-8 rounded-3xl shadow-sm hover:shadow-md transition-shadow group">
                <div className="absolute top-4 right-6 text-4xl font-black text-slate-100 group-hover:text-violet-50 transition-colors">
                  {step.step}
                </div>
                <div className="w-12 h-12 bg-slate-50 rounded-xl flex items-center justify-center text-xl mb-5 shadow-sm border border-black/[0.02]">
                  {step.icon}
                </div>
                <h3 className="text-lg font-bold text-slate-800 mb-2">{step.title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech Stack Section */}
      <section className="py-24 max-w-[1400px] mx-auto px-4">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-cyan-600/10 border border-cyan-600/15 rounded-full text-xs font-bold text-cyan-600 mb-4 uppercase tracking-wider">
            Texnologiyalar
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
            Zamonaviy va ishonchli stack
          </h2>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {techStack.map((tech, idx) => (
            <div key={idx} className="flex flex-col items-center text-center p-6 bg-slate-50/50 border border-black/[0.03] rounded-2xl hover:bg-white hover:shadow-md hover:border-black/5 transition-all">
              <div className="w-18 h-18 p-2 bg-white rounded-xl flex items-center justify-center text-xl mb-3 shadow-sm">
                <img src={tech.icon} className='w-full' alt={tech.name} />
              </div>
              <div className="font-bold text-slate-800 text-base">{tech.name}</div>
              <div className="text-xs text-slate-400 font-medium mt-0.5">{tech.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 max-w-[1400px] mx-auto px-4 mb-12" id="sp-contact">
        <div className="bg-gradient-to-br from-indigo-900 via-purple-900 to-slate-900 text-white rounded-[32px] p-8 md:p-16 text-center relative overflow-hidden shadow-xl">
          <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />
          
          <div className="relative z-10 max-w-2xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-4">
              {t('web.cta.title') || 'Loyiha haqida gaplashaylik'}
            </h2>
            <p className="text-white/80 text-base md:text-lg mb-10 leading-relaxed">
              {t('web.cta.desc') || 'Telegram orqali yozing yoki so\'rov qoldiring — 24 soat ichida javob beramiz.'}
            </p>
            
            <div className="flex flex-wrap gap-4 justify-center">
              <a 
                href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" 
                className="inline-flex items-center gap-2 bg-white text-indigo-950 font-bold text-base px-8 py-4 rounded-xl transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
              >
                <Send size={20} /> {t('web.cta.btn1') || 'Telegram yozish'} <ArrowRight />
              </a>
              <a 
                href="tel:+998889118171" 
                className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl transition-all duration-300 backdrop-blur-md hover:bg-white/20 hover:-translate-y-0.5"
              >
                <Phone size={20} /> {t('web.cta.btn2') || 'Qo\'ng\'iroq qilish'}
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}