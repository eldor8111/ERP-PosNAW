import { lazy, Suspense } from 'react'
import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import PrivateRoute from './components/PrivateRoute'
import { ROLE_GROUPS } from './constants/roles'
import Toast from './components/Toast'
import Login from './pages/Login'
import PosLogin from './pages/PosLogin'
import RegisterCompany from './pages/RegisterCompany'
import AdminLayout from './components/AdminLayout'

// Lazy-loaded pages — faqat kerak bo'lganda yuklanadi
const Dashboard       = lazy(() => import('./pages/admin/Dashboard'))
const Products        = lazy(() => import('./pages/admin/Products'))
const Purchases       = lazy(() => import('./pages/admin/Purchases'))
const Warehouse       = lazy(() => import('./pages/admin/Warehouse'))
const InventoryCounts = lazy(() => import('./pages/admin/InventoryCounts'))
const Finance         = lazy(() => import('./pages/admin/Finance'))
const Reports         = lazy(() => import('./pages/admin/Reports'))
const Customers       = lazy(() => import('./pages/admin/Customers'))
const CustomerDetail  = lazy(() => import('./pages/admin/CustomerDetail'))
const SotuvMijozlar   = lazy(() => import('./pages/admin/SotuvMijozlar'))
const UlgurjiSotuv   = lazy(() => import('./pages/admin/UlgurjiSotuv'))
const PosKassa        = lazy(() => import('./pages/admin/PosKassa'))
const PosReturn       = lazy(() => import('./pages/admin/PosReturn'))
const Operations      = lazy(() => import('./pages/admin/Operations'))
const Settings        = lazy(() => import('./pages/admin/Settings'))
const MobileDashboard = lazy(() => import('./pages/admin/MobileDashboard'))
const Users           = lazy(() => import('./pages/admin/Users'))
const Shifts          = lazy(() => import('./pages/admin/Shifts'))
const SuperAdmin      = lazy(() => import('./pages/admin/SuperAdmin'))
const AgentsPage      = lazy(() => import('./pages/admin/SuperAdmin').then(m => ({ default: m.AgentsPage })))
const Ombor           = lazy(() => import('./pages/admin/Ombor'))
const Tariflar        = lazy(() => import('./pages/admin/Tariflar'))
const Register        = lazy(() => import('./pages/Register'))
const Landing         = lazy(() => import('./pages/Landing'))
const ERPTizim        = lazy(() => import('./pages/ERPTizim'))
const VebSaytlar      = lazy(() => import('./pages/VebSaytlar'))
const TelegramBotlar  = lazy(() => import('./pages/TelegramBotlar'))
const NoyobDasturlar  = lazy(() => import('./pages/NoyobDasturlar'))
const ChaqqonPro      = lazy(() => import('./pages/ChaqqonPro'))
const Aloqa           = lazy(() => import('./pages/Aloqa'))

// Sahifa almashinayotganda ko'rinadigan loading spinner
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="relative">
        <div className="w-10 h-10 border-4 border-indigo-100 rounded-full" />
        <div className="absolute inset-0 w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    </div>
  )
}

export default function App() {
  const Router = window.location.protocol === 'file:' ? HashRouter : BrowserRouter

  return (
    <Router>
      <Toast />
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/pos-login" element={<PosLogin />} />
          <Route path="/register" element={<RegisterCompany />} />

          <Route path="/admin" element={
            <PrivateRoute roles={ROLE_GROUPS.ALL_STAFF}>
              <AdminLayout />
            </PrivateRoute>
          }>
            <Route path="dashboard" element={<Suspense fallback={<PageLoader />}><Dashboard /></Suspense>} />
            <Route path="products" element={<Suspense fallback={<PageLoader />}><Products /></Suspense>} />
            <Route path="purchases" element={<Suspense fallback={<PageLoader />}><Purchases /></Suspense>} />
            <Route path="warehouse" element={<Suspense fallback={<PageLoader />}><Warehouse /></Suspense>} />
            <Route path="inventory-counts" element={<Suspense fallback={<PageLoader />}><InventoryCounts /></Suspense>} />
            <Route path="finance" element={<Suspense fallback={<PageLoader />}><Finance /></Suspense>} />
            <Route path="reports" element={<Suspense fallback={<PageLoader />}><Reports /></Suspense>} />
            <Route path="customers" element={<Suspense fallback={<PageLoader />}><Customers /></Suspense>} />
            <Route path="customers/:customerId" element={<Suspense fallback={<PageLoader />}><CustomerDetail /></Suspense>} />
            <Route path="sotuv-mijozlar" element={<Suspense fallback={<PageLoader />}><SotuvMijozlar /></Suspense>} />
            <Route path="ulgurji-sotuv" element={<Suspense fallback={<PageLoader />}><UlgurjiSotuv /></Suspense>} />
            <Route path="pos-kassa" element={<Suspense fallback={<PageLoader />}><PosKassa /></Suspense>} />
            <Route path="pos-return" element={<Suspense fallback={<PageLoader />}><PosReturn /></Suspense>} />
            <Route path="operations" element={<Suspense fallback={<PageLoader />}><Operations /></Suspense>} />
            <Route path="settings" element={<Suspense fallback={<PageLoader />}><Settings /></Suspense>} />
            <Route path="mobile" element={<Suspense fallback={<PageLoader />}><MobileDashboard /></Suspense>} />
            <Route path="users" element={<Suspense fallback={<PageLoader />}><Users /></Suspense>} />
            <Route path="shifts" element={<Suspense fallback={<PageLoader />}><Shifts /></Suspense>} />
            <Route path="super-admin" element={<Suspense fallback={<PageLoader />}><SuperAdmin /></Suspense>} />
            <Route path="agents" element={<Suspense fallback={<PageLoader />}><AgentsPage /></Suspense>} />
            <Route path="ombor" element={<Suspense fallback={<PageLoader />}><Ombor /></Suspense>} />
            <Route path="tariflar" element={<Suspense fallback={<PageLoader />}><Tariflar /></Suspense>} />
            <Route path="users/create" element={
              <PrivateRoute roles={ROLE_GROUPS.MANAGEMENT}>
                <Suspense fallback={<PageLoader />}><Register /></Suspense>
              </PrivateRoute>
            } />
          </Route>
                      
          <Route path="/" element={
            window.location.hostname.startsWith('savdo.') || window.location.hostname.includes('biznes') 
            ? <Navigate to="/login" replace /> 
            : <Suspense fallback={<PageLoader />}><Landing /></Suspense>
          } />
          <Route path="/erp-tizim" element={<Suspense fallback={<PageLoader />}><ERPTizim /></Suspense>} />
          <Route path="/veb-saytlar" element={<Suspense fallback={<PageLoader />}><VebSaytlar /></Suspense>} />
          <Route path="/telegram-botlar" element={<Suspense fallback={<PageLoader />}><TelegramBotlar /></Suspense>} />
          <Route path="/noyob-dasturlar" element={<Suspense fallback={<PageLoader />}><NoyobDasturlar /></Suspense>} />
          <Route path="/chaqqon-pro" element={<Suspense fallback={<PageLoader />}><ChaqqonPro /></Suspense>} />
          <Route path="/aloqa" element={<Suspense fallback={<PageLoader />}><Aloqa /></Suspense>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </Router>
  )
}
