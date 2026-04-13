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

// Modules moved into the component


import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'

export default function ERPTizim() {
  const navigate = useNavigate()
  const { t } = useLang()
  useSeo(
    "ERP Tizimi – Savdo, Ombor va Moliya Boshqaruvi | E-code",
    "E-code ERP tizimi: savdo, ombor, xodimlar, moliya va hisobotlarni bir joyda boshqaring. O'zbekiston bizneslar uchun professional yechim."
  )

const tariffs = [
  {
    name: t('erp.tariffs.starter.name') || 'Starter',
    price: t('erp.tariffs.arzonnar.price') || 'Arzon narxda',
    badge: t('erp.tariffs.kichikbi.badge') || '💼 Kichik biznes',
    color: '#2563eb',
    popular: false,
    desc: t('erp.tariffs.savdonib.desc') || 'Savdoni boshlash uchun ideal',
    hint: t('erp.tariffs.narxbizn.hint') || 'Narx biznes hajmiga qarab belgilanadi',
    features: ['1 ta omborxona', '2 ta kassa', '3 ta foydalanuvchi', 'POS + Ombor modullari', 'Email qo\'llab-quvvatlash'],
  },
  {
    name: t('erp.tariffs.business.name') || 'Business',
    price: t('erp.tariffs.kelishil.price') || 'Kelishilgan narxda',
    badge: t('erp.tariffs.engmashh.badge') || '🚀 Eng mashhur',
    color: '#10b981',
    popular: true,
    desc: t('erp.tariffs.o.desc') || 'O\'sib borayotgan biznes uchun',
    hint: t('erp.tariffs.bepuldem.hint') || 'Bepul demo va narx hisob-kitobi uchun murojaat qiling',
    features: ['5 ta omborxona', '10 ta kassa', '20 ta foydalanuvchi', 'Barcha modullar', 'Telegram xabarnoma', 'CRM + Analitika', 'Telegram qo\'llab-quvvatlash'],
  },
  {
    name: t('erp.tariffs.enterpri.name') || 'Enterprise',
    price: t('erp.tariffs.individu.price') || 'Individual narx',
    badge: t('erp.tariffs.yirikkor.badge') || '🏢 Yirik korxona',
    color: '#8b5cf6',
    popular: false,
    desc: t('erp.tariffs.maxsusta.desc') || 'Maxsus talablar uchun',
    hint: t('erp.tariffs.mutaxass.hint') || 'Mutaxassis bilan bepul konsultatsiya',
    features: ['Cheksiz omborxona', 'Cheksiz kassa', 'Cheksiz foydalanuvchi', 'Custom integratsiya', 'API kirish', 'Dedicated server', '24/7 qo\'llab-quvvatlash'],
  },
]
  const [activeModule, setActiveModule] = useState(0)

  const modules = [
    {
      id: 'pos',
      icon: '🖥️',
      color: '#2563eb',
      bg: 'rgba(37,99,235,0.08)',
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
      icon: '🏭',
      color: '#10b981',
      bg: 'rgba(16,185,129,0.08)',
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
      icon: '👥',
      color: '#8b5cf6',
      bg: 'rgba(139,92,246,0.08)',
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
      icon: '💰',
      color: '#f59e0b',
      bg: 'rgba(245,158,11,0.08)',
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
      icon: '📊',
      color: '#ef4444',
      bg: 'rgba(239,68,68,0.08)',
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
      icon: '🔐',
      color: '#0891b2',
      bg: 'rgba(8,145,178,0.08)',
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

  return (
    <LandingLayout>
      {/* ── Hero ── */}
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #0f172a 100%)' }}>
        <div className="sp-hero-bg-dots" />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>{t('erp.bc.home') || 'Bosh sahifa'}</span>
            <span className="sp-bc-sep">›</span>
            <span>{t('erp.bc.current') || 'ERP Tizim'}</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(37,99,235,0.3)', color: '#93c5fd', borderColor: 'rgba(37,99,235,0.4)' }} dangerouslySetInnerHTML={{ __html: t('erp.tag') || '🏆 &nbsp;Enterprise ERP — POS' }} />
          <h1 className="sp-hero-title">
            {t('erp.hero.title1') || 'Biznesingizni to\'liq'}<br />
            <span className="sp-gradient-text">{t('erp.hero.title2') || 'raqamlashtiring'}</span>
          </h1>
          <p className="sp-hero-desc">
            {t('erp.hero.desc') || 'Savdo, ombor, moliya, mijozlar va xodimlarni — barchasini yagona tizimda boshqaring...'}
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">{t('erp.hero.stat1.val') || '500+'}</span><span className="sp-stat-lbl">{t('erp.hero.stat1.lbl') || 'Faol foydalanuvchi'}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('erp.hero.stat2.val') || '6'}</span><span className="sp-stat-lbl">{t('erp.hero.stat2.lbl') || 'Asosiy modul'}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('erp.hero.stat3.val') || '99.9%'}</span><span className="sp-stat-lbl">{t('erp.hero.stat3.lbl') || 'Uptime kafolat'}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('erp.hero.stat4.val') || '3 yil'}</span><span className="sp-stat-lbl">{t('erp.hero.stat4.lbl') || 'Bozorda tajriba'}</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" onClick={() => window.location.href = 'https://savdo.e-code.uz/register'}>
              {t('erp.hero.btn1') || 'Bepul sinab ko\'ring'} <ArrowRight />
            </button>
            <button className="sp-btn-ghost" onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              {t('erp.hero.btn2') || 'Demo so\'rash'}
            </button>
          </div>
        </div>
      </section>

      {/* ── Modules Interactive ── */}
      <section className="sp-section" id="modullar">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('erp.mod.tag') || 'Modullar'}</div>
            <h2 className="sp-section-title">{t('erp.mod.title') || '6 ta kuchli modul — bitta tizim'}</h2>
            <p className="sp-section-desc">{t('erp.mod.desc') || 'Har bir biznes jarayoni uchun maxsus ishlab chiqilgan, bir-biri bilan to\'liq integratsiya qilingan modullar'}</p>
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
                onClick={() => window.location.href = 'https://savdo.e-code.uz/register'}
              >
                {t('erp.mod.btn') || 'Bu modul bilan boshlash'} <ArrowRight />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Nima uchun E-code ERP? ── */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('erp.why.tag') || 'Nima uchun E-code ERP?'}</div>
            <h2 className="sp-section-title">{t('erp.why.title') || 'Raqobatchilardan farqi'}</h2>
          </div>
          <div className="sp-compare-grid">
            <div className="sp-compare-col sp-compare-bad">
              <div className="sp-compare-header">
                <span className="sp-compare-icon sp-bad">✕</span>
                <h3>{t('erp.why.bad.title') || 'Oddiy yondashuv'}</h3>
              </div>
              {[
                {k: '1', default: 'Excel jadvallar — xato va sekin'},
                {k: '2', default: 'Ma\'lumotlar tarqoq'},
                {k: '3', default: 'Hisobotlar qo\'lda'},
                {k: '4', default: 'Ombor nazorati yo\'q'},
                {k: '5', default: 'Mijoz tarixi saqlanmaydi'}
              ].map((item, i) => (
                <div key={i} className="sp-compare-item sp-compare-item-bad">
                  <span>✕</span> {t(`erp.why.bad.${item.k}`) || item.default}
                </div>
              ))}
            </div>
            <div className="sp-compare-col sp-compare-good">
              <div className="sp-compare-header">
                <span className="sp-compare-icon sp-good">✓</span>
                <h3>{t('erp.why.good.title') || 'E-code ERP bilan'}</h3>
              </div>
              {[
                {k: '1', default: 'Avtomatlashtirilgan raqamli hisob'},
                {k: '2', default: 'Barcha ma\'lumotlar yagona bazada'},
                {k: '3', default: 'Bir klik — to\'liq hisobot'},
                {k: '4', default: '100% real-vaqt ombor nazorati'},
                {k: '5', default: 'Mijozning to\'liq tarixi'}
              ].map((item, i) => (
                <div key={i} className="sp-compare-item sp-compare-item-good">
                  <CheckIcon /> {t(`erp.why.good.${item.k}`) || item.default}
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
            <div className="sp-section-tag">{t('erp.plan.tag') || 'Rejalar'}</div>
            <h2 className="sp-section-title">{t('erp.plan.title') || 'Biznesingiz uchun mos reja'}</h2>
            <p className="sp-section-desc">{t('erp.plan.desc') || 'Narx biznesingiz hajmi va ehtiyojlariga qarab belgilanadi. Bepul konsultatsiya oling.'}</p>
          </div>

          <div className="sp-price-notice">
            <span className="sp-price-notice-icon">💬</span>
            <div>
              <strong>{t('erp.plan.notice.title') || 'Narxni bilish uchun murojaat qiling'}</strong>
              <p>{t('erp.plan.notice.desc') || 'Biznes hajmingiz, modul tanlovi va foydalanuvchilar soniga qarab individual narx taklif qilamiz. Bepul demo seans o\'tkazamiz.'}</p>
            </div>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-price-contact-btn">
              💬 {t('erp.plan.notice.btn') || 'Narxni so\'rash'}
            </a>
          </div>

          <div className="sp-tariff-grid">
            {tariffs.map((tariff) => (
              <div key={tariff.name} className={`sp-tariff-card ${tariff.popular ? 'sp-tariff-popular' : ''}`}>
                {tariff.popular && <div className="sp-tariff-badge">⭐ {t('erp.plan.popular') || 'Eng mashhur'}</div>}
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
                  {t('erp.hero.btn2') || "Narxni so'rash"}
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
            <h2>{t('erp.cta.title') || 'Tizimni bepul 14 kun sinab ko\'ring'}</h2>
            <p>{t('erp.cta.desc') || 'Kartangizni bog\'lashingiz shart emas. Biznes ma\'lumotlaringizni kiriting va darhol boshlang.'}</p>
            <div className="sp-cta-btns">
              <button className="sp-btn-white" onClick={() => window.location.href = 'https://savdo.e-code.uz/register'}>
                {t('erp.cta.btn1') || 'Bepul ro\'yxatdan o\'tish'} <ArrowRight />
              </button>
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-tg">
                📞 {t('erp.cta.btn2') || 'Telegram orqali bog\'lanish'}
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
