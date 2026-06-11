import axios from 'axios'
import { toast } from '../utils/toast'

const DEFAULT_URL = import.meta.env.VITE_API_URL || 'http://localhost:8010/api'
const getBaseUrl = () => {
  try { return localStorage.getItem('api_server_url') || DEFAULT_URL; } catch { return DEFAULT_URL; }
}

// ── Stale-While-Revalidate cache ─────────────────────────────────────────
const _cache = new Map()    // cacheKey → { data, ts }
const _inflight = new Map() // cacheKey → Promise

const LONG_TTL = [
  '/branches', '/categories', '/currencies', '/inventory/warehouses',
  '/bin-locations', '/users/', '/companies/me', '/agents', '/api-keys',
  '/warehouses', '/finance/cash-balance', '/inventory/low-stock-count', '/paginated'
]
const SHORT_TTL_MS = 30_000
const LONG_TTL_MS = 120_000

const getTTL = (url) =>
  LONG_TTL.some(p => url.includes(p)) ? LONG_TTL_MS : SHORT_TTL_MS

const cacheKey = (url, params) => url + (params ? JSON.stringify(params) : '')

export function invalidateCache(urlPattern) {
  for (const k of _cache.keys()) {
    if (k.includes(urlPattern)) _cache.delete(k)
  }
}
export function clearCache() { _cache.clear(); _inflight.clear() }

// ── Timeout toast deduplikatsiya ─────────────────────────────────────────
// Ko'p parallel so'rovlar bir vaqtda timeout bo'lsa, faqat bitta toast ko'rsatamiz
let _timeoutToastShown = false
let _timeoutToastTimer = null
function _showTimeoutToast() {
  if (_timeoutToastShown) return
  _timeoutToastShown = true
  toast.error("So'rov vaqti tugadi. Server band, iltimos qayta urinib ko'ring.")
  clearTimeout(_timeoutToastTimer)
  _timeoutToastTimer = setTimeout(() => { _timeoutToastShown = false }, 3000)
}

// ── Token refresh ─────────────────────────────────────────────────────────
// 401 bo'lganda avtomatik refresh qiladi, cart yo'qolmaydi
let _isRefreshing = false
let _refreshQueue = [] // { resolve, reject }[]

async function _tryRefreshToken() {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) return null
  try {
    const res = await axios.post(`${getBaseUrl()}/auth/refresh`, { refresh_token: refreshToken })
    const { access_token, refresh_token: newRefresh } = res.data
    if (access_token) {
      localStorage.setItem('access_token', access_token)
      if (newRefresh) localStorage.setItem('refresh_token', newRefresh)
      return access_token
    }
  } catch {
    // Refresh ham ishlamadi — login sahifasiga o'tamiz
  }
  return null
}

// ── axios instance ────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: getBaseUrl(),
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,   // 30 soniya — og'ir mahsulot qidiruvlari uchun yetarli
})

