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

const solutionTypes = [
  {
    icon: '🏭',
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    title: 'ERP Tizimlar',
    desc: 'Kichik biznesdan yirik korxonagacha — to\'liq avtomatlashtirilgan boshqaruv tizimi.',
    features: ['Savdo va ombor boshqaruvi', 'CRM va mijozlar tizimi', 'Moliya va buxgalteriya', 'HR va xodimlar', 'Ko\'p omborxona va filial', 'Rol asosida huquq tizimi'],
  },
  {
    icon: '📱',
    color: '#8b5cf6',
    bg: 'rgba(139,92,246,0.08)',
    title: 'Mobil Ilovalar',
    desc: 'iOS va Android uchun native yoki cross-platform mobil ilovalar.',
    features: ['React Native/Flutter', 'App Store / Google Play', 'Push bildirishnomalar', 'Offline ishlash rejimi', 'Biometrik autentifikatsiya', 'Native kamera/GPS'],
  },
  {
    icon: '🏥',
    color: '#0891b2',
    bg: 'rgba(8,145,178,0.08)',
    title: 'Tibbiy Tizimlar',
    desc: 'Klinikalar, laboratoriyalar va tibbiyot markazlari uchun maxsus tizimlar.',
    features: ['Bemor qabul tizimi', 'Tibbiy tarix (EHR)', 'Laboratoriya natijalari', 'Navbat boshqaruvi', 'To\'lov integratsiyasi', 'Hisobot va analitika'],
  },
  {
    icon: '🏫',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.08)',
    title: 'Ta\'lim Platformalari',
    desc: 'Online maktablar, kurslar va o\'quv markazlari uchun LMS tizimlar.',
    features: ['Kurs yaratish vositasi', 'Video darslar', 'Test va baholash', 'Sertifikat berish', 'To\'lov tizimi', 'Telegram integratsiya'],
  },
  {
    icon: '📦',
    color: '#10b981',
    bg: 'rgba(16,185,129,0.08)',
    title: 'Logistika & Yetkazib Berish',
    desc: 'Buyurtmalarni kuzatish, kuryer boshqaruvi va omborxona avtomatlash.',
    features: ['Real-vaqt buyurtma kuzatuvi', 'Kuryer mobil ilovasi', 'Marshrut optimallashtirish', 'Mijoz bildirishnomasi', 'Ombor boshqaruvi', 'Hisobot va tahlil'],
  },
  {
    icon: '🏗️',
    color: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    title: 'Construction & Loyiha',
    desc: 'Qurilish kompaniyalari va loyiha boshqaruvi uchun maxsus yechimlar.',
    features: ['Loyiha boshqaruvi', 'Resurs rejalashtirish', 'Xarajat nazorati', 'Xodimlar grafigi', 'Hujjat boshqaruvi', 'Mijoz hisobotlari'],
  },
]

const devProcess = [
  { num: '01', icon: '🔍', title: 'Chuqur Tahlil', desc: 'Biznesingiz, jarayonlar, muammolar va maqsadlarni batafsil o\'rganamiz. Raqobatchilar tahlili.', time: '1-2 kun' },
  { num: '02', icon: '📐', title: 'Arxitektura', desc: 'Texnik arxitektura, ma\'lumotlar bazasi dizayni va tizim xavfsizligi rejasini ishlab chiqamiz.', time: '3-5 kun' },
  { num: '03', icon: '🎨', title: 'UI/UX Dizayn', desc: 'Figma\'da to\'liq prototip va foydalanuvchi tajribasi loyihasini yaratamiz.', time: '1-2 hafta' },
  { num: '04', icon: '⚙️', title: 'Backend Ishlab Chiqish', desc: 'Server tomoni logika, API, ma\'lumotlar bazasi va xavfsizlik integratsiyasi.', time: '2-4 hafta' },
  { num: '05', icon: '💻', title: 'Frontend Ishlab Chiqish', desc: 'Interaktiv va responsive UI, animatsiyalar va foydalanuvchi funksionalligi.', time: '2-3 hafta' },
  { num: '06', icon: '🧪', title: 'Test & QA', desc: 'Unit testlar, integratsiya testlar, performance va xavfsizlik tekshiruvlari.', time: '1 hafta' },
  { num: '07', icon: '🚀', title: 'Deploy & Ishga Tushirish', desc: 'Server sozlash, CI/CD pipeline, monitoring va backup tizimini o\'rnatish.', time: '2-3 kun' },
  { num: '08', icon: '📊', title: 'Monitoring & Qo\'llab-Quvvatlash', desc: 'Doimiy monitoring, hotfix, yangi xususiyatlar va texnik qo\'llab-quvvatlash.', time: 'Doimiy' },
]

