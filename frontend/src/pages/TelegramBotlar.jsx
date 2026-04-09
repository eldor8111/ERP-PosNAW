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

const botTypes = [
  {
    icon: '🛒',
    color: '#10b981',
    bg: 'rgba(16,185,129,0.08)',
    title: 'Onlayn Do\'kon Boti',
    desc: 'Telegram orqali tovarlarni ko\'rsatish, buyurtma qabul qilish va to\'lovni avtomatlashtirish.',
    examples: ['Mahsulotlar katalogi', 'Buyurtma qabul qilish', 'Payme/Click to\'lov', 'Buyurtma holati kuzatuvi', 'Yetkazib berish manzili'],
    popular: false,
  },
  {
    icon: '🤖',
    color: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    title: 'Mijozlarga Xizmat Boti',
    desc: 'Savollarga avtomatik javob, muammolarni hal qilish va operator bilan bog\'lanish.',
    examples: ['FAQ avtomatik javob', 'Tiket tizimi', 'Operator bilan ulash', 'Qo\'ng\'iroq jadval', 'Ko\'p tilli qo\'llab-quvvatlash'],
    popular: true,
  },
  {
    icon: '📢',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.08)',
    title: 'Marketing & Xabarnoma Boti',
    desc: 'Yangi mahsulotlar, aktsiyalar va yangiliklar haqida subscriberlarga avtomatik xabar.',
    examples: ['Bulk xabar yuborish', 'Segmentatsiya', 'Reaksiya va statistika', 'Jadval bo\'yicha xabarlar', 'Fayl va rasm yuborish'],
    popular: false,
  },
  {
    icon: '📊',
    color: '#8b5cf6',
    bg: 'rgba(139,92,246,0.08)',
    title: 'CRM & Analitika Boti',
    desc: 'ERP tizimingiz ma\'lumotlarini Telegram orqali ko\'rish va boshqarish.',
    examples: ['Kunlik hisobot', 'Sotuvlar statistikasi', 'Yangi buyurtma bildirishnoma', 'Ombor qoldiq alert', 'Xodim faoliyati'],
    popular: false,
  },
  {
    icon: '🎓',
    color: '#0891b2',
    bg: 'rgba(8,145,178,0.08)',
    title: 'Ta\'lim & Test Botlari',
    desc: 'O\'quv kurslari, testlar va sertifikatlash uchun interaktiv Telegram boti.',
    examples: ['Test va viktorina', 'Kurs materiallari', 'Progress kuzatuvi', 'Sertifikat berish', 'To\'lov integratsiyasi'],
    popular: false,
  },
  {
    icon: '💼',
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    title: 'HR & Ichki Korporativ Botlar',
    desc: 'Xodimlar uchun ichki vositalar: bayram simshollar, ta\'til ariza, ish topshiriq.',
    examples: ['Ta\'til ariza tizimi', 'Ish topshiriq berish', 'Xodim kuzatuvi', 'Maosh hisoboti', 'Korporativ xabarlar'],
    popular: false,
  },
]

const features = [
  { icon: '⚡', title: 'Tez ishlab chiqish', desc: '1-2 haftada tayyor bot yetkazib beramiz' },
  { icon: '🔗', title: 'API Integratsiya', desc: 'Mavjud tizim va bazangiz bilan ulash' },
  { icon: '📈', title: 'Analitika', desc: 'Bot statistikasi va foydalanuvchi faoliyati' },
  { icon: '🛡️', title: 'Xavfsizlik', desc: 'Shifrlangan aloqa va ma\'lumot himoyasi' },
  { icon: '🌍', title: 'Ko\'p tilli', desc: 'Uzbek, Rus, Ingliz tili qo\'llab-quvvatlash' },
  { icon: '♾️', title: 'Cheksiz foydalanuvchi', desc: 'Biznesiz o\'sib borgan boti bilan' },
]

