import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';
import {
  CreditCard,
  Wallet,
  Store,
  Zap,
  Sparkles,
  Crown,
  Package,
  Warehouse,
  Users,
  Bike,
  Truck,
  BarChart3,
  Factory,
  Share2,
  Check,
  X,
  AlertTriangle,
} from 'lucide-react';

const fmtMoney = (n) => Number(n || 0).toLocaleString('uz-UZ');

const getTariffTheme = (name = '') => {
  const n = (name || '').toLowerCase();
  if (n.includes('mini')) {
    return {
      type: 'mini',
      badge: "Kichik Do'kon",
      badgeCls: 'bg-emerald-600 text-white shadow-xs',
      borderCls: 'border-emerald-200 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10',
      bgCls: 'bg-white',
      priceColor: 'text-emerald-700',
      iconBg: 'bg-emerald-50 text-emerald-600 border border-emerald-200',
      btnGradient: 'from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 shadow-emerald-500/20',
      accentBar: 'from-emerald-500 via-teal-500 to-emerald-600',
      icon: Store,
    };
  }
  if (n.includes('pro')) {
    return {
      type: 'pro',
      badge: 'VIP Korxona',
      badgeCls: 'bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-xs',
      borderCls: 'border-violet-200 hover:border-violet-400 hover:shadow-xl hover:shadow-violet-500/10',
      bgCls: 'bg-white',
      priceColor: 'text-violet-700',
      iconBg: 'bg-violet-50 text-violet-600 border border-violet-200',
      btnGradient: 'from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 shadow-violet-500/20',
      accentBar: 'from-violet-600 via-purple-600 to-indigo-600',
      icon: Crown,
    };
  }
  if (n.includes('standart')) {
    return {
      type: 'standart',
      badge: 'Eng Ommabop',
      badgeCls: 'bg-blue-600 text-white shadow-md shadow-blue-500/30',
      borderCls: 'border-blue-400 ring-2 ring-blue-500/30 hover:border-blue-600 hover:shadow-xl hover:shadow-blue-500/15',
      bgCls: 'bg-gradient-to-br from-blue-50/40 via-white to-indigo-50/30',
      priceColor: 'text-blue-700',
      iconBg: 'bg-blue-50 text-blue-600 border border-blue-200',
      btnGradient: 'from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-blue-500/25',
      accentBar: 'from-blue-600 via-indigo-600 to-blue-500',
      isPopular: true,
      icon: Sparkles,
    };
  }
  return {
    type: 'start',
    badge: 'Distribyutsiya Start',
    badgeCls: 'bg-sky-600 text-white shadow-xs',
    borderCls: 'border-sky-200 hover:border-sky-400 hover:shadow-xl hover:shadow-sky-500/10',
    bgCls: 'bg-white',
    priceColor: 'text-sky-700',
    iconBg: 'bg-sky-50 text-sky-600 border border-sky-200',
    btnGradient: 'from-sky-600 to-blue-600 hover:from-sky-700 hover:to-blue-700 shadow-sky-500/20',
    accentBar: 'from-sky-500 via-blue-500 to-sky-600',
    icon: Zap,
  };
};

