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

const modules = [
  {
    id: 'kassa',
    icon: '🍔',
    color: '#f97316', // Orange
    bg: 'rgba(249,115,22,0.08)',
    title: 'Tezkor Kassa',
    subtitle: 'Ofitsiant va kassirlar uchun POS',
    desc: 'Buyurtmani xatosiz va tez qabul qiling. Retseptli taomlar, kombinatsiyalar, stol va yetkazib berish (delivery) funksiyalari mavjud.',
    features: [
      'Stollar xaritasi va band qilish',
      'Oshxona printerlari bilan ishlash (tichets)',
      'Olib ketish va Yetkazib berish (Delivery)',
      'Chegirma va mijoz loyiqligi kartalari',
      'Bir nechta to\'lov usullari (Naqd, Karta, Click/Payme)',
    ],
    stats: [{ val: '2 soniya', label: 'Buyurtma qabul' }, { val: 'Cheksiz', label: 'Stollar soni' }, { val: '100%', label: 'Xatosizlik' }]
  },
  {
    id: 'oshxona',
    icon: '👨‍🍳',
    color: '#ef4444', // Red
    bg: 'rgba(239,68,68,0.08)',
    title: 'Oshxona Ekrani (KDS)',
    subtitle: 'Kitchen Display System',
    desc: 'Qog\'oz cheklarni unuting. Buyurtmalar ofitsiant qo\'shgan zahoti to\'g\'ridan to\'g\'ri oshxona ekranida paydo bo\'ladi.',
    features: [
      'Sensor ekranlarga mos dizayn',
      'Taom tayyorlanish jarayoni va holati (Kutilmoqda, Tayyorlanmoqda, Tayyor)',
      'Gecikkan buyurtmalar uchun ogohlantirish (qizil rangda)',
      'Ofitsiantga avtomatik bildirishnoma',
    ],
    stats: [{ val: '<5 soniya', label: 'Ma\'lumot o\'tishi' }, { val: '0', label: 'Yo\'qolgan cheklar' }]
  },
  {
    id: 'ombor',
    icon: '📦',
    color: '#10b981', // Green
    bg: 'rgba(16,185,129,0.08)',
    title: 'Retsept va Skalad',
    subtitle: 'Murakkab ombor va kalkulyatsiya',
    desc: 'Sotilgan har bir porsiya taom uchun kerakli masalliqlar avtomatik ravishda ombordan hisobdan chiqariladi (kalkulyatsiya).',
    features: [
      'Taomlar kalkulyatsiya xaritasi (Retseptlar)',
      'Yarim tayyor (zakovetlar) mahsulotlar/yarim tayyor',
      'Masalliqlar qoldig\'ini real-vaqtda nazorat qilish',
      'Yaroqlilik muddati nazorati (Spisaniya)',
      'Ta\'minotchilar bilan hisob-kitoblar',
    ],
    stats: [{ val: 'Avtomat', label: 'Spisaniya' }, { val: 'Gramm/Shtuk', label: 'Aniq o\'lchovlar' }]
  },
  {
    id: 'analitika',
    icon: '📈',
    color: '#8b5cf6', // Violet
    bg: 'rgba(139,92,246,0.08)',
    title: 'Daromad va Analitika',
    subtitle: 'Restoran ko\'rsatkichlari',
    desc: 'Qaysi taom ko\'p sotilyapti? Qaysi ofitsiant yaxshi ishlayapti? Foyda / Zarar hisoboti to\'liq kaftingizda.',
    features: [
      'ABC tahlili - eng daromadli taomlarni aniqlash',
      'Soatbay tirbandlik tahlili (Peak hours)',
      'Sof foyda (P&L) va kunlik kassa hisoboti',
      'Ofitsiantlarning xizmat foizlarini (chayeviye)',
    ],
    stats: [{ val: 'Real-time', label: 'Statistika' }, { val: 'Excel/PDF', label: 'Eksport' }]
  }
]

export default function ChaqqonPro() {
  const navigate = useNavigate()
  const [activeModule, setActiveModule] = useState(0)

  return (
    <LandingLayout>
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #431407 0%, #7c2d12 50%, #431407 100%)' }}>
        <div className="sp-hero-bg-dots" style={{ opacity: 0.1 }} />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>Bosh sahifa</span>
            <span className="sp-bc-sep">›</span>
            <span>Chaqqon Pro</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(249,115,22,0.3)', color: '#fdba74', borderColor: 'rgba(249,115,22,0.4)' }}>
            🍽️ &nbsp;Restoran / Kafe POS
          </div>
          <h1 className="sp-hero-title">
            Ovqatlanish biznesingizni<br />
            <span className="sp-gradient-text" style={{ background: 'linear-gradient(to right, #fbbf24, #f97316)', WebkitBackgroundClip: 'text', color: 'transparent' }}>Chaqqon</span> boshqaring
          </h1>
          <p className="sp-hero-desc">
            Restoran, kafe, fast-food va oshxonalar uchun tezkor, ishonchli va to'liq avtomatlashgan POS tizimi. Stollardan tortib oshxona ekranigacha, to'liq yagona tarmoq!
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">Tez</span><span className="sp-stat-lbl">Xizmat ko'rsatish</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">0</span><span className="sp-stat-lbl">Xatolik</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">To'liq</span><span className="sp-stat-lbl">Kalkulyatsiya</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" style={{ background: 'linear-gradient(135deg, #ea580c, #c2410c)', borderColor: '#c2410c' }} onClick={() => window.location.href = 'https://chaqqonpro.e-code.uz/login'}>
              Tizimni sinab ko'rish <ArrowRight />
            </button>
            <button className="sp-btn-ghost" onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              Narxlarni bilish
            </button>
          </div>
        </div>
      </section>

      <section className="sp-section" id="modullar">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag" style={{ color: '#ea580c', background: 'rgba(234,88,12,0.1)' }}>Maxsus Modullar</div>
            <h2 className="sp-section-title">Ovqatlanish sohasi uchun barcha yechimlar</h2>
            <p className="sp-section-desc">Faqat POS emas, balki butun biznesingiz yuragini boshqaring.</p>
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
            <h2 style={{ color: 'white' }}>Chaqqon Pro ga ulanish tayyormisiz?</h2>
            <p style={{ color: 'rgba(255,255,255,0.9)' }}>
              Restoraningiz hajmidan qat'iy nazar, yordam beramiz.
            </p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white" style={{ color: '#ea580c' }}>
                💬 Biz bilan bog'lanish
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
