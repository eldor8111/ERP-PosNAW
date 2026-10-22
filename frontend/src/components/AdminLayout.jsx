import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import useCompanyFeatures, { refreshCompanyFeatures } from '../hooks/useCompanyFeatures';
import { useLang } from '../context/LangContext';
import api from '../api/axios';
import { ROLES, ROLE_GROUPS, ROLE_LABELS, ROLE_GRADIENTS } from '../constants/roles';
import { getSettingsMenus, getSettingsMenuGroups } from '../constants/settingsMenus';
import ECodeLogo, { ECodeIcon } from './ECodeLogo';
import toast from 'react-hot-toast';
import {
  BriefcaseBusiness, CircleChevronLeft, Copy, Minus, TextAlignJustify, X, Sparkles,
  ChevronRight, ShoppingBag, Navigation, Package, DollarSign, BarChart3,
  Settings as SettingsIcon, ShieldAlert, Layers, ShieldCheck, Store, Truck, Shield,
  Users, AlertTriangle, FileText, CheckCircle2, SlidersHorizontal,
  Building2, Tag, Landmark, Scale, MapPin
} from 'lucide-react';
import AnnouncementModal from './AnnouncementModal';
import AnnouncementBanner from './AnnouncementBanner';
import BranchSwitcher from './BranchSwitcher';
import { getPendingPosCount, flushPosQueue } from '../utils/posQueue';
import { isPageAllowed } from '../utils/permissions';

const fmt = (n) => Number(n || 0).toLocaleString('ru-RU');

