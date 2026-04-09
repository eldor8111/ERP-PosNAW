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

const services = [
  {
    icon: '🏢',
    color: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    title: 'Korporativ Saytlar',
    desc: 'Kompaniyangizni professional taqdim eting. Brendingizni aks ettiruvchi zamonaviy dizayn.',
    features: ['Brend identifikatsiya', 'Ko\'p tilli sahifalar', 'SEO optimallashtirish', 'Admin panel', 'Tez yuklash tezligi'],
    price: '3,000,000 so\'mdan',
  },
  {
    icon: '🛒',
    color: '#10b981',
    bg: 'rgba(16,185,129,0.08)',
    title: 'E-Commerce Do\'konlar',
    desc: 'To\'liq onlayn savdo tizimi. To\'lov integratsiyasi, buyurtma boshqaruvi va inventar nazorati.',
    features: ['Mahsulotlar katalogi', 'Online to\'lov', 'Buyurtma kuzatuvi', 'Mobil moslashuvchan', 'Payme/Click integratsiya'],
    price: '7,000,000 so\'mdan',
  },
  {
    icon: '🎨',
    color: '#8b5cf6',
    bg: 'rgba(139,92,246,0.08)',
    title: 'Mualliflik Loyihalari',
    desc: 'Portfolio, blog, shaxsiy brend yoki ijodiy loyihalar uchun noyob dizayn va funksionallik.',
    features: ['Noyob dizayn konsepsiya', 'Animatsiyalar', 'Blog tizimi', 'Ko\'p media format', 'Ijtimoiy tarmoq integratsiya'],
    price: '2,000,000 so\'mdan',
  },
  {
    icon: '📱',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.08)',
    title: 'Landing Page',
    desc: 'Xizmat yoki mahsulotni sotish uchun maxsus bir sahifali sayt. Konversiya uchun optimallashtirilgan.',
    features: ['Konversiya optimallashtirish', 'A/B testing', 'Lead capture forma', 'Analytics integratsiya', 'Tez yetkazib berish'],
    price: '1,500,000 so\'mdan',
  },
  {
    icon: '⚙️',
    color: '#0891b2',
    bg: 'rgba(8,145,178,0.08)',
    title: 'Veb Ilovalar',
    desc: 'Murakkab biznes logikali veb ilovalar. SaaS, dashboard va boshqaruv tizimlar.',
    features: ['React / Next.js', 'REST API yoki GraphQL', 'Real-vaqt ma\'lumot', 'Autentifikatsiya tizimi', 'Cloud deployment'],
    price: '10,000,000 so\'mdan',
  },
  {
    icon: '🔧',
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    title: 'Texnik Qo\'llab-Quvvatlash',
    desc: 'Mavjud saytingizni yangilash, xatolarni tuzatish, tezligini oshirish va xavfsizligini ta\'minlash.',
    features: ['Sayt tezligini oshirish', 'Xavfsizlik tekshiruvi', 'Server sozlamalari', 'Backup tizimi', 'SSL sertifikat'],
    price: '500,000 so\'mdan/oy',
  },
]

const process = [
  { step: '01', icon: '💬', title: 'Murojaat', desc: 'Telegram yoki telefon orqali bog\'laning. Loyiha haqida batafsil suhbatlashtiring.' },
  { step: '02', icon: '📋', title: 'Tahlil & TZ', desc: 'Biznes talablarini tahlil qilamiz va texnik topshiriq (TZ) tayyorlaymiz.' },
  { step: '03', icon: '🎨', title: 'Dizayn', desc: 'Figma\'da professional dizayn yaratamiz va tasdiqlash uchun taqdim etamiz.' },
  { step: '04', icon: '💻', title: 'Ishlab chiqish', desc: 'Zamonaviy texnologiyalarda saytni kod qilamiz, test qilamiz.' },
  { step: '05', icon: '🚀', title: 'Yetkazib berish', desc: 'Saytni serverga joylashtiramiz, domen ulaymiiz va topshiramiz.' },
  { step: '06', icon: '🛡️', title: 'Qo\'llab-quvvatlash', desc: '1 oylik bepul qo\'llab-quvvatlash va keyingi yangilanishlar.' },
]

const techStack = [
  { name: 'React', icon: '⚛️', desc: 'Frontend' },
  { name: 'Next.js', icon: '▲', desc: 'SSR/SSG' },
  { name: 'Node.js', icon: '🟢', desc: 'Backend' },
  { name: 'PostgreSQL', icon: '🐘', desc: 'Database' },
  { name: 'Nginx', icon: '🌐', desc: 'Server' },
  { name: 'Docker', icon: '🐳', desc: 'DevOps' },
  { name: 'Figma', icon: '🎨', desc: 'Dizayn' },
  { name: 'AWS/VPS', icon: '☁️', desc: 'Hosting' },
]

