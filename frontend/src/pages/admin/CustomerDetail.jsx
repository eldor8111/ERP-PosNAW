import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../../api/axios'

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')
const fmtDate = (d) => d ? new Date(d).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

const TIER_STYLES = {
  Gold:     'bg-amber-100 text-amber-700',
  Silver:   'bg-slate-200 text-slate-700',
  Bronze:   'bg-orange-100 text-orange-700',
  Standard: 'bg-slate-100 text-slate-500',
}

const STATUS_STYLES = {
  completed:     'bg-emerald-100 text-emerald-700',
  refunded:      'bg-red-100 text-red-700',
  partial_refund:'bg-amber-100 text-amber-700',
  cancelled:     'bg-slate-100 text-slate-500',
}
const STATUS_LABELS = {
  completed: 'Bajarildi', refunded: 'Qaytarildi',
  partial_refund: 'Qisman qaytarildi', cancelled: 'Bekor qilindi',
}

const PAY_LABELS = { cash: 'Naqd', card: 'Karta', debt: 'Qarz', mixed: 'Aralash' }
const PAY_STYLES = {
  cash: 'bg-emerald-100 text-emerald-700',
  card: 'bg-blue-100 text-blue-700',
  debt: 'bg-red-100 text-red-700',
  mixed: 'bg-violet-100 text-violet-700',
}

const TABS = [
  { id: 'umumiy',      label: 'Umumiy' },
  { id: 'sotuvlar',    label: 'Sotuvlar' },
  { id: 'qaytarishlar',label: 'Qaytarishlar' },
  { id: 'operatsiyalar',label: 'Operatsiyalar' },
  { id: 'akt',         label: 'Akt Sverka' },
]

