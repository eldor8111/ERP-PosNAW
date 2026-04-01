/**
 * Kutubxonasiz global toast utility.
 * Axios interceptor va ixtiyoriy joydan chaqiriladi,
 * Toast.jsx komponenti esa subscribe qilib, ekranda ko'rsatadi.
 */
const listeners = new Set()

export const toast = {
  error: (message) => listeners.forEach(fn => fn({ type: 'error', message })),
  warn: (message)  => listeners.forEach(fn => fn({ type: 'warn',  message })),
  info: (message)  => listeners.forEach(fn => fn({ type: 'info',  message })),
  subscribe: (fn)  => {
    listeners.add(fn)
    return () => listeners.delete(fn)   // unsubscribe funksiyasini qaytaradi
  },
}
