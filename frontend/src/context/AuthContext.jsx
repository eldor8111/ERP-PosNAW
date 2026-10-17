import { createContext, useContext, useState, useMemo, useCallback } from 'react'
import api, { clearCache, setCurrentBranchId } from '../api/axios'
import { migrateLegacyQueue } from '../utils/posQueue'
import { invalidateBranches } from '../hooks/useBranches'

const AuthContext = createContext(null)

// Faqat kesh kalitlari. Oflayn navbat (pos_pending_*:<companyId>) bu yerga KIRMAYDI —
// chiqish/kirishda yuborilmagan sotuvlar o'chib ketmasin (T3.11, utils/posQueue.js).
const POS_CACHE_KEYS = [
  'pos_cache_products',
  'pos_cache_customers',
  'pos_cache_categories',
]

function clearPosCache() {
  POS_CACHE_KEYS.forEach(k => localStorage.removeItem(k))
  clearCache()
}

function readStoredUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null') } catch { return null }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('user')
    return saved ? JSON.parse(saved) : null
  })

  // Token + user javobini qo'llaydi (login va /auth/select-company uchun umumiy, T1.2).
  // Keshni tozalaydi. Oflayn navbat korxona bo'yicha kalitlanadi (pos_pending_sales:<id>) —
  // korxona almashganda eski korxona navbati o'chmaydi va yangi token bilan yuborilmaydi (T3.11).
  const applyAuthResponse = useCallback((data) => {
    const nextUser = data.user
    const prev = readStoredUser()
    // Eski (korxonasiz) navbat kaliti bo'lsa — avvalgi korxonaga ko'chiramiz, yangisiga emas
    if (prev?.company_id != null) migrateLegacyQueue(prev.company_id)
    // Eski foydalanuvchi keshini tozalaymiz — boshqa korxona ma'lumotlari qolmasin.
    clearPosCache()
    setCurrentBranchId(null) // boshqa korxona filiali X-Branch-Id sifatida ketmasin
    localStorage.setItem('access_token', data.access_token)
    if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('user', JSON.stringify(nextUser))
    invalidateBranches() // T3.8: korxona/foydalanuvchi almashdi — eski filiallar keshi qolmasin
    setUser(nextUser)
    return nextUser
  }, [])

  const login = useCallback(async (phone, password) => {
    const res = await api.post('/auth/login', { phone, password })
    if (res.status === 202) {
      const err = new Error('OTP Required')
      err.response = res
      throw err
    }
    const { data } = res

    if (data.needs_company_selection) {
      // Eski foydalanuvchi keshini bu yerda ham tozalaymiz (T1.2). Oflayn navbat tegilmaydi.
      clearPosCache()
      return data // UI da tanlash uchun ob'ektni qaytaramiz
    }

    return applyAuthResponse(data)
  }, [applyAuthResponse])

  // Ko'p korxonali foydalanuvchi: login() qaytargan temp_token bilan korxona tanlash (T3.11)
  const selectCompany = useCallback(async (tempToken, companyId) => {
    const res = await api.post('/auth/select-company', { temp_token: tempToken, company_id: companyId })
    return applyAuthResponse(res.data)
  }, [applyAuthResponse])

  const logout = useCallback(() => {
    // Eski korxonasiz navbat chiqishdan oldin shu foydalanuvchi korxonasiga biriktiriladi (boshqa korxonaga o'tib ketmasin)
    migrateLegacyQueue(readStoredUser()?.company_id)
    clearPosCache()
    invalidateBranches() // T3.8: filiallar keshi chiqishda tozalanadi (kesh kaliti baribir user/company bo'yicha)
    // SessionStorage ni ham tozalaymiz — boshqa kompaniyaga kirganda
    // eski kompaniyaning savati, mijozi, pending sale ID si qolmasin
    sessionStorage.removeItem('ulgurji_cart')
    sessionStorage.removeItem('ulgurji_customer')
    sessionStorage.removeItem('ulgurji_session_sale_id')
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    setUser(null)
  }, [])

  // Profil tahrirlangach (ism, email) keshdagi foydalanuvchini yangilaymiz — token va korxona konteksti o'zgarmaydi
  const updateUser = useCallback((patch) => {
    setUser(prev => {
      const next = { ...(prev || {}), ...patch }
      localStorage.setItem('user', JSON.stringify(next))
      return next
    })
  }, [])

  const value = useMemo(() => ({ user, login, logout, updateUser, applyAuthResponse, selectCompany }), [user, login, logout, updateUser, applyAuthResponse, selectCompany])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext)