const techStack = [
  { category: 'Frontend', techs: ['React', 'Next.js', 'TypeScript', 'TailwindCSS'] },
  { category: 'Backend', techs: ['Python/Django', 'Node.js', 'FastAPI', 'Go'] },
  { category: 'Database', techs: ['PostgreSQL', 'MongoDB', 'Redis', 'Elasticsearch'] },
  { category: 'Mobile', techs: ['React Native', 'Flutter', 'Expo'] },
  { category: 'Infrastructure', techs: ['Docker', 'Kubernetes', 'AWS', 'Nginx'] },
  { category: 'Integrations', techs: ['Telegram API', 'Payme', 'Click', 'Stripe'] },
]

const projects = [
  {
    icon: '🛒',
    title: 'E-code ERP POS',
    tags: ['ERP', 'SaaS', 'Multi-tenant'],
    desc: 'Ko\'p foydalanuvchili savdo boshqaruv tizimi. 500+ aktiv kompaniya foydalanadi.',
    stats: ['500+ kompaniya', '6 modul', '3 yil bozorda'],
    color: '#2563eb',
  },
  {
    icon: '🏥',
    title: 'MedCRM',
    tags: ['Healthcare', 'CRM', 'Mobile'],
    desc: 'Xususiy klinikalar uchun to\'liq tibbiy boshqaruv tizimi.',
    stats: ['12 klinika', '15K+ bemor', 'iOS & Android'],
    color: '#10b981',
  },
  {
    icon: '📚',
    title: 'EduPlatform',
    tags: ['EdTech', 'LMS', 'Telegram Bot'],
    desc: 'Online ta\'lim markazi uchun kurs tizimi, test va sertifikatlash.',
    stats: ['8 maktab', '3K+ talaba', 'Telegram bot'],
    color: '#8b5cf6',
  },
]

