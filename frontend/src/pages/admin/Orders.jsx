import { useState, useEffect } from 'react';
import api from '../../api/axios';
import toast from 'react-hot-toast';
import { CheckCircle, Clock, Truck, AlertCircle, X, Package, Download } from 'lucide-react';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const STATUS_COLORS = {
  pending: { bg: 'bg-yellow-50', text: 'text-yellow-700', icon: Clock, label: 'Kutilmoqda' },
  confirmed: { bg: 'bg-blue-50', text: 'text-blue-700', icon: CheckCircle, label: 'Tasdiqlangan' },
  preparing: { bg: 'bg-indigo-50', text: 'text-indigo-700', icon: Package, label: 'Tayyorlanmoqda' },
  assigned: { bg: 'bg-purple-50', text: 'text-purple-700', icon: Truck, label: 'Kuryerda' },
  on_way: { bg: 'bg-orange-50', text: 'text-orange-700', icon: Truck, label: "Yo'lda" },
  delivered: { bg: 'bg-green-50', text: 'text-green-700', icon: Truck, label: 'Yetkazildi' },
  cancelled: { bg: 'bg-red-50', text: 'text-red-700', icon: AlertCircle, label: 'Bekor qilindi' },
};

export default function Orders({ embedded = false }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('pending');
  const [detailGroup, setDetailGroup] = useState(null);

  useEffect(() => {
    loadOrders();
  }, [filter]);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/orders', {
        params: { status: filter }
      });
      setGroups(data);
    } catch (err) {
      toast.error('Buyurtmalarni yuklashda xatolik');
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (groupId, newStatus) => {
    try {
      await api.put(`/orders/group/${groupId}/status`, { status: newStatus });
      toast.success(`Status yangilandi: ${STATUS_COLORS[newStatus]?.label || newStatus}`);
      setDetailGroup(null);
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yangilashda xatolik');
    }
  };

  const statusOptions = [
    { value: 'pending', label: '⏳ Kutilmoqda' },
    { value: 'confirmed', label: '✅ Tasdiqlangan' },
    { value: 'preparing', label: '📦 Tayyorlanmoqda' },
    { value: 'on_way', label: "🛵 Yo'lda" },
    { value: 'delivered', label: '🚚 Yetkazildi' },
  ];

  // Statusdan keyingi mumkin bo'lgan qadam(lar) — tugmalar shu oqimdan chiqadi
  const NEXT_STEPS = {
    pending: [{ to: 'confirmed', label: 'Tasdiqlash', cls: 'bg-green-100 text-green-700 hover:bg-green-200' }],
    confirmed: [
      { to: 'preparing', label: 'Tayyorlash', cls: 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200' },
      { to: 'delivered', label: 'Yetkazildi', cls: 'bg-blue-100 text-blue-700 hover:bg-blue-200' },
    ],
    preparing: [
      { to: 'on_way', label: "Yo'lga chiqdi", cls: 'bg-orange-100 text-orange-700 hover:bg-orange-200' },
      { to: 'delivered', label: 'Yetkazildi', cls: 'bg-blue-100 text-blue-700 hover:bg-blue-200' },
    ],
    assigned: [
      { to: 'on_way', label: "Yo'lga chiqdi", cls: 'bg-orange-100 text-orange-700 hover:bg-orange-200' },
      { to: 'delivered', label: 'Yetkazildi', cls: 'bg-blue-100 text-blue-700 hover:bg-blue-200' },
    ],
    on_way: [{ to: 'delivered', label: 'Yetkazildi', cls: 'bg-blue-100 text-blue-700 hover:bg-blue-200' }],
  };

  const exportExcel = async () => {
    if (!groups.length) {
      toast.error('Eksport qilish uchun buyurtma topilmadi');
      return;
    }
    const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
    const rows = [];
    groups.forEach(group => {
      group.items.forEach(item => {
        rows.push({
          'Mijoz': group.customer_name,
          'Telefon': group.customer_phone,
          'Mahsulot': item.product_name,
          'Miqdor': item.quantity,
          'Narx': Number(item.unit_price),
          'Jami': Number(item.total_amount),
          'Status': STATUS_COLORS[group.status]?.label || group.status,
          "To'lov turi": group.payment_type || '',
          'Izoh': group.notes || '',
          'Sana': new Date(group.created_at).toLocaleString('uz-UZ'),
        });
      });
    });
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Buyurtmalar');
    const today = new Date().toISOString().slice(0, 10);
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `buyurtmalar_${today}.xlsx`);
  };

  return (
    <div className={embedded ? '' : 'p-6 bg-slate-50 min-h-screen'}>
      <div className={embedded ? '' : 'max-w-7xl mx-auto'}>
        {/* Header */}
        {!embedded && (
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-slate-800">📦 Buyurtmalar</h1>
            <p className="text-slate-600 mt-1">Pelanggan buyurtmalarini boshqarish</p>
          </div>
        )}

        {/* Filter */}
        <div className="mb-6 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex gap-2">
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
          <button
            onClick={exportExcel}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-lg border border-emerald-200 transition-colors"
          >
            <Download className="w-4 h-4" />
            Excelga eksport
          </button>
        </div>

        {/* Orders Table */}
        <div className="bg-white rounded-xl shadow overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-slate-500">
              Yuklanimoqda...
            </div>
          ) : groups.length === 0 ? (
            <div className="p-8 text-center text-slate-500">
              Buyurtmalar topilmadi
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Mijoz</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Mahsulotlar</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Jami narx</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Status</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Vaqt</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-slate-700">Amal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {groups.map(group => {
                    const StatusIcon = STATUS_COLORS[group.status]?.icon || Clock;
                    const colors = STATUS_COLORS[group.status];
                    const itemsCount = group.items.length;
                    return (
                      <tr
                        key={group.group_id}
                        className="hover:bg-slate-50 transition-colors cursor-pointer"
                        onClick={() => setDetailGroup(group)}
                      >
                        <td className="px-6 py-4 text-sm">
                          <div className="font-medium text-slate-800">{group.customer_name}</div>
                          <div className="text-xs text-slate-500">{group.customer_phone}</div>
                          <div className="text-[11px] mt-0.5 font-medium text-slate-400">
                            {group.delivery_type === 'delivery' ? '🚚 Yetkazib berish' : '🏬 Olib ketish'}
                          </div>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-800">
                          {itemsCount === 1 ? (
                            <span>{group.items[0].product_name} <span className="text-slate-400">× {group.items[0].quantity}</span></span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-blue-600 font-medium">
                              <Package className="w-3.5 h-3.5" /> {itemsCount} ta mahsulot
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-sm font-medium text-slate-800">{fmt(group.total_amount)} so'm</td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${colors?.bg} ${colors?.text}`}>
                            <StatusIcon className="w-4 h-4" />
                            {colors?.label}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-600">
                          {new Date(group.created_at).toLocaleDateString('uz-UZ')}
                        </td>
                        <td className="px-6 py-4" onClick={e => e.stopPropagation()}>
                          <div className="flex flex-wrap gap-1.5">
                            {(NEXT_STEPS[group.status] || []).map(step => (
                              <button
                                key={step.to}
                                onClick={() => updateStatus(group.group_id, step.to)}
                                className={`px-3 py-1 rounded text-sm transition-colors ${step.cls}`}
                              >
                                {step.label}
                              </button>
                            ))}
                          </div>
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
              {groups.filter(g => g.status === 'pending').length}
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-slate-600 mb-1">✅ Tasdiqlangan</div>
            <div className="text-2xl font-bold text-blue-600">
              {groups.filter(g => g.status === 'confirmed').length}
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-slate-600 mb-1">🚚 Yetkazildi</div>
            <div className="text-2xl font-bold text-green-600">
              {groups.filter(g => g.status === 'delivered').length}
            </div>
          </div>
        </div>
      </div>

      {/* Detail modal */}
      {detailGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDetailGroup(null)} />
          <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-100">
              <div>
                <h2 className="text-lg font-bold text-slate-800">{detailGroup.customer_name}</h2>
                <p className="text-xs text-slate-500">{detailGroup.customer_phone}</p>
              </div>
              <button onClick={() => setDetailGroup(null)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
              {detailGroup.items.map(item => (
                <div key={item.id} className="flex items-center justify-between border border-slate-100 rounded-xl px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-800">{item.product_name}</p>
                    <p className="text-xs text-slate-400">{fmt(item.unit_price)} so'm × {item.quantity}</p>
                  </div>
                  <p className="text-sm font-semibold text-slate-800">{fmt(item.total_amount)} so'm</p>
                </div>
              ))}
            </div>

            <div className="px-6 py-4 border-t border-slate-100">
              {/* Yetkazib berish ma'lumotlari */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-500">Turi</span>
                <span className="text-sm font-medium text-slate-700">
                  {detailGroup.delivery_type === 'delivery' ? '🚚 Yetkazib berish' : '🏬 Olib ketish'}
                </span>
              </div>
              {detailGroup.delivery_type === 'delivery' && (
                <>
                  {detailGroup.delivery_address && (
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <span className="text-sm text-slate-500 shrink-0">Manzil</span>
                      <span className="text-sm text-slate-700 text-right">
                        {detailGroup.delivery_address}
                        {detailGroup.delivery_lat && detailGroup.delivery_lng && (
                          <a
                            href={`https://maps.google.com/?q=${detailGroup.delivery_lat},${detailGroup.delivery_lng}`}
                            target="_blank" rel="noreferrer"
                            className="ml-2 text-blue-500 hover:underline whitespace-nowrap"
                          >📍 Xaritada</a>
                        )}
                      </span>
                    </div>
                  )}
                  {detailGroup.contact_phone && (
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-slate-500">Aloqa tel</span>
                      <a href={`tel:${detailGroup.contact_phone}`} className="text-sm text-blue-600 hover:underline">{detailGroup.contact_phone}</a>
                    </div>
                  )}
                  {Number(detailGroup.delivery_fee) > 0 && (
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-slate-500">Yetkazish haqi</span>
                      <span className="text-sm text-slate-700">+{fmt(detailGroup.delivery_fee)} so'm</span>
                    </div>
                  )}
                </>
              )}
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-slate-500">Jami</span>
                <span className="text-lg font-bold text-slate-800">
                  {fmt(Number(detailGroup.total_amount) + (detailGroup.delivery_type === 'delivery' ? Number(detailGroup.delivery_fee || 0) : 0))} so'm
                </span>
              </div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-slate-500">Sana</span>
                <span className="text-sm text-slate-700">{new Date(detailGroup.created_at).toLocaleString('uz-UZ')}</span>
              </div>
              <div className="flex gap-2">
                {(NEXT_STEPS[detailGroup.status] || []).map(step => (
                  <button
                    key={step.to}
                    onClick={() => updateStatus(detailGroup.group_id, step.to)}
                    className={`flex-1 py-2.5 rounded-xl font-semibold text-sm transition-colors ${step.cls}`}
                  >
                    {step.label}
                  </button>
                ))}
                {(detailGroup.status === 'delivered' || detailGroup.status === 'cancelled') && (
                  <span className={`flex-1 py-2.5 text-center rounded-xl font-semibold text-sm ${STATUS_COLORS[detailGroup.status]?.bg} ${STATUS_COLORS[detailGroup.status]?.text}`}>
                    {STATUS_COLORS[detailGroup.status]?.label}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
