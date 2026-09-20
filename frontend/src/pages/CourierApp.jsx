/**
 * Dostavchik (kuryer) Mini App — kuryer boti orqali ochiladi.
 * Auth: URL query paramlar (c=company, u=chat_id, t=HMAC imzo) —
 * mijoz do'konidagi (TelegramShop) bilan bir xil uslub.
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import axios from 'axios'
import {
  Truck, Phone, MapPin, RefreshCw, Loader2, Package,
  CheckCircle2, AlertCircle, Banknote, CreditCard,
} from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || '/api'

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')

const PAY_LABELS = {
  cash: { label: 'Naqd', icon: Banknote, cls: 'bg-green-50 text-green-700' },
  card: { label: 'Karta', icon: CreditCard, cls: 'bg-blue-50 text-blue-700' },
  debt: { label: 'Qarzga', icon: AlertCircle, cls: 'bg-orange-50 text-orange-700' },
}

export default function CourierApp() {
  const params = useMemo(() => new URLSearchParams(window.location.search), [])
  const companyId = params.get('c')
  const u = params.get('u')
  const t = params.get('t')

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyGroup, setBusyGroup] = useState(null)
  const [confirmGroup, setConfirmGroup] = useState(null) // "Yetkazdim" tasdiqlash

  const load = useCallback((silent = false) => {
    if (!companyId || !u || !t) {
      setError("Havola noto'g'ri. Botdagi \"📦 Buyurtmalarim\" tugmasidan foydalaning.")
      setLoading(false)
      return
    }
    if (!silent) setLoading(true)
    axios.get(`${API_URL}/courier-bot/${companyId}/my-orders`, { params: { u, t } })
      .then(r => { setData(r.data); setError(null) })
      .catch(err => setError(err.response?.data?.detail || 'Yuklashda xatolik'))
      .finally(() => setLoading(false))
  }, [companyId, u, t])

  useEffect(() => { load() }, [load])

  const setStatus = async (group, status) => {
    setBusyGroup(group.group_id)
    try {
      await axios.put(
        `${API_URL}/courier-bot/${companyId}/orders/${group.group_id}/status`,
        { status },
        { params: { u, t } },
      )
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      setConfirmGroup(null)
      load(true)
    } catch (err) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      alert(err.response?.data?.detail || 'Xatolik yuz berdi')
    } finally {
      setBusyGroup(null)
    }
  }

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    tg?.ready?.()
    tg?.expand?.()
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-slate-50 p-6 text-center">
        <AlertCircle className="w-10 h-10 text-red-400" />
        <p className="text-sm text-slate-600">{error}</p>
        <button onClick={() => load()} className="px-4 py-2 bg-blue-500 text-white rounded-xl text-sm font-semibold">
          Qayta urinish
        </button>
      </div>
    )
  }

  const orders = data?.orders || []

  return (
    <div className="min-h-screen bg-slate-50 pb-8">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white border-b border-slate-100 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 bg-blue-50 rounded-xl flex items-center justify-center">
            <Truck className="w-5 h-5 text-blue-500" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-800">{data?.courier?.name || 'Dostavchik'}</p>
            <p className="text-[11px] text-slate-400">Bugun yetkazildi: <b className="text-green-600">{data?.delivered_today ?? 0}</b></p>
          </div>
        </div>
        <button onClick={() => load()} className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-100 active:scale-95">
          <RefreshCw className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {/* Orders */}
      <div className="p-4 space-y-3">
        {orders.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-20 text-slate-400">
            <Package className="w-12 h-12" />
            <p className="text-sm font-medium">Hozircha faol buyurtma yo'q</p>
            <p className="text-xs">Yangi buyurtma biriktirilganda bot xabar beradi</p>
          </div>
        ) : orders.map(group => {
          const pay = PAY_LABELS[group.payment_type] || PAY_LABELS.cash
          const PayIcon = pay.icon
          const total = group.total_amount + (group.delivery_fee || 0)
          const busy = busyGroup === group.group_id
          return (
            <div key={group.group_id} className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
              {/* Status chizig'i */}
              <div className={`h-1 ${group.status === 'on_way' ? 'bg-orange-400' : 'bg-purple-400'}`} />
              <div className="p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-slate-800">{group.customer_name}</p>
                    <span className={`inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-md text-[11px] font-semibold ${group.status === 'on_way' ? 'bg-orange-50 text-orange-600' : 'bg-purple-50 text-purple-600'}`}>
                      {group.status === 'on_way' ? "🚚 Yo'ldasiz" : '🛵 Sizga biriktirildi'}
                    </span>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-base font-bold text-slate-800">{fmt(total)} so'm</p>
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${pay.cls}`}>
                      <PayIcon className="w-3 h-3" /> {pay.label}
                    </span>
                  </div>
                </div>

                {/* Mahsulotlar */}
                <div className="bg-slate-50 rounded-xl px-3 py-2 space-y-1">
                  {group.items.map((it, i) => (
                    <div key={i} className="flex justify-between text-xs">
                      <span className="text-slate-600 truncate">{it.product_name} × {it.quantity}</span>
                      <span className="text-slate-500 font-medium shrink-0 ml-2">{fmt(it.total_amount)}</span>
                    </div>
                  ))}
                  {group.delivery_fee > 0 && (
                    <div className="flex justify-between text-xs pt-1 border-t border-slate-200/70">
                      <span className="text-slate-400">Yetkazish haqi</span>
                      <span className="text-slate-500 font-medium">+{fmt(group.delivery_fee)}</span>
                    </div>
                  )}
                </div>

                {/* Manzil / tel / izoh */}
                <div className="space-y-1.5">
                  {group.delivery_address && (
                    <a
                      href={group.delivery_lat && group.delivery_lng
                        ? `https://maps.google.com/?q=${group.delivery_lat},${group.delivery_lng}`
                        : `https://maps.google.com/?q=${encodeURIComponent(group.delivery_address)}`}
                      target="_blank" rel="noreferrer"
                      className="flex items-start gap-2 text-xs text-blue-600"
                    >
                      <MapPin className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                      <span className="underline">{group.delivery_address}</span>
                    </a>
                  )}
                  {group.customer_phone && (
                    <a href={`tel:${group.customer_phone}`} className="flex items-center gap-2 text-xs text-blue-600">
                      <Phone className="w-3.5 h-3.5 shrink-0" />
                      <span className="underline">{group.customer_phone}</span>
                    </a>
                  )}
                  {group.notes && <p className="text-[11px] text-slate-400">💬 {group.notes}</p>}
                </div>

                {/* Amallar */}
                {group.status === 'assigned' ? (
                  <button
                    onClick={() => setStatus(group, 'on_way')}
                    disabled={busy}
                    className="w-full py-2.5 bg-orange-500 active:bg-orange-600 disabled:opacity-60 text-white rounded-xl font-semibold text-sm flex items-center justify-center gap-2"
                  >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Truck className="w-4 h-4" />}
                    Yo'lga chiqdim
                  </button>
                ) : (
                  <button
                    onClick={() => setConfirmGroup(group)}
                    disabled={busy}
                    className="w-full py-2.5 bg-green-500 active:bg-green-600 disabled:opacity-60 text-white rounded-xl font-semibold text-sm flex items-center justify-center gap-2"
                  >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                    Yetkazdim
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Yetkazdim tasdiqlash */}
      {confirmGroup && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setConfirmGroup(null)} />
          <div className="relative w-full bg-white rounded-t-3xl p-6 space-y-4">
            <p className="text-base font-bold text-slate-800 text-center">Buyurtma yetkazildimi?</p>
            <p className="text-sm text-slate-500 text-center">
              {confirmGroup.customer_name} — <b>{fmt(confirmGroup.total_amount + (confirmGroup.delivery_fee || 0))} so'm</b>
              {confirmGroup.payment_type === 'cash' && <span className="block mt-1 text-orange-600 font-semibold">💵 Naqd pulni qabul qilganingizga ishonch hosil qiling!</span>}
            </p>
            <div className="flex gap-2">
              <button onClick={() => setConfirmGroup(null)}
                className="flex-1 py-3 bg-slate-100 text-slate-600 rounded-xl font-semibold text-sm">
                Bekor qilish
              </button>
              <button onClick={() => setStatus(confirmGroup, 'delivered')}
                disabled={busyGroup === confirmGroup.group_id}
                className="flex-1 py-3 bg-green-500 text-white rounded-xl font-semibold text-sm disabled:opacity-60">
                ✅ Ha, yetkazdim
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
