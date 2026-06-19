import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'
import { ArrowUpRight, ChartNoAxesColumn, ChartNoAxesCombined, Hamburger, Handshake, MonitorCheck, ChefHat, Box, Rocket, MessageCircleMore, Send } from 'lucide-react'

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const ArrowRight = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-[18px] h-[18px]">
    <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
  </svg>
)

export default function ChaqqonPro() {
  const navigate = useNavigate()
  const { t } = useLang()
  const [activeModule, setActiveModule] = useState(0)
  
  useSeo(
    "ChaqqonPro – Restoran va Kafe uchun POS Tizimi | E-code",
    "ChaqqonPro: restoran, kafe va mehmonxonalar uchun buyurtma boshqaruvi, oshxona ekrani, kuryer va moliya hisobi. O'zbekistonda eng qulay POS tizimi."
  )

  const modules = [
    {
      id: 'kassa',
      icon: <Hamburger size={28} />,
      color: '#f97316',
      textColor: 'text-orange-500',
      borderColor: 'border-orange-500',
      bg: 'bg-orange-500/10',
      title: t('cp.m1.t') || 'Tezkor Kassa',
      subtitle: t('cp.m1.s') || 'Ofitsiant va kassirlar uchun POS',
      desc: t('cp.m1.d') || 'Buyurtmani xatosiz va tez qabul qiling. Retseptli taomlar, kombinatsiyalar, stol va yetkazib berish (delivery) funksiyalari mavjud.',
      features: [
        t('cp.m1.f1') || 'Stollar xaritasi va band qilish',
        t('cp.m1.f2') || 'Oshxona printerlari bilan ishlash (tichets)',
        t('cp.m1.f3') || 'Olib ketish va Yetkazib berish (Delivery)',
        t('cp.m1.f4') || 'Chegirma va mijoz loyiqligi kartalari',
        t('cp.m1.f5') || 'Bir nechta to\'lov usullari (Naqd, Karta, Click/Payme)',
      ],
      stats: [{ val: t('cp.hero.stat1.val') || '2 soniya', label: t('cp.hero.stat1.lbl') || 'Buyurtma qabul' }, { val: 'Cheksiz', label: 'Stollar soni' }, { val: '100%', label: t('cp.hero.stat2.lbl') || 'Xatosizlik' }]
    },
    {
      id: 'oshxona',
      icon: <ChefHat size={28} />,
      color: '#ef4444',
      textColor: 'text-red-500',
      borderColor: 'border-red-500',
      bg: 'bg-red-500/10',
      title: t('cp.m2.t') || 'Oshxona Ekrani (KDS)',
      subtitle: t('cp.m2.s') || 'Kitchen Display System',
      desc: t('cp.m2.d') || 'Qog\'oz cheklarni unuting. Buyurtmalar ofitsiant qo\'shgan zahoti to\'g\'ridan to\'g\'ri oshxona ekranida paydo bo\'ladi.',
      features: [
        t('cp.m2.f1') || 'Sensor ekranlarga mos dizayn',
        t('cp.m2.f2') || 'Taom tayyorlanish jarayoni va holati (Kutilmoqda, Tayyorlanmoqda, Tayyor)',
        t('cp.m2.f3') || 'Gecikkan buyurtmalar uchun ogohlantirish (qizil rangda)',
        t('cp.m2.f4') || 'Ofitsiantga avtomatik bildirishnoma',
      ],
      stats: [{ val: '<5 soniya', label: 'Ma\'lumot o\'tishi' }, { val: '0', label: t('cp.hero.stat2.lbl') || 'Yo\'qolgan cheklar' }]
    },
    {
      id: 'ombor',
      icon: <Box size={28} />,
      color: '#10b981',
      textColor: 'text-emerald-500',
      borderColor: 'border-emerald-500',
      bg: 'bg-emerald-500/10',
      title: t('cp.m3.t') || 'Retsept va Skalad',
      subtitle: t('cp.m3.s') || 'Murakkab ombor va kalkulyatsiya',
      desc: t('cp.m3.d') || 'Sotilgan har bir porsiya taom uchun kerakli masalliqlar avtomatik ravishda ombordan hisobdan chiqariladi (kalkulyatsiya).',
      features: [
        t('cp.m3.f1') || 'Taomlar kalkulyatsiya xaritasi (Retseptlar)',
        t('cp.m3.f2') || 'Yarim tayyor (zakovetlar) mahsulotlar',
        t('cp.m3.f3') || 'Masalliqlar qoldig\'ini real-vaqtda nazorat qilish',
        t('cp.m3.f4') || 'Yaroqlilik muddati nazorati (Spisaniya)',
        t('cp.m3.f5') || 'Ta\'minotchilar bilan hisob-kitoblar',
      ],
      stats: [{ val: 'Avtomat', label: 'Spisaniya' }, { val: 'Gramm/Shtuk', label: 'Aniq o\'lchovlar' }]
    },
    {
      id: 'analitika',
      icon: <ChartNoAxesCombined size={28} />,
      color: '#8b5cf6',
      textColor: 'text-violet-500',
      borderColor: 'border-violet-500',
      bg: 'bg-violet-500/10',
      title: t('cp.m4.t') || 'Daromad va Analitika',
      subtitle: t('cp.m4.s') || 'Restoran ko\'rsatkichlari',
      desc: t('cp.m4.d') || 'Qaysi taom ko\'p sotilyapti? Qaysi ofitsiant yaxshi ishlayapti? Foyda / Zarar hisoboti to\'liq kaftingizda.',
      features: [
        t('cp.m4.f1') || 'ABC tahlili - eng daromadli taomlarni aniqlash',
        t('cp.m4.f2') || 'Soatbay tirbandlik tahlili (Peak hours)',
        t('cp.m4.f3') || 'Sof foyda (P&L) va kunlik kassa hisoboti',
        t('cp.m4.f4') || 'Ofitsiantlarning xizmat foizlarini (chayeviye)',
      ],
      stats: [{ val: 'Real-time', label: 'Statistika' }, { val: 'Excel/PDF', label: 'Eksport' }]
    }
  ]

  return (
    <LandingLayout>
      {/* Hero Section */}
      <section className="relative py-[100px] md:py-[120px] h-screen flex items-center overflow-hidden bg-gradient-to-br from-indigo-600 via-blue-800 to-indigo-600">
        <div className="inset-0 opacity-10 bg-[radial-gradient(rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:28px_28px] pointer-events-none" />
        <div className="container max-w-[1400px] mx-auto px-4 relative z-10 text-center">
          <div className="inline-flex items-center gap-2 upper text-sm text-white/50 mb-6 font-medium">
            <span onClick={() => navigate('/')} className="cursor-pointer hover:opacity-100 opacity-60 transition-opacity">{t('cp.bc.home') || 'Bosh sahifa'}</span>
            <span className="opacity-60">›</span>
            <span>{'Eviko'}</span>
          </div>
          
          <div className="inline-block ml-4 px-5 py-2 border rounded-full text-sm font-bold mb-8 bg-blue-500/30 text-blue-200 border-blue-500/40 animate-fade-in" dangerouslySetInnerHTML={{ __html: t('cp.tag') || '🍽️ &nbsp;Restoran / Kafe POS' }} />
          
          <h1 className="text-[44px] md:text-[72px] font-black leading-[1.08] tracking-tight text-white mb-5">
            {t('cp.hero.title1') || 'Restoran biznesingizni'}<br />
            <span className="bg-gradient-to-r from-amber-400 to-orange-500 bg-clip-text uppercase text-transparent inline-block">{t('cp.hero.title2')}</span> {t('cp.hero.title3')}
          </h1>
          
          <p className="text-lg md:text-19px text-white/70 max-w-[660px] mx-auto mb-10 className-relaxed">
            {t('cp.hero.desc') || 'Restoran, kafe, fast-food va oshxonalar uchun tezkor...'}
          </p>
          
          <div className="flex items-center w-max mx-auto justify-center bg-white/5 border border-white/10 rounded-[20px] p-7 md:p-8 mb-12 flex-wrap gap-5">
            <div className="flex flex-col items-center gap-1 px-7">
              <span className="text-3xl font-black text-white tracking-tight">{t('cp.hero.stat1.val') || 'Tez'}</span>
              <span className="text-xs text-white/50 font-medium">{t('cp.hero.stat1.lbl') || 'Xizmat ko\'rsatish'}</span>
            </div>
            <div className="hidden md:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7">
              <span className="text-3xl font-black text-white tracking-tight">{t('cp.hero.stat2.val') || '0'}</span>
              <span className="text-xs text-white/50 font-medium">{t('cp.hero.stat2.lbl') || 'Xatolik'}</span>
            </div>
            <div className="hidden md:block w-[1px] h-10 bg-white/10" />
            <div className="flex flex-col items-center gap-1 px-7">
              <span className="text-3xl font-black text-white tracking-tight">{t('cp.hero.stat3.val') || 'To\'liq'}</span>
              <span className="text-xs text-white/50 font-medium">{t('cp.hero.stat3.lbl') || 'Kalkulyatsiya'}</span>
            </div>
          </div>
          
          <div className="flex gap-4 justify-center flex-wrap">
            <button 
              className="inline-flex items-center gap-2 bg-white text-blue-700 font-bold text-base py-4 px-8 rounded-e-xl cursor-pointer border border-blue-700 hover:-translate-y-[3px] hover:scale-[1.02] transition-all duration-300 rounded-xl"
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/login'}
            >
              {t('cp.hero.btn1') || 'Tizimni sinab ko\'rish'} <ArrowRight />
            </button>
            <button 
              className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base py-4 px-8 rounded-xl cursor-pointer backdrop-blur-md hover:bg-white/15 hover:-translate-y-0.5 transition-all duration-300"
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
            >
              {t('cp.hero.btn2') || 'Narxlarni bilish'}
            </button>
          </div>
        </div>
      </section>

      {/* Portals Section */}
      <section className="bg-white py-[60px] border-b border-pink-100">
        <div className="container mx-auto px-4">
          <div className="text-center mb-10">
            <h2 className="text-3xl font-extrabold text-slate-800 mb-4">{t('cp.portals.title') || 'Tizimga Kirish Portallari'}</h2>
            <p className="text-slate-500 max-w-2xl mx-auto">{t('cp.portals.desc') || 'Huddi bir yaxlit ekotizimdek — har kim o\'zining ishchi o\'rniga ega!'}</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* Biznes Egasi */}
            <div 
              className="bg-slate-50 p-6 rounded-2xl border border-slate-200 cursor-pointer transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/?mode=admin'}
            >
               <div className="text-4xl flex items-start justify-between mb-4 text-green-700">
                <ChartNoAxesCombined size={52} />
                <ArrowUpRight size={30} />
               </div>
               <h3 className="text-xl font-bold text-slate-800 mb-2">{t('cp.portals.p1.title') || 'Biznes Egasi (Admin)'}</h3>
               <p className="text-slate-500 text-sm leading-relaxed">{t('cp.portals.p1.desc') || 'Restoran adminstratori, ombor hisob-kitobi va moliyaviy tahlil'}</p>
            </div>

            {/* Kassir / Ofitsiant */}
            <div
              className="bg-slate-50 p-6 rounded-2xl border border-slate-200 cursor-pointer transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/kassa/login'}
            >
               <div className="text-4xl flex items-start justify-between mb-4 text-blue-600">
                <MonitorCheck size={52} />
                <ArrowUpRight size={30} />
               </div>
               <h3 className="text-xl font-bold text-slate-800 mb-2">{t('cp.portals.p2.title') || 'Kassa / POS'}</h3>
               <p className="text-slate-500 text-sm leading-relaxed">{t('cp.portals.p2.desc') || 'Kassirlar savdosi xaritasi, Ofitsiantlar va KDS oshxona ekrani'}</p>
            </div>

            {/* Agent Portali */}
            <div 
              className="bg-slate-50 p-6 rounded-2xl border border-slate-200 cursor-pointer transition-all duration-300 hover:shadow-lg hover:-translate-y-1"
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/agent-portal'}
            >
               <div className="text-4xl flex items-start justify-between mb-4 text-yellow-500">
                <Handshake size={52} />
                <ArrowUpRight size={30} />
               </div>
               <h3 className="text-xl font-bold text-slate-800 mb-2">{t('cp.portals.p4.title') || 'Agent Portali'}</h3>
               <p className="text-slate-500 text-sm leading-relaxed">{t('cp.portals.p4.desc') || 'Restoranlarni tizimga ulovchi yordamchi kadrlar / franshiza xonasi'}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Modules Section */}
      <section className="py-[100px] bg-slate-50" id="modullar">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <div className="inline-block text-orange-600 bg-orange-600/10 font-bold px-4 py-1.5 rounded-full text-sm mb-3">{t('cp.mod.tag') || 'Maxsus Modullar'}</div>
            <h2 className="text-3xl md:text-4xl font-black text-slate-800 mb-4">{t('cp.mod.title') || 'Ovqatlanish sohasi uchun barcha yechimlar'}</h2>
            <p className="text-slate-500 max-w-xl mx-auto">{t('cp.mod.desc') || 'Faqat POS emas, balki butun biznesingiz yuragini boshqaring.'}</p>
          </div>

          <div className="flex flex-col lg:flex-row gap-8 items-start">
            {/* Sidebar Tabs */}
            <div className="w-full lg:w-1/3 flex flex-col gap-3">
              {modules.map((mod, idx) => (
                <button
                  key={mod.id}
                  className={`flex cursor-pointer items-center text-left gap-4 p-5 rounded-xl border bg-white transition-all duration-200 group ${
                    activeModule === idx 
                      ? `border-l-4 ${mod.borderColor} ${mod.textColor} ${mod.bg} font-semibold shadow-sm` 
                      : 'hover:bg-slate-100 text-slate-700 border-slate-200'
                  }`}
                  onClick={() => setActiveModule(idx)}
                >
                  <span className="text-2xl">{mod.icon}</span>
                  <div>
                    <div className="font-bold text-base">{mod.title}</div>
                    <div className="text-xs mt-0.5">{mod.subtitle}</div>
                  </div>
                </button>
              ))}
            </div>

            {/* Content Display */}
            <div className="w-full lg:w-2/3 bg-white p-6 md:p-8 rounded-2xl border border-slate-200 shadow-sm" key={activeModule}>
              <div 
                className="flex items-center gap-4 pb-6 mb-6 border-b border-slate-100 border-t-4 pt-4"
                style={{ borderTopColor: modules[activeModule].color }}
              >
                <div 
                  className={`text-3xl w-14 h-14 rounded-xl flex items-center justify-center ${modules[activeModule].bg} ${modules[activeModule].textColor}`}
                >
                  {modules[activeModule].icon}
                </div>
                <div>
                  <h3 className="text-xl font-bold text-slate-800">{modules[activeModule].title}</h3>
                  <p className="text-sm text-slate-400">{modules[activeModule].subtitle}</p>
                </div>
              </div>
              
              <p className="text-slate-600 leading-relaxed mb-8">{modules[activeModule].desc}</p>

              {/* Module Stats */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
                {modules[activeModule].stats.map((s, i) => (
                  <div 
                    key={i} 
                    className="p-4 bg-slate-50 rounded-xl border-t-4 border-slate-200"
                    style={{ borderTopColor: modules[activeModule].color }}
                  >
                    <span className={`block text-xl font-black mb-1 ${modules[activeModule].textColor}`}>{s.val}</span>
                    <span className="text-xs font-medium text-slate-500">{s.label}</span>
                  </div>
                ))}
              </div>

              {/* Features List */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {modules[activeModule].features.map((f, i) => (
                  <div key={i} className="flex items-start gap-3 text-slate-700 text-sm">
                    <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5 ${modules[activeModule].bg} ${modules[activeModule].textColor}`}>
                      <CheckIcon />
                    </span>
                    <span className="leading-tight">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA / Contact Section */}
      <section className="py-[120px] bg-gradient-to-br from-blue-700 to-blue-800 relative overflow-hidden" id="sp-contact">
        {/* Background effects */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:28px_28px] pointer-events-none" />
        <div className="absolute top-[-100px] left-[10%] w-[400px] h-[400px] rounded-full bg-[radial-gradient(circle,rgba(234,88,12,0.2)_0%,transparent_70%)] blur-[60px] pointer-events-none" />
        <div className="absolute bottom-[-80px] right-[10%] w-[350px] h-[350px] rounded-full bg-[radial-gradient(circle,rgba(251,146,60,0.15)_0%,transparent_70%)] blur-[60px] pointer-events-none" />

        <div className="container mx-auto px-4 relative z-10">
          <div className="text-center max-w-[700px] mx-auto">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-orange-600/15 border border-orange-600/30 rounded-full px-5 py-2 mb-8">
              <span className="w-2 h-2 rounded-full bg-orange-600 inline-block" />
              <span className="text-orange-400 text-sm font-bold">Bepul sinab ko'ring</span>
            </div>

            <h2 className="text-[36px] sm:text-[5vw] md:text-[56px] font-black text-white tracking-tight mb-5 leading-[1.1]">
              EVIKO ga ulanishga{' '}
              <span className="bg-gradient-to-br from-orange-400 to-orange-600 bg-clip-text text-transparent">tayyormisiz?</span>
            </h2>

            <p className="text-lg text-white/65 mb-12 leading-relaxed">
              {t('cp.cta.desc') || "Restoraningiz hajmidan qat'iy nazar, yordam beramiz."}
            </p>

            {/* Stats row */}
            <div className="flex justify-center gap-10 mb-12 flex-wrap">
              {[
                ['5 daqiqa', "Sozlash vaqti"], 
                ['24/7', 'Texnik yordam'], 
                ['14 kun', 'Bepul sinov']
              ].map(([val, lbl]) => (
                <div key={lbl} className="text-center">
                  <div className="text-3xl font-black text-orange-400 tracking-tight">{val}</div>
                  <div className="text-xs text-white/50 font-semibold mt-1">{lbl}</div>
                </div>
              ))}
            </div>

            {/* CTA Buttons */}
            <div className="flex gap-4 justify-center flex-wrap">
              <a 
                href="https://t.me/ecode_uz" 
                target="_blank" 
                rel="noreferrer"
                className="inline-flex items-center gap-2.5 bg-gradient-to-br from-orange-600 to-orange-400 text-white font-bold text-base py-4 px-9 rounded-xl shadow-[0_10px_30px_rgba(234,88,12,0.4)] hover:-translate-y-0.5 transition-all duration-300 text-decoration-none"
              >
                <Send size={20} /> {t('cp.cta.btn') || "Biz bilan bog'lanish"}
              </a>
              <a 
                href="https://chaqqonpro.e-code.uz" 
                target="_blank" 
                rel="noreferrer"
                className="inline-flex items-center gap-2.5 bg-white/5 text-white border border-white/15 font-semibold text-base py-4 px-9 rounded-xl backdrop-blur-md hover:bg-white/10 hover:-translate-y-0.5 transition-all duration-300 text-decoration-none"
              >
                <Rocket size={20} /> Tizimga kirish
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}