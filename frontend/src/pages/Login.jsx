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
  const { t } = useLang();

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

function ForgotPasswordModal({ onClose, t }) {

  const [step, setStep] = useState(1)
  const [phone, setPhone] = useState('')
  const [userName, setUserName] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPass, setNewPass] = useState('')
  const [confirmPass, setConfirmPass] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const checkPhone = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api.post('/auth/check-phone', { phone })
      setUserName(res.data.name)
      setResetToken(res.data.reset_token)
      setStep(2)
    } catch (err) {
      setError(err.response?.data?.detail || t('error.notFound'))
    } finally {
      setLoading(false)
    }
  }

  const resetPassword = async (e) => {
    e.preventDefault()
    setError('')
    if (newPass !== confirmPass) {
      setError('Parollar mos kelmadi')
      return
    }
    if (newPass.length < 6) {
      setError("Parol kamida 6 ta belgidan iborat bo'lishi kerak")
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/reset-password', { phone, new_password: newPass, reset_token: resetToken })
      setSuccess(true)
    } catch (err) {
      setError(err.response?.data?.detail || t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors">
          <Icon d="M6 18L18 6M6 6l12 12" cls="w-5 h-5" />
        </button>

        {success ? (
          <div className="text-center py-4">
            <div className="w-14 h-14 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Icon d="M5 13l4 4L19 7" cls="w-7 h-7 text-green-600" />
            </div>
            <h3 className="text-lg font-bold text-slate-800 mb-1">{t('auth.passUpdated')}</h3>
            <p className="text-sm text-slate-500 mb-5">{t('auth.loginWithNewPass')}</p>
            <button onClick={onClose} className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm transition-colors">
              {t('common.back')}
            </button>
          </div>
        ) : (
          <>
            <div className="mb-5">
              <h3 className="text-lg font-bold text-slate-800">{t('auth.resetPass')}</h3>
              <p className="text-sm text-slate-500 mt-0.5">
                {step === 1 ? 'Telefon raqamingizni kiriting' : `Salom, ${userName}! Yangi parol o'rnating`}
              </p>
              <div className="flex gap-1 mt-3">
                <div className="h-1 flex-1 rounded-full bg-indigo-600" />
                <div className={`h-1 flex-1 rounded-full ${step === 2 ? 'bg-indigo-600' : 'bg-slate-200'}`} />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-600 rounded-xl px-3 py-2.5 mb-4 text-sm">
                <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}

            {step === 1 ? (
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
            ) : (
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
                      <Icon d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </div>
                    <input type={showConfirm ? 'text' : 'password'} placeholder="••••••" value={confirmPass} onChange={e => setConfirmPass(e.target.value)} required
                      className="w-full pl-10 pr-10 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 transition-all" />
                    <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600">
                      <Icon d={showConfirm ? "M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" : "M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"} />
                    </button>
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => { setStep(1); setError('') }}
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

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(form.phone, form.password)
      navigate('/admin/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || t('login.error'))
    } finally {
      setLoading(false)
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

        {/* Logo only — lang switcher moved to top-right of right panel */}
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

        {/* Desktop: lang switcher — top-right corner */}
        <div className="hidden lg:flex absolute top-4 right-4">
          <LoginLangSwitcher lang={lang} setLang={setLang} dark={false} />
        </div>

        <div className="w-full max-w-md">

          {/* Mobile: logo + lang switcher */}
          <div className="lg:hidden flex items-center justify-between mb-8">
            <ECodeLogo size={34} showText={true} textClassName="text-lg" />
            <LoginLangSwitcher lang={lang} setLang={setLang} dark={false} />
          </div>

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
            {/* Phone */}
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

            {/* Password */}
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
              className="w-full py-3 rounded-xl bg-linear-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 text-white font-bold text-sm transition-all shadow-lg shadow-indigo-200 flex items-center justify-center gap-2 mt-2">
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
        </div>
      </div>
    </div>
  )
}
