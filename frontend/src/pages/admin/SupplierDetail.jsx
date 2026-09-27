import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../../api/axios'
import { ChevronLeft, ListOrdered, Edit, Trash2 } from 'lucide-react'
import { useLang } from '../../context/LangContext'
import toast from 'react-hot-toast'

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')
const fmtDate = (d) => d ? new Date(d).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

const PO_STATUS = {
  draft: { key: 'purchase.statusDraft', c: 'bg-slate-100 text-slate-600' },
  sent: { key: 'purchase.statusOrdered', c: 'bg-blue-100 text-blue-700' },
  partial: { key: 'purchase.statusPartial', c: 'bg-amber-100 text-amber-700' },
  received: { key: 'purchase.statusReceived', c: 'bg-emerald-100 text-emerald-700' },
  cancelled: { key: 'purchase.statusCancelled', c: 'bg-red-100 text-red-500' },
}

const TABS = [
  { id: 'umumiy', key: 'supplier.tabGeneral' },
  { id: 'xaridlar', key: 'supplier.tabPurchases' },
  { id: 'tolovlar', key: 'supplier.tabPayments' },
  { id: 'operatsiyalar', key: 'supplier.tabOperations' },
]

function StatCard({ icon, label, value, sub, color = 'indigo' }) {
  const colors = {
    indigo: 'bg-blue-50 text-blue-600',
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
    api.get(`/suppliers/${supplierId}/stats`, { _suppressToast: true, _noCache: true })
      .then(r => setStats(r.data))
      .catch(() => navigate('/admin/purchases'))
      .finally(() => setLoading(false))
  }, [supplierId, navigate])

  const loadHistory = useCallback(async () => {
    setLoadingTab(true)
    try {
      const { data } = await api.get(`/suppliers/${supplierId}/history`, { _suppressToast: true, _noCache: true })
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
    if (!window.confirm(t('supplier.confirmDeletePayment'))) return
    try {
      await api.delete(`/finance/transactions/${id}`)
      toast.success(t('supplier.paymentDeleted'))
    } catch {
      // xabarni axios interceptor ko'rsatadi
    }
    // Qarz va tarix har holda serverdan qayta o'qiladi
    loadHistory()
    api.get(`/suppliers/${supplierId}/stats`, { _noCache: true }).then(r => setStats(r.data)).catch(() => { })
  }

  if (loading) {
    return <div className="flex h-[80vh] items-center justify-center"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div></div>
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
              <span className="hidden sm:inline font-medium">{t('common.back')}</span>
            </button>
            <div className="w-px h-6 bg-slate-200 hidden sm:block" />
            <div>
              <h1 className="text-lg sm:text-xl font-bold text-slate-800 leading-tight truncate max-w-[200px] sm:max-w-[400px]">
                {stats.name}
              </h1>
              <div className="text-[11px] sm:text-xs text-slate-500 font-medium">
                {stats.phone || t('supplier.noPhone')}
              </div>
            </div>
          </div>
        </div>

        {/* TABS */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex gap-2 sm:gap-6 overflow-x-auto hide-scrollbar">
            {TABS.map(tb => (
              <button key={tb.id} onClick={() => setTab(tb.id)}
                className={`py-3 px-2 text-sm font-semibold whitespace-nowrap border-b-2 transition-all ${tab === tb.id ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}>
                {t(tb.key)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {tab === 'umumiy' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 sm:gap-5">
              {/* Valyuta bo'yicha balans: musbat — bizning qarzimiz, manfiy — avans (oldindan to'langan) */}
              {(() => {
                const entries = Object.entries(stats.debt_balances || {}).filter(([, v]) => Math.abs(Number(v)) >= 0.01)
                const icon = <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                if (!entries.length) {
                  return <StatCard color="emerald" icon={icon} label={t('supplier.currentDebt')} value={`0 UZS`} />
                }
                return entries.map(([cur, amt]) => {
                  const v = Number(amt)
                  const isAvans = v < 0
                  return (
                    <StatCard
                      key={cur}
                      color={isAvans ? 'emerald' : 'red'}
                      icon={icon}
                      label={`${isAvans ? t('purchase.avans') : t('supplier.currentDebt')} (${cur})`}
                      value={`${fmt(Math.abs(v))} ${cur}`}
                      sub={cur !== 'UZS' ? `≈ ${fmt(Math.round(Math.abs(v) * (stats.rates?.[cur] || 1)))} UZS` : null}
                    />
                  )
                })
              })()}
              <StatCard color="indigo"
                icon={<ListOrdered className="w-6 h-6" />}
                label={t('supplier.totalPurchasesCount')}
                value={fmt(stats.total_purchases_count)}
              />
              <StatCard color="violet"
                icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>}
                label={t('supplier.totalPurchasesAmount')}
                value={fmt(stats.total_purchases_amount)}
              />
              <StatCard color="amber"
                icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2z" /></svg>}
                label={t('supplier.totalPaidAmount')}
                value={fmt(stats.total_paid_amount)}
              />
              {Number(stats.total_returns_amount) > 0 && (
                <StatCard color="violet"
                  icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>}
                  label={t('supplier.totalReturns')}
                  value={fmt(stats.total_returns_amount)}
                />
              )}
            </div>
          </div>
        )}

        {tab === 'operatsiyalar' && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('common.date')}</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('supplier.operationType')}</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('supplier.detail')}</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('supplier.employee')}</th>
                    <th className="px-4 py-3 text-right font-semibold text-slate-500 text-xs">{t('supplier.inOut')}</th>
                    <th className="px-4 py-3 text-right font-semibold text-slate-500 text-xs">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loadingTab ? <tr><td colSpan={6} className="text-center py-10">{t('common.loading')}</td></tr> : history.map(h => (
                    <tr key={`${h.op_type}-${h.id || h.date}`} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{fmtDate(h.date)}</td>
                      <td className="px-4 py-3">
                        {h.op_type === 'purchase' ? (
                          <div className="flex flex-wrap items-center gap-1">
                            <span className="bg-blue-100 text-blue-700 px-2 py-1 rounded text-xs">{t('supplier.purchase')}</span>
                            {h.status && PO_STATUS[h.status] && <span className={`px-2 py-1 rounded text-[10px] font-semibold ${PO_STATUS[h.status].c}`}>{t(PO_STATUS[h.status].key)}</span>}
                          </div>
                        ) :
                         h.op_type === 'payment' ? <span className="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs">{t('supplier.payment')}</span> :
                         h.op_type === 'return' ? <span className="bg-violet-100 text-violet-700 px-2 py-1 rounded text-xs">{t('supplier.return')}</span> :
                         h.op_type === 'refund' ? <span className="bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs">{t('supplier.refund')}</span> :
                         <span className="bg-slate-100 text-slate-700 px-2 py-1 rounded text-xs">{h.op_type}</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-xs">{h.description}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{h.cashier || '—'}</td>
                      <td className="px-4 py-3 text-right font-semibold">
                        {h.op_type === 'purchase' ? (
                          // Qarzga faqat qabul qilingan tovar qo'shiladi
                          Number(h.received) > 0
                            ? <span className="text-red-500">-{fmt(h.received)} {h.currency}</span>
                            : <span className="text-slate-400">{fmt(h.amount)} {h.currency}</span>
                        ) : h.op_type === 'refund' ? (
                          <span className="text-red-500">-{fmt(h.amount)} {h.currency}</span>
                        ) : (
                          <span className="text-emerald-500">+{fmt(h.amount)} {h.currency}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {h.deletable && (h.op_type === 'payment' || h.op_type === 'refund') && (
                          <button onClick={() => handleDeletePay(h.id)} className="text-red-400 hover:text-red-600 bg-red-50 p-1.5 rounded-lg transition-colors" title={t('common.delete')}>
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!loadingTab && history.length === 0 && <tr><td colSpan={6} className="text-center py-10 text-slate-400">{t('common.noData')}</td></tr>}
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
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('common.date')}</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('common.amount')}</th>
                    <th className="px-4 py-3 text-left font-semibold text-slate-500 text-xs">{t('common.note')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loadingTab ? <tr><td colSpan={3} className="text-center py-10">{t('common.loading')}</td></tr> : history.filter(i => tab === 'xaridlar' ? i.op_type === 'purchase' : (i.op_type === 'payment' || i.op_type === 'refund')).map(h => (
                    <tr key={`${h.op_type}-${h.id}`} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{fmtDate(h.date)}</td>
                      <td className="px-4 py-3 font-semibold text-slate-800">
                        <div>{h.op_type === 'refund' ? '−' : ''}{fmt(h.amount)} <span className="text-xs font-bold text-slate-500">{h.currency}</span>
                          {h.op_type === 'purchase' && h.status && PO_STATUS[h.status] && <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] font-semibold ${PO_STATUS[h.status].c}`}>{t(PO_STATUS[h.status].key)}</span>}
                        </div>
                        {h.currency !== 'UZS' && h.amount_uzs && (
                          <div className="text-[11px] text-slate-400 font-normal">≈ {fmt(h.amount_uzs)} {t('common.sum')}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-xs">{h.description}</td>
                    </tr>
                  ))}
                  {!loadingTab && history.filter(i => tab === 'xaridlar' ? i.op_type === 'purchase' : (i.op_type === 'payment' || i.op_type === 'refund')).length === 0 && <tr><td colSpan={3} className="text-center py-10 text-slate-400">{t('common.noData')}</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