export default function NoyobDasturlar() {
  const navigate = useNavigate()
  const [activeType, setActiveType] = useState(0)

  return (
    <LandingLayout>
      {/* Hero */}
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #0f172a 0%, #3b0764 50%, #0f172a 100%)' }}>
        <div className="sp-hero-bg-dots" />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>Bosh sahifa</span>
            <span className="sp-bc-sep">›</span>
            <span>Noyob Dasturlar</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(139,92,246,0.3)', color: '#e9d5ff', borderColor: 'rgba(139,92,246,0.4)' }}>
            💻 &nbsp;Custom Software Development
          </div>
          <h1 className="sp-hero-title">
            G'oyangizni<br />
            <span className="sp-gradient-text-violet">kuchli dasturga</span> aylantiramiz
          </h1>
          <p className="sp-hero-desc">
            ERP, mobil ilova, tibbiy tizim yoki maxsus platform — qanday murakkab bo'lmasin, 
            sifatli va o'lchamli dasturlar yaratamiz.
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">20+</span><span className="sp-stat-lbl">Yaratilgan tizimlar</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">5+</span><span className="sp-stat-lbl">Soha tajribasi</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">100%</span><span className="sp-stat-lbl">Kodga egalik</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">NDA</span><span className="sp-stat-lbl">Maxfiylik kafolati</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" style={{ background: 'linear-gradient(135deg, #7c3aed, #8b5cf6)' }}
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              Loyiha muhokamasi <ArrowRight />
            </button>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-ghost">
              💬 Bepul maslahat
            </a>
          </div>
        </div>
      </section>

      {/* Solutions */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Yechim turlari</div>
            <h2 className="sp-section-title">Qanday dasturlar yaratamiz?</h2>
            <p className="sp-section-desc">Har bir sohaga maxsus yondashuv bilan</p>
          </div>
          <div className="sp-modules-wrap">
            <div className="sp-module-sidebar">
              {solutionTypes.map((sol, idx) => (
                <button
                  key={idx}
                  className={`sp-module-tab ${activeType === idx ? 'active' : ''}`}
                  style={activeType === idx ? { borderLeftColor: sol.color, color: sol.color, background: sol.bg } : {}}
                  onClick={() => setActiveType(idx)}
                >
                  <span className="sp-module-icon">{sol.icon}</span>
                  <div>
                    <div className="sp-module-tab-title">{sol.title}</div>
                  </div>
                </button>
              ))}
            </div>
            <div className="sp-module-content" key={activeType}>
              <div className="sp-module-content-top" style={{ borderTopColor: solutionTypes[activeType].color }}>
                <div className="sp-module-big-icon" style={{ color: solutionTypes[activeType].color, background: solutionTypes[activeType].bg }}>
                  {solutionTypes[activeType].icon}
                </div>
                <div>
                  <h3 className="sp-module-title">{solutionTypes[activeType].title}</h3>
                </div>
              </div>
              <p className="sp-module-desc">{solutionTypes[activeType].desc}</p>
              <div className="sp-feature-list">
                {solutionTypes[activeType].features.map((f, i) => (
                  <div key={i} className="sp-feature-item">
                    <span className="sp-feature-check" style={{ color: solutionTypes[activeType].color, background: solutionTypes[activeType].bg }}>
                      <CheckIcon />
                    </span>
                    <span>{f}</span>
                  </div>
                ))}
              </div>
              <button
                className="sp-btn-primary"
                style={{ background: `linear-gradient(135deg, ${solutionTypes[activeType].color}, ${solutionTypes[activeType].color}cc)` }}
                onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
              >
                Muhokama qilish <ArrowRight />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Projects Showcase */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Portfolio</div>
            <h2 className="sp-section-title">Muvaffaqiyatli loyihalar</h2>
          </div>
          <div className="sp-projects-grid">
            {projects.map((proj, i) => (
              <div key={i} className="sp-project-card">
                <div className="sp-proj-icon" style={{ background: `${proj.color}20`, color: proj.color }}>{proj.icon}</div>
                <div className="sp-proj-tags">
                  {proj.tags.map(tag => (
                    <span key={tag} className="sp-proj-tag" style={{ color: proj.color, background: `${proj.color}15`, borderColor: `${proj.color}30` }}>{tag}</span>
                  ))}
                </div>
                <h3 className="sp-proj-title" style={{ color: proj.color }}>{proj.title}</h3>
                <p className="sp-proj-desc">{proj.desc}</p>
                <div className="sp-proj-stats">
                  {proj.stats.map((s, si) => (
                    <span key={si} className="sp-proj-stat">{s}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Development Process */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Jarayon</div>
            <h2 className="sp-section-title">Professionallar metodologiyasi</h2>
            <p className="sp-section-desc">Agile yondashuv bilan sifatli va vaqtida yetkazib bermiz</p>
          </div>
          <div className="sp-dev-process">
            {devProcess.map((step, i) => (
              <div key={i} className="sp-dev-step">
                <div className="sp-dev-num">{step.num}</div>
                <div className="sp-dev-content">
                  <div className="sp-dev-icon">{step.icon}</div>
                  <h3 className="sp-dev-title">{step.title}</h3>
                  <p className="sp-dev-desc">{step.desc}</p>
                  <div className="sp-dev-time">⏱️ {step.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Texnologiyalar</div>
            <h2 className="sp-section-title">Enterprise darajali texnologiyalar</h2>
          </div>
          <div className="sp-tech-cats">
            {techStack.map((cat, i) => (
              <div key={i} className="sp-tech-cat">
                <h3 className="sp-tech-cat-title">{cat.category}</h3>
                <div className="sp-tech-badges">
                  {cat.techs.map((t, ti) => (
                    <span key={ti} className="sp-tech-badge">{t}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why Us */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Kafolatlar</div>
            <h2 className="sp-section-title">Nima uchun E-code LLC?</h2>
          </div>
          <div className="sp-why-grid">
            {[
              { icon: '🔐', title: 'NDA Shartnoma', desc: 'Loyiha va ma\'lumotlaringiz 100% maxfiy. Notarial tasdiqlangan NDA imzolaymiz.' },
              { icon: '📅', title: 'Vaqt kafolati', desc: 'Kelishilgan muddatda yetkazamiz. Kechikish bo\'lsa — chegirma beramiz.' },
              { icon: '🧩', title: 'Kodega to\'liq egalik', desc: 'Loyiha tugagach barcha kod, server va resurslar sizga o\'tadi.' },
              { icon: '🔧', title: 'Texnik qo\'llab-quvvatlash', desc: 'Xato bo\'lsa 24 soat ichida tuzatamiz. Uzoq muddatli hamkorlik.' },
              { icon: '📈', title: 'O\'lchamli arxitektura', desc: 'Tizim o\'sgan sari ishlaydi. 100 yoki 100,000 foydalanuvchi — farq qilmaydi.' },
              { icon: '💡', title: 'Qo\'shimcha maslahat', desc: 'Faqat kod emas — biznes jarayonlarini yaxshilash bo\'yicha ham maslahatlashamiz.' },
            ].map((w, i) => (
              <div key={i} className="sp-why-card">
                <div className="sp-why-icon">{w.icon}</div>
                <h3 className="sp-why-title">{w.title}</h3>
                <p className="sp-why-desc">{w.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="sp-cta-section sp-cta-violet" id="sp-contact">
        <div className="ent-container">
          <div className="sp-cta-box">
            <h2>G'oyangiz bormi? Gaplashamiz.</h2>
            <p>Bepul konsultatsiya va loyiha narxini aniqlash uchun bog'laning. NDA imzolaymiz.</p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white">
                💬 Telegram orqali bog'lanish <ArrowRight />
              </a>
              <a href="mailto:ecode.uz@gmail.com" className="sp-btn-tg">
                ✉️ Email yozish
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
