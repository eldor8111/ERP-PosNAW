import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';

const fmtMoney = (n) => Number(n || 0).toLocaleString('uz-UZ');

const TG_ICON = (
  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L7.09 13.98l-2.95-.924c-.642-.2-.654-.642.136-.953l11.57-4.461c.537-.194 1.006.131.716.606z"/>
  </svg>
);
const PHONE_ICON = (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
  </svg>
);

export default function Tariflar() {
  const { user } = useAuth();
  const { t } = useLang();
  const [tariffs, setTariffs] = useState([]);
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(true);
  const [buyModal, setBuyModal] = useState(null);
  const [months, setMonths] = useState(1);
  const [copied, setCopied] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [toast, setToast] = useState(null);

  // API dan keladigan sozlamalar
  const [settings, setSettings] = useState({
    card_number: '— — — —',
    card_owner:  '...',
    tg_username: 'loading',
    phone:       '...',
    phone_raw:   '',
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [t, s] = await Promise.all([
          api.get('/billing/tariffs'),
          api.get('/billing/settings'),
        ]);
        setTariffs(t.data);
        setSettings(s.data);
        try {
          const b = await api.get('/billing/my-company');
          setBilling(b.data);
        } catch { /* company yo'q bo'lsa skip */ }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [user]);

  const handlePayme = async () => {
    if (!buyModal) return;
    setTrialLoading(true);
    try {
      const amount = Math.round(buyModal.tariff.price_per_month * months);
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

      setBuyModal(null);

      // Popup yopilishini kutib balansni yangilaymiz
      const timer = setInterval(async () => {
        if (popup && popup.closed) {
          clearInterval(timer);
          try {
            const b = await api.get('/billing/my-company');
            setBilling(b.data);
            setToast({ msg: "Balans yangilandi!", ok: true });
          } catch { /* ignore */ }
        }
      }, 1000);
    } catch (e) {
      setToast({ msg: e.response?.data?.detail || "Xatolik yuz berdi", ok: false });
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

  const openBuy = (t) => {
    setMonths(1);
    setBuyModal({ tariff: t });
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

  const total = buyModal ? Math.round(buyModal.tariff.price_per_month * months) : 0;

  const tgMessage = buyModal
    ? encodeURIComponent(
        `Salom! Men ${billing?.name || user?.name || 'korxona'} uchun ${buyModal.tariff.name} tarifini ${months} oyga sotib olmoqchiman.\n` +
        `Summa: ${fmtMoney(total)} so'm\n` +
        `Kodni: ${billing?.org_code || '—'}\n` +
        `Iltimos balni to'ldirib bering.`
      )
    : '';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const priceColor = (price) => {
    if (!price) return 'text-emerald-600';
    if (price <= 150000) return 'text-blue-600';
    if (price <= 300000) return 'text-indigo-600';
    return 'text-purple-600';
  };

  const bgAccent = (price) => {
    if (!price) return 'from-emerald-50 to-teal-50 border-emerald-200';
    if (price <= 150000) return 'from-blue-50 to-sky-50 border-blue-200';
    if (price <= 300000) return 'from-indigo-50 to-violet-50 border-indigo-200';
    return 'from-purple-50 to-pink-50 border-purple-200';
  };

  const btnColor = (price) => {
    if (price <= 150000) return 'bg-blue-600 hover:bg-blue-700 shadow-blue-200';
    if (price <= 300000) return 'bg-indigo-600 hover:bg-indigo-700 shadow-indigo-200';
    return 'bg-purple-600 hover:bg-purple-700 shadow-purple-200';
  };

  const isCurrent = (tariff) => billing?.tariff_id === tariff.id;

  const hasBhm = tariffs.some(tr => tr.bhm_percent != null && tr.price_per_month > 0);

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">

      {/* ── Header + BHM noti ── */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-black text-slate-800 leading-tight">{t('nav.tariffs')}</h1>
          <p className="text-xs text-slate-400 mt-0.5">{t('tariffs.subtitle')}</p>
        </div>
        {hasBhm && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 border border-indigo-100 rounded-xl">
            <svg className="w-3.5 h-3.5 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-xs text-indigo-600 font-medium">
              Tariflar O'zbekiston Respublikasi <span className="font-bold">BHM</span> asosida tuzilgan
            </span>
          </div>
        )}
      </div>

      {/* ── Joriy obuna holati ── */}
      {billing && (
        <div className={`mb-5 rounded-xl px-4 py-3 border flex items-center gap-3 ${billing.subscription_active ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-base font-black ${billing.subscription_active ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-500'}`}>
            {billing.subscription_active ? '✓' : '✕'}
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold text-slate-500">{t('tariffs.currentStatus')}: </span>
            {billing.subscription_active ? (
              <span className="text-xs text-emerald-700">
                <span className="font-bold">{billing.tariff_name || 'Noma\'lum tarif'}</span>
                {billing.is_trial && <span className="ml-1.5 px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded-full text-[10px] font-bold">{t('tariffs.trial')}</span>}
                <span className="ml-1.5 text-slate-400">— {billing.days_left} {t('tariffs.daysLeft')}</span>
              </span>
            ) : (
              <span className="text-xs text-red-600 font-bold">{t('tariffs.expired')}</span>
            )}
          </div>
          {billing.subscription_active && billing.subscription_ends_at && (
            <div className="text-right text-[11px] text-slate-400 shrink-0">
              <div>{t('tariffs.expiresOn')}</div>
              <div className="font-bold text-slate-600">{new Date(billing.subscription_ends_at).toLocaleDateString('uz-UZ')}</div>
            </div>
          )}
        </div>
      )}

      {/* ── Tarif kartalar ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {tariffs
          .filter(tariff => tariff.price_per_month > 0 || !billing?.subscription_ends_at || (billing?.is_trial && billing?.subscription_active))
          .map(tariff => (
          <div
            key={tariff.id}
            className={`relative rounded-2xl border-2 bg-gradient-to-br p-4 flex flex-col transition-all hover:shadow-md ${bgAccent(tariff.price_per_month)} ${isCurrent(tariff) ? 'ring-2 ring-offset-2 ring-indigo-400' : ''}`}
          >
            {isCurrent(tariff) && (
              <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-indigo-600 text-white text-[10px] font-black rounded-full whitespace-nowrap shadow">
                {t('tariffs.currentPlan')}
              </span>
            )}

            <div className="mb-2">
              <h3 className="font-black text-slate-800 text-sm">{tariff.name}</h3>
              {tariff.description && <p className="text-[11px] text-slate-500 mt-0.5">{tariff.description}</p>}
            </div>

            <div className={`text-2xl font-black mb-2 ${priceColor(tariff.price_per_month)}`}>
              {tariff.price_per_month > 0 ? (
                <>{fmtMoney(tariff.price_per_month)} <span className="text-sm font-semibold text-slate-400">{t('tariffs.perMonth')}</span></>
              ) : (
                t('tariffs.trial')
              )}
            </div>

            <div className="space-y-1 flex-1">
              <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                <svg className="w-3 h-3 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {t('tariffs.duration')} <span className="font-bold">{tariff.duration_days} kun</span>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                <svg className="w-3 h-3 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                {t('tariffs.maxUsers')} <span className="font-bold">{tariff.max_users >= 9999 ? t('tariffs.unlimited') : tariff.max_users}</span>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                <svg className="w-3 h-3 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                {t('tariffs.maxBranches')} <span className="font-bold">{tariff.max_branches >= 9999 ? t('tariffs.unlimited') : tariff.max_branches}</span>
              </div>
            </div>

            {/* BHM ko'rsatkichi */}
            {tariff.bhm_percent != null && tariff.price_per_month > 0 && (
              <div className="mt-2.5 pt-2.5 border-t border-dashed border-slate-200/80">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 border border-indigo-100 rounded-lg text-[10px] text-indigo-600 font-semibold">
                  BHMning <span className="font-black">{tariff.bhm_percent}%</span>
                  <span className="text-indigo-400">({(tariff.bhm_percent / 100).toFixed(2)} qism)</span>
                </span>
              </div>
            )}

            {/* Tugma */}
            <div className="mt-3">
              {!isCurrent(tariff) && (
                tariff.price_per_month <= 0 ? (
                  <button
                    onClick={activateTrial}
                    disabled={trialLoading}
                    className="w-full py-2 text-white font-bold rounded-xl text-xs shadow-md transition-all bg-emerald-600 hover:bg-emerald-700 shadow-emerald-200 disabled:opacity-60"
                  >
                    {trialLoading ? t('tariffs.activating') : t('tariffs.tryFree')}
                  </button>
                ) : (
                  <button
                    onClick={() => openBuy(tariff)}
                    className={`w-full py-2 text-white font-bold rounded-xl text-xs shadow-md transition-all ${btnColor(tariff.price_per_month)}`}
                  >
                    {t('tariffs.buy')}
                  </button>
                )
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ── Aloqa ── */}
      <div className="mt-5 bg-slate-50 rounded-xl px-5 py-4 border border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-xs text-slate-500 font-medium">Savol yoki muammo bo'lsa biz bilan bog'laning:</p>
        <div className="flex items-center gap-2">
          <a href={`https://t.me/${settings.tg_username}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-[#2AABEE] hover:bg-[#1d9bd6] text-white rounded-xl font-bold text-xs transition-all shadow-sm">
            {TG_ICON} @{settings.tg_username}
          </a>
          <a href={`tel:${settings.phone_raw}`}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold text-xs transition-all shadow-sm">
            {PHONE_ICON} {settings.phone}
          </a>
        </div>
      </div>

      {/* ─── Sotib olish modali ─── */}
      {buyModal && (
        <div className="fixed inset-0 z-300 flex items-center justify-center bg-black/50 p-4" onClick={() => setBuyModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>

            {/* Header */}
            <div className={`rounded-t-2xl px-6 py-4 bg-linear-to-r ${buyModal.tariff.price_per_month <= 150000 ? 'from-blue-600 to-sky-500' : buyModal.tariff.price_per_month <= 300000 ? 'from-indigo-600 to-violet-500' : 'from-purple-600 to-pink-500'}`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-white/70 text-xs font-semibold uppercase tracking-wider">Tarif</div>
                  <div className="text-white font-black text-xl">{buyModal.tariff.name}</div>
                </div>
                <button onClick={() => setBuyModal(null)} className="text-white/70 hover:text-white">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="p-6 space-y-5">
              {/* Muddat tanlash */}
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wide">{t('tariffs.durationMonths')}</label>
                <div className="grid grid-cols-5 gap-2">
                  {[1, 2, 3, 6, 12].map(m => (
                    <button key={m} onClick={() => setMonths(m)}
                      className={`py-2 rounded-xl text-sm font-bold border-2 transition-all ${months === m ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 text-slate-500 hover:border-slate-300'}`}>
                      {m}
                    </button>
                  ))}
                </div>
              </div>

              {/* Jami summa */}
              <div className="bg-slate-50 rounded-xl p-4 flex items-center justify-between">
                <div className="text-sm text-slate-500">
                  {fmtMoney(buyModal.tariff.price_per_month)} × {months} oy
                </div>
                <div className="text-2xl font-black text-slate-800">
                  {fmtMoney(total)} <span className="text-base font-semibold text-slate-400">so'm</span>
                </div>
              </div>

              {/* Karta raqami */}
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wide">{t('tariffs.cardNumber')}</label>
                <div className="bg-linear-to-r from-slate-800 to-slate-700 rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <div className="text-white font-mono text-lg font-bold tracking-widest">{settings.card_number}</div>
                    <div className="text-slate-400 text-xs mt-0.5">{settings.card_owner}</div>
                  </div>
                  <button onClick={copyCard}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${copied ? 'bg-emerald-500 text-white' : 'bg-white/10 hover:bg-white/20 text-white'}`}>
                    {copied ? `✓ ${t('tariffs.copied')}` : t('tariffs.copy')}
                  </button>
                </div>
              </div>

              {/* Yo'riqnoma */}
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <div className="text-xs font-bold text-amber-700 mb-2">{t('tariffs.paymentInstructions')}</div>
                <ol className="space-y-1.5 text-xs text-amber-800">
                  <li className="flex gap-2"><span className="font-black w-4">1.</span>Quyidagi Payme tugmasi orqali to'lovni tasdiqlang</li>
                  <li className="flex gap-2"><span className="font-black w-4">2.</span>Yoki yuqoridagi kartaga <span className="font-bold">{fmtMoney(total)} so'm</span> o'tkazib Telegramga yozing</li>
                  <li className="flex gap-2"><span className="font-black w-4">3.</span>Balans to'ldirilgach, o'zingiz obuna faollashtirasiz</li>
                </ol>
              </div>

              {/* Harakatlar */}
              <div className="grid grid-cols-1 gap-3">
                <button
                  onClick={handlePayme}
                  disabled={trialLoading}
                  className="flex items-center justify-center gap-2 py-3.5 bg-[#4BDE95] hover:bg-[#3ccf87] text-white font-bold rounded-xl text-base transition-all shadow-md disabled:opacity-60"
                >
                  {trialLoading ? "Kuting..." : (
                    <>💳 Payme orqali to'lash</>
                  )}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-100">
                <a
                  href={`https://t.me/${settings.tg_username}?text=${tgMessage}`}
                  target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 py-3 bg-[#2AABEE] hover:bg-[#1d9bd6] text-white font-bold rounded-xl text-sm transition-all shadow-md shadow-blue-200"
                >
                  {TG_ICON} Telegram
                </a>
                <a
                  href={`tel:${settings.phone_raw}`}
                  className="flex items-center justify-center gap-2 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-sm transition-all"
                >
                  {PHONE_ICON} {t('tariffs.call')}
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-4 right-4 px-6 py-3 rounded-xl shadow-lg text-white font-bold transition-all z-[400] ${toast.ok ? 'bg-emerald-600' : 'bg-red-600'}`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
