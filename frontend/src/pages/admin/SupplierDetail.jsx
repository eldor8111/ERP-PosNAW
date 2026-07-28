import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../../api/axios'
import { ChevronLeft, ListOrdered, Edit, Trash2 } from 'lucide-react'
import { useLang } from '../../context/LangContext'

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')
const fmtDate = (d) => d ? new Date(d).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

const TABS = [
  { id: 'umumiy', label: 'Umumiy' },
  { id: 'xaridlar', label: 'Xaridlar' },
  { id: 'tolovlar', label: "To'lovlar" },
  { id: 'operatsiyalar', label: 'Operatsiyalar' },
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
    <div className="group relative bg-gradient-to-br from-slate-50/90 via-white to-slate-100/60 rounded-2xl border border-slate-200/60 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] p-2 sm:p-5 flex items-center gap-4 overflow-hidden transition-all duration-300">
      <div className={`w-13 h-13 rounded-xl flex items-center justify-center shrink-0 shadow-sm border border-black/5 ${colors[color]}`}>
        {icon}
      </div>
      <div className="min-w-0 z-10">
        <div className="text-[10px] sm:text-[11px] font-bold text-slate-400 uppercase tracking-widest">{label}</div>
        <div className="text-lg sm:text-2xl font-extrabold text-slate-800 sm:mt-0.5 tracking-tight truncate">{value}</div>
        {sub && <div className="text-[11px] sm:text-xs text-slate-500 font-medium sm:mt-1">{sub}</div>}
      </div>
    </div>
  )
}

export default function SupplierDetail() {
  const { supplierId } = useParams()
  const navigate = useNavigate()
  const { t } = useLang()

  const [tab, setTab] = useState('umumiy')
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  const [purchases, setPurchases] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingTab, setLoadingTab] = useState(false)

  useEffect(() => {
    api.get(`/suppliers/${supplierId}/stats`, { _suppressToast: true })
      .then(r => setStats(r.data))
      .catch(() => navigate('/admin/purchases'))
      .finally(() => setLoading(false))
  }, [supplierId, navigate])

  const loadHistory = useCallback(async () => {
    setLoadingTab(true)
    try {
      const { data } = await api.get(`/suppliers/${supplierId}/history`, { _suppressToast: true })
      setHistory(data)
      setPurchases(data.filter(i => i.op_type === 'purchase'))
    } finally {
      setLoadingTab(false)
    }
  }, [supplierId])

  useEffect(() => {
    if (tab !== 'umumiy') loadHistory()
  }, [tab, loadHistory])

  const handleDeletePay = async (id) => {
    if (!window.confirm("Rostdan ham o'chirasizmi?")) return
    try {
      await api.delete(`/finance/transactions/${id}`)
      loadHistory()
      // yangi statlarni olish
      const r = await api.get(`/suppliers/${supplierId}/stats`)
      setStats(r.data)
    } catch (err) {
      console.error(err)
    }
  }

  if (loading) {
    return <div className="flex h-[80vh] items-center justify-center"><div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div></div>
  }
  if (!stats) return null

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      <div className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200/60 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 sm:gap-4">
            <button onClick={() => navigate('/admin/purchases')}
              className="p-2 sm:px-3 sm:py-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-all flex items-center gap-2">
              <ChevronLeft className="w-5 h-5" />
              <span className="hidden sm:inline font-medium">Orqaga</span>
            </button>
            <div className="w-px h-6 bg-slate-200 hidden sm:block" />
            <div>
              <h1 className="text-lg sm:text-xl font-bold text-slate-800 leading-tight truncate max-w-[200px] sm:max-w-[400px]">
                {stats.name}
              </h1>
              <div className="text-[11px] sm:text-xs text-slate-500 font-medium">
                {stats.phone || 'Telefon yo\'q'}
              </div>
            </div>
          </div>
        </div>

        {/* TABS */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex gap-2 sm:gap-6 overflow-x-auto hide-scrollbar">
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`py-3 px-2 text-sm font-semibold whitespace-nowrap border-b-2 transition-all ${tab === t.id ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {tab === 'umumiy' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 sm:gap-5">
              <StatCard
                color={stats.debt_balance > 0 ? 'red' : 'emerald'}
                icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                label="Joriy Qarz"
                value={fmt(stats.debt_balance)}
              />
              <StatCard color="indigo"
                icon={<ListOrdered className="w-6 h-6" />}
                label="Jami Xaridlar soni"
                value={fmt(stats.total_purchases_count)}
              />
              <StatCard color="violet"
                icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>}
                label="Jami Xarid summasi"
                value={fmt(stats.total_purchases_amount)}
              />
              <StatCard color="amber"
                icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2z" /></svg>}
                label="Jami To'langan"
                value={fmt(stats.total_paid_amount)}
              />
            </div>
          </div>
        )}

        {tab === 'operatsiyalar' && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">Sana</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">Amaliyot turi</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">Tafsilot</th>
                    <th className="px-4 py-3 text-right font-semibold text-slate-500 text-xs">Kirim / Chiqim</th>
                    <th className="px-4 py-3 text-right font-semibold text-slate-500 text-xs">Amallar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loadingTab ? <tr><td colSpan={5} className="text-center py-10">Yuklanmoqda...</td></tr> : history.map(h => (
                    <tr key={`${h.op_type}-${h.id || h.date}`} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{fmtDate(h.date)}</td>
                      <td className="px-4 py-3">
                        {h.op_type === 'purchase' ? <span className="bg-indigo-100 text-indigo-700 px-2 py-1 rounded text-xs">Xarid</span> : 
                         h.op_type === 'payment' ? <span className="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs">To'lov</span> : 
                         <span className="bg-slate-100 text-slate-700 px-2 py-1 rounded text-xs">{h.op_type}</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-xs">{h.description}</td>
                      <td className="px-4 py-3 text-right font-semibold">
                        {h.op_type === 'purchase' ? (
                          <span className="text-red-500">-{fmt(h.amount)} {h.currency}</span>
                        ) : (
                          <span className="text-emerald-500">+{fmt(h.amount)} {h.currency}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {h.op_type === 'payment' && (
                          <button onClick={() => handleDeletePay(h.id)} className="text-red-400 hover:text-red-600 bg-red-50 p-1.5 rounded-lg transition-colors" title="O'chirish">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!loadingTab && history.length === 0 && <tr><td colSpan={5} className="text-center py-10 text-slate-400">Hech qanday ma'lumot yo'q</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {(tab === 'xaridlar' || tab === 'tolovlar') && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">Sana</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">Summa</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">Izoh</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loadingTab ? <tr><td colSpan={3} className="text-center py-10">Yuklanmoqda...</td></tr> : history.filter(i => i.op_type === (tab === 'xaridlar' ? 'purchase' : 'payment')).map(h => (
                    <tr key={`${h.op_type}-${h.id}`} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{fmtDate(h.date)}</td>
                      <td className="px-4 py-3 font-semibold text-slate-800">{fmt(h.amount)} {h.currency}</td>
                      <td className="px-4 py-3 text-slate-600 text-xs">{h.description}</td>
                    </tr>
                  ))}
                  {!loadingTab && history.filter(i => i.op_type === (tab === 'xaridlar' ? 'purchase' : 'payment')).length === 0 && <tr><td colSpan={3} className="text-center py-10 text-slate-400">Hech qanday ma'lumot yo'q</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
