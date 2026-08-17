import { useLang } from '../../context/LangContext';
import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../../api/axios'
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, ListOrdered, ChevronsUpDown, CheckIcon, X, RotateCcw } from 'lucide-react';
import PartialReturnModal from './PartialReturnModal';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')
const fmtDate = (d) => d ? new Date(d).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

const TIER_STYLES = {
  Gold: 'bg-amber-100 text-amber-700',
  Silver: 'bg-slate-200 text-slate-700',
  Bronze: 'bg-orange-100 text-orange-700',
  Standard: 'bg-slate-100 text-slate-500',
}

const STATUS_STYLES = {
  completed: 'bg-emerald-100 text-emerald-700',
  refunded: 'bg-red-100 text-red-700',
  partial_refund: 'bg-amber-100 text-amber-700',
  cancelled: 'bg-slate-100 text-slate-500',
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
  { id: 'umumiy', label: 'Umumiy' },
  { id: 'sotuvlar', label: 'Sotuvlar' },
  { id: 'qaytarishlar', label: 'Qaytarishlar' },
  { id: 'operatsiyalar', label: 'Operatsiyalar' },
  { id: 'akt', label: 'Akt Sverka' },
  { id: 'kirim_tolovlar', label: "Kirim to'lovlar" },
]

function StatCard({ icon, label, value, sub, color = 'indigo' }) {
  const { t } = useLang();
  const colors = {
    indigo: 'bg-blue-50 text-blue-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    red: 'bg-red-50 text-red-500',
    amber: 'bg-amber-50 text-amber-600',
    violet: 'bg-violet-50 text-violet-600',
  }
  return (
    <div className="group relative bg-gradient-to-br from-slate-50/90 via-white to-slate-100/60 rounded-2xl border border-slate-200/60 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] p-2 sm:p-5 cursor-pointer flex items-center gap-4 overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_24px_-6px_rgba(0,0,0,0.08)] hover:border-slate-300/70">

      <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full bg-gradient-to-r from-transparent via-white/50 to-transparent -skew-x-12 transition-transform duration-1000 ease-out pointer-events-none z-10" />

      <div className="absolute -inset-px bg-gradient-to-br from-white/40 via-transparent to-slate-200/20 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

      {/* Ikonka Konteyneri */}
      <div className={`w-13 h-13 rounded-xl flex items-center justify-center shrink-0 shadow-sm border border-black/5 transition-all duration-300 group-hover:scale-105 group-hover:shadow ${colors[color]}`}>
        {icon}
      </div>

      {/* Matnlar qismi */}
      <div className="min-w-0 z-10">
        <div className="text-[10px] sm:text-[11px] font-bold text-slate-400 uppercase tracking-widest">
          {label}
        </div>
        <div className="text-lg sm:text-2xl font-extrabold text-slate-800 sm:mt-0.5 tracking-tight truncate">
          {value}
        </div>
        {sub && (
          <div className="text-[11px] sm:text-xs text-slate-500 font-medium sm:mt-1 flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}

export default function CustomerDetail() {
  const { t } = useLang();
  const { customerId } = useParams()
  const navigate = useNavigate()

  const [tab, setTab] = useState('umumiy')
  const [stats, setStats] = useState(null)
  const [sales, setSales] = useState([])
  const [returns, setReturns] = useState([])
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingTab, setLoadingTab] = useState(false)
  const [salesData, setSalesData] = useState([])
  const [currencies, setCurrencies] = useState([])
  const [income, setIncome] = useState([])

  const [debtSales, setDebtSales] = useState([]);
  const [returnModal, setReturnModal] = useState(false);
  const [warehouses, setWarehouses] = useState([]);
  const [wallets, setWallets] = useState([]);

  useEffect(() => {
    api.get(`/customers/${customerId}/stats`, { _suppressToast: true })
      .then(r => setStats(r.data))
      .catch(() => navigate('/admin/customers'))
      .finally(() => setLoading(false))

    api.get('/finance/payments/income', { _suppressToast: true })
      .then(r => setIncome(r.data.items))
      .catch(() => setIncome([]))
    api.get('/sales/', { params: { customer_id: customerId, limit: 200 }, _suppressToast: true })
      .then(r => setSalesData(r.data))
      .catch(() => setSalesData([]))
    api.get('/currencies', { _suppressToast: true }).then(r => setCurrencies(r.data)).catch(() => { })
    api.get('/inventory/warehouses', { _suppressToast: true }).then(r => setWarehouses(r.data)).catch(() => { })
    api.get('/finance/wallets', { _suppressToast: true }).then(r => setWallets(r.data)).catch(() => { })
  }, [customerId, navigate])

  const loadSales = useCallback(async () => {
    setLoadingTab(true)
    try {
      const { data } = await api.get(`/sales/`, { params: { customer_id: customerId, limit: 200 }, _suppressToast: true })
      setSales(data.filter(s => s.status !== 'refunded' && s.status !== 'cancelled'))
      setReturns(data.filter(s => s.status === 'refunded' || s.status === 'partial_refund'))
    } finally {
      setLoadingTab(false)
    }
  }, [customerId])

  const loadHistory = useCallback(async () => {
    setLoadingTab(true)
    try {
      const { data } = await api.get(`/customers/${customerId}/history`, { _suppressToast: true })
      setHistory(data)
    } finally {
      setLoadingTab(false)
    }
  }, [customerId])

  useEffect(() => {
    if (tab === 'sotuvlar' || tab === 'qaytarishlar' || tab === 'akt') loadSales()
    if (tab === 'operatsiyalar' || tab === 'akt') loadHistory()
  }, [tab, loadSales, loadHistory])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!stats) return null

  const dynamicBalance = (() => {
    if (stats.debt_balances && Object.keys(stats.debt_balances).length > 0) {
      let uzs = 0;
      Object.entries(stats.debt_balances).forEach(([curr, amt]) => {
        const rate = curr === 'UZS' ? 1 : (currencies.find(c => c.code === curr)?.rate || 1);
        uzs += (Number(amt) || 0) * rate;
      });
      return uzs;
    }
    return Number(stats.debt_balance || 0);
  })();

  const customerName = stats.name
  const initial = customerName?.charAt(0)?.toUpperCase()
  const avatarColors = ['bg-blue-100 text-blue-600', 'bg-emerald-100 text-emerald-600', 'bg-violet-100 text-violet-600', 'bg-blue-100 text-blue-600', 'bg-amber-100 text-amber-600']
  const avatarColor = avatarColors[(customerName?.charCodeAt(0) || 0) % avatarColors.length]

  return (
    <div className="space-y-6">
      {/* Back button + Header */}
      <div className="flex items-center sm:gap-4">
        <button
          onClick={() => navigate('/admin/customers')}
          className="mt-1 p-2 rounded-xl cursor-pointer hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex items-center gap-4 flex-1">
          <div className={`w-10 h-10 sm:w-14 sm:h-14 rounded-lg sm:rounded-2xl flex items-center justify-center text-xl font-bold shrink-0 ${avatarColor}`}>
            {initial}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-md sm:text-2xl font-bold text-slate-800">{stats.name}</h1>
              <span className={`px-2 py-0.5 rounded-lg sm:rounded-full text-xs font-semibold ${TIER_STYLES[stats.tier]}`}>
                {stats.tier}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs sm:text-sm text-slate-500">
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
        <div className="flex border-b overflow-x-auto overflow-y-hidden border-slate-100">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-2 md:px-5 py-3.5 text-[12px] sm:text-sm cursor-pointer font-semibold whitespace-nowrap transition-colors border-b-2 -mb-px
                ${tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-2 sm:p-4 md:p-6">
          {/* UMUMIY TAB */}
          {tab === 'umumiy' && (
            <div className="space-y-6">
              <div className='flex gap-6 flex-col xl:flex-row'>
                <div className='w-full xl:w-max bg-linear-to-t py-4 sm:p-10 xl:p-0 mx-auto from-white  xl:via-white xl:to-white md:via-blue-00 md:to-blue-600 shadow-inner shadow-white rounded-3xl'>
                  {/* Virtual Card */}
                  {stats.card_number && (
                    <div className="bg-linear-to-tr mx-auto from-blue-900 via-blue-800 to-blue-600 rounded-3xl p-4 sm:p-6 md:p-8 text-white shadow-xl shadow-blue-900/20 relative overflow-hidden flex flex-col justify-between sm:h-[280px] w-max border-2 border-blue-500">
                      {/* Background decoration */}
                      <div className="absolute -right-10 -top-10 w-40 h-40 bg-white/10 rounded-full blur-2xl"></div>
                      <div className="absolute -left-10 -bottom-10 w-32 h-32 bg-blue-400/20 rounded-full blur-xl"></div>

                      <div className="relative z-10 flex justify-between items-start">
                        <div>
                          <div className="text-blue-200 text-[9px] sm:text-[11px] uppercase tracking-widest font-semibold sm:mb-1">Mijoz Kartasi</div>
                          <div className="text-lg sm:text-xl font-bold drop-shadow-sm">{stats.name}</div>
                        </div>
                        <div className="bg-white/20 backdrop-blur-md border border-white/10 px-2 sm:px-3 py-1 sm:py-1.5 rounded-full text-xs sm:text-sm font-semibold flex items-center gap-1.5 shadow-sm">
                          <svg className="w-4 h-4 text-amber-300" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                          </svg>
                          {stats.cashback_percent > 0 ? `${stats.cashback_percent}% Keshbek` : 'Standard Card'}
                        </div>
                      </div>

                      <div className="relative z-10 mt-4 sm:mt-8 space-y-2 sm:space-y-5">
                        <div className="text-[23px] sm:text-[30px] font-mono sm:tracking-[4px] text-white/90 drop-shadow-md">
                          {stats.card_number}
                        </div>
                        <div className="flex items-center justify-between border-t border-white/10 pt-4">
                          <div>
                            <div className="text-blue-200 text-[10px] uppercase font-bold tracking-wider mb-0.5">Bonus Balans</div>
                            <div className="font-bold text-[14px] sm:text-lg text-emerald-300">{fmt(stats.bonus_balance)} <span className="text-xs font-medium opacity-80">{stats.debt_currency === 'USD' ? '$' : "so'm"}</span></div>
                          </div>
                          <div className="text-right">
                            <div className="text-blue-200 text-[10px] uppercase font-bold tracking-wider mb-0.5">Jami Xaridlar</div>
                            <div className="font-bold text-[14px] sm:text-base text-white">{fmt(stats.total_spent)} <span className="text-xs font-medium opacity-80">{stats.debt_currency === 'USD' ? '$' : "so'm"}</span></div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 flex-1 w-full gap-1 sm:gap-4">
                  <StatCard
                    color="indigo"
                    label="Jami Sotuvlar"
                    value={`${fmt(stats.total_sales_count)} ta`}
                    sub={`${fmt(stats.total_sales_amount)} ${stats.debt_currency === 'USD' ? '$' : "so'm"}`}
                    icon={<svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>}
                  />
                  <StatCard
                    color="emerald"
                    label="To'langan"
                    value={`${fmt(stats.total_paid_amount)} ${stats.debt_currency === 'USD' ? '$' : "so'm"}`}
                    sub={`${fmt(stats.total_sales_count)} sotuvdan`}
                    icon={<svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                  />
                  <StatCard
                    color="red"
                    label="Qarzdorlik"
                    value={`${fmt(dynamicBalance)} so'm`}
                    sub={
                      stats.debt_balances && Object.keys(stats.debt_balances).length > 0 ? (
                        <div className="flex gap-x-3 flex-wrap mt-1">
                          {Object.entries(stats.debt_balances).map(([curr, amt]) => (
                            <span key={curr} className="px-1.5 py-0.5 bg-white/50 rounded border border-black/5 text-[10px] font-bold text-slate-600">
                              {fmt(amt)} {curr === 'USD' ? '$' : curr}
                            </span>
                          ))}
                        </div>
                      ) : (
                        stats.debt_limit > 0 ? `Limit: ${fmt(stats.debt_limit)} so'm` : 'Limit belgilanmagan'
                      )
                    }
                    icon={<svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                  />
                  <StatCard
                    color="amber"
                    label="Qaytarishlar"
                    value={`${fmt(stats.total_returns_count)} ta`}
                    sub={`${fmt(stats.total_returns_amount)} ${stats.debt_currency === 'USD' ? '$' : "so'm"}`}
                    icon={<svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" /></svg>}
                  />
                </div>
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
                      <div className={`h-2 rounded-full mb-1.5 ${['Standard', 'Bronze', 'Silver', 'Gold'].indexOf(stats.tier) >= i ? 'bg-blue-500' : 'bg-slate-200'}`} />
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
            <SalesTable rows={sales} stats={stats} salesData={salesData} loading={loadingTab} />
          )}

          {/* QAYTARISHLAR TAB */}
          {tab === 'qaytarishlar' && (
            <div>
              <div className="flex justify-end mb-4">
                <button
                  onClick={() => setReturnModal(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-xl font-semibold text-sm shadow-sm transition-all active:scale-95"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                  </svg>
                  Yangi qaytarish
                </button>
              </div>
              <ReturnsTable rows={returns} loading={loadingTab} />
              {returnModal && (
                <CustomerReturnModal
                  customerId={customerId}
                  warehouses={warehouses}
                  wallets={wallets}
                  onClose={() => setReturnModal(false)}
                  onSuccess={() => { setReturnModal(false); loadSales(); }}
                />
              )}
            </div>
          )}

          {/* OPERATSIYALAR TAB */}
          {tab === 'operatsiyalar' && (
            <OperationsTable rows={history} loading={loadingTab} />
          )}

          {/* AKT SVERKA TAB */}
          {tab === 'akt' && (
            <AktSverka stats={{ ...stats, debt_balance: dynamicBalance }} sales={sales} history={history} loading={loadingTab} />
          )}

          {tab === 'kirim_tolovlar' && (
            <KirimTolovlar stats={stats} income={income} loading={loadingTab} />
          )}
        </div>
      </div>
    </div>
  )
}
function SalesTable({ rows, stats, salesData, loading, emptyText = "Sotuvlar yo'q" }) {
  const { t } = useLang();

  // 1. BARCHA HOOKLAR ENG TEPADA BO'LISHI SHART
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [selectedEmployee, setSelectedEmployee] = useState('all');

  const [openSaleDetailModal, setOpenSaleDetailModal] = useState(false);
  const [saleDetailData, setSaleDetailData] = useState(null);

  async function openSaleDetail(id) {
    try {
      const response = await api.get(`/sales/${id}`);
      setSaleDetailData(response.data);
      setOpenSaleDetailModal(true);
    } catch (error) {
      console.error(error);
    }
  }

  const [openPartialReturnModal, setOpenPartialReturnModal] = useState(false);

  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(() => Number(localStorage.getItem('sales_limit')) || 10);

  // Filtrlar o'zgarganda 1-sahifaga qaytish
  useEffect(() => {
    setPage(1);
  }, [fromDate, toDate, selectedEmployee, limit]);

  // 2. HOOKLARDAN KEYINGI ERTA QAYTISHLAR (Early returns)
  if (loading) return <LoadingSpinner />
  if (!rows.length) return <Empty text={emptyText} />

  // 3. ASOSIY MANTIQ
  const filteredByEmployee = [];

  // Ma'lumotlarni ham mijoz bo'yicha, ham sana bo'yicha filtrlash
  const filtered_sales = salesData.filter(i => {
    if (i.customer_name !== stats.name) return false;

    if (fromDate || toDate) {
      const itemDate = new Date(i.created_at);

      if (fromDate) {
        const from = new Date(fromDate);
        from.setHours(0, 0, 0, 0);
        if (itemDate < from) return false;
      }

      if (toDate) {
        const to = new Date(toDate);
        to.setHours(23, 59, 59, 999);
        if (itemDate > to) return false;
      }
    }
    return true;
  });

  // Xodimlarni yig'ish
  filtered_sales.forEach(item => {
    if (filteredByEmployee.includes(item.cashier_name)) return;
    filteredByEmployee.push(item.cashier_name);
  });

  // Xodim bo'yicha filtrlash
  const filteredByEmployeeSales = filtered_sales.filter(item => {
    if (selectedEmployee === 'all') return true;
    return item.cashier_name === selectedEmployee;
  });

  // Sahifalash (Pagination Logic)
  const totalRecords = filteredByEmployeeSales.length;
  const totalPages = Math.ceil(totalRecords / limit) || 1;
  const paginatedSales = filteredByEmployeeSales.slice((page - 1) * limit, page * limit);

  return (
    <div>
      <div className="flex justify-end mb-4 gap-1 flex-wrap xl:gap-3 sm:-mt-2">
        {/* Xodim filtrlari */}
        <div className="flex items-center border px-3 border-slate-200 rounded-md gap-2 bg-white">
          <label htmlFor="employee" className='text-sm xl:text-md text-slate-600'>Xodim</label>
          <select
            id="employee"
            value={selectedEmployee}
            onChange={(e) => setSelectedEmployee(e.target.value)}
            className='cursor-pointer py-1.5 xl:py-2 border-l border-slate-200 pl-2 outline-none bg-transparent'
          >
            <option value="all">Barchasi</option>
            {filteredByEmployee.map(employee => (
              <option key={employee} className='' value={employee}>{employee}</option>
            ))}
          </select>
        </div>

        {/* Sana filtrlari */}
        <div className='flex gap-1 xl:gap-3 flex-wrap justify-end'>
          <div className='flex items-center border px-3 border-slate-200 rounded-md gap-2 bg-white'>
            <label htmlFor="from" className='text-sm xl:text-md text-slate-600'>dan</label>
            <input
              type="date"
              id='from'
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className='cursor-pointer text-sm xl:text-md py-1.5 xl:py-2 border-l border-slate-200 pl-2 outline-none bg-transparent'
            />
          </div>
          <div className='flex items-center border px-3 border-slate-200 rounded-md gap-2 bg-white'>
            <label htmlFor="to" className='text-sm xl:text-md text-slate-600'>gacha</label>
            <input
              type="date"
              id='to'
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className='cursor-pointer text-sm xl:text-md py-1.5 xl:py-2 border-l border-slate-200 pl-2 outline-none bg-transparent'
            />
          </div>
          {/* Filterni tozalash tugmasi */}
          {(fromDate || toDate) && (
            <button
              onClick={() => { setFromDate(''); setToDate(''); }}
              className="text-sm cursor-pointer text-red-500 hover:text-red-700 underline px-2"
            >
              Tozalash
            </button>
          )}
        </div>
      </div>

      {/* Table Konteyneri */}
      <div className="flex bg-white rounded-2xl flex-col h-full border border-slate-100 shadow-sm">
        <div className="w-full overflow-x-auto table-fixed scrollbar-thin scrollbar-thumb-slate-200 rounded-t-2xl overflow-hidden">
          <table className="min-w-[1200px] w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.number') || 'Raqam'}</th>
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{'Xodim'}</th>
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">To'lov turi</th>
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.total') || 'Jami'}</th>
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">To'langan</th>
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.debt') || 'Qarz'}</th>
                <th className="px-4 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{t('admin.dict.date') || 'Sana'}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {paginatedSales.length > 0 ? (
                paginatedSales.map(s => {
                  const debt = Number(s.total_amount) - Number(s.paid_amount)
                  
                  // Har bir valyuta uchun to'g'ri ko'rsatish
                  let debtStr = '—';
                  if (s.debt_amounts && Object.keys(s.debt_amounts).length > 0) {
                    const validDebts = Object.entries(s.debt_amounts).filter(([, v]) => Math.abs(v) > 0.001);
                    if (validDebts.length > 0) {
                      debtStr = validDebts.map(([k, v]) => `${fmt(v)} ${k === 'USD' ? '$' : k}`).join(', ');
                    }
                  } else if (debt > 0.01) {
                    debtStr = `${fmt(debt)} ${s.currency_code === 'USD' ? '$' : "so'm"}`;
                  }
                  
                  const curr = s.currency_code || s.currency || 'UZS';
                  const currSign = curr === 'USD' ? '$' : "so'm";
                  return (
                    <tr key={s.id} onClick={() => openSaleDetail(s.id)} className="hover:bg-slate-50 transition-colors cursor-pointer">
                      <td className="px-4 py-4 font-mono text-xs text-slate-600">{s.number}</td>
                      <td className="px-4 py-4">
                        <code className="py-0.5 rounded-full text-xs">
                          {s.cashier_name}
                        </code>
                      </td>
                      <td className="px-4 py-4">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PAY_STYLES[s.payment_type] || ''}`}>
                          {PAY_LABELS[s.payment_type] || s.payment_type}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-left font-semibold text-slate-800">{fmt(s.total_amount)} {currSign}</td>
                      <td className="px-4 py-4 text-left text-emerald-600 font-medium">{fmt(s.paid_amount)} {currSign}</td>
                      <td className={`px-4 py-4 text-left font-medium ${debtStr !== '—' ? 'text-red-500' : 'text-slate-400'}`}>
                        {debtStr}
                      </td>
                      <td className="px-4 py-4 text-slate-500 whitespace-nowrap">{fmtDate(s.created_at)}</td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan="7" className="text-center py-16 text-slate-500">
                    <div className="flex flex-col items-center gap-2 text-slate-400">
                      <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                      </svg>
                      <span className="text-sm">Ushbu holat bo'yicha ma'lumot topilmadi</span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
            {/* Tfoot: Umumiy yig'indilar */}
            {filteredByEmployeeSales.length > 0 && (
              <tfoot>
                <tr className="border-t-2 border-slate-200 bg-slate-50/50">
                  <td colSpan={3} className="px-4 py-4 text-xs font-semibold text-slate-400 uppercase">{t('admin.dict.total') || 'Jami'}</td>
                  <td className="px-4 py-4 text-left font-bold text-slate-800">
                    {fmt(filteredByEmployeeSales.reduce((s, r) => s + Number(r.total_amount), 0))} {stats.debt_currency === 'USD' ? '$' : "so'm"}
                  </td>
                  <td className="px-4 py-4 text-left font-bold text-emerald-600">
                    {fmt(filteredByEmployeeSales.reduce((s, r) => s + Number(r.paid_amount), 0))} {stats.debt_currency === 'USD' ? '$' : "so'm"}
                  </td>
                  <td className="px-4 py-4 text-left font-bold text-red-500">
                    {fmt(filteredByEmployeeSales.reduce((s, r) => s + Math.max(0, Number(r.total_amount) - Number(r.paid_amount)), 0))} {stats.debt_currency === 'USD' ? '$' : "so'm"}
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>

        {/* Sahifalash (Pagination) qismi */}
        {filteredByEmployeeSales.length > 0 && (
          <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-xs md:text-sm text-slate-500 bg-slate-50 rounded-b-2xl">
            <span>Jami <strong className="text-slate-700">{totalRecords}</strong> ta sotuv</span>

            <div className="flex items-center flex-nowrap gap-0 sm:gap-1">
              <button disabled={page === 1} onClick={() => setPage(1)}
                className={`rounded-lg ${page === 1 ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronsLeft className='size-4 sm:size-5' />
              </button>
              <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                className={`rounded-lg ${page === 1 ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronLeft className='size-4 sm:size-5' />
              </button>
              <span className="px-2 sm:px-3 text-[12px] xl:text-[14px] whitespace-nowrap font-semibold text-slate-700">{page} / {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                className={`rounded-lg ${page >= totalPages ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronRight className='size-4 sm:size-5' />
              </button>
              <button disabled={page === totalPages} onClick={() => setPage(totalPages)}
                className={`rounded-lg ${page === totalPages ? 'text-slate-300' : 'text-slate-700 hover:bg-white bg-slate-50 cursor-pointer'} transition-colors`}>
                <ChevronsRight className='size-4 sm:size-5' />
              </button>
            </div>

            <div className='flex gap-1 md:gap-3 text-right md:text-left items-center flex-col md:flex-row'>
              <div className="z-30 ml-auto md:ml-0">
                <Listbox
                  value={limit}
                  onChange={(val) => {
                    const v = Number(val);
                    localStorage.setItem('sales_limit', v);
                    setLimit(v);
                  }}
                >
                  <div className="relative min-w-[90px] sm:min-w-[120px]">
                    <ListboxButton className="w-full cursor-pointer flex items-center py-1 px-2 xl:px-3 xl:py-1.5 justify-between rounded-lg border border-slate-200 text-[13px] xl:text-[14px] bg-white text-slate-900 outline-none hover:border-blue-400 focus:border-blue-500 transition-colors shadow-sm text-left">
                      <span className="flex items-center gap-2">
                        <ListOrdered className="size-4 shrink-0 text-slate-400" />
                        <span>{limit} {t('common.item') || 'ta'}</span>
                      </span>
                      <ChevronsUpDown aria-hidden="true" className="size-4 text-gray-400" />
                    </ListboxButton>
                    <ListboxOptions
                      anchor="top end"
                      className="z-50 min-w-[120px] mb-1 overflow-auto rounded-xl bg-white border border-slate-200 p-1 shadow-2xl focus:outline-none [--anchor-gap:4px]"
                    >
                      {[5, 10, 20, 50, 100, 500].map((n) => (
                        <ListboxOption key={n} value={n} className="group flex cursor-pointer items-center gap-2 rounded-lg py-2 px-3 select-none data-[focus]:bg-blue-50">
                          <CheckIcon className="size-4 text-blue-600 group-not-data-[selected]:invisible" />
                          <div className="text-[13px] font-medium text-slate-700 group-data-[selected]:text-blue-700">{n} {t('common.item') || 'ta'}</div>
                        </ListboxOption>
                      ))}
                    </ListboxOptions>
                  </div>
                </Listbox>
              </div>
            </div>
          </div>
        )}
      </div>

      {openSaleDetailModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm z-50 p-4 transition-opacity">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">

            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white shrink-0">
              <div className="flex items-center gap-4">
                <h3 className="text-xl font-bold text-slate-800">Sotuv tafsilotlari</h3>
                {saleDetailData?.status !== 'refunded' && saleDetailData?.status !== 'cancelled' && (
                  <button
                    onClick={() => {
                      setOpenPartialReturnModal(true);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors border border-red-100/50"
                  >
                    <RotateCcw size={14} />
                    Vozvrat qilish
                  </button>
                )}
              </div>
              <button
                onClick={() => setOpenSaleDetailModal(false)}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors duration-150 cursor-pointer"
              >
                <X size={20} />
              </button>
            </div>

            {/* Scrollable Body */}
            <div className="p-6 overflow-y-auto space-y-6">

              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Umumiy Summa */}
                <div className="bg-slate-50/80 p-4 rounded-xl border border-slate-100">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Umumiy summa</p>
                  <p className="text-lg font-bold text-slate-900 mt-1">
                    {fmt(saleDetailData?.total_amount)} <span className="text-xs text-slate-500 font-normal">{saleDetailData?.currency_code || saleDetailData?.currency}</span>
                  </p>
                </div>

                {/* To'langan */}
                <div className="bg-emerald-50/50 p-4 rounded-xl border border-emerald-100/60">
                  <p className="text-xs font-medium text-emerald-600 uppercase tracking-wider">To'langan</p>
                  <p className="text-lg font-bold text-emerald-700 mt-1">
                    {fmt(saleDetailData?.paid_amount)} <span className="text-xs text-emerald-600 font-normal">{saleDetailData?.currency_code || saleDetailData?.currency}</span>
                  </p>
                </div>

                {/* Qarzga qolgan */}
                <div className={`p-4 rounded-xl border ${saleDetailData?.debt_amount > 0 ? 'bg-amber-50/50 border-amber-100/60' : 'bg-slate-50/80 border-slate-100'}`}>
                  <p className={`text-xs font-medium uppercase tracking-wider ${saleDetailData?.debt_amount > 0 ? 'text-amber-600' : 'text-slate-500'}`}>
                    Qarzga qolgan
                  </p>
                  <p className={`text-lg font-bold mt-1 ${saleDetailData?.debt_amount > 0 ? 'text-amber-700' : 'text-slate-700'}`}>
                    {fmt(saleDetailData?.debt_amount)} <span className="text-xs font-normal opacity-75">{saleDetailData?.currency_code || saleDetailData?.currency}</span>
                  </p>
                </div>
              </div>

              {/* Items Table */}
              <div className="space-y-3">
                <h4 className="text-sm font-bold text-slate-800 uppercase tracking-wider">Mahsulotlar</h4>
                <div className="border border-slate-100 rounded-xl overflow-hidden shadow-xs">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Mahsulot</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Miqdor</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Narx</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Jami</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-slate-100 text-sm text-slate-700">
                        {saleDetailData?.items?.map((item, index) => {
                          const itemCurrency = item.currency_code || saleDetailData?.currency_code || saleDetailData?.currency || 'UZS';
                          const currLabel = itemCurrency === 'USD' ? '$' : "so'm";
                          return (
                          <tr key={index} className="hover:bg-slate-50/60 transition-colors">
                            <td className="px-4 py-3 font-medium text-slate-900">{item.product_name}</td>
                            <td className="px-4 py-3 text-right font-mono text-slate-600">{Number(item.quantity).toFixed(2).replace(/\.00$/, '')} {item.unit}</td>
                            <td className="px-4 py-3 text-right font-mono text-slate-600 whitespace-nowrap">{fmt(item.unit_price)} {currLabel}</td>
                            <td className="px-4 py-3 text-right font-semibold text-slate-900 whitespace-nowrap">{fmt(item.subtotal)} {currLabel}</td>
                          </tr>
                        )})}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-slate-100 flex justify-end bg-slate-50/50 shrink-0">
              <button
                onClick={() => setOpenSaleDetailModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors cursor-pointer"
              >
                Yopish
              </button>
            </div>

          </div>
        </div>
      )}

      {openPartialReturnModal && (
        <PartialReturnModal
          sale={saleDetailData}
          onClose={() => setOpenPartialReturnModal(false)}
          onSuccess={() => {
            setOpenPartialReturnModal(false);
            setOpenSaleDetailModal(false);
            // Sahifani yangilash uchun fetchData yuboriladi agar kerak bo'lsa
            // Ammo bu yerda window.location.reload yoki prop chaqirish mumkin
          }}
        />
      )}
    </div>
  )
}
// ────────────────────────────────────────────────────────────
// Har bir operatsiya turi uchun rang va belgilar
// ────────────────────────────────────────────────────────────
const OP_ICON = {
  sale: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
    </svg>
  ),
  payment: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  debt_edit: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  ),
}
const OP_COLOR = {
  sale: 'bg-blue-100 text-blue-600',
  payment: 'bg-emerald-100 text-emerald-600',
  debt_edit: 'bg-amber-100 text-amber-600',
}
const OP_LABEL = {
  sale: 'Sotuv',
  payment: "Qarz to'lovi",
  debt_edit: 'Qarz tahriri',
}

function OperationsTable({ rows, loading }) {
  if (loading) return <LoadingSpinner />
  if (!rows.length) return <Empty text="Operatsiyalar yo'q" />

  const getCurrencyCode = (c) => {
    if (!c) return 'UZS'
    if (typeof c === 'object') return c.code || 'UZS'
    return c
  }

  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const opType = r.op_type || r.type || 'sale'
        const currCode = getCurrencyCode(r.currency)
        const curr = currCode === 'USD' ? '$' : (currCode || "so'm")
        return (
          <div key={i} className="flex items-start gap-3 p-3 rounded-xl border border-slate-100 hover:bg-slate-50 transition-colors">
            {/* Ikon */}
            <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${OP_COLOR[opType] || 'bg-slate-100 text-slate-500'}`}>
              {OP_ICON[opType] || OP_ICON.sale}
            </div>

            {/* Matn */}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-slate-700">
                {OP_LABEL[opType] || opType}
                {r.sale_number ? <span className="ml-1 text-xs text-slate-400">#{r.sale_number}</span> : null}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{fmtDate(r.date)}</div>
            </div>

            {/* Raqamlar */}
            <div className="text-right shrink-0">
              {opType === 'sale' && (
                <div className="text-sm font-bold text-blue-600">
                  {fmt(r.amount)} {curr}
                </div>
              )}
              {opType === 'payment' && (
                <div className="text-sm font-bold text-emerald-600">
                  +{fmt(r.amount)} {curr}
                </div>
              )}
              {opType === 'debt_edit' && (
                <div className="text-sm font-bold text-amber-600">
                  {fmt(r.amount)} {curr}
                </div>
              )}
              {opType === 'sale' && (
                <div className="flex gap-2 mt-0.5 justify-end">
                  <span className="text-[11px] text-emerald-600">To'landi: {fmt(r.paid)} {curr}</span>
                  {(r.debt > 0) && (
                    <span className="text-[11px] text-red-500">Qarz: {fmt(r.debt)} {curr}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AktSverka({ stats, sales, loading, history }) {
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [sortOrder, setSortOrder] = useState('asc')
  const [operationType, setOperationType] = useState('all')
  const [selectedCashier, setSelectedCashier] = useState('all')
  const [openSaleDetailModal, setOpenSaleDetailModal] = useState(false)
  const [saleDetailData, setSaleDetailData] = useState(null)
  const [openPartialReturnModal, setOpenPartialReturnModal] = useState(false)

  async function openSaleDetail(id) {
    try {
      const response = await api.get(`/sales/${id}`)
      setSaleDetailData(response.data)
      setOpenSaleDetailModal(true)
    } catch (error) {
      console.error(error)
    }
  }

  if (loading) return <LoadingSpinner />

  const fmtDate2 = (dateString) => {
    if (!dateString) return '—'
    const date = new Date(dateString)
    const p = (n) => String(n).padStart(2, '0')
    return `${p(date.getDate())}.${p(date.getMonth() + 1)}.${date.getFullYear()} ${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}`
  }

  const mappedBalances = Object.entries(stats.debt_balances || {}).map(([currency, amount]) => ({ currency, amount }))

  // ── Birlashtirilgan timeline yasash ──────────────────────────────────────────
  // (1) Sotuvlar
  const saleEvents = sales.map(s => ({
    id: s.id,
    key: `sale-${s.id}`,
    date: s.created_at,
    label: 'Sotuv',
    sublabel: s.payment_type ? PAY_LABELS[s.payment_type] || s.payment_type : '',
    amount: Number(s.total_amount || 0),
    paid: Number(s.paid_amount || 0),
    // Qarzga sotuv: to'lanmagan qism qarz bo'ladi
    debtChange: +Math.max(0, Number(s.total_amount || 0) - Number(s.paid_amount || 0)),
    cashier: s.cashier_name || '',
    currency: s.currency || 'UZS',
    rowType: 'sale',
    saleNumber: s.number || '',
  }))

  // (2) Qarz to'lovlari (history ichidan payment turlar)
  const paymentEvents = (history || []).filter(h => h.op_type === 'payment' || h.type === 'payment').map(h => ({
    id: h.id || null,
    key: `pay-${h.date}`,
    date: h.date,
    label: "Qarz to'lovi",
    sublabel: h.payment_type || '',
    amount: Number(h.amount || 0),
    paid: Number(h.amount || 0),
    // To'lov qarzni kamaytiradi
    debtChange: -Number(h.amount || 0),
    cashier: h.cashier || '',
    currency: h.currency || 'UZS',
    rowType: 'payment',
    description: h.description || '',
  }))

  // (3) Qarz tahrirlari
  const editEvents = (history || []).filter(h => h.op_type === 'debt_edit' || h.type === 'debt_edit').map(h => ({
    id: h.id || null,
    key: `edit-${h.date}`,
    date: h.date,
    label: 'Qarz tahriri',
    sublabel: '',
    amount: Number(h.amount || 0),
    paid: 0,
    debtChange: Number(h.debt || 0),  // musbat: qarz ortdi, manfiy: qarz kamaydi
    cashier: h.cashier || '',
    currency: h.currency || 'UZS',
    rowType: 'debt_edit',
    description: h.description || '',
  }))

  // Eski tartib (eng eski birinchi)
  const allEvents = [...saleEvents, ...paymentEvents, ...editEvents]
    .sort((a, b) => new Date(a.date) - new Date(b.date))

  // Kassirlarni dinamik yig'ish (faqat mavjud kassirlar)
  const cashiers = Array.from(new Set(allEvents.map(e => e.cashier).filter(Boolean)))

  // ── Running balance hisoblash ─────────────────────────────────────────────
  // Joriy qarz allaqachon barcha operatsiyalarni o'z ichiga oladi.
  // Boshlang'ich qarz = joriy qarz − barcha operatsiyalar yig'indisi.
  const currentDebt = mappedBalances.reduce((sum, b) => sum + Number(b.amount || 0), 0)
  const totalDebtChange = allEvents.reduce((sum, ev) => sum + ev.debtChange, 0)
  const initialDebt = Math.max(0, currentDebt - totalDebtChange)

  const allEventsWithBalance = allEvents.reduce((acc, ev) => {
    const prevDebt = acc.length > 0 ? acc[acc.length - 1].finalDebt : initialDebt
    const finalDebt = Math.max(0, prevDebt + ev.debtChange)
    acc.push({ ...ev, prevDebt, finalDebt })
    return acc
  }, [])

  // Filtrlar
  const filteredRows = allEventsWithBalance.filter(ev => {
    // 1. Sana bo'yicha filter
    if (fromDate || toDate) {
      const itemDate = new Date(ev.date)
      if (fromDate) {
        const from = new Date(fromDate)
        from.setHours(0, 0, 0, 0)
        if (itemDate < from) return false
      }
      if (toDate) {
        const to = new Date(toDate)
        to.setHours(23, 59, 59, 999)
        if (itemDate > to) return false
      }
    }

    // 2. Operatsiya turi bo'yicha filter
    if (operationType !== 'all') {
      if (ev.rowType !== operationType) return false
    }

    // 3. Kassir bo'yicha filter
    if (selectedCashier !== 'all') {
      if (ev.cashier !== selectedCashier) return false
    }

    return true
  })

  // Tartib bo'yicha saralash
  const displayRows = [...filteredRows].sort((a, b) => {
    const dateA = new Date(a.date).getTime()
    const dateB = new Date(b.date).getTime()
    if (sortOrder === 'desc') {
      return dateB - dateA
    } else {
      return dateA - dateB
    }
  })

  const finalBalance = allEventsWithBalance.length > 0 ? allEventsWithBalance[allEventsWithBalance.length - 1].finalDebt : currentDebt
  const totalPaid = saleEvents.reduce((s, e) => s + e.paid, 0)
  const totalPayments = paymentEvents.reduce((s, e) => s + e.amount, 0)

  const rowBg = {
    sale: '',
    payment: 'bg-emerald-50',
    debt_edit: 'bg-amber-50',
  }
  const rowLabel = {
    sale: 'text-blue-700',
    payment: 'text-emerald-700',
    debt_edit: 'text-amber-700',
  }

  return (
    <div className="space-y-3">
      {/* Sarlavha */}
      <div className='flex flex-wrap items-center gap-3'>
        <h3 className="text-sm font-semibold text-slate-700">Akt Sverka — {stats.name}</h3>
        {mappedBalances.length > 0 && (
          <div className='text-sm border border-slate-200 px-3 py-1 rounded flex gap-3 font-medium text-slate-600'>
            Qarzdorlik:
            {mappedBalances.map((item) => (
              <span key={item.currency}>
                <span className='text-red-600'>{fmt(item.amount)}</span>{' '}
                <span className='text-blue-500 text-xs'>{item.currency}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-2 border-b flex-wrap border-slate-200 pb-3">
        <div className="border border-slate-200 flex items-center gap-2 px-3 min-w-50 rounded">
          <span className='text-slate-700'>dan:</span>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className='outline-0 border-l border-slate-200 pl-2 py-1'
          />
        </div>

        <div className="border border-slate-200 flex items-center gap-2 px-3 min-w-50 rounded">
          <span className='text-slate-700'>gacha:</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className='outline-0 border-l border-slate-200 pl-2 py-1'
          />
        </div>

        <div className="border border-slate-200 flex items-center gap-2 px-3 min-w-55 rounded">
          <span className='text-slate-700'>Tartib:</span>
          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            className='outline-0 w-full cursor-pointer border-l border-slate-200 pl-2 py-1'
          >
            <option value="asc">Eski birinchi</option>
            <option value="desc">Yangi birinchi</option>
          </select>
        </div>

        <div className="border border-slate-200 flex items-center gap-2 px-3 min-w-60 rounded">
          <span className='text-slate-700'>Operatsiya:</span>
          <select
            value={operationType}
            onChange={(e) => setOperationType(e.target.value)}
            className='outline-0 w-full cursor-pointer border-l border-slate-200 pl-2 py-1'
          >
            <option value="all">Barchasi</option>
            <option value="sale">Sotuv</option>
            <option value="payment">Qarz to'lovi</option>
            <option value="debt_edit">Qarz tahriri</option>
          </select>
        </div>

        <div className="border border-slate-200 flex items-center gap-2 px-3 min-w-50 rounded">
          <span className='text-slate-700'>Kassir:</span>
          <select
            value={selectedCashier}
            onChange={(e) => setSelectedCashier(e.target.value)}
            className='outline-0 w-full cursor-pointer border-l border-slate-200 pl-2 py-1'
          >
            <option value="all">Barchasi</option>
            {cashiers.map((cashierName) => (
              <option key={cashierName} value={cashierName}>{cashierName}</option>
            ))}
          </select>
        </div>

        <button
          onClick={() => {
            setFromDate('')
            setToDate('')
            setSortOrder('asc')
            setOperationType('all')
            setSelectedCashier('all')
          }}
          className='border ml-auto border-slate-200 text-slate-700 px-3 py-1 flex gap-1.5 items-center rounded cursor-pointer'
        >
          <RotateCcw size={18} />
          <span>Filterni tozalash</span>
        </button>
      </div>

      {/* Jadval */}
      {displayRows.length === 0 ? (
        <Empty text="Operatsiyalar yo'q" />
      ) : (
        <div className='overflow-x-auto'>
          <table className='w-full min-w-[980px] text-sm'>
            <thead>
              <tr>
                {['#', 'Operatsiya', "To'lov turi", 'Oldingi qarz', 'Qarzning oshishi', "Qarzning kamayishi", 'Yakuniy qarz', "To'langan", 'Kassir', 'Sana'].map((h, i) => (
                  <th key={i} className='font-semibold uppercase text-slate-700 p-2 border border-slate-200'>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className='divide-y divide-slate-100'>
              {displayRows.map((row, i) => {
                const curr = row.currency === 'USD' ? '$' : (row.currency || "so'm")
                const debtIncrease = row.debtChange > 0 ? row.debtChange : 0
                const debtDecrease = row.debtChange < 0 ? Math.abs(row.debtChange) : 0

                return (
                  <tr key={row.key} className={`text-center text-slate-700 hover:bg-slate-100 transition-all cursor-pointer`} onClick={() => openSaleDetail(row.id)}>
                    <td className='p-2 border border-slate-200'>{i + 1}</td>
                    <td className={`p-2 border border-slate-200 font-medium`}>
                      {row.label}
                    </td>
                    <td className='p-2 border capitalize border-slate-200'>
                      {row.sublabel || '—'}
                    </td>
                    {/* Oldingi qarz */}
                    <td className='p-2 border border-slate-200'>
                      {fmt(row.prevDebt)} {curr}
                    </td>
                    {/* Qarzning oshishi (qizil) */}
                    <td className='p-2 border border-slate-200'>
                      {debtIncrease > 0
                        ? <span className=''>{fmt(debtIncrease)} {curr}</span>
                        : ""}
                    </td>
                    {/* Qarzning kamayishi (yashil) */}
                    <td className='p-2 border border-slate-200'>
                      {debtDecrease > 0
                        ? <span className=''>{fmt(debtDecrease)} {curr}</span>
                        : ""}
                    </td>
                    {/* Yakuniy qarz */}
                    <td className='p-2 border border-slate-200'>
                      <span>
                        {fmt(row.finalDebt)} {curr}
                      </span>
                    </td>
                    {/* To'langan */}
                    <td className='p-2 border border-slate-200'>
                      {row.paid > 0 ? `${fmt(row.paid)} ${curr}` : ""}
                    </td>
                    <td className='p-2 border border-slate-200 text-slate-500'>{row.cashier || ''}</td>
                    <td className='p-2 border border-slate-200 text-slate-500 whitespace-nowrap'>{fmtDate2(row.date)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* modal */}

      {openSaleDetailModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm z-50 p-4 transition-opacity">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">

            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white shrink-0">
              <div className="flex items-center gap-4">
                <h3 className="text-xl font-bold text-slate-800">Sotuv tafsilotlari</h3>
                {saleDetailData?.status !== 'refunded' && saleDetailData?.status !== 'cancelled' && (
                  <button
                    onClick={() => {
                      setOpenPartialReturnModal(true);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors border border-red-100/50"
                  >
                    <RotateCcw size={14} />
                    Vozvrat qilish
                  </button>
                )}
              </div>
              <button
                onClick={() => setOpenSaleDetailModal(false)}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors duration-150 cursor-pointer"
              >
                <X size={20} />
              </button>
            </div>

            {/* Scrollable Body */}
            <div className="p-6 overflow-y-auto space-y-6">

              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Umumiy Summa */}
                <div className="bg-slate-50/80 p-4 rounded-xl border border-slate-100">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Umumiy summa</p>
                  <p className="text-lg font-bold text-slate-900 mt-1">
                    {fmt(saleDetailData?.total_amount)} <span className="text-xs text-slate-500 font-normal">{saleDetailData?.currency}</span>
                  </p>
                </div>

                {/* To'langan */}
                <div className="bg-emerald-50/50 p-4 rounded-xl border border-emerald-100/60">
                  <p className="text-xs font-medium text-emerald-600 uppercase tracking-wider">To'langan</p>
                  <p className="text-lg font-bold text-emerald-700 mt-1">
                    {fmt(saleDetailData?.paid_amount)} <span className="text-xs text-emerald-600 font-normal">{saleDetailData?.currency}</span>
                  </p>
                </div>

                {/* Qarzga qolgan */}
                <div className={`p-4 rounded-xl border ${saleDetailData?.debt_amount > 0 ? 'bg-amber-50/50 border-amber-100/60' : 'bg-slate-50/80 border-slate-100'}`}>
                  <p className={`text-xs font-medium uppercase tracking-wider ${saleDetailData?.debt_amount > 0 ? 'text-amber-600' : 'text-slate-500'}`}>
                    Qarzga qolgan
                  </p>
                  <p className={`text-lg font-bold mt-1 ${saleDetailData?.debt_amount > 0 ? 'text-amber-700' : 'text-slate-700'}`}>
                    {fmt(saleDetailData?.debt_amount)} <span className="text-xs font-normal opacity-75">{saleDetailData?.currency}</span>
                  </p>
                </div>
              </div>

              {/* Items Table */}
              <div className="space-y-3">
                <h4 className="text-sm font-bold text-slate-800 uppercase tracking-wider">Mahsulotlar</h4>
                <div className="border border-slate-100 rounded-xl overflow-hidden shadow-xs">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Mahsulot</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Miqdor</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Narx</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">Jami</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-slate-100 text-sm text-slate-700">
                        {saleDetailData?.items?.map((item, index) => (
                          <tr key={index} className="hover:bg-slate-50/60 transition-colors">
                            <td className="px-4 py-3 font-medium text-slate-900">{item.product_name}</td>
                            <td className="px-4 py-3 text-right font-mono text-slate-600">{Number(item.quantity).toFixed(0)} {item.unit}</td>
                            <td className="px-4 py-3 text-right font-mono text-slate-600">{fmt(item.unit_price)}</td>
                            <td className="px-4 py-3 text-right font-semibold text-slate-900">{fmt(item.subtotal)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-slate-100 flex justify-end bg-slate-50/50 shrink-0">
              <button
                onClick={() => setOpenSaleDetailModal(false)}
                className="bg-slate-900 text-white hover:bg-slate-800 px-5 py-2.5 rounded-xl font-medium text-sm transition-all duration-150 shadow-sm active:scale-98 cursor-pointer"
              >
                Yopish
              </button>
            </div>

          </div>
        </div>
      )}

      {openPartialReturnModal && (
        <PartialReturnModal
          sale={saleDetailData}
          onClose={() => setOpenPartialReturnModal(false)}
          onSuccess={() => {
            setOpenPartialReturnModal(false);
            setOpenSaleDetailModal(false);
          }}
        />
      )}
    </div>
  )
}

function KirimTolovlar({ stats, income, loading, openEdit, handleDelete }) {
  // Pullarni chiroyli formatda chiqarish uchun yordamchi funksiya (Masalan: 1 250 000)
  const fmt = (num) => {
    return num ? Number(num).toLocaleString('uz-UZ') : '0';
  };

  // Ma'lumotlarni contagent nomi bo'yicha filtrlash
  const correct_income = income && stats
    ? income.filter(i => i.contragent === stats.name)
    : [];

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">#</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">CONTRAGENT</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">TURI</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">TO'LOV</th>
              <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500" colSpan="6">TO'LOV TURLARI</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">KIRIM MANBASI</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">KASSA</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">MA'LUMOT</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">SANA</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500">AMALLAR</th>
            </tr>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th colSpan="4"></th>
              <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">NAQD</th>
              <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">UZCARD/HUMO</th>
              <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">BANK O'TKAZMASI</th>
              <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">CLICK</th>
              <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">PAYME</th>
              <th className="px-2 py-2 text-center text-[10px] font-semibold text-slate-500 border-x border-slate-200">UZUM</th>
              <th colSpan="5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {loading ? (
              <tr>
                <td colSpan="15" className="text-center py-8 text-slate-500">
                  Yuklanmoqda...
                </td>
              </tr>
            ) : correct_income.length > 0 ? (
              correct_income.map((i, idx) => (
                <tr key={i.id || idx} className="hover:bg-slate-50 text-sm">
                  <td className="px-4 py-3 text-slate-500">{idx + 1}</td>
                  <td className="px-4 py-3 font-semibold text-blue-600">{i.contragent}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-md text-xs font-medium ${i.turi === 'Mijoz' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                      {i.turi || 'Mijoz'}
                    </span>
                  </td>
                  {/* Agar obyektingizda 'amount' o'rniga 'value' bo'lsa, i.value deb o'zgartiring */}
                  <td className="px-4 py-3 font-bold text-emerald-600">{fmt(i.amount || i.value)}</td>

                  {/* To'lov turlari bo'yicha filterlar */}
                  <td className="px-2 py-3 text-center border-x border-slate-50">{['cash', 'naqd'].includes(i.payment_type) ? fmt(i.amount || i.value) : 0}</td>
                  <td className="px-2 py-3 text-center border-x border-slate-50">{['card', 'plastik', 'uzcard', 'humo'].includes(i.payment_type) ? fmt(i.amount || i.value) : 0}</td>
                  <td className="px-2 py-3 text-center border-x border-slate-50">{['bank', 'bank_transfer'].includes(i.payment_type) ? fmt(i.amount || i.value) : 0}</td>
                  <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'click' ? fmt(i.amount || i.value) : 0}</td>
                  <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'payme' ? fmt(i.amount || i.value) : 0}</td>
                  <td className="px-2 py-3 text-center border-x border-slate-50">{i.payment_type === 'uzum' ? fmt(i.amount || i.value) : 0}</td>

                  <td className="px-4 py-3">
                    <span className="px-2 py-1 rounded-md text-xs bg-blue-50 text-blue-600 border border-blue-100">
                      {i.reference_type === 'customer_payment' ? "Qarz yopish" : i.reference_type === 'sale' ? "Sotuv" : "Ta'minotchidan qaytaruv"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600 text-xs">{i.wallet || i.name || '—'}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{i.description || '—'}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">
                    {i.created_at ? new Date(i.created_at).toLocaleString('uz-UZ') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      {i.reference_type !== 'sale' ? (
                        <>
                          <button
                            onClick={() => openEdit && openEdit(i)}
                            className="px-2 py-1 text-xs font-semibold bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg transition-colors"
                          >
                            Tahrirlash
                          </button>
                          <button
                            onClick={() => handleDelete && handleDelete(i)}
                            className="px-2 py-1 text-xs font-semibold bg-red-50 text-red-500 hover:bg-red-100 rounded-lg transition-colors"
                          >
                            O'chirish
                          </button>
                        </>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Savdo bo'limidan</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="15" className="text-center py-8 text-slate-500">
                  Ma'lumot topilmadi
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Qaytarishlar jadvali (CustomerDetail qaytarishlar tab)
// ────────────────────────────────────────────────────────────
function ReturnsTable({ rows, loading }) {
  if (loading) return <LoadingSpinner />
  if (!rows.length) return (
    <div className="flex flex-col items-center justify-center h-48 text-slate-400 gap-2">
      <svg className="w-12 h-12 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
      </svg>
      <p className="text-sm">Bu mijozdan qaytarishlar yo'q</p>
    </div>
  )

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-[700px] w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Raqam</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">To'lov turi</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Jami</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Qaytarilgan</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Sana</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Holat</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {rows.map(s => (
              <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-4 py-3 font-mono text-xs text-slate-600">{s.number}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PAY_STYLES[s.payment_type] || 'bg-slate-100 text-slate-600'}`}>
                    {PAY_LABELS[s.payment_type] || s.payment_type}
                  </span>
                </td>
                <td className="px-4 py-3 font-semibold text-slate-800">{fmt(s.total_amount)} so'm</td>
                <td className="px-4 py-3 text-emerald-600 font-medium">{fmt(s.paid_amount)} so'm</td>
                <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{fmtDate(s.created_at)}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[s.status] || ''}`}>
                    {STATUS_LABELS[s.status] || s.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────
// Mijozdan qaytarish modali
// ────────────────────────────────────────────────────────────
function CustomerReturnModal({ customerId, warehouses, wallets, onClose, onSuccess }) {
  const [products, setProducts] = useState([])
  const [prodSearch, setProdSearch] = useState('')
  const [selProd, setSelProd] = useState(null)
  const [qty, setQty] = useState('1')
  const [price, setPrice] = useState('')
  const [items, setItems] = useState([])
  const [warehouseId, setWarehouseId] = useState('')
  const [paymentType, setPaymentType] = useState('debt')
  const [walletId, setWalletId] = useState('')
  const [paidCash, setPaidCash] = useState('')
  const [paidCard, setPaidCard] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  // Mahsulotlarni yuklash
  useEffect(() => {
    api.get('/products/', { params: { limit: 5000 } })
      .then(r => setProducts(Array.isArray(r.data) ? r.data : (r.data.items || [])))
      .catch(() => { })
  }, [])

  const filtered = prodSearch.length >= 1
    ? products.filter(p =>
      p.name.toLowerCase().includes(prodSearch.toLowerCase()) ||
      (p.sku && p.sku.toLowerCase().includes(prodSearch.toLowerCase()))
    ).slice(0, 20)
    : []

  const selectProduct = (p) => {
    setSelProd(p)
    setPrice(p.sale_price ? String(p.sale_price) : '')
    setProdSearch('')
  }

  const addItem = () => {
    if (!selProd) { setErr('Mahsulot tanlang'); return }
    if (!qty || Number(qty) <= 0) { setErr('Miqdorni kiriting'); return }
    if (!price || Number(price) < 0) { setErr('Narxni kiriting'); return }
    setItems(prev => {
      const ex = prev.find(i => i.product_id === selProd.id && i.price === Number(price))
      if (ex) return prev.map(i => i.product_id === selProd.id && i.price === Number(price) ? { ...i, qty: i.qty + Number(qty) } : i)
      return [...prev, { product_id: selProd.id, name: selProd.name, unit: selProd.unit || 'dona', qty: Number(qty), price: Number(price) }]
    })
    setSelProd(null); setQty('1'); setPrice(''); setErr('')
  }

  const totalAmount = items.reduce((s, i) => s + i.qty * i.price, 0)

  const save = async () => {
    if (!items.length) { setErr("Mahsulot qo'shing"); return }
    if (!warehouseId) { setErr('Omborni tanlang'); return }
    if (paymentType !== 'debt' && !walletId) { setErr('Kassani tanlang'); return }

    let paidAmount = 0
    let pCash = 0
    let pCard = 0
    if (paymentType === 'cash') { paidAmount = totalAmount; pCash = totalAmount }
    else if (paymentType === 'card') { paidAmount = totalAmount; pCard = totalAmount }
    else if (paymentType === 'mixed') {
      pCash = Number(paidCash) || 0
      pCard = Number(paidCard) || 0
      paidAmount = pCash + pCard
      if (paidAmount > totalAmount) { setErr("Qaytarilgan summa umumiy summadan ko'p"); return }
    }

    setSaving(true); setErr('')
    try {
      await api.post('/sales/return', {
        items: items.map(i => ({ product_id: i.product_id, quantity: i.qty, unit_price: i.price, discount: 0 })),
        payment_type: paymentType,
        paid_amount: paidAmount,
        paid_cash: pCash,
        paid_card: pCard,
        discount_amount: 0,
        customer_id: Number(customerId),
        warehouse_id: Number(warehouseId),
        wallet_id: walletId ? Number(walletId) : null,
        note: note,
      })
      onSuccess()
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik yuz berdi')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-800">Mijozdan qaytarish</h2>
            <p className="text-xs text-slate-400 mt-0.5">Mahsulotlarni qo'shing va qaytarish turini tanlang</p>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Ombor tanlash */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">Ombor *</label>
            <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
              className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white">
              <option value="">Omborni tanlang...</option>
              {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>

          {/* Mahsulot qidirish */}
          <div className="relative">
            <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">Mahsulot qidirish</label>
            <input
              type="text"
              value={prodSearch}
              onChange={e => setProdSearch(e.target.value)}
              placeholder="Nomi yoki SKU bo'yicha..."
              className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            {filtered.length > 0 && (
              <div className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-xl shadow-lg max-h-48 overflow-y-auto">
                {filtered.map(p => (
                  <button key={p.id} onClick={() => selectProduct(p)}
                    className="w-full text-left px-4 py-2.5 text-sm hover:bg-blue-50 flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-800">{p.name}</span>
                    <span className="text-xs text-slate-400 shrink-0">{fmt(p.sale_price)} so'm</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {selProd && (
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 flex items-end gap-3">
              <div className="flex-1">
                <div className="text-sm font-semibold text-slate-700">{selProd.name}</div>
                <div className="text-xs text-slate-400 mt-0.5">Joriy qoldiq: {fmt(selProd.stock_quantity || 0)} {selProd.unit || 'dona'}</div>
              </div>
              <div className="flex gap-2 items-end">
                <div>
                  <label className="text-xs text-slate-500 block mb-1">Miqdor</label>
                  <input type="number" min="0.001" step="any" value={qty} onChange={e => setQty(e.target.value)}
                    className="w-20 border border-slate-200 rounded-lg px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-300" />
                </div>
                <div>
                  <label className="text-xs text-slate-500 block mb-1">Narx (so'm)</label>
                  <input type="number" min="0" step="any" value={price} onChange={e => setPrice(e.target.value)}
                    className="w-32 border border-slate-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" />
                </div>
                <button onClick={addItem}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors">
                  Qo'sh
                </button>
              </div>
            </div>
          )}

          {/* Items jadvali */}
          {items.length > 0 && (
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs text-slate-500">Mahsulot</th>
                    <th className="px-3 py-2 text-center text-xs text-slate-500">Soni</th>
                    <th className="px-3 py-2 text-right text-xs text-slate-500">Narx</th>
                    <th className="px-3 py-2 text-right text-xs text-slate-500">Jami</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((it, i) => (
                    <tr key={i}>
                      <td className="px-3 py-2 font-medium">{it.name}</td>
                      <td className="px-3 py-2 text-center">{it.qty} {it.unit}</td>
                      <td className="px-3 py-2 text-right">{fmt(it.price)}</td>
                      <td className="px-3 py-2 text-right font-bold text-blue-700">{fmt(it.qty * it.price)}</td>
                      <td className="px-2 py-2">
                        <button onClick={() => setItems(p => p.filter((_, idx) => idx !== i))}
                          className="text-slate-300 hover:text-red-500 transition-colors">✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-50">
                  <tr>
                    <td colSpan={3} className="px-3 py-2 text-xs text-slate-500 font-semibold">Jami qaytarilayotgan:</td>
                    <td className="px-3 py-2 text-right font-bold text-blue-700">{fmt(totalAmount)} so'm</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {/* Qaytarish turi */}
          {items.length > 0 && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">Qaytarish turi</label>
                <select value={paymentType} onChange={e => setPaymentType(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white">
                  <option value="debt">Qarzdan chegirish</option>
                  <option value="cash">Naqd pul qaytarish</option>
                  <option value="card">Plastik kartaga qaytarish</option>
                  <option value="mixed">Aralash qaytarish</option>
                </select>
              </div>

              {paymentType === 'mixed' && (
                <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3 rounded-xl border border-slate-200">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Naqd</label>
                    <input type="number" min="0" value={paidCash} onChange={e => setPaidCash(e.target.value)}
                      className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" placeholder="0" />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Karta</label>
                    <input type="number" min="0" value={paidCard} onChange={e => setPaidCard(e.target.value)}
                      className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" placeholder="0" />
                  </div>
                </div>
              )}

              {paymentType !== 'debt' && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">Kassadan chiqim *</label>
                  <select value={walletId} onChange={e => setWalletId(e.target.value)}
                    className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white">
                    <option value="">Kassani tanlang...</option>
                    {wallets.map(w => <option key={w.id} value={w.id}>{w.name} ({fmt(w.balance)} so'm)</option>)}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5">Izoh (ixtiyoriy)</label>
                <input type="text" value={note} onChange={e => setNote(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder="Qaytarish sababi..." />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex items-center justify-between">
          <div>
            {err && <span className="text-red-500 text-sm font-medium">{err}</span>}
          </div>
          <div className="flex gap-3">
            <button onClick={onClose}
              className="px-4 py-2 text-sm font-semibold text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
              Bekor qilish
            </button>
            <button onClick={save} disabled={saving || !items.length}
              className="px-5 py-2 bg-red-500 hover:bg-red-600 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-all active:scale-95 flex items-center gap-2">
              {saving ? (
                <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block" /> Saqlanmoqda...</>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                  </svg>
                  Qaytarishni saqlash
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function LoadingSpinner() {
  const { t } = useLang();
  return (
    <div className="flex items-center justify-center h-32">
      <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

function Empty({ text }) {
  const { t } = useLang();
  return (
    <div className="flex flex-col items-center justify-center h-32 text-slate-400">
      <svg className="w-10 h-10 mb-2 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
      <p className="text-sm">{text}</p>
    </div>
  )
}