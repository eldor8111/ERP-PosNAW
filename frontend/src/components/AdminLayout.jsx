import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LangContext';
import { ROLES, ROLE_GROUPS, ROLE_LABELS, ROLE_GRADIENTS } from '../constants/roles';
import ECodeLogo, { ECodeIcon } from './ECodeLogo';

const fmt = (n) => Number(n || 0).toLocaleString('ru-RU');

function buildNavGroups(t) {
  return [
    {
      key: 'main',
      label: t('nav.main'),
      links: [
        {
          name: t('nav.dashboard'),
          path: '/admin/dashboard',
          roles: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>,
        },
      ],
    },
    {
      key: 'sales_group',
      label: t('nav.sales_group'),
      links: [
        {
          name: t('nav.sales'),
          path: '/admin/sotuv-mijozlar',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>,
        },
        {
          name: t('nav.pos'),
          path: '/admin/pos-kassa',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>,
        },
        {
          name: t('nav.shifts'),
          path: '/admin/shifts',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
        },
      ],
    },
    {
      key: 'warehouse_group',
      label: t('nav.warehouse_group'),
      links: [
        {
          name: t('nav.products'),
          path: '/admin/products',
          roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>,
        },
        {
          name: t('nav.purchases'),
          path: '/admin/purchases',
          roles: ROLE_GROUPS.REPORTS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>,
        },
        {
          name: t('nav.warehouse'),
          path: '/admin/warehouse',
          roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" /></svg>,
        },
        {
          name: t('nav.operations'),
          path: '/admin/operations',
          roles: ROLE_GROUPS.OPS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>,
        },
      ],
    },
    {
      key: 'finance_group',
      label: t('nav.finance_group'),
      links: [
        {
          name: t('nav.finance'),
          path: '/admin/finance',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
        },
        {
          name: t('nav.reports'),
          path: '/admin/reports',
          roles: ROLE_GROUPS.REPORTS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>,
        },
      ],
    },
    {
      key: 'management_group',
      label: t('nav.management_group'),
      links: [
        {
          name: t('nav.users'),
          path: '/admin/users',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>,
        },
        {
          name: t('nav.settings'),
          path: '/admin/settings',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
        },
        {
          name: t('nav.tariffs'),
          path: '/admin/tariflar',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>,
        },
      ],
    },
    {
      key: 'admin_group',
      label: t('nav.admin_group'),
      links: [
        {
          name: t('nav.companies'),
          path: '/admin/super-admin',
          roles: [ROLES.SUPER_ADMIN],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>,
        },
        {
          name: t('nav.agents'),
          path: '/admin/agents',
          roles: [ROLES.SUPER_ADMIN],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>,
        },
      ],
    },
  ];
}

