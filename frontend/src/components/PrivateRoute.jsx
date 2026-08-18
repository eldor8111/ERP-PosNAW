import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function PrivateRoute({ children, roles }) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) return <Navigate to="/login" replace />

  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/admin" replace />
  }

  // Sahifa bo'yicha ruxsatlarni (permissions) tekshirish
  if (user.role !== 'super_admin' && user.permissions && Object.keys(user.permissions).length > 0) {
    const pathParts = location.pathname.split('/').filter(Boolean);
    // pathParts[0] == 'admin', pathParts[1] == module name (e.g., 'finance', 'customers')
    if (pathParts.length >= 2 && pathParts[0] === 'admin') {
      const permKey = pathParts[1];
      if (user.permissions[permKey] === false) {
        return <Navigate to="/admin" replace />
      }
    }
  }

  return children
}
