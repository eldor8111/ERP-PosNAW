import { useState, useEffect, useMemo, useCallback } from 'react'
import axios from 'axios'
import { ShoppingCart, Search, Plus, Minus, X, Package, CheckCircle2, Loader2 } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8010/api'
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')

const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null

function useTelegram() {
  useEffect(() => {
    if (!tg) return
    tg.ready()
    tg.expand()
    try { tg.setHeaderColor?.('secondary_bg_color') } catch { /* ignore */ }
  }, [])
  return tg
}

function shopApi(initData) {
  return axios.create({
    baseURL: API_URL,
    headers: { 'X-Init-Data': initData || '' },
    timeout: 15000,
  })
}

export default function TelegramShop() {
  useTelegram()

  const params = new URLSearchParams(window.location.search)
  const companyId = params.get('c')
  const initData = tg?.initData || ''

  const [shopName, setShopName] = useState('')
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [activeCategory, setActiveCategory] = useState(null)
  const [search, setSearch] = useState('')
  const [cart, setCart] = useState({})
  const [showCart, setShowCart] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  const api = useMemo(() => shopApi(initData), [initData])

  useEffect(() => {
    if (!companyId) {
      setError('Do\'kon aniqlanmadi. Botdan qayta urinib ko\'ring.')
      setLoading(false)
      return
    }
    if (!initData) {
      setError('Telegram orqali ochilmagan. Botdan "Dokon" tugmasini bosing.')
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    Promise.all([
      axios.get(`${API_URL}/shop/${companyId}/info`).then(r => r.data).catch(() => null),
      api.get(`/shop/${companyId}/products`).then(r => r.data).catch(() => null),
      api.get(`/shop/${companyId}/categories`).then(r => r.data).catch(() => []),
    ]).then(([info, prods, cats]) => {
      if (cancelled) return
      if (!prods) {
        setError('Mahsulotlarni yuklab bo\'lmadi. Qayta urinib ko\'ring.')
      } else {
        setShopName(info?.name || 'Do\'kon')
        setProducts(prods)
        setCategories(cats || [])
      }
      setLoading(false)
    })

    return () => { cancelled = true }
  }, [companyId, initData, api])

  const filteredProducts = useMemo(() => {
    let list = products
    if (activeCategory) list = list.filter(p => p.category === activeCategory)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(p => p.name.toLowerCase().includes(q))
    }
    return list
  }, [products, activeCategory, search])

  const cartItems = useMemo(() => {
    return Object.entries(cart)
      .filter(([, qty]) => qty > 0)
      .map(([id, qty]) => {
        const product = products.find(p => p.id === Number(id))
        return product ? { ...product, qty } : null
      })
      .filter(Boolean)
  }, [cart, products])

  const cartTotal = useMemo(() => cartItems.reduce((sum, i) => sum + i.price * i.qty, 0), [cartItems])
  const cartCount = useMemo(() => cartItems.reduce((sum, i) => sum + i.qty, 0), [cartItems])

  const addToCart = useCallback((product) => {
    tg?.HapticFeedback?.impactOccurred?.('light')
    setCart(prev => {
      const current = prev[product.id] || 0
      const next = Math.min(current + 1, product.available)
      return { ...prev, [product.id]: next }
    })
  }, [])

  const removeFromCart = useCallback((productId) => {
    tg?.HapticFeedback?.impactOccurred?.('light')
    setCart(prev => {
      const current = prev[productId] || 0
      if (current <= 1) {
        const { [productId]: _, ...rest } = prev
        return rest
      }
      return { ...prev, [productId]: current - 1 }
    })
  }, [])

  useEffect(() => {
    if (!tg) return
    if (cartCount > 0 && !showCart) {
      tg.MainButton.setText(`🛒 Savat — ${fmt(cartTotal)} so'm`)
      tg.MainButton.show()
      tg.MainButton.onClick(() => setShowCart(true))
    } else {
      tg.MainButton.hide()
    }
    return () => { tg.MainButton.offClick?.(() => setShowCart(true)) }
  }, [cartCount, cartTotal, showCart])

  const submitOrder = async () => {
    if (!cartItems.length || submitting) return
    setSubmitting(true)
    try {
      await api.post(`/shop/${companyId}/order`, {
        items: cartItems.map(i => ({ product_id: i.id, quantity: i.qty })),
        payment_type: 'cash',
      })
      tg?.HapticFeedback?.notificationOccurred?.('success')
      setSuccess(true)
      setCart({})
      setTimeout(() => {
        setShowCart(false)
        setSuccess(false)
        tg?.close?.()
      }, 2000)
    } catch (err) {
      tg?.HapticFeedback?.notificationOccurred?.('error')
      const msg = err.response?.data?.detail || 'Buyurtma berishda xatolik yuz berdi'
      window.Telegram?.WebApp?.showAlert?.(msg) || alert(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color,#f8fafc)]">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 px-6 text-center bg-[var(--tg-theme-bg-color,#f8fafc)]">
        <Package className="w-12 h-12 text-slate-300" />
        <p className="text-slate-500 text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-6" style={{ background: 'var(--tg-theme-bg-color, #f8fafc)' }}>
      {/* Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-slate-200 px-4 pt-4 pb-3 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              🏪 {shopName}
            </h1>
            <p className="text-xs text-slate-400">{products.length} ta mahsulot mavjud</p>
          </div>
          <button
            onClick={() => setShowCart(true)}
            className="relative w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center active:scale-95 transition-transform"
          >
            <ShoppingCart className="w-5 h-5 text-blue-600" />
            {cartCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                {cartCount}
              </span>
            )}
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Mahsulot qidirish..."
            className="w-full pl-9 pr-3 py-2.5 bg-slate-100 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>

        {/* Categories */}
        {categories.length > 0 && (
          <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-1 px-1">
            <button
              onClick={() => setActiveCategory(null)}
              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                !activeCategory ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600'
              }`}
            >
              Barchasi
            </button>
            {categories.map(c => (
              <button
                key={c.id}
                onClick={() => setActiveCategory(c.name)}
                className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  activeCategory === c.name ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600'
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Products grid */}
      <div className="px-4 pt-4">
        {filteredProducts.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-slate-400">
            <Package className="w-10 h-10" />
            <p className="text-sm">Mahsulot topilmadi</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {filteredProducts.map(product => {
              const qty = cart[product.id] || 0
              return (
                <div key={product.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden flex flex-col">
                  <div className="aspect-square bg-slate-50 flex items-center justify-center overflow-hidden">
                    {product.image_url ? (
                      <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" />
                    ) : (
                      <Package className="w-8 h-8 text-slate-300" />
                    )}
                  </div>
                  <div className="p-2.5 flex-1 flex flex-col gap-1.5">
                    <p className="text-xs font-medium text-slate-700 line-clamp-2 min-h-[32px]">{product.name}</p>
                    <p className="text-sm font-bold text-blue-600">{fmt(product.price)} so'm</p>
                    <p className="text-[10px] text-slate-400">Qoldiq: {product.available} ta</p>

                    {qty === 0 ? (
                      <button
                        onClick={() => addToCart(product)}
                        className="mt-1 w-full py-1.5 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1 active:scale-95 transition-transform"
                      >
                        <Plus className="w-3.5 h-3.5" /> Savatga
                      </button>
                    ) : (
                      <div className="mt-1 flex items-center justify-between bg-blue-50 rounded-lg px-1 py-1">
                        <button onClick={() => removeFromCart(product.id)} className="w-6 h-6 flex items-center justify-center text-blue-600 active:scale-90">
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="text-xs font-bold text-blue-700">{qty}</span>
                        <button onClick={() => addToCart(product)} className="w-6 h-6 flex items-center justify-center text-blue-600 active:scale-90">
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Cart drawer */}
      {showCart && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => !submitting && setShowCart(false)} />
          <div className="relative w-full bg-white rounded-t-3xl max-h-[85vh] flex flex-col animate-[slideUp_0.25s_ease-out]">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-800">🛒 Savat</h2>
              <button onClick={() => !submitting && setShowCart(false)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {success ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16 px-6">
                <CheckCircle2 className="w-14 h-14 text-green-500" />
                <p className="text-base font-semibold text-slate-800">Buyurtma qabul qilindi!</p>
                <p className="text-sm text-slate-500 text-center">Do'kon xodimlari tez orada siz bilan bog'lanadi</p>
              </div>
            ) : cartItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16 text-slate-400">
                <ShoppingCart className="w-10 h-10" />
                <p className="text-sm">Savat bo'sh</p>
              </div>
            ) : (
              <>
                <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
                  {cartItems.map(item => (
                    <div key={item.id} className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
                      <div className="w-12 h-12 rounded-xl bg-slate-50 flex items-center justify-center shrink-0 overflow-hidden">
                        {item.image_url ? (
                          <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                        ) : (
                          <Package className="w-5 h-5 text-slate-300" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-700 truncate">{item.name}</p>
                        <p className="text-xs text-slate-400">{fmt(item.price)} so'm × {item.qty}</p>
                      </div>
                      <div className="flex items-center gap-2 bg-slate-100 rounded-lg px-1.5 py-1">
                        <button onClick={() => removeFromCart(item.id)} className="w-6 h-6 flex items-center justify-center text-slate-600 active:scale-90">
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="text-xs font-bold w-4 text-center">{item.qty}</span>
                        <button onClick={() => addToCart(item)} className="w-6 h-6 flex items-center justify-center text-slate-600 active:scale-90">
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="px-5 py-4 border-t border-slate-100 bg-white">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm text-slate-500">Jami</span>
                    <span className="text-lg font-bold text-slate-800">{fmt(cartTotal)} so'm</span>
                  </div>
                  <button
                    onClick={submitOrder}
                    disabled={submitting}
                    className="w-full py-3 bg-blue-500 hover:bg-blue-600 disabled:opacity-60 text-white rounded-xl font-semibold text-sm flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
                  >
                    {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                    {submitting ? 'Yuborilmoqda...' : 'Buyurtma berish'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      `}</style>
    </div>
  )
}