// Language switcher dropdown
function LangSwitcher({ t, lang, setLang, LANGUAGES }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = LANGUAGES.find(l => l.code === lang) || LANGUAGES[0];

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        title={t('header.lang')}
        className="flex items-center gap-1.5 px-3 py-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl transition-all duration-150 group"
      >
        {/* Globe icon */}
        <svg className="w-4 h-4 text-slate-500 group-hover:text-indigo-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
        </svg>
        <span className="text-[11px] font-bold text-slate-600 group-hover:text-indigo-700">{current.short}</span>
        <svg className={`w-3 h-3 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-40 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
          {LANGUAGES.map(l => (
            <button
              key={l.code}
              onClick={() => { setLang(l.code); setOpen(false); }}
              className={`w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm font-medium hover:bg-indigo-50 hover:text-indigo-700 transition-colors ${lang === l.code ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-slate-700'}`}
            >
              <span className="text-base">{l.flag}</span>
              <span>{l.label}</span>
              {lang === l.code && (
                <svg className="w-3.5 h-3.5 ml-auto text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const { t, lang, setLang, LANGUAGES } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Eski localStorage flagni tozalaymiz (oldingi implementatsiyadan qolgan)
  useState(() => { localStorage.removeItem('subscription_expired'); });

  // Obuna muddati — serverdan tekshiriladi (localStorage ishlatilmaydi)
  const [isSubExpired, setIsSubExpired] = useState(false);
  const subExpiredMsg = isSubExpired ? "Obuna muddati tugagan. Iltimos to'lov qiling." : '';

  useEffect(() => {
    if (!user?.company_id || user?.role === 'super_admin') return;
    api.get('/billing/my-company').then(res => {
      const d = res.data;
      // Faqat subscription_ends_at o'rnatilgan VA muddati o'tgan bo'lsa blok
      const expired = d.subscription_ends_at !== null && d.subscription_active === false;
      setIsSubExpired(expired);
      if (expired && !location.pathname.includes('/admin/tariflar')) {
        navigate('/admin/tariflar', { replace: true });
      }
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.company_id]);

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
    if (!ROLE_GROUPS.WAREHOUSE_ACCESS.includes(user?.role)) return;
    api.get('/inventory/low-stock-count').then(r => {
      setLowStockCount(r.data.count || 0);
    }).catch(() => {});
  }, [user?.role]);

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

  // Rebuild navGroups on lang change
  const navGroups = useMemo(() => buildNavGroups(t), [t]);

  const currentPage = useMemo(() => {
    const allLinks = navGroups.flatMap(g => g.links);
    const currentLink = allLinks.find(l => location.pathname.startsWith(l.path));
    return currentLink?.name || 'ERP System';
  }, [location.pathname, navGroups]);

  const initials = useMemo(() =>
    user?.name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'U'
  , [user?.name]);

  // Date locale map
  const dateLocales = { uz: 'uz-UZ', ru: 'ru-RU', en: 'en-US' };

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden relative">

      {/* Mobile Backdrop */}
      {mobileMenuOpen && (
        <div 
          className="lg:hidden fixed inset-0 bg-slate-900/50 z-40 backdrop-blur-sm transition-opacity"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* ── SIDEBAR ─────────────────────────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 lg:static lg:z-auto bg-white border-r border-slate-200 flex flex-col shrink-0 transition-transform duration-300 ease-in-out lg:transition-all ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        } ${collapsed ? 'w-[220px] lg:w-[60px]' : 'w-[220px]'}`}
        style={{ boxShadow: '1px 0 12px rgba(0,0,0,0.06)' }}
      >
        {/* Logo */}
        <div className={`flex items-center ${collapsed ? 'justify-center px-2 py-3' : 'justify-between px-4 py-3'} border-b border-slate-100`}>
          {!collapsed && (
            <div className="flex items-center gap-2 min-w-0">
              <ECodeLogo size={28} showText={true} textClassName="text-[13px]" />
            </div>
          )}
          {collapsed && <ECodeIcon size={30} />}
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
              <div key={group.key} className="mb-1">
                {!collapsed && (
                  <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest px-2 pt-2.5 pb-1 select-none">
                    {group.label}
                  </p>
                )}
                {collapsed && <div className="border-t border-slate-100 my-2 mx-1" />}

                {visibleLinks.map((link) => {
                  const isActive = location.pathname.startsWith(link.path);
                  const isBlocked = isSubExpired && !link.path.includes('/admin/tariflar');
                  return (
                    <Link
                      key={link.path}
                      to={isBlocked ? '/admin/tariflar' : link.path}
                      onClick={() => setMobileMenuOpen(false)}
                      title={collapsed ? link.name : undefined}
                      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg transition-all duration-150 group mb-0.5 ${
                        isBlocked
                          ? 'opacity-35 cursor-not-allowed pointer-events-none'
                          : isActive
                            ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
                      } ${collapsed ? 'justify-center lg:justify-center' : ''}`}
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
            title={t('header.logout')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-rose-500 hover:bg-rose-50 hover:text-rose-600 transition-all duration-150 ${collapsed ? 'justify-center' : ''}`}
          >
            <svg className="w-[18px] h-[18px] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {!collapsed && <span className="text-[13px] font-semibold">{t('header.logout')}</span>}
          </button>
        </div>
      </aside>

      {/* ── MAIN CONTENT ─────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden w-full relative">

        {/* Top Header */}
        <header className="bg-white border-b border-slate-100 px-4 md:px-6 py-3.5 flex items-center justify-between shrink-0" style={{ boxShadow: '0 1px 8px rgba(0,0,0,0.05)' }}>
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-1.5 -ml-1.5 mr-1 text-slate-500 hover:bg-slate-100 rounded-lg"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div>
              <h1 className="text-[14px] md:text-[15px] font-bold text-slate-800 leading-none truncate max-w-[150px] sm:max-w-xs">{currentPage}</h1>
              <p className="text-[10px] md:text-[11px] text-slate-400 mt-1 hidden sm:block">
                {new Date().toLocaleDateString(dateLocales[lang] || 'uz-UZ', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-2.5">
            {/* Tizim faol */}
            <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-100 rounded-full px-3 py-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-700 text-xs font-medium">{t('header.systemActive')}</span>
            </div>

            {/* Kam qoldiq */}
            {lowStockCount > 0 && (
              <button
                onClick={() => navigate('/admin/warehouse')}
                className="relative flex items-center gap-1.5 bg-amber-50 border border-amber-200 rounded-full px-2 sm:px-3 py-1.5 hover:bg-amber-100 transition-colors cursor-pointer"
                title={`${lowStockCount} ${t('header.lowStock')}`}
              >
                <svg className="w-4 h-4 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
                <span className="hidden sm:inline text-amber-700 text-xs font-semibold">{t('header.lowStock')}</span>
                <span className="min-w-[18px] h-[18px] px-1 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                  {lowStockCount > 99 ? '99+' : lowStockCount}
                </span>
              </button>
            )}

            {/* Org kodi */}
            <div className="hidden md:flex flex-col items-center bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-1.5 min-w-[90px]">
              <span className="text-slate-400 text-[10px] font-semibold leading-none mb-0.5 uppercase tracking-wide">{t('header.code')}</span>
              <span className="text-slate-700 text-[14px] font-black leading-none tracking-wide">{orgData.code}</span>
            </div>

            {/* Balans */}
            <div className="hidden lg:flex flex-col items-center bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-1.5 min-w-[90px]">
              <span className="text-emerald-500 text-[10px] font-semibold leading-none mb-0.5 uppercase tracking-wide">{t('header.balance')}</span>
              <span className="text-emerald-700 text-[14px] font-black leading-none tracking-wide">{fmt(orgData.balance)} s</span>
            </div>

            {/* 🌐 Lang Switcher */}
            <LangSwitcher t={t} lang={lang} setLang={setLang} LANGUAGES={LANGUAGES} />

            {/* User */}
            <div className="hidden md:flex items-center gap-2.5 bg-indigo-600 rounded-xl px-3.5 py-2 shadow-md shadow-indigo-200">
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
        <main className={`flex-1 overflow-x-hidden overflow-y-auto bg-slate-50 relative ${location.pathname.startsWith('/admin/pos-kassa') ? '' : 'p-6'}`}>
          <Outlet />

          {/* ── Obuna tugagan blok overlay ── */}
          {isSubExpired && !location.pathname.includes('/admin/tariflar') && (
            <div className="absolute inset-0 z-50 bg-white/80 backdrop-blur-sm flex items-center justify-center p-6">
              <div className="bg-white rounded-2xl border border-red-200 shadow-2xl max-w-md w-full p-8 text-center">
                <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  </svg>
                </div>
                <h2 className="text-xl font-black text-slate-800 mb-2">Obuna muddati tugagan</h2>
                <p className="text-sm text-slate-500 mb-6">{subExpiredMsg || "Tizimdan foydalanish uchun obunani yangilang."}</p>
                <button
                  onClick={() => navigate('/admin/tariflar')}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-sm hover:opacity-90 transition-all shadow-lg"
                >
                  To'lovga o'tish →
                </button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
