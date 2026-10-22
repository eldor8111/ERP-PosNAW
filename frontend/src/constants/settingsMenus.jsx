import React from 'react';
import {
  CreditCard, Key, Receipt, MessageSquare, Lock, Cpu, SlidersHorizontal
} from 'lucide-react';

// Kalit lug'atda bo'lmasa (t() kalitning o'zini qaytaradi) — o'zbekcha zaxira matn
const fb = (v, key, fallback) => (v === key ? fallback : v);

export const getSettingsMenuGroups = (t) => [
  {
    key: 'system',
    label: fb(t('settings.group.system'), 'settings.group.system', 'Tizim sozlamalari'),
    items: [
      { id: 'general',  icon: <SlidersHorizontal className="w-[18px] h-[18px]" />, label: t('settings.menu.general') || 'Umumiy sozlamalar' },
      { id: 'password', icon: <Lock className="w-[18px] h-[18px]" />, label: t('settings.menu.password') || "Parol o'zgartirish" },
    ],
  },
  {
    key: 'finance',
    label: fb(t('settings.group.finance'), 'settings.group.finance', 'Fiskal & Chek sozlamalari'),
    items: [
      { id: 'currencies', icon: <CreditCard className="w-[18px] h-[18px]" />, label: t('settings.menu.currencies') || 'Valyutalar' },
      { id: 'fiskal',     icon: <Cpu className="w-[18px] h-[18px]" />, label: t('settings.menu.fiskal') || 'Fiskal modul' },
      { id: 'receipt',    icon: <Receipt className="w-[18px] h-[18px]" />, label: t('settings.menu.receipt') || 'Chek sozlamalari' },
    ],
  },
  {
    key: 'integrations',
    label: fb(t('settings.group.integrations'), 'settings.group.integrations', 'Integratsiyalar'),
    items: [
      { id: 'tgbot', icon: <MessageSquare className="w-[18px] h-[18px]" />, label: t('settings.menu.tgbot') || 'Telegram Bot' },
      { id: 'api',   icon: <Key className="w-[18px] h-[18px]" />, label: t('settings.menu.api') || 'API kalitlar' },
    ],
  },
];

export const getSettingsMenus = (t) => {
  return getSettingsMenuGroups(t).flatMap((g) => g.items);
};
