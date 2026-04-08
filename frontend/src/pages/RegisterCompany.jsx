import { useState, useRef, useEffect, useCallback } from 'react'
import { useLang } from '../context/LangContext';
import { Link } from 'react-router-dom'
import api from '../api/axios'
import { ECodeLogoPrimary } from '../components/ECodeLogo'
import ECodeLogo from '../components/ECodeLogo'

const REGIONS = {
  "Toshkent shahri": ["Bektemir","Chilonzor","Hamza","Mirzo Ulug'bek","Mirobod","Sergeli","Shayxontohur","Olmazor","Uchtepa","Yakkasaroy","Yunusobod"],
  "Toshkent viloyati": ["Angren","Bekabad","Bo'ka","Bo'stonliq","Chirchiq","Chinoz","Ohangaron","Olmaliq","Oqqo'rg'on","Parkent","Piskent","Quyichirchiq","Toshkent tumani","Yuqorichirchiq","Zangiota"],
  "Andijon viloyati": ["Andijon shahri","Asaka","Baliqchi","Bo'z","Buloqboshi","Jalaquduq","Izboskan","Xo'jaobod","Marhamat","Oltinko'l","Paxtaobod","Qo'rg'ontepa","Shahrixon","Ulug'nor"],
  "Farg'ona viloyati": ["Farg'ona shahri","Beshariq","Bog'dod","Buvayda","Dang'ara","Furqat","Qo'shtepa","Marg'ilon","Oltiariq","Quva","Rishton","So'x","Toshloq","O'zbekiston","Yozyovon"],
  "Namangan viloyati": ["Namangan shahri","Chortoq","Chust","Kosonsoy","Mingbuloq","Namangan tumani","Norin","Pop","To'raqo'rg'on","Uchqo'rg'on","Yangiqo'rg'on"],
  "Samarqand viloyati": ["Samarqand shahri","Bulung'ur","Ishtixon","Jomboy","Kattaqo'rg'on","Narpay","Nurobod","Oqdaryo","Pastdarg'om","Paxtachi","Payariq","Qo'shrabot","Toyloq","Urgut"],
  "Buxoro viloyati": ["Buxoro shahri","Buxoro tumani","G'ijduvon","Jondor","Kogon","Qorovulbozor","Olot","Peshku","Romitan","Shofirkon","Vobkent"],
  "Navoiy viloyati": ["Navoiy shahri","Karmana","Konimex","Navbahor","Nurota","Qiziltepa","Tomdi","Uchquduq","Xatirchi"],
  "Qashqadaryo viloyati": ["Qarshi shahri","Chiroqchi","Dehqonobod","G'uzor","Kamashi","Kasbi","Kitob","Koson","Mirishkor","Muborak","Nishon","Qamashi","Shahrisabz","Yakkabog'"],
  "Surxondaryo viloyati": ["Termiz shahri","Angor","Bandixon","Boysun","Denov","Jarqo'rg'on","Muzrabot","Oltinsoy","Qiziriq","Sariosiyo","Sherobod","Sho'rchi","Uzun"],
  "Jizzax viloyati": ["Jizzax shahri","Arnasoy","Baxmal","Do'stlik","Forish","G'allaorol","Mirzacho'l","Paxtakor","Yangiobod","Zafarobod","Zarbdor"],
  "Sirdaryo viloyati": ["Guliston shahri","Boyovut","Xovos","Mirzaobod","Oqoltin","Sardoba","Sayxunobod","Shirin","Sirdaryo tumani"],
  "Xorazm viloyati": ["Urganch shahri","Bog'ot","Gurlan","Xiva","Xonqa","Qo'shko'pir","Shovot","Tuproqqal'a","Urganch tumani","Yangiariq","Yangibozor"],
  "Qoraqalpog'iston Respublikasi": ["Nukus shahri","Amudaryo","Beruniy","Chimboy","Ellikkala","Kegeyli","Mo'ynoq","Nukus tumani","Qanliko'l","Qo'ng'irot","Qorao'zak","Shumanay","Taxtako'pir","To'rtko'l","Xo'jayli"],
}

const Icon = ({ d, cls = "w-4 h-4" }) => (
  <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={d} />
  </svg>
)
const EyeOpen = () => <Icon d="M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
const EyeOff = () => <Icon d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />

// OTP Input — 6 ta katak
function OtpInput({ value, onChange }) {
  const handleKey = (e, i) => {
    const num = e.key
    if (num >= '0' && num <= '9') {
      const arr = value.padEnd(6, ' ').split('')
      arr[i] = num
      onChange(arr.join('').trimEnd())
      const next = document.getElementById(`reg-otp-${i + 1}`)
      if (next) next.focus()
    } else if (num === 'Backspace') {
      onChange(value.slice(0, Math.max(0, i)))
      const prev = document.getElementById(`reg-otp-${i - 1}`)
      if (prev) prev.focus()
    }
  }
  const digits = (value + '      ').slice(0, 6).split('')
  return (
    <div className="flex gap-2 justify-center my-1">
      {[0,1,2,3,4,5].map(i => (
        <input key={i} id={`reg-otp-${i}`} type="text" inputMode="numeric" maxLength={1}
          value={digits[i].trim()} readOnly
          onKeyDown={e => handleKey(e, i)} onFocus={e => e.target.select()}
          className="w-11 text-center text-xl font-bold border-2 rounded-xl border-slate-200 bg-white text-slate-800
            focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 transition-all caret-transparent"
          style={{ width: 44, height: 52 }}
        />
      ))}
    </div>
  )
}

function Steps({ current }) {
  const STEPS = [
    { n: 1, label: "Korxona ma'lumotlari" },
    { n: 2, label: 'Shaxsiy ma\'lumotlar' },
    { n: 3, label: 'OTP Tasdiqlash' },
  ]
  return (
    <div className="flex items-center mb-8">
      {STEPS.map((s, i, arr) => (
        <div key={s.n} className="flex items-center flex-1">
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all
              ${current > s.n ? 'bg-indigo-600 text-white' :
                current === s.n ? 'bg-indigo-600 text-white ring-4 ring-indigo-100' :
                'bg-slate-100 text-slate-400'}`}>
              {current > s.n ? <Icon d="M5 13l4 4L19 7" cls="w-3.5 h-3.5" /> : s.n}
            </div>
            <span className={`text-xs mt-1.5 font-medium whitespace-nowrap ${current >= s.n ? 'text-indigo-600' : 'text-slate-400'}`}>
              {s.label}
            </span>
          </div>
          {i < arr.length - 1 && (
            <div className={`flex-1 h-0.5 mx-3 mb-5 rounded ${current > s.n ? 'bg-indigo-500' : 'bg-slate-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

function InputField({ label, icon, error, hint, children }) {
  return (
    <div>
      <label className="flex text-sm font-semibold text-slate-700 mb-1.5 items-center gap-1.5">
        {icon && <span className="text-indigo-500">{icon}</span>}
        {label}
      </label>
      {children}
      {error && <p className="text-xs text-red-500 mt-1 flex items-center gap-1"><span>⚠</span>{error}</p>}
      {hint && !error && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  )
}

const inputBase = `w-full border rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400
  focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400
  transition-all bg-white`

function TInput({ icon, right, err, ...props }) {
  return (
    <div className="relative">
      {icon && <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">{icon}</div>}
      <input
        {...props}
        className={`${inputBase} ${icon ? 'pl-10' : ''} ${right ? 'pr-10' : ''} ${err ? 'border-red-300 bg-red-50/30' : 'border-slate-200'}`}
      />
      {right && <div className="absolute inset-y-0 right-3 flex items-center">{right}</div>}
    </div>
  )
}

function FloatingSelect({ label, value, onChange, options, disabled, error }) {
  const { t } = useLang();

  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const hasValue = !!value

  return (
    <div>
      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => { if (!disabled) setOpen(o => !o) }}
          className={`w-full border rounded-xl px-4 text-left text-sm transition-all relative
            focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400
            ${error ? 'border-red-300 bg-red-50/30' : open ? 'border-indigo-400 ring-2 ring-indigo-100 bg-white' : 'border-slate-200 bg-white hover:border-slate-300'}
            ${disabled ? 'opacity-50 cursor-not-allowed bg-slate-50' : 'cursor-pointer'}
            ${hasValue ? 'pt-5 pb-2' : 'py-3.5'}`}
        >
          <span className={`absolute left-4 transition-all duration-150 pointer-events-none font-medium
            ${hasValue
              ? 'top-1.5 text-[10px] text-indigo-500 uppercase tracking-wide'
              : 'top-1/2 -translate-y-1/2 text-sm text-slate-400'}`}>
            {label}
          </span>
          <span className={`block truncate ${hasValue ? 'text-slate-800' : 'text-transparent select-none'}`}>
            {value || label}
          </span>
        </button>
        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400">
          <Icon d={open ? "M5 15l7-7 7 7" : "M19 9l-7 7-7-7"} />
        </div>

        {open && (
          <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-60 overflow-y-auto">
            {options.map(opt => (
              <button
                key={opt}
                type="button"
                onClick={() => { onChange(opt); setOpen(false) }}
                className={`w-full text-left px-4 py-2.5 text-sm transition-colors
                  ${value === opt
                    ? 'bg-indigo-50 text-indigo-700 font-semibold'
                    : 'text-slate-700 hover:bg-slate-50 hover:text-indigo-600'}`}
              >
                {opt}
              </button>
            ))}
          </div>
        )}
      </div>
      {error && <p className="text-xs text-red-500 mt-1 flex items-center gap-1"><span>⚠</span>{error}</p>}
    </div>
  )
}

export default function RegisterCompany() {
  const { t } = useLang();

  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    company_name: '', region: '', district: '',
    name: '', phone: '', agent_code: '',
    password: '', confirm_password: '',
  })
  const [errors, setErrors] = useState({})
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [agentStatus, setAgentStatus] = useState(null)
  const [agentName, setAgentName] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(null)
  // OTP state
  const [otp, setOtp] = useState('')
  const [otpError, setOtpError] = useState('')
  const [otpLoading, setOtpLoading] = useState(false)
  const [otpSent, setOtpSent] = useState(false)
  const [devMode, setDevMode] = useState(false)
  const [resendTimer, setResendTimer] = useState(0)
  const [verifiedToken, setVerifiedToken] = useState('')

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
    if (!form.company_name.trim()) e.company_name = "Korxona nomi kiritilishi shart"
    if (!form.region) e.region = "Viloyat tanlanishi shart"
    if (!form.district) e.district = "Tuman tanlanishi shart"
    setErrors(e)
    return !Object.keys(e).length
  }

  const validateStep2 = () => {
    const e = {}
    if (!form.name.trim()) e.name = "Ism familya kiritilishi shart"
    if (!form.phone.trim()) e.phone = "Telefon raqam kiritilishi shart"
    if (form.password.length < 6) e.password = "Kamida 6 ta belgi"
    if (form.password !== form.confirm_password) e.confirm_password = "Parollar mos kelmadi"
    if (agentStatus === 'invalid') e.agent_code = "Agent kodi topilmadi"
    setErrors(e)
    return !Object.keys(e).length
  }

  // Resend timer
  const startResendTimer = useCallback(() => {
    setResendTimer(60)
    const interval = setInterval(() => {
      setResendTimer(prev => {
        if (prev <= 1) { clearInterval(interval); return 0 }
        return prev - 1
      })
    }, 1000)
  }, [])

  // Step 2 → Step 3: OTP yuborish
  const goToOtp = async () => {
    if (!validateStep2()) return
    setOtpLoading(true)
    setOtpError('')
    try {
      const normalized = form.phone.replace(/[^0-9]/g, '')
      const res = await api.post('/auth/send-otp', { phone: normalized, purpose: 'register' })
      setDevMode(res.data.dev_mode || false)
      setOtpSent(true)
      setStep(3)
      startResendTimer()
    } catch (err) {
      setErrors({ submit: err.response?.data?.detail || 'OTP yuborishda xato' })
    } finally {
      setOtpLoading(false)
    }
  }

  // OTP qayta yuborish
  const resendOtp = async () => {
    if (resendTimer > 0) return
    setOtpLoading(true)
    setOtpError('')
    try {
      const normalized = form.phone.replace(/[^0-9]/g, '')
      const res = await api.post('/auth/send-otp', { phone: normalized, purpose: 'register' })
      setDevMode(res.data.dev_mode || false)
      startResendTimer()
    } catch (err) {
      setOtpError(err.response?.data?.detail || 'Xatolik')
    } finally {
      setOtpLoading(false)
    }
  }

  // OTP tasdiqlash
  const verifyOtp = async () => {
    if (otp.length < 6) { setOtpError("6 xonali kodni to'liq kiriting"); return }
    setOtpLoading(true)
    setOtpError('')
    try {
      const normalized = form.phone.replace(/[^0-9]/g, '')
      const res = await api.post('/auth/verify-otp', { phone: normalized, otp })
      setVerifiedToken(res.data.verified_token)
      // OTP tasdiqlandi — ro'yxatni yakunlash
      await submitRegister(res.data.verified_token)
    } catch (err) {
      setOtpError(err.response?.data?.detail || "OTP noto'g'ri")
      setOtp('')
    } finally {
      setOtpLoading(false)
    }
  }

  const submitRegister = async (vToken) => {
    setLoading(true)
    try {
      const payload = {
        company_name: form.company_name, name: form.name,
        phone: form.phone, region: form.region,
        district: form.district, password: form.password,
        otp_verified_token: vToken || verifiedToken || undefined,
      }
      if (form.agent_code.trim()) payload.agent_code = form.agent_code.trim().toUpperCase()
      const { data } = await api.post('/auth/register', payload)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      setDone({ org_code: data.org_code, company_name: data.company_name })
    } catch (err) {
      setOtpError(err.response?.data?.detail || 'Xatolik yuz berdi')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validateStep2()) return
    // Dev modeda OTP skip — to'g'ridan submit
    await submitRegister(null)
  }

  /* ── SUCCESS ── */
  if (done) {
    return (
      <div className="min-h-screen bg-linear-to-br from-indigo-600 via-indigo-700 to-purple-700 flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          <div className="bg-white rounded-3xl shadow-2xl p-10 text-center">

            {/* Icon */}
            <div className="w-24 h-24 mx-auto mb-6 rounded-3xl bg-linear-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow-xl shadow-emerald-200">
              <Icon d="M5 13l4 4L19 7" cls="w-12 h-12 text-white" />
            </div>

            <h2 className="text-3xl font-black text-slate-800 mb-2">{t('common.success')}</h2>
            <p className="text-slate-500 text-base mb-8">{t('auth.companyRegistered')}</p>

            {/* Company Name */}
            <div className="mb-4 bg-slate-50 border-2 border-slate-200 rounded-2xl px-6 py-4">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">{t('settings.companyName')}</p>
              <div className="text-2xl font-black text-slate-800">{done.company_name}</div>
            </div>

            {/* Org Code */}
            <div className="mb-5 bg-linear-to-br from-indigo-50 to-purple-50 border-2 border-indigo-200 rounded-2xl px-6 py-5">
              <p className="text-xs font-bold text-indigo-400 uppercase tracking-widest mb-3">{t('settings.orgCode')}</p>
              <div className="text-6xl font-black text-indigo-700 tracking-[0.25em] leading-none">{done.org_code}</div>
              <div className="flex items-center justify-center gap-2 text-sm text-amber-700 bg-amber-50 rounded-xl px-4 py-2.5 mt-4 border border-amber-200 font-semibold">
                <Icon d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" cls="w-5 h-5 shrink-0 text-amber-600" />
                Ushbu kodni albatta saqlab qo'ying!
              </div>
            </div>

            {/* Balance info */}
            <div className="mb-6 bg-emerald-50 border border-emerald-200 rounded-2xl px-5 py-3 flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center shrink-0">
                <Icon d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-5 h-5 text-emerald-600" />
              </div>
              <div className="text-left">
                <p className="text-xs font-bold text-emerald-700 uppercase tracking-wide">{t('auth.balanceOpened')}</p>
                <p className="text-sm text-emerald-600">{t('auth.fillBalance')}</p>
              </div>
            </div>

            <button
              onClick={() => window.location.href = '/admin/dashboard'}
              className="w-full py-4 rounded-2xl bg-linear-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold text-base transition-all shadow-lg shadow-indigo-300 flex items-center justify-center gap-2"
            >
              Tizimga kirish
              <Icon d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </button>
          </div>
        </div>
      </div>
    )
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

        {/* Logo */}
        <div className="relative flex items-center gap-3">
          <ECodeLogoPrimary size={40} />
        </div>

        {/* Center content */}
        <div className="relative space-y-6">
          <div>
            <h2 className="text-2xl font-black text-white leading-tight mb-2">
              Biznesingizni<br />
              <span className="text-indigo-200">{t('auth.manageBusiness')}</span>
            </h2>
            <p className="text-indigo-300/80 text-xs leading-relaxed mt-3">
              Ro'yxatdan o'tib, savdo, ombor va moliyani bitta tizimda boshqaring.
            </p>
          </div>

          <div className="space-y-3">
            {[
              { icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z", label: "Real vaqtda savdo hisoboti" },
              { icon: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4", label: "Ombor va zaxira boshqaruvi" },
              { icon: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z", label: "Moliyaviy nazorat" },
              { icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z", label: "Xavfsiz va ishonchli tizim" },
            ].map(item => (
              <div key={item.label} className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-lg bg-white/15 flex items-center justify-center shrink-0">
                  <Icon d={item.icon} cls="w-3.5 h-3.5 text-indigo-200" />
                </div>
                <span className="text-indigo-100 text-xs">{item.label}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-indigo-300/50 text-xs">{t('common.copyright')}</p>
      </div>

      {/* ── Right panel (form) ── */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-xl">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <ECodeLogo size={34} showText={true} textClassName="text-lg" />
          </div>

          <div className="mb-7">
            <h1 className="text-2xl font-black text-slate-800">{t('land.nav.register')}</h1>
            <p className="text-slate-500 text-sm mt-1">{t('auth.createAccount')}</p>
          </div>

          <Steps current={step} />

          {/* ── STEP 1 ── */}
          {step === 1 && (
            <div className="space-y-5">
              <InputField
                label="Korxona nomi"
                icon={<Icon d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />}
                error={errors.company_name}
              >
                <TInput
                  value={form.company_name}
                  onChange={e => { set('company_name', e.target.value); clearErr('company_name') }}
                  placeholder="Masalan: Baraka Savdo MChJ"
                  icon={<Icon d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />}
                  err={errors.company_name}
                />
              </InputField>

              <div className="grid grid-cols-2 gap-4">
                <FloatingSelect
                  label="Viloyat"
                  value={form.region}
                  onChange={v => { set('region', v); set('district', ''); clearErr('region') }}
                  options={Object.keys(REGIONS)}
                  error={errors.region}
                />
                <FloatingSelect
                  label="Tuman / Shahar"
                  value={form.district}
                  onChange={v => { set('district', v); clearErr('district') }}
                  options={districts}
                  disabled={!form.region}
                  error={errors.district}
                />
              </div>

              <button
                onClick={() => { if (validateStep1()) setStep(2) }}
                className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm transition-all shadow-md shadow-indigo-200 flex items-center justify-center gap-2 mt-2"
              >
                Keyingi qadam
                <Icon d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </button>

              <p className="text-center text-sm text-slate-500">
                Allaqachon hisobingiz bormi?{' '}
                <Link to="/login" className="text-indigo-600 font-semibold hover:underline">{t('land.nav.login')}</Link>
              </p>
            </div>
          )}

          {/* ── STEP 2 ── */}
          {step === 2 && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <InputField label="Ism Familya" error={errors.name}>
                  <TInput
                    value={form.name}
                    onChange={e => { set('name', e.target.value); clearErr('name') }}
                    placeholder="Alisher Rahimov"
                    icon={<Icon d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />}
                    err={errors.name}
                  />
                </InputField>

                <InputField label="Telefon raqami" error={errors.phone}>
                  <TInput
                    value={form.phone}
                    onChange={e => { set('phone', e.target.value); clearErr('phone') }}
                    placeholder="+998 90 000 00 00"
                    icon={<Icon d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />}
                    err={errors.phone}
                  />
                </InputField>
              </div>

              {/* Agent kodi */}
              <InputField
                label="Agent kodi"
                icon={<Icon d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />}
                error={errors.agent_code}
                hint="Ixtiyoriy — agent orqali kelgan bo'lsangiz kiriting"
              >
                <TInput
                  type="password"
                  value={form.agent_code}
                  onChange={e => {
                    const v = e.target.value.toUpperCase()
                    set('agent_code', v); clearErr('agent_code')
                    if (v.length >= 3) checkAgentCode(v)
                    else { setAgentStatus(null); setAgentName('') }
                  }}
                  placeholder="••••••"
                  className="font-mono tracking-widest"
                  icon={<Icon d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />}
                  err={errors.agent_code || agentStatus === 'invalid'}
                  right={
                    agentStatus === 'checking' ? (
                      <svg className="animate-spin w-4 h-4 text-slate-400" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                    ) : agentStatus === 'valid' ? (
                      <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center">
                        <Icon d="M5 13l4 4L19 7" cls="w-3 h-3 text-emerald-600" />
                      </div>
                    ) : agentStatus === 'invalid' ? (
                      <div className="w-5 h-5 rounded-full bg-red-100 flex items-center justify-center">
                        <Icon d="M6 18L18 6M6 6l12 12" cls="w-3 h-3 text-red-500" />
                      </div>
                    ) : null
                  }
                />
                {agentStatus === 'valid' && (
                  <p className="text-xs text-emerald-600 mt-1 font-medium">✓ {agentName}</p>
                )}
              </InputField>

              <div className="grid grid-cols-2 gap-4">
                <InputField label="Parol" error={errors.password}>
                  <TInput
                    type={showPass ? 'text' : 'password'}
                    value={form.password}
                    onChange={e => { set('password', e.target.value); clearErr('password') }}
                    placeholder="Kamida 6 belgi"
                    icon={<Icon d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />}
                    right={<button type="button" onClick={() => setShowPass(!showPass)} className="text-slate-400 hover:text-slate-600">{showPass ? <EyeOff /> : <EyeOpen />}</button>}
                    err={errors.password}
                  />
                </InputField>

                <InputField label="Qayta kiriting" error={errors.confirm_password}>
                  <TInput
                    type={showConfirm ? 'text' : 'password'}
                    value={form.confirm_password}
                    onChange={e => { set('confirm_password', e.target.value); clearErr('confirm_password') }}
                    placeholder="Takrorlang"
                    icon={<Icon d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />}
                    right={<button type="button" onClick={() => setShowConfirm(!showConfirm)} className="text-slate-400 hover:text-slate-600">{showConfirm ? <EyeOff /> : <EyeOpen />}</button>}
                    err={errors.confirm_password}
                  />
                </InputField>
              </div>

              {errors.submit && (
                <div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                  <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0" />
                  {errors.submit}
                </div>
              )}

              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="px-5 py-3 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-sm transition-all flex items-center gap-2"
                >
                  <Icon d="M11 17l-5-5m0 0l5-5m-5 5h12" />
                  Ortga
                </button>
                <button
                  type="button"
                  onClick={goToOtp}
                  disabled={otpLoading || loading}
                  className="flex-1 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold text-sm transition-all shadow-md shadow-indigo-200 flex items-center justify-center gap-2"
                >
                  {otpLoading ? (
                    <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Yuklanmoqda...</>
                  ) : (<>Keyingi qadam <Icon d="M13 7l5 5m0 0l-5 5m5-5H6" /></>)}
                </button>
              </div>

              <p className="text-center text-sm text-slate-500">
                Allaqachon hisobingiz bormi?{' '}
                <Link to="/login" className="text-indigo-600 font-semibold hover:underline">{t('land.nav.login')}</Link>
              </p>
            </form>
          )}

          {/* ── STEP 3: OTP Tasdiqlash ── */}
          {step === 3 && (
            <div className="space-y-5">
              <div className="text-center">
                <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center mx-auto mb-3">
                  <svg viewBox="0 0 24 24" className="w-8 h-8 text-indigo-600" fill="currentColor">
                    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/>
                  </svg>
                </div>
                <h3 className="text-base font-bold text-slate-800">Telegram tasdiqlash</h3>
                <p className="text-sm text-slate-500 mt-1">
                  <span className="font-semibold text-slate-700">{form.phone}</span> raqamiga bog'liq Telegram botga 6 xonali kod yuborildi
                </p>
              </div>

              {devMode && (
                <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-3 py-2.5 text-xs font-medium">
                  <span>🛠</span>
                  <span>Developer mode: OTP backend konsolga (terminalga) chiqarildi</span>
                </div>
              )}

              <div>
                <p className="text-xs text-center text-slate-500 mb-2">6 xonali kodni kiriting</p>
                <OtpInput value={otp} onChange={setOtp} />
              </div>

              {otpError && (
                <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-600 rounded-xl px-3 py-2.5 text-sm">
                  <Icon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" cls="w-4 h-4 shrink-0" />
                  {otpError}
                </div>
              )}

              <button
                onClick={verifyOtp}
                disabled={otpLoading || loading || otp.length < 6}
                className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold text-sm transition-all shadow-md shadow-indigo-200 flex items-center justify-center gap-2"
              >
                {(otpLoading || loading) ? (
                  <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Tekshirilmoqda...</>
                ) : (
                  <>Tasdiqlash va ro'yxatdan o'tish <Icon d="M5 13l4 4L19 7" /></>
                )}
              </button>

              <div className="text-center">
                <button onClick={resendOtp} disabled={resendTimer > 0 || otpLoading}
                  className="text-sm text-indigo-600 hover:text-indigo-700 disabled:text-slate-400 font-medium transition-colors">
                  {resendTimer > 0 ? `Qayta yuborish (${resendTimer}s)` : 'Kodni qayta yuborish'}
                </button>
              </div>

              <button
                onClick={() => { setStep(2); setOtp(''); setOtpError('') }}
                className="w-full py-2 text-slate-500 hover:text-slate-700 text-sm font-medium transition-colors flex items-center justify-center gap-1"
              >
                <Icon d="M11 17l-5-5m0 0l5-5m-5 5h12" cls="w-3.5 h-3.5" /> Ortga
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
