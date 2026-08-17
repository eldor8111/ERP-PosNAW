import React from 'react';
import { User, Building, MapPin, Shield, Users, MessageSquare, Monitor, Smartphone } from 'lucide-react';

export const getSettingsMenus = (t) => [
  { id: 'profile', icon: <User className="w-[18px] h-[18px]" />, label: t('profile') || 'Profil' },
  { id: 'company', icon: <Building className="w-[18px] h-[18px]" />, label: t('company') || 'Kompaniya' },
  { id: 'branches', icon: <MapPin className="w-[18px] h-[18px]" />, label: t('branches') || 'Filiallar' },
  { id: 'roles', icon: <Shield className="w-[18px] h-[18px]" />, label: t('roles') || 'Rollar' },
  { id: 'users', icon: <Users className="w-[18px] h-[18px]" />, label: t('users') || 'Foydalanuvchilar' },
  { id: 'tg_bot', icon: <MessageSquare className="w-[18px] h-[18px]" />, label: t('tg_bot') || 'Telegram Bot' },
  { id: 'pos', icon: <Monitor className="w-[18px] h-[18px]" />, label: t('pos') || 'POS Terminal' },
  { id: 'devices', icon: <Smartphone className="w-[18px] h-[18px]" />, label: t('devices') || 'Qurilmalar' },
];
