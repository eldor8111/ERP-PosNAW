import { useState, useRef, useEffect } from 'react'
import { useLang } from '../context/LangContext'
import { Link, useNavigate } from 'react-router-dom'
import api from '../api/axios'
import ECodeLogo, { ECodeIcon } from '../components/ECodeLogo'
import { REGIONS } from '../constants/regions'
import { LANGUAGES } from '../i18n/index.js'
import { 
  Building2, 
  MapPin, 
  User, 
  Phone, 
  Lock, 
  Eye, 
  EyeOff, 
  CheckCircle2, 
  ShieldCheck, 
  Sparkles, 
  ArrowRight, 
  ArrowLeft, 
  AlertCircle,
  Tag,
  Check,
  CheckCheck
} from 'lucide-react'

function RegisterLangSwitcher({ lang, setLang }) {
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

function Steps({ current, t }) {
  const STEPS = [
    { n: 1, label: t('auth.regStep1') || "Korxona" },
    { n: 2, label: t('auth.regStep2') || "Shaxsiy" },
    { n: 3, label: "Tasdiqlash" },
  ]
  return (
    <div className="flex items-center justify-between mb-8 px-2">
      {STEPS.map((s, i) => {
        const isDone = current > s.n
        const isCurrent = current === s.n
        return (
          <div key={s.n} className="flex items-center flex-1 last:flex-none">
            <div className="flex items-center gap-2.5">
              <div
                className={`w-9 h-9 rounded-2xl flex items-center justify-center text-xs font-black transition-all duration-300 shadow-xs ${
                  isDone
                    ? 'bg-blue-600 text-white'
                    : isCurrent
                    ? 'bg-blue-600 text-white ring-4 ring-blue-100 shadow-md shadow-blue-500/25'
                    : 'bg-slate-100 text-slate-400'
                }`}
              >
                {isDone ? <Check className="w-4 h-4 stroke-[3]" /> : s.n}
              </div>
              <span
                className={`text-xs font-bold whitespace-nowrap transition-colors ${
                  isCurrent ? 'text-blue-600' : isDone ? 'text-slate-700' : 'text-slate-400'
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`flex-1 h-1 mx-3 rounded-full transition-all duration-300 ${
                  current > s.n ? 'bg-blue-600' : 'bg-slate-100'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function FloatingSelect({ label, value, onChange, options, disabled, error }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const hasValue = !!value

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => { if (!disabled) setOpen(o => !o) }}
        className={`w-full border rounded-2xl px-4 text-left text-sm transition-all relative bg-white font-medium
          focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 shadow-xs
          ${error ? 'border-rose-300 bg-rose-50/20' : open ? 'border-blue-600 ring-4 ring-blue-100' : 'border-slate-200 hover:border-slate-300'}
          ${disabled ? 'opacity-50 cursor-not-allowed bg-slate-50' : 'cursor-pointer'}
          ${hasValue ? 'pt-5 pb-2.5' : 'py-3.5'}`}
      >
        <span
          className={`absolute left-4 transition-all duration-150 pointer-events-none font-bold ${
            hasValue
              ? 'top-1.5 text-[10px] text-blue-600 uppercase tracking-wider'
              : 'top-1/2 -translate-y-1/2 text-xs text-slate-400 font-semibold'
          }`}
        >
          {label}
        </span>
        <span className={`block truncate ${hasValue ? 'text-slate-900 font-semibold' : 'text-transparent select-none'}`}>
          {value || label}
        </span>
        <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-slate-400">
          <svg className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {open && (
        <div className="absolute z-50 w-full mt-2 bg-white border border-blue-100 rounded-2xl shadow-xl max-h-56 overflow-y-auto p-1 animate-in fade-in">
          {options.map(opt => (
            <button
              key={opt}
              type="button"
              onClick={() => { onChange(opt); setOpen(false) }}
              className={`w-full text-left px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-colors ${
                value === opt
                  ? 'bg-blue-50 text-blue-700 font-bold'
                  : 'text-slate-700 hover:bg-slate-50 hover:text-blue-600'
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
      {error && <p className="text-[11px] text-rose-600 font-semibold mt-1.5 flex items-center gap-1"><span>⚠</span>{error}</p>}
    </div>
  )
}

export default function RegisterCompany() {
  const { t, lang, setLang } = useLang()
  const navigate = useNavigate()

  const [step, setStep] = useState(1)
  const [otpSession, setOtpSession] = useState(null)
  const [otpCode, setOtpCode] = useState('')
  const [form, setForm] = useState({
    company_name: '', region: '', district: '',
    name: '', phone: '', agent_code: 'A0001',
    password: '', confirm_password: '', oferta: false,
  })
  const [errors, setErrors] = useState({})
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [agentStatus, setAgentStatus] = useState(null)
  const [agentName, setAgentName] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const clearErr = k => setErrors(e => { const n = { ...e }; delete n[k]; return n })
  const districts = form.region ? REGIONS[form.region] || [] : []

  const checkAgentCode = async (code) => {
    if (!code.trim()) { setAgentStatus(null); setAgentName(''); return }
    setAgentStatus('checking')
    try {
      const { data } = await api.post('/auth/check-agent-code', { code: code.trim().toUpperCase() })
      setAgentStatus(data.valid ? 'valid' : 'invalid')
      setAgentName(data.valid ? data.agent_name : '')
    } catch { setAgentStatus('invalid'); setAgentName('') }
  }

  const validateStep1 = () => {
    const e = {}
    if (!form.company_name.trim()) e.company_name = t('auth.errCompanyReq') || "Korxona nomi kiritilishi shart"
    if (!form.region) e.region = t('auth.errRegionReq') || "Viloyat tanlanishi shart"
    if (!form.district) e.district = t('auth.errDistrictReq') || "Tuman tanlanishi shart"
    setErrors(e)
    return !Object.keys(e).length
  }

  const validateStep2 = () => {
    const e = {}
    if (!form.name.trim()) e.name = t('auth.errNameReq') || "Ism familiya kiritilishi shart"
    if (!form.phone.trim()) e.phone = t('auth.errPhoneReq') || "Telefon raqam kiritilishi shart"
    if (form.password.length < 6) e.password = t('auth.errPassLen') || "Kamida 6 ta belgi"
    if (form.password !== form.confirm_password) e.confirm_password = t('auth.errPassMatch') || "Parollar mos kelmadi"
    if (agentStatus === 'invalid') e.agent_code = t('auth.errAgentNotFound') || "Agent kodi topilmadi"
    if (!form.oferta) e.oferta = t('auth.errOfertaReq') || "Ommaviy oferta shartlariga rozi bo'lishingiz shart"
    setErrors(e)
    return !Object.keys(e).length
  }

  // Step 2 → OTP yuborish
  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validateStep2()) return
    setLoading(true)
    setErrors({})
    try {
      const { data } = await api.post('/auth/send-otp', {
        phone: form.phone.replace(/[^0-9]/g, ''),
        purpose: 'register'
      })
      if (data.sent || data.dev_mode) {
        setOtpSession(data.otp_session)
        setStep(3)
      } else {
        setErrors({ submit: data.message || "SMS yuborishda xatolik yuz berdi" })
      }
    } catch (err) {
      const detail = err.response?.data?.detail
      setErrors({ submit: detail || t('auth.errGeneral') || 'Xatolik yuz berdi' })
    } finally {
      setLoading(false)
    }
  }

  // Step 3 → OTP tasdiqlash va ro'yxatdan o'tish
  const handleVerifyOtp = async (e) => {
    e.preventDefault()
    if (!otpCode || otpCode.length !== 4) {
      setErrors({ otp: "Kodni to'g'ri kiriting" })
      return
    }
    setLoading(true)
    setErrors({})
    try {
      const { data: verifyData } = await api.post('/auth/verify-otp', {
        phone: form.phone.replace(/[^0-9]/g, ''),
        otp: otpCode,
        otp_session: otpSession
      })

      const payload = {
        company_name: form.company_name,
        name: form.name,
        phone: form.phone.replace(/[^0-9]/g, ''),
        region: form.region,
        district: form.district,
        password: form.password,
        otp_verified_token: verifyData.verified_token
      }
      if (form.agent_code.trim()) payload.agent_code = form.agent_code.trim().toUpperCase()
      const { data } = await api.post('/auth/register', payload)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      setDone({ org_code: data.org_code, company_name: data.company_name })
    } catch (err) {
      const detail = err.response?.data?.detail
      setErrors({ submit: detail || 'Tasdiqlashda xatolik yuz berdi' })
    } finally {
      setLoading(false)
    }
  }

  // ── SUCCESS SCREEN ──
  if (done) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center p-4 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
        </div>
        <div className="w-full max-w-lg relative z-10">
          <div className="bg-white/95 backdrop-blur-2xl border border-blue-100 rounded-3xl shadow-[0_25px_60px_-15px_rgba(37,99,235,0.15)] p-8 sm:p-10 text-center">
            
            <div className="w-20 h-20 mx-auto mb-6 rounded-3xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-xl shadow-blue-500/25 text-white">
              <CheckCircle2 className="w-10 h-10" />
            </div>

            <h2 className="text-3xl font-black text-slate-900 mb-2">{t('common.success')}</h2>
            <p className="text-slate-500 text-sm mb-6">{t('auth.companyRegistered')}</p>

            <div className="mb-4 bg-slate-50/80 border border-slate-200/80 rounded-2xl px-6 py-4">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{t('settings.companyName')}</p>
              <div className="text-xl font-black text-slate-800">{done.company_name}</div>
            </div>

            <div className="mb-6 bg-gradient-to-br from-blue-50/90 to-indigo-50/80 border border-blue-200/80 rounded-2xl px-6 py-6 shadow-xs">
              <p className="text-xs font-bold text-blue-600 uppercase tracking-widest mb-2">{t('settings.orgCode')}</p>
              <div className="text-5xl font-black text-blue-700 tracking-[0.2em] leading-none my-2 font-mono">{done.org_code}</div>
              <div className="flex items-center justify-center gap-2 text-xs text-amber-700 bg-amber-50 rounded-xl px-4 py-2.5 mt-4 border border-amber-200 font-semibold">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
                <span>{t('auth.saveThisCode') || "Ushbu kodni albatta saqlab qo'ying!"}</span>
              </div>
            </div>

            <button
              onClick={() => window.location.href = '/admin/'}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-base shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transition-all flex items-center justify-center gap-2"
            >
              <span>{t('login.enter') || "Tizimga kirish"}</span>
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] relative overflow-hidden flex flex-col justify-between">
      
      {/* Background Tech Grid & Glows */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div 
          className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage: `radial-gradient(#2563EB 1px, transparent 1px)`,
            backgroundSize: '28px 28px'
          }}
        />
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] bg-gradient-to-br from-blue-400/15 to-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-40 -right-40 w-[700px] h-[700px] bg-gradient-to-tl from-blue-500/15 to-sky-300/10 rounded-full blur-3xl pointer-events-none" />
      </div>

      {/* Top Header */}
      <header className="relative z-10 w-full max-w-7xl mx-auto px-6 py-6 flex items-center justify-between">
        <Link to="/landing" className="flex items-center gap-3 group">
          <ECodeLogo size={42} showText={true} />
        </Link>
        <RegisterLangSwitcher lang={lang} setLang={setLang} />
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
        <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          
          {/* Left Side: Enterprise Perks & Mockup matching */}
          <div className="hidden lg:flex lg:col-span-5 flex-col justify-center space-y-8 pr-4">
            
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-bold w-fit shadow-xs">
              <Sparkles className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
              <span>14 kunlik bepul sinov davri</span>
            </div>

            <div>
              <h1 className="text-4xl xl:text-5xl font-black text-slate-900 tracking-tight leading-[1.15]">
                {t('auth.manageYour') || 'Korxonangizni'}{' '}
                <span className="bg-gradient-to-r from-blue-600 via-blue-700 to-indigo-600 bg-clip-text text-transparent">
                  {t('auth.manageBusiness') || "raqamlashtiring"}
                </span>
              </h1>
              <p className="mt-4 text-slate-600 text-sm leading-relaxed">
                {t('auth.registerDesc') || "Savdo, ombor, mijozlar va hisobotlarni bitta kuchli va xavfsiz ERP tizimida jamlang."}
              </p>
            </div>

            {/* Verified Enterprise Card (matches mockup) */}
            <div className="p-6 rounded-3xl bg-white/90 backdrop-blur-xl border border-blue-100 shadow-[0_12px_35px_rgba(37,99,235,0.06)] space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/25">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="text-sm font-black text-slate-900">Verified Enterprise</h4>
                  <p className="text-xs text-slate-500">Rasmiy xavfsizlik va kafolat</p>
                </div>
              </div>

              <div className="space-y-2.5 pt-2 border-t border-slate-100">
                {[
                  "Real vaqtda savdo hisoboti",
                  "Avtomatlashtirilgan kassa va ombor",
                  "Jamoaviy qulay boshqaruv",
                  "Bank darajasidagi ma'lumotlar xavfsizligi"
                ].map((perk, i) => (
                  <div key={i} className="flex items-center gap-2.5 text-xs font-bold text-slate-700">
                    <CheckCheck className="w-4 h-4 text-blue-600 shrink-0" />
                    <span>{perk}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Right Side: Registration Form Card */}
          <div className="lg:col-span-7 flex justify-center">
            <div className="w-full max-w-xl bg-white/95 backdrop-blur-2xl border border-blue-100/90 rounded-3xl shadow-[0_20px_60px_-15px_rgba(37,99,235,0.12)] p-8 sm:p-10 relative">

              <div className="mb-6">
                <h2 className="text-2xl font-black text-slate-900 tracking-tight">
                  {t('land.nav.register')}
                </h2>
                <p className="text-slate-500 text-xs mt-1">
                  {t('auth.createAccount')}
                </p>
              </div>

              <Steps current={step} t={t} />

              {/* ── STEP 1: Korxona ── */}
              {step === 1 && (
                <div className="space-y-5 animate-in fade-in">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                      {t('auth.companyNameLabel') || "Korxona nomi"}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-400">
                        <Building2 className="w-4 h-4" />
                      </div>
                      <input
                        type="text"
                        value={form.company_name}
                        onChange={e => { set('company_name', e.target.value); clearErr('company_name') }}
                        placeholder={t('auth.companyNamePl') || "Masalan: Baraka Savdo MChJ"}
                        className={`w-full pl-11 pr-4 py-3.5 border rounded-2xl bg-white text-sm font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs ${
                          errors.company_name ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200'
                        }`}
                      />
                    </div>
                    {errors.company_name && (
                      <p className="text-[11px] text-rose-600 font-semibold mt-1.5 flex items-center gap-1">
                        <span>⚠</span>{errors.company_name}
                      </p>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <FloatingSelect
                      label={t('auth.region') || "Viloyat"}
                      value={form.region}
                      onChange={v => { set('region', v); set('district', ''); clearErr('region') }}
                      options={Object.keys(REGIONS)}
                      error={errors.region}
                    />
                    <FloatingSelect
                      label={t('auth.district') || "Tuman / Shahar"}
                      value={form.district}
                      onChange={v => { set('district', v); clearErr('district') }}
                      options={districts}
                      disabled={!form.region}
                      error={errors.district}
                    />
                  </div>

                  <button
                    type="button"
                    onClick={() => { if (validateStep1()) setStep(2) }}
                    className="w-full py-3.5 px-6 rounded-2xl bg-gradient-to-r from-blue-600 via-blue-700 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transition-all flex items-center justify-center gap-2 mt-4"
                  >
                    <span>{t('common.nextStep') || "Keyingi qadam"}</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>

                  <div className="pt-4 border-t border-slate-100 text-center">
                    <p className="text-xs sm:text-sm text-slate-500 font-medium">
                      {t('auth.alreadyHaveAcc') || "Allaqachon hisobingiz bormi?"}{' '}
                      <Link to="/login" className="text-blue-600 font-bold hover:underline ml-1">
                        {t('land.nav.login')}
                      </Link>
                    </p>
                  </div>
                </div>
              )}

              {/* ── STEP 2: Shaxsiy ── */}
              {step === 2 && (
                <form onSubmit={handleSubmit} className="space-y-4 animate-in fade-in">
                  
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                        {t('auth.nameSurname') || "Ism Familya"}
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                          <User className="w-4 h-4" />
                        </div>
                        <input
                          type="text"
                          value={form.name}
                          onChange={e => { set('name', e.target.value); clearErr('name') }}
                          placeholder={t('auth.namePl') || "Alisher Rahimov"}
                          className={`w-full pl-10 pr-3 py-3 border rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs ${
                            errors.name ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200'
                          }`}
                        />
                      </div>
                      {errors.name && <p className="text-[10px] text-rose-600 font-semibold mt-1">⚠ {errors.name}</p>}
                    </div>

                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                        {t('auth.phone') || "Telefon raqami"}
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                          <Phone className="w-4 h-4" />
                        </div>
                        <input
                          type="text"
                          value={form.phone}
                          onChange={e => { set('phone', e.target.value); clearErr('phone') }}
                          placeholder={t('auth.phonePl') || "+998 90 000 00 00"}
                          className={`w-full pl-10 pr-3 py-3 border rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs ${
                            errors.phone ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200'
                          }`}
                        />
                      </div>
                      {errors.phone && <p className="text-[10px] text-rose-600 font-semibold mt-1">⚠ {errors.phone}</p>}
                    </div>
                  </div>

                  {/* Agent Code */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-bold uppercase tracking-wider text-slate-700">
                        {t('auth.agentCode') || "Agent kodi"}
                      </label>
                      <span className="text-[10px] text-slate-400 font-medium">Ixtiyoriy</span>
                    </div>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                        <Tag className="w-4 h-4" />
                      </div>
                      <input
                        type="password"
                        value={form.agent_code}
                        onChange={e => {
                          const v = e.target.value.toUpperCase()
                          set('agent_code', v); clearErr('agent_code')
                          if (v.length >= 3) checkAgentCode(v)
                          else { setAgentStatus(null); setAgentName('') }
                        }}
                        placeholder="••••••"
                        className={`w-full pl-10 pr-10 py-3 border rounded-2xl bg-white text-xs font-mono tracking-widest text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs ${
                          errors.agent_code || agentStatus === 'invalid' ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200'
                        }`}
                      />
                      <div className="absolute inset-y-0 right-3.5 flex items-center">
                        {agentStatus === 'checking' && (
                          <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                        )}
                        {agentStatus === 'valid' && (
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        )}
                        {agentStatus === 'invalid' && (
                          <AlertCircle className="w-4 h-4 text-rose-600" />
                        )}
                      </div>
                    </div>
                    {agentStatus === 'valid' && (
                      <p className="text-[11px] text-emerald-600 font-bold mt-1">✓ {agentName}</p>
                    )}
                    {errors.agent_code && (
                      <p className="text-[10px] text-rose-600 font-semibold mt-1">⚠ {errors.agent_code}</p>
                    )}
                  </div>

                  {/* Password & Confirm */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                        {t('login.password') || "Parol"}
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                          <Lock className="w-4 h-4" />
                        </div>
                        <input
                          type={showPass ? 'text' : 'password'}
                          value={form.password}
                          onChange={e => { set('password', e.target.value); clearErr('password') }}
                          placeholder={t('auth.passwordPl') || "Kamida 6 belgi"}
                          className={`w-full pl-10 pr-9 py-3 border rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs ${
                            errors.password ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200'
                          }`}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPass(!showPass)}
                          className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600"
                        >
                          {showPass ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                      {errors.password && <p className="text-[10px] text-rose-600 font-semibold mt-1">⚠ {errors.password}</p>}
                    </div>

                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                        {t('auth.confirmPassword') || "Qayta kiriting"}
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                          <Lock className="w-4 h-4" />
                        </div>
                        <input
                          type={showConfirm ? 'text' : 'password'}
                          value={form.confirm_password}
                          onChange={e => { set('confirm_password', e.target.value); clearErr('confirm_password') }}
                          placeholder={t('auth.confirmPasswordPl') || "Takrorlang"}
                          className={`w-full pl-10 pr-9 py-3 border rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs ${
                            errors.confirm_password ? 'border-rose-300 bg-rose-50/20' : 'border-slate-200'
                          }`}
                        />
                        <button
                          type="button"
                          onClick={() => setShowConfirm(!showConfirm)}
                          className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600"
                        >
                          {showConfirm ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                      {errors.confirm_password && <p className="text-[10px] text-rose-600 font-semibold mt-1">⚠ {errors.confirm_password}</p>}
                    </div>
                  </div>

                  {errors.submit && (
                    <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-2xl px-4 py-3 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{errors.submit}</span>
                    </div>
                  )}

                  {/* Oferta */}
                  <div className="flex items-start gap-3 py-1">
                    <input
                      type="checkbox"
                      id="oferta"
                      checked={form.oferta}
                      onChange={e => { set('oferta', e.target.checked); clearErr('oferta') }}
                      className="mt-0.5 w-4 h-4 text-blue-600 rounded-lg border-slate-300 focus:ring-blue-500 cursor-pointer"
                    />
                    <label htmlFor="oferta" className="text-xs text-slate-600 leading-tight cursor-pointer">
                      Men <a href="/oferta.pdf" target="_blank" className="text-blue-600 font-bold hover:underline">Ommaviy oferta</a> shartlari bilan tanishdim va rozi man
                    </label>
                  </div>
                  {errors.oferta && <p className="text-[10px] text-rose-600 font-semibold">⚠ {errors.oferta}</p>}

                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setStep(1)}
                      className="px-5 py-3.5 rounded-2xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-bold text-xs transition-all flex items-center gap-1.5"
                    >
                      <ArrowLeft className="w-4 h-4" />
                      <span>{t('auth.back') || "Ortga"}</span>
                    </button>
                    <button
                      type="submit"
                      disabled={loading}
                      className="flex-1 py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-xs shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2"
                    >
                      {loading ? (
                        <span>Yuklanmoqda...</span>
                      ) : (
                        <>
                          <span>{t('auth.regBtn') || "Ro'yxatdan o'tish"}</span>
                          <ArrowRight className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* ── STEP 3: SMS Kod ── */}
              {step === 3 && (
                <form onSubmit={handleVerifyOtp} className="space-y-5 animate-in fade-in">
                  <div className="text-center mb-6">
                    <div className="w-14 h-14 mx-auto bg-blue-50 border border-blue-100 text-blue-600 rounded-2xl flex items-center justify-center mb-3">
                      <Phone className="w-6 h-6" />
                    </div>
                    <h3 className="text-lg font-black text-slate-900">SMS kodni kiriting</h3>
                    <p className="text-slate-500 text-xs mt-1">
                      <span className="font-bold text-slate-800">{form.phone}</span> raqamiga tasdiqlash kodi yuborildi
                    </p>
                  </div>

                  <div>
                    <input
                      type="text"
                      maxLength={4}
                      value={otpCode}
                      onChange={e => { setOtpCode(e.target.value.replace(/\D/g, '')); clearErr('otp') }}
                      placeholder="• • • •"
                      className="w-full border border-slate-200 rounded-2xl px-4 py-3.5 text-center text-3xl font-mono tracking-[0.5em] text-slate-900 placeholder-slate-300 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all bg-white shadow-xs"
                    />
                    {errors.otp && <p className="text-[11px] text-rose-600 font-semibold mt-1.5 text-center">⚠ {errors.otp}</p>}
                  </div>

                  {errors.submit && (
                    <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-2xl px-4 py-3 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{errors.submit}</span>
                    </div>
                  )}

                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setStep(2)}
                      className="px-5 py-3.5 rounded-2xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-bold text-xs transition-all flex items-center gap-1.5"
                    >
                      <ArrowLeft className="w-4 h-4" />
                      <span>Ortga</span>
                    </button>
                    <button
                      type="submit"
                      disabled={loading || otpCode.length !== 4}
                      className="flex-1 py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-xs shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2"
                    >
                      {loading ? (
                        <span>Tasdiqlanmoqda...</span>
                      ) : (
                        <>
                          <span>Tasdiqlash va kirish</span>
                          <CheckCircle2 className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

            </div>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 w-full py-6 text-center text-xs text-slate-400">
        <p>© {new Date().getFullYear()} E-Code Universal ERP. Barcha huquqlar himoyalangan.</p>
      </footer>

    </div>
  )
}
