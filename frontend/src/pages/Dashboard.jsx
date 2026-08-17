import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../api/axios'
import toast from 'react-hot-toast';
import ECodeLogo from '../components/ECodeLogo'

const roleLabels = {
  admin: 'Admin',
  director: 'Direktor',
  manager: 'Menejer',
  cashier: 'Kassir',
  warehouse: 'Ombor',
  accountant: 'Buxgalter',
}

const fmt = (n) => Number(n || 0).toLocaleString('ru-RU');
const fmtDate = (d) => {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expiringBatches, setExpiringBatches] = useState([])
  const [expiryLoading, setExpiryLoading] = useState(true)

  useEffect(() => {
    api.get('/reports/dashboard')
      .then(res => setStats(res.data))
      .catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
      .finally(() => setLoading(false))

    api.get('/inventory/expiring-batches')
      .then(res => setExpiringBatches(res.data || []))
      .catch(() => {})
      .finally(() => setExpiryLoading(false))
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const expiredCount = expiringBatches.filter(b => b.is_expired).length;
  const criticalCount = expiringBatches.filter(b => !b.is_expired && b.days_left <= 7).length;
  const topExpiring = expiringBatches.slice(0, 5);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <ECodeLogo size={32} showText={true} />
            </div>

            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-sm font-medium text-gray-800">{user?.full_name}</p>
                <p className="text-xs text-gray-500">{roleLabels[user?.role] || user?.role}</p>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 text-sm text-red-600 hover:text-red-700 font-medium transition"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                Chiqish
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Bugungi holat</p>
        </div>

        {/* Expiry Alert Banner */}
        {!expiryLoading && (expiredCount > 0 || criticalCount > 0) && (
          <div
            onClick={() => navigate('/admin/alerts')}
            className="mb-6 bg-gradient-to-r from-red-500 to-blue-600 rounded-2xl p-4 flex items-center justify-between cursor-pointer hover:from-red-600 hover:to-blue-700 transition-all shadow-lg shadow-red-200"
          >
            <div className="flex items-center gap-3 text-white">
              <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
                    d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
              </div>
              <div>
                <p className="font-black text-sm">
                  {expiredCount > 0 && `${expiredCount} ta mahsulot muddati o'tgan!`}
                  {expiredCount > 0 && criticalCount > 0 && ' • '}
                  {criticalCount > 0 && `${criticalCount} ta mahsulot 7 kun ichida tugaydi`}
                </p>
                <p className="text-red-100 text-xs mt-0.5">Darhol ko'rish uchun bosing</p>
              </div>
            </div>
            <svg className="w-5 h-5 text-white/70 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <svg className="animate-spin h-8 w-8 text-blue-600" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
          </div>
        ) : (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <StatCard
                title="Bugungi savdo"
                value={stats ? `${Number(stats.today_revenue).toLocaleString()} so'm` : '—'}
                sub={`${stats?.today_orders ?? 0} ta buyurtma`}
                color="blue"
                icon={
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 13v-1m0 0c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                }
              />
              <StatCard
                title="Jami mahsulot"
                value={stats?.total_products ?? '—'}
                sub="aktiv mahsulotlar"
                color="green"
                icon={
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                }
              />
              <StatCard
                title="Kam qolgan"
                value={stats?.low_stock_count ?? '—'}
                sub="minimal zahiradan past"
                color="yellow"
                icon={
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                }
              />
              <div
                onClick={() => navigate('/admin/alerts')}
                className={`rounded-2xl shadow-sm p-5 cursor-pointer transition-all hover:shadow-md ${
                  expiredCount + criticalCount > 0
                    ? 'bg-gradient-to-br from-red-500 to-blue-600'
                    : 'bg-white'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <p className={`text-sm ${expiredCount + criticalCount > 0 ? 'text-red-100' : 'text-gray-500'}`}>
                    Yaroqlilik muddati
                  </p>
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${expiredCount + criticalCount > 0 ? 'bg-white/20' : 'bg-red-100'}`}>
                    <svg className={`w-5 h-5 ${expiredCount + criticalCount > 0 ? 'text-white' : 'text-red-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                    </svg>
                  </div>
                </div>
                <p className={`text-2xl font-bold ${expiredCount + criticalCount > 0 ? 'text-white' : 'text-gray-800'}`}>
                  {expiryLoading ? '...' : (expiredCount + criticalCount)}
                </p>
                <p className={`text-xs mt-1 ${expiredCount + criticalCount > 0 ? 'text-red-100' : 'text-gray-400'}`}>
                  {expiredCount + criticalCount > 0 ? "Ko'rish uchun bosing →" : 'Barcha muddatlar joyida'}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Top Products */}
              {stats?.top_products?.length > 0 && (
                <div className="bg-white rounded-2xl shadow-sm p-6">
                  <h2 className="text-lg font-semibold text-gray-800 mb-4">Top mahsulotlar (bugun)</h2>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-3 font-medium">#</th>
                          <th className="pb-3 font-medium">Mahsulot</th>
                          <th className="pb-3 font-medium text-right">Soni</th>
                          <th className="pb-3 font-medium text-right">Summa</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {stats.top_products.map((p, i) => (
                          <tr key={p.product_id} className="hover:bg-gray-50">
                            <td className="py-3 text-gray-400">{i + 1}</td>
                            <td className="py-3 font-medium text-gray-800">{p.name}</td>
                            <td className="py-3 text-right text-gray-600">{p.total_qty}</td>
                            <td className="py-3 text-right font-semibold text-gray-800">
                              {Number(p.total_revenue).toLocaleString()} so'm
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Expiring Products Widget */}
              {!expiryLoading && topExpiring.length > 0 && (
                <div className="bg-white rounded-2xl shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-800">Muddati tugayotganlar</h2>
                    <button
                      onClick={() => navigate('/admin/alerts')}
                      className="text-xs text-blue-600 font-bold hover:underline"
                    >
                      Barchasini ko'rish →
                    </button>
                  </div>
                  <div className="space-y-2">
                    {topExpiring.map(b => (
                      <div key={b.batch_id} className={`flex items-center justify-between p-3 rounded-xl ${b.is_expired ? 'bg-red-50' : b.days_left <= 7 ? 'bg-orange-50' : 'bg-amber-50'}`}>
                        <div className="min-w-0 flex-1">
                          <div className="font-semibold text-sm text-gray-800 truncate">{b.product_name}</div>
                          <div className="text-xs text-gray-500 mt-0.5">Muddat: {fmtDate(b.expiry_date)} • {fmt(b.quantity)} dona</div>
                        </div>
                        <div className={`ml-3 text-xs font-bold px-2 py-1 rounded-lg flex-shrink-0 ${
                          b.is_expired ? 'bg-red-100 text-red-700' :
                          b.days_left <= 7 ? 'bg-orange-100 text-orange-700' :
                          'bg-amber-100 text-amber-700'
                        }`}>
                          {b.is_expired ? "O'tgan" : `${b.days_left} kun`}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Admin links */}
            {(user?.role === 'admin' || user?.role === 'director') && (
              <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
                <button
                  onClick={() => navigate('/users/create')}
                  className="bg-white rounded-2xl shadow-sm p-5 flex items-center gap-4 hover:shadow-md transition text-left"
                >
                  <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">
                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-semibold text-gray-800">Foydalanuvchi qo'shish</p>
                    <p className="text-xs text-gray-500 mt-0.5">Yangi xodim ro'yxatdan o'tkazish</p>
                  </div>
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

function StatCard({ title, value, sub, color, icon }) {
  const colors = {
    blue: 'bg-blue-100 text-blue-600',
    green: 'bg-green-100 text-green-600',
    yellow: 'bg-yellow-100 text-yellow-600',
    purple: 'bg-blue-100 text-blue-600',
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-gray-500">{title}</p>
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${colors[color]}`}>
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {icon}
          </svg>
        </div>
      </div>
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      <p className="text-xs text-gray-400 mt-1">{sub}</p>
    </div>
  )
}
