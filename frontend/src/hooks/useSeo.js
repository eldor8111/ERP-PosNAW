import { useEffect } from 'react'

/**
 * Sahifa title va meta description ni dinamik ravishda o'rnatadi
 * @param {string} title - Sahifa sarlavhasi
 * @param {string} description - Meta description matni
 */
export function useSeo(title, description) {
  useEffect(() => {
    if (title) {
      document.title = title
    }
    if (description) {
      let meta = document.querySelector('meta[name="description"]')
      if (meta) {
        meta.setAttribute('content', description)
      }
    }
    return () => {
      document.title = "E-code – ERP, POS, Veb Sayt va Telegram Bot Yechimlari | O'zbekiston"
    }
  }, [title, description])
}
