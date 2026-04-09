import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLang } from '../context/LangContext'
import ECodeLogo from './ECodeLogo'

const LangIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ width: 16, height: 16 }}>
    <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
    <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
  </svg>
)

export default function LandingLayout({ children }) {
  const { t, lang, setLang, LANGUAGES } = useLang()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [mobileMenu, setMobileMenu] = useState(false)
  const currentLang = LANGUAGES.find(l => l.code === lang)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const navLinks = [
    { label: 'ERP Tizim', path: '/erp-tizim' },
    { label: 'Veb-saytlar', path: '/veb-saytlar' },
    { label: 'Telegram Botlar', path: '/telegram-botlar' },
    { label: 'Noyob Dasturlar', path: '/noyob-dasturlar' },
    { label: 'Aloqa', path: '/aloqa' },
  ]

  return (
    <div className="ent-root">
      {/* Navbar */}
      <nav className={`ent-nav ${scrolled ? 'scrolled' : ''}`}>
        <div className="ent-container ent-nav-inner">
          <span onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
            <ECodeLogo size={32} />
          </span>

          <div className="ent-nav-links">
            {navLinks.map(link => (
              <a key={link.path} onClick={() => navigate(link.path)} style={{ cursor: 'pointer' }}>
                {link.label}
              </a>
            ))}
          </div>

          <div className="ent-nav-actions">
            <div className="ent-lang-wrap">
              <button className="ent-lang-btn" onClick={() => setLangOpen(!langOpen)}>
                {currentLang?.short} <LangIcon />
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
            <button className="ent-btn-ghost" onClick={() => window.location.href = 'https://savdo.e-code.uz/login'}>
              Kirish
            </button>
            <button className="ent-btn-primary" onClick={() => window.location.href = 'https://savdo.e-code.uz/register'}>
              Boshlash
            </button>
            <button className="ent-hamburger" onClick={() => setMobileMenu(!mobileMenu)}>☰</button>
          </div>
        </div>

        {mobileMenu && (
          <div className="ent-mobile-menu">
            {navLinks.map(link => (
              <a key={link.path} onClick={() => { navigate(link.path); setMobileMenu(false); }} style={{ cursor: 'pointer' }}>
                {link.label}
              </a>
            ))}
            <button onClick={() => window.location.href = 'https://savdo.e-code.uz/login'}>Kirish</button>
            <button className="ent-btn-primary" onClick={() => window.location.href = 'https://savdo.e-code.uz/register'}>Boshlash</button>
          </div>
        )}
      </nav>

      {/* Page Content */}
      {children}

      {/* Footer */}
      <footer className="ent-footer">
        <div className="ent-container ent-footer-inner">
          <div className="ent-footer-brand">
            <span onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
              <ECodeLogo size={24} />
            </span>
            <p className="copy">© {new Date().getFullYear()} E-code LLC. Barcha huquqlar himoyalangan.</p>
          </div>
          <div className="ent-footer-links">
            <div>
              <strong>Xizmatlar</strong>
              {navLinks.map(link => (
                <span key={link.path} onClick={() => navigate(link.path)} className="clickable">{link.label}</span>
              ))}
            </div>
            <div>
              <strong>Aloqa</strong>
              <span>ecode.uz@gmail.com</span>
              <span>+998 88 911 81 71</span>
            </div>
            <div>
              <strong>Tizim</strong>
              <span onClick={() => window.location.href = 'https://savdo.e-code.uz/login'} className="clickable">Kirish</span>
              <span onClick={() => window.location.href = 'https://savdo.e-code.uz/register'} className="clickable">Ro'yxatdan o'tish</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
