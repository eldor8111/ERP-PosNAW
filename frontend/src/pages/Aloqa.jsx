import { useNavigate } from 'react-router-dom'
import LandingLayout from '../components/LandingLayout'
import { useLang } from '../i18n'
import { useSeo } from '../hooks/useSeo'
import { Clock, MapPin, MessageCircleHeart, Phone, Send, ArrowRight } from 'lucide-react'

export default function Aloqa() {
  const navigate = useNavigate()
  const { t } = useLang()

  useSeo(
    "Aloqa – Biz bilan Bog'laning | E-code",
    "E-code bilan bog'laning: ERP, POS, veb sayt yoki Telegram bot bo'yicha maslahat oling."
  )

  const contacts = [
    {
      id: 'telegram',
      icon: (
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-16 h-16 drop-shadow-md transition-transform duration-500 group-hover:scale-110">
          <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.247-2.01 9.471c-.148.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L6.24 14.26l-2.95-.924c-.642-.2-.654-.643.136-.953l11.526-4.445c.537-.194 1.006.131.61.31z" />
        </svg>
      ),
      name: 'Telegram',
      handle: '@ecode_uz',
      desc: t('aloqa.tezkormu.d') || 'Tezkor murojaat va maslahat uchun',
      url: 'https://t.me/ecode_uz',
      color: '#229ED9',
      bg: 'linear-gradient(135deg, rgba(34,158,217,0.1) 0%, rgba(34,158,217,0.02) 100%)',
      action: 'Yozish',
    },
    {
      id: 'whatsapp',
      icon: (
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-16 h-16 drop-shadow-md transition-transform duration-500 group-hover:scale-110">
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
        </svg>
      ),
      name: 'WhatsApp',
      handle: '+998 88 911 81 71',
      desc: t('aloqa.qo.d') || 'Qo\'ng\'iroq yoki xabar uchun',
      url: 'https://wa.me/998889118171',
      color: '#25D366',
      bg: 'linear-gradient(135deg, rgba(37,211,102,0.1) 0%, rgba(37,211,102,0.02) 100%)',
      action: 'Xabar yozish',
    },
    {
      id: 'instagram',
      icon: (
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-16 h-16 drop-shadow-md transition-transform duration-500 group-hover:scale-110">
          <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
        </svg>
      ),
      name: 'Instagram',
      handle: '@ecode.uz',
      desc: t('aloqa.loyihala.d') || 'Loyihalarimiz va yangiliklar',
      url: 'https://instagram.com/ecode.uz',
      color: '#E1306C',
      bg: 'linear-gradient(135deg, rgba(225,48,108,0.1) 0%, rgba(225,48,108,0.02) 100%)',
      action: 'Kuzatish',
    },
    {
      id: 'phone',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-16 h-16 drop-shadow-md transition-transform duration-500 group-hover:scale-110">
          <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
        </svg>
      ),
      name: 'Telefon',
      handle: '+998 88 911 81 71',
      desc: t('aloqa.ishkunla.d') || 'Ish kunlari 09:00 – 18:00',
      url: 'tel:+998889118171',
      color: '#2563eb',
      bg: 'linear-gradient(135deg, rgba(37,99,235,0.1) 0%, rgba(37,99,235,0.02) 100%)',
      action: 'Qo\'ng\'iroq',
    },
    {
      id: 'email',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-16 h-16 drop-shadow-md transition-transform duration-500 group-hover:scale-110">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
          <polyline points="22,6 12,13 2,6" />
        </svg>
      ),
      name: 'Email',
      handle: 'ecode.uz@gmail.com',
      desc: t('aloqa.rasmiymu.d') || 'Rasmiy murojaat va hamkorlik',
      url: 'mailto:ecode.uz@gmail.com',
      color: '#EA4335',
      bg: 'linear-gradient(135deg, rgba(234,67,53,0.1) 0%, rgba(234,67,53,0.02) 100%)',
      action: 'Xat yuborish',
    },
    {
      id: 'youtube',
      icon: (
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-16 h-16 drop-shadow-md transition-transform duration-500 group-hover:scale-110">
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
        </svg>
      ),
      name: 'YouTube',
      handle: 'E-code LLC',
      desc: t('aloqa.darslikl.d') || 'Darsliklar va ko\'rsatmalar',
      url: 'https://youtube.com/@ecode_uz',
      color: '#FF0000',
      bg: 'linear-gradient(135deg, rgba(255,0,0,0.1) 0%, rgba(255,0,0,0.02) 100%)',
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
      <section className="relative py-32 overflow-hidden flex items-center bg-slate-900 min-h-[60vh]">
        {/* Abstract shapes & glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-blue-600/30 blur-[120px] rounded-[100%] pointer-events-none opacity-50" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[400px] h-[400px] bg-emerald-500/20 blur-[100px] rounded-full pointer-events-none" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />

        <div className="max-w-[1400px] mx-auto px-4 w-full relative z-10 text-center flex flex-col items-center">
          
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500/10 border border-blue-500/20 rounded-full text-blue-400 font-semibold text-sm mb-8 animate-[fadeInDown_0.6s_ease-out_both]">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
            </span>
            {t('aloqa.tag') || "Biz har doim aloqadamiz"}
          </div>

          <h1 className="text-5xl md:text-7xl font-extrabold text-white tracking-[-0.04em] mb-6 leading-[1.1] animate-[fadeInUp_0.7s_ease-out_0.1s_both]">
            {t('aloqa.hero.title1') || "Savollaringiz bormi?"} <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-400 to-emerald-400 inline-block mt-2">
              {t('aloqa.hero.title2') || "Keling, suhbatlashamiz!"}
            </span>
          </h1>

          <p className="text-lg md:text-xl text-slate-300 max-w-2xl mx-auto mb-10 leading-relaxed animate-[fadeInUp_0.7s_ease-out_0.2s_both]">
            {t('aloqa.hero.desc') || "Sizning biznesingiz uchun eng yaxshi yechimni tanlashda yordam berishga tayyormiz. O'zingizga qulay tarmoq orqali yozing."}
          </p>

          <button onClick={() => document.getElementById('contact-cards-section').scrollIntoView({behavior: 'smooth'})} className="group relative inline-flex items-center justify-center gap-3 px-8 py-4 bg-white text-slate-900 font-bold rounded-2xl overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-[0_0_40px_rgba(255,255,255,0.3)] animate-[fadeInUp_0.7s_ease-out_0.3s_both]">
            <MessageCircleHeart size={22} className="text-blue-600 transition-transform group-hover:scale-110" />
            <span className="text-[17px]">Bog'lanish usullari</span>
          </button>

        </div>
      </section>

      {/* Modern Bento Grid Cards Section */}
      <section id="contact-cards-section" className="py-24 bg-slate-50 relative">
        <div className="max-w-[1400px] mx-auto px-4">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-black text-slate-900 tracking-tight mb-4">
              {t('aloqa.ch.title') || "Biz bilan bog'lanish tarmog'i"}
            </h2>
            <p className="text-lg text-slate-500 max-w-2xl mx-auto">
              {t('aloqa.ch.desc') || "Sizga qaysi platforma qulay bo'lsa, o'sha orqali bizga yozing."}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {contacts.map((c, idx) => (
              <a
                key={c.id}
                href={c.url}
                target={c.url.startsWith('http') ? '_blank' : '_self'}
                rel="noreferrer"
                className="group relative overflow-hidden bg-white rounded-[32px] p-8 transition-all duration-500 hover:-translate-y-2"
                style={{
                  boxShadow: '0 10px 40px -10px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02)',
                  border: '1px solid rgba(0,0,0,0.04)'
                }}
              >
                {/* Background Gradient Hover Effect */}
                <div 
                  className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                  style={{ background: c.bg }}
                />

                <div className="relative z-10 flex flex-col h-full justify-between">
                  <div>
                    <div 
                      className="mb-8 w-24 h-24 flex items-center justify-center rounded-[24px] bg-slate-50 shadow-inner group-hover:bg-white transition-colors duration-500"
                      style={{ color: c.color }}
                    >
                      {c.icon}
                    </div>
                    
                    <h3 className="text-3xl font-black text-slate-900 mb-2 group-hover:text-slate-800 transition-colors">
                      {c.name}
                    </h3>
                    <p className="text-slate-500 text-lg mb-6 leading-relaxed">
                      {c.desc}
                    </p>
                  </div>

                  <div>
                    <div className="inline-flex items-center gap-2 font-bold text-lg mb-4" style={{ color: c.color }}>
                      {c.handle}
                    </div>
                    <div className="flex items-center justify-between w-full">
                      <span className="font-semibold text-slate-900">{c.action}</span>
                      <div 
                        className="w-12 h-12 rounded-full flex items-center justify-center text-white transform transition-transform duration-500 group-hover:translate-x-2 shadow-lg"
                        style={{ backgroundColor: c.color }}
                      >
                        <ArrowRight size={20} />
                      </div>
                    </div>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Info & Location Bento Box */}
      <section className="py-24 bg-white">
        <div className="max-w-[1400px] mx-auto px-4">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            
            {/* Working Hours - Takes 2 columns */}
            <div className="lg:col-span-2 bg-slate-900 text-white rounded-[32px] p-10 relative overflow-hidden group shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-purple-600/20 opacity-50 transition-opacity duration-500 group-hover:opacity-100" />
              <div className="relative z-10">
                <div className="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center text-blue-400 mb-8 backdrop-blur-md">
                  <Clock size={32} />
                </div>
                <h2 className="text-3xl font-black mb-3">
                  {t('aloqa.hours.title') || 'Ish vaqti'}
                </h2>
                <p className="text-white/60 text-lg mb-10">
                  {t('aloqa.hours.sub') || 'Dam olish kunlarisiz doimiy texnik yordam'}
                </p>

                <div className="space-y-6">
                  {workingHours.map((w, i) => (
                    <div key={i} className={`flex items-center justify-between border-b border-white/10 pb-4 last:border-0 ${!w.active ? 'opacity-40' : ''}`}>
                      <span className="font-medium text-lg text-white/90">{w.day}</span>
                      <span className="font-bold text-lg flex items-center gap-2">
                        {w.active && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>}
                        {w.time}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Map Location - Takes 3 columns */}
            <div className="lg:col-span-3 bg-slate-50 border border-slate-200 rounded-[32px] p-4 flex flex-col relative overflow-hidden group">
              <div className="flex-1 rounded-[24px] overflow-hidden relative min-h-[400px]">
                <iframe 
                  className="w-full h-full absolute inset-0 grayscale opacity-80 group-hover:grayscale-0 group-hover:opacity-100 transition-all duration-700" 
                  src="https://www.google.com/maps/embed?pb=!1m14!1m12!1m3!1d1813.8304565553844!2d66.91392589946706!3d39.65617586413823!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!5e1!3m2!1sen!2s!4v1780287990785!5m2!1sen!2s" 
                  style={{ border: 0 }} 
                  allowFullScreen 
                  loading="lazy" 
                  referrerPolicy="no-referrer-when-downgrade"
                ></iframe>
                
                {/* Floating Info Box on Map */}
                <div className="absolute top-6 left-6 bg-white/90 backdrop-blur-md border border-white p-6 rounded-2xl shadow-xl max-w-sm">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 bg-red-100 text-red-600 rounded-xl flex items-center justify-center">
                      <MapPin size={20} />
                    </div>
                    <h3 className="text-xl font-black text-slate-900">{t('aloqa.loc.title') || 'Bizning ofisimiz'}</h3>
                  </div>
                  <p className="text-slate-600 text-sm font-medium">Samarqand shahar, ko'cha nomi 123-uy. Tashrif buyurishdan oldin qo'ng'iroq qiling.</p>
                </div>
              </div>
            </div>
            
          </div>
        </div>
      </section>

      {/* FAQ Modern Section */}
      <section className="py-24 bg-slate-50 border-t border-slate-200">
        <div className="max-w-[1000px] mx-auto px-4">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-black text-slate-900 tracking-tight mb-4">
              {t('aloqa.faq.title') || "Ko'p beriladigan savollar"}
            </h2>
          </div>

          <div className="space-y-4">
            {faq.map((item, i) => (
              <div key={i} className="bg-white border border-slate-200 p-8 rounded-[24px] shadow-sm hover:shadow-md transition-shadow duration-300">
                <h3 className="text-xl font-bold text-slate-900 mb-3 flex items-start gap-4">
                  <span className="text-blue-600 font-black">Q.</span>
                  {item.q}
                </h3>
                <p className="text-slate-600 text-lg leading-relaxed pl-8">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final Premium CTA */}
      <section className="py-24 bg-white relative overflow-hidden">
        <div className="absolute inset-0 bg-blue-600">
          <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.1)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.1)_1px,transparent_1px)] bg-[size:40px_40px] opacity-20 [mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,#000_70%,transparent_100%)]" />
        </div>
        
        <div className="max-w-[1000px] mx-auto px-4 relative z-10 text-center text-white">
          <h2 className="text-5xl md:text-6xl font-black tracking-[-0.02em] mb-6">
            {t('aloqa.cta.title') || "Biznesingizni keyingi bosqichga olib chiqing!"}
          </h2>
          <p className="text-xl text-blue-100 mb-12 max-w-2xl mx-auto">
            {t('aloqa.cta.desc') || "Hoziroq biz bilan bog'laning va loyihangizni birgalikda muhokama qilamiz."}
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
            <a
              href="https://t.me/ecode_uz"
              target="_blank"
              rel="noreferrer"
              className="group flex items-center gap-3 bg-white text-blue-900 text-lg font-bold px-10 py-5 rounded-2xl hover:scale-105 hover:shadow-[0_20px_40px_rgba(0,0,0,0.2)] transition-all duration-300"
            >
              <Send size={24} className="text-blue-600 group-hover:translate-x-1 transition-transform" />
              {t('aloqa.cta.btn1') || "Telegram orqali yozish"}
            </a>
            <a
              href="tel:+998889118171"
              className="flex items-center gap-3 bg-blue-700/50 backdrop-blur-md border border-blue-500/30 text-white text-lg font-bold px-10 py-5 rounded-2xl hover:bg-blue-700 hover:scale-105 transition-all duration-300"
            >
              <Phone size={24} className="animate-pulse" />
              +998 88 911 81 71
            </a>
          </div>
        </div>
      </section>
    </LandingLayout>
  )
}