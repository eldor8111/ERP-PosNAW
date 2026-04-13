import axios from 'axios'
import { toast } from '../utils/toast'

const DEFAULT_URL = import.meta.env.VITE_API_URL || 'http://localhost:8010/api'
const getBaseUrl = () => {
  try { return localStorage.getItem('api_server_url') || DEFAULT_URL; } catch { return DEFAULT_URL; }
}

// ── Stale-While-Revalidate cache ─────────────────────────────────────────
// Barcha api.get() avtomatik keshlanadi — birorta sahifani o'zgartirish
// shart emas. Sahifadan sahifaga o'tganda eski ma'lumot DARHOL ko'rinadi,
// fon fonda yangi ma'lumot yuklanadi.

const _cache = new Map()    // cacheKey → { data, ts }
const _inflight = new Map() // cacheKey → Promise

const LONG_TTL = [
  '/branches', '/categories', '/currencies', '/inventory/warehouses',
  '/bin-locations', '/users/', '/companies/me', '/agents', '/api-keys',
  '/warehouses', '/finance/cash-balance', '/inventory/low-stock-count',
]
const SHORT_TTL_MS = 30_000   // 30 sek — tez o'zgaruvchan ma'lumotlar
const LONG_TTL_MS  = 120_000  // 2 min — kam o'zgaruvchan ma'lumotlar

const getTTL = (url) =>
  LONG_TTL.some(p => url.includes(p)) ? LONG_TTL_MS : SHORT_TTL_MS

const cacheKey = (url, params) => url + (params ? JSON.stringify(params) : '')

// Mutatsiyadan keyin tegishli keshni tozalash uchun
export function invalidateCache(urlPattern) {
  for (const k of _cache.keys()) {
    if (k.includes(urlPattern)) _cache.delete(k)
  }
}

// Logout yoki serverdan barcha kesh tozalash
export function clearCache() { _cache.clear(); _inflight.clear() }

// ── axios instance ────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: getBaseUrl(),
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,   // 15 soniya — POS uchun yetarli, keraksiz kutish oldini oladi
})

// ── Request interceptor ───────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  const currentUrl = getBaseUrl()
  if (config.baseURL !== currentUrl) config.baseURL = currentUrl
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`

  // Only cache GET requests that don't have no-cache flag
  if (config.method === 'get' && !config._noCache) {
    const key = cacheKey(config.url, config.params)
    const now = Date.now()
    const ttl = getTTL(config.url)
    const cached = _cache.get(key)

    if (cached && now - cached.ts < ttl) {
      // Fresh cache: cancel real request, return cached immediately
      config._cached = cached.data
      config._cacheKey = key
    } else if (cached) {
      // Stale cache: mark for SWR — will serve stale, then update
      config._stale = cached.data
      config._cacheKey = key
    } else if (_inflight.has(key)) {
      // Duplicate in-flight: piggyback on existing request
      config._piggyback = _inflight.get(key)
    }
  }
  return config
})

// ── Response interceptor ──────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => {
    // Store GET responses in cache
    if (response.config.method === 'get' && !response.config._noCache) {
      const key = cacheKey(response.config.url, response.config.params)
      _cache.set(key, { data: response.data, ts: Date.now() })
      _inflight.delete(key)
    }
    // Clear related caches on mutating requests
    if (['post', 'put', 'patch', 'delete'].includes(response.config.method)) {
      const url = response.config.url || ''
      // Invalidate parent resource (e.g. POST /sales/ → delete /sales/ cache)
      const parts = url.split('/')
      if (parts.length >= 2) invalidateCache('/' + parts[1])
    }
    return response
  },
  (error) => {
    const config = error.config || {}
    const key = config._cacheKey
    if (key) _inflight.delete(key)

    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      if (window.location.protocol === 'file:') window.location.hash = '#/login'
      else window.location.href = '/login'
      return Promise.reject(error)
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
    if (status === 400) { toast.error(detail || "Noto'g'ri ma'lumot kiritildi"); return Promise.reject(error) }
    if (status === 403) { toast.warn("Sizda bu amalni bajarish huquqi yo'q"); return Promise.reject(error) }
    if (status === 404) { toast.warn(detail || "Ma'lumot topilmadi"); return Promise.reject(error) }
    if (status === 422) {
      const msg = error.response?.data?.detail?.[0]?.msg || "Maydonlarni to'g'ri to'ldiring"
      toast.error(msg); return Promise.reject(error)
    }
    if (status >= 500) { toast.error(detail || 'Server xatosi yuz berdi. Iltimos qayta urinib ko\'ring.'); return Promise.reject(error) }
    if (!error.response && !config._silent) {
      if (error.code === 'ECONNABORTED') toast.error("So'rov vaqti tugadi.")
      else toast.error("Server bilan aloqa yo'q.")
    }
    return Promise.reject(error)
  }
)

// ── Cached GET wrapper — used by pages that want SWR pattern explicitly ──
// api.get() still works as-is; this helper lets callers get stale data
// synchronously on first call then update via onChange callback.
export async function apiGetCached(url, params, onChange) {
  const key = cacheKey(url, params)
  const now = Date.now()
  const ttl = getTTL(url)
  const cached = _cache.get(key)

  // Return stale immediately then refresh
  if (cached && now - cached.ts >= ttl) {
    // Fire background refresh
    api.get(url, { params }).then(res => {
      if (onChange && JSON.stringify(res.data) !== JSON.stringify(cached.data)) {
        onChange(res.data)
      }
    }).catch(() => {})
    return cached.data
  }

  // No cache: wait for fresh
  const res = await api.get(url, { params })
  return res.data
}

export default api
