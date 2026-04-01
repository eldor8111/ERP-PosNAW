import { useState, useEffect } from 'react'
import { toast } from '../utils/toast'

const ICONS = {
  error: (
    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  warn: (
    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
    </svg>
  ),
  info: (
    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
}

const STYLES = {
  error: 'bg-red-50 border-red-200 text-red-700',
  warn:  'bg-amber-50 border-amber-200 text-amber-700',
  info:  'bg-blue-50 border-blue-200 text-blue-700',
}

export default function Toast() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    return toast.subscribe(({ type, message }) => {
      const id = Date.now() + Math.random()
      setToasts(prev => [...prev.slice(-4), { id, type, message }])  // max 5 ta
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, 4500)
    })
  }, [])

  if (!toasts.length) return null

  return (
    <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 w-80 pointer-events-none">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`flex items-start gap-2.5 px-4 py-3 rounded-xl border shadow-lg text-sm font-medium
            pointer-events-auto animate-in slide-in-from-right-4 ${STYLES[t.type]}`}
        >
          {ICONS[t.type]}
          <span className="leading-snug">{t.message}</span>
        </div>
      ))}
    </div>
  )
}
