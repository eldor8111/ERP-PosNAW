import React from 'react';
import {
  Users, Shield, MapPin, CreditCard,
  Key, Receipt, MessageSquare, Lock, Cpu, Tag, Package
} from 'lucide-react';

export const getSettingsMenus = (_t) => [
  { id: 'users',      icon: <Users         className="w-[18px] h-[18px]" />, label: 'Foydalanuvchilar' },
  { id: 'roles',      icon: <Shield        className="w-[18px] h-[18px]" />, label: 'Rollar' },
  { id: 'branches',   icon: <MapPin        className="w-[18px] h-[18px]" />, label: 'Filiallar' },
  { id: 'currencies', icon: <CreditCard    className="w-[18px] h-[18px]" />, label: 'Valyutalar' },
  { id: 'receipt',    icon: <Receipt       className="w-[18px] h-[18px]" />, label: 'Chek sozlamalari' },
  { id: 'tgbot',      icon: <MessageSquare className="w-[18px] h-[18px]" />, label: 'Telegram Bot' },
  { id: 'api',        icon: <Key           className="w-[18px] h-[18px]" />, label: 'API kalitlar' },
  { id: 'fiskal',     icon: <Cpu           className="w-[18px] h-[18px]" />, label: 'Fiskal' },
  { id: 'password',   icon: <Lock          className="w-[18px] h-[18px]" />, label: 'Parol' },
  { id: 'promotions', icon: <Tag className="w-[18px] h-[18px]" />, label: 'Aksiyalar' },
  { id: 'warehouse',  icon: <Package className="w-[18px] h-[18px]" />, label: 'Omborlar' },
];
