import axios from 'axios'
import { toast } from '../utils/toast'

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,  // 15 soniyadan keyin timeout
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

    // 403 — huquq yo'q (toast ko'rsatamiz, lekin redirect qilmaymiz)
    if (status === 403) {
      toast.warn("Sizda bu amalni bajarish huquqi yo'q")
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