export default function VebSaytlar() {
  const navigate = useNavigate()
  const [activeService, setActiveService] = useState(null)

  return (
    <LandingLayout>
      {/* Hero */}
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)' }}>
        <div className="sp-hero-bg-dots" />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>Bosh sahifa</span>
            <span className="sp-bc-sep">›</span>
            <span>Maxsus Veb-saytlar</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(139,92,246,0.3)', color: '#c4b5fd', borderColor: 'rgba(139,92,246,0.4)' }}>
            🌐 &nbsp;Professional Veb Ishlab Chiqish
          </div>
          <h1 className="sp-hero-title">
            Sizning g'oyangizni<br />
            <span className="sp-gradient-text-purple">veb reallikka</span> aylantiramiz
          </h1>
          <p className="sp-hero-desc">
            Korporativ saytlardan tortib, murakkab e-commerce platformalarigacha — zamonaviy texnologiyalar 
            va premium dizayn bilan quramiz.
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">50+</span><span className="sp-stat-lbl">Yaratilgan saytlar</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">3 yil</span><span className="sp-stat-lbl">Tajriba</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">100%</span><span className="sp-stat-lbl">Mijoz mamnuniyati</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">2-4 hafta</span><span className="sp-stat-lbl">O'rtacha vaqt</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" style={{ background: 'linear-gradient(135deg, #7c3aed, #8b5cf6)' }}
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              Loyiha boshlash <ArrowRight />
            </button>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-ghost">
              💬 Maslahat olish
            </a>
          </div>
        </div>
      </section>

      {/* Services Grid */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Xizmatlar</div>
            <h2 className="sp-section-title">Qanday saytlar yaratamiz?</h2>
            <p className="sp-section-desc">Har xil biznes uchun moslashtirilgan veb yechimlar</p>
          </div>
          <div className="sp-services-grid">
            {services.map((svc, idx) => (
              <div
                key={idx}
                className={`sp-service-card ${activeService === idx ? 'active' : ''}`}
                style={{ '--svc-color': svc.color, '--svc-bg': svc.bg }}
                onClick={() => setActiveService(activeService === idx ? null : idx)}
              >
                <div className="sp-svc-icon" style={{ color: svc.color, background: svc.bg }}>{svc.icon}</div>
                <h3 className="sp-svc-title">{svc.title}</h3>
                <p className="sp-svc-desc">{svc.desc}</p>
                <div className="sp-svc-price" style={{ color: svc.color }}>{svc.price}</div>
                {activeService === idx && (
                  <div className="sp-svc-features">
                    {svc.features.map((f, i) => (
                      <div key={i} className="sp-svc-feature">
                        <span style={{ color: svc.color }}><CheckIcon /></span> {f}
                      </div>
                    ))}
                    <button
                      className="sp-svc-btn"
                      style={{ background: `linear-gradient(135deg, ${svc.color}, ${svc.color}cc)` }}
                      onClick={e => { e.stopPropagation(); const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
                    >
                      Buyurtma berish <ArrowRight />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Process */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Jarayon</div>
            <h2 className="sp-section-title">Qanday ishlayti?</h2>
            <p className="sp-section-desc">6 bosqichli samarali ishlab chiqish jarayoni</p>
          </div>
          <div className="sp-process-grid">
            {process.map((step, idx) => (
              <div key={idx} className="sp-process-card">
                <div className="sp-process-step">{step.step}</div>
                <div className="sp-process-icon">{step.icon}</div>
                <h3 className="sp-process-title">{step.title}</h3>
                <p className="sp-process-desc">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Texnologiyalar</div>
            <h2 className="sp-section-title">Zamonaviy va ishonchli stack</h2>
          </div>
          <div className="sp-tech-grid">
            {techStack.map((tech, idx) => (
              <div key={idx} className="sp-tech-card">
                <div className="sp-tech-icon">{tech.icon}</div>
                <div className="sp-tech-name">{tech.name}</div>
                <div className="sp-tech-desc">{tech.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="sp-cta-section sp-cta-purple" id="sp-contact">
        <div className="ent-container">
          <div className="sp-cta-box">
            <h2>Loyiha haqida gaplashaylik</h2>
            <p>Telegram orqali yozing yoki so'rov qoldiring — 24 soat ichida javob beramiz.</p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white">
                💬 Telegram yozish <ArrowRight />
              </a>
              <a href="tel:+998889118171" className="sp-btn-tg">
                📞 Qo'ng'iroq qilish
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
