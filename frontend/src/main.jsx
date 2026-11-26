import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { LangProvider } from './context/LangContext.jsx'
import { getStoredLang, loadLang } from './i18n/index.js'

// Saqlangan til (ru/en) lug'ati ilova chizilishidan oldin yuklanadi — uz sukut, kutilmaydi
loadLang(getStoredLang()).finally(() => {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <LangProvider>
        <App />
      </LangProvider>
    </StrictMode>,
  )
})
