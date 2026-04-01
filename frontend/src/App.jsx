import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import PrivateRoute from './components/PrivateRoute'
import { ROLE_GROUPS } from './constants/roles'
import Toast from './components/Toast'
import Login from './pages/Login'
import PosLogin from './pages/PosLogin'
import Register from './pages/Register'
import RegisterCompany from './pages/RegisterCompany'
import AdminLayout from './components/AdminLayout'

import Dashboard from './pages/admin/Dashboard'
import Products from './pages/admin/Products'
import Purchases from './pages/admin/Purchases'
import Warehouse from './pages/admin/Warehouse'
import InventoryCounts from './pages/admin/InventoryCounts'
import Finance from './pages/admin/Finance'
import Reports from './pages/admin/Reports'
import Customers from './pages/admin/Customers'
import SotuvMijozlar from './pages/admin/SotuvMijozlar'
import PosDesktop from './pages/admin/PosDesktop'
import PosReturn from './pages/admin/PosReturn'

import Operations from './pages/admin/Operations'
import Settings from './pages/admin/Settings'
import MobileDashboard from './pages/admin/MobileDashboard'
import Users from './pages/admin/Users'
import Shifts from './pages/admin/Shifts'
import SuperAdmin, { AgentsPage } from './pages/admin/SuperAdmin'
import Ombor from './pages/admin/Ombor'
import CustomerDetail from './pages/admin/CustomerDetail'

export default function App() {
  const Router = window.location.protocol === 'file:' ? HashRouter : BrowserRouter;

  return (
    <Router>
      <Toast />
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/pos-login" element={<PosLogin />} />
          <Route path="/register" element={<RegisterCompany />} />

          {/* ERP Admin Layout Routes */}
          <Route path="/admin" element={
            <PrivateRoute roles={ROLE_GROUPS.ALL_STAFF}>
              <AdminLayout />
            </PrivateRoute>
          }>
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="products" element={<Products />} />
            <Route path="purchases" element={<Purchases />} />
            <Route path="warehouse" element={<Warehouse />} />
            <Route path="inventory-counts" element={<InventoryCounts />} />
            <Route path="finance" element={<Finance />} />
            <Route path="reports" element={<Reports />} />
            <Route path="customers" element={<Customers />} />
            <Route path="customers/:customerId" element={<CustomerDetail />} />
            <Route path="sotuv-mijozlar" element={<SotuvMijozlar />} />
            <Route path="pos-desktop" element={<PosDesktop />} />
            <Route path="pos-return" element={<PosReturn />} />

            <Route path="operations" element={<Operations />} />
            <Route path="settings" element={<Settings />} />
            <Route path="mobile" element={<MobileDashboard />} />
            <Route path="users" element={<Users />} />
            <Route path="shifts" element={<Shifts />} />
            <Route path="super-admin" element={<SuperAdmin />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="ombor" element={<Ombor />} />
            <Route path="users/create" element={
              <PrivateRoute roles={ROLE_GROUPS.MANAGEMENT}>
                <Register />
              </PrivateRoute>
            } />
          </Route>



          <Route path="/" element={<Navigate to="/admin/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </Router>
  )
}