function StatCard({ icon, label, value, sub, color = 'indigo' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-500',
    amber: 'bg-amber-50 text-amber-600',
    violet: 'bg-violet-50 text-violet-600',
  }
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${colors[color]}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</div>
        <div className="text-xl font-bold text-slate-800 mt-0.5 truncate">{value}</div>
        {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}

export default function CustomerDetail() {
  const { customerId } = useParams()
  const navigate = useNavigate()

  const [tab, setTab] = useState('umumiy')
  const [stats, setStats] = useState(null)
  const [sales, setSales] = useState([])
  const [returns, setReturns] = useState([])
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingTab, setLoadingTab] = useState(false)

  useEffect(() => {
    api.get(`/customers/${customerId}/stats`)
      .then(r => setStats(r.data))
      .catch(() => navigate('/admin/customers'))
      .finally(() => setLoading(false))
  }, [customerId, navigate])

  const loadSales = useCallback(async () => {
    setLoadingTab(true)
    try {
      const { data } = await api.get(`/sales/?customer_id=${customerId}&limit=200`)
      setSales(data.filter(s => s.status !== 'refunded' && s.status !== 'cancelled'))
      setReturns(data.filter(s => s.status === 'refunded' || s.status === 'partial_refund'))
    } finally {
      setLoadingTab(false)
    }
  }, [customerId])

  const loadHistory = useCallback(async () => {
    setLoadingTab(true)
    try {
      const { data } = await api.get(`/customers/${customerId}/history`)
      setHistory(data)
    } finally {
      setLoadingTab(false)
    }
  }, [customerId])

  useEffect(() => {
    if (tab === 'sotuvlar' || tab === 'qaytarishlar' || tab === 'akt') loadSales()
    if (tab === 'operatsiyalar') loadHistory()
  }, [tab, loadSales, loadHistory])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!stats) return null

  const customerName = stats.name
  const initial = customerName?.charAt(0)?.toUpperCase()
  const avatarColors = ['bg-indigo-100 text-indigo-600', 'bg-emerald-100 text-emerald-600', 'bg-violet-100 text-violet-600', 'bg-rose-100 text-rose-600', 'bg-amber-100 text-amber-600']
  const avatarColor = avatarColors[(customerName?.charCodeAt(0) || 0) % avatarColors.length]

  return (
    <div className="space-y-6">
      {/* Back button + Header */}
      <div className="flex items-start gap-4">
        <button
          onClick={() => navigate('/admin/customers')}
          className="mt-1 p-2 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex items-center gap-4 flex-1">
          <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold shrink-0 ${avatarColor}`}>
            {initial}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-800">{stats.name}</h1>
              <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${TIER_STYLES[stats.tier]}`}>
                {stats.tier}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1 text-sm text-slate-500">
              {stats.phone && (
                <span className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  {stats.phone}
                </span>
              )}
              <span className="flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                </svg>
                {fmt(stats.loyalty_points)} ball
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex border-b border-slate-100 overflow-x-auto">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-5 py-3.5 text-sm font-semibold whitespace-nowrap transition-colors border-b-2 -mb-px
                ${tab === t.id
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* UMUMIY TAB */}
          {tab === 'umumiy' && (
            <div className="space-y-6">
              {/* Virtual Card */}
              {stats.card_number && (
                <div className="bg-linear-to-tr from-indigo-900 via-indigo-800 to-indigo-600 rounded-3xl p-6 md:p-8 text-white shadow-xl shadow-indigo-900/20 relative overflow-hidden flex flex-col justify-between min-h-[220px] max-w-md border border-indigo-500/30">
                  {/* Background decoration */}
                  <div className="absolute -right-10 -top-10 w-40 h-40 bg-white/10 rounded-full blur-2xl"></div>
                  <div className="absolute -left-10 -bottom-10 w-32 h-32 bg-indigo-400/20 rounded-full blur-xl"></div>
                  
                  <div className="relative z-10 flex justify-between items-start">
                    <div>
                      <div className="text-indigo-200 text-xs uppercase tracking-widest font-semibold mb-1">Mijoz Kartasi</div>
                      <div className="text-xl font-bold drop-shadow-sm">{stats.name}</div>
                    </div>
                    <div className="bg-white/20 backdrop-blur-md border border-white/10 px-3 py-1.5 rounded-full text-sm font-semibold flex items-center gap-1.5 shadow-sm">
                      <svg className="w-4 h-4 text-amber-300" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      {stats.cashback_percent > 0 ? `${stats.cashback_percent}% Keshbek` : 'Standard Card'}
                    </div>
                  </div>
                  
                  <div className="relative z-10 mt-8 space-y-5">
                    <div className="text-2xl sm:text-3xl font-mono tracking-[0.2em] text-white/90 drop-shadow-md">
                      {stats.card_number.replace(/(.{4})/g, '$1 ').trim()}
                    </div>
                    <div className="flex items-center justify-between border-t border-white/10 pt-4">
                      <div>
                        <div className="text-indigo-200 text-[10px] uppercase font-bold tracking-wider mb-0.5">Bonus Balans</div>
                        <div className="font-bold text-lg text-emerald-300">{fmt(stats.bonus_balance)} <span className="text-xs font-medium opacity-80">so'm</span></div>
                      </div>
                      <div className="text-right">
                        <div className="text-indigo-200 text-[10px] uppercase font-bold tracking-wider mb-0.5">Jami Xaridlar</div>
                        <div className="font-bold text-base text-white">{fmt(stats.total_spent)} <span className="text-xs font-medium opacity-80">so'm</span></div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                  color="indigo"
                  label="Jami Sotuvlar"
                  value={`${fmt(stats.total_sales_count)} ta`}
                  sub={`${fmt(stats.total_sales_amount)} so'm`}
                  icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>}
                />
                <StatCard
                  color="emerald"
                  label="To'langan"
                  value={`${fmt(stats.total_paid_amount)} so'm`}
                  sub={`${fmt(stats.total_sales_count)} sotuvdan`}
                  icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                />
                <StatCard
                  color="red"
                  label="Qarzdorlik"
                  value={`${fmt(stats.debt_balance)} so'm`}
                  sub={stats.debt_limit > 0 ? `Limit: ${fmt(stats.debt_limit)} so'm` : 'Limit belgilanmagan'}
                  icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                />
                <StatCard
                  color="amber"
                  label="Qaytarishlar"
                  value={`${fmt(stats.total_returns_count)} ta`}
                  sub={`${fmt(stats.total_returns_amount)} so'm`}
                  icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>}
                />
              </div>

              {/* Loyalty progress */}
              <div className="bg-slate-50 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-semibold text-slate-600">Loyallik Dasturi</span>
                  <span className={`px-3 py-1 rounded-full text-xs font-semibold ${TIER_STYLES[stats.tier]}`}>{stats.tier}</span>
                </div>
                <div className="flex items-center gap-3">
                  {['Standard', 'Bronze', 'Silver', 'Gold'].map((tier, i) => (
                    <div key={tier} className="flex-1 text-center">
                      <div className={`h-2 rounded-full mb-1.5 ${['Standard', 'Bronze', 'Silver', 'Gold'].indexOf(stats.tier) >= i ? 'bg-indigo-500' : 'bg-slate-200'}`} />
                      <span className="text-xs text-slate-400">{tier}</span>
                    </div>
                  ))}
                </div>
                <div className="text-xs text-slate-400 mt-2">
                  {stats.tier === 'Standard' && `Bronze uchun ${fmt(1000 - stats.loyalty_points)} ball kerak`}
                  {stats.tier === 'Bronze' && `Silver uchun ${fmt(5000 - stats.loyalty_points)} ball kerak`}
                  {stats.tier === 'Silver' && `Gold uchun ${fmt(10000 - stats.loyalty_points)} ball kerak`}
                  {stats.tier === 'Gold' && 'Maksimal daraja — Gold!'}
                </div>
              </div>
            </div>
          )}

          {/* SOTUVLAR TAB */}
          {tab === 'sotuvlar' && (
            <SalesTable rows={sales} loading={loadingTab} />
          )}

          {/* QAYTARISHLAR TAB */}
          {tab === 'qaytarishlar' && (
            <SalesTable rows={returns} loading={loadingTab} emptyText="Bu mijozdan qaytarishlar yo'q" />
          )}

          {/* OPERATSIYALAR TAB */}
          {tab === 'operatsiyalar' && (
            <OperationsTable rows={history} loading={loadingTab} />
          )}

          {/* AKT SVERKA TAB */}
          {tab === 'akt' && (
            <AktSverka stats={stats} sales={sales} returns={returns} loading={loadingTab} />
          )}
        </div>
      </div>
    </div>
  )
}

