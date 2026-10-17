import axios from 'axios'
import { toast } from '../utils/toast'
import { createTranslator, getStoredLang } from '../i18n/index.js'

const DEFAULT_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const getBaseUrl = () => {
  return DEFAULT_URL;
}

// ── Joriy filial (T1.1) ───────────────────────────────────────────────────
// BranchContext boshqaradi; har so'rovga X-Branch-Id header qo'shiladi.
const BRANCH_STORAGE_KEY = 'current_branch_id'
let _currentBranchId = null
try {
  const v = localStorage.getItem(BRANCH_STORAGE_KEY)
  _currentBranchId = v ? (Number(v) || null) : null
} catch { /* localStorage mavjud bo'lmasa */ }
export function getCurrentBranchId() { return _currentBranchId }
export function setCurrentBranchId(id) {
  _currentBranchId = id ? (Number(id) || null) : null
  try {
    if (_currentBranchId) localStorage.setItem(BRANCH_STORAGE_KEY, String(_currentBranchId))
    else localStorage.removeItem(BRANCH_STORAGE_KEY)
  } catch { /* e'tibor bermaymiz */ }
}

// T3.8: o'lik SWR keshi olib tashlandi (u hech qachon keshdan javob bermagan).
// `clearCache` / `invalidateCache` — AuthContext va BranchContext import qilgani uchun
// bo'sh funksiya sifatida qoldirildi.
export function invalidateCache() { /* kesh yo'q */ }
export function clearCache() { /* kesh yo'q */ }

// Interceptor xabarlari tanlangan tilda (T3.5): til har xatoda qayta o'qiladi
const _t = (key) => createTranslator(getStoredLang())(key)

// T4.6: detail obyekt bo'lishi mumkin ({code, message, ...}) — toast'ga faqat matn beriladi
const _detailMsg = (detail) => (detail && typeof detail === 'object' && !Array.isArray(detail) ? detail.message : detail)

// ── Timeout toast deduplikatsiya ─────────────────────────────────────────
// Ko'p parallel so'rovlar bir vaqtda timeout bo'lsa, faqat bitta toast ko'rsatamiz
let _timeoutToastShown = false
let _timeoutToastTimer = null
function _showTimeoutToast() {
  if (_timeoutToastShown) return
  _timeoutToastShown = true
  toast.error(_t('api.error.timeout'))
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
  // T1.1: joriy filial header'i (my-context so'rovi _noBranch bilan header'siz ketadi)
  if (_currentBranchId && !config._noBranch) config.headers['X-Branch-Id'] = String(_currentBranchId)

  // T3.18: X-Hippo-Factory-Id headeri OLIB TASHLANDI. Fiskallash kassir kompyuteridagi lokal ko'prik
  // (hippoLocal.js) orqali tasdiqlash modalidan keyin bajariladi va natija PATCH /sales/{id}/fiscal bilan
  // yoziladi; server ham fiskallasa chek ikki marta fiskallanardi (va "Yo'q" bosilsa ham fiskallanardi).

  return config
})

// ── Response interceptor ──────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => {
    return response
  },
  async (error) => {
    const config = error.config || {}

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
        // Refresh ham ishlamadi — lekin foydalanuvchini majburiy chiqarmaymiz
        _refreshQueue.forEach(q => q.reject(error))
        _refreshQueue = []
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
    if (status === 400 && !config._suppressToast) { toast.error(_detailMsg(detail) || _t('api.error.invalid')); return Promise.reject(error) }
    if (status === 403 && !config._suppressToast) {
      // Tarif limiti (code=TARIFF_LIMIT) — aniq limit matni; boshqa 403 — oddiy "huquq yo'q"
      const isTariffLimit = error.response?.data?.code === 'TARIFF_LIMIT' && typeof detail === 'string' && detail
      // T4.6: tasdiq oqimi (approval_required — modal o'zi ko'rsatadi, toast'siz) va limit (limit_exceeded — ogohlantirish)
      const detailCode = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail.code : null
      if (detailCode === 'approval_required') return Promise.reject(error)
      if (detailCode === 'limit_exceeded' && detail.message) {
        toast.warn(detail.message)
        return Promise.reject(error)
      }
      toast.warn(isTariffLimit ? detail : _t('api.error.forbidden'))
      return Promise.reject(error)
    }
    if (status === 404 && !config._suppressToast) { toast.warn(_detailMsg(detail) || _t('api.error.notFound')); return Promise.reject(error) }
    if (status === 422) {
      const msg = error.response?.data?.detail?.[0]?.msg || _t('api.error.validation')
      toast.error(msg); return Promise.reject(error)
    }
    if (status >= 500) { toast.error(_detailMsg(detail) || _t('api.error.server')); return Promise.reject(error) }
    if (!error.response && !config._silent) {
      if (error.code === 'ECONNABORTED') _showTimeoutToast()
      else toast.error(_t('api.error.network'))
    }
    return Promise.reject(error)
  }
)

export default api