const showcase = [
  { emoji: '🏪', name: 'BozorBot', desc: 'Onlayn savdo boti', users: '2,400+ foydalanuvchi', color: '#10b981' },
  { emoji: '🎓', name: 'O\'quv Boti', desc: 'Ta\'lim platformasi', users: '1,800+ talaba', color: '#2563eb' },
  { emoji: '🏥', name: 'Klinika Boti', desc: 'Navbat yozish tizimi', users: '3,100+ bemor', color: '#8b5cf6' },
]

export default function TelegramBotlar() {
  const navigate = useNavigate()
  const [activeBot, setActiveBot] = useState(0)

  return (
    <LandingLayout>
      {/* Hero */}
      <section className="sp-hero" style={{ background: 'linear-gradient(135deg, #0f172a 0%, #064e3b 50%, #0f172a 100%)' }}>
        <div className="sp-hero-bg-dots" />
        <div className="ent-container sp-hero-inner">
          <div className="sp-breadcrumb">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer', opacity: 0.6 }}>Bosh sahifa</span>
            <span className="sp-bc-sep">›</span>
            <span>Telegram Botlar</span>
          </div>
          <div className="sp-tag" style={{ background: 'rgba(16,185,129,0.3)', color: '#6ee7b7', borderColor: 'rgba(16,185,129,0.4)' }}>
            🤖 &nbsp;Aqlli Telegram Bot Ishlab Chiqish
          </div>
          <h1 className="sp-hero-title">
            Biznesingizni<br />
            <span className="sp-gradient-text-green">Telegram orqali</span> avtomatlashtiring
          </h1>
          <p className="sp-hero-desc">
            32 milliondan ortiq o'zbekistonliklar har kun Telegram ishlatadilar. 
            Mijozlaringizni ana shu platform orqali xizmat qiling, soting, xabardor qiling.
          </p>
          <div className="sp-hero-stats">
            <div className="sp-stat"><span className="sp-stat-val">30+</span><span className="sp-stat-lbl">Yaratilgan botlar</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">15K+</span><span className="sp-stat-lbl">Bot foydalanuvchilari</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">7 kun</span><span className="sp-stat-lbl">O'rtacha yetkazib berish</span></div>
            <div className="sp-stat-div" />
            <div className="sp-stat"><span className="sp-stat-val">24/7</span><span className="sp-stat-lbl">Bot ishlash vaqti</span></div>
          </div>
          <div className="sp-hero-ctas">
            <button className="sp-btn-primary" style={{ background: 'linear-gradient(135deg, #059669, #10b981)' }}
              onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}>
              Bot buyurtma berish <ArrowRight />
            </button>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-ghost">
              💬 Maslahat olish
            </a>
          </div>
        </div>
      </section>

      {/* Bot Types */}
      <section className="sp-section">
        <div className="ent-container">
          <div className="sp-section-head">
            <div className="sp-section-tag">Bot turlari</div>
            <h2 className="sp-section-title">Qanday botlar yaratamiz?</h2>
            <p className="sp-section-desc">Sizning biznesingizga mos bot turini tanlang</p>
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
                    <div className="sp-tg-bubble">Albatta! Quyidagi bo'limlardan birini tanlang 👇</div>
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
                  Bu bot turini buyurtma berish <ArrowRight />
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
            <div className="sp-section-tag">Imkoniyatlar</div>
            <h2 className="sp-section-title">Nima uchun E-code Boti?</h2>
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
            <div className="sp-section-tag">Portfolio</div>
            <h2 className="sp-section-title">Ishlab chiqilgan botlar</h2>
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
            <div className="sp-section-tag">Rejalar</div>
            <h2 className="sp-section-title">Bot xizmati rejalari</h2>
            <p className="sp-section-desc">Narx bot murakkabligiga, integratsiyalarga va qo'llab-quvvatlash muddatiga qarab belgilanadi</p>
          </div>

          <div className="sp-price-notice">
            <span className="sp-price-notice-icon">💬</span>
            <div>
              <strong>Bepul narx hisob-kitobi</strong>
              <p>Bot talablaringizni aytib bering — biz loyihangizga mos narxni hisoblab beramiz. Hech qanday yashirin to'lovlar yo'q.</p>
            </div>
            <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-price-contact-btn">
              💬 Narxni so'rash
            </a>
          </div>

          <div className="sp-tariff-grid">
            {[
              {
                name: 'Oddiy Bot',
                badge: '⚡ Tez yetkazib berish',
                label: 'Murojaat asosida',
                hint: 'Funksiyalar soniga qarab narx belgilanadi',
                popular: false,
                color: '#10b981',
                desc: 'Asosiy funksiyali bot',
                features: ['Mahsulotlar katalogi', 'Buyurtma qabul qilish', 'Admin panel', 'Telegram bildirishnoma', '1 oy qo\'llab-quvvatlash'],
              },
              {
                name: 'Pro Bot',
                badge: '🔥 Eng mashhur',
                label: 'Kelishilgan narxda',
                hint: 'To\'lov integratsiyasi va analitika bilan',
                popular: true,
                color: '#2563eb',
                desc: 'To\'liq funksiyali bot tizimi',
                features: ['Barcha asosiy funksiyalar', 'To\'lov integratsiyasi (Payme/Click)', 'Statistika va analitika', 'Ko\'p tilli qo\'llab-quvvatlash', 'API integratsiya', '3 oy qo\'llab-quvvatlash'],
              },
              {
                name: 'Enterprise',
                badge: '🏢 Yirik loyiha',
                label: 'Individual narx',
                hint: 'Bepul texnik tahlil va narx taklif',
                popular: false,
                color: '#8b5cf6',
                desc: 'Murakkab custom yechimlar',
                features: ['Custom bot arxitekturasi', 'CRM integratsiya', 'ERP bog\'lash', 'Maxsus funksiyalar', 'Dedicated server', '12 oy qo\'llab-quvvatlash'],
              },
            ].map(t => (
              <div key={t.name} className={`sp-tariff-card ${t.popular ? 'sp-tariff-popular' : ''}`}>
                {t.popular && <div className="sp-tariff-badge">🔥 Eng mashhur</div>}
                <div className="sp-tariff-badge-top">{t.badge}</div>
                <div className="sp-tariff-name" style={{ color: t.color }}>{t.name}</div>
                <div className="sp-tariff-desc">{t.desc}</div>
                <div className="sp-tariff-price-contact" style={{ borderColor: `${t.color}30`, background: `${t.color}08` }}>
                  <span className="sp-tariff-contact-label" style={{ color: t.color }}>{t.label}</span>
                  <span className="sp-tariff-contact-hint">{t.hint}</span>
                </div>
                <div className="sp-tariff-features">
                  {t.features.map((f, i) => (
                    <div key={i} className="sp-tariff-feature">
                      <span className="sp-tf-check" style={{ color: t.color }}><CheckIcon /></span> {f}
                    </div>
                  ))}
                </div>
                <button
                  className="sp-tariff-btn"
                  style={t.popular ? { background: `linear-gradient(135deg, ${t.color}, ${t.color}cc)`, color: 'white' } : { borderColor: t.color, color: t.color }}
                  onClick={() => { const el = document.getElementById('sp-contact'); if(el) el.scrollIntoView({behavior:'smooth'}); }}
                >
                  Narxni so'rash →
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
            <h2>Botingizni bugun boshlaylik</h2>
            <p>Telegram yozing — bepul maslahat va loyiha tahlilini qilamiz.</p>
            <div className="sp-cta-btns">
              <a href="https://t.me/ecode_uz" target="_blank" rel="noreferrer" className="sp-btn-white">
                🤖 @ecode_uz ga yozish <ArrowRight />
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
