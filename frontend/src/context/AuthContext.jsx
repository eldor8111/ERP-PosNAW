import { createContext, useContext, useState, useMemo, useCallback } from 'react'
import api, { clearCache } from '../api/axios'

const AuthContext = createContext(null)

const POS_CACHE_KEYS = [
  'pos_cache_products',
  'pos_cache_customers',
  'pos_cache_categories',
  'pos_pending_sales',
  'pos_pending_returns',
]

function clearPosCache() {
  POS_CACHE_KEYS.forEach(k => localStorage.removeItem(k))
  clearCache()
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('user')
    return saved ? JSON.parse(saved) : null
  })

  const login = useCallback(async (phone, password) => {
    const res = await api.post('/auth/login', { phone, password })
    if (res.status === 202) {
      const err = new Error('OTP Required')
      err.response = res
      throw err
    }
    const { data } = res
    // Eski foydalanuvchi keshini tozalaymiz — boshqa korxona ma'lumotlari qolmasin
    clearPosCache()
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    clearPosCache()
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext)
