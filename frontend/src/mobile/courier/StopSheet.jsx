import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { X, Camera, Check, Ban, Phone, Navigation, Truck } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import api, { errText } from '../lib/api';
import { getPosition, navigateUrl } from '../lib/geo';
import { takePhoto } from '../lib/photo';
import { Btn } from '../ui';
import { fmtMoney } from '../format';

const REASONS = ['absent', 'refused', 'wrong_address', 'no_money', 'other'];

export default function StopSheet({ stop, onClose, onAction }) {
  const { t } = useLang();
  const [detail, setDetail] = useState(null);
  const [mode, setMode] = useState(null); // null | 'confirm' | 'fail'
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [photos, setPhotos] = useState(0);
  const done = ['delivered', 'cancelled'].includes(stop.status);

  useEffect(() => {
    api.get(`/mobile/courier/stops/${encodeURIComponent(stop.group_key)}`)
      .then(r => { setDetail(r.data); setPhotos(r.data.proof_count || 0); })
      .catch(() => { /* oflayn — faqat ro'yxatdagi ma'lumot */ });
  }, [stop.group_key]);

  const s = detail || stop;

  const run = async (action, extra = {}) => {
    setBusy(true);
    const pos = await getPosition({ timeout: 6000 });
    await onAction(stop, action, { ...extra, ...(pos ? { lat: pos.lat, lng: pos.lng } : {}) });
    setBusy(false);
  };

  const photo = async () => {
    const blob = await takePhoto();
    if (!blob) return;
    setBusy(true);
    try {
      const pos = await getPosition({ timeout: 6000 });
      const fd = new FormData();
      fd.append('file', blob, 'proof.jpg');
      if (pos) { fd.append('lat', pos.lat); fd.append('lng', pos.lng); }
      await api.post(`/mobile/courier/stops/${encodeURIComponent(stop.group_key)}/proof`, fd, { timeout: 60000 });
      setPhotos(n => n + 1);
      toast.success(t('m.photoSaved'));
    } catch (e) { toast.error(errText(e, t('m.photoNeedsInternet'))); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/40" onClick={onClose}>
      <div className="bg-bg-base rounded-t-3xl max-h-[88%] flex flex-col" onClick={e => e.stopPropagation()}
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
          <div className="min-w-0">
            <div className="text-lg font-bold text-ink-900">{s.customer_name}</div>
            <div className="text-sm text-ink-500">{s.address || t('logistics.noAddress')}</div>
          </div>
          <button onClick={onClose} className="p-2 -m-2 text-ink-300"><X className="size-6" /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <a href={s.phone ? `tel:${s.phone}` : undefined} className={`min-h-12 rounded-xl border border-line bg-surface flex items-center justify-center gap-2 font-semibold ${s.phone ? 'text-brand' : 'text-ink-300'}`}>
              <Phone className="size-4" />{s.phone || '—'}
            </a>
            <a href={s.lat != null ? navigateUrl(s.lat, s.lng) : undefined} target="_blank" rel="noreferrer"
              className={`min-h-12 rounded-xl border border-line bg-surface flex items-center justify-center gap-2 font-semibold ${s.lat != null ? 'text-brand' : 'text-ink-300'}`}>
              <Navigation className="size-4" />{t('m.navigate')}
            </a>
          </div>

          {s.note && <div className="text-sm bg-warning/10 text-ink-900 rounded-xl px-4 py-3">📝 {s.note}</div>}

          {detail?.items && (
            <div className="bg-surface border border-line rounded-2xl divide-y divide-line">
              {detail.items.map((it, i) => (
                <div key={i} className="flex justify-between gap-3 px-4 py-2.5 text-sm">
                  <span className="text-ink-900">{it.name} <span className="text-ink-500">× {it.quantity} {it.unit || ''}</span></span>
                  <span className="tabular-nums text-ink-500 shrink-0">{fmtMoney(it.amount)}</span>
                </div>
              ))}
              {s.delivery_fee > 0 && (
                <div className="flex justify-between px-4 py-2.5 text-sm text-ink-500">
                  <span>{t('saleDelivery.fee')}</span><span className="tabular-nums">{fmtMoney(s.delivery_fee)}</span>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between bg-surface border border-line rounded-2xl px-4 py-3">
            <span className="text-sm text-ink-500">{t('m.collectFromCustomer')}</span>
            <span className="text-xl font-bold tabular-nums text-ink-900">{fmtMoney(s.collect_amount)} <span className="text-sm font-medium text-ink-500">so'm</span></span>
          </div>
          {s.collect_amount === 0 && <p className="text-xs text-ink-500 -mt-1 px-1">{t('m.noCashHint')}</p>}

          <button onClick={photo} disabled={busy}
            className="w-full min-h-12 rounded-xl border-2 border-dashed border-line text-ink-500 font-semibold flex items-center justify-center gap-2">
            <Camera className="size-5" />{t('m.proofPhoto')}{photos > 0 ? ` (${photos})` : ''}
          </button>

          {mode === 'fail' && (
            <div className="space-y-2">
              <div className="text-sm font-semibold text-ink-900">{t('m.failReason')}</div>
              <div className="flex flex-wrap gap-2">
                {REASONS.map(r => (
                  <button key={r} onClick={() => setReason(t(`m.reason.${r}`))}
                    className={`px-3 min-h-10 rounded-xl text-sm font-medium border ${reason === t(`m.reason.${r}`) ? 'bg-danger text-white border-danger' : 'border-line bg-surface text-ink-900'}`}>
                    {t(`m.reason.${r}`)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {mode === 'confirm' && s.collect_amount > 0 && (
            <div className="text-center text-sm font-semibold text-ink-900 bg-success/10 rounded-xl px-4 py-3">
              {t('m.confirmCash', { amount: fmtMoney(s.collect_amount) })}
            </div>
          )}
        </div>

        {!done && (
          <div className="px-5 pt-3 pb-4 grid grid-cols-2 gap-2">
            {mode === null && <>
              {stop.status === 'assigned'
                ? <Btn variant="ghost" onClick={() => run('on_way')} loading={busy}><Truck className="size-4" />{t('m.action.on_way')}</Btn>
                : <Btn variant="ghost" onClick={() => setMode('fail')} className="!text-danger"><Ban className="size-4" />{t('m.action.failed')}</Btn>}
              <Btn variant="success" onClick={() => setMode('confirm')}><Check className="size-5" />{t('m.action.delivered')}</Btn>
            </>}
            {mode === 'confirm' && <>
              <Btn variant="ghost" onClick={() => setMode(null)}>{t('common.cancel')}</Btn>
              <Btn variant="success" loading={busy} onClick={() => run('delivered')}>{t('m.yesDelivered')}</Btn>
            </>}
            {mode === 'fail' && <>
              <Btn variant="ghost" onClick={() => { setMode(null); setReason(''); }}>{t('common.cancel')}</Btn>
              <Btn variant="danger" loading={busy} disabled={!reason} onClick={() => run('failed', { reason })}>{t('m.action.failed')}</Btn>
            </>}
          </div>
        )}
      </div>
    </div>
  );
}