function buildNavGroups(t, alertsCount = 0, approvalsCount = 0) {
  return [
    {
      key: 'pos_group',
      label: t('nav.pos_group') || 'Savdo & Kassa',
      primaryPath: '/admin/sotuv',
      icon: <ShoppingBag className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.SALES,
      links: [
        {
          name: t('nav.saleScreen') || 'Kassa (Sotuv oynasi)',
          path: '/admin/sotuv',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>,
        },
        {
          name: t('nav.customers') || 'Mijozlar CRM',
          path: '/admin/customers',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>,
        },
        {
          name: t('nav.shifts') || 'Smenalar va Kassa',
          path: '/admin/shifts',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
        },
        {
          name: t('nav.promotions') || 'Aksiyalar & Chegirmalar',
          path: '/admin/promotions',
          roles: ROLE_GROUPS.SALES,
          icon: <Tag className="w-[18px] h-[18px]" />,
        },
      ],
    },
    {
      key: 'sfa_group',
      label: t('nav.sfa_group') || 'SFA & Dala Savdosi',
      primaryPath: '/admin/sfa',
      icon: <Navigation className="w-[20px] h-[20px]" />,
      feature: 'distribution',
      roles: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER],
      links: [
        {
          name: t('nav.sfa') || 'SFA Markazi (Jonli GPS)',
          path: '/admin/sfa',
          feature: 'distribution',
          roles: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
        },
        {
          name: t('nav.distributors') || 'Distribyutorlar',
          path: '/admin/distributors',
          feature: 'distribution',
          roles: ROLE_GROUPS.SALES,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>,
        },
        {
          name: t('nav.logistics') || 'Logistika va Yetkazish',
          path: '/admin/logistics',
          feature: 'distribution',
          roles: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>,
        },
      ],
    },
    {
      key: 'supply_group',
      label: t('nav.supply_group') || 'Ombor & Mahsulotlar',
      primaryPath: '/admin/ombor',
      icon: <Package className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
      links: [
        {
          name: t('nav.warehouse') || 'Omborlar',
          path: '/admin/ombor',
          roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" /></svg>,
        },
        {
          name: t('nav.products') || 'Mahsulotlar katalogi',
          path: '/admin/products',
          roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>,
        },
        {
          name: t('nav.purchases') || "Xarid va Ta'minotchilar",
          path: '/admin/purchases',
          roles: ROLE_GROUPS.REPORTS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>,
        },
        {
          name: t('nav.operations') || 'Operatsiyalar tarixi',
          path: '/admin/operations',
          roles: ROLE_GROUPS.OPS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>,
        },
        {
          name: t('nav.production') || 'Ishlab chiqarish',
          path: '/admin/production',
          feature: 'manufacturing',
          roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>,
        },
      ],
    },
    {
      key: 'finance_group',
      label: t('nav.finance_group') || "Moliya & To'lovlar",
      primaryPath: '/admin/finance',
      icon: <DollarSign className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.FINANCE_ACCESS,
      links: [
        {
          name: t('nav.finance') || 'Moliya balansi',
          path: '/admin/finance',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
        },
        {
          name: t('nav.kirimTolov') || "Kirim to'lovlar",
          path: '/admin/kirim-tolovlar',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 13l-5 5m0 0l-5-5m5 5V6" /></svg>,
        },
        {
          name: t('nav.chiqimTolov') || "Chiqim to'lovlar",
          path: '/admin/chiqim-tolovlar',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 11l5-5m0 0l5 5m-5-5v12" /></svg>,
        },
        {
          name: t('nav.kassa') || 'Kassa hisoblari',
          path: '/admin/kassa',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" /></svg>,
        },
        {
          name: t('nav.payment_terminals') || "To'lov terminallari",
          path: '/admin/settings?tab=payment_terminals',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <Landmark className="w-[18px] h-[18px]" />,
        },
        {
          name: t('nav.payment_reconciliation') || "To'lovlarni solishtirish",
          path: '/admin/payment-reconciliation',
          roles: ROLE_GROUPS.FINANCE_ACCESS,
          icon: <Scale className="w-[18px] h-[18px]" />,
        },
      ],
    },
    {
      key: 'branches_group',
      label: t('nav.branches_group') || 'Filiallar & Tariflar',
      primaryPath: '/admin/filiallar',
      icon: <Building2 className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.MANAGEMENT,
      links: [
        {
          name: t('nav.branches') || 'Filiallar',
          path: '/admin/filiallar',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>,
        },
        {
          name: t('nav.tariffs') || 'Tariflar',
          path: '/admin/tariflar',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>,
        },
      ],
    },
    {
      key: 'access_group',
      label: t('nav.access_group') || 'Xodimlar & Ruxsatlar',
      primaryPath: '/admin/settings?tab=users',
      icon: <Users className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.MANAGEMENT,
      links: [
        {
          name: t('nav.users') || 'Foydalanuvchilar',
          path: '/admin/settings?tab=users',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <Users className="w-[18px] h-[18px]" />,
        },
        {
          name: t('nav.roles') || 'Rollar va Ruxsatlar',
          path: '/admin/settings?tab=roles',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <ShieldCheck className="w-[18px] h-[18px]" />,
        },
        {
          name: t('approvals.title') || 'Tasdiqlashlar',
          path: '/admin/approvals',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>,
          badge: approvalsCount > 0 ? String(approvalsCount) : null,
        },
      ],
    },
    {
      key: 'analytics_group',
      label: t('nav.analytics_group') || 'Tahlil & Hisobotlar',
      primaryPath: '/admin/reports',
      icon: <BarChart3 className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.REPORTS_ACCESS,
      links: [
        {
          name: t('nav.reports') || 'Asosiy hisobotlar',
          path: '/admin/reports',
          roles: ROLE_GROUPS.REPORTS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>,
        },
        {
          name: t('plan.title') || 'Reja va KPI',
          path: '/admin/branch-plans',
          roles: ROLE_GROUPS.REPORTS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>,
        },
        {
          name: 'AI Copilot',
          path: '/admin/ai',
          roles: ROLE_GROUPS.REPORTS_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
        },
        {
          name: t('nav.alerts') || 'Ogohlantirishlar',
          path: '/admin/alerts',
          roles: ROLE_GROUPS.WAREHOUSE_ACCESS,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>,
          badge: alertsCount > 0 ? `⚠️ ${alertsCount}` : null,
        },
      ],
    },
    {
      key: 'marketplace_agents_group',
      label: t('nav.marketplace_agents') || 'Marketplace agentlari',
      primaryPath: '/admin/marketplace-agents',
      icon: <Store className="w-[20px] h-[20px]" />,
      feature: 'marketplace_agents',
      roles: ROLE_GROUPS.MANAGEMENT,
      links: [
        {
          name: t('nav.marketplace_agents') || 'Marketplace agentlari',
          path: '/admin/marketplace-agents',
          feature: 'marketplace_agents',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <Store className="w-[18px] h-[18px]" />,
        },
      ],
    },
    {
      key: 'settings_group',
      label: t('nav.settings') || 'Sozlamalar',
      primaryPath: '/admin/settings',
      icon: <SettingsIcon className="w-[20px] h-[20px]" />,
      roles: ROLE_GROUPS.MANAGEMENT,
      isSettings: true,
      links: [
        {
          name: t('nav.settings') || 'Barcha sozlamalar',
          path: '/admin/settings',
          roles: ROLE_GROUPS.MANAGEMENT,
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
        },
      ],
    },
    {
      key: 'admin_group',
      label: t('nav.admin_group') || 'Admin',
      primaryPath: '/admin/super-admin',
      icon: <Shield className="w-[20px] h-[20px]" />,
      roles: [ROLES.SUPER_ADMIN],
      links: [
        {
          name: t('nav.companies') || 'Korxonalar',
          path: '/admin/super-admin',
          roles: [ROLES.SUPER_ADMIN],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>,
        },
        {
          name: t('nav.agents') || 'Agentlar',
          path: '/admin/agents',
          roles: [ROLES.SUPER_ADMIN],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>,
        },
        {
          name: t('nav.audit_logs') || 'Audit jurnali',
          path: '/admin/audit-logs',
          roles: [ROLES.SUPER_ADMIN],
          icon: <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" /></svg>,
        },
      ],
    },
  ];
}

