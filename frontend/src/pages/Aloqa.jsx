import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'
import { Clock, MapPin, MessageCircleHeart, Phone, Send } from 'lucide-react'

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
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
          <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.247-2.01 9.471c-.148.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.24 14.26l-2.95-.924c-.642-.2-.654-.643.136-.953l11.526-4.445c.537-.194 1.006.131.61.31z" />
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
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
          <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
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
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
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
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
          <polyline points="22,6 12,13 2,6" />
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
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
          <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
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
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-full h-full">
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
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
      {/* Hero Section */}
      <section className="relative py-24 md:py-32 overflow-hidden min-h-[620px] flex items-center bg-gradient-to-br from-[#0f172a] via-[#1e3a8a] to-[#0f172a]">
        {/* Background Dots */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.08)_1px,transparent_1px)] bg-[size:28px_28px] pointer-events-none" />

        <div className="max-w-[1400px] flex flex-col justify-center h-[calc(100dvh-250px)] mx-auto px-4 w-full relative z-10 text-center">
          {/* Breadcrumb */}
          <div>
            <div className="inline-flex items-center gap-2 text-sm text-white/50 mb-6 font-medium">
              <span onClick={() => navigate('/')} className="cursor-pointer hover:opacity-100 opacity-60 transition-opacity">
                {t('aloqa.bc.home') || 'Bosh sahifa'}
              </span>
              <span className="opacity-60">›</span>
              <span>{t('aloqa.bc.current') || 'Aloqa'}</span>
            </div>

            {/* Tag Badge */}
            <div
              className="inline-block w-max ml-3 px-5 py-2 bg-blue-600/25 text-blue-300 border border-blue-600/40 rounded-full text-sm font-bold mb-8 animate-fade-in"
              dangerouslySetInnerHTML={{ __html: t('aloqa.tag') || '📬 &nbsp;Biz bilan bog\'laning' }}
            />
          </div>

          {/* Title */}
          <h1 className="text-[clamp(44px,7vw,72px)] font-black leading-[1.08] tracking-tight text-white mb-7 animate-[fadeInUp_0.7s_ease-out_0.1s_both]">
            {t('aloqa.hero.title1') || 'Savollaringiz bormi?'}<br />
            <span className="bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent inline-block">
              {t('aloqa.hero.title2') || 'Bog\'laning!'}
            </span>
          </h1>

          {/* Description */}
          <p className="text-lg md:text-xl text-white/72 max-w-[660px] mx-auto mb-12 leading-relaxed animate-[fadeInUp_0.7s_ease-out_0.2s_both]">
            {t('aloqa.hero.desc') || 'Istalgan murojaat uchun qulay kanal orqali yozing yoki qo\'ng\'iroq qiling. Biz sizga 30 daqiqa ichida javob beramiz.'}
          </p>

          <a
            href="#contact-cards-section"
            className="inline-flex items-center mx-auto w-max gap-2 bg-white/10 text-white border border-white/20 font-semibold text-base px-8 py-4 rounded-xl cursor-pointer transition-all duration-300 backdrop-blur-md hover:bg-white/15 hover:-translate-y-0.5"
          >
            <MessageCircleHeart size={20} /> Bog'lanish
          </a>
        </div>
      </section>

      {/* Contact Cards Section */}
      <section id='contact-cards-section' className="py-24 max-w-[1400px] mx-auto px-4">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-blue-600/10 border border-blue-600/15 rounded-full text-xs font-bold text-blue-600 mb-4 uppercase tracking-wider">
            {t('aloqa.ch.tag') || 'Murojaat kanallari'}
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight mb-3">
            {t('aloqa.ch.title') || 'Qaysi orqali bog\'lanasiz?'}
          </h2>
          <p className="text-base text-slate-500 max-w-[560px] mx-auto">
            {t('aloqa.ch.desc') || 'Hammasi ishlaydi — qulay bo\'lgani bo\'yicha tanlang'}
          </p>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {contacts.map((c) => (
            <a
              key={c.id}
              href={c.url}
              target={c.url.startsWith('http') ? '_blank' : '_self'}
              rel="noreferrer"
              className="group bg-white border border-slate-100 p-8 rounded-3xl shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-6">
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center p-3 transition-transform group-hover:scale-110 duration-300"
                    style={{ color: c.color, background: c.bg }}
                  >
                    {c.icon}
                  </div>
                  <div
                    className="text-xs font-bold px-3 py-1.5 rounded-full border border-transparent transition-colors group-hover:bg-transparent"
                    style={{ color: c.color, background: c.bg, borderColor: `${c.color}20` }}
                  >
                    {c.action} →
                  </div>
                </div>

                <h3 className="text-xl font-black mb-1" style={{ color: c.color }}>
                  {c.name}
                </h3>
                <div className="text-slate-800 font-bold text-base mb-3">
                  {c.handle}
                </div>
                <p className="text-slate-500 text-sm leading-relaxed mb-6">
                  {c.desc}
                </p>
              </div>

              <div
                className="w-full text-center text-white font-bold text-sm py-3.5 rounded-xl transition-all opacity-90 group-hover:opacity-100 shadow-md"
                style={{ background: c.color }}
              >
                {c.action}
              </div>
            </a>
          ))}
        </div>
      </section>

      {/* Working Hours & Location */}
      <section className="py-24 bg-gradient-to-b from-slate-50 to-white border-y border-black/[0.04]">
        <div className="max-w-[1400px] mx-auto px-4 grid grid-cols-1 lg:grid-cols-2 gap-8">

          {/* Working Hours Card */}
          <div className="bg-white flex flex-col justify-between border border-slate-100 p-8 md:p-10 rounded-[32px] shadow-sm">
            <div>
              <div className="w-12 h-12 text-green-600 bg-slate-50 border border-slate-100 rounded-2xl flex items-center justify-center text-xl mb-6 shadow-inner">
                <Clock size={26} />
              </div>
              <h2 className="text-2xl font-black text-slate-900 mb-2">
                {t('aloqa.hours.title') || 'Ish vaqti'}
              </h2>
              <p className="text-slate-500 text-sm mb-8">
                {t('aloqa.hours.sub') || 'Telegram va WhatsApp orqali tezroq javob beramiz'}
              </p>

              <div className="flex flex-col gap-4 mb-8">
                {workingHours.map((w, i) => (
                  <div
                    key={i}
                    className={`flex items-center justify-between pb-3 border-b border-slate-50 last:border-0 ${!w.active ? 'opacity-50' : ''}`}
                  >
                    <span className="font-semibold text-slate-700 text-[15px]">{w.day}</span>
                    <span
                      className="font-bold text-sm flex items-center gap-1.5"
                      style={{ color: w.active ? '#10b981' : '#ef4444' }}
                    >
                      <span className='animate-pulse'>{w.active ? '●' : '○'}</span> {w.time}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3 bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm text-slate-600 font-medium">
              <span className="text-base">
                <Send size={20} />
              </span>
              <span>Telegram orqali murojaat har doim qabul qilinadi</span>
            </div>
          </div>

          {/* Location Card */}
          <div className="bg-white border border-slate-100 p-8 md:p-10 rounded-[32px] shadow-sm flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 text-red-600 bg-slate-50 border border-slate-100 rounded-2xl flex items-center justify-center text-xl mb-6 shadow-inner">
                <MapPin size={26} />
              </div>
              <h2 className="text-2xl font-black text-slate-900 mb-2">
                {t('aloqa.loc.title') || 'Manzil'}
              </h2>
              <p className="text-slate-500 text-sm mb-6">
                {t('aloqa.loc.sub') || 'Oldindan murojaat qilib keling'}
              </p>

              {/* Map Placeholder */}
              <div className="h-full mb-6">
                <iframe className='rounded-2xl' src="https://www.google.com/maps/embed?pb=!1m14!1m12!1m3!1d1813.8304565553844!2d66.91392589946706!3d39.65617586413823!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!5e1!3m2!1sen!2s!4v1780287990785!5m2!1sen!2s" width="600" height="450" style={{ border: 0 }} allowFullScreen loading="lazy" referrerPolicy="no-referrer-when-downgrade"></iframe>
              </div>
            </div>

            <div className="w-full">
              <a
                href="https://t.me/ecode_uz"
                target="_blank"
                rel="noreferrer"
                className="inline-flex w-full items-center justify-center gap-2 bg-slate-900 text-white font-bold text-sm px-6 py-4 rounded-xl transition-all duration-300 hover:bg-slate-800 shadow-md"
              >
                <MapPin size={20} /> Manzilni so'rash
              </a>
            </div>
          </div>

        </div>
      </section>

      {/* FAQ Section */}
      <section className="py-24 max-w-[1400px] mx-auto px-4">
        <div className="text-center mb-16">
          <div className="inline-block px-4 py-1 bg-purple-600/10 border border-purple-600/15 rounded-full text-xs font-bold text-purple-600 mb-4 uppercase tracking-wider">
            {t('aloqa.faq.tag') || 'Ko\'p so\'raladigan savollar'}
          </div>
          <h2 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight">
            {t('aloqa.faq.title') || 'Tez-tez beriladigan savollar'}
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {faq.map((item, i) => (
            <div key={i} className="bg-white border border-slate-100 p-6 md:p-8 rounded-2xl shadow-sm">
              <div className="flex items-start gap-3 font-black text-slate-800 text-base md:text-lg mb-3">
                <span className="text-purple-600">❓</span>
                <h3>{item.q}</h3>
              </div>
              <p className="text-slate-500 text-sm leading-relaxed pl-7">
                {item.a}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Final CTA Section */}
      <section className="py-16 max-w-[1400px] mx-auto px-4 mb-12">
        <div className="bg-gradient-to-br from-blue-950 via-blue-900 to-slate-900 text-white rounded-[32px] p-8 md:p-16 text-center relative overflow-hidden shadow-xl">
          <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />

          <div className="relative z-10 max-w-2xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-4">
              {t('aloqa.cta.title') || 'Hali ham savolingiz bormi?'}
            </h2>
            <p className="text-white/80 text-base md:text-lg mb-10 leading-relaxed">
              {t('aloqa.cta.desc') || 'Telegram orqali yozing — 30 daqiqa ichida javob beramiz.'}
            </p>

            <div className="flex flex-wrap gap-4 justify-center">
              <a
                href="https://t.me/ecode_uz"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 bg-white text-blue-950 font-bold text-base px-8 py-4 rounded-xl transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
              >
                <Send size={20} />
                {t('aloqa.cta.btn1') || 'Telegram yozish'}
              </a>
              <a
                href="tel:+998889118171"
                className="inline-flex items-center gap-2 bg-white/10 text-white border border-white/25 font-semibold text-base px-8 py-4 rounded-xl transition-all duration-300 backdrop-blur-md hover:bg-white/20 hover:-translate-y-0.5"
              >
                <Phone size={20} /> +998 88 911 81 71
              </a>
            </div>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}