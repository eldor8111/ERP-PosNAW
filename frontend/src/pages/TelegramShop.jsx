import { useState, useEffect, useMemo, useCallback } from 'react'
import axios from 'axios'
import { ShoppingCart, Search, Plus, Minus, X, Package, CheckCircle2, Loader2, ClipboardList, Clock, Truck, AlertCircle, Wallet, CreditCard, Copy, Receipt, Menu, Store, ChevronRight } from 'lucide-react'
import { ECodeIconLight } from '../components/ECodeLogo'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8010/api'
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ')
const fmtDate = (d) => d ? new Date(d).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''

const ORDER_STATUS = {
  pending: { label: 'Kutilmoqda', icon: Clock, bg: 'bg-yellow-50', text: 'text-yellow-700' },
  confirmed: { label: 'Tasdiqlangan', icon: CheckCircle2, bg: 'bg-blue-50', text: 'text-blue-700' },
  delivered: { label: 'Yetkazildi', icon: Truck, bg: 'bg-green-50', text: 'text-green-700' },
  cancelled: { label: 'Bekor qilindi', icon: AlertCircle, bg: 'bg-red-50', text: 'text-red-700' },
}

function getTg() {
  return typeof window !== 'undefined' ? window.Telegram?.WebApp : null
}

// Telegram Desktop/Web'da ba'zi WebApp metodlari (showAlert, HapticFeedback)
// qo'llab-quvvatlanmasligi yoki xato tashlashi mumkin — hech qachon asosiy
// oqimni to'xtatib qo'ymasligi uchun har doim try/catch bilan chaqiramiz.
function safeTg(fn) {
  try {
    fn(getTg())
  } catch { /* Telegram metodi mavjud emas yoki ishlamadi — e'tiborsiz qoldiramiz */ }
}

function getInitData() {
  const tg = getTg()
  if (tg?.initData) return tg.initData
  // Fallback: Telegram ba'zan initData'ni URL hash orqali ham beradi
  const hash = window.location.hash?.replace(/^#/, '') || ''
  const hashParams = new URLSearchParams(hash)
  const fromHash = hashParams.get('tgWebAppData')
  if (fromHash) return fromHash
  return ''
}

function shopApi(initData, u, t) {
  const instance = axios.create({
    baseURL: API_URL,
    headers: { 'X-Init-Data': initData || '' },
    timeout: 15000,
  })
  // Reply-keyboard web_app tugmasi ba'zi Telegram klientlarida initData'ni
  // bo'sh qaytaradi — shu sabab bot shaxsiy imzolangan havola (u, t) ham beradi
  instance.interceptors.request.use(config => {
    if (u && t) config.params = { ...config.params, u, t }
    return config
  })
  return instance
}

export default function TelegramShop() {
  const params = new URLSearchParams(window.location.search)
  const companyId = params.get('c')
  const urlUser = params.get('u')
  const urlToken = params.get('t')
  const hasUrlAuth = !!(urlUser && urlToken)

  const [tgReady, setTgReady] = useState(false)
  const [initData, setInitData] = useState('')

  // Telegram WebApp skripti async yuklanishi mumkin — bir necha marta poll qilamiz.
  // Agar bot shaxsiy havola (u, t) bergan bo'lsa, initData'ni kutish shart emas.
  useEffect(() => {
    let attempts = 0
    let cancelled = false

    const tryInit = () => {
      if (cancelled) return
      const tg = getTg()
      const data = getInitData()
      if (tg) {
        try {
          tg.ready()
          tg.expand()
          tg.setHeaderColor?.('secondary_bg_color')
        } catch { /* ignore */ }
      }
      if (data) {
        setInitData(data)
        setTgReady(true)
        return
      }
      if (hasUrlAuth) {
        setTgReady(true)
        return
      }
      attempts += 1
      if (attempts < 20) {
        setTimeout(tryInit, 150)
      } else {
        setTgReady(true) // to'xtatamiz, xato holatini ko'rsatamiz
      }
    }

    tryInit()
    return () => { cancelled = true }
  }, [hasUrlAuth])

  const hasAuth = !!initData || hasUrlAuth

  const [shopName, setShopName] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [activeCategory, setActiveCategory] = useState(null)
  const [search, setSearch] = useState('')
  const [cart, setCart] = useState({})
  const [showCart, setShowCart] = useState(false)
  const [showOrders, setShowOrders] = useState(false)
  const [myOrders, setMyOrders] = useState([])
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [showBalance, setShowBalance] = useState(false)
  const [meData, setMeData] = useState(null)
  const [balanceLoading, setBalanceLoading] = useState(false)
  const [showPurchases, setShowPurchases] = useState(false)
  const [purchases, setPurchases] = useState([])
  const [purchasesLoading, setPurchasesLoading] = useState(false)
  const [showCard, setShowCard] = useState(false)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [orderError, setOrderError] = useState(null)

  const api = useMemo(() => shopApi(initData, urlUser, urlToken), [initData, urlUser, urlToken])

  useEffect(() => {
    if (!tgReady) return // Telegram WebApp SDK hali tekshirilmoqda

    if (!companyId) {
      setError('Do\'kon aniqlanmadi. Botdan qayta urinib ko\'ring.')
      setLoading(false)
      return
    }
    if (!hasAuth) {
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

    api.get(`/shop/${companyId}/me`).then(r => { if (!cancelled) setMeData(r.data) }).catch(() => {})

    return () => { cancelled = true }
  }, [tgReady, companyId, hasAuth, api])

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
    safeTg(tg => tg?.HapticFeedback?.impactOccurred?.('light'))
    setCart(prev => {
      const current = prev[product.id] || 0
      const next = Math.min(current + 1, product.available)
      return { ...prev, [product.id]: next }
    })
  }, [])

  const removeFromCart = useCallback((productId) => {
    safeTg(tg => tg?.HapticFeedback?.impactOccurred?.('light'))
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
    const tg = getTg()
    if (!tg?.MainButton) return
    const onClick = () => setShowCart(true)
    try {
      if (cartCount > 0 && !showCart) {
        tg.MainButton.setText(`🛒 Savat — ${fmt(cartTotal)} so'm`)
        tg.MainButton.show()
        tg.MainButton.onClick(onClick)
      } else {
        tg.MainButton.hide()
      }
    } catch { /* Desktop/Web'da MainButton to'liq qo'llab-quvvatlanmasligi mumkin */ }
    return () => { try { tg.MainButton.offClick?.(onClick) } catch { /* ignore */ } }
  }, [cartCount, cartTotal, showCart])

  const openMyOrders = useCallback(() => {
    setShowMenu(false)
    setShowOrders(true)
    setOrdersLoading(true)
    api.get(`/shop/${companyId}/my-orders`)
      .then(r => setMyOrders(r.data || []))
      .catch(() => setMyOrders([]))
      .finally(() => setOrdersLoading(false))
  }, [api, companyId])

  const loadMe = useCallback(() => {
    setBalanceLoading(true)
    return api.get(`/shop/${companyId}/me`)
      .then(r => { setMeData(r.data); return r.data })
      .catch(() => { setMeData(null); return null })
      .finally(() => setBalanceLoading(false))
  }, [api, companyId])

  const openBalance = useCallback(() => {
    setShowMenu(false)
    setShowBalance(true)
    loadMe()
  }, [loadMe])

  const openCard = useCallback(() => {
    setShowMenu(false)
    setShowCard(true)
    if (!meData) loadMe()
  }, [meData, loadMe])

  const openPurchases = useCallback(() => {
    setShowMenu(false)
    setShowPurchases(true)
    setPurchasesLoading(true)
    api.get(`/shop/${companyId}/purchases`)
      .then(r => setPurchases(r.data || []))
      .catch(() => setPurchases([]))
      .finally(() => setPurchasesLoading(false))
  }, [api, companyId])

  const copyCardNumber = useCallback(() => {
    if (!meData?.card_number) return
    navigator.clipboard?.writeText(meData.card_number).then(() => {
      setCopied(true)
      safeTg(tg => tg?.HapticFeedback?.impactOccurred?.('light'))
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }, [meData])

  const submitOrder = async () => {
    if (!cartItems.length || submitting) return
    setSubmitting(true)
    setOrderError(null)
    try {
      await api.post(`/shop/${companyId}/order`, {
        items: cartItems.map(i => ({ product_id: i.id, quantity: i.qty })),
        payment_type: 'cash',
      })
      safeTg(tg => tg?.HapticFeedback?.notificationOccurred?.('success'))
      setSuccess(true)
      setCart({})
      setTimeout(() => {
        setShowCart(false)
        setSuccess(false)
        safeTg(tg => tg?.close?.())
      }, 2000)
    } catch (err) {
      safeTg(tg => tg?.HapticFeedback?.notificationOccurred?.('error'))
      const msg = err.response?.data?.detail || err.message || 'Buyurtma berishda xatolik yuz berdi'
      setOrderError(msg)
      safeTg(tg => tg?.showAlert?.(String(msg)))
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
    const tg = getTg()
    const debug = {
      hasWindowTelegram: typeof window !== 'undefined' && !!window.Telegram,
      hasWebApp: !!tg,
      initDataLength: tg?.initData?.length || 0,
      initDataUnsafeKeys: tg?.initDataUnsafe ? Object.keys(tg.initDataUnsafe) : [],
      platform: tg?.platform || 'n/a',
      version: tg?.version || 'n/a',
      href: window.location.href,
      search: window.location.search,
      hash: window.location.hash,
    }
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 px-6 text-center bg-[var(--tg-theme-bg-color,#f8fafc)]">
        <Package className="w-12 h-12 text-slate-300" />
        <p className="text-slate-500 text-sm">{error}</p>
        <pre className="mt-4 text-left text-[10px] text-slate-400 bg-slate-50 rounded-lg p-3 max-w-full overflow-x-auto whitespace-pre-wrap break-all">
          {JSON.stringify(debug, null, 2)}
        </pre>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-6" style={{ background: 'var(--tg-theme-bg-color, #f8fafc)' }}>
      {/* Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-slate-200 px-4 pt-4 pb-3 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <button
              onClick={() => setShowMenu(true)}
              className="w-9 h-9 shrink-0 rounded-xl bg-slate-100 flex items-center justify-center active:scale-95 transition-transform"
              title="Menyu"
            >
              <Menu className="w-[18px] h-[18px] text-slate-700" />
            </button>
            <div className="min-w-0">
              <h1 className="text-base font-bold text-slate-800 truncate">{shopName}</h1>
              <p className="text-[11px] text-slate-400">{products.length} ta mahsulot</p>
            </div>
          </div>
          <button
            onClick={() => setShowCart(true)}
            className="relative w-9 h-9 shrink-0 rounded-xl bg-blue-500 flex items-center justify-center active:scale-95 transition-transform shadow-sm shadow-blue-200"
            title="Savat"
          >
            <ShoppingCart className="w-4 h-4 text-white" />
            {cartCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-white">
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

      {/* Side menu */}
      {showMenu && (
        <div className="fixed inset-0 z-[60] flex">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowMenu(false)} />
          <div className="relative w-[82%] max-w-[320px] h-full bg-white flex flex-col animate-[slideInLeft_0.22s_ease-out] shadow-2xl">
            {/* Profile header */}
            <div className="px-5 pt-6 pb-5 bg-gradient-to-br from-blue-600 to-indigo-700 text-white">
              <div className="flex items-center justify-between mb-4">
                <div className="w-11 h-11 rounded-2xl bg-white/15 flex items-center justify-center">
                  <ECodeIconLight size={26} />
                </div>
                <button onClick={() => setShowMenu(false)} className="w-8 h-8 rounded-full bg-white/15 flex items-center justify-center active:scale-95 transition-transform">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-sm font-bold truncate">{shopName}</p>
              <p className="text-[11px] text-blue-100 mt-0.5">{meData?.name || 'Mijoz'}</p>
              {meData?.card_number && (
                <p className="text-xs font-mono text-blue-100 mt-2 tracking-wider">
                  •••• {meData.card_number.slice(-4)}
                </p>
              )}
            </div>

            {/* Menu items */}
            <div className="flex-1 overflow-y-auto py-2">
              <button
                onClick={() => setShowMenu(false)}
                className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                  <Store className="w-4 h-4 text-blue-600" />
                </div>
                <span className="flex-1 text-left text-sm font-medium text-slate-700">Katalog</span>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>

              <button
                onClick={openMyOrders}
                className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center shrink-0">
                  <ClipboardList className="w-4 h-4 text-amber-600" />
                </div>
                <span className="flex-1 text-left text-sm font-medium text-slate-700">Buyurtmalarim</span>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>

              <button
                onClick={openBalance}
                className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <div className="w-9 h-9 rounded-xl bg-green-50 flex items-center justify-center shrink-0">
                  <Wallet className="w-4 h-4 text-green-600" />
                </div>
                <span className="flex-1 text-left text-sm font-medium text-slate-700">Balansim</span>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>

              <button
                onClick={openCard}
                className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center shrink-0">
                  <CreditCard className="w-4 h-4 text-violet-600" />
                </div>
                <span className="flex-1 text-left text-sm font-medium text-slate-700">Loyallik kartam</span>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>

              <button
                onClick={openPurchases}
                className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <div className="w-9 h-9 rounded-xl bg-rose-50 flex items-center justify-center shrink-0">
                  <Receipt className="w-4 h-4 text-rose-600" />
                </div>
                <span className="flex-1 text-left text-sm font-medium text-slate-700">Xaridlar tarixi</span>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>
            </div>

            <div className="px-5 py-4 border-t border-slate-100">
              <p className="text-[11px] text-slate-300 text-center">E-Code orqali ishga tushirilgan</p>
            </div>
          </div>
        </div>
      )}

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
                  {orderError && (
                    <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-600 text-xs">
                      {orderError}
                    </div>
                  )}
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

      {/* Buyurtmalarim drawer */}
      {showOrders && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowOrders(false)} />
          <div className="relative w-full bg-white rounded-t-3xl max-h-[85vh] flex flex-col animate-[slideUp_0.25s_ease-out]">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-800">📋 Buyurtmalarim</h2>
              <button onClick={() => setShowOrders(false)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {ordersLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
              </div>
            ) : myOrders.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16 text-slate-400">
                <ClipboardList className="w-10 h-10" />
                <p className="text-sm">Hali buyurtma yo'q</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto px-5 py-3 space-y-2 pb-6">
                {myOrders.map(order => {
                  const st = ORDER_STATUS[order.status] || ORDER_STATUS.pending
                  const StIcon = st.icon
                  return (
                    <div key={order.id} className="border border-slate-100 rounded-xl p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{order.product_name}</p>
                          <p className="text-xs text-slate-400 mt-0.5">
                            {order.quantity} ta × {fmt(order.unit_price)} so'm
                          </p>
                          <p className="text-[11px] text-slate-400 mt-1">{fmtDate(order.created_at)}</p>
                        </div>
                        <div className="text-right shrink-0">
                          <p className="text-sm font-bold text-slate-800">{fmt(order.total_amount)} so'm</p>
                          <span className={`mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${st.bg} ${st.text}`}>
                            <StIcon className="w-3 h-3" /> {st.label}
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Balans drawer */}
      {showBalance && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowBalance(false)} />
          <div className="relative w-full bg-white rounded-t-3xl max-h-[85vh] flex flex-col animate-[slideUp_0.25s_ease-out]">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-800">💰 Balansim</h2>
              <button onClick={() => setShowBalance(false)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {balanceLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
              </div>
            ) : !meData ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16 text-slate-400">
                <Wallet className="w-10 h-10" />
                <p className="text-sm">Ma'lumot topilmadi</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 pb-6">
                <div className={`rounded-2xl p-4 ${meData.debt_balance > 0 ? 'bg-red-50' : 'bg-green-50'}`}>
                  <p className="text-xs text-slate-500 mb-1">Joriy qarz</p>
                  <p className={`text-2xl font-extrabold ${meData.debt_balance > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {fmt(meData.debt_balance)} so'm
                  </p>
                  {meData.debt_limit > 0 && (
                    <p className="text-xs text-slate-400 mt-1">Limit: {fmt(meData.debt_limit)} so'm</p>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-amber-50 rounded-xl p-3">
                    <p className="text-[11px] text-amber-700 mb-1">⭐ Bonus</p>
                    <p className="text-base font-bold text-amber-700">{fmt(meData.bonus_balance)} so'm</p>
                  </div>
                  <div className="bg-blue-50 rounded-xl p-3">
                    <p className="text-[11px] text-blue-700 mb-1">🏆 Daraja</p>
                    <p className="text-base font-bold text-blue-700">{meData.tier || '—'}</p>
                  </div>
                  {meData.discount_percent > 0 && (
                    <div className="bg-violet-50 rounded-xl p-3">
                      <p className="text-[11px] text-violet-700 mb-1">🏷 Chegirma</p>
                      <p className="text-base font-bold text-violet-700">{meData.discount_percent}%</p>
                    </div>
                  )}
                  {meData.cashback_percent > 0 && (
                    <div className="bg-emerald-50 rounded-xl p-3">
                      <p className="text-[11px] text-emerald-700 mb-1">🔄 Keshbek</p>
                      <p className="text-base font-bold text-emerald-700">{meData.cashback_percent}%</p>
                    </div>
                  )}
                </div>

                {meData.debt_schedule?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-slate-500 mb-2">📅 Qarz muddatlari</p>
                    <div className="space-y-1.5">
                      {meData.debt_schedule.map((d, i) => {
                        const overdue = d.days_left < 0
                        const today = d.days_left === 0
                        const soon = d.days_left > 0 && d.days_left <= 3
                        const dot = overdue ? '🔴' : today ? '🟠' : soon ? '🟡' : '🟢'
                        return (
                          <div key={i} className="flex items-center justify-between text-xs bg-slate-50 rounded-lg px-3 py-2">
                            <span>{dot} {new Date(d.due_date).toLocaleDateString('uz-UZ')}</span>
                            <span className="font-semibold">{fmt(d.amount)} so'm</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                <button
                  onClick={openPurchases}
                  className="w-full py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-colors"
                >
                  <Receipt className="w-4 h-4" /> Oxirgi xaridlarim
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Kartam drawer */}
      {showCard && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowCard(false)} />
          <div className="relative w-full bg-white rounded-t-3xl max-h-[85vh] flex flex-col animate-[slideUp_0.25s_ease-out]">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-800">🎫 Mening kartam</h2>
              <button onClick={() => setShowCard(false)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {!meData ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
              </div>
            ) : (
              <div className="px-5 py-5 pb-8">
                <div className="rounded-2xl p-5 bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-lg">
                  <p className="text-xs text-blue-100 mb-4">{shopName}</p>
                  <p className="text-xl font-mono tracking-widest mb-1">
                    {(meData.card_number || '').replace(/(\d{4})(?=\d)/g, '$1 ')}
                  </p>
                  <div className="flex items-center justify-between mt-4">
                    <p className="text-sm font-medium">{meData.name}</p>
                    {meData.cashback_percent > 0 && (
                      <p className="text-xs bg-white/20 rounded-full px-2 py-1">🔄 {meData.cashback_percent}%</p>
                    )}
                  </div>
                </div>

                <button
                  onClick={copyCardNumber}
                  className="w-full mt-4 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-colors"
                >
                  <Copy className="w-4 h-4" /> {copied ? 'Nusxalandi!' : 'Raqamni nusxalash'}
                </button>
                <p className="text-xs text-slate-400 text-center mt-3">
                  Kassirga shu karta raqamini ko'rsating — naqd pul yig'asiz
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Xaridlar tarixi drawer */}
      {showPurchases && (
        <div className="fixed inset-0 z-50 flex items-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowPurchases(false)} />
          <div className="relative w-full bg-white rounded-t-3xl max-h-[85vh] flex flex-col animate-[slideUp_0.25s_ease-out]">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-800">🧾 Xaridlarim</h2>
              <button onClick={() => setShowPurchases(false)} className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            {purchasesLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
              </div>
            ) : purchases.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16 text-slate-400">
                <Receipt className="w-10 h-10" />
                <p className="text-sm">Xarid tarixi yo'q</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto px-5 py-3 space-y-2 pb-6">
                {purchases.map(p => (
                  <div key={p.id} className="flex items-center justify-between border border-slate-100 rounded-xl px-3 py-2.5">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{fmt(p.total_amount)} so'm</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">{fmtDate(p.created_at)}</p>
                      {p.debt_due_date && (
                        <p className="text-[11px] text-red-500 mt-0.5">Muddat: {new Date(p.debt_due_date).toLocaleDateString('uz-UZ')}</p>
                      )}
                    </div>
                    <span className="text-[11px] px-2 py-1 rounded-full bg-slate-100 text-slate-600 font-medium">
                      {p.payment_type}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        @keyframes slideInLeft { from { transform: translateX(-100%); } to { transform: translateX(0); } }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      `}</style>
    </div>
  )
}
