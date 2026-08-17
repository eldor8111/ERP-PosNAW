import React, { useState, useEffect } from 'react';
import { X, Check } from 'lucide-react';
import api from '../../api/axios';
import { toast } from 'react-hot-toast';

function fmt(n) {
  if (!n) return '0';
  return Number(n).toLocaleString('ru-RU');
}

export default function PartialReturnModal({ sale, onClose, onSuccess }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [paymentType, setPaymentType] = useState('cash');

  useEffect(() => {
    if (sale && sale.items) {
      setItems(sale.items.map(item => ({
        ...item,
        returnQty: 0,
        maxReturn: item.quantity - (item.returned_quantity || 0)
      })));
    }
  }, [sale]);

  const handleQtyChange = (index, val) => {
    const newItems = [...items];
    let qty = Number(val);
    if (qty < 0) qty = 0;
    if (qty > newItems[index].maxReturn) qty = newItems[index].maxReturn;
    newItems[index].returnQty = qty;
    setItems(newItems);
  };

  const calculateTotalRefund = () => {
    return items.reduce((sum, item) => {
      const avgPrice = item.subtotal / item.quantity;
      return sum + (avgPrice * item.returnQty);
    }, 0);
  };

  const submitReturn = async () => {
    const returnItems = items
      .filter(item => item.returnQty > 0)
      .map(item => ({
        sale_item_id: item.id,
        quantity: item.returnQty
      }));

    if (returnItems.length === 0) {
      toast.error('Qaytariladigan tovarlar tanlanmadi');
      return;
    }

    setLoading(true);
    try {
      await api.post(`/sales/${sale.id}/return-items`, {
        items: returnItems,
        payment_type: paymentType,
        note: "Qisman qaytarish (Sotuvlar tarixi orqali)"
      });
      toast.success('Muvaffaqiyatli qaytarildi');
      onSuccess();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setLoading(false);
    }
  };

  const curr = sale?.currency_code || sale?.currency || 'UZS';
  const currLabel = curr === 'USD' ? '$' : "so'm";
  const totalRefund = calculateTotalRefund();

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm z-[60] p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white shrink-0">
          <div>
            <h3 className="text-xl font-bold text-slate-800">Qisman qaytarish (Sotuv #{sale?.number})</h3>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors duration-150">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          <div className="border border-slate-100 rounded-xl overflow-hidden shadow-xs">
            <table className="min-w-full divide-y divide-slate-100">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Mahsulot</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">Sotilgan</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">Narx</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">Qaytarish miqdori</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">Qaytarish summasi</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-100 text-sm">
                {items.map((item, idx) => {
                  const avgPrice = item.subtotal / item.quantity;
                  const itemRefund = avgPrice * item.returnQty;
                  return (
                    <tr key={item.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-900">{item.product_name}</td>
                      <td className="px-4 py-3 text-right text-slate-600 font-mono">
                        {fmt(item.quantity)} {item.unit}
                        {item.returned_quantity > 0 && (
                          <div className="text-[10px] text-red-500 font-semibold">Qaytarilgan: {fmt(item.returned_quantity)}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-600 font-mono">{fmt(avgPrice)} {currLabel}</td>
                      <td className="px-4 py-3 text-right">
                        <input
                          type="number"
                          min="0"
                          max={item.maxReturn}
                          value={item.returnQty || ''}
                          onChange={(e) => handleQtyChange(idx, e.target.value)}
                          disabled={item.maxReturn <= 0}
                          className="w-24 px-2 py-1 border border-slate-200 rounded text-right focus:outline-none focus:border-blue-400"
                        />
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-blue-600 font-mono">
                        {fmt(itemRefund)} {currLabel}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between bg-slate-50 p-4 rounded-xl border border-slate-100">
            <div className="flex gap-4 items-center">
              <span className="text-sm font-semibold text-slate-700">Qaytarish turi:</span>
              <select
                value={paymentType}
                onChange={(e) => setPaymentType(e.target.value)}
                className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 bg-white"
              >
                <option value="cash">Naqd pul qaytarish (Kassadan)</option>
                <option value="debt">Qarzdan chegirish (Mijoz balansi)</option>
              </select>
            </div>
            <div className="text-right">
              <span className="text-sm text-slate-500 uppercase tracking-wider font-semibold block mb-1">Jami qaytarilmoqda</span>
              <span className="text-2xl font-bold text-slate-900">{fmt(totalRefund)} {currLabel}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 bg-white shrink-0">
          <button onClick={onClose} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-xl transition-colors">
            Bekor qilish
          </button>
          <button
            onClick={submitReturn}
            disabled={loading || totalRefund <= 0}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors flex items-center gap-2"
          >
            {loading ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span> : <Check size={18} />}
            Tasdiqlash
          </button>
        </div>
      </div>
    </div>
  );
}
