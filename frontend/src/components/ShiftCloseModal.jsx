import { useState } from 'react';
import api from '../api/axios';
import { useLang } from '../context/LangContext';
import toast from 'react-hot-toast';
import { uzs, terminalUzs, foreignEntries, tOr } from '../utils/shiftBalances';

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');

const fmtDt = (dt) => {
  if (!dt) return '—';
  return new Date(dt).toLocaleString('uz-UZ', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};

// Smenani yopish modali (T3.1): Shifts sahifasi va POS ekranlari (PosKassa, UlgurjiSotuv) uchun umumiy.
// `shift` — GET /shifts/current javobi (balances, expected_cash, handover_wallets bilan).
// Muvaffaqiyatli yopilgach `onClosed(data)`, bekor qilinsa `onCancel()` chaqiriladi.
export default function ShiftCloseModal({ shift, onClosed, onCancel }) {
  const { t } = useLang();
  const [closingCash, setClosingCash] = useState('');
  const [selectedWallet, setSelectedWallet] = useState('');
  const [selectedCardWallet, setSelectedCardWallet] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleClose = async (e) => {
    e.preventDefault(); setSaving(true); setError('');
    try {
      const payload = {};
      if (closingCash !== '') payload.closing_cash = Number(closingCash);
      if (selectedWallet) payload.wallet_id = Number(selectedWallet);
      if (selectedCardWallet) payload.wallet_card_id = Number(selectedCardWallet);

      const { data } = await api.post(`/shifts/${shift.id}/close`, payload);
      toast.success(t('shift.closeSuccess'));
      // Yopilgandan keyin farq ko'rsatiladi: kamomad (manfiy) yoki ortiqcha (musbat)
      const diff = Number(data?.difference);
      if (Number.isFinite(diff) && diff !== 0) {
        const label = diff < 0 ? tOr(t, 'shift.shortage', 'Kamomad') : tOr(t, 'shift.surplus', 'Ortiqcha');
        toast(`${label}: ${fmt(Math.abs(diff))} so'm`, { icon: diff < 0 ? '🔻' : '🔺', duration: 6000 });
      }
      (data?.warnings || []).forEach(w => toast(w, { icon: '⚠️' }));
      onClosed && onClosed(data);
    } catch (err) { setError(err.response?.data?.detail || t('auth.errGeneral')); }
    finally { setSaving(false); }
  };

  const handoverWallets = shift?.handover_wallets || [];
  // Hisob-kitob: kassir kiritgan summa - kutilgan summa (manfiy = kamomad, musbat = ortiqcha)
  const expectedCash = uzs(shift?.expected_cash);
  const cashDiff = Number(closingCash || 0) - expectedCash;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onClick={onCancel}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-6 border-b border-slate-100">
          <div>
            <h3 className="text-lg font-bold text-slate-800">{t('shift.closeShiftTitle')}</h3>
            <p className="text-xs text-slate-400 mt-0.5">{t('shift.closeShiftSubtitle')}</p>
          </div>
          <button onClick={onCancel} className="p-2 hover:bg-slate-100 rounded-xl text-slate-400">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form onSubmit={handleClose} className="p-6 space-y-4">
          {/* Smena ma'lumoti */}
          <div className="p-4 bg-slate-50 rounded-xl text-sm space-y-2">
            <div className="flex justify-between text-slate-600">
              <span>{t('shift.startTime')}:</span>
              <span className="font-medium text-slate-800">{fmtDt(shift.opened_at)}</span>
            </div>
            <div className="flex justify-between text-slate-600">
              <span>{t('shift.openingCashLabel')}:</span>
              <span className="font-medium text-slate-800">{fmt(shift.opening_cash)} so'm</span>
            </div>
            <div className="flex justify-between text-emerald-600">
              <span>{t('shift.cashSalesPlus')}:</span>
              <span className="font-bold">{fmt(uzs(shift.balances?.cash?.UZS))} so'm</span>
            </div>
            {foreignEntries(shift.balances?.cash).map(([cur, v]) => (
              <div key={`cash-${cur}`} className="flex justify-between text-emerald-600 text-xs">
                <span>{t('shift.cashSalesPlus')} ({cur}):</span>
                <span className="font-bold">{cur}: {fmt(v)}</span>
              </div>
            ))}
            {Object.entries(shift.balances || {}).map(([pType, map]) => {
              if (pType === 'cash') return null;
              const foreign = foreignEntries(map);
              if (uzs(map) === 0 && foreign.length === 0) return null;
              return (
                <div key={pType}>
                  <div className="flex justify-between text-blue-600">
                    <span className="capitalize">{pType} {t('shift.salesPlus')}:</span>
                    <span className="font-bold">{fmt(uzs(map))} so'm</span>
                  </div>
                  {foreign.map(([cur, v]) => (
                    <div key={cur} className="flex justify-between text-blue-500 text-xs">
                      <span className="capitalize">{pType} ({cur}):</span>
                      <span className="font-bold">{cur}: {fmt(v)}</span>
                    </div>
                  ))}
                </div>
              );
            })}
            <div className="border-t border-slate-200 pt-2 mt-2 flex justify-between font-bold text-slate-800">
              <span>{t('shift.expectedCashBalance')}:</span>
              <span>{fmt(expectedCash)} so'm</span>
            </div>
            {closingCash !== '' && (
              <div className={`flex justify-between font-bold ${cashDiff === 0 ? 'text-emerald-600' : cashDiff < 0 ? 'text-red-600' : 'text-blue-600'}`}>
                <span>
                  {cashDiff < 0 ? tOr(t, 'shift.shortage', 'Kamomad') : cashDiff > 0 ? tOr(t, 'shift.surplus', 'Ortiqcha') : tOr(t, 'shift.difference', 'Farq')}:
                </span>
                <span>{cashDiff > 0 ? '+' : ''}{fmt(cashDiff)} so'm</span>
              </div>
            )}
          </div>

          {/* Kassadagi pul */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                {t('shift.actualCash')} <span className="text-red-500">*</span>
              </label>
              <input
                type="number" min="0" required autoFocus value={closingCash}
                onChange={e => setClosingCash(e.target.value)}
                placeholder={t('shift.actualCashPlaceholder')}
                className="w-full px-3.5 py-2.5 border-2 border-slate-200 focus:border-emerald-500 rounded-xl text-sm font-bold focus:outline-none transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                {t('shift.terminalPayments')}
              </label>
              <input
                readOnly
                value={fmt(terminalUzs(shift.balances))}
                className="w-full px-3.5 py-2.5 border-2 border-slate-100 bg-slate-50 rounded-xl text-sm font-bold text-slate-500 cursor-not-allowed"
              />
            </div>
          </div>

          {/* Inkassatsiya */}
          {handoverWallets.length > 0 && (
            <div className="space-y-3 p-3 bg-slate-50 border border-slate-200 rounded-xl">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  📦 {t('shift.handOverCash')}
                </label>
                <select
                  value={selectedWallet}
                  onChange={e => setSelectedWallet(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
                >
                  <option value="">— {t('shift.doNotHandOver')} —</option>
                  {handoverWallets.filter(w => !w.type || w.type === 'cash').map(w => (
                    <option key={w.id} value={w.id}>
                      {w.name}{w.balance !== undefined ? ` (${t('shift.currentBalance')}: ${fmt(w.balance)} so'm)` : ''}
                    </option>
                  ))}
                </select>
                {selectedWallet && String(shift.cashier_wallet_id) === selectedWallet && (
                  <p className="text-xs text-amber-600 mt-1">{t('shift.handoverSameWallet')}</p>
                )}
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  💳 {t('shift.handOverTerminal')}
                </label>
                <select
                  value={selectedCardWallet}
                  onChange={e => setSelectedCardWallet(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">— {t('shift.doNotHandOver')} —</option>
                  {handoverWallets.map(w => (
                    <option key={w.id} value={w.id}>
                      {w.name}{w.balance !== undefined ? ` (${t('shift.currentBalance')}: ${fmt(w.balance)} so'm)` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-slate-400">{t('shift.handoverCapped')}</p>
            </div>
          )}
          {handoverWallets.length === 0 && (
            <p className="text-xs text-slate-400">{t('shift.noHandoverWallets')}</p>
          )}

          {error && <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-xl">{error}</div>}

          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onCancel} className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">{t('common.cancel')}</button>
            <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 disabled:opacity-60 text-white font-bold text-sm rounded-xl transition-colors shadow-sm shadow-red-200">
              {saving ? '...' : `✓ ${t('shift.close')}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
