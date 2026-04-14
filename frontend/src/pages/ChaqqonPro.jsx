import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import './service-pages.css'

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="sp-check-svg">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const ArrowRight = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: 18, height: 18 }}>
    <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
  </svg>
)

// We will move this inside the component to use the t() function.

import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'

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
      icon: '🍔',
      color: '#f97316',
      bg: 'rgba(249,115,22,0.08)',
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
      icon: '👨‍🍳',
      color: '#ef4444',
      bg: 'rgba(239,68,68,0.08)',
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
      icon: '📦',
      color: '#10b981',
      bg: 'rgba(16,185,129,0.08)',
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
      icon: '📈',
      color: '#8b5cf6',
      bg: 'rgba(139,92,246,0.08)',
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
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #431407 0%, #7c2d12 50%, #431407 100%)' }}>
        <div className="sp-hero-bg-dots" style={{ opacity: 0.1 }} />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>{t('cp.bc.home') || 'Bosh sahifa'}</span>
            <span className="sp-bc-sep">›</span>
            <span>{t('cp.bc.current') || 'Chaqqon Pro'}</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(249,115,22,0.3)', color: '#fdba74', borderColor: 'rgba(249,115,22,0.4)' }} dangerouslySetInnerHTML={{ __html: t('cp.tag') || '🍽️ &nbsp;Restoran / Kafe POS' }} />
          <h1 className="sp-hero-title">
            {t('cp.hero.title1') || 'Ovqatlanish biznesingizni'}<br />
            <span className="sp-gradient-text" style={{ background: 'linear-gradient(to right, #fbbf24, #f97316)', WebkitBackgroundClip: 'text', color: 'transparent' }}>{t('cp.hero.title2') || 'Chaqqon'}</span> {t('cp.hero.title3') || 'boshqaring'}
          </h1>
          <p className="sp-hero-desc">
            {t('cp.hero.desc') || 'Restoran, kafe, fast-food va oshxonalar uchun tezkor...'}
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">{t('cp.hero.stat1.val') || 'Tez'}</span><span className="sp-stat-lbl">{t('cp.hero.stat1.lbl') || 'Xizmat ko\'rsatish'}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('cp.hero.stat2.val') || '0'}</span><span className="sp-stat-lbl">{t('cp.hero.stat2.lbl') || 'Xatolik'}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('cp.hero.stat3.val') || 'To\'liq'}</span><span className="sp-stat-lbl">{t('cp.hero.stat3.lbl') || 'Kalkulyatsiya'}</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" style={{ background: 'linear-gradient(135deg, #ea580c, #c2410c)', borderColor: '#c2410c' }} onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/login'}>
              {t('cp.hero.btn1') || 'Tizimni sinab ko\'rish'} <ArrowRight />
            </button>
            <button className="sp-btn-ghost" onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              {t('cp.hero.btn2') || 'Narxlarni bilish'}
            </button>
          </div>
        </div>
      </section>
      <section className="sp-portals-section" style={{ background: '#fff', padding: '60px 0', borderBottom: '1px solid #fce7f3' }}>
        <div className="ent-container">
          <div className="sp-section-head" style={{ textAlign: 'center', marginBottom: '40px' }}>
            <h2 className="sp-section-title" style={{ fontSize: '32px', marginBottom: '16px' }}>{t('cp.portals.title') || 'Tizimga Kirish Portallari'}</h2>
            <p className="sp-section-desc">{t('cp.portals.desc') || 'Huddi bir yaxlit ekotizimdek — har kim o\'zining ishchi o\'rniga ega!'}</p>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
            {/* Biznes Egasi */}
            <div 
              style={{ background: '#f8fafc', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0', cursor: 'pointer', transition: 'all 0.3s ease' }}
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/'}
            >
               <div style={{ fontSize: '36px', marginBottom: '16px' }}>📊</div>
               <h3 style={{ fontSize: '20px', fontWeight: 'bold', color: '#1e293b', marginBottom: '8px' }}>{t('cp.portals.p1.title') || 'Biznes Egasi (Admin)'}</h3>
               <p style={{ color: '#64748b', fontSize: '14px', lineHeight: '1.5' }}>{t('cp.portals.p1.desc') || 'Restoran adminstratori, ombor hisob-kitobi va moliyaviy tahlil'}</p>
            </div>

            {/* Kassir / Ofitsiant */}
            <div
              style={{ background: '#f8fafc', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0', cursor: 'pointer', transition: 'all 0.3s ease' }}
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/kassa/login'}
            >
               <div style={{ fontSize: '36px', marginBottom: '16px' }}>💻</div>
               <h3 style={{ fontSize: '20px', fontWeight: 'bold', color: '#1e293b', marginBottom: '8px' }}>{t('cp.portals.p2.title') || 'Kassa / POS'}</h3>
               <p style={{ color: '#64748b', fontSize: '14px', lineHeight: '1.5' }}>{t('cp.portals.p2.desc') || 'Kassirlar savdosi xaritasi, Ofitsiantlar va KDS oshxona ekrani'}</p>
            </div>

            {/* Super Admin */}
            <div
              style={{ background: '#f8fafc', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0', cursor: 'pointer', transition: 'all 0.3s ease' }}
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/super-admin/login'}
            >
               <div style={{ fontSize: '36px', marginBottom: '16px' }}>👑</div>
               <h3 style={{ fontSize: '20px', fontWeight: 'bold', color: '#1e293b', marginBottom: '8px' }}>{t('cp.portals.p3.title') || 'Super Admin'}</h3>
               <p style={{ color: '#64748b', fontSize: '14px', lineHeight: '1.5' }}>{t('cp.portals.p3.desc') || 'Tizim muallifi (Siz) uchun. Klientlarning oylik to\'lov va litsenziyalari'}</p>
            </div>

            {/* Agent Portali */}
            <div 
              style={{ background: '#f8fafc', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0', cursor: 'pointer', transition: 'all 0.3s ease' }}
              onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/agent-portal'}
            >
               <div style={{ fontSize: '36px', marginBottom: '16px' }}>🤝</div>
               <h3 style={{ fontSize: '20px', fontWeight: 'bold', color: '#1e293b', marginBottom: '8px' }}>{t('cp.portals.p4.title') || 'Agent Portali'}</h3>
               <p style={{ color: '#64748b', fontSize: '14px', lineHeight: '1.5' }}>{t('cp.portals.p4.desc') || 'Restoranlarni tizimga ulovchi yordamchi kadrlar / franshiza xonasi'}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="sp-section" id="modullar">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag" style={{ color: '#ea580c', background: 'rgba(234,88,12,0.1)' }}>{t('cp.mod.tag') || 'Maxsus Modullar'}</div>
            <h2 className="sp-section-title">{t('cp.mod.title') || 'Ovqatlanish sohasi uchun barcha yechimlar'}</h2>
            <p className="sp-section-desc">{t('cp.mod.desc') || 'Faqat POS emas, balki butun biznesingiz yuragini boshqaring.'}</p>
          </div>

          <div className="sp-modules-wrap">
            <div className="sp-module-sidebar">
              {modules.map((mod, idx) => (
                <button
                  key={mod.id}
                  className={`sp-module-tab ${activeModule === idx ? 'active' : ''}`}
                  style={activeModule === idx ? { borderLeftColor: mod.color, color: mod.color, background: mod.bg } : {}}
                  onClick={() => setActiveModule(idx)}
                >
                  <span className="sp-module-icon">{mod.icon}</span>
                  <div>
                    <div className="sp-module-tab-title">{mod.title}</div>
                    <div className="sp-module-tab-sub">{mod.subtitle}</div>
                  </div>
                </button>
              ))}
            </div>

            <div className="sp-module-content" key={activeModule}>
              <div className="sp-module-content-top" style={{ borderTopColor: modules[activeModule].color }}>
                <div className="sp-module-big-icon" style={{ color: modules[activeModule].color, background: modules[activeModule].bg }}>
                  {modules[activeModule].icon}
                </div>
                <div>
                  <h3 className="sp-module-title">{modules[activeModule].title}</h3>
                  <p className="sp-module-sub">{modules[activeModule].subtitle}</p>
                </div>
              </div>
              <p className="sp-module-desc">{modules[activeModule].desc}</p>

              <div className="sp-module-stats">
                {modules[activeModule].stats.map((s, i) => (
                  <div key={i} className="sp-module-stat-card" style={{ borderTopColor: modules[activeModule].color }}>
                    <span className="sp-ms-val" style={{ color: modules[activeModule].color }}>{s.val}</span>
                    <span className="sp-ms-lbl">{s.label}</span>
                  </div>
                ))}
              </div>

              <div className="sp-feature-list">
                {modules[activeModule].features.map((f, i) => (
                  <div key={i} className="sp-feature-item">
                    <span className="sp-feature-check" style={{ color: modules[activeModule].color, background: modules[activeModule].bg }}>
                      <CheckIcon />
                    </span>
                    <span>{f}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="sp-cta-section" id="sp-contact" style={{ background: '#fffbeb' }}>
        <div className="ent-container">
          <div className="sp-cta-box" style={{ background: '#ea580c' }}>
            <h2 style={{ color: 'white' }}>{t('cp.cta.title') || 'Chaqqon Pro ga ulanish tayyormisiz?'}</h2>
            <p style={{ color: 'rgba(255,255,255,0.9)' }}>
              {t('cp.cta.desc') || 'Restoraningiz hajmidan qat\'iy nazar, yordam beramiz.'}
            </p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white" style={{ color: '#ea580c' }}>
                {t('cp.cta.btn') || '💬 Biz bilan bog\'lanish'}
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
