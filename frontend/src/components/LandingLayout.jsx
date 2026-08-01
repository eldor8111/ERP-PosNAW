import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import ECodeLogo from './ECodeLogo'
import FlagIcon from './FlagIcon'
import Preloader from './Preloader'
import { MapPin, Phone, Mail, Send, ChevronDown } from 'lucide-react'

const TelegramIcon = ({ className = "w-4 h-4" }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
)

const InstagramIcon = ({ className = "w-4 h-4" }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
)

const FacebookIcon = ({ className = "w-4 h-4" }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
  </svg>
)

const LinkedinIcon = ({ className = "w-4 h-4" }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
    <rect x="2" y="9" width="4" height="12" />
    <circle cx="4" cy="4" r="2" />
  </svg>
)

const YoutubeIcon = ({ className = "w-4 h-4" }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M22.54 6.42a2.78 2.78 0 0 0-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 0 0-1.94 2A29 29 0 0 0 1 11.75a29 29 0 0 0 .46 5.33A2.78 2.78 0 0 0 3.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 0 0 1.94-2 29 29 0 0 0 .46-5.25 29 29 0 0 0-.46-5.33z" />
    <polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02" fill="currentColor" />
  </svg>
)

const PaymeLogo = () => (
  <svg viewBox="0 0 240 75" className="h-7 w-auto hover:scale-105 transition-transform cursor-pointer drop-shadow-sm">
    <path d="M 12 0 L 205 0 L 240 37.5 L 205 75 L 12 75 A 12 12 0 0 1 0 63 L 0 12 A 12 12 0 0 1 12 0 Z" fill="#2BD7F7" />
    <text x="108" y="53" fill="#000000" fontSize="44" fontWeight="900" fontStyle="italic" textAnchor="middle" fontFamily="sans-serif">payme</text>
  </svg>
)

const ClickLogo = () => (
  <svg viewBox="0 0 170 54" className="h-7 w-auto bg-white rounded-lg px-3 py-1 hover:scale-105 transition-transform cursor-pointer shadow-xs">
    <g transform="translate(6, 6)">
      <rect x="0" y="0" width="40" height="40" rx="14" fill="#0066FF" transform="rotate(45 20 20)" />
      <circle cx="20" cy="20" r="7.5" fill="#FFFFFF" />
    </g>
    <text x="68" y="37" fill="#000000" fontSize="34" fontWeight="900" fontFamily="sans-serif">click</text>
  </svg>
)

const HumoLogo = () => (
  <svg viewBox="0 0 170 100" className="h-8 w-auto rounded-lg hover:scale-105 transition-transform cursor-pointer shadow-xs">
    <rect width="170" height="100" rx="10" fill="#2C3E50" />
    <path d="M 135 5 Q 170 30 148 95 C 165 72 170 42 135 5 Z" fill="#E5C158" />
    <path d="M 152 20 Q 172 48 158 95 C 170 72 172 48 152 20 Z" fill="#E5C158" opacity="0.85" />
    <text x="68" y="62" fill="#E5C158" fontSize="34" fontWeight="900" textAnchor="middle" fontFamily="sans-serif" letterSpacing="2">HUMO</text>
  </svg>
)

const UzcardLogo = () => (
  <svg viewBox="0 0 180 54" className="h-7 w-auto bg-white rounded-lg px-2.5 py-1 hover:scale-105 transition-transform cursor-pointer shadow-xs">
    <g transform="translate(8, 4) scale(0.44)">
      <path d="M 30 18 V 54 A 20 20 0 0 0 70 54 V 41 H 54 V 31 H 84 V 54 A 34 34 0 0 1 16 54 V 18 Z" fill="#1B365D" />
      <path d="M 68 18 A 16 16 0 0 1 84 34 H 68 Z" fill="#F58220" />
    </g>
    <text x="112" y="37" fill="#1B365D" fontSize="26" fontWeight="900" textAnchor="middle" fontFamily="system-ui, -apple-system, sans-serif" letterSpacing="1">UZCARD</text>
  </svg>
)