// ── Request interceptor ───────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  const currentUrl = getBaseUrl()
  if (config.baseURL !== currentUrl) config.baseURL = currentUrl
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`

  if (config.method === 'get' && !config._noCache) {
    const key = cacheKey(config.url, config.params)
    const now = Date.now()
    const ttl = getTTL(config.url)
    const cached = _cache.get(key)

    if (cached && now - cached.ts < ttl) {
      config._cached = cached.data
      config._cacheKey = key
    } else if (cached) {
      config._stale = cached.data
      config._cacheKey = key
    } else if (_inflight.has(key)) {
      config._piggyback = _inflight.get(key)
    } else {
      // In-flight ni kuzatamiz
      let resolveFn
      const p = new Promise(r => { resolveFn = r })
      p._resolve = resolveFn
      _inflight.set(key, p)
      config._cacheKey = key
      config._inflightResolve = resolveFn
    }
  }
  return config
})

// ── Response interceptor ──────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => {
    if (response.config.method === 'get' && !response.config._noCache) {
      const key = cacheKey(response.config.url, response.config.params)
      _cache.set(key, { data: response.data, ts: Date.now() })
      // In-flight ni resolve qilamiz
      const infly = _inflight.get(key)
      if (infly?._resolve) infly._resolve(response.data)
      _inflight.delete(key)
    }
    if (['post', 'put', 'patch', 'delete'].includes(response.config.method)) {
      const url = response.config.url || ''
      const parts = url.split('/')
      if (parts.length >= 2) invalidateCache('/' + parts[1])
    }
    return response
  },
  async (error) => {
    const config = error.config || {}
    const key = config._cacheKey
    if (key) _inflight.delete(key)

    const status = error.response?.status
    const detail = error.response?.data?.detail

    // ── 401: Token yangilashga urinib ko'ramiz ────────────────────────────
    if (status === 401 && !config._isRetry) {
      if (_isRefreshing) {
        // Boshqa so'rov allaqachon refresh qilayapti — navbatda kutatamiz
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject })
        }).then(newToken => {
          config._isRetry = true
          config.headers.Authorization = `Bearer ${newToken}`
          return api(config)
        })
      }

      _isRefreshing = true
      const newToken = await _tryRefreshToken()
      _isRefreshing = false

      if (newToken) {
        // Navbatdagi barcha so'rovlarga yangi token beramiz
        _refreshQueue.forEach(q => q.resolve(newToken))
        _refreshQueue = []
        config._isRetry = true
        config.headers.Authorization = `Bearer ${newToken}`
        return api(config)
      } else {
        // Refresh ham ishlamadi
        _refreshQueue.forEach(q => q.reject(error))
        _refreshQueue = []
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user')
        toast.warn("Sessiya tugadi. Iltimos qayta kiring.")
        setTimeout(() => {
          if (window.location.protocol === 'file:') window.location.hash = '#/login'
          else window.location.href = '/login'
        }, 1500)
        return Promise.reject(error)
      }
    }

    if (status === 402) {
      const path = window.location.pathname
      const onLoginPage = path === '/login' || window.location.hash.includes('/login')
      const onTariflarPage = path.includes('/admin/tariflar')
      if (!onLoginPage && !onTariflarPage) {
        window.location.href = '/admin/tariflar'
      }
      return Promise.reject(error)
    }
    if (status === 400) { if (!config._silent) toast.error(detail || "Noto'g'ri ma'lumot kiritildi"); return Promise.reject(error) }
    if (status === 403) { if (!config._silent) toast.warn("Sizda bu amalni bajarish huquqi yo'q"); return Promise.reject(error) }
    if (status === 404) { if (!config._silent) toast.warn(detail || "Ma'lumot topilmadi"); return Promise.reject(error) }
    if (status === 422) {
      const msg = error.response?.data?.detail?.[0]?.msg || "Maydonlarni to'g'ri to'ldiring"
      if (!config._silent) toast.error(msg); return Promise.reject(error)
    }
    if (status >= 500) { if (!config._silent) toast.error(detail || 'Server xatosi yuz berdi. Iltimos qayta urinib ko\'ring.'); return Promise.reject(error) }
    if (!error.response && !config._silent) {
      if (error.code === 'ECONNABORTED') _showTimeoutToast()
      else toast.error("Server bilan aloqa yo'q.")
    }
    return Promise.reject(error)
  }
)

// ── Cached GET wrapper ────────────────────────────────────────────────────
export async function apiGetCached(url, params, onChange) {
  const key = cacheKey(url, params)
  const now = Date.now()
  const ttl = getTTL(url)
  const cached = _cache.get(key)

  if (cached && now - cached.ts >= ttl) {
    api.get(url, { params }).then(res => {
      if (onChange && JSON.stringify(res.data) !== JSON.stringify(cached.data)) {
        onChange(res.data)
      }
    }).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })
    return cached.data
  }

  const res = await api.get(url, { params })
  return res.data
}

export default api
