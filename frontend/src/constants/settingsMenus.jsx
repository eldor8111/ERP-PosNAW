import React from 'react';
import {
  Users, Shield, MapPin, CreditCard,
  Key, Receipt, MessageSquare, Lock, Cpu, Tag, Package, Star, SlidersHorizontal, Store, ShieldCheck, Landmark, Scale
} from 'lucide-react';

// Kalit lug'atda bo'lmasa (t() kalitning o'zini qaytaradi) — o'zbekcha zaxira matn
const fb = (v, key, fallback) => (v === key ? fallback : v);

export const getSettingsMenus = (t) => [
  // Umumiy: qo'shimcha modullar (ishlab chiqarish, distribyutor), POS va yetkazish sozlamalari
  { id: 'general',    icon: <SlidersHorizontal className="w-[18px] h-[18px]" />, label: t('settings.menu.general') },
  { id: 'users',      icon: <Users         className="w-[18px] h-[18px]" />, label: t('settings.menu.users') },
  { id: 'roles',      icon: <Shield        className="w-[18px] h-[18px]" />, label: t('settings.menu.roles') },
  { id: 'branches',   icon: <MapPin        className="w-[18px] h-[18px]" />, label: t('settings.menu.branches') },
  { id: 'currencies', icon: <CreditCard    className="w-[18px] h-[18px]" />, label: t('settings.menu.currencies') },
  { id: 'receipt',    icon: <Receipt       className="w-[18px] h-[18px]" />, label: t('settings.menu.receipt') },
  { id: 'tgbot',      icon: <MessageSquare className="w-[18px] h-[18px]" />, label: t('settings.menu.tgbot') },
  { id: 'api',        icon: <Key           className="w-[18px] h-[18px]" />, label: t('settings.menu.api') },
  { id: 'fiskal',     icon: <Cpu           className="w-[18px] h-[18px]" />, label: t('settings.menu.fiskal') },
  // T3.18: to'lov terminallari (Click/Payme/Uzum/Uzcard/Humo) va to'lovlarni solishtirish (alohida sahifa)
  { id: 'payment_terminals', icon: <Landmark className="w-[18px] h-[18px]" />, label: fb(t('settings.menu.payment_terminals'), 'settings.menu.payment_terminals', "To'lov terminallari") },
  { id: 'payment_reconciliation', icon: <Scale className="w-[18px] h-[18px]" />, label: fb(t('settings.menu.payment_reconciliation'), 'settings.menu.payment_reconciliation', "To'lovlarni solishtirish"), path: '/admin/payment-reconciliation' },
  { id: 'password',   icon: <Lock          className="w-[18px] h-[18px]" />, label: t('settings.menu.password') },
  { id: 'promotions', icon: <Tag className="w-[18px] h-[18px]" />, label: t('settings.menu.promotions') },
  { id: 'warehouse',  icon: <Package className="w-[18px] h-[18px]" />, label: t('settings.menu.warehouse') },
  // T3.17: Marketplace agentlari (modul yoqilmagan korxonada sahifa FeatureGate bilan yopiq)
  { id: 'marketplace-agents', icon: <Store className="w-[18px] h-[18px]" />, label: t('settings.menu.marketplace-agents'), path: '/admin/marketplace-agents' },
  // T4.6: tasdiqlash so'rovlari va qoidalari (chegirma, narx, xarajat, qaytarish limitlari)
  { id: 'approvals',  icon: <ShieldCheck className="w-[18px] h-[18px]" />, label: t('settings.menu.approvals'), path: '/admin/approvals' },
  { id: 'tariflar',   icon: <Star className="w-[18px] h-[18px]" />, label: t('settings.menu.tariflar'), path: '/admin/tariflar' },
];