// Language switcher dropdown
function LangSwitcher({ t, lang, setLang, LANGUAGES }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = LANGUAGES.find((l) => l.code === lang) || LANGUAGES[0];

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
        onClick={() => setOpen((o) => !o)}
        title={t('header.lang')}
        className="flex items-center cursor-pointer gap-1.5 px-2 md:px-3 py-1 xl:py-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-full transition-all duration-150 group"
      >
        <svg className="w-4 h-4 text-slate-500 group-hover:text-blue-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
        </svg>
        <span className="text-[10px] xl:text-[12px] font-bold text-slate-600 group-hover:text-blue-700">{current.short}</span>
        <svg className={`w-3 h-3 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-40 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => {
                setLang(l.code);
                setOpen(false);
              }}
              className={`w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs xl:text-sm font-medium hover:bg-blue-50 hover:text-blue-700 transition-colors ${
                lang === l.code ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-slate-700'
              }`}
            >
              <span className="text-base">{l.flag}</span>
              <span>{l.label}</span>
              {lang === l.code && (
                <svg className="w-3.5 h-3.5 ml-auto text-blue-600" fill="currentColor" viewBox="0 0 20 20">
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
  const features = useCompanyFeatures();
  useEffect(() => {
    if (user?.company_id) refreshCompanyFeatures();
  }, [user?.company_id]);
  const { t, lang, setLang, LANGUAGES } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Universal Flyout State (sotuv, sfa, ombor, moliya, analytics, settings, etc.)
  const [activeFlyout, setActiveFlyout] = useState(null);
  const flyoutTimeout = useRef(null);

  const handleFlyoutEnter = useCallback((key) => {
    if (flyoutTimeout.current) clearTimeout(flyoutTimeout.current);
    setActiveFlyout(key);
  }, []);

  const handleFlyoutLeave = useCallback(() => {
    flyoutTimeout.current = setTimeout(() => {
      setActiveFlyout(null);
    }, 180);
  }, []);

  const SETTINGS_MENU_GROUPS = useMemo(() => getSettingsMenuGroups(t), [t]);

  // Eski localStorage flagni tozalaymiz
  useState(() => {
    localStorage.removeItem('subscription_expired');
  });

  const [orgData, setOrgData] = useState({
    name: user?.company_name || 'E-Code',
    code: '...',
    balance: 0,
  });

  const [isSubExpired, setIsSubExpired] = useState(false);
  const subExpiredMsg = isSubExpired ? t('subscription.expiredMsg') : '';

  useEffect(() => {
    if (!user?.company_id || user?.role === 'super_admin') return;
    api
      .get('/billing/my-company')
      .then((res) => {
        const d = res.data;
        const expired = d.subscription_ends_at !== null && d.subscription_active === false;
        setIsSubExpired(expired);
        setOrgData((prev) => ({
          ...prev,
          name: d.name || prev.name,
          code: d.org_code || prev.code,
          balance: d.balance !== undefined ? d.balance : prev.balance,
        }));
        if (expired && !location.pathname.includes('/admin/tariflar')) {
          navigate('/admin/tariflar', { replace: true });
        }
      })
      .catch(() => {});
  }, [user?.company_id, navigate, location.pathname]);

  const [lowStockCount, setLowStockCount] = useState(0);
  const [expiredCount, setExpiredCount] = useState(0);
  const [approvalsCount, setApprovalsCount] = useState(0);
  const [announcements, setAnnouncements] = useState([]);

  useEffect(() => {
    if (!user) return;
    api
      .get('/super-admin/announcements/active')
      .then((res) => setAnnouncements(res.data || []))
      .catch(() => {});
  }, [user?.id]);

  const refreshBalance = useCallback(() => {
    if (!user?.company_id || user?.role === ROLES.SUPER_ADMIN) return;
    api
      .get('/billing/my-company')
      .then((r) => {
        setOrgData((prev) => ({
          ...prev,
          name: r.data?.name || prev.name,
          code: r.data?.org_code || prev.code,
          balance: r.data?.balance !== undefined ? r.data.balance : prev.balance,
        }));
      })
      .catch(() => {});
  }, [user?.role, user?.company_id]);

  const refreshLowStock = useCallback(() => {
    if (!ROLE_GROUPS.WAREHOUSE_ACCESS.includes(user?.role)) return;
    api
      .get('/reports/low-stock')
      .then((r) => setLowStockCount((r.data || []).length))
      .catch(() => {});
    api
      .get('/reports/expired-batches')
      .then((r) => setExpiredCount((r.data || []).length))
      .catch(() => {});
  }, [user?.role]);

  const refreshApprovals = useCallback(() => {
    if (!ROLE_GROUPS.POS_ACCESS.includes(user?.role) && user?.role !== ROLES.SUPER_ADMIN) return;
    api
      .get('/approvals/requests', { params: { status: 'pending', limit: 100 } })
      .then((r) => setApprovalsCount((r.data || []).length))
      .catch(() => {});
  }, [user?.role]);

  useEffect(() => {
    refreshBalance();
    refreshLowStock();
    refreshApprovals();
    const id = setInterval(() => {
      refreshBalance();
      refreshLowStock();
      refreshApprovals();
    }, 60000);
    return () => clearInterval(id);
  }, [refreshBalance, refreshLowStock, refreshApprovals]);

  const handleLogout = useCallback(async () => {
    let left = getPendingPosCount();
    if (left > 0) {
      const tl = (key, fallback, vars) => {
        let s = t(key);
        if (s === key) s = fallback;
        if (vars) Object.entries(vars).forEach(([k, v]) => { s = s.replace(`{${k}}`, v); });
        return s;
      };
      if (
        !window.confirm(
          tl('pos.logoutWarningSync', "{count} ta saqlanmagan oflayn sotuv bor. Serverga yuborilsinmi? Bekor qilinsa, ular qurilmada qoladi.", { count: left })
        )
      ) {
        return;
      }
      try {
        await flushPosQueue(api);
      } catch {}
      left = getPendingPosCount();
      if (
        left > 0 &&
        !window.confirm(
          tl('pos.logoutPendingConfirm', "Yuborilmagan {count} ta oflayn sotuv bor. Chiqsangiz ular qurilmada saqlanadi, lekin serverga yuborilmaydi. Baribir chiqasizmi?", { count: left })
        )
      ) {
        return;
      }
    }
    logout();
    navigate('/login');
  }, [logout, navigate, t]);

  const navGroups = useMemo(
    () => buildNavGroups(t, lowStockCount + expiredCount, approvalsCount),
    [t, lowStockCount, expiredCount, approvalsCount]
  );

  const currentPage = useMemo(() => {
    const allLinks = navGroups.flatMap((g) => g.links);
    const currentLink = allLinks.find((l) => {
      if (l.path.includes('?')) {
        const [pathPart, queryPart] = l.path.split('?');
        return location.pathname === pathPart && location.search.includes(queryPart);
      }
      return location.pathname.startsWith(l.path);
    });
    return currentLink?.name || t('app.title');
  }, [location.pathname, location.search, navGroups, t]);

  const initials = useMemo(
    () => user?.name?.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase() || 'U',
    [user?.name]
  );

  const activeGroup = useMemo(
    () => navGroups.find((g) => g.key === activeFlyout),
    [navGroups, activeFlyout]
  );

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden relative">
      {/* Mobile Backdrop */}
      {mobileMenuOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-slate-900/50 z-50 backdrop-blur-sm transition-opacity"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* SIDEBAR */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 lg:z-40 lg:static py-1 bg-white border-r border-slate-200 flex flex-col shrink-0 transition-transform duration-300 ease-in-out lg:transition-all ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        } ${collapsed ? 'w-[280px] lg:w-[68px]' : 'w-[220px] xl:w-[260px]'}`}
        style={{ boxShadow: '1px 0 12px rgba(0,0,0,0.06)' }}
      >
        <div className={`flex justify-between items-center ${collapsed ? 'px-2.5 py-1' : 'px-4 py-2'} border-b border-slate-100`}>
          {!collapsed && (
            <Link to={'/admin/sotuv'} className="flex items-center gap-2 min-w-0 overflow-hidden">
              <ECodeLogo size={40} showText={true} className="shrink-0" textClassName="text-[18px] xl:text-[22px] truncate" />
            </Link>
          )}
          {collapsed && (
            <Link to={'/admin/sotuv'}>
              <ECodeIcon size={42} className="scale-90 xl:scale-100" />
            </Link>
          )}

          <button onClick={() => setMobileMenuOpen(false)} className="cursor-pointer block lg:hidden text-slate-500 hover:text-slate-700">
            <X size={22} />
          </button>
        </div>

        {/* Primary Navigation Menu */}
        <nav
          className="flex-1 mt-3 overflow-y-auto px-2 space-y-1"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {navGroups.map((group) => {
            if (!user) return null;
            if (group.feature && !features?.[group.feature]) return null;
            if (user.role !== 'super_admin' && group.roles && !group.roles.includes(user.role)) return null;

            // Check if any sub-link is active
            const isGroupActive = group.links.some((l) => {
              if (l.path.includes('?')) {
                const [pathPart, queryPart] = l.path.split('?');
                return location.pathname === pathPart && location.search.includes(queryPart);
              }
              return location.pathname.startsWith(l.path);
            }) || (group.isSettings && location.pathname.startsWith('/admin/settings') && !location.search.includes('tab=users') && !location.search.includes('tab=roles') && !location.search.includes('tab=payment_terminals'));
            const isFlyoutOpen = activeFlyout === group.key;

            return (
              <div
                key={group.key}
                onMouseEnter={() => handleFlyoutEnter(group.key)}
                onMouseLeave={handleFlyoutLeave}
                className="relative"
              >
                <Link
                  to={group.primaryPath}
                  onClick={() => {
                    setActiveFlyout(null);
                    setMobileMenuOpen(false);
                  }}
                  title={collapsed ? group.label : undefined}
                  className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all duration-150 group cursor-pointer ${
                    isGroupActive
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20 font-bold'
                      : isFlyoutOpen
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900 font-medium'
                  }`}
                >
                  <span className={`shrink-0 transition-transform ${collapsed ? 'scale-110' : ''} ${isGroupActive ? 'text-white' : 'text-slate-500 group-hover:text-blue-600'}`}>
                    {group.icon}
                  </span>

                  {!collapsed && (
                    <span className="text-[13px] xl:text-[14px] truncate flex-1 leading-tight">
                      {group.label}
                    </span>
                  )}

                  {!collapsed && (
                    <ChevronRight
                      className={`size-3.5 transition-transform duration-200 shrink-0 ${
                        isGroupActive ? 'text-white/80' : isFlyoutOpen ? 'text-blue-600 translate-x-0.5' : 'text-slate-400 group-hover:text-slate-600'
                      }`}
                    />
                  )}
                </Link>
              </div>
            );
          })}
        </nav>

        {/* Bottom: User + Logout */}
        <div className="border-t border-slate-100 p-2.5 space-y-1">
          {!collapsed && (
            <Link to={'/admin/profile'} className="flex items-center gap-2.5 px-2 py-2 rounded-xl bg-slate-50 hover:bg-slate-100 transition-colors">
              <div
                className={`w-8 h-8 rounded-xl bg-gradient-to-br ${ROLE_GRADIENTS[user?.role] || 'from-blue-500 to-blue-700'} flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-sm`}
              >
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-bold text-slate-800 truncate leading-none mb-1">{user?.name}</p>
                <p className="text-[11px] text-slate-400 truncate leading-none">{ROLE_LABELS[user?.role] || user?.role}</p>
              </div>
            </Link>
          )}

          {collapsed && (
            <Link to={'/admin/profile'} className="flex justify-center py-1">
              <div
                className={`w-9 h-9 rounded-xl bg-gradient-to-br ${ROLE_GRADIENTS[user?.role] || 'from-blue-500 to-blue-700'} flex items-center justify-center text-white text-xs font-bold shadow-sm`}
              >
                {initials}
              </div>
            </Link>
          )}

          <button
            onClick={handleLogout}
            title={t('header.logout')}
            className="w-full cursor-pointer flex items-center gap-2.5 px-3 py-2 rounded-xl text-rose-500 hover:bg-rose-50 hover:text-rose-600 transition-all text-xs font-bold"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {!collapsed && <span>{t('header.logout')}</span>}
          </button>
        </div>

        {/* UNIVERSAL HOVER FLYOUT SUB-MENU */}
        {activeGroup && (
          <div
            onMouseEnter={() => handleFlyoutEnter(activeGroup.key)}
            onMouseLeave={handleFlyoutLeave}
            className={`absolute top-0 bottom-0 z-50 bg-white border-r border-slate-200 shadow-2xl flex flex-col w-[280px] xl:w-[310px] transition-all overflow-hidden ${
              collapsed ? 'left-[68px]' : 'left-[220px] xl:left-[260px]'
            }`}
          >
            {/* Flyout Header */}
            <div className="p-4 flex items-center justify-between border-b border-slate-100 bg-slate-50/50 sticky top-0 z-10">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center text-blue-600 shadow-xs">
                  {activeGroup.icon}
                </div>
                <div>
                  <h2 className="text-[15px] font-extrabold text-slate-800 leading-tight">
                    {activeGroup.label}
                  </h2>
                  <span className="text-[11px] text-slate-400 font-medium">Bo'limlar va sahifalar</span>
                </div>
              </div>
              <button
                onClick={() => setActiveFlyout(null)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-200/50"
              >
                <X size={16} />
              </button>
            </div>

            {/* Flyout Content */}
            <div className="flex-1 py-2 overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
              {activeGroup.isSettings ? (
                /* SOZLAMALAR: 4 ta toza guruhlangan kategoriya */
                SETTINGS_MENU_GROUPS.map((sec) => (
                  <div key={sec.key} className="mb-3">
                    <div className="px-5 pt-2 pb-1 text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                      {sec.label}
                    </div>
                    {sec.items.map((m) => {
                      const isActive = m.path
                        ? location.pathname.startsWith(m.path)
                        : location.search.includes(`tab=${m.id}`);
                      return (
                        <Link
                          key={m.id}
                          to={m.path || `/admin/settings?tab=${m.id}`}
                          onClick={() => {
                            setActiveFlyout(null);
                            setMobileMenuOpen(false);
                          }}
                          className={`w-full flex items-center gap-2.5 px-5 py-2 text-[13px] font-medium transition-colors text-left ${
                            isActive
                              ? 'bg-blue-50/80 text-blue-700 font-bold border-r-2 border-blue-600'
                              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                          }`}
                        >
                          <div className={isActive ? 'text-blue-600' : 'text-slate-500'}>{m.icon}</div>
                          <span className="truncate flex-1">{m.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                ))
              ) : (
                /* STANDART GURUHLARNING HAVOLALARI */
                <div className="space-y-0.5 px-2">
                  {activeGroup.links.map((link) => {
                    if (link.feature && !features?.[link.feature]) return null;
                    if (user.role !== 'super_admin' && link.roles && !link.roles.includes(user.role)) return null;

                    const isActive = link.path.includes('?')
                      ? location.pathname === link.path.split('?')[0] && location.search.includes(link.path.split('?')[1])
                      : location.pathname.startsWith(link.path);
                    const isBlocked = isSubExpired && !link.path.includes('/admin/tariflar');

                    return (
                      <Link
                        key={link.path}
                        to={isBlocked ? '/admin/tariflar' : link.path}
                        onClick={() => {
                          setActiveFlyout(null);
                          setMobileMenuOpen(false);
                        }}
                        className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-[13px] transition-all text-left ${
                          isBlocked
                            ? 'opacity-40 cursor-not-allowed pointer-events-none'
                            : isActive
                            ? 'bg-blue-50 text-blue-700 font-bold shadow-xs'
                            : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 font-medium'
                        }`}
                      >
                        <div className={`shrink-0 ${isActive ? 'text-blue-600' : 'text-slate-500'}`}>
                          {link.icon}
                        </div>
                        <span className="truncate flex-1">{link.name}</span>
                        {link.badge && (
                          <span className="bg-blue-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap">
                            {link.badge}
                          </span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </aside>

      {/* MAIN CONTENT AREA */}
      <div className="flex-1 flex flex-col overflow-hidden w-full relative">
        <AnnouncementBanner announcements={announcements} />
        <AnnouncementModal announcements={announcements} />

        {/* Top Header */}
        <header className="bg-white border-b border-slate-100 px-4 md:px-6 py-2.25 flex items-center justify-between shrink-0" style={{ boxShadow: '0 1px 8px rgba(0,0,0,0.05)' }}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 -ml-2 text-slate-500 hover:text-slate-700 rounded-lg hover:bg-slate-100 cursor-pointer"
            >
              <TextAlignJustify size={20} />
            </button>
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="hidden lg:flex p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              title={collapsed ? t('header.expandSidebar') : t('header.collapseSidebar')}
            >
              <CircleChevronLeft size={20} className={`transform transition-transform ${collapsed ? 'rotate-180' : ''}`} />
            </button>
            <div className="h-5 w-px bg-slate-200 hidden sm:block" />
            <h1 className="text-base sm:text-lg font-bold text-slate-800 truncate max-w-[200px] sm:max-w-none">
              {currentPage}
            </h1>
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2.5">
            <BranchSwitcher />

            <LangSwitcher t={t} lang={lang} setLang={setLang} LANGUAGES={LANGUAGES} />

            {/* Org kodi */}
            {user?.role !== ROLES.SUPER_ADMIN && orgData.code && orgData.code !== '...' && (
              <div className="hidden md:flex flex-col items-center bg-slate-50 border border-slate-200 rounded-lg xl:rounded-xl px-2 sm:px-3 py-1 min-w-[70px]">
                <span className="text-slate-400 text-[8px] xl:text-[9px] font-semibold leading-none mb-0.5 uppercase tracking-wide">
                  {t('header.code') || 'ID'}
                </span>
                <div className="flex items-center gap-1">
                  <span className="text-slate-700 text-[11px] xl:text-[13px] font-black leading-none font-mono">
                    {orgData.code}
                  </span>
                  <Copy
                    className="size-3 text-slate-400 hover:text-slate-600 cursor-pointer"
                    onClick={() => {
                      navigator.clipboard.writeText(orgData.code);
                      toast.success(t('common.copied') || 'Nusxalandi');
                    }}
                  />
                </div>
              </div>
            )}

            {/* Balans */}
            {user?.role !== ROLES.SUPER_ADMIN && (
              <div
                onClick={() => navigate('/admin/tariflar')}
                title={t('nav.tariffs') || 'Tariflar va Balans'}
                className="flex flex-col items-center bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg xl:rounded-xl px-2.5 sm:px-3.5 py-1 cursor-pointer transition-colors shadow-xs"
              >
                <span className="text-emerald-500 text-[8px] xl:text-[9px] font-semibold leading-none mb-0.5 uppercase tracking-wide">
                  {t('header.balance') || 'Balans'}
                </span>
                <span className="text-emerald-700 text-[11px] xl:text-[13px] font-black leading-none tracking-wide">
                  {fmt(orgData.balance)} <span className="text-[10px] font-semibold">{t('header.sum') === 'header.sum' ? "so'm" : t('header.sum')}</span>
                </span>
              </div>
            )}

            {/* User & Korxona nomi */}
            <Link
              to={'/admin/profile'}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 transition-colors rounded-lg sm:rounded-xl px-2 sm:px-3 py-1 sm:py-1.5 shadow-md shadow-blue-200 text-white"
            >
              <div className="w-6 h-6 rounded sm:rounded-lg bg-white/20 flex items-center justify-center text-white text-[11px] font-black shrink-0">
                {initials}
              </div>
              <div className="hidden sm:flex flex-col text-left">
                <span className="text-white text-[12px] font-bold leading-none max-w-[130px] truncate">
                  {orgData.name && orgData.name !== 'Tizim' ? orgData.name : (user?.company_name || user?.name || 'E-Code')}
                </span>
                <span className="text-blue-200 text-[10px] font-medium leading-none mt-0.5">
                  {ROLE_LABELS[user?.role] || user?.role}
                </span>
              </div>
            </Link>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto bg-slate-50 relative">
          {subExpiredMsg && (
            <div className="p-4 bg-amber-50 border-b border-amber-200 text-amber-800 text-sm flex items-center justify-between">
              <span>{subExpiredMsg}</span>
              <Link to="/admin/tariflar" className="font-bold underline ml-2">
                {t('subscription.renewNow')}
              </Link>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
