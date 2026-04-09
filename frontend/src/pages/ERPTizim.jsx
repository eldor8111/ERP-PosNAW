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
    id: 'pos',
    icon: '🖥️',
    color: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    title: 'POS Kassa',
    subtitle: 'Tezkor sotuv terminali',
    desc: 'Bir nechta kassa punktlarini yagona tizimga ulang. Shtrix-kod, skanerlash, naqd va bank kartasi to\'lovlari.',
    features: [
      'Tezkor mahsulot qidirish va skanerlash',
      'Naqd, karta, nasiya to\'lov usullari',
      'Bir vaqtda bir nechta kassa',
      'Smena ochish/yopish hisobotlari',
      'Chek chiqarish (termal printer)',
      'Qaytarish (return) boshqaruvi',
    ],
    stats: [{ val: '< 2 son', label: 'Sotuv qayta ishlash' }, { val: '∞', label: 'Mahsulot soni' }, { val: '99.9%', label: 'Uptime kafolat' }]
  },
  {
    id: 'ombor',
    icon: '🏭',
    color: '#10b981',
    bg: 'rgba(16,185,129,0.08)',
    title: 'Ombor Boshqaruvi',
    subtitle: 'WMS — Warehouse Management System',
    desc: 'Real-vaqtda tovar harakatini kuzating. Kirim, chiqim, ko\'chirish va inventarizatsiya to\'liq avtomatlashtirilgan.',
    features: [
      'Tovar kirim/chiqim/ko\'chirish',
      'Bir nechta omborxona boshqaruvi',
      'FIFO / LIFO hisobi',
      'Minimal qoldiq ogohlantirish',
      'Shtrix-kod va QR kod yetkazib berish',
      'Inventarizatsiya (reviziya)',
    ],
    stats: [{ val: '10+', label: 'Omborxona parallel' }, { val: 'FIFO', label: 'Hisob metodi' }, { val: 'Real-vaqt', label: 'Qoldiq kuzatuvi' }]
  },
  {
    id: 'crm',
    icon: '👥',
    color: '#8b5cf6',
    bg: 'rgba(139,92,246,0.08)',
    title: 'CRM — Mijozlar',
    subtitle: 'Mijozlar munosabatlari boshqaruvi',
    desc: 'Har bir mijozning sotib olish tarixi, qarzi, shartnomalari va muloqotlarini bir joyda saqlang.',
    features: [
      'Mijoz profili va kontakt ma\'lumotlari',
      'Qarzdorlik va nasiya hisobi',
      'Sotuv tarixi va statistika',
      'B2B: Shartnomaviy sotuv',
      'Telegram xabarnoma yuborish',
      'Mijoz segmentatsiyasi',
    ],
    stats: [{ val: '100K+', label: 'Mijoz bazasi' }, { val: 'B2B+B2C', label: 'Sotuv modeli' }, { val: 'Telegram', label: 'Xabarnoma kanal' }]
  },
  {
    id: 'moliya',
    icon: '💰',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.08)',
    title: 'Moliya va Kassa',
    subtitle: 'To\'liq moliyaviy nazorat',
    desc: 'Har kungi kassa harakati, xarajatlar, daromadlar va foyda/zarar hisobotini real-vaqtda kuzating.',
    features: [
      'Kassa kirim/chiqim operatsiyalari',
      'Xarajatlar kategoriyasi',
      'Foyda/zarar P&L hisoboti',
      'Valyuta konvertatsiyasi',
      'Bank hisobvaraqlari integratsiyasi',
      'Soliq hisobot eksport',
    ],
    stats: [{ val: 'P&L', label: 'Foyda/zarar' }, { val: '3+', label: 'Valyuta qo\'llab quvvatlash' }, { val: 'Excel', label: 'Eksport format' }]
  },
  {
    id: 'hisobot',
    icon: '📊',
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    title: 'Analitika va Hisobotlar',
    subtitle: 'Business Intelligence Dashboard',
    desc: 'Savdoni, omborni, moliyani va xodimlarni tahlil qiling. Vizual grafiklar va chuqur insight\'lar.',
    features: [
      'Sotuv dinamikasi grafigi',
      'ABC tovar tahlili',
      'Xodim unumdorligi hisoboti',
      'Mijoz faoliyati tahlili',
      'Daromad prognozi',
      'PDF / Excel eksport',
    ],
    stats: [{ val: '20+', label: 'Hisobot turi' }, { val: 'ABC', label: 'Tovar tahlil metodi' }, { val: 'PDF/Excel', label: 'Eksport format' }]
  },
  {
    id: 'users',
    icon: '🔐',
    color: '#0891b2',
    bg: 'rgba(8,145,178,0.08)',
    title: 'Foydalanuvchi & Huquqlar',
    subtitle: 'Rol asosida kirish nazorati',
    desc: 'Kassir, menejer, ombordor, direktor — har bir xodimga alohida huquqlar bering. Audit log to\'liq.',
    features: [
      'Rol asosida huquq tizimi (RBAC)',
      'Har bir operatsiya audit logi',
      'Telegram orqali OTP kirish',
      'Ko\'p filial boshqaruvi',
      'Super admin panel',
      'Smena va navbat boshqaruvi',
    ],
    stats: [{ val: '10+', label: 'Rol turi' }, { val: '100%', label: 'Audit log' }, { val: 'OTP', label: 'Ikki faktorli kirish' }]
  },
]

