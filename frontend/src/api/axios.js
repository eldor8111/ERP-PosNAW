import axios from 'axios'
import { toast } from '../utils/toast'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

// Har so'rovga token qo'shish
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Global xatolarni boshqarish
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      if (window.location.protocol === 'file:') {
        window.location.hash = '#/login'
      } else {
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }

    // 400 — validation xato
    if (status === 400) {
      toast.error(detail || 'Noto\'g\'ri ma\'lumot kiritildi')
      return Promise.reject(error)
    }

    // 403 — huquq yo'q
    if (status === 403) {
      toast.warn("Sizda bu amalni bajarish huquqi yo'q")
      return Promise.reject(error)
    }

    // 404 — topilmadi
    if (status === 404) {
      toast.warn(detail || 'Ma\'lumot topilmadi')
      return Promise.reject(error)
    }

    // 422 — FastAPI validation xato
    if (status === 422) {
      const msg = error.response?.data?.detail?.[0]?.msg || 'Maydonlarni to\'g\'ri to\'ldiring'
      toast.error(msg)
      return Promise.reject(error)
    }

    // 500 — server xatosi
    if (status >= 500) {
      toast.error(detail || 'Server xatosi yuz berdi. Iltimos qayta urinib ko\'ring.')
      return Promise.reject(error)
    }

    // Tarmoq uzilishi yoki timeout
    if (!error.response) {
      if (error.code === 'ECONNABORTED') {
        toast.error('So\'rov vaqti tugadi. Internet aloqasini tekshiring.')
      } else {
        toast.error('Server bilan aloqa yo\'q. Internet aloqasini tekshiring.')
      }
    }

    return Promise.reject(error)
  }
)

export default api
