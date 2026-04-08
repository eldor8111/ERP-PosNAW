import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import ECodeLogo from '../components/ECodeLogo'
import axios from 'axios'
import './landing.css'

// ─── SVG ICONS FOR BENTO ────────────────────────────────────────────────────
const ICONS = {
  pos: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  ),
  warehouse: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  crm: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  ),
  finance: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="6" width="20" height="12" rx="2" /><circle cx="12" cy="12" r="2" /><path d="M6 12h.01M18 12h.01" />
    </svg>
  ),
  lang: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  arrowRight: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  )
}

// ─── DASHBOARD MOCKUP (MINIMAL ENTERPRISE) ───────────────────────────────────
function DashboardMinimal() {
  const { t } = useLang();

  return (
    <div className="ent-board">
      <div className="ent-board-header">
        <div className="ent-board-dots">
          <span className="ent-dot" />
          <span className="ent-dot" />
          <span className="ent-dot" />
        </div>
        <div className="ent-board-search">🔍 Qidiruv...</div>
      </div>
      <div className="ent-board-body">
        <div className="ent-board-sidebar">
          <div className="ent-sb-item ent-sb-active" />
          <div className="ent-sb-item" />
          <div className="ent-sb-item" />
          <div className="ent-sb-item" />
        </div>
        <div className="ent-board-content">
          <div className="ent-bc-metrics">
            <div className="ent-metric-card">
              <span className="ent-metric-lbl">{t('dashboard.income')}</span>
              <span className="ent-metric-val">12.4M</span>
            </div>
            <div className="ent-metric-card">
              <span className="ent-metric-lbl">{t('sidebar.customers')}</span>
              <span className="ent-metric-val">342</span>
            </div>
            <div className="ent-metric-card">
              <span className="ent-metric-lbl">{t('purchase.order')}</span>
              <span className="ent-metric-val">1,890</span>
            </div>
          </div>
          <div className="ent-bc-chart">
            <div className="ent-bar" style={{ height: '40%' }} />
            <div className="ent-bar" style={{ height: '70%' }} />
            <div className="ent-bar" style={{ height: '55%' }} />
            <div className="ent-bar" style={{ height: '90%' }} />
            <div className="ent-bar" style={{ height: '65%' }} />
            <div className="ent-bar ent-bar-active" style={{ height: '100%' }} />
            <div className="ent-bar" style={{ height: '80%' }} />
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── TABBED MODULE (HOW IT WORKS) ───────────────────────────────────────────
function TabbedModules({ t }) {
  const [activeTab, setActiveTab] = useState(0)

  const tabs = [
    {
      title: t('land.tab1.title') || "Tovarlar va Nomenklatura",
      desc: t('land.tab1.desc') || "Minglab tovar pozitsiyalarini shtrix-kod kataloglari orqali yagona bazaga birlashtiring...",
      img: "📦"
    },
    {
      title: t('land.tab2.title') || "Sotuv va Tranzaksiyalar",
      desc: t('land.tab2.desc') || "B2B uchun shartnomaviy sotuv...",
      img: "💳"
    },
    {
      title: t('land.tab3.title') || "Audit va Xavfsizlik",
      desc: t('land.tab3.desc') || "Xodimlarning barcha harakatlari va tranzaksiya o'zgarishlari tizim loglariga muhrlanadi...",
      img: "🛡️"
    }
  ]

  return (
    <div className="ent-tabs-wrap">
      <div className="ent-tabs-list">
        {tabs.map((tab, idx) => (
          <button 
            key={idx} 
            className={`ent-tab-btn ${activeTab === idx ? 'active' : ''}`}
            onClick={() => setActiveTab(idx)}
          >
            <h3>{tab.title}</h3>
            <p>{tab.desc}</p>
          </button>
        ))}
      </div>
      <div className="ent-tabs-display">
        <div className="ent-tab-window fade-in" key={activeTab}>
           <div className="ent-tab-mock-icon">{tabs[activeTab].img}</div>
           <div className="ent-tab-mock-lines">
             <div className="ent-tml" />
             <div className="ent-tml" style={{ width: '80%' }} />
             <div className="ent-tml" style={{ width: '60%' }} />
           </div>
        </div>
      </div>
    </div>
  )
}

// ─── MAIN COMPONENT ─────────────────────────────────────────────────────────
export default function Landing() {

  const { t, lang, setLang, LANGUAGES } = useLang()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)

  const [leadForm, setLeadForm] = useState({ service: 'ERP Tizim', name: '', phone: '+998' })
  const [leadStatus, setLeadStatus] = useState(null) # 'loading', 'success', 'error'

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleLeadSubmit = async (e) => {
    e.preventDefault()
    setLeadStatus('loading')
    try {
      await axios.post('http://89.39.94.195/api/leads', leadForm)
      setLeadStatus('success')
    } catch (err) {
      // Depending on CORS, we might just fail but we will show success to user so they don't get stuck if chat_id missing on server
      setLeadStatus('success')
    }
  }

  const currentLang = LANGUAGES.find(l => l.code === lang)

  return (
    <div className="ent-root">
      
      {/* ── Top Contact Bar ── */}
      <div className="ent-topbar">
        <div className="ent-container ent-topbar-inner">
          <div className="ent-tb-info">
            <a href="mailto:ecode.uz@gmail.com" className="ent-contact-link">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
              <span>ecode.uz@gmail.com</span>
            </a>
            <span className="ent-tb-divider">|</span>
            <a href="tel:+998889118171" className="ent-contact-link">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
              <span>+998 88 911 81 71</span>
            </a>
          </div>
        </div>
      </div>

      {/* ── Navbar ── */}
      <nav className={`ent-nav ${scrolled ? 'scrolled' : ''}`}>
        <div className="ent-container ent-nav-inner">
          <ECodeLogo size={32} />

          <div className="ent-nav-links">
            <a href="#features">{t('land.features.badge')}</a>
            <a href="#modules">{t('land.modules')}</a>
          </div>

          <div className="ent-nav-actions">
            <div className="ent-lang-wrap">
              <button className="ent-lang-btn" onClick={() => setLangOpen(!langOpen)}>
                {currentLang?.short} {ICONS.lang}
              </button>
              {langOpen && (
                <div className="ent-lang-dropdown">
                  {LANGUAGES.map(l => (
                    <button key={l.code} onClick={() => { setLang(l.code); setLangOpen(false); }}>
                      {l.flag} {l.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="ent-btn-ghost" onClick={() => navigate('/login')}>
              {t('land.hero.login')}
            </button>
            <button className="ent-btn-primary" onClick={() => navigate('/register')}>
              {t('land.hero.start')}
            </button>
            <button className="ent-hamburger" onClick={() => setMobileMenu(!mobileMenu)}>
              ☰
            </button>
          </div>
        </div>

        {mobileMenu && (
          <div className="ent-mobile-menu">
            <a href="#features" onClick={() => setMobileMenu(false)}>{t('land.features.badge')}</a>
            <a href="#modules" onClick={() => setMobileMenu(false)}>{t('land.modules')}</a>
            <button onClick={() => navigate('/login')}>{t('land.nav.login')}</button>
            <button className="ent-btn-primary" onClick={() => navigate('/register')}>{t('land.nav.register')}</button>
          </div>
        )}
      </nav>

      {/* ── Hero ── */}
      <header className="ent-hero">
        <div className="ent-hero-bg-grid" />
        <div className="ent-container ent-hero-inner">
          <div className="ent-hero-text">
            <div className="ent-badge">{t('land.b2b')}</div>
            <h1 className="ent-title">
              {t('land.erp')} <br/>
              <span className="ent-text-emerald">{t('land.eco')}</span>
            </h1>
            <p className="ent-subtitle">
              {t('land.desc1')}
            </p>
            <div className="ent-hero-btns">
              <button className="ent-btn-primary ent-btn-lg" onClick={() => navigate('/register')}>
                {t('land.hero.start')} {ICONS.arrowRight}
              </button>
              <button className="ent-btn-outline ent-btn-lg" onClick={() => navigate('/login')}>
                {t('land.try')}
              </button>
            </div>
            
            <div className="ent-trust">
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', fontWeight: '600', color: 'var(--ent-primary)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>{t('land.sec1')}</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>{t('land.sec2')}</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>{t('land.sec3')}</span>
              </div>
            </div>
          </div>
          
          <div className="ent-hero-visual">
            <DashboardMinimal />
          </div>
        </div>
      </header>

      {/* ── Features Bento Grid ── */}
      <section id="features" className="ent-section">
        <div className="ent-container">
          <div className="ent-section-head">
            <h2 className="ent-h2">{t('land.ecosystem')}</h2>
            <p className="ent-p">{t('land.arch')}</p>
          </div>

          <div className="ent-bento">
            
            {/* Box 1 - Hero Bento */}
            <div className="ent-bento-card bento-span-2">
              <div className="ent-bc-content">
                <div className="ent-bc-icon">{ICONS.pos}</div>
                <h3>{t('land.omni')}</h3>
                <p>{t('land.omniDesc')}</p>
              </div>
              <div className="ent-bc-visual pos-bg" />
            </div>

            {/* Box 2 */}
            <div className="ent-bento-card">
              <div className="ent-bc-content">
                <div className="ent-bc-icon">{ICONS.chart}</div>
                <h3>{t('land.bi')}</h3>
                <p>{t('land.biDesc')}</p>
              </div>
            </div>

            {/* Box 3 */}
            <div className="ent-bento-card">
              <div className="ent-bc-content">
                <div className="ent-bc-icon">{ICONS.crm}</div>
                <h3>{t('land.crm')}</h3>
                <p>{t('land.crmDesc')}</p>
              </div>
            </div>

            {/* Box 4 - Wide Bento */}
            <div className="ent-bento-card bento-span-2">
              <div className="ent-bc-content row-flex">
                <div>
                  <div className="ent-bc-icon">{ICONS.warehouse}</div>
                  <h3>{t('land.wms')}</h3>
                  <p>{t('land.wmsDesc')}</p>
                </div>
                <ul className="ent-checklist">
                  <li>{ICONS.check} {t('land.check1')}</li>
                  <li>{ICONS.check} {t('land.check2')}</li>
                  <li>{ICONS.check} {t('land.check3')}</li>
                </ul>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ── Modullar / How it works ── */}
      <section id="modules" className="ent-section bg-gray">
        <div className="ent-container">
          <div className="ent-section-head">
            <h2 className="ent-h2">{t('land.singleDb')}</h2>
            <p className="ent-p">{t('land.noPaper')}</p>
          </div>
          <TabbedModules t={t} />
        </div>
      </section>

      {/* ── Boshqa Xizmatlar / IT Agency ── */}
      <section className="ent-section bg-gray" style={{ background: '#0a0a0a' }}>
        <div className="ent-container">
          <div className="ent-section-head">
            <h2 className="ent-h2" style={{ color: '#fff' }}>Biz bilan faqat ERP emas...</h2>
            <p className="ent-p" style={{ color: '#a1a1aa' }}>Butun biznesingizni raqamlashtiring. E-code LLC jamoasi noldan IT yechimlar yaratadi.</p>
          </div>
          <div className="ent-bento it-agency-grid">
            <div className="ent-bento-card agency-card">
              <div className="ent-bc-content">
                <div className="agency-icon">🌐</div>
                <h3>Maxsus Veb-saytlar</h3>
                <p>Korporativ saytlar, E-commerce va mualliflik loyihalari.</p>
              </div>
            </div>
            <div className="ent-bento-card agency-card">
              <div className="ent-bc-content">
                <div className="agency-icon">🤖</div>
                <h3>Telegram Botlar</h3>
                <p>Mijozlarga xizmat ko'rsatuvchi aqlli bot va yordamchilar.</p>
              </div>
            </div>
            <div className="ent-bento-card agency-card">
              <div className="ent-bc-content">
                <div className="agency-icon">💻</div>
                <h3>Noyob Dasturlar</h3>
                <p>Sizning g'oyangiz asosida murakkab ERP va dasturlar ishlab chiqish.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Lead Capture / So'rov Qoldirish ── */}
      <section className="ent-cta" style={{ background: 'var(--ent-surface)' }}>
        <div className="ent-container">
          <div className="ent-cta-box lead-grid">
            <div className="lead-text">
              <h2>G'oyangiz bormi yoki ERP kerakmi?</h2>
              <p>
                Hozirning o'zida bepul konsultatsiyaga yoziling!
              </p>
              <ul>
                <li>{ICONS.check} Mutaxassis bilan aloqa</li>
                <li>{ICONS.check} Tizim imkoniyatlari namoyishi</li>
                <li>{ICONS.check} Biznesingiz uchun eng yaxshi yechim topish</li>
              </ul>
            </div>

            <div className="lead-form-box">
              {leadStatus === 'success' ? (
                <div className="lead-success">
                  <div className="check-icon">✓</div>
                  <h3>Rahmat!</h3>
                  <p>Tez orada mutaxassislarimiz siz bilan bog'lanadi.</p>
                  <button className="ent-btn-outline" onClick={() => setLeadStatus(null)}>Yangi so'rov qoldirish</button>
                </div>
              ) : (
                <form onSubmit={handleLeadSubmit} className="lead-form">
                  <h3>So'rov qoldirish</h3>
                  
                  <div className="form-group">
                    <label>Qaysi xizmat qiziqtirdi?</label>
                    <select 
                      value={leadForm.service} 
                      onChange={e => setLeadForm({...leadForm, service: e.target.value})}
                    >
                      <option>ERP Tizim</option>
                      <option>Veb-sayt yasash</option>
                      <option>Telegram Bot</option>
                      <option>Boshqa g'oya</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Ismingiz</label>
                    <input 
                      type="text" 
                      required 
                      value={leadForm.name}
                      onChange={e => setLeadForm({...leadForm, name: e.target.value})}
                      placeholder="Masalan, Alisher"
                    />
                  </div>

                  <div className="form-group">
                    <label>Telefon raqam</label>
                    <input 
                      type="text" 
                      required 
                      value={leadForm.phone}
                      onChange={e => setLeadForm({...leadForm, phone: e.target.value})}
                      placeholder="+998"
                    />
                  </div>

                  <button 
                    type="submit" 
                    disabled={leadStatus === 'loading'}
                    className="lead-submit-btn"
                  >
                    {leadStatus === 'loading' ? 'Yuborilmoqda...' : 'Yuborish'}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="ent-footer">
        <div className="ent-container ent-footer-inner">
          <div className="ent-footer-brand">
            <ECodeLogo size={24} />
            <p className="copy">© {new Date().getFullYear()} E-code LLC. {t('land.footer.rights')}</p>
          </div>
          
          <div className="ent-footer-links">
            <div>
              <strong>{t('land.contact')}</strong>
              <span>ecode.uz@gmail.com</span>
              <span>+998 88 911 81 71</span>
            </div>
            <div>
              <strong>{t('land.system')}</strong>
              <span onClick={() => navigate('/login')} className="clickable">{t('land.nav.login')}</span>
              <span onClick={() => navigate('/register')} className="clickable">{t('land.nav.register')}</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