function SalesTable({ rows, loading, emptyText = "Sotuvlar yo'q" }) {
  if (loading) return <LoadingSpinner />
  if (!rows.length) return <Empty text={emptyText} />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100">
            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Raqam</th>
            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Holat</th>
            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">To'lov turi</th>
            <th className="text-right text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">Jami</th>
            <th className="text-right text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pr-4">To'langan</th>
            <th className="text-right text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3">Qarz</th>
            <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-3 pl-4">Sana</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {rows.map(s => {
            const debt = Number(s.total_amount) - Number(s.paid_amount)
            return (
              <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                <td className="py-3 pr-4 font-mono text-xs text-slate-600">{s.number}</td>
                <td className="py-3 pr-4">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[s.status] || ''}`}>
                    {STATUS_LABELS[s.status] || s.status}
                  </span>
                </td>
                <td className="py-3 pr-4">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PAY_STYLES[s.payment_type] || ''}`}>
                    {PAY_LABELS[s.payment_type] || s.payment_type}
                  </span>
                </td>
                <td className="py-3 pr-4 text-right font-semibold text-slate-800">{fmt(s.total_amount)}</td>
                <td className="py-3 pr-4 text-right text-emerald-600 font-medium">{fmt(s.paid_amount)}</td>
                <td className={`py-3 pr-4 text-right font-medium ${debt > 0 ? 'text-red-500' : 'text-slate-400'}`}>
                  {debt > 0 ? fmt(debt) : '—'}
                </td>
                <td className="py-3 pl-4 text-slate-500 whitespace-nowrap">{fmtDate(s.created_at)}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-200">
            <td colSpan={3} className="pt-3 text-xs font-semibold text-slate-400 uppercase">Jami</td>
            <td className="pt-3 text-right font-bold text-slate-800">
              {fmt(rows.reduce((s, r) => s + Number(r.total_amount), 0))}
            </td>
            <td className="pt-3 text-right font-bold text-emerald-600">
              {fmt(rows.reduce((s, r) => s + Number(r.paid_amount), 0))}
            </td>
            <td className="pt-3 text-right font-bold text-red-500">
              {fmt(rows.reduce((s, r) => s + Math.max(0, Number(r.total_amount) - Number(r.paid_amount)), 0))}
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function OperationsTable({ rows, loading }) {
  if (loading) return <LoadingSpinner />
  if (!rows.length) return <Empty text="Operatsiyalar yo'q" />
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 hover:bg-slate-50 transition-colors">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${r.type === 'sale' ? 'bg-indigo-100 text-indigo-600' : 'bg-emerald-100 text-emerald-600'}`}>
            {r.type === 'sale' ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-slate-700">
              {r.type === 'sale' ? 'Sotuv' : "To'lov qabul qilindi"}
            </div>
            <div className="text-xs text-slate-400">{fmtDate(r.date)}</div>
          </div>
          <div className="text-right">
            <div className={`text-sm font-bold ${r.type === 'sale' ? 'text-indigo-600' : 'text-emerald-600'}`}>
              {r.type === 'sale' ? '-' : '+'}{fmt(r.amount)} so'm
            </div>
            {r.type === 'sale' && r.debt > 0 && (
              <div className="text-xs text-red-500">Qarz: {fmt(r.debt)} so'm</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function AktSverka({ stats, sales, returns, loading }) {
  if (loading) return <LoadingSpinner />

  const totalSales = sales.reduce((s, r) => s + Number(r.total_amount), 0)
  const totalPaid = sales.reduce((s, r) => s + Number(r.paid_amount), 0)
  const totalReturns = returns.reduce((s, r) => s + Number(r.total_amount), 0)
  const balance = stats.debt_balance

  const rows = [
    { label: 'Jami sotuvlar summasi', debit: totalSales, credit: 0, color: 'text-slate-800' },
    { label: "To'langan summasi (naqd + karta)", debit: 0, credit: totalPaid, color: 'text-emerald-600' },
    { label: 'Qaytarishlar summasi', debit: 0, credit: totalReturns, color: 'text-amber-600' },
  ]

  return (
    <div className="space-y-6">
      <div className="bg-slate-50 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-600 mb-4">Akt Sverka — {stats.name}</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider pb-2">Operatsiya</th>
              <th className="text-right text-xs font-semibold text-slate-400 uppercase tracking-wider pb-2 pr-4">Debet (so'm)</th>
              <th className="text-right text-xs font-semibold text-slate-400 uppercase tracking-wider pb-2">Kredit (so'm)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="py-2.5 text-slate-700">{r.label}</td>
                <td className="py-2.5 text-right pr-4 font-medium text-slate-800">
                  {r.debit > 0 ? fmt(r.debit) : '—'}
                </td>
                <td className="py-2.5 text-right font-medium">
                  {r.credit > 0 ? <span className="text-emerald-600">{fmt(r.credit)}</span> : '—'}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-slate-300">
              <td className="pt-3 font-bold text-slate-700">Yakuniy Qoldiq (Qarzdorlik)</td>
              <td />
              <td className={`pt-3 text-right font-bold text-lg ${balance > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                {fmt(balance)} so'm
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="bg-indigo-50 rounded-xl p-4">
          <div className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">Jami Sotuv</div>
          <div className="text-lg font-bold text-indigo-700">{fmt(totalSales)} so'm</div>
        </div>
        <div className="bg-emerald-50 rounded-xl p-4">
          <div className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1">To'langan</div>
          <div className="text-lg font-bold text-emerald-700">{fmt(totalPaid)} so'm</div>
        </div>
        <div className={`rounded-xl p-4 ${balance > 0 ? 'bg-red-50' : 'bg-slate-50'}`}>
          <div className={`text-xs font-semibold uppercase tracking-wider mb-1 ${balance > 0 ? 'text-red-400' : 'text-slate-400'}`}>Qoldiq Qarz</div>
          <div className={`text-lg font-bold ${balance > 0 ? 'text-red-700' : 'text-slate-500'}`}>{fmt(balance)} so'm</div>
        </div>
      </div>
    </div>
  )
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

function Empty({ text }) {
  return (
    <div className="flex flex-col items-center justify-center h-32 text-slate-400">
      <svg className="w-10 h-10 mb-2 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p className="text-sm">{text}</p>
    </div>
  )
}
