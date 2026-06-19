import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import ECodeLogo from './ECodeLogo'

const LangIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
    <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
  </svg>
)

export default function LandingLayout({ children }) {
  const { t, lang, setLang, LANGUAGES } = useLang()
  const navigate = useNavigate()
  const location = useLocation()
  const [scrolled, setScrolled] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const currentLang = LANGUAGES.find(l => l.code === lang)

  const isChaqqon = location.pathname === '/chaqqon-pro'
  const loginUrl = isChaqqon ? 'https://chaqqonpro.e-code.uz/' : 'https://savdo.e-code.uz/login'
  const registerUrl = isChaqqon ? 'https://chaqqonpro.e-code.uz/' : 'https://savdo.e-code.uz/register'

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const navLinks = [
    { label: t('land.nav.erp') || 'ERP Tizim', path: '/' },
    { label: 'Eviko', path: '/chaqqon-pro'},
    { label: t('land.nav.websites') || 'Veb-saytlar', path: '/veb-saytlar' },
    { label: t('land.nav.bots') || 'Telegram Botlar', path: '/telegram-botlar' },
    { label: t('land.nav.custom') || 'Noyob Dasturlar', path: '/noyob-dasturlar' },
    { label: t('land.nav.contact') || 'Aloqa', path: '/aloqa' },
  ]

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Navbar */}
      <nav className={`fixed w-full top-0 z-100 backdrop-blur-xl border-b transition-all duration-300 animate-[slideUp_0.6s_ease-out_0.1s_backwards] ${
        scrolled
          ? 'bg-white/80 border-black/8 shadow-[0_4px_20px_rgba(0,0,0,0.03)]'
          : 'bg-white border-transparent'
      }`}>
        <div className="max-w-[1400px] w-full mx-auto relative z-10">
          <div className="h-20 flex items-center gap-10">
            <span onClick={() => navigate('/')} className="cursor-pointer">
              <ECodeLogo size={36} />
            </span> 

            {/* Desktop Nav Links */}
            <div className="hidden lg:flex items-center gap-9 mx-auto">
              {navLinks.map(link => (
                <a
                  key={link.path}
                  onClick={() => navigate(link.path)}
                  className={`cursor-pointer text-nowrap no-underline font-semibold text-[16px] transition-colors duration-200 relative py-2 group ${
                    link.path === location.pathname ? 'text-green-700' : 'text-slate-500 hover:text-green-700'
                  }`}
                >
                  {link.label}
                  <span className="absolute bottom-[-4px] left-0 w-0 h-0.5 bg-green-700 rounded-sm transition-all duration-300 group-hover:w-full" />
                </a>
              ))}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3">
              {/* Lang switcher */}
              <div className="relative">
                <button
                  onClick={() => setLangOpen(!langOpen)}
                  className="bg-white border border-black/8 flex items-center gap-1.5 text-[13px] text-slate-900 cursor-pointer px-3 py-1 rounded-lg font-semibold transition-all duration-200 hover:bg-slate-100"
                >
                  {currentLang?.short} <LangIcon />
                </button>
                {langOpen && (
                  <div className="absolute right-0 top-full mt-2 bg-white border border-black/8 rounded-xl p-1.5 shadow-[0_20px_40px_rgba(0,0,0,0.08)] min-w-[140px] animate-[fadeInUp_0.2s_ease-out_forwards] origin-top-right z-50">
                    {LANGUAGES.map(l => (
                      <button
                        key={l.code}
                        onClick={() => { setLang(l.code); setLangOpen(false); }}
                        className="w-full text-left bg-none border-none px-2.5 py-2.5 rounded-lg cursor-pointer text-sm text-slate-500 font-medium hover:bg-slate-50 hover:text-blue-600"
                      >
                        {l.flag} {l.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                className="hidden lg:inline-flex bg-transparent text-slate-500 border-none font-semibold px-4 py-2 rounded-xl cursor-pointer transition-all duration-200 hover:text-slate-900 hover:bg-black/3"
                onClick={() => window.location.href = loginUrl}
              >
                {t('land.nav.login') || 'Kirish'}
              </button>
              <button
                className="hidden lg:inline-flex items-center justify-center gap-2 bg-linear-to-br from-green-700 to-green-500 text-white border-none font-bold px-5 py-2 rounded-xl cursor-pointer transition-all duration-400 shadow-[0_10px_30px_rgba(37,99,235,0.15)] text-[15px] relative overflow-hidden hover:scale-[1.02] hover:shadow-[0_15px_30px_rgba(37,99,235,0.3)]"
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
        {mobileMenu && (
          <div className="flex flex-col gap-4 bg-white px-6 py-6 border-t border-black/8 shadow-[0_10px_30px_rgba(0,0,0,0.1)] absolute top-full left-0 w-full z-90 animate-[fadeDown_0.3s_ease-out]">
            {navLinks.map(link => (
              <a
                key={link.path}
                onClick={() => { navigate(link.path); setMobileMenu(false); }}
                className="cursor-pointer no-underline text-slate-900 text-base font-semibold py-2 border-b border-black/5 last:border-none"
              >
                {link.label}
              </a>
            ))}
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
        )}
      </nav>

      {/* Page Content */}
      {children}

      {/* Footer */}
      <footer className="bg-white border-t border-black/8 py-20 pb-[60px]">
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
          <div className="flex justify-between flex-wrap gap-[60px]">
            <div className="flex flex-col">
              <span onClick={() => navigate('/')} className="cursor-pointer">
                <ECodeLogo size={32} />
              </span>
              <p className="mt-6 text-[15px] text-slate-500">
                © {new Date().getFullYear()} E-code LLC. {t('land.footer.rights') || 'Barcha huquqlar himoyalangan.'}
              </p>
            </div>
            <div className="flex gap-20 flex-wrap">
              <div className="flex flex-col gap-4">
                <strong className="text-slate-900 text-base mb-3 font-bold uppercase">
                  {t('land.footer.services') || 'Xizmatlar'}
                </strong>
                {navLinks.map(link => (
                  <span
                    key={link.path}
                    onClick={() => navigate(link.path)}
                    className="cursor-pointer text-slate-500 text-[15px] transition-all duration-300 hover:text-blue-600 hover:translate-x-1"
                  >
                    {link.label}
                  </span>
                ))}
              </div>
              <div className="flex flex-col gap-4">
                <strong className="text-slate-900 text-base mb-3 font-bold uppercase">
                  {t('land.footer.contact') || 'Aloqa'}
                </strong>
                <span className="text-slate-500 text-[15px]">ecode.uz@gmail.com</span>
                <span className="text-slate-500 text-[15px]">+998 88 911 81 71</span>
              </div>
              <div className="flex flex-col gap-4">
                <strong className="text-slate-900 text-base mb-3 font-bold uppercase">
                  {t('land.footer.system') || 'Tizim'}
                </strong>
                <span
                  onClick={() => window.location.href = loginUrl}
                  className="cursor-pointer text-slate-500 text-[15px] transition-all duration-300 hover:text-blue-600 hover:translate-x-1"
                >
                  {t('land.nav.login') || 'Kirish'}
                </span>
                <span
                  onClick={() => window.location.href = registerUrl}
                  className="cursor-pointer text-slate-500 text-[15px] transition-all duration-300 hover:text-blue-600 hover:translate-x-1"
                >
                  {t('land.nav.register') || 'Boshlash'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