const VisaLogo = () => (
  <svg viewBox="0 0 150 48" className="h-7 w-auto bg-white rounded-lg px-2.5 py-1 hover:scale-105 transition-transform cursor-pointer shadow-xs">
    <text x="75" y="37" fill="#1434CB" fontSize="42" fontWeight="900" fontStyle="italic" textAnchor="middle" fontFamily="sans-serif" letterSpacing="-1">VISA</text>
  </svg>
)

const LangIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
  </svg>
)

export default function LandingLayout({ children }) {
  const { t, lang, setLang, LANGUAGES } = useLang()
  const navigate = useNavigate()
  const location = useLocation()
  const [scrolled, setScrolled] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const langRef = useRef(null)
  const currentLang = LANGUAGES.find(l => l.code === lang)

  const isChaqqon = location.pathname === '/chaqqon-pro'
  const loginUrl = isChaqqon ? 'https://chaqqonpro.e-code.uz/' : 'https://savdo.e-code.uz/login'
  const registerUrl = isChaqqon ? 'https://chaqqonpro.e-code.uz/' : 'https://savdo.e-code.uz/register'

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (langRef.current && !langRef.current.contains(e.target)) {
        setLangOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const navLinks = [
    { label: t('land.nav.erp') || 'ERP Tizim', path: '/' },
    { label: t('land.nav.integrations') || 'Integratsiyalar', path: '/integratsiyalar' },
    { label: t('land.nav.about') || 'Biz haqimizda', path: '/biz-haqimizda' },
    { label: t('land.nav.news') || 'Yangiliklar', path: '/yangiliklar' },
    { label: t('land.nav.contact') || 'Aloqa', path: '/aloqa' },
  ]

  return (
    <div className="min-h-screen relative bg-[#F8FAFC] font-sans text-slate-900 selection:bg-emerald-500 selection:text-white">
      {/* Initial Splash Preloader */}
      <Preloader />

      {/* Navbar */}
      <nav className={`fixed w-full px-5 top-0 z-100 backdrop-blur-xl border-b transition-all duration-300 ${scrolled
        ? 'bg-white/90 border-slate-200/80 shadow-[0_4px_25px_rgba(0,0,0,0.06)]'
        : 'bg-white/70 border-slate-200/40 backdrop-blur-md shadow-xs'
        }`}>
        <div className="max-w-[1400px] w-full mx-auto relative z-10">
          <div className="py-3.5 md:py-4 flex justify-between w-full items-center gap-6 xl:gap-12">
            <span onClick={() => navigate('/')} className="cursor-pointer flex items-center shrink-0">
              <ECodeLogo size={40} />
            </span>

            {/* Desktop Nav Links */}
            <div className="hidden lg:flex items-center gap-8 xl:gap-12 mx-auto">
              {navLinks.map(link => (
                <a
                  key={link.path}
                  onClick={() => navigate(link.path)}
                  className={`cursor-pointer text-nowrap no-underline font-bold text-[15px] xl:text-[17px] transition-colors duration-200 relative py-2 group ${link.path === location.pathname ? 'text-emerald-600 font-extrabold' : 'text-slate-700 hover:text-emerald-600'
                    }`}
                >
                  {link.label}
                  <span className={`absolute bottom-[-4px] left-0 h-0.5 bg-emerald-600 rounded-sm transition-all duration-300 ${link.path === location.pathname ? 'w-full' : 'w-0 group-hover:w-full'}`} />
                </a>
              ))}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-4 shrink-0">
              {/* Lang switcher with flag SVG */}
              <div className="relative" ref={langRef}>
                <button
                  onClick={() => setLangOpen(!langOpen)}
                  className="bg-slate-100/90 border border-slate-200/80 flex items-center gap-2 text-[14px] text-slate-800 cursor-pointer px-3.5 py-2 rounded-xl font-bold transition-all duration-200 hover:bg-slate-200/80 shadow-xs"
                >
                  <FlagIcon code={currentLang?.code} className="w-5 h-3.5 rounded-xs" />
                  <span className="font-semibold text-sm hidden sm:inline">{currentLang?.label}</span>
                  <ChevronDown className="w-4 h-4 text-slate-500" />
                </button>
                {langOpen && (
                  <div className="absolute right-0 top-full mt-2 bg-white border border-slate-200/80 rounded-2xl p-1.5 shadow-[0_20px_40px_rgba(0,0,0,0.12)] min-w-[150px] animate-[fadeInUp_0.2s_ease-out_forwards] origin-top-right z-50 flex flex-col gap-1">
                    {LANGUAGES.map(l => (
                      <button
                        key={l.code}
                        onClick={() => { setLang(l.code); setLangOpen(false); }}
                        className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-left cursor-pointer text-sm font-semibold transition-all ${
                          lang === l.code ? 'bg-slate-100/90 text-emerald-700 font-bold' : 'text-slate-700 hover:bg-slate-50 hover:text-emerald-600'
                        }`}
                      >
                        <FlagIcon code={l.code} className="w-5 h-3.5 rounded-xs shrink-0" />
                        <span className="font-medium text-slate-800">{l.label}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                className="hidden lg:inline-flex bg-transparent text-slate-700 border-none font-bold text-[15px] xl:text-[16px] px-4 py-2.5 rounded-xl cursor-pointer transition-all duration-200 hover:text-emerald-600 hover:bg-black/5"
                onClick={() => window.location.href = loginUrl}
              >
                {t('land.nav.login') || 'Kirish'}
              </button>
              <button
                className="hidden lg:inline-flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 via-blue-500 to-indigo-600 text-white border-none font-bold px-6 py-2.5 rounded-xl cursor-pointer transition-all duration-300 shadow-md shadow-blue-500/25 hover:shadow-lg hover:shadow-blue-500/35 text-[15px] xl:text-[16px] relative overflow-hidden hover:scale-[1.03] hover:from-blue-700 hover:to-indigo-700 active:scale-95"
                onClick={() => window.location.href = registerUrl}
              >
                {t('land.nav.register') || 'Boshlash'}
              </button>

              {/* Hamburger */}
              <button
                className="lg:hidden bg-none border-none text-[28px] text-slate-900 cursor-pointer"
                onClick={() => setMobileMenu(!mobileMenu)}
              >
                ☰
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        <div className={`flex justify-between flex-col gap-4 h-[calc(100vh-50px)] bg-white px-6 py-6 border-l border-black/8 absolute transition-all duration-300 top-full w-full max-w-90 z-80 ${mobileMenu ? 'right-0' : '-right-90'}`}>
          <div className='flex flex-col gap-4'>
            {navLinks.map(link => (
              <a
                key={link.path}
                onClick={() => { navigate(link.path); setMobileMenu(false); }}
                className="cursor-pointer no-underline text-slate-900 text-base font-semibold py-2 border-b border-black/5 last:border-none"
              >
                {link.label}
              </a>
            ))}
          </div>
          <div className='flex flex-col'>
            <button
              onClick={() => window.location.href = loginUrl}
              className="py-3 rounded-xl font-bold text-[15px] mt-2 cursor-pointer border border-black/8 bg-white"
            >
              {t('land.nav.login') || 'Kirish'}
            </button>
            <button
              className="py-3 rounded-xl font-bold text-[15px] mt-1 cursor-pointer border-none bg-linear-to-br from-blue-600 to-blue-400 text-white"
              onClick={() => window.location.href = registerUrl}
            >
              {t('land.nav.register') || 'Boshlash'}
            </button>
          </div>
        </div>
      </nav>

      {/* Page Content */}
      {children}

      {/* Footer */}
      <footer className="bg-[#141518] text-slate-300 border-t border-white/10 pt-16 pb-10">
        <div className="max-w-[1400px] mx-auto px-6">
          {/* Main Footer Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-12 pb-14 border-b border-white/10">
            
            {/* 1. Manzil */}
            <div className="flex flex-col gap-4">
              <span className="text-slate-300 font-bold text-sm md:text-base tracking-wider uppercase">Manzil</span>
              <div className="flex items-start gap-3 text-slate-200">
                <MapPin className="w-5 h-5 text-emerald-500 shrink-0 mt-1" />
                <span className="leading-relaxed text-sm md:text-base font-medium">
                  Samarqand shahar, Vokzal. <br />
                  <span className="text-slate-400 text-sm">Mo'ljal: Oltin Samarqand yonida</span>
                </span>
              </div>
            </div>

            {/* 2. Aloqa va Savollar */}
            <div className="flex flex-col gap-4">
              <span className="text-slate-300 font-bold text-sm md:text-base tracking-wider uppercase">Aloqa va Savollar</span>
              <div className="flex items-center gap-3 text-white">
                <Phone className="w-5 h-5 text-emerald-500 shrink-0" />
                <a href="tel:+998889118171" className="hover:text-emerald-400 text-base md:text-lg font-bold transition-colors no-underline text-white">+998 88 911 81 71</a>
              </div>
              <div className="flex items-center gap-3 text-slate-200">
                <Mail className="w-5 h-5 text-emerald-500 shrink-0" />
                <a href="mailto:ecode.uz@gmail.com" className="hover:text-emerald-400 text-sm md:text-base font-semibold transition-colors no-underline text-slate-200">ecode.uz@gmail.com</a>
              </div>
              <span className="text-xs text-slate-400 font-medium">24/7 Texnik yordam va maslahat</span>
            </div>

            {/* 3. Ijtimoiy tarmoqlar & To'lov tizimlari */}
            <div className="flex flex-col gap-4">
              <span className="text-slate-300 font-bold text-sm md:text-base tracking-wider uppercase">Ijtimoiy tarmoqlar</span>
              <div className="flex items-center gap-3 flex-wrap">
                <a href="https://t.me/Ecodenews" target="_blank" rel="noreferrer" title="Telegram" className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-300 hover:bg-emerald-500 hover:text-white hover:border-emerald-500 transition-all">
                  <TelegramIcon className="w-5 h-5" />
                </a>
                <a href="https://www.instagram.com/ecode_uz/" target="_blank" rel="noreferrer" title="Instagram" className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-300 hover:bg-pink-600 hover:text-white hover:border-pink-600 transition-all">
                  <InstagramIcon className="w-5 h-5" />
                </a>
                <a href="https://facebook.com" target="_blank" rel="noreferrer" title="Facebook" className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-300 hover:bg-blue-600 hover:text-white hover:border-blue-600 transition-all">
                  <FacebookIcon className="w-5 h-5" />
                </a>
                <a href="https://linkedin.com" target="_blank" rel="noreferrer" title="LinkedIn" className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-300 hover:bg-blue-500 hover:text-white hover:border-blue-500 transition-all">
                  <LinkedinIcon className="w-5 h-5" />
                </a>
                <a href="https://youtube.com" target="_blank" rel="noreferrer" title="YouTube" className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-300 hover:bg-red-600 hover:text-white hover:border-red-600 transition-all">
                  <YoutubeIcon className="w-5 h-5" />
                </a>
              </div>

              <span className="text-slate-300 font-bold text-xs md:text-sm tracking-wider uppercase mt-3">To'lov tizimlari</span>
              <div className="flex items-center gap-2.5 flex-wrap">
                <PaymeLogo />
                <ClickLogo />
                <HumoLogo />
                <UzcardLogo />
                <VisaLogo />
              </div>
            </div>

            {/* 4. Xizmatlar & Navigatsiya */}
            <div className="flex flex-col gap-3">
              <span className="text-slate-300 font-bold text-sm md:text-base tracking-wider uppercase">Xizmatlar</span>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
                {navLinks.map(link => (
                  <a
                    key={link.path}
                    onClick={() => navigate(link.path)}
                    className="cursor-pointer text-slate-300 hover:text-emerald-400 text-sm md:text-base font-medium transition-colors"
                  >
                    {link.label}
                  </a>
                ))}
                <a onClick={() => window.location.href = loginUrl} className="cursor-pointer text-slate-300 hover:text-emerald-400 text-sm md:text-base font-medium transition-colors">
                  Kirish
                </a>
                <a onClick={() => window.location.href = registerUrl} className="cursor-pointer text-slate-300 hover:text-emerald-400 text-sm md:text-base font-medium transition-colors">
                  Boshlash
                </a>
              </div>
            </div>

          </div>

          {/* Bottom Bar */}
          <div className="pt-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-slate-400">
            <div>
              E-code © {new Date().getFullYear()}. Barcha huquqlar himoyalangan.
            </div>
            <div className="flex items-center gap-6">
              <a href="#" className="hover:text-slate-200 transition-colors no-underline text-slate-400">Ommaviy taklif</a>
              <a href="#" className="hover:text-slate-200 transition-colors no-underline text-slate-500">Maxfiylik siyosati</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
