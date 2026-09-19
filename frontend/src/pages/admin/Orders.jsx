import { useState, useEffect } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { CheckCircle, Clock, Truck, AlertCircle } from 'lucide-react';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const STATUS_COLORS = {
  pending: { bg: 'bg-yellow-50', text: 'text-yellow-700', icon: Clock },
  confirmed: { bg: 'bg-blue-50', text: 'text-blue-700', icon: CheckCircle },
  delivered: { bg: 'bg-green-50', text: 'text-green-700', icon: Truck },
  cancelled: { bg: 'bg-red-50', text: 'text-red-700', icon: AlertCircle },
};

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('pending');

  useEffect(() => {
    loadOrders();
  }, [filter]);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/orders', {
        params: { status: filter }
      });
      setOrders(data);
    } catch (err) {
      toast.error('Buyurtmalarni yuklashda xatolik');
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (orderId, newStatus) => {
    try {
      await api.put(`/orders/${orderId}/confirm`);
      toast.success(newStatus === 'confirmed' ? 'Buyurtma tasdiqlandi' : 'Status yangilandi');
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yangilashda xatolik');
    }
  };

  const statusOptions = [
    { value: 'pending', label: '⏳ Kutilmoqda' },
    { value: 'confirmed', label: '✅ Tasdiqlangan' },
    { value: 'delivered', label: '🚚 Yetkazildi' },
  ];

  return (
    <div className="p-6 bg-slate-50 min-h-screen">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-slate-800">📦 Buyurtmalar</h1>
          <p className="text-slate-600 mt-1">Pelanggan buyurtmalarini boshqarish</p>
        </div>

        {/* Filter */}
        <div className="mb-6 flex gap-2">
          {statusOptions.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                filter === opt.value
                  ? 'bg-blue-500 text-white'
                  : 'bg-white text-slate-700 hover:bg-slate-100'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Orders Table */}
        <div className="bg-white rounded-xl shadow overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-slate-500">
              Yuklanimoqda...
            </div>
          ) : orders.length === 0 ? (
            <div className="p-8 text-center text-slate-500">
              Buyurtmalar topilmadi
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">ID</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Mijoz</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Mahsulot</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Miqdor</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Narx</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Status</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Vaqt</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Amal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {orders.map(order => {
                    const StatusIcon = STATUS_COLORS[order.status]?.icon || Clock;
                    const colors = STATUS_COLORS[order.status];
                    return (
                      <tr key={order.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-6 py-4 text-sm font-medium text-slate-800">#{order.id}</td>
                        <td className="px-6 py-4 text-sm">
                          <div className="font-medium text-slate-800">{order.customer_name}</div>
                          <div className="text-xs text-slate-500">{order.customer_phone}</div>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-800">{order.product_name}</td>
                        <td className="px-6 py-4 text-sm text-slate-800">{order.quantity}</td>
                        <td className="px-6 py-4 text-sm font-medium text-slate-800">{fmt(order.total_amount)} so'm</td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${colors?.bg} ${colors?.text}`}>
                            <StatusIcon className="w-4 h-4" />
                            {order.status === 'pending' && 'Kutilmoqda'}
                            {order.status === 'confirmed' && 'Tasdiqlangan'}
                            {order.status === 'delivered' && 'Yetkazildi'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-600">
                          {new Date(order.created_at).toLocaleDateString('uz-UZ')}
                        </td>
                        <td className="px-6 py-4">
                          {order.status === 'pending' && (
                            <button
                              onClick={() => updateStatus(order.id, 'confirmed')}
                              className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm hover:bg-green-200 transition-colors"
                            >
                              Tasdiqlash
                            </button>
                          )}
                          {order.status === 'confirmed' && (
                            <button
                              onClick={() => updateStatus(order.id, 'delivered')}
                              className="px-3 py-1 bg-blue-100 text-blue-700 rounded text-sm hover:bg-blue-200 transition-colors"
                            >
                              Yetkazildi
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-slate-600 mb-1">⏳ Kutilmoqda</div>
            <div className="text-2xl font-bold text-yellow-600">
              {orders.filter(o => o.status === 'pending').length}
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-slate-600 mb-1">✅ Tasdiqlangan</div>
            <div className="text-2xl font-bold text-blue-600">
              {orders.filter(o => o.status === 'confirmed').length}
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-slate-600 mb-1">🚚 Yetkazildi</div>
            <div className="text-2xl font-bold text-green-600">
              {orders.filter(o => o.status === 'delivered').length}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
