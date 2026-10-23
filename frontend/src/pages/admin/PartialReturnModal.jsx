import React, { useState, useEffect, useRef } from 'react';
import { X, Check } from 'lucide-react';
import api from '../../api/axios';
import { toast } from 'react-hot-toast';
import { getReceiptSettings, buildReceiptHtml, printReceiptHtml } from '../../utils/receiptBuilder';
import { useLang } from '../../context/LangContext';
import { useApprovalFlow, ApprovalModal } from './Approvals'; // T4.6: menejer tasdig'i
import useCompanyFeatures from '../../hooks/useCompanyFeatures';
import { tOr } from '../../utils/shiftBalances';

function fmt(n) {
  if (!n) return '0';
  return Number(n).toLocaleString('ru-RU');
}

export default function PartialReturnModal({ sale, onClose, onSuccess }) {
  const { t } = useLang();
  const tf = (k, fb) => tOr(t, k, fb);
  // D1.4: dorixona rejimida asl partiyasi yo'q qator uchun seriya va muddat kiritiladi (modul o'chiq bo'lsa — o'zgarmaydi)
  const features = useCompanyFeatures();
  const pharmacy = !!features?.pharmacy;
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchingItems, setFetchingItems] = useState(false);
  const [paymentType, setPaymentType] = useState('cash');
  const [printReceipt, setPrintReceipt] = useState(true);

  useEffect(() => {
    if (!sale) return;
    if (sale.items && sale.items.length > 0) {
      // Items already loaded (e.g. from cart)
      setItems(sale.items.map(item => ({
        ...item,
        returnQty: 0,
        maxReturn: item.quantity - (item.returned_quantity || 0)
      })));
    } else {
      // Fetch full sale details from API
      setFetchingItems(true);
      api.get(`/sales/${sale.id}`)
        .then(res => {
          const saleData = res.data;
          const saleItems = saleData.items || saleData.sale_items || [];
          setItems(saleItems.map(item => ({
            ...item,
            returnQty: 0,
            maxReturn: item.quantity - (item.returned_quantity || 0)
          })));
        })
        .catch(() => {
          toast.error(t('partialReturn.loadError'));
        })
        .finally(() => setFetchingItems(false));
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

  const handleLotChange = (index, field, val) => {
    setItems(prev => prev.map((it, i) => (i === index ? { ...it, [field]: val } : it)));
  };

  // Asl partiya yo'q qator: serverdan 400 kelgan (needLot) yoki sotuv qatorida batches bo'sh massiv
  const rowNeedsLot = (item) => pharmacy && item.returnQty > 0
    && (item.needLot || (Array.isArray(item.batches) && item.batches.length === 0));

  const calculateTotalRefund = () => {
    return items.reduce((sum, item) => {
      const avgPrice = item.subtotal / item.quantity;
      return sum + (avgPrice * item.returnQty);
    }, 0);
  };

  // Bir urinish uchun bitta kalit: sekin tarmoqda qayta bosilsa server dublikat yaratmaydi
  const idemKeyRef = useRef(null);

  const submitReturn = async (approvalId = null) => {
    const returnItems = items
      .filter(item => item.returnQty > 0)
      .map(item => ({
        sale_item_id: item.id,
        quantity: item.returnQty,
        // D1.4: faqat dorixona rejimida va kiritilgan bo'lsa
        ...(pharmacy && item.lot_number && String(item.lot_number).trim() ? { lot_number: String(item.lot_number).trim() } : {}),
        ...(pharmacy && item.expiry_date ? { expiry_date: item.expiry_date } : {}),
      }));

    if (returnItems.length === 0) {
      toast.error(t('partialReturn.noItemsSelected'));
      return;
    }
    // D1.4: seriya/muddat so'ralgan qatorlar to'ldirilmaguncha yuborilmaydi
    if (items.some(it => rowNeedsLot(it) && (!String(it.lot_number || '').trim() || !it.expiry_date))) {
      toast.error(tf('pharmacyReturn.lotRequired', "Seriya raqami va yaroqlilik muddatini kiriting"));
      return;
    }

    setLoading(true);
    try {
      const payload = {
        items: returnItems,
        payment_type: paymentType,
        note: t('partialReturn.title', { number: sale.number }),
        // T4.6: limitdan katta qaytarish uchun menejer tasdiqlagan so'rov
        approval_id: approvalId || undefined,
      };

      if (!idemKeyRef.current) {
        idemKeyRef.current = (typeof crypto !== 'undefined' && crypto.randomUUID)
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      }
      const resp = await api.post(`/sales/${sale.id}/return-items`, payload, { headers: { 'Idempotency-Key': idemKeyRef.current }, _suppressToast: true });
      const saved = resp?.data;
      idemKeyRef.current = null;

      if (printReceipt) {
        try {
          const posSettings = JSON.parse(localStorage.getItem('pos_desktop_settings') || '{}');
          const settings = getReceiptSettings();
          const templateType = posSettings.template || (posSettings.paper === '58mm' ? '58' : '80');
          const tmplCfg = settings['r' + templateType] || settings[templateType] || {};
          const currCode = sale?.currency_code || sale?.currency || 'UZS';
          const returnedItems = items.filter(i => i.returnQty > 0).map(i => {
            const avgPrice = i.subtotal / i.quantity;
            return {
              product_name: i.product_name,
              quantity: i.returnQty,
              unit_price: avgPrice,
              discount: 0,
              subtotal: avgPrice * i.returnQty,
              currency_code: currCode,
            };
          });
          const totalRefund = returnedItems.reduce((s, i) => s + i.subtotal, 0);
          const meta = {
            id: 'Vazvrat-' + Date.now(),
            number: t('partialReturn.receiptTitle', { number: sale.number }),
            cashier_name: t('partialReturn.cashierLabel'),
            created_at: new Date().toISOString(),
            total_amount: totalRefund,
            paid_amount: paymentType === 'debt' ? 0 : totalRefund,
            discount_amount: 0,
            payment_types_array: [{ type: paymentType, amount: totalRefund }],
            items: returnedItems,
            customer_name: sale?.customer_name || undefined,
            // T3.7: asl sotuv filialining rekvizitlari (SaleOut dan)
            branch_name: sale?.branch_name,
            branch_address: sale?.branch_address,
            branch_phone: sale?.branch_phone,
            company_name: sale?.company_name,
            // T4.2: filial yuridik nomi va STIR (server javobi, bo'lmasa asl sotuvdan)
            branch_legal_name: saved?.branch_legal_name || sale?.branch_legal_name,
            branch_stir: saved?.branch_stir || sale?.branch_stir,
          };
          printReceiptHtml(buildReceiptHtml(meta, templateType, tmplCfg));
        } catch { /* chek chop etilmasa ham qaytarish bekor bo'lmasin */ }
      }

      toast.success(t('partialReturn.returnSuccess'));
      onSuccess();
    } catch (error) {
      // 4xx — hujjat yaratilmagan, keyingi urinishga yangi kalit; tarmoq xatosida kalit saqlanadi
      if (error.response && error.response.status >= 400 && error.response.status < 500) idemKeyRef.current = null;
      const raw = error.response?.data?.detail;
      // T4.6: detail obyekt bo'lishi mumkin ({code, message, ...})
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        if (error.response?.status === 403 && raw.code === 'approval_required') {
          approvalFlow.begin(raw, {});
          return;
        }
        if (raw.code === 'approval_invalid') approvalFlow.close();
        toast.error(raw.message || t('auth.errGeneral'));
      } else {
        // D1.4: server "asl partiya topilmadi" desa (xabarda lot_number) — shu qatorlarga seriya/muddat maydoni ochiladi
        if (pharmacy && error.response?.status === 400 && typeof raw === 'string' && raw.includes('lot_number')) {
          const named = items.filter(it => it.returnQty > 0 && it.product_name && raw.includes(`'${it.product_name}'`)).map(it => it.id);
          setItems(prev => prev.map(it => (
            it.returnQty > 0 && (named.length === 0 || named.includes(it.id)) ? { ...it, needLot: true } : it
          )));
        }
        toast.error(raw || t('auth.errGeneral'));
      }
    } finally {
      setLoading(false);
    }
  };

  // T4.6: tasdiq so'rovi/kutish/qayta yuborish (Approvals.jsx); tasdiqlansa qaytarish approval_id bilan qayta yuboriladi
  const approvalFlow = useApprovalFlow((requestId) => submitReturn(requestId));

  const curr = sale?.currency_code || sale?.currency || 'UZS';
  const currLabel = curr === 'USD' ? '$' : "so'm";
  const totalRefund = calculateTotalRefund();

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm z-[60] p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white shrink-0">
          <div>
            <h3 className="text-xl font-bold text-slate-800">{t('partialReturn.title', { number: sale?.number })}</h3>
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
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('admin.dict.product')}</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">{t('partialReturn.soldQty')}</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">{t('common.price')}</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">{t('ops.returnQty')}</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase">{t('partialReturn.returnAmount')}</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-100 text-sm">
                {fetchingItems ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center">
                      <div className="flex items-center justify-center gap-2 text-slate-400">
                        <span className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                        <span className="text-sm">{t('pos.productsLoading')}</span>
                      </div>
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-sm">
                      {t('product.noProducts')}
                    </td>
                  </tr>
                ) : (
                  items.map((item, idx) => {
                    const avgPrice = item.subtotal / item.quantity;
                    const itemRefund = avgPrice * item.returnQty;
                    return (
                      <tr key={item.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-900">
                          {item.product_name}
                          {rowNeedsLot(item) && (
                            <div className="mt-2 space-y-1.5">
                              <div className="text-[11px] font-semibold text-amber-600">
                                {tf('pharmacyReturn.needLot', "Asl partiya topilmadi — seriya va muddatni kiriting")}
                              </div>
                              <div className="flex gap-2">
                                <input
                                  type="text"
                                  value={item.lot_number || ''}
                                  onChange={(e) => handleLotChange(idx, 'lot_number', e.target.value)}
                                  placeholder={tf('pharmacyReturn.lot', 'Seriya')}
                                  className="w-32 px-2 py-1 border border-slate-200 rounded text-xs focus:outline-none focus:border-blue-400"
                                />
                                <input
                                  type="date"
                                  value={item.expiry_date || ''}
                                  onChange={(e) => handleLotChange(idx, 'expiry_date', e.target.value)}
                                  title={tf('pharmacyReturn.expiry', 'Yaroqlilik muddati')}
                                  className="px-2 py-1 border border-slate-200 rounded text-xs focus:outline-none focus:border-blue-400"
                                />
                              </div>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-600 font-mono">
                          {fmt(item.quantity)} {item.unit}
                          {item.returned_quantity > 0 && (
                            <div className="text-[10px] text-red-500 font-semibold">{t('partialReturn.returnedLabel')}: {fmt(item.returned_quantity)}</div>
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
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between bg-slate-50 p-4 rounded-xl border border-slate-100">
            <div className="flex gap-4 items-center flex-wrap">
              <span className="text-sm font-semibold text-slate-700">{t('partialReturn.returnTypeLabel')}</span>
              <select
                value={paymentType}
                onChange={(e) => setPaymentType(e.target.value)}
                className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 bg-white"
              >
                <option value="cash">{t('partialReturn.cashRefundOption')}</option>
                <option value="debt">{t('partialReturn.debtDeductOption')}</option>
              </select>
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={printReceipt}
                  onChange={(e) => setPrintReceipt(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-400"
                />
                {t('sale.printReceipt')}
              </label>
            </div>
            <div className="text-right">
              <span className="text-sm text-slate-500 uppercase tracking-wider font-semibold block mb-1">{t('partialReturn.totalRefundLabel')}</span>
              <span className="text-2xl font-bold text-slate-900">{fmt(totalRefund)} {currLabel}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 bg-white shrink-0">
          <button onClick={onClose} className="px-5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-xl transition-colors">
            {t('admin.dict.cancel')}
          </button>
          <button
            onClick={() => submitReturn()}
            disabled={loading || totalRefund <= 0}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors flex items-center gap-2"
          >
            {loading ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span> : <Check size={18} />}
            {t('common.confirm')}
          </button>
        </div>
      </div>
      <ApprovalModal flow={approvalFlow} />
    </div>
  );
}
