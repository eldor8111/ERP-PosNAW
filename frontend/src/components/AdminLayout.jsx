import { useState, useEffect, useCallback, useMemo } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';
import { ROLES, ROLE_GROUPS, ROLE_LABELS, ROLE_GRADIENTS } from '../constants/roles';

const navGroups = [
  {
    label: 'Asosiy',
    links: [
      {
        name: 'Dashboard',
        path: '/admin/dashboard',
        roles: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER],
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>,
      },
    ],
  },
  {
    label: 'Savdo',
    links: [
      {
        name: 'Sotuv va Mijozlar',
        path: '/admin/sotuv-mijozlar',
        roles: ROLE_GROUPS.SALES,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>,
      },
      {
        name: 'POS (Chakana)',
        path: '/admin/pos-kassa',
        roles: ROLE_GROUPS.SALES,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>,
      },
      {
        name: 'Smenalar',
        path: '/admin/shifts',
        roles: ROLE_GROUPS.SALES,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
      },
    ],
  },
  {
    label: 'Mahsulot va Ombor',
    links: [
      {
        name: 'Mahsulotlar',
        path: '/admin/products',
        roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>,
      },
      {
        name: "Xarid va Ta'minotchilar",
        path: '/admin/purchases',
        roles: ROLE_GROUPS.REPORTS_ACCESS,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>,
      },
      {
        name: "Ombor va Ko'chirish",
        path: '/admin/warehouse',
        roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" /></svg>,
      },
      {
        name: 'Operatsiyalar',
        path: '/admin/operations',
        roles: ROLE_GROUPS.OPS_ACCESS,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>,
      },
    ],
  },
  {
    label: 'Moliya va Tahlil',
    links: [
      {
        name: 'Moliya va Kassa',
        path: '/admin/finance',
        roles: ROLE_GROUPS.FINANCE_ACCESS,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
      },
      {
        name: 'Hisobotlar',
        path: '/admin/reports',
        roles: ROLE_GROUPS.REPORTS_ACCESS,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>,
      },
    ],
  },
  {
    label: 'Boshqaruv',
    links: [
      {
        name: 'Foydalanuvchilar',
        path: '/admin/users',
        roles: ROLE_GROUPS.MANAGEMENT,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>,
      },
      {
        name: 'Sozlamalar',
        path: '/admin/settings',
        roles: ROLE_GROUPS.MANAGEMENT,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
      },
      {
        name: 'Tariflar',
        path: '/admin/tariflar',
        roles: ROLE_GROUPS.MANAGEMENT,
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>,
      },
    ],
  },
  {
    label: 'Admin',
    links: [
      {
        name: 'Korxonalar',
        path: '/admin/super-admin',
        roles: [ROLES.SUPER_ADMIN],
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>,
      },
      {
        name: 'Agentlar',
        path: '/admin/agents',
        roles: [ROLES.SUPER_ADMIN],
        icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>,
      },
    ],
  },
];

