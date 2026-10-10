import { useState } from 'react'
import { useLang } from '../context/LangContext'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import { UserPlus, ArrowLeft, CheckCircle2, AlertCircle, Phone, Lock, User, Briefcase } from 'lucide-react'

const roles = [
  { value: 'admin', label: 'Admin' },
  { value: 'director', label: 'Direktor' },
  { value: 'manager', label: 'Menejer' },
  { value: 'cashier', label: 'Kassir' },
  { value: 'warehouse', label: 'Ombor xodimi' },
  { value: 'accountant', label: 'Buxgalter' },
  { value: 'courier', label: 'Kuryer (mobil ilova)' },
  { value: 'agent', label: 'Savdo agenti (mobil ilova)' },
]

export default function Register() {
  const { t } = useLang()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    phone: '',
    password: '',
    name: '',
    role: 'cashier',
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      const { data } = await api.post('/users/', form)
      setSuccess(`${t('user.newUser')}: "${data.name}" — ${t('common.success').toLowerCase()}!`)
      setForm({ phone: '', password: '', name: '', role: 'cashier' })
    } catch (err) {
      const detail = err.response?.data?.detail
      if (Array.isArray(detail)) {
        setError(detail.map(d => d.msg).join(', '))
      } else {
        setError(detail || t('auth.errGeneral') || 'Xatolik yuz berdi')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] relative flex items-center justify-center p-4 overflow-hidden">
      {/* Background Glows */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `radial-gradient(#2563EB 1px, transparent 1px)`,
            backgroundSize: '24px 24px'
          }}
        />
        <div className="absolute -top-32 -right-32 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      </div>

      <div className="bg-white/95 backdrop-blur-2xl border border-blue-100 rounded-3xl shadow-[0_20px_50px_rgba(37,99,235,0.08)] w-full max-w-md p-8 relative z-10">

        {/* Back button */}
        <button
          onClick={() => navigate('/admin/users')}
          className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-blue-600 mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('user.title')}</span>
        </button>

        {/* Header */}
        <div className="text-center mb-6">
          <div className="w-14 h-14 bg-blue-50 border border-blue-100 text-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-xs">
            <UserPlus className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-black text-slate-900">{t('user.newUser')}</h1>
          <p className="text-slate-500 text-xs mt-1">{t('auth.addNewEmp')}</p>
        </div>

        {/* Success */}
        {success && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-2xl p-3.5 mb-4 text-xs font-semibold flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
            <span>{success}</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl p-3.5 mb-4 text-xs font-semibold flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Full Name */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              {t('customer.fullName') || "To'liq ism"}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                <User className="w-4 h-4" />
              </div>
              <input
                type="text"
                name="name"
                placeholder="Abdullayev Sardor"
                value={form.name}
                onChange={handleChange}
                required
                className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs"
              />
            </div>
          </div>

          {/* Phone */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              {t('common.phone') || "Telefon raqam"}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                <Phone className="w-4 h-4" />
              </div>
              <input
                type="text"
                name="phone"
                placeholder="998901234567"
                value={form.phone}
                onChange={handleChange}
                required
                className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs"
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              {t('login.password') || "Parol"}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                <Lock className="w-4 h-4" />
              </div>
              <input
                type="password"
                name="password"
                placeholder={t('auth.passwordPl') || "Kamida 6 ta belgi"}
                value={form.password}
                onChange={handleChange}
                required
                minLength={6}
                className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-2xl bg-white text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs"
              />
            </div>
          </div>

          {/* Role */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              {t('user.role') || "Lavozim"}
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none text-slate-400">
                <Briefcase className="w-4 h-4" />
              </div>
              <select
                name="role"
                value={form.role}
                onChange={handleChange}
                className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-2xl bg-white text-xs font-semibold text-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all shadow-xs cursor-pointer"
              >
                {roles.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white font-bold text-xs shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2 mt-2"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                {t('common.saving') || "Saqlanmoqda..."}
              </span>
            ) : t('common.save') || 'Saqlash'}
          </button>
        </form>
      </div>
    </div>
  )
}
