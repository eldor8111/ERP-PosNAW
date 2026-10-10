import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import api from '../api/axios'
import ECodeLogo, { ECodeLogoPrimary, ECodeIcon } from '../components/ECodeLogo'
import { LANGUAGES } from '../i18n/index.js'
import { 
  Phone, 
  Lock, 
  Eye, 
  EyeOff, 
  ArrowRight, 
  ShieldCheck, 
  TrendingUp, 
  Sparkles, 
  Building2, 
  ChevronRight, 
  CheckCircle2, 
  AlertCircle,
  KeyRound,
  RotateCcw
} from 'lucide-react'

function LoginLangSwitcher({ lang, setLang }) {
  return (
    <div className="inline-flex items-center p-1 bg-white/80 backdrop-blur-md border border-blue-100/80 rounded-2xl shadow-xs">
      {LANGUAGES.map(l => {
        const isActive = lang === l.code
        return (
          <button
            key={l.code}
            type="button"
            onClick={() => {
              setLang(l.code)
              try { localStorage.setItem('app_language', l.code) } catch {}
            }}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all duration-200 ${
              isActive
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/25 scale-[1.02]'
                : 'text-slate-600 hover:text-blue-600 hover:bg-blue-50/60'
            }`}
          >
            {l.short}
          </button>
        )
      })}
    </div>
  )
}

// ─── OTP Input — 4 ta bo'sh katak ─────────────────────────────────────────
function OtpInput({ value, onChange }) {
  const digits = (value + '    ').slice(0, 4).split('')
  const handleKey = (e, i) => {
    const num = e.key
    if (num >= '0' && num <= '9') {
      const arr = value.padEnd(4, ' ').split('')
      arr[i] = num
      const next = arr.join('').trimEnd()
      onChange(next)
      const nextEl = document.getElementById(`otp-input-${i + 1}`)
      if (nextEl) nextEl.focus()
    } else if (num === 'Backspace') {
      const trimmed = value.slice(0, Math.max(0, i))
      onChange(trimmed)
      const prevEl = document.getElementById(`otp-input-${i - 1}`)
      if (prevEl) prevEl.focus()
    }
  }

  return (
    <div className="flex gap-3 justify-center my-4">
      {[0, 1, 2, 3].map(i => (
        <input
          key={i}
          id={`otp-input-${i}`}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digits[i].trim()}
          readOnly
          onKeyDown={(e) => handleKey(e, i)}
          onFocus={e => e.target.select()}
          className="w-12 h-14 text-center text-2xl font-black rounded-2xl
            border-2 border-slate-200 bg-white text-slate-800 focus:outline-none focus:border-blue-600
            focus:ring-4 focus:ring-blue-100 transition-all select-none
            focus:scale-105 shadow-xs"
        />
      ))}
    </div>
  )
}

// ─── Parolni unutdingizmi modal — 3 bosqich ─────────────────────────────────
function ForgotPasswordModal({ onClose, t }) {
  const [step, setStep] = useState(1) // 1: telefon, 2: OTP, 3: yangi parol
  const [phone, setPhone] = useState('')
  const [userName, setUserName] = useState('')
  const [otp, setOtp] = useState('')
  const [verifiedToken, setVerifiedToken] = useState('')
  const [newPass, setNewPass] = useState('')
  const [confirmPass, setConfirmPass] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [resendTimer, setResendTimer] = useState(0)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [devMode, setDevMode] = useState(false)
  const [botLink, setBotLink] = useState('')
  const [otpSession, setOtpSession] = useState('')

  const startResendTimer = () => {
    setResendTimer(60)
    const interval = setInterval(() => {
      setResendTimer(prev => {
        if (prev <= 1) { clearInterval(interval); return 0 }
        return prev - 1
      })
    }, 1000)
  }

  const checkPhone = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/auth/check-phone', { phone })
      if (!res.data.otp_sent) {
        setBotLink(res.data.bot_link || '')
        setError(res.data.message || 'Telegram bot ulanmagan')
        return
      }
      setUserName(res.data.name)
      setDevMode(res.data.dev_mode || false)
      setOtpSession(res.data.otp_session || '')
      setStep(2)
      startResendTimer()
    } catch (err) {
      setError(err.response?.data?.detail || t('error.notFound'))
    } finally {
      setLoading(false)
    }
  }

  const resendOtp = async () => {
    if (resendTimer > 0) return
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/auth/check-phone', { phone })
      setDevMode(res.data.dev_mode || false)
      setOtpSession(res.data.otp_session || '')
      startResendTimer()
    } catch (err) {
      setError(err.response?.data?.detail || 'Xatolik')
    } finally {
      setLoading(false)
    }
  }

  const verifyOtp = async (e) => {
    e.preventDefault()
    if (otp.length < 4) { setError("4 xonali kodni to'liq kiriting"); return }
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/auth/verify-otp', { phone, otp, otp_session: otpSession })
      setVerifiedToken(res.data.verified_token)
      setStep(3)
    } catch (err) {
      setError(err.response?.data?.detail || "OTP noto'g'ri")
      setOtp('')
    } finally {
      setLoading(false)
    }
  }

  const resetPassword = async (e) => {
    e.preventDefault()
    setError('')
    if (newPass !== confirmPass) { setError('Parollar mos kelmadi'); return }
    if (newPass.length < 6) { setError("Parol kamida 6 ta belgidan iborat bo'lishi kerak"); return }
    setLoading(true)
    try {
      await api.post('/auth/reset-password', {
        phone,
        verified_token: verifiedToken,
        new_password: newPass
      })
      setSuccess(true)
    } catch (err) {
      setError(err.response?.data?.detail || t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  const stepLabels = ['Telefon', 'OTP', 'Yangi parol']

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-white/95 backdrop-blur-xl border border-blue-100 rounded-3xl shadow-2xl w-full max-w-md p-7 relative">
        <button 
          onClick={onClose} 
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 p-1 rounded-full hover:bg-slate-100 transition-colors"
        >
          ✕
        </button>

        {success ? (
          <div className="text-center py-6">
            <div className="w-16 h-16 bg-emerald-50 border border-emerald-200 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-sm text-emerald-600">
              <CheckCircle2 className="w-9 h-9" />
            </div>
            <h3 className="text-xl font-black text-slate-800 mb-1">{t('auth.passUpdated')}</h3>
            <p className="text-sm text-slate-500 mb-6">{t('auth.loginWithNewPass')}</p>
            <button 
              onClick={onClose} 
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-sm shadow-lg shadow-blue-500/25 transition-all"
            >
              {t('common.back')}
            </button>
          </div>
        ) : (
          <>
            <div className="mb-6">
              <div className="inline-flex p-2.5 bg-blue-50 text-blue-600 rounded-2xl mb-3 border border-blue-100">
                <KeyRound className="w-5 h-5" />
              </div>
              <h3 className="text-xl font-black text-slate-800">{t('auth.resetPass')}</h3>
              <p className="text-xs text-slate-500 mt-1">
                {step === 1 ? 'Telefon raqamingizni kiriting'
                  : step === 2 ? `Salom, ${userName}! SMS orqali yuborilgan kodni kiriting`
                  : `Yangi xavfsiz parol o'rnating`}
              </p>
              
              {/* Progress bars */}
              <div className="flex gap-2 mt-4">
                {stepLabels.map((_, i) => (
                  <div key={i} className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${i < step ? 'bg-blue-600' : 'bg-slate-100'}`} />
                ))}
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2.5 bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl px-4 py-3 mb-4 text-xs font-medium">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="flex-1">
                  {error}
                  {botLink && (
                    <a href={botLink} target="_blank" rel="noreferrer"
                      className="block mt-1 text-blue-600 font-bold hover:underline">
                      📱 Telegram botni ochish →
                    </a>
                  )}
                </div>
              </div>
            )}

            {step === 1 && (
              <form onSubmit={checkPhone} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">{t('common.phone')}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Phone className="w-4 h-4" />
                    </div>
                    <input 
                      type="text" 
                      placeholder="998901234567" 
                      value={phone} 
                      onChange={e => setPhone(e.target.value)} 
                      required
                      className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-2xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all font-medium" 
                    />
                  </div>
                </div>
                <button 
                  type="submit" 
                  disabled={loading}
                  className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-sm shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2"
                >
                  {loading ? t('common.loading') : <>{t('common.next')} <ArrowRight className="w-4 h-4" /></>}
                </button>
              </form>
            )}

            {step === 2 && (
              <form onSubmit={verifyOtp} className="space-y-4">
                {devMode && (
                  <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-2xl text-xs font-semibold text-center">
                    🛠 Dev mode: OTP konsolga chiqarildi
                  </div>
                )}
                <OtpInput value={otp} onChange={setOtp} />
                <button 
                  type="submit" 
                  disabled={loading || otp.length < 4}
                  className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-sm shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2"
                >
                  {loading ? t('common.loading') : <>Tasdiqlash <CheckCircle2 className="w-4 h-4" /></>}
                </button>
                <div className="flex items-center justify-between pt-2">
                  <button 
                    type="button" 
                    onClick={() => { setStep(1); setError(''); setOtp('') }}
                    className="text-xs text-slate-500 hover:text-slate-800 font-semibold"
                  >
                    ← Ortga
                  </button>
                  <button 
                    type="button" 
                    onClick={resendOtp} 
                    disabled={resendTimer > 0 || loading}
                    className="text-xs text-blue-600 hover:text-blue-700 disabled:text-slate-400 font-bold"
                  >
                    {resendTimer > 0 ? `Qayta yuborish (${resendTimer}s)` : 'Kodni qayta yuborish'}
                  </button>
                </div>
              </form>
            )}

            {step === 3 && (
              <form onSubmit={resetPassword} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">{t('auth.newPass')}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Lock className="w-4 h-4" />
                    </div>
                    <input 
                      type={showNew ? 'text' : 'password'} 
                      placeholder="••••••••" 
                      value={newPass} 
                      onChange={e => setNewPass(e.target.value)} 
                      required
                      className="w-full pl-10 pr-10 py-3 border border-slate-200 rounded-2xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all font-medium" 
                    />
                    <button type="button" onClick={() => setShowNew(!showNew)} className="absolute inset-y-0 right-3.5 flex items-center text-slate-400 hover:text-slate-600">
                      {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">{t('auth.confirmPass')}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Lock className="w-4 h-4" />
                    </div>
                    <input 
                      type={showConfirm ? 'text' : 'password'} 
                      placeholder="••••••••" 
                      value={confirmPass} 
                      onChange={e => setConfirmPass(e.target.value)} 
                      required
                      className="w-full pl-10 pr-10 py-3 border border-slate-200 rounded-2xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all font-medium" 
                    />
                    <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute inset-y-0 right-3.5 flex items-center text-slate-400 hover:text-slate-600">
                      {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  <button 
                    type="button" 
                    onClick={() => { setStep(2); setError(''); setOtp('') }}
                    className="flex-1 py-3 rounded-2xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-bold text-xs"
                  >
                    {t('common.back')}
                  </button>
                  <button 
                    type="submit" 
                    disabled={loading}
                    className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-xs shadow-md shadow-blue-500/25"
                  >
                    {loading ? t('common.saving') : t('common.save')}
                  </button>
                </div>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function Login() {
  const { login } = useAuth()
  const { t, lang, setLang } = useLang()
  const navigate = useNavigate()
  const [form, setForm] = useState({ phone: '+998', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showForgot, setShowForgot] = useState(false)

  // OTP bosqich
  const [otpStep, setOtpStep] = useState(false)
  const [otp, setOtp] = useState('')
  const [otpName, setOtpName] = useState('')
  const [otpDevMode, setOtpDevMode] = useState(false)
  const [otpLoading, setOtpLoading] = useState(false)
  const [loginOtpSession, setLoginOtpSession] = useState('')

  // Multi-company bosqich
  const [companyStep, setCompanyStep] = useState(false)
  const [companiesList, setCompaniesList] = useState([])
  const [tempToken, setTempToken] = useState('')
  const [companyLoading, setCompanyLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const userRes = await login(form.phone.replace(/[+ -]/g, ''), form.password)

      if (userRes?.needs_company_selection) {
        setCompaniesList(userRes.companies || [])
        setTempToken(userRes.temp_token)
        setCompanyStep(true)
        return
      }

      if (userRes?.role === 'super_admin') {
        navigate('/admin/super-admin')
      } else if (userRes?.role === 'cashier') {
        navigate('/admin/ulgurji-sotuv')
      } else {
        navigate('/admin/products')
      }
    } catch (err) {
      const detail = err.response?.data?.detail
      if (err.response?.status === 202 && detail?.otp_required) {
        setOtpName(detail.name || '')
        setOtpDevMode(detail.dev_mode || false)
        setLoginOtpSession(detail.otp_session || '')
        setOtpStep(true)
        setError('')
      } else {
        setError(detail || t('login.error'))
      }
    } finally {
      setLoading(false)
    }
  }

  const handleOtpVerify = async (e) => {
    e.preventDefault()
    if (otp.length < 4) { setError("4 xonali kodni to'liq kiriting"); return }
    setOtpLoading(true); setError('')
    try {
      const normalized = form.phone.replace(/[+ -]/g, '')
      const res = await api.post('/auth/login-verify', { phone: normalized, otp, otp_session: loginOtpSession })
      const { data } = res

      if (data.needs_company_selection) {
        setCompaniesList(data.companies || [])
        setTempToken(data.temp_token)
        setOtpStep(false)
        setCompanyStep(true)
        return
      }

      const { access_token, refresh_token, user } = data
      localStorage.setItem('access_token', access_token)
      localStorage.setItem('refresh_token', refresh_token)
      localStorage.setItem('user', JSON.stringify(user))

      if (user?.role === 'super_admin') {
        window.location.href = '/admin/super-admin'
      } else if (user?.role === 'cashier') {
        window.location.href = '/admin/ulgurji-sotuv'
      } else {
        window.location.href = '/admin/products'
      }
    } catch (err) {
      setError(err.response?.data?.detail || "OTP noto'g'ri")
      setOtp('')
    } finally {
      setOtpLoading(false)
    }
  }

  const handleSelectCompany = async (company_id) => {
    setCompanyLoading(true)
    setError('')
    try {
      const res = await api.post('/auth/select-company', {
        temp_token: tempToken,
        company_id
      })
      const { access_token, refresh_token, user } = res.data
      localStorage.setItem('access_token', access_token)
      localStorage.setItem('refresh_token', refresh_token)
      localStorage.setItem('user', JSON.stringify(user))

      if (user?.role === 'super_admin') {
        window.location.href = '/admin/super-admin'
      } else if (user?.role === 'cashier') {
        window.location.href = '/admin/ulgurji-sotuv'
      } else {
        window.location.href = '/admin/products'
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Korxona tanlashda xato")
    } finally {
      setCompanyLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] relative overflow-hidden flex flex-col justify-between">
      
      {/* ── Background Subtle Tech Grid & Ambient Blue Glows ── */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {/* Subtle grid pattern */}
        <div 
          className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage: `radial-gradient(#2563EB 1px, transparent 1px)`,
            backgroundSize: '28px 28px'
          }}
        />
        {/* Soft radial blue ambient lights */}
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] bg-gradient-to-br from-blue-400/15 to-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-40 -right-40 w-[700px] h-[700px] bg-gradient-to-tl from-blue-500/15 to-sky-300/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-1/2 left-1/3 -translate-y-1/2 w-96 h-96 bg-blue-100/40 rounded-full blur-2xl pointer-events-none" />
      </div>

      {/* ── Top Header Bar ── */}
      <header className="relative z-10 w-full max-w-7xl mx-auto px-6 py-6 flex items-center justify-between">
        <Link to="/landing" className="flex items-center gap-3 group">
          <ECodeLogo size={42} showText={true} />
        </Link>
        <LoginLangSwitcher lang={lang} setLang={setLang} />
      </header>

      {/* ── Main Container ── */}
      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
        <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          
          {/* ── Left Side: E-Code Enterprise Hero & Live Badges (Desktop) ── */}
          <div className="hidden lg:flex lg:col-span-6 flex-col justify-center space-y-8 pr-4">
            
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-bold w-fit shadow-xs">
              <Sparkles className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
              <span>Universal ERP Ecosystem 2.0</span>
            </div>

            <div>
              <h1 className="text-4xl xl:text-5xl font-black text-slate-900 tracking-tight leading-[1.15]">
                {lang === 'ru' ? 'Управляйте' : lang === 'en' ? 'Manage your' : 'Biznesingizni'}{' '}
                <span className="bg-gradient-to-r from-blue-600 via-blue-700 to-indigo-600 bg-clip-text text-transparent">
                  {lang === 'ru' ? 'бизнесом с легкостью' : lang === 'en' ? 'enterprise smarter' : 'yangi bosqichga olib chiqing'}
                </span>
              </h1>
              <p className="mt-4 text-slate-600 text-base leading-relaxed max-w-lg">
                {lang === 'ru' 
                  ? 'Единая платформа для автоматизации торговли, оптовых продаж, склада, финансов и мобильных агентов.' 
                  : lang === 'en'
                  ? 'A single unified platform to automate sales, wholesale, warehouse, financials, and mobile teams.'
                  : 'Savdo, ombor, ulgurji kassa, moliya va mobil agentlarni yagona aqlli tizimda to\'liq nazorat qiling.'}
              </p>
            </div>

            {/* Live Floating Metric Cards (Mockup matching) */}
            <div className="grid grid-cols-2 gap-4 max-w-lg">
              <div className="p-4 rounded-2xl bg-white/90 backdrop-blur-xl border border-blue-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-md hover:border-blue-200 transition-all">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Savdo o'sishi</span>
                  <div className="p-1.5 rounded-xl bg-blue-50 text-blue-600">
                    <TrendingUp className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900">+38.6%</div>
                <div className="text-[11px] text-blue-600 font-semibold mt-1">Real-vaqt analitikasi</div>
              </div>

              <div className="p-4 rounded-2xl bg-white/90 backdrop-blur-xl border border-blue-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-md hover:border-blue-200 transition-all">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Tizim barqarorligi</span>
                  <div className="p-1.5 rounded-xl bg-emerald-50 text-emerald-600">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900">99.98%</div>
                <div className="text-[11px] text-emerald-600 font-semibold mt-1">256-bit xavfsizlik kafolati</div>
              </div>
            </div>

            {/* Quick Feature Perks */}
            <div className="flex items-center gap-6 text-xs font-bold text-slate-600 pt-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-blue-600" />
                <span>14 kunlik bepul sinov</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-blue-600" />
                <span>Tezkor 24/7 qo'llab-quvvatlash</span>
              </div>
            </div>

          </div>

          {/* ── Right Side: Crystal Glass Login Card ── */}
          <div className="lg:col-span-6 flex justify-center">
            <div className="w-full max-w-md bg-white/95 backdrop-blur-2xl border border-blue-100/90 rounded-3xl shadow-[0_20px_60px_-15px_rgba(37,99,235,0.12)] p-8 sm:p-10 relative">

              {/* Card Header */}
              <div className="text-center mb-8">
                <div className="inline-flex justify-center items-center mb-4">
                  <ECodeIcon size={48} />
                </div>
                <h2 className="text-2xl font-black text-slate-900 tracking-tight">
                  {t('login.welcome')}
                </h2>
                <p className="text-slate-500 text-xs sm:text-sm mt-1">
                  {t('login.subtitle')}
                </p>
              </div>

              {/* Error Message */}
              {error && (
                <div className="flex items-center gap-2.5 bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl px-4 py-3 mb-6 text-xs font-medium animate-in fade-in">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {/* Forgot Password Modal */}
              {showForgot && <ForgotPasswordModal onClose={() => setShowForgot(false)} t={t} />}

              {/* ── Multi-company Selection Step ── */}
              {companyStep ? (
                <div>
                  <div className="mb-6">
                    <h3 className="text-lg font-black text-slate-900">Korxonani tanlang</h3>
                    <p className="text-slate-500 text-xs mt-1">
                      Siz bir nechta korxonaga biriktirilgansiz. Qaysi biri bilan ishlamoqchisiz?
                    </p>
                  </div>
                  <div className="space-y-3 mb-6 max-h-72 overflow-y-auto pr-1">
                    {companiesList.map(c => (
                      <button
                        key={c.company_id}
                        onClick={() => handleSelectCompany(c.company_id)}
                        disabled={companyLoading || !c.is_active}
                        className={`w-full text-left p-4 rounded-2xl border transition-all flex items-center justify-between group
                          ${companyLoading ? 'opacity-50 cursor-not-allowed' : 'hover:border-blue-600 hover:shadow-md hover:shadow-blue-500/10'} 
                          ${!c.is_active ? 'opacity-50 grayscale bg-slate-50 border-slate-200' : 'bg-white border-slate-200 hover:bg-blue-50/30'}`}
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
                            <Building2 className="w-5 h-5" />
                          </div>
                          <div>
                            <h4 className="font-bold text-slate-800 text-sm group-hover:text-blue-600 transition-colors">{c.company_name}</h4>
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 uppercase tracking-wider">
                              {c.role} {c.is_active ? '' : '(Bloklangan)'}
                            </span>
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all" />
                      </button>
                    ))}
                  </div>
                  <button 
                    type="button" 
                    onClick={() => { setCompanyStep(false); setError('') }}
                    disabled={companyLoading}
                    className="w-full py-2.5 text-slate-500 hover:text-slate-800 text-xs font-bold transition-colors"
                  >
                    ← Boshqa hisob bilan kirish
                  </button>
                </div>

              /* ── OTP Verification Step ── */
              ) : otpStep ? (
                <div>
                  <div className="mb-6 text-center">
                    <h3 className="text-lg font-black text-slate-900">SMS OTP tasdiqlash</h3>
                    <p className="text-slate-500 text-xs mt-1">
                      Salom, <strong className="text-slate-800">{otpName}</strong>! Telefon raqamingizga kod yuborildi.
                    </p>
                  </div>
                  {otpDevMode && (
                    <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-2xl text-xs font-semibold mb-4 text-center">
                      🛠 Dev mode: OTP backend konsolga chiqarildi
                    </div>
                  )}
                  <form onSubmit={handleOtpVerify} className="space-y-5">
                    <OtpInput value={otp} onChange={setOtp} />
                    <button 
                      type="submit" 
                      disabled={otpLoading || otp.length < 4}
                      className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-sm shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2"
                    >
                      {otpLoading ? (
                        <>Tekshirilmoqda...</>
                      ) : (
                        <>Tasdiqlash <ArrowRight className="w-4 h-4" /></>
                      )}
                    </button>
                    <button 
                      type="button" 
                      onClick={() => { setOtpStep(false); setOtp(''); setError('') }}
                      className="w-full py-2 text-slate-500 hover:text-slate-800 text-xs font-bold transition-colors"
                    >
                      ← Parolga qaytish
                    </button>
                  </form>
                </div>

              /* ── Primary Login Form ── */
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5">
                  
                  {/* Phone Input */}
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                      {t('login.username')}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-400">
                        <span className="text-base mr-1">🇺🇿</span>
                      </div>
                      <input 
                        type="tel" 
                        placeholder="+998 XX XXX XX XX" 
                        value={form.phone}
                        onChange={e => {
                          let val = e.target.value
                          if (!val.startsWith('+998')) val = '+998' + val.replace(/^\+?9{0,1}9{0,1}8{0,1}/, '')
                          if (val.length > 13) val = val.slice(0, 13)
                          setForm({ ...form, phone: val })
                        }}
                        onKeyDown={e => {
                          if (e.key === 'Backspace' && form.phone.length <= 4) e.preventDefault()
                        }}
                        required
                        className="w-full pl-12 pr-4 py-3.5 border border-slate-200/90 rounded-2xl bg-white text-sm font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs" 
                      />
                    </div>
                  </div>

                  {/* Password Input */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs font-bold uppercase tracking-wider text-slate-700">
                        {t('login.password')}
                      </label>
                      <button 
                        type="button" 
                        onClick={() => setShowForgot(true)}
                        className="text-xs text-blue-600 hover:text-blue-700 font-bold hover:underline transition-colors"
                      >
                        {t('login.forgotPass')}
                      </button>
                    </div>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-400">
                        <Lock className="w-4 h-4" />
                      </div>
                      <input 
                        type={showPass ? 'text' : 'password'} 
                        placeholder="••••••••" 
                        value={form.password}
                        onChange={e => setForm({ ...form, password: e.target.value })} 
                        required
                        className="w-full pl-11 pr-11 py-3.5 border border-slate-200/90 rounded-2xl bg-white text-sm font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs" 
                      />
                      <button 
                        type="button" 
                        onClick={() => setShowPass(!showPass)}
                        className="absolute inset-y-0 right-3.5 flex items-center text-slate-400 hover:text-slate-600 p-1"
                      >
                        {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Submit Button */}
                  <button 
                    type="submit" 
                    disabled={loading}
                    className="w-full py-3.5 px-6 rounded-2xl bg-gradient-to-r from-blue-600 via-blue-700 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-sm transition-all duration-300 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2 mt-2"
                  >
                    {loading ? (
                      <span className="flex items-center gap-2">
                        <svg className="animate-spin w-4 h-4 text-white" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                        {t('login.entering')}
                      </span>
                    ) : (
                      <>
                        <span>{t('login.enter')}</span>
                        <ArrowRight className="w-4 h-4" />
                      </>
                    )}
                  </button>

                  {/* Register Link */}
                  <div className="pt-6 border-t border-slate-100 text-center">
                    <p className="text-xs sm:text-sm text-slate-500 font-medium">
                      {lang === 'ru' ? 'Нет вашей организации?' : lang === 'en' ? "Don't have a company?" : "Korxonangiz yo'qmi?"}{' '}
                      <Link 
                        to="/register" 
                        className="text-blue-600 font-bold hover:text-blue-800 hover:underline transition-colors ml-1"
                      >
                        {lang === 'ru' ? 'Зарегистрируйтесь' : lang === 'en' ? 'Register' : "Ro'yxatdan o'ting"}
                      </Link>
                    </p>
                  </div>

                </form>
              )}

            </div>
          </div>

        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="relative z-10 w-full py-6 text-center text-xs text-slate-400">
        <p>© {new Date().getFullYear()} E-Code Universal ERP. Barcha huquqlar himoyalangan.</p>
      </footer>

    </div>
  )
}