function TariflarTab({ hasBhm, billing, settings, tariffs, bgAccent, btnColor, priceColor, handleBuyTariff, handlePayme, trialLoading, isCurrent, hasActiveSub }) {
  const { t } = useLang();
  const [selectedMonths, setSelectedMonths] = useState(1);

  return (
    <div className="max-w-7xl mx-auto px-2 sm:px-4 py-8">
      {/* ── Header + BHM noti ── */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight leading-tight">{t('nav.tariffs')}</h1>
          <p className="text-sm text-slate-500 mt-1">{t('tariffs.subtitle')}</p>
        </div>
        {hasBhm && (
          <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 border border-blue-200 rounded-2xl shadow-xs">
            <svg className="w-4 h-4 text-blue-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-xs text-blue-700 font-bold">
              {t('tariff.bhmNotice')}
            </span>
          </div>
        )}
      </div>

      {/* ── Joriy obuna holati ── */}
      {billing && (
        <div className={`mb-8 rounded-3xl p-5 border-2 shadow-sm flex items-center gap-4 ${
          billing.subscription_active ? 'bg-emerald-50/80 border-emerald-300' : 'bg-red-50/80 border-red-300'
        }`}>
          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center text-xl font-black shadow-xs ${
            billing.subscription_active ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'
          }`}>
            {billing.subscription_active ? '✓' : '✕'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">{t('tariffs.currentStatus')}</div>
            {billing.subscription_active ? (
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                <span className="text-base font-black text-slate-900">{billing.tariff_name || t('tariff.unknownTariff')}</span>
                {billing.is_trial && (
                  <span className="px-2.5 py-0.5 bg-amber-100 text-amber-800 rounded-full text-xs font-black uppercase tracking-wider">
                    {t('tariffs.trial')}
                  </span>
                )}
                <span className="text-sm font-semibold text-emerald-700">— {billing.days_left} {t('tariffs.daysLeft')}</span>
              </div>
            ) : (
              <span className="text-sm text-red-600 font-bold">{t('tariffs.expired')}</span>
            )}
          </div>
          {billing.subscription_active && billing.subscription_ends_at && (
            <div className="text-right text-xs text-slate-500 shrink-0">
              <div>{t('tariffs.expiresOn')}</div>
              <div className="text-sm font-black text-slate-800">{new Date(billing.subscription_ends_at).toLocaleDateString('uz-UZ')}</div>
            </div>
          )}
        </div>
      )}

      {/* ── Paket muddati tanlash (1 oy | 3 oy | 6 oy -10% | 1 yil -20%) ── */}
      <div className="flex flex-col items-center justify-center mb-8">
        <div className="inline-flex p-1.5 bg-slate-100 rounded-2xl border border-slate-200/90 shadow-inner gap-1 flex-wrap justify-center">
          {[
            { m: 1, label: t('tariffs.package1m') },
            { m: 3, label: t('tariffs.package3m') },
            { m: 6, label: t('tariffs.package6m'), badge: '-10%' },
            { m: 12, label: t('tariffs.package12m'), badge: '-20%' },
          ].map(opt => {
            const active = selectedMonths === opt.m;
            return (
              <button
                key={opt.m}
                onClick={() => setSelectedMonths(opt.m)}
                className={`relative px-5 py-2.5 rounded-xl text-xs sm:text-sm font-bold transition-all cursor-pointer flex items-center gap-2 ${
                  active
                    ? 'bg-white text-blue-700 shadow-md ring-1 ring-slate-200'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
                }`}
              >
                <span>{opt.label}</span>
                {opt.badge && (
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-black ${
                    active ? 'bg-blue-600 text-white' : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    {opt.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-slate-500 font-medium mt-2.5">
          Paket muddatini tanlang: 6 oyga <span className="font-bold text-emerald-600">-10%</span>, 1 yilga <span className="font-bold text-emerald-600">-20%</span> chegirma
        </p>
      </div>

      {/* ── Keng, aniq va muvozanatli tarif kartalar (2 ustunli keng dizayn) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-7 items-stretch">
        {tariffs.map(tariff => {
          const theme = getTariffTheme(tariff.name);
          const IconComp = theme.icon;
          const isMini = theme.type === 'mini';
          const minMonths = tariff.min_duration_months || 1;
          const isUnderMin = selectedMonths < minMonths;
          const effMonths = Math.max(selectedMonths, minMonths);

          let discountRate = 0;
          if (effMonths >= 12) discountRate = 0.20;
          else if (effMonths >= 6) discountRate = 0.10;

          const baseMonthly = tariff.price_per_month || 0;
          const discountedMonthly = Math.round(baseMonthly * (1 - discountRate));
          const totalPackagePrice = Math.round(discountedMonthly * effMonths);
          const savedAmount = Math.max(0, (baseMonthly * effMonths) - totalPackagePrice);

          return (
            <div
              key={tariff.id}
              className={`relative rounded-3xl border-2 overflow-hidden flex flex-col justify-between transition-all duration-300 shadow-sm ${
                theme.bgCls
              } ${theme.borderCls} ${
                isCurrent(tariff) ? 'ring-2 ring-offset-2 ring-blue-500' : ''
              }`}
            >
              {/* Yuqori accent chiziq */}
              <div className={`h-1.5 w-full bg-gradient-to-r ${theme.accentBar}`} />

              <div className="p-6 sm:p-7 flex-1 flex flex-col justify-between">
                <div>
                  {/* ── Top Header & Price Row ── */}
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 pb-4 border-b border-slate-100">
                    <div className="flex items-start gap-3.5">
                      <div className={`w-12 h-12 rounded-2xl ${theme.iconBg} flex items-center justify-center shadow-xs shrink-0`}>
                        <IconComp size={24} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-black text-slate-900 text-xl tracking-tight">{tariff.name}</h3>
                          <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${theme.badgeCls}`}>
                            {theme.badge}
                          </span>
                          {isCurrent(tariff) && (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-blue-600 text-white">
                              ✓ {t('tariffs.currentPlan')}
                            </span>
                          )}
                        </div>
                        {tariff.description && (
                          <p className="text-xs text-slate-500 mt-1 leading-relaxed max-w-sm">{tariff.description}</p>
                        )}
                      </div>
                    </div>

                    {/* Price Block */}
                    <div className="sm:text-right shrink-0 bg-slate-50/80 sm:bg-transparent p-3 sm:p-0 rounded-2xl">
                      {tariff.price_per_month > 0 ? (
                        <div>
                          <div className="flex items-baseline sm:justify-end gap-1">
                            <span className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
                              {fmtMoney(discountedMonthly)}
                            </span>
                            <span className="text-xs font-bold text-slate-400">so'm/oy</span>
                          </div>
                          {effMonths > 1 && (
                            <div className="text-xs text-slate-600 font-semibold mt-0.5">
                              {effMonths} oylik: <span className={`font-black ${theme.priceColor}`}>{fmtMoney(totalPackagePrice)} s</span>
                            </div>
                          )}
                          {savedAmount > 0 && (
                            <div className="mt-1">
                              <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                                ✓ Tejaladi: {fmtMoney(savedAmount)} s (-{Math.round(discountRate * 100)}%)
                              </span>
                            </div>
                          )}
                          {isUnderMin && (
                            <div className="mt-1.5 text-[11px] font-bold text-amber-800 bg-amber-50 border border-amber-200 px-2 py-1 rounded-lg flex items-center sm:justify-end gap-1">
                              <AlertTriangle size={12} className="shrink-0 text-amber-600" />
                              <span>Kamida {minMonths} oylik paket talab etiladi</span>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-2xl font-black text-emerald-600">{t('tariffs.trial')}</div>
                      )}
                    </div>
                  </div>

                  {/* ── 2-Ustunli Kvotalar & Imkoniyatlar Paneli (Keng va aniq) ── */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-5">
                    {/* Chap ustun: Kvotalar va Resurslar */}
                    <div className="bg-slate-50/70 border border-slate-100 rounded-2xl p-3.5 space-y-2">
                      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                        Resurs Limitlari
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-600 font-medium">
                          <Package size={15} className="text-amber-600 shrink-0" />
                          Tovar limiti:
                        </span>
                        <span className={`font-black ${tariff.max_products > 0 ? (isMini ? 'text-amber-700' : 'text-slate-900') : 'text-emerald-600'}`}>
                          {tariff.max_products > 0 ? `${tariff.max_products.toLocaleString('uz-UZ')} ta` : 'Cheksiz'}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-600 font-medium">
                          <Warehouse size={15} className="text-blue-600 shrink-0" />
                          Omborlar:
                        </span>
                        <span className="font-black text-slate-900">
                          {tariff.max_warehouses && tariff.max_warehouses < 9999 ? `${tariff.max_warehouses} ta` : 'Cheksiz'}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-600 font-medium">
                          <Users size={15} className="text-indigo-600 shrink-0" />
                          Xodimlar:
                        </span>
                        <span className="font-black text-slate-900">
                          {tariff.max_users >= 9999 ? 'Cheksiz' : `${tariff.max_users} ta`}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-600 font-medium">
                          <Bike size={15} className="text-violet-600 shrink-0" />
                          Savdo agentlari:
                        </span>
                        <span className={`font-black ${tariff.max_agents > 0 ? 'text-blue-700' : 'text-slate-400'}`}>
                          {tariff.max_agents > 0 ? `${tariff.max_agents} ta` : '—'}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-600 font-medium">
                          <Truck size={15} className="text-sky-600 shrink-0" />
                          Kuryerlar:
                        </span>
                        <span className={`font-black ${tariff.max_couriers > 0 ? 'text-blue-700' : 'text-slate-400'}`}>
                          {tariff.max_couriers > 0 ? `${tariff.max_couriers} ta` : '—'}
                        </span>
                      </div>
                    </div>

                    {/* O'ng ustun: Modullar & Funksiyalar */}
                    <div className="bg-slate-50/70 border border-slate-100 rounded-2xl p-3.5 space-y-2 flex flex-col justify-between">
                      <div>
                        <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                          Tizim Modullari
                        </div>

                        <div className="flex items-center justify-between text-xs py-1">
                          <span className="flex items-center gap-2 text-slate-600 font-medium">
                            <BarChart3 size={15} className="text-blue-600 shrink-0" />
                            P&L 2 davr solishtirish:
                          </span>
                          <span className={`font-black text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                            tariff.has_pnl_compare ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-400'
                          }`}>
                            {tariff.has_pnl_compare ? <><Check size={12} /> Bor</> : <><X size={12} /> Yo'q</>}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-xs py-1">
                          <span className="flex items-center gap-2 text-slate-600 font-medium">
                            <Factory size={15} className="text-amber-600 shrink-0" />
                            Ishlab chiqarish:
                          </span>
                          <span className={`font-black text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                            tariff.has_manufacturing ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-400'
                          }`}>
                            {tariff.has_manufacturing ? <><Check size={12} /> Bor</> : <><X size={12} /> Yo'q</>}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-xs py-1">
                          <span className="flex items-center gap-2 text-slate-600 font-medium">
                            <Share2 size={15} className="text-purple-600 shrink-0" />
                            Distribyutsiya:
                          </span>
                          <span className={`font-black text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1 ${
                            tariff.has_distribution ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-400'
                          }`}>
                            {tariff.has_distribution ? <><Check size={12} /> Bor</> : <><X size={12} /> Yo'q</>}
                          </span>
                        </div>
                      </div>

                      {tariff.bhm_percent != null && tariff.price_per_month > 0 && (
                        <div className="pt-2 border-t border-dashed border-slate-200">
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-blue-50 border border-blue-100 rounded-lg text-[11px] text-blue-700 font-semibold">
                            BHM ulushi: <span className="font-black">{tariff.bhm_percent}%</span>
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* ── Tugmalar qatori (Yonma-yon 2 ta tugma) ── */}
                <div className="pt-4 border-t border-slate-100">
                  {isCurrent(tariff) ? (
                    <div className="w-full py-3 text-center font-black rounded-xl text-sm bg-emerald-50 text-emerald-800 border border-emerald-300 flex items-center justify-center gap-2">
                      <Check size={16} /> {t('tariff.active')}
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <button
                        onClick={() => handlePayme(tariff, effMonths, totalPackagePrice)}
                        disabled={trialLoading}
                        className="py-3 px-4 bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white font-bold rounded-xl text-sm transition-all shadow-md shadow-emerald-600/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60"
                      >
                        {trialLoading ? t('tariff.waiting') : (
                          <>
                            <CreditCard size={17} className="shrink-0" />
                            <span>Payme orqali to'lash</span>
                          </>
                        )}
                      </button>

                      <button
                        onClick={() => handleBuyTariff(tariff, effMonths, totalPackagePrice)}
                        disabled={trialLoading || (hasActiveSub && !isCurrent(tariff))}
                        className={`py-3 px-4 bg-gradient-to-r ${theme.btnGradient} text-white font-bold rounded-xl text-sm transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60`}
                      >
                        {trialLoading ? t('tariff.waiting') : (
                          <>
                            <Wallet size={17} className="shrink-0" />
                            <span>Balansdan sotib olish</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SubscriptionHistoryTab({ logs }) {
  const { t } = useLang();
  return (
    <div className="mt-10 mb-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6 tracking-tight">{t('tariff.subscriptionHistory')}</h2>

      <div className="overflow-hidden bg-white rounded-2xl border border-gray-200 shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50/80 border-b border-gray-200">
              <tr>
                <th scope="col" className="pl-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">#</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.startDate')}</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.endDate')}</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.amount')}</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('nav.tariffs')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {logs && logs.length > 0 ? (
                logs.filter(item => item.log_type === 'subscription').map((item, index) => (
                  <tr
                    key={item.id}
                    className="group hover:bg-violet-50/40 transition-all duration-300"
                  >
                    <td className="pl-6 py-4 font-medium text-gray-400 group-hover:text-violet-600 transition-colors">
                      {(index + 1).toString().padStart(2, '0')}
                    </td>
                    <td className="px-4 py-4 text-gray-600 font-medium">
                      {new Date(item.created_at).toLocaleDateString('uz-UZ', {
                        day: 'numeric',
                        month: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </td>
                    <td className="px-3 py-4 text-gray-600 font-medium">
                      {new Date(item.subscription_ends_at).toLocaleDateString('uz-UZ', {
                        day: 'numeric',
                        month: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-bold text-gray-900 group-hover:text-violet-700 transition-colors">
                        {Number(item.amount).toLocaleString()} UZS
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-sm font-medium bg-gray-100 text-gray-600 group-hover:bg-violet-100 group-hover:text-violet-700 transition-colors">
                        {item.note}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="px-6 py-14 text-center">
                    <div className="flex flex-col items-center justify-center space-y-3">
                      <div className="w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center">
                        {/* Bo'sh holat uchun hujjat ikonkasi */}
                        <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                        </svg>
                      </div>
                      <p className="text-gray-500 font-medium text-sm">{t('tariff.noSubscriptionHistory')}</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function BillingHistoryTab({ logs }) {
  const { t } = useLang();
  return (
    <div className="mt-10 mb-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6 tracking-tight">{t('tariff.balanceHistory')}</h2>

      <div className="overflow-hidden bg-white rounded-2xl border border-gray-200 shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50/80 border-b border-gray-200">
              <tr>
                <th scope="col" className="pl-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">#</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.date')}</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.amount')}</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.via')}</th>
                <th scope="col" className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('tariff.note')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {logs && logs.length > 0 ? (
                logs.filter(item => item.log_type === 'top_up').map((item, index) => (
                  <tr
                    key={item?.id}
                    className="group hover:bg-violet-50/40 transition-all duration-300"
                  >
                    <td className="pl-6 py-4 font-medium text-gray-400 group-hover:text-violet-600 transition-colors">
                      {(index + 1).toString().padStart(2, '0')}
                    </td>
                    <td className="px-6 py-4 text-gray-600 font-medium">
                      {new Date(item?.created_at).toLocaleDateString('uz-UZ', {
                        day: 'numeric',
                        month: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-bold text-gray-900 group-hover:text-violet-700 transition-colors">
                        {Number(item?.amount).toLocaleString()} UZS
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-bold text-gray-900 group-hover:text-violet-700 transition-colors">
                        {item?.created_by}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-bold text-gray-900 group-hover:text-violet-700 transition-colors">
                        {item?.note}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="px-6 py-14 text-center">
                    <div className="flex flex-col items-center justify-center space-y-3">
                      <div className="w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center">
                        {/* Bo'sh holat uchun hujjat ikonkasi */}
                        <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                        </svg>
                      </div>
                      <p className="text-gray-500 font-medium text-sm">{t('tariff.noBalanceHistory')}</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default function Tariflar() {
  const { user } = useAuth();
  const { t } = useLang();
  const [tariffs, setTariffs] = useState([]);
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [logs, setLogs] = useState([]);
  const [tabs, setTabs] = useState('tariflar');

  // API dan keladigan sozlamalar
  const [settings, setSettings] = useState({
    card_number: '— — — —',
    card_owner: '...',
    tg_username: '@JavokhirUbaydullayev',
    phone: '...',
    phone_raw: '',
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [t, s, l] = await Promise.all([
          api.get('/billing/tariffs').catch(err => {
            console.error("Failed to load tariffs:", err);
            return { data: [] };
          }),
          api.get('/billing/settings').catch(err => {
            console.error("Failed to load billing settings:", err);
            return { data: null };
          }),
          api.get(`/billing/companies/${user.company_id}/logs`).catch(err => {
            console.error("Failed to load logs:", err);
            return { data: [] };
          }),
        ]);
        if (t?.data) setTariffs(t.data);
        if (s?.data) setSettings(prev => ({ ...prev, ...s.data }));
        if (l?.data) setLogs(l.data);
        try {
          const b = await api.get('/billing/my-company');
          setBilling(b.data);
        } catch (e) {
          console.error("Failed to load my-company billing:", e);
        }
      } catch (e) {
        console.error("Global fetchData error:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [user]);

  const handlePayme = async (directTariff = null, customMonths = 1, customAmount = null) => {
    const tariffToPay = directTariff;
    if (!tariffToPay) return;

    setTrialLoading(true);
    try {
      const payMonths = customMonths || 1;
      const amount = customAmount != null ? Math.round(customAmount) : Math.round(tariffToPay.price_per_month * payMonths);
      const res = await api.post('/payme/checkout-url', { amount });

      // Popup oynani markazda ochish
      const w = 600, h = 700;
      const left = Math.round(window.innerWidth / 2 - w / 2);
      const top = Math.round(window.innerHeight / 2 - h / 2);
      const popup = window.open(
        res.data.checkout_url,
        'payme_checkout',
        `width=${w},height=${h},top=${top},left=${left}`
      );

      // Popup yopilishini kutib balansni yangilaymiz
      const timer = setInterval(async () => {
        if (popup && popup.closed) {
          clearInterval(timer);
          try {
            const b = await api.get('/billing/my-company');
            setBilling(b.data);
            setToast({ msg: t('tariff.balanceUpdated'), ok: true });
          } catch { /* ignore */ }
        }
      }, 1000);
    } catch (e) {
      setToast({ msg: e.response?.data?.detail || t('auth.errGeneral'), ok: false });
    } finally {
      setTrialLoading(false);
      setTimeout(() => setToast(null), 4000);
    }
  };

  const copyCard = () => {
    navigator.clipboard.writeText((settings.card_number || '').replace(/\s/g, '')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleBuyTariff = async (tariff, customMonths = 1, customPrice = null) => {
    setTrialLoading(true);
    try {
      // 1. Fetch latest company billing to ensure balance is up-to-date
      const bRes = await api.get('/billing/my-company');
      const latestBilling = bRes.data;
      setBilling(latestBilling);

      const balance = latestBilling.balance || 0;
      const months = customMonths || 1;
      const price = customPrice != null ? customPrice : ((tariff.price_per_month || 0) * months);

      // 2. Perform balance checks
      if (latestBilling.subscription_active && !latestBilling.is_trial && latestBilling.tariff_id !== tariff.id) {
        setToast({ msg: t('tariff.alreadyActiveTariff'), ok: false });
        return;
      }
      if (balance <= 0) {
        setToast({ msg: t('tariff.noBalance'), ok: false });
        return;
      }
      if (balance < price) {
        setToast({ msg: t('tariff.insufficientBalance'), ok: false });
        return;
      }

      // 3. Prompt for confirmation
      const confirmed = window.confirm(
        t('tariff.confirmActivate', { name: `${tariff.name} (${months} ${t('superAdmin.month') || 'oy'})`, amount: fmtMoney(price) })
      );
      if (!confirmed) return;

      // 4. Activate subscription
      const res = await api.post('/billing/my-company/subscribe', {
        tariff_id: tariff.id,
        months: months
      });
      setToast({ msg: res.data.message || t('tariff.subscriptionActivated'), ok: true });

      // Refresh billing info
      const updatedBilling = await api.get('/billing/my-company');
      setBilling(updatedBilling.data);
    } catch (e) {
      setToast({ msg: e.response?.data?.detail || t('auth.errGeneral'), ok: false });
    } finally {
      setTrialLoading(false);
      setTimeout(() => setToast(null), 4000);
    }
  };


  const activateTrial = async () => {
    setTrialLoading(true);
    try {
      const res = await api.post('/billing/activate-my-trial');
      setToast({ msg: res.data.message || t('common.success'), ok: true });
      // billing holatini yangilaymiz
      const b = await api.get('/billing/my-company');
      setBilling(b.data);
    } catch (e) {
      setToast({ msg: e.response?.data?.detail || t('common.error'), ok: false });
    } finally {
      setTrialLoading(false);
      setTimeout(() => setToast(null), 4000);
    }
  };


  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const priceColor = (price) => {
    if (!price) return 'text-emerald-600';
    if (price <= 150000) return 'text-blue-600';
    if (price <= 300000) return 'text-blue-600';
    return 'text-blue-600';
  };

  const bgAccent = (price) => {
    if (!price) return 'from-emerald-50 to-blue-50 border-emerald-200';
    if (price <= 150000) return 'from-blue-50 to-sky-50 border-blue-200';
    if (price <= 300000) return 'from-blue-50 to-violet-50 border-blue-200';
    return 'from-blue-50 to-pink-50 border-blue-200';
  };

  const btnColor = (price) => {
    if (price <= 150000) return 'bg-blue-600 hover:bg-blue-700 shadow-blue-200';
    if (price <= 300000) return 'bg-blue-600 hover:bg-blue-700 shadow-blue-200';
    return 'bg-blue-600 hover:bg-blue-700 shadow-blue-200';
  };

  // isCurrent: tarif ham mos, ham obuna FAOL bo'lishi kerak
  const isCurrent = (tariff) => billing?.tariff_id == tariff.id && billing?.subscription_active;
  const hasActiveSub = billing?.subscription_active && !billing?.is_trial;

  const hasBhm = tariffs.some(tr => tr.bhm_percent != null && tr.price_per_month > 0);

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="flex text-[14px] whitespace-nowrap shadow w-max rounded-lg">
        <button onClick={() => setTabs('tariflar')} className={`px-4 py-1.5 w-35 cursor-pointer font-medium rounded-l-lg ${tabs === 'tariflar' ? 'bg-white text-slate-900' : 'bg-slate-100 text-gray-700'}`}>
          {t('nav.tariffs')}
        </button>
        <button onClick={() => setTabs('subscription')} className={`px-4 py-1.5 cursor-pointer font-medium w-35 ${tabs === 'subscription' ? 'bg-white text-slate-900' : 'bg-slate-100 text-gray-700'}`}>
          {t('tariff.subscriptionHistory')}
        </button>
        <button onClick={() => setTabs('billing')} className={`px-4 py-1.5 rounded-r-lg cursor-pointer font-medium w-35 ${tabs === 'billing' ? 'bg-white text-slate-900' : 'bg-slate-100 text-gray-700'}`}>
          {t('tariff.balanceHistory')}
        </button>
      </div>

      {
        tabs === 'tariflar' && <TariflarTab hasBhm={hasBhm} billing={billing} settings={settings} tariffs={tariffs} bgAccent={bgAccent} btnColor={btnColor} priceColor={priceColor} handleBuyTariff={handleBuyTariff} handlePayme={handlePayme} trialLoading={trialLoading} isCurrent={isCurrent} hasActiveSub={hasActiveSub} />
      }
      {
        tabs === 'subscription' && <SubscriptionHistoryTab logs={logs} />
      }
      {
        tabs === 'billing' && <BillingHistoryTab logs={logs} />
      }

      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-4 right-4 px-6 py-3 rounded-xl shadow-lg text-white font-bold transition-all z-[400] ${toast.ok ? 'bg-emerald-600' : 'bg-red-600'}`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}