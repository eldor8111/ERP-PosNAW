import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import ECodeLogo from './ECodeLogo'

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
    { label: t('land.nav.contact') || 'Aloqa', path: '/aloqa' },
  ]

  return (
    <div className="min-h-screen relative overflow-hidden bg-slate-900 text-slate-100 font-sans">
      {/* Navbar */}
      <nav className={`fixed w-full px-5 top-0 z-100 backdrop-blur-xl border-b transition-all duration-300 animate-[slideUp_0.6s_ease-out_0.1s_backwards] ${scrolled
        ? 'bg-slate-900/90 border-white/10 shadow-[0_4px_30px_rgba(0,0,0,0.5)]'
        : 'bg-transparent border-transparent'
        }`}>
        <div className="max-w-[1400px] w-full mx-auto relative z-10">
          <div className="py-3 md:py-4 xl:py-5 flex justify-between w-full items-center gap-5 xl:gap-10">
            <span onClick={() => navigate('/')} className="cursor-pointer">
              <ECodeLogo size={42} showText={false} />
            </span>

            {/* Desktop Nav Links */}
            <div className="hidden lg:flex items-center gap-8 xl:gap-12 mx-auto">
              {navLinks.map(link => (
                <a
                  key={link.path}
                  onClick={() => navigate(link.path)}
                  className={`cursor-pointer text-nowrap no-underline font-medium text-[15px] xl:text-[16px] transition-colors duration-200 relative py-2 group ${link.path === location.pathname ? 'text-blue-400' : 'text-slate-300 hover:text-white'
                    }`}
                >
                  {link.label}
                  <span className="absolute bottom-0 left-0 w-0 h-[2px] bg-blue-500 rounded-sm transition-all duration-300 group-hover:w-full" />
                </a>
              ))}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-4">
              {/* Lang switcher */}
              <div className="relative">
                <button
                  onClick={() => setLangOpen(!langOpen)}
                  className="bg-slate-800 border border-white/10 flex items-center gap-2 text-[13px] text-white cursor-pointer px-4 py-2 rounded-xl font-medium transition-all duration-200 hover:bg-slate-700 hover:border-white/20 shadow-sm"
                >
                  {currentLang?.short} <LangIcon />
                </button>
                {langOpen && (
                  <div className="absolute right-0 top-full mt-2 bg-slate-800 border border-white/10 rounded-xl p-1.5 shadow-[0_20px_40px_rgba(0,0,0,0.4)] min-w-[140px] animate-[fadeInUp_0.2s_ease-out_forwards] origin-top-right z-50">
                    {LANGUAGES.map(l => (
                      <button
                        key={l.code}
                        onClick={() => { setLang(l.code); setLangOpen(false); }}
                        className="w-full text-left bg-transparent border-none px-3 py-2.5 rounded-lg cursor-pointer text-sm text-slate-300 font-medium hover:bg-slate-700 hover:text-white transition-colors"
                      >
                        {l.flag} {l.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                className="hidden lg:inline-flex bg-transparent text-slate-300 border-none font-medium px-5 py-2.5 rounded-xl cursor-pointer transition-all duration-200 hover:text-white hover:bg-white/5"
                onClick={() => window.location.href = loginUrl}
              >
                {t('land.nav.login') || 'Kirish'}
              </button>
              <button
                className="hidden lg:inline-flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 to-blue-500 text-white border border-blue-400/20 font-semibold px-6 py-2.5 rounded-xl cursor-pointer transition-all duration-300 shadow-[0_0_20px_rgba(37,99,235,0.3)] text-[15px] hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)] hover:from-blue-500 hover:to-blue-400"
                onClick={() => window.location.href = registerUrl}
              >
                {t('land.nav.register') || 'Boshlash'}
              </button>

              {/* Hamburger */}
              <button
                className="lg:hidden bg-transparent border-none text-[28px] text-white cursor-pointer"
                onClick={() => setMobileMenu(!mobileMenu)}
              >
                ☰
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        <div className={`flex justify-between flex-col gap-4 h-[calc(100vh-60px)] bg-slate-900 px-6 py-8 border-l border-white/10 absolute transition-all duration-300 top-full w-full max-w-sm z-80 shadow-2xl ${mobileMenu ? 'right-0' : '-right-full'}`}>
          <div className='flex flex-col gap-2'>
            {navLinks.map(link => (
              <a
                key={link.path}
                onClick={() => { navigate(link.path); setMobileMenu(false); }}
                className="cursor-pointer no-underline text-white text-lg font-medium py-3 border-b border-white/10 last:border-none hover:text-blue-400 transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>
          <div className='flex flex-col gap-3 pb-8'>
            <button
              onClick={() => window.location.href = loginUrl}
              className="py-3.5 rounded-xl font-semibold text-[16px] cursor-pointer border border-white/20 bg-slate-800 text-white hover:bg-slate-700 transition-colors"
            >
              {t('land.nav.login') || 'Kirish'}
            </button>
            <button
              className="py-3.5 rounded-xl font-semibold text-[16px] cursor-pointer border-none bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg hover:from-blue-500 hover:to-blue-400 transition-all"
              onClick={() => window.location.href = registerUrl}
            >
              {t('land.nav.register') || 'Boshlash'}
            </button>
          </div>
        </div>
      </nav>

      {/* Page Content */}
      <main className="min-h-screen">
        {children}
      </main>

      {/* Footer */}
      <footer className="bg-slate-950 border-t border-white/10 py-20 pb-[60px] relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-blue-900/10 via-slate-950 to-slate-950"></div>
        <div className="max-w-[1400px] mx-auto px-6 relative z-10">
          <div className="flex justify-between flex-wrap gap-[60px]">
            <div className="flex flex-col">
              <span onClick={() => navigate('/')} className="cursor-pointer">
                <ECodeLogo size={42} showText={false} />
              </span>
              <p className="mt-8 text-[15px] text-slate-400 max-w-xs leading-relaxed">
                Kichik va o'rta biznes uchun eng yaxshi raqamlashtirish yechimlari.
              </p>
              <p className="mt-4 text-[14px] text-slate-500">
                © {new Date().getFullYear()} E-code LLC. {t('land.footer.rights') || 'Barcha huquqlar himoyalangan.'}
              </p>
            </div>
            <div className="flex gap-x-24 gap-y-12 flex-wrap">
              <div className="flex flex-col gap-4">
                <strong className="text-white text-sm mb-2 font-bold tracking-wider uppercase opacity-80">
                  {t('land.footer.services') || 'Xizmatlar'}
                </strong>
                {navLinks.map(link => (
                  <span
                    key={link.path}
                    onClick={() => navigate(link.path)}
                    className="cursor-pointer text-slate-400 text-[15px] transition-all duration-300 hover:text-blue-400 hover:translate-x-1"
                  >
                    {link.label}
                  </span>
                ))}
              </div>
              <div className="flex flex-col gap-4">
                <strong className="text-white text-sm mb-2 font-bold tracking-wider uppercase opacity-80">
                  {t('land.footer.contact') || 'Aloqa'}
                </strong>
                <a href="mailto:ecode.uz@gmail.com" className="text-slate-400 text-[15px] hover:text-blue-400 transition-colors no-underline">ecode.uz@gmail.com</a>
                <a href="tel:+998889118171" className="text-slate-400 text-[15px] hover:text-blue-400 transition-colors no-underline">+998 88 911 81 71</a>
              </div>
              <div className="flex flex-col gap-4">
                <strong className="text-white text-sm mb-2 font-bold tracking-wider uppercase opacity-80">
                  {t('land.footer.system') || 'Tizim'}
                </strong>
                <span
                  onClick={() => window.location.href = loginUrl}
                  className="cursor-pointer text-slate-400 text-[15px] transition-all duration-300 hover:text-blue-400 hover:translate-x-1"
                >
                  {t('land.nav.login') || 'Kirish'}
                </span>
                <span
                  onClick={() => window.location.href = registerUrl}
                  className="cursor-pointer text-slate-400 text-[15px] transition-all duration-300 hover:text-blue-400 hover:translate-x-1"
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
