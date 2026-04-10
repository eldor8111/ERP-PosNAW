import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import './service-pages.css'
import { useLang } from '../i18n'

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

export default function TelegramBotlar() {
  const navigate = useNavigate()
  const { t } = useLang()
  const [activeBot, setActiveBot] = useState(0)

  const botTypes = [
    { icon: '🛒', color: '#10b981', bg: 'rgba(16,185,129,0.08)', title: t('tg.b1.t'), desc: t('tg.b1.d'), examples: [t('tg.b1.f1'), t('tg.b1.f2'), t('tg.b1.f3'), t('tg.b1.f4'), t('tg.b1.f5')], popular: false },
    { icon: '🤖', color: '#2563eb', bg: 'rgba(37,99,235,0.08)', title: t('tg.b2.t'), desc: t('tg.b2.d'), examples: [t('tg.b2.f1'), t('tg.b2.f2'), t('tg.b2.f3'), t('tg.b2.f4'), t('tg.b2.f5')], popular: true },
    { icon: '📢', color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', title: t('tg.b3.t'), desc: t('tg.b3.d'), examples: [t('tg.b3.f1'), t('tg.b3.f2'), t('tg.b3.f3'), t('tg.b3.f4'), t('tg.b3.f5')], popular: false },
    { icon: '📊', color: '#8b5cf6', bg: 'rgba(139,92,246,0.08)', title: t('tg.b4.t'), desc: t('tg.b4.d'), examples: [t('tg.b4.f1'), t('tg.b4.f2'), t('tg.b4.f3'), t('tg.b4.f4'), t('tg.b4.f5')], popular: false },
    { icon: '🎓', color: '#0891b2', bg: 'rgba(8,145,178,0.08)', title: t('tg.b5.t'), desc: t('tg.b5.d'), examples: [t('tg.b5.f1'), t('tg.b5.f2'), t('tg.b5.f3'), t('tg.b5.f4'), t('tg.b5.f5')], popular: false },
    { icon: '💼', color: '#ef4444', bg: 'rgba(239,68,68,0.08)', title: t('tg.b6.t'), desc: t('tg.b6.d'), examples: [t('tg.b6.f1'), t('tg.b6.f2'), t('tg.b6.f3'), t('tg.b6.f4'), t('tg.b6.f5')], popular: false },
  ]

  const features = [
    { icon: '⚡', title: t('tg.feat.1.t'), desc: t('tg.feat.1.d') },
    { icon: '🔗', title: t('tg.feat.2.t'), desc: t('tg.feat.2.d') },
    { icon: '📈', title: t('tg.feat.3.t'), desc: t('tg.feat.3.d') },
    { icon: '🛡️', title: t('tg.feat.4.t'), desc: t('tg.feat.4.d') },
    { icon: '🌍', title: t('tg.feat.5.t'), desc: t('tg.feat.5.d') },
    { icon: '♾️', title: t('tg.feat.6.t'), desc: t('tg.feat.6.d') },
  ]

  const showcase = [
    { emoji: '🏪', name: t('tg.port.1.t'), desc: t('tg.port.1.d'), users: t('tg.port.1.u'), color: '#10b981' },
    { emoji: '🎓', name: t('tg.port.2.t'), desc: t('tg.port.2.d'), users: t('tg.port.2.u'), color: '#2563eb' },
    { emoji: '🏥', name: t('tg.port.3.t'), desc: t('tg.port.3.d'), users: t('tg.port.3.u'), color: '#8b5cf6' },
  ]

  const plans = [
    { name: t('tg.p1.n'), badge: `⚡ ${t('tg.p1.b')}`, label: t('tg.p1.l'), hint: t('tg.p1.h'), popular: false, color: '#10b981', desc: t('tg.p1.d'), features: [t('tg.p1.f1'), t('tg.p1.f2'), t('tg.p1.f3'), t('tg.p1.f4'), t('tg.p1.f5')] },
    { name: t('tg.p2.n'), badge: `🔥 ${t('tg.p2.b')}`, label: t('tg.p2.l'), hint: t('tg.p2.h'), popular: true, color: '#2563eb', desc: t('tg.p2.d'), features: [t('tg.p2.f1'), t('tg.p2.f2'), t('tg.p2.f3'), t('tg.p2.f4'), t('tg.p2.f5'), t('tg.p2.f6')] },
    { name: t('tg.p3.n'), badge: `🏢 ${t('tg.p3.b')}`, label: t('tg.p3.l'), hint: t('tg.p3.h'), popular: false, color: '#8b5cf6', desc: t('tg.p3.d'), features: [t('tg.p3.f1'), t('tg.p3.f2'), t('tg.p3.f3'), t('tg.p3.f4'), t('tg.p3.f5'), t('tg.p3.f6')] },
  ]

  return (
    <LandingLayout>
      {/* Hero */}
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #0f172a 0%, #064e3b 50%, #0f172a 100%)' }}>
        <div className="sp-hero-bg-dots" />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>{t('tg.bc.home')}</span>
            <span className="sp-bc-sep">›</span>
            <span>{t('tg.bc.current')}</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(16,185,129,0.3)', color: '#6ee7b7', borderColor: 'rgba(16,185,129,0.4)' }} dangerouslySetInnerHTML={{ __html: t('tg.tag') }} />
          <h1 className="sp-hero-title">
            {t('tg.hero.title1')}<br />
            <span className="sp-gradient-text-green">{t('tg.hero.title2')}</span> {t('tg.hero.title3')}
          </h1>
          <p className="sp-hero-desc">{t('tg.hero.desc')}</p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">{t('tg.hero.stat1.val')}</span><span className="sp-stat-lbl">{t('tg.hero.stat1.lbl')}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('tg.hero.stat2.val')}</span><span className="sp-stat-lbl">{t('tg.hero.stat2.lbl')}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('tg.hero.stat3.val')}</span><span className="sp-stat-lbl">{t('tg.hero.stat3.lbl')}</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">{t('tg.hero.stat4.val')}</span><span className="sp-stat-lbl">{t('tg.hero.stat4.lbl')}</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" style={{ background: 'linear-gradient(135deg, #059669, #10b981)' }}
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              {t('tg.hero.btn1')} <ArrowRight />
            </button>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-ghost">
              💬 {t('tg.hero.btn2')}
            </a>
          </div>
        </div>
      </section>

      {/* Bot Types */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('tg.bot.tag')}</div>
            <h2 className="sp-section-title">{t('tg.bot.title')}</h2>
            <p className="sp-section-desc">{t('tg.bot.desc')}</p>
          </div>

          {/* Bot tabs + preview */}
          <div className="sp-bot-wrap">
            <div className="sp-bot-tabs">
              {botTypes.map((bot, idx) => (
                <button
                  key={idx}
                  className={`sp-bot-tab ${activeBot === idx ? 'active' : ''}`}
                  style={activeBot === idx ? { borderLeftColor: bot.color, color: bot.color, background: bot.bg } : {}}
                  onClick={() => setActiveBot(idx)}
                >
                  <span className="sp-bot-tab-icon">{bot.icon}</span>
                  <span className="sp-bot-tab-name">{bot.title}</span>
                  {bot.popular && <span className="sp-bot-popular">🔥</span>}
                </button>
              ))}
            </div>

            <div className="sp-bot-preview" key={activeBot}>
              {/* Telegram mockup */}
              <div className="sp-tg-mockup">
                <div className="sp-tg-header" style={{ background: `linear-gradient(135deg, ${botTypes[activeBot].color}cc, ${botTypes[activeBot].color})` }}>
                  <div className="sp-tg-avatar">{botTypes[activeBot].icon}</div>
                  <div>
                    <div className="sp-tg-name">{botTypes[activeBot].title}</div>
                    <div className="sp-tg-status">● Online</div>
                  </div>
                </div>
                <div className="sp-tg-body">
                  <div className="sp-tg-msg sp-tg-msg-in">
                    <div className="sp-tg-bubble">Salom! Sizga qanday yordam bera olaman? 👋</div>
                    <div className="sp-tg-time">10:00</div>
                  </div>
                  <div className="sp-tg-msg sp-tg-msg-out">
                    <div className="sp-tg-bubble-out">Mahsulotlar ro'yxatini ko'rsating</div>
                    <div className="sp-tg-time">10:01</div>
                  </div>
                  <div className="sp-tg-msg sp-tg-msg-in">
                    <div className="sp-tg-bubble">{t('tg.mock.opt')}</div>
                    <div className="sp-tg-btns">
                      {botTypes[activeBot].examples.slice(0, 3).map((ex, i) => (
                        <div key={i} className="sp-tg-btn" style={{ borderColor: botTypes[activeBot].color, color: botTypes[activeBot].color }}>
                          {ex}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="sp-bot-details">
                <h3 style={{ color: botTypes[activeBot].color }}>{botTypes[activeBot].title}</h3>
                <p>{botTypes[activeBot].desc}</p>
                <div className="sp-bot-examples">
                  {botTypes[activeBot].examples.map((ex, i) => (
                    <div key={i} className="sp-bot-example">
                      <span style={{ color: botTypes[activeBot].color }}><CheckIcon /></span> {ex}
                    </div>
                  ))}
                </div>
                <button
                  className="sp-btn-primary"
                  style={{ background: `linear-gradient(135deg, ${botTypes[activeBot].color}, ${botTypes[activeBot].color}cc)` }}
                  onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
                >
                  {t('tg.mock.btn')} <ArrowRight />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('tg.feat.tag')}</div>
            <h2 className="sp-section-title">{t('tg.feat.title')}</h2>
          </div>
          <div className="sp-features-grid">
            {features.map((f, i) => (
              <div key={i} className="sp-feature-card">
                <div className="sp-fc-icon">{f.icon}</div>
                <h3 className="sp-fc-title">{f.title}</h3>
                <p className="sp-fc-desc">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Showcase */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('tg.port.tag')}</div>
            <h2 className="sp-section-title">{t('tg.port.title')}</h2>
          </div>
          <div className="sp-showcase-grid">
            {showcase.map((item, i) => (
              <div key={i} className="sp-showcase-card">
                <div className="sp-showcase-emoji" style={{ background: `${item.color}20`, color: item.color }}>{item.emoji}</div>
                <h3 className="sp-showcase-name" style={{ color: item.color }}>{item.name}</h3>
                <p className="sp-showcase-desc">{item.desc}</p>
                <div className="sp-showcase-users">{item.users}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('tg.plan.tag')}</div>
            <h2 className="sp-section-title">{t('tg.plan.title')}</h2>
            <p className="sp-section-desc">{t('tg.plan.desc')}</p>
          </div>

          <div className="sp-price-notice">
            <span className="sp-price-notice-icon">💬</span>
            <div>
              <strong>{t('tg.plan.notice.title')}</strong>
              <p>{t('tg.plan.notice.desc')}</p>
            </div>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-price-contact-btn">
              💬 {t('tg.plan.notice.btn')}
            </a>
          </div>

          <div className="sp-tariff-grid">
            {plans.map(plan => (
              <div key={plan.name} className={`sp-tariff-card ${plan.popular ? 'sp-tariff-popular' : ''}`}>
                {plan.popular && <div className="sp-tariff-badge">🔥 {t('tg.p2.b')}</div>}
                <div className="sp-tariff-badge-top">{plan.badge}</div>
                <div className="sp-tariff-name" style={{ color: plan.color }}>{plan.name}</div>
                <div className="sp-tariff-desc">{plan.desc}</div>
                <div className="sp-tariff-price-contact" style={{ borderColor: `${plan.color}30`, background: `${plan.color}08` }}>
                  <span className="sp-tariff-contact-label" style={{ color: plan.color }}>{plan.label}</span>
                  <span className="sp-tariff-contact-hint">{plan.hint}</span>
                </div>
                <div className="sp-tariff-features">
                  {plan.features.map((f, i) => (
                    <div key={i} className="sp-tariff-feature">
                      <span className="sp-tf-check" style={{ color: plan.color }}><CheckIcon /></span> {f}
                    </div>
                  ))}
                </div>
                <button
                  className="sp-tariff-btn"
                  style={plan.popular ? { background: `linear-gradient(135deg, ${plan.color}, ${plan.color}cc)`, color: 'white' } : { borderColor: plan.color, color: plan.color }}
                  onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
                >
                  {t('tg.plan.notice.btn')} →
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>


      {/* CTA */}
      <section className="sp-cta-section sp-cta-green" id="sp-contact">
        <div className="ent-container">
          <div className="sp-cta-box">
            <h2>{t('tg.cta.title')}</h2>
            <p>{t('tg.cta.desc')}</p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white">
                🤖 {t('tg.cta.btn1')} <ArrowRight />
              </a>
              <a href="tel:+998889118171" className="sp-btn-tg">
                📞 {t('tg.cta.btn2')}
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
