import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import './service-pages.css'
import './aloqa.css'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'

export default function Aloqa() {
  const navigate = useNavigate()
  const { t } = useLang()
  useSeo(
    "Aloqa – Biz bilan Bog'laning | E-code",
    "E-code bilan bog'laning: ERP, POS, veb sayt yoki Telegram bot bo'yicha maslahat oling. Telefon, Telegram yoki email orqali murojaat qiling."
  )

const contacts = [
  {
    id: 'telegram',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.247-2.01 9.471c-.148.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.24 14.26l-2.95-.924c-.642-.2-.654-.643.136-.953l11.526-4.445c.537-.194 1.006.131.61.31z"/>
      </svg>
    ),
    name: 'Telegram',
    handle: '@ecode_uz',
    desc: t('aloqa.tezkormu.d') || 'Tezkor murojaat va maslahat uchun',
    url: 'https://t.me/ecode_uz',
    color: '#229ED9',
    bg: 'rgba(34,158,217,0.08)',
    action: 'Yozish',
  },
  {
    id: 'instagram',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
      </svg>
    ),
    name: 'Instagram',
    handle: '@ecode.uz',
    desc: t('aloqa.loyihala.d') || 'Loyihalarimiz va yangiliklar',
    url: 'https://instagram.com/ecode.uz',
    color: '#E1306C',
    bg: 'rgba(225,48,108,0.08)',
    action: 'Kuzatish',
  },
  {
    id: 'whatsapp',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
      </svg>
    ),
    name: 'WhatsApp',
    handle: '+998 88 911 81 71',
    desc: t('aloqa.qo.d') || 'Qo\'ng\'iroq yoki xabar uchun',
    url: 'https://wa.me/998889118171',
    color: '#25D366',
    bg: 'rgba(37,211,102,0.08)',
    action: 'Xabar yozish',
  },
  {
    id: 'email',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
        <polyline points="22,6 12,13 2,6"/>
      </svg>
    ),
    name: 'Email',
    handle: 'ecode.uz@gmail.com',
    desc: t('aloqa.rasmiymu.d') || 'Rasmiy murojaat va hamkorlik uchun',
    url: 'mailto:ecode.uz@gmail.com',
    color: '#EA4335',
    bg: 'rgba(234,67,53,0.08)',
    action: 'Xat yuborish',
  },
  {
    id: 'phone',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
      </svg>
    ),
    name: 'Telefon',
    handle: '+998 88 911 81 71',
    desc: t('aloqa.ishkunla.d') || 'Ish kunlari 09:00 – 18:00',
    url: 'tel:+998889118171',
    color: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    action: 'Qo\'ng\'iroq',
  },
  {
    id: 'youtube',
    icon: (
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
      </svg>
    ),
    name: 'YouTube',
    handle: 'E-code LLC',
    desc: t('aloqa.darslikl.d') || 'Darsliklar va tizim ko\'rsatmalari',
    url: 'https://youtube.com/@ecode_uz',
    color: '#FF0000',
    bg: 'rgba(255,0,0,0.08)',
    action: 'Obuna bo\'lish',
  },
]

const workingHours = [
  { day: 'Dushanba – Juma', time: '09:00 – 18:00', active: true },
  { day: 'Shanba', time: '10:00 – 15:00', active: true },
  { day: 'Yakshanba', time: 'Dam olish', active: false },
]