const fmt = (n) => Number(n || 0).toLocaleString('ru-RU');

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const [orgData, setOrgData] = useState({ name: user?.company_name || 'Tizim', code: '...', balance: 0 });
  const [lowStockCount, setLowStockCount] = useState(0);

  const refreshBalance = useCallback(() => {
    api.get('/finance/cash-balance').then(r => {
      setOrgData({
        name: r.data.company_name || 'Tizim',
        code: r.data.org_code || '-',
        balance: r.data.balance || 0
      });
    }).catch(() => {});
  }, []);

  const refreshLowStock = useCallback(() => {
    api.get('/inventory/low-stock-count').then(r => {
      setLowStockCount(r.data.count || 0);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    refreshBalance();
    refreshLowStock();
    const interval = setInterval(refreshBalance, 60000);
    const lowStockInterval = setInterval(refreshLowStock, 300000);
    window.addEventListener('balance-updated', refreshBalance);
    return () => {
      clearInterval(interval);
      clearInterval(lowStockInterval);
      window.removeEventListener('balance-updated', refreshBalance);
    };
  }, [refreshBalance, refreshLowStock]);

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  const currentPage = useMemo(() => {
    const allLinks = navGroups.flatMap(g => g.links);
    const currentLink = allLinks.find(l => location.pathname.startsWith(l.path));
    return currentLink?.name || 'ERP System';
  }, [location.pathname]);

  const initials = useMemo(() =>
    user?.name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'U'
  , [user?.name]);

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden">

      {/* ── SIDEBAR ─────────────────────────────────── */}
      <aside
        className={`${collapsed ? 'w-[60px]' : 'w-[220px]'} bg-white border-r border-slate-200 flex flex-col shrink-0 transition-all duration-300 ease-in-out`}
        style={{ boxShadow: '1px 0 12px rgba(0,0,0,0.06)' }}
      >
        {/* Logo */}
        <div className={`flex items-center ${collapsed ? 'justify-center px-2 py-3.5' : 'justify-between px-4 py-3.5'} border-b border-slate-100`}>
          {!collapsed && (
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-200 shrink-0">
                <span className="text-white font-black text-[10px] tracking-tight">UBT</span>
              </div>
              <div>
                <span className="text-[13px] font-bold text-slate-800 leading-none block">UBT</span>
                <span className="text-[10px] text-slate-400 leading-none">{user?.company_name || 'System'}</span>
              </div>
            </div>
          )}
          {collapsed && (
            <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-200">
              <span className="text-white font-black text-[11px] tracking-tight">UBT</span>
            </div>
          )}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              className="w-7 h-7 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 flex items-center justify-center transition-all shrink-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}
          {collapsed && (
            <button
              onClick={() => setCollapsed(false)}
              className="absolute left-[52px] top-[20px] w-6 h-6 rounded-full bg-white border border-slate-200 text-slate-400 hover:text-indigo-600 flex items-center justify-center transition-all shadow-md z-50"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav
          className="flex-1 overflow-y-auto py-3 px-3 space-y-0.5"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {navGroups.map((group) => {
            const visibleLinks = group.links.filter(link => user && link.roles.includes(user.role));
            if (!visibleLinks.length) return null;
            return (
              <div key={group.label} className="mb-1">
                {!collapsed && (
                  <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest px-2 pt-2.5 pb-1 select-none">
                    {group.label}
                  </p>
                )}
                {collapsed && <div className="border-t border-slate-100 my-2 mx-1" />}

                {visibleLinks.map((link) => {
                  const isActive = location.pathname.startsWith(link.path);
                  return (
                    <Link
                      key={link.path}
                      to={link.path}
                      title={collapsed ? link.name : undefined}
                      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg transition-all duration-150 group mb-0.5 ${
                        isActive
                          ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
                      } ${collapsed ? 'justify-center' : ''}`}
                    >
                      <span className={`shrink-0 relative [&>svg]:w-[16px] [&>svg]:h-[16px] ${isActive ? 'text-white' : 'text-slate-500 group-hover:text-slate-700'}`}>
                        {link.icon}
                        {collapsed && link.path === '/admin/warehouse' && lowStockCount > 0 && (
                          <span className="absolute -top-1 -right-1 w-2 h-2 bg-rose-500 rounded-full" />
                        )}
                      </span>
                      {!collapsed && (
                        <span className={`text-[12px] font-medium truncate flex-1 ${isActive ? 'font-semibold' : ''}`}>
                          {link.name}
                        </span>
                      )}
                      {!collapsed && link.path === '/admin/warehouse' && lowStockCount > 0 && (
                        <span className={`min-w-[18px] h-[18px] px-1 text-white text-[10px] font-bold rounded-full flex items-center justify-center shrink-0 ${isActive ? 'bg-white/30' : 'bg-rose-500'}`}>
                          {lowStockCount > 99 ? '99+' : lowStockCount}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>

        {/* Bottom: User + Logout */}
        <div className="border-t border-slate-100 p-3 space-y-1">
          {/* User info */}
          {!collapsed && (
            <div className="flex items-center gap-2.5 px-2 py-2 rounded-xl bg-slate-50">
              <div className={`w-8 h-8 rounded-xl bg-linear-to-br ${ROLE_GRADIENTS[user?.role] || 'from-indigo-500 to-indigo-700'} flex items-center justify-center text-white text-xs font-bold shrink-0`}>
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-semibold text-slate-800 truncate leading-none mb-0.5">{user?.name}</p>
                <p className="text-[11px] text-slate-400 truncate leading-none">{ROLE_LABELS[user?.role] || user?.role}</p>
              </div>
            </div>
          )}
          {collapsed && (
            <div className="flex justify-center py-1">
              <div className={`w-8 h-8 rounded-xl bg-linear-to-br ${ROLE_GRADIENTS[user?.role] || 'from-indigo-500 to-indigo-700'} flex items-center justify-center text-white text-xs font-bold`}>
                {initials}
              </div>
            </div>
          )}

          {/* Logout */}
          <button
            onClick={handleLogout}
            title="Chiqish"
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-rose-500 hover:bg-rose-50 hover:text-rose-600 transition-all duration-150 ${collapsed ? 'justify-center' : ''}`}
          >
            <svg className="w-[18px] h-[18px] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {!collapsed && <span className="text-[13px] font-semibold">Chiqish</span>}
          </button>
        </div>
      </aside>

      {/* ── MAIN CONTENT ─────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top Header */}
        <header className="bg-white border-b border-slate-100 px-6 py-3.5 flex items-center justify-between shrink-0" style={{ boxShadow: '0 1px 8px rgba(0,0,0,0.05)' }}>
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-[15px] font-bold text-slate-800 leading-none">{currentPage}</h1>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {new Date().toLocaleDateString('uz-UZ', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Tizim faol */}
            <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-100 rounded-full px-3 py-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-700 text-xs font-medium">Tizim faol</span>
            </div>

            {/* Kam qoldiq */}
            {lowStockCount > 0 && (
              <button
                onClick={() => navigate('/admin/warehouse')}
                className="relative flex items-center gap-1.5 bg-amber-50 border border-amber-200 rounded-full px-3 py-1.5 hover:bg-amber-100 transition-colors cursor-pointer"
                title={`${lowStockCount} ta mahsulot kam qoldiqda`}
              >
                <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
                <span className="text-amber-700 text-xs font-semibold">Kam qoldiq</span>
                <span className="min-w-[18px] h-[18px] px-1 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                  {lowStockCount > 99 ? '99+' : lowStockCount}
                </span>
              </button>
            )}

            {/* Org kodi */}
            <div className="flex flex-col items-center bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-1.5 min-w-[90px]">
              <span className="text-slate-400 text-[10px] font-semibold leading-none mb-0.5 uppercase tracking-wide">Kod</span>
              <span className="text-slate-700 text-[14px] font-black leading-none tracking-wide">{orgData.code}</span>
            </div>

            {/* Balans */}
            <div className="flex flex-col items-center bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-1.5 min-w-[90px]">
              <span className="text-emerald-500 text-[10px] font-semibold leading-none mb-0.5 uppercase tracking-wide">Balans</span>
              <span className="text-emerald-700 text-[14px] font-black leading-none tracking-wide">{fmt(orgData.balance)} s</span>
            </div>

            {/* User */}
            <div className="flex items-center gap-2.5 bg-indigo-600 rounded-xl px-3.5 py-2 shadow-md shadow-indigo-200">
              <div className="w-7 h-7 rounded-lg bg-white/20 flex items-center justify-center text-white text-[11px] font-black shrink-0">
                {initials}
              </div>
              <div className="flex flex-col">
                <span className="text-white text-[12px] font-bold leading-none">{orgData.name}</span>
                <span className="text-indigo-200 text-[10px] font-medium leading-none mt-0.5">{ROLE_LABELS[user?.role] || user?.role}</span>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className={`flex-1 overflow-x-hidden overflow-y-auto bg-slate-50 ${location.pathname.startsWith('/admin/pos-kassa') ? '' : 'p-6'}`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
