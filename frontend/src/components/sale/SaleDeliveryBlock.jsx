import { useEffect, useState } from 'react';
import { Truck, MapPin, X, AlertTriangle, Send } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import MapPicker from '../MapPicker';

const inputCls = 'w-full border-2 border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white';

/**
 * Ulgurji sotuvda "Yetkazib berish" bloki. Manzil/nuqta bo'sh qoldirilsa
 * backend mijoz kartasidagi manzil va joylashuvni oladi.
 */
export default function SaleDeliveryBlock({ value, onChange, customerId }) {
  const { t } = useLang();
  const [loaded, setLoaded] = useState(null); // { id, data }
  const [mapOpen, setMapOpen] = useState(false);
  const set = (patch) => onChange({ ...value, ...patch });

  // Mijoz almashsa eski ma'lumot ko'rinmasligi uchun id bo'yicha tekshiramiz
  const customer = customerId && loaded?.id === String(customerId) ? loaded.data : null;
  useEffect(() => {
    if (!customerId) return;
    let alive = true;
    api.post(`/customers/${customerId}`, null, { _silent: true })
      .then(r => alive && setLoaded({ id: String(customerId), data: r.data }))
      .catch(() => {});
    return () => { alive = false; };
  }, [customerId]);

  const customerAddress = customer ? [customer.district, customer.address].filter(Boolean).join(', ') : '';
  const hasOwnPoint = value.lat != null;
  // Manzil qo'lda yozilmasa mijoz nuqtasi ishlatiladi (backend ham shunday)
  const usesCustomerPoint = !hasOwnPoint && !value.address && customer?.lat != null;
  const noLocation = value.enabled && !hasOwnPoint && !usesCustomerPoint;

  const requestTg = async () => {
    try { const { data } = await api.post(`/customers/${customerId}/request-location`); toast.success(data.message); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className={`rounded-xl border-2 transition-colors ${value.enabled ? 'border-blue-200 bg-blue-50/40' : 'border-slate-200'}`}>
      <label className="flex items-center justify-between px-3 py-2.5 cursor-pointer select-none">
        <span className="flex items-center gap-2 text-sm font-bold text-slate-700">
          <Truck className={`size-4 ${value.enabled ? 'text-blue-600' : 'text-slate-400'}`} />
          {t('saleDelivery.title')}
        </span>
        <span className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${value.enabled ? 'bg-blue-600' : 'bg-slate-300'}`}>
          <input type="checkbox" className="sr-only" checked={value.enabled} onChange={e => set({ enabled: e.target.checked })} />
          <span className={`absolute top-0.5 size-4 rounded-full bg-white shadow transition-all ${value.enabled ? 'left-[18px]' : 'left-0.5'}`} />
        </span>
      </label>

      {value.enabled && (
        <div className="px-3 pb-3 space-y-2.5">
          <div className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 border-2 border-slate-200 rounded-lg px-3 bg-white focus-within:ring-2 focus-within:ring-blue-400">
              <MapPin className="size-4 text-slate-400 shrink-0" />
              <input value={value.address} onChange={e => set({ address: e.target.value })}
                placeholder={customerAddress || t('saleDelivery.addressPlaceholder')}
                className="flex-1 py-2 text-sm outline-none bg-transparent min-w-0" />
            </div>
            <button type="button" onClick={() => setMapOpen(true)}
              className={`px-3 rounded-lg border-2 text-xs font-semibold whitespace-nowrap ${hasOwnPoint ? 'border-blue-300 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'}`}>
              {hasOwnPoint ? `📍 ${t('saleDelivery.pointSet')}` : t('saleDelivery.pickOnMap')}
            </button>
          </div>

          {usesCustomerPoint && <p className="text-[11px] text-emerald-600">✓ {t('saleDelivery.usesCustomerPoint')}</p>}
          {noLocation && (
            <div className="flex items-start gap-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-2">
              <AlertTriangle className="size-3.5 shrink-0 mt-px" />
              <span className="flex-1">{t('saleDelivery.noLocationWarning')}</span>
              {customer?.tg_connected && (
                <button type="button" onClick={requestTg} className="shrink-0 font-semibold text-sky-700 flex items-center gap-1 hover:underline">
                  <Send className="size-3" />{t('customerProfile.requestTgLocation')}
                </button>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-2">
            <input value={value.contact_phone} onChange={e => set({ contact_phone: e.target.value })} inputMode="tel"
              placeholder={customer?.phone || t('saleDelivery.phone')} className={inputCls} />
            <input type="number" min="0" value={value.delivery_fee} onChange={e => set({ delivery_fee: e.target.value })}
              placeholder={t('saleDelivery.fee')} className={inputCls} />
            <input type="date" value={value.planned_date} onChange={e => set({ planned_date: e.target.value })}
              title={t('saleDelivery.plannedDate')} className={inputCls} />
          </div>
          <input value={value.note} onChange={e => set({ note: e.target.value })}
            placeholder={t('saleDelivery.notePlaceholder')} className={inputCls} />
          {value.status && value.status !== 'pending' && (
            <p className="text-[11px] text-slate-500">{t('saleDelivery.currentStatus')}: <b>{t(`logistics.orderStatus.${value.status}`)}</b></p>
          )}
        </div>
      )}

      {mapOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onClick={() => setMapOpen(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100">
              <h3 className="font-bold text-slate-800">{t('saleDelivery.pickOnMap')}</h3>
              <button onClick={() => setMapOpen(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded-lg"><X className="size-5" /></button>
            </div>
            <div className="p-5 space-y-3">
              <MapPicker
                value={hasOwnPoint ? { lat: value.lat, lng: value.lng } : (customer?.lat != null ? { lat: customer.lat, lng: customer.lng } : null)}
                onChange={({ lat, lng, address }) => set({ lat, lng, address: value.address || address || '' })}
                height={380}
              />
              <div className="flex justify-between">
                {hasOwnPoint
                  ? <button onClick={() => set({ lat: null, lng: null })} className="text-sm text-red-500 font-medium hover:underline">{t('customerProfile.clearLocation')}</button>
                  : <span />}
                <button onClick={() => setMapOpen(false)} className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg">{t('common.save')}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