const faq = [
  {
    q: 'Demo ko\'rish mumkinmi?',
    a: 'Ha, Telegram orqali murojaat qiling — biz siz uchun bepul demo seans o\'tkazamiz.',
  },
  {
    q: 'Qancha vaqtda javob berasiz?',
    a: 'Odatda Telegram va WhatsApp orqali 30 daqiqa ichida javob beramiz. Email orqali 24 soat.',
  },
  {
    q: 'Ofisga kelish mumkinmi?',
    a: 'Ha, oldindan murojaat qilgan holda ofisimizni ziyorat qilishingiz mumkin. Toshkent shahri.',
  },
  {
    q: 'Texnik qo\'llab-quvvatlash bormi?',
    a: 'Ha, barcha mijozlarimiz uchun Telegram orqali texnik yordam ko\'rsatamiz.',
  },
]

  return (
    <LandingLayout>
      {/* Hero */}
      <section className="aloqa-hero">
        <div className="aloqa-hero-bg" />
        <div className="ent-container aloqa-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>{t('aloqa.bc.home') || 'Bosh sahifa'}</span>
            <span className="sp-bc-sep">›</span>
            <span>{t('aloqa.bc.current') || 'Aloqa'}</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(37,99,235,0.25)', color: '#93c5fd', borderColor: 'rgba(37,99,235,0.4)' }} dangerouslySetInnerHTML={{ __html: t('aloqa.tag') || '📬 &nbsp;Biz bilan bog\'laning' }} />
          <h1 className="sp-hero-title">
            {t('aloqa.hero.title1') || 'Savollaringiz bormi?'}<br />
            <span className="sp-gradient-text">{t('aloqa.hero.title2') || 'Bog\'laning!'}</span>
          </h1>
          <p className="sp-hero-desc">
            {t('aloqa.hero.desc') || 'Istalgan murojaat uchun qulay kanal orqali yozing yoki qo\'ng\'iroq qiling. Biz sizga 30 daqiqa ichida javob beramiz.'}
          </p>
        </div>
      </section>

      {/* Contact Cards */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('aloqa.ch.tag') || 'Murojaat kanallari'}</div>
            <h2 className="sp-section-title">{t('aloqa.ch.title') || 'Qaysi orqali bog\'lanasiz?'}</h2>
            <p className="sp-section-desc">{t('aloqa.ch.desc') || 'Hammasi ishlaydi — qulay bo\'lgani bo\'yicha tanlang'}</p>
          </div>
          <div className="aloqa-grid">
            {contacts.map((c) => (
              <a
                key={c.id}
                href={c.url}
                target={c.url.startsWith('http') ? '_blank' : '_self'}
                rel="noreferrer"
                className="aloqa-card"
                style={{ '--aloqa-color': c.color, '--aloqa-bg': c.bg }}
              >
                <div className="aloqa-card-top">
                  <div className="aloqa-icon" style={{ color: c.color, background: c.bg }}>
                    {c.icon}
                  </div>
                  <div className="aloqa-badge" style={{ color: c.color, background: c.bg }}>
                    {c.action} →
                  </div>
                </div>
                <h3 className="aloqa-name" style={{ color: c.color }}>{c.name}</h3>
                <div className="aloqa-handle">{c.handle}</div>
                <p className="aloqa-desc">{c.desc}</p>
                <div className="aloqa-cta" style={{ background: c.color }}>
                  {c.action}
                </div>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Working Hours + FAQ */}
      <section className="sp-section sp-section-alt">
        <div className="ent-container aloqa-info-grid">

          {/* Ish vaqti */}
          <div className="aloqa-hours-card">
            <div className="aloqa-info-icon">🕐</div>
            <h2 className="aloqa-info-title">{t('aloqa.hours.title') || 'Ish vaqti'}</h2>
            <p className="aloqa-info-sub">{t('aloqa.hours.sub') || 'Telegram va WhatsApp orqali tezroq javob beramiz'}</p>
            <div className="aloqa-hours-list">
              {workingHours.map((w, i) => (
                <div key={i} className={`aloqa-hour-row ${!w.active ? 'aloqa-hour-off' : ''}`}>
                  <span className="aloqa-hour-day">{w.day}</span>
                  <span className="aloqa-hour-time" style={{ color: w.active ? '#10b981' : '#ef4444' }}>
                    {w.active ? '●' : '○'} {w.time}
                  </span>
                </div>
              ))}
            </div>
            <div className="aloqa-hours-note">
              <span>💬</span>
              <span>Telegram orqali murojaat har doim qabul qilinadi</span>
            </div>
          </div>

          {/* Joylashuv */}
          <div className="aloqa-location-card">
            <div className="aloqa-info-icon">📍</div>
            <h2 className="aloqa-info-title">{t('aloqa.loc.title') || 'Manzil'}</h2>
            <p className="aloqa-info-sub">{t('aloqa.loc.sub') || 'Oldindan murojaat qilib keling'}</p>
            <div className="aloqa-map-placeholder">
              <div className="aloqa-map-pin">📍</div>
              <div className="aloqa-map-text">
                <strong>Toshkent shahri</strong>
                <span>O'zbekiston</span>
              </div>
            </div>
            <div className="aloqa-location-links">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="aloqa-loc-btn">
                💬 Manzilni so'rash
              </a>
            </div>
          </div>

        </div>
      </section>

      {/* FAQ */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">{t('aloqa.faq.tag') || 'Ko\'p so\'raladigan savollar'}</div>
            <h2 className="sp-section-title">{t('aloqa.faq.title') || 'Tez-tez beriladigan savollar'}</h2>
          </div>
          <div className="aloqa-faq-grid">
            {faq.map((item, i) => (
              <div key={i} className="aloqa-faq-card">
                <div className="aloqa-faq-q">
                  <span className="aloqa-faq-icon">❓</span>
                  {item.q}
                </div>
                <p className="aloqa-faq-a">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="sp-cta-section">
        <div className="ent-container">
          <div className="sp-cta-box">
            <h2>{t('aloqa.cta.title') || 'Hali ham savolingiz bormi?'}</h2>
            <p>{t('aloqa.cta.desc') || 'Telegram orqali yozing — 30 daqiqa ichida javob beramiz.'}</p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white">
                <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: 20, height: 20 }}>
                  <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.247-2.01 9.471c-.148.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.24 14.26l-2.95-.924c-.642-.2-.654-.643.136-.953l11.526-4.445c.537-.194 1.006.131.61.31z"/>
                </svg>
                {t('aloqa.cta.btn1') || 'Telegram yozish'}
              </a>
              <a href="tel:+998889118171" className="sp-btn-tg">
                📞 +998 88 911 81 71
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}