const tariffs = [
  {
    name: 'Starter',
    price: 'Arzon narxda',
    badge: '💼 Kichik biznes',
    color: '#2563eb',
    popular: false,
    desc: 'Savdoni boshlash uchun ideal',
    hint: 'Narx biznes hajmiga qarab belgilanadi',
    features: ['1 ta omborxona', '2 ta kassa', '3 ta foydalanuvchi', 'POS + Ombor modullari', 'Email qo\'llab-quvvatlash'],
  },
  {
    name: 'Business',
    price: 'Kelishilgan narxda',
    badge: '🚀 Eng mashhur',
    color: '#10b981',
    popular: true,
    desc: 'O\'sib borayotgan biznes uchun',
    hint: 'Bepul demo va narx hisob-kitobi uchun murojaat qiling',
    features: ['5 ta omborxona', '10 ta kassa', '20 ta foydalanuvchi', 'Barcha modullar', 'Telegram xabarnoma', 'CRM + Analitika', 'Telegram qo\'llab-quvvatlash'],
  },
  {
    name: 'Enterprise',
    price: 'Individual narx',
    badge: '🏢 Yirik korxona',
    color: '#8b5cf6',
    popular: false,
    desc: 'Maxsus talablar uchun',
    hint: 'Mutaxassis bilan bepul konsultatsiya',
    features: ['Cheksiz omborxona', 'Cheksiz kassa', 'Cheksiz foydalanuvchi', 'Custom integratsiya', 'API kirish', 'Dedicated server', '24/7 qo\'llab-quvvatlash'],
  },
]

