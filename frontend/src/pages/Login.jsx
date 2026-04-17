import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useLang } from '../context/LangContext'
import api from '../api/axios'
import { ECodeLogoPrimary } from '../components/ECodeLogo'
import ECodeLogo from '../components/ECodeLogo'
import { LANGUAGES } from '../i18n/index.js'

const Icon = ({ d, cls = "w-4 h-4" }) => (
  <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
  </svg>
)

function LoginLangSwitcher({ lang, setLang, dark = false }) {
  return (
    <div className="flex items-center gap-1">
      {LANGUAGES.map(l => (
        <button
          key={l.code}
          onClick={() => { setLang(l.code); try { localStorage.setItem('app_language', l.code); } catch {} }}
          className={`px-2 py-1 rounded-lg text-xs font-bold transition-all ${
            dark
              ? lang === l.code ? 'bg-white/20 text-white' : 'text-white/60 hover:text-white hover:bg-white/10'
              : lang === l.code ? 'bg-indigo-100 text-indigo-700' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
          }`}
        >
          {l.short}
        </button>
      ))}
    </div>
  )
}

// ─── OTP Input — 6 ta bo'sh katak ─────────────────────────────────────────
function OtpInput({ value, onChange }) {
  const digits = (value + '      ').slice(0, 6).split('')
  const handleKey = (e, i) => {
    const num = e.key
    if (num >= '0' && num <= '9') {
      const arr = value.padEnd(6, ' ').split('')
      arr[i] = num
      const next = arr.join('').trimEnd()
      onChange(next)
      // avtomatik keyingiga o'tish
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
    <div className="flex gap-2 justify-center my-2">
      {[0, 1, 2, 3, 4, 5].map(i => (
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
          className="w-11 h-13 text-center text-xl font-bold border-2 rounded-xl
            border-slate-200 bg-white text-slate-800 focus:outline-none focus:border-indigo-500
            focus:ring-2 focus:ring-indigo-200 transition-all caret-transparent select-none
            focus:scale-105"
          style={{ width: 44, height: 52 }}
        />
      ))}
    </div>
  )
}

// ─── Parolni unutdingizmi modal — 3 bosqim ─────────────────────────────────
function ForgotPasswordModal({ onClose, t }) {
  const [step, setStep] = useState(1)   // 1: telefon, 2: OTP, 3: yangi parol
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
  const [otpSession, setOtpSession] = useState('')  // JWT da saqlangan OTP sessiyasi

  // Qayta yuborish taymer
  const startResendTimer = () => {
    setResendTimer(60)
    const interval = setInterval(() => {
      setResendTimer(prev => {
        if (prev <= 1) { clearInterval(interval); return 0 }
        return prev - 1
      })
    }, 1000)
  }

  // Step 1 → Step 2: Telefon tekshirish va OTP yuborish
  const checkPhone = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/auth/check-phone', { phone })
      if (!res.data.otp_sent) {
        // Bot ulanmagan
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

  // OTP qayta yuborish
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

  // Step 2 → Step 3: OTP tasdiqlash
  const verifyOtp = async (e) => {
    e.preventDefault()
    if (otp.length < 6) { setError("6 xonali kodni to'liq kiriting"); return }
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

  // Step 3: Yangi parol o'rnatish
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

  const totalSteps = 3
  const stepLabels = ['Telefon', 'OTP', 'Yangi parol']

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors">
          <Icon d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" />
        </button>

        {success ? (
          <div className="text-center py-4">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Icon d="M5 13l4 4L19 7" cls="w-8 h-8 text-green-600" />
            </div>
            <h3 className="text-lg font-bold text-slate-800 mb-1">{t('auth.passUpdated')}</h3>
            <p className="text-sm text-slate-500 mb-5">{t('auth.loginWithNewPass')}</p>
            <button onClick={onClose} className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm transition-colors">
              {t('common.back')}
            </button>
          </div>
        ) : (
          <>
            {/* Header + Progress */}
            <div className="mb-5">
              <h3 className="text-lg font-bold text-slate-800">{t('auth.resetPass')}</h3>
              <p className="text-sm text-slate-500 mt-0.5">
                {step === 1 ? 'Telefon raqamingizni kiriting'
                  : step === 2 ? `Salom, ${userName}! Telegram botdagi kodni kiriting`
                  : `Yangi parol o'rnating`}
              </p>
              {/* Step indicator */}
              <div className="flex gap-1 mt-3">
                {stepLabels.map((_, i) => (
                  <div key={i} className={`h-1 flex-1 rounded-full transition-all ${i < step ? 'bg-indigo-600' : 'bg-slate-200'}`} />
                ))}
              </div>
              <div className="flex justify-between mt-1">
                {stepLabels.map((label, i) => (
                  <span key={i} className={`text-[10px] font-semibold ${i < step ? 'text-indigo-500' : 'text-slate-400'}`}>{label}</span>
                ))}
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-600 rounded-xl px-3 py-2.5 mb-4 text-sm">
                <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  {error}
                  {botLink && (
                    <a href={botLink} target="_blank" rel="noreferrer"
                      className="block mt-1.5 text-indigo-600 font-semibold underline hover:text-indigo-700">
                      📱 Botni ochish →
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* ── STEP 1: Telefon ── */}
            {step === 1 && (
              <form onSubmit={checkPhone} className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">{t('common.phone')}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Icon d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                    </div>
                    <input type="text" placeholder="998901234567" value={phone} onChange={e => setPhone(e.target.value)} required
                      className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all" />
                  </div>
                </div>
                <button type="submit" disabled={loading}
                  className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors flex items-center justify-center gap-2">
                  {loading ? t('common.loading') : <>{t('common.next')} <Icon d="M13 7l5 5m0 0l-5 5m5-5H6" /></>}
                </button>
              </form>
            )}

            {/* ── STEP 2: OTP ── */}
            {step === 2 && (
              <form onSubmit={verifyOtp} className="space-y-4">
                {devMode && (
                  <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-3 py-2.5 text-xs font-medium">
                    <span>🛠</span>
                    <span>Developer mode: OTP backend konsolga chiqarildi</span>
                  </div>
                )}
                <div>
                  <p className="text-xs text-slate-500 text-center mb-3">
                    <span className="font-semibold text-indigo-600">Telegram</span> botdagi 6 xonali kodni kiriting
                  </p>
                  <OtpInput value={otp} onChange={setOtp} />
                </div>
                <button type="submit" disabled={loading || otp.length < 6}
                  className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors flex items-center justify-center gap-2">
                  {loading ? t('common.loading') : <>Tasdiqlash <Icon d="M5 13l4 4L19 7" /></>}
                </button>
                <div className="text-center">
                  <button type="button" onClick={resendOtp} disabled={resendTimer > 0 || loading}
                    className="text-sm text-indigo-600 hover:text-indigo-700 disabled:text-slate-400 font-medium transition-colors">
                    {resendTimer > 0 ? `Qayta yuborish (${resendTimer}s)` : 'Kodni qayta yuborish'}
                  </button>
                </div>
                <button type="button" onClick={() => { setStep(1); setError(''); setOtp('') }}
                  className="w-full py-2 text-slate-500 hover:text-slate-700 text-sm font-medium transition-colors">
                  ← Ortga
                </button>
              </form>
            )}

            {/* ── STEP 3: Yangi parol ── */}
            {step === 3 && (
              <form onSubmit={resetPassword} className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">{t('auth.newPass')}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Icon d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </div>
                    <input type={showNew ? 'text' : 'password'} placeholder="••••••" value={newPass} onChange={e => setNewPass(e.target.value)} required
                      className="w-full pl-10 pr-10 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all" />
                    <button type="button" onClick={() => setShowNew(!showNew)} className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600">
                      <Icon d={showNew ? "M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" : "M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"} />
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">{t('auth.confirmPass')}</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Icon d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </div>
                    <input type={showConfirm ? 'text' : 'password'} placeholder="••••••" value={confirmPass} onChange={e => setConfirmPass(e.target.value)} required
                      className="w-full pl-10 pr-10 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all" />
                    <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600">
                      <Icon d={showConfirm ? "M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" : "M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"} />
                    </button>
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => { setStep(2); setError(''); setOtp('') }}
                    className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-semibold text-sm transition-colors">
                    {t('common.back')}
                  </button>
                  <button type="submit" disabled={loading}
                    className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors">
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
  const [form, setForm] = useState({ phone: '', password: '' })
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
      const userRes = await login(form.phone, form.password)
      
      if (userRes?.needs_company_selection) {
        setCompaniesList(userRes.companies || [])
        setTempToken(userRes.temp_token)
        setCompanyStep(true)
        return
      }
      
      if (userRes?.role === 'cashier') {
        navigate('/admin/pos-kassa')
      } else {
        navigate('/admin/dashboard')
      }
    } catch (err) {
      // 202 = OTP talab qilinadi (kassir/sub-foydalanuvchi)
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
    if (otp.length < 6) { setError("6 xonali kodni to'liq kiriting"); return }
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
      
      // login context ni yangilaymiz
      const { access_token, refresh_token, user } = data
      localStorage.setItem('access_token', access_token)
      localStorage.setItem('refresh_token', refresh_token)
      localStorage.setItem('user', JSON.stringify(user))
      // Auth context ni reload qilish uchun sahifani yangilaymiz
      if (user?.role === 'cashier') {
        window.location.href = '/admin/pos-kassa'
      } else {
        window.location.href = '/admin/dashboard'
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
      
      if (user?.role === 'cashier') {
        window.location.href = '/admin/pos-kassa'
      } else {
        window.location.href = '/admin/dashboard'
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Korxona tanlashda xato")
    } finally {
      setCompanyLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-linear-to-br from-slate-50 via-white to-indigo-50/40 flex">

      {/* ── Left panel ── */}
      <div className="hidden lg:flex lg:w-[260px] xl:w-[300px] bg-linear-to-br from-indigo-600 via-indigo-700 to-purple-700 flex-col justify-between p-10 relative overflow-hidden shrink-0">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full bg-white/5" />
          <div className="absolute -bottom-20 -left-20 w-80 h-80 rounded-full bg-white/5" />
          <div className="absolute top-1/2 right-0 w-40 h-40 rounded-full bg-purple-500/20" />
        </div>

        <div className="relative">
          <ECodeLogoPrimary size={40} />
        </div>

        <div className="relative">
          <h2 className="text-2xl font-black text-white leading-tight mb-2">
            {lang === 'ru' ? 'Управляйте' : lang === 'en' ? 'Manage your' : 'Biznesingizni'}<br />
            <span className="text-indigo-200">
              {lang === 'ru' ? 'своим бизнесом' : lang === 'en' ? 'business' : 'boshqaring'}
            </span>
          </h2>
          <p className="text-indigo-300/80 text-xs leading-relaxed mt-3">
            {lang === 'ru' ? 'Управляйте продажами, складом, финансами и отчётами в одной системе.' :
             lang === 'en' ? 'Manage sales, warehouse, finance and reports in one system.' :
             'Savdo, ombor, moliya va hisobotlarni bitta tizimda boshqaring.'}
          </p>
        </div>

        <p className="relative text-indigo-300/50 text-xs">{t('common.copyright')}</p>
      </div>

      {/* ── Right panel (form) ── */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12 relative">

        <div className="hidden lg:flex absolute top-4 right-4">
          <LoginLangSwitcher lang={lang} setLang={setLang} dark={false} />
        </div>

        <div className="w-full max-w-md">

          <div className="lg:hidden flex items-center justify-between mb-8">
            <ECodeLogo size={34} showText={true} textClassName="text-lg" />
            <LoginLangSwitcher lang={lang} setLang={setLang} dark={false} />
          </div>

          {/* ── OTP bosqich ── */}
          {companyStep ? (
            <>
              <div className="mb-8">
                <h1 className="text-2xl font-black text-slate-800">Korxonani tanlang</h1>
                <p className="text-slate-500 text-sm mt-1">Siz bir nechta korxonaga biriktirilgansiz. Ishni qaysi biri nomidan boshlamoqchisiz?</p>
              </div>
              {error && (
                <div className="flex items-center gap-2.5 bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 mb-6 text-sm">
                  <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0" />
                  {error}
                </div>
              )}
              <div className="space-y-3 mb-6">
                {companiesList.map(c => (
                  <button
                    key={c.company_id}
                    onClick={() => handleSelectCompany(c.company_id)}
                    disabled={companyLoading || !c.is_active}
                    className={`w-full text-left p-4 rounded-xl border-2 transition-all flex items-center justify-between group
                      ${companyLoading ? 'opacity-50 cursor-not-allowed' : 'hover:border-indigo-500 hover:shadow-md hover:shadow-indigo-100'} 
                      ${!c.is_active ? 'opacity-50 grayscale bg-slate-50 border-slate-200' : 'bg-white border-slate-200'}`}
                  >
                    <div>
                      <h3 className="font-bold text-slate-800 text-lg group-hover:text-indigo-700 transition-colors">{c.company_name}</h3>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 mt-1 inline-block uppercase tracking-wider">
                        {c.role} {c.is_active ? '' : '(Bloklangan)'}
                      </span>
                    </div>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors
                      ${!c.is_active ? 'bg-slate-200 text-slate-400' : 'bg-indigo-50 text-indigo-500 group-hover:bg-indigo-600 group-hover:text-white'}`}>
                      <Icon d="M9 5l7 7-7 7" cls="w-4 h-4" />
                    </div>
                  </button>
                ))}
              </div>
              <button type="button" onClick={() => { setCompanyStep(false); setError(''); }}
                disabled={companyLoading}
                className="w-full py-2 text-slate-500 hover:text-slate-700 text-sm font-medium transition-colors">
                ← Boshqa hisob bilan kirish
              </button>
            </>
          ) : otpStep ? (
            <>
              <div className="mb-8">
                <h1 className="text-2xl font-black text-slate-800">Telegram OTP tasdiqlash</h1>
                <p className="text-slate-500 text-sm mt-1">Salom, <strong>{otpName}</strong>! Telegram botdagi kodni kiriting.</p>
              </div>
              {otpDevMode && (
                <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-3 py-2.5 text-xs font-medium mb-4">
                  <span>🛠</span><span>Dev mode: OTP backend konsolga chiqarildi</span>
                </div>
              )}
              {error && (
                <div className="flex items-center gap-2.5 bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 mb-6 text-sm">
                  <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0" />
                  {error}
                </div>
              )}
              <form onSubmit={handleOtpVerify} className="space-y-5">
                <div>
                  <p className="text-xs text-slate-500 text-center mb-3">
                    <span className="font-semibold text-indigo-600">Telegram</span> botdagi 6 xonali kodni kiriting
                  </p>
                  <OtpInput value={otp} onChange={setOtp} />
                </div>
                <button type="submit" disabled={otpLoading || otp.length < 6}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 text-white font-bold text-sm transition-all shadow-lg shadow-indigo-200 flex items-center justify-center gap-2">
                  {otpLoading ? (
                    <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/></svg>Tekshirilmoqda...</>
                  ) : (
                    <>Tasdiqlash <Icon d="M5 13l4 4L19 7" /></>
                  )}
                </button>
                <button type="button" onClick={() => { setOtpStep(false); setOtp(''); setError(''); }}
                  className="w-full py-2 text-slate-500 hover:text-slate-700 text-sm font-medium transition-colors">
                  ← Parolga qaytish
                </button>
              </form>
            </>
          ) : (
            <>
          <div className="mb-8">
            <h1 className="text-2xl font-black text-slate-800">{t('login.welcome')}</h1>
            <p className="text-slate-500 text-sm mt-1">{t('login.subtitle')}</p>
          </div>

          {error && (
            <div className="flex items-center gap-2.5 bg-red-50 border border-red-200 text-red-600 rounded-xl px-4 py-3 mb-6 text-sm">
              <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          {showForgot && <ForgotPasswordModal onClose={() => setShowForgot(false)} t={t} />}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">{t('login.username')}</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                  <Icon d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                </div>
                <input type="text" placeholder="998901234567" value={form.phone}
                  onChange={e => setForm({ ...form, phone: e.target.value })} required
                  className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all" />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-semibold text-slate-700">{t('login.password')}</label>
                <button type="button" onClick={() => setShowForgot(true)}
                  className="text-sm text-indigo-600 hover:text-indigo-700 font-semibold hover:underline transition-colors">
                  {t('login.forgotPass')}
                </button>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                  <Icon d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </div>
                <input type={showPass ? 'text' : 'password'} placeholder="••••••••" value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })} required
                  className="w-full pl-10 pr-10 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all" />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600">
                  {showPass
                    ? <Icon d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    : <Icon d="M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 text-white font-bold text-sm transition-all shadow-lg shadow-indigo-200 flex items-center justify-center gap-2 mt-2">
              {loading ? (
                <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>{t('login.entering')}</>
              ) : (
                <>{t('login.enter')} <Icon d="M13 7l5 5m0 0l-5 5m5-5H6" /></>
              )}
            </button>
          </form>

          <div className="mt-8 text-center">
            <p className="text-base text-slate-500">
              {lang === 'ru' ? 'Нет вашей организации?' : lang === 'en' ? "Don't have a company?" : "Korxonangiz yo'qmi?"}{' '}
              <Link to="/register" className="text-indigo-600 font-bold hover:text-indigo-800 hover:underline transition-colors text-base">
                {lang === 'ru' ? 'Зарегистрируйтесь' : lang === 'en' ? 'Register' : "Ro'yxatdan o'ting"}
              </Link>
            </p>
          </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