export default function ERPTizim() {
  const navigate = useNavigate()
  const [activeModule, setActiveModule] = useState(0)

  return (
    <LandingLayout>
      {/* ── Hero ── */}
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #0f172a 100%)' }}>
        <div className="sp-hero-bg-dots" />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>Bosh sahifa</span>
            <span className="sp-bc-sep">›</span>
            <span>ERP Tizim</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(37,99,235,0.3)', color: '#93c5fd', borderColor: 'rgba(37,99,235,0.4)' }}>
            🏆 &nbsp;Enterprise ERP — POS
          </div>
          <h1 className="sp-hero-title">
            Biznesingizni to'liq<br />
            <span className="sp-gradient-text">raqamlashtiring</span>
          </h1>
          <p className="sp-hero-desc">
            Savdo, ombor, moliya, mijozlar va xodimlarni — barchasini yagona tizimda boshqaring. 
            Real-vaqtda analitika va professional hisobotlar.
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">500+</span><span className="sp-stat-lbl">Faol foydalanuvchi</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">6</span><span className="sp-stat-lbl">Asosiy modul</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">99.9%</span><span className="sp-stat-lbl">Uptime kafolat</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">3 yil</span><span className="sp-stat-lbl">Bozorda tajriba</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" onClick={() => window.location.href = 'http://erp.e-code.uz/register'}>
              Bepul sinab ko'ring <ArrowRight />
            </button>
            <button className="sp-btn-ghost" onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              Demo so'rash
            </button>
          </div>
        </div>
      </section>

      {/* ── Modules Interactive ── */}
      <section className="sp-section" id="modullar">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Modullar</div>
            <h2 className="sp-section-title">6 ta kuchli modul — bitta tizim</h2>
            <p className="sp-section-desc">Har bir biznes jarayoni uchun maxsus ishlab chiqilgan, bir-biri bilan to'liq integratsiya qilingan modullar</p>
          </div>

          <div className="sp-modules-wrap">
            {/* Sidebar */}
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

            {/* Content */}
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

              <button
                className="sp-btn-primary"
                style={{ background: `linear-gradient(135deg, ${modules[activeModule].color}, ${modules[activeModule].color}cc)` }}
                onClick={() => window.location.href = 'http://erp.e-code.uz/register'}
              >
                Bu modul bilan boshlash <ArrowRight />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Why ERP ── */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Nima uchun E-code ERP?</div>
            <h2 className="sp-section-title">Raqobatchilardan farqi</h2>
          </div>
          <div className="sp-compare-grid">
            <div className="sp-compare-col sp-compare-bad">
              <div className="sp-compare-header">
                <span className="sp-compare-icon sp-bad">✗</span>
                <h3>Oddiy yondashuv</h3>
              </div>
              {[
                'Excel jadvallar — xato va sekin',
                'Ma\'lumotlar tarqoq — bir joyda emas',
                'Hisobotlar qo\'lda — vaqt yo\'qotish',
                'Ombor nazorati yo\'q',
                'Mijoz tarixi saqlanmaydi',
                'Real-vaqt ma\'lumot yo\'q',
              ].map((t, i) => (
                <div key={i} className="sp-compare-item sp-compare-item-bad">
                  <span>✗</span> {t}
                </div>
              ))}
            </div>
            <div className="sp-compare-col sp-compare-good">
              <div className="sp-compare-header">
                <span className="sp-compare-icon sp-good">✓</span>
                <h3>E-code ERP bilan</h3>
              </div>
              {[
                'Avtomatlashtirilgan raqamli hisob',
                'Barcha ma\'lumotlar yagona bazada',
                'Bir klik — to\'liq hisobot',
                '100% real-vaqt ombor nazorati',
                'Har bir mijozning to\'liq tarixi',
                'Dashboard — har qanday qurilmadan',
              ].map((t, i) => (
                <div key={i} className="sp-compare-item sp-compare-item-good">
                  <CheckIcon /> {t}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Tariffs ── */}
      <section className="sp-section" id="tariff">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Rejalar</div>
            <h2 className="sp-section-title">Biznesingiz uchun mos reja</h2>
            <p className="sp-section-desc">Narx biznesingiz hajmi va ehtiyojlariga qarab belgilanadi. Bepul konsultatsiya oling.</p>
          </div>

          <div className="sp-price-notice">
            <span className="sp-price-notice-icon">💬</span>
            <div>
              <strong>Narxni bilish uchun murojaat qiling</strong>
              <p>Biznes hajmingiz, modul tanlovi va foydalanuvchilar soniga qarab individual narx taklif qilamiz. Bepul demo seans o'tkazamiz.</p>
            </div>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-price-contact-btn">
              💬 Narxni so'rash
            </a>
          </div>

          <div className="sp-tariff-grid">
            {tariffs.map((tariff) => (
              <div key={tariff.name} className={`sp-tariff-card ${tariff.popular ? 'sp-tariff-popular' : ''}`}>
                {tariff.popular && <div className="sp-tariff-badge">⭐ Eng mashhur</div>}
                <div className="sp-tariff-badge-top">{tariff.badge}</div>
                <div className="sp-tariff-name" style={{ color: tariff.color }}>{tariff.name}</div>
                <div className="sp-tariff-desc">{tariff.desc}</div>
                <div className="sp-tariff-price-contact" style={{ borderColor: `${tariff.color}30`, background: `${tariff.color}08` }}>
                  <span className="sp-tariff-contact-label" style={{ color: tariff.color }}>{tariff.price}</span>
                  <span className="sp-tariff-contact-hint">{tariff.hint}</span>
                </div>
                <div className="sp-tariff-features">
                  {tariff.features.map((f, i) => (
                    <div key={i} className="sp-tariff-feature">
                      <span className="sp-tf-check" style={{ color: tariff.color }}><CheckIcon /></span>
                      {f}
                    </div>
                  ))}
                </div>
                <button
                  className="sp-tariff-btn"
                  style={tariff.popular ? { background: `linear-gradient(135deg, ${tariff.color}, ${tariff.color}cc)`, color: 'white' } : { borderColor: tariff.color, color: tariff.color }}
                  onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
                >
                  Narxni so'rash →
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="sp-cta-section" id="sp-contact">
        <div className="ent-container">
          <div className="sp-cta-box">
            <h2>Tizimni bepul 14 kun sinab ko'ring</h2>
            <p>Kartangizni bog'lashingiz shart emas. Biznes ma'lumotlaringizni kiriting va darhol boshlang.</p>
            <div className="sp-cta-btns">
              <button className="sp-btn-white" onClick={() => window.location.href = 'http://erp.e-code.uz/register'}>
                Bepul ro'yxatdan o'tish <ArrowRight />
              </button>
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-tg">
                💬 Telegram orqali bog'lanish
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
