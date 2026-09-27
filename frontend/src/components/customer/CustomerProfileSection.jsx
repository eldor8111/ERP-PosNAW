import { useEffect, useMemo, useRef, useState } from 'react';
import { MapPin, Send, Plus, Minus, ImagePlus, Paperclip, Trash2, Download, FileText, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { REGIONS } from '../../constants/regions';
import MapPicker from '../MapPicker';
import { yandexMapsUrl } from '../../utils/maps';

const inputCls = 'w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500';
const labelCls = 'block text-xs font-semibold text-slate-600 mb-1.5';
const API_ORIGIN = (import.meta.env.VITE_API_URL || '').replace(/\/api\/?$/, '');
const fmtSize = (b) => b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil((b || 0) / 1024)} KB`;

function Section({ title, children, right }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{title}</h4>
        {right}
      </div>
      {children}
    </div>
  );
}

/**
 * Mijoz oynasining o'ng ustuni: manzil + xarita + Telegram lokatsiya,
 * qo'shimcha telefonlar, chegirma, agent, ish kunlari, tashrif radiusi,
 * rasm va hujjatlar.
 *
 * customer — tahrirlanayotgan mijoz (yangi bo'lsa null). Yangi mijozda
 * rasm/hujjatlar `pending`da saqlanib, mijoz yaratilgach yuklanadi.
 */
export default function CustomerProfileSection({ form, setForm, customer, pending, setPending, onCustomerUpdated }) {
  const { t } = useLang();
  const [agents, setAgents] = useState([]);
  const [docs, setDocs] = useState([]);
  const [photoUrl, setPhotoUrl] = useState(customer?.photo_url || null);
  const [busy, setBusy] = useState(false);
  const photoInput = useRef(null);
  const docInput = useRef(null);
  const isEdit = !!customer?.id;

  const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7].map(d => ({ d, label: t(`weekday.short${d}`) }));
  const districts = form.region ? REGIONS[form.region] || [] : [];
  const set = (patch) => setForm(f => ({ ...f, ...patch }));

  useEffect(() => {
    api.get('/users/', { _silent: true }).then(r => setAgents(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => {
    if (isEdit) api.get(`/customers/${customer.id}/documents`, { _silent: true }).then(r => setDocs(r.data)).catch(() => {});
  }, [isEdit, customer?.id]);

  // ── Joylashuv ──
  const onMapPick = ({ lat, lng, address }) => {
    setForm(f => ({ ...f, lat, lng, location_source: 'map', address: f.address || address || '' }));
  };
  const requestTgLocation = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/customers/${customer.id}/request-location`);
      toast.success(data.message);
    } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
    finally { setBusy(false); }
  };
  // Mijoz Telegramdan yuborgach, qayta yuklab olish
  const refreshLocation = async () => {
    try {
      const { data } = await api.post(`/customers/${customer.id}`);
      if (data.lat != null) {
        setForm(f => ({ ...f, lat: data.lat, lng: data.lng, location_source: data.location_source }));
        toast.success(t('customerProfile.locationUpdated'));
      } else toast(t('customerProfile.noLocationYet'));
    } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  // ── Rasm ──
  const onPhotoSelected = async (file) => {
    if (!file) return;
    if (!isEdit) { setPending(p => ({ ...p, photo: file })); return; }
    const fd = new FormData(); fd.append('file', file);
    setBusy(true);
    try {
      const { data } = await api.post(`/customers/${customer.id}/photo`, fd);
      setPhotoUrl(data.photo_url); onCustomerUpdated?.();
    } catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
    finally { setBusy(false); }
  };
  const removePhoto = async () => {
    if (!isEdit) { setPending(p => ({ ...p, photo: null })); return; }
    try { await api.delete(`/customers/${customer.id}/photo`); setPhotoUrl(null); onCustomerUpdated?.(); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };
  const pendingPhotoUrl = useMemo(() => (pending?.photo ? URL.createObjectURL(pending.photo) : null), [pending?.photo]);
  useEffect(() => () => { if (pendingPhotoUrl) URL.revokeObjectURL(pendingPhotoUrl); }, [pendingPhotoUrl]);
  const shownPhoto = pendingPhotoUrl || (photoUrl ? `${API_ORIGIN}${photoUrl}` : null);

  // ── Hujjatlar ──
  const onDocsSelected = async (files) => {
    const list = Array.from(files || []);
    if (!list.length) return;
    if (!isEdit) { setPending(p => ({ ...p, docs: [...(p.docs || []), ...list] })); return; }
    setBusy(true);
    for (const f of list) {
      const fd = new FormData(); fd.append('file', f);
      try {
        const { data } = await api.post(`/customers/${customer.id}/documents`, fd);
        setDocs(d => [data, ...d]);
      } catch (e) { toast.error(`${f.name}: ${e.response?.data?.detail || t('common.error')}`); }
    }
    setBusy(false);
  };
  const downloadDoc = async (doc) => {
    try {
      const r = await api.get(`/customers/${customer.id}/documents/${doc.id}/file`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a'); a.href = url; a.download = doc.original_name; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { toast.error(t('common.error')); }
  };
  const deleteDoc = async (doc) => {
    if (!window.confirm(t('customerProfile.confirmDeleteDoc'))) return;
    try { await api.delete(`/customers/${customer.id}/documents/${doc.id}`); setDocs(d => d.filter(x => x.id !== doc.id)); }
    catch (e) { toast.error(e.response?.data?.detail || t('common.error')); }
  };

  const sourceLabel = { map: t('customerProfile.srcMap'), telegram: t('customerProfile.srcTelegram'), manual: t('customerProfile.srcManual') };

  return (
    <div className="space-y-6">
      {/* Qo'shimcha telefonlar + chegirma */}
      <Section title={t('customerProfile.contacts')}
        right={form.extra_phones.length < 5 && (
          <button type="button" onClick={() => set({ extra_phones: [...form.extra_phones, ''] })}
            className="text-xs text-blue-600 font-bold flex items-center gap-1 bg-blue-50 px-2 py-1 rounded-lg">
            <Plus className="size-3" />{t('customerProfile.addPhone')}
          </button>
        )}>
        {form.extra_phones.map((p, i) => (
          <div key={i} className="flex gap-2">
            <input value={p} inputMode="tel" placeholder="+998 90 123 45 67"
              onChange={e => set({ extra_phones: form.extra_phones.map((x, j) => j === i ? e.target.value : x) })}
              className={inputCls} />
            <button type="button" onClick={() => set({ extra_phones: form.extra_phones.filter((_, j) => j !== i) })}
              className="p-2.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-xl"><Minus className="size-4" /></button>
          </div>
        ))}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>{t('customerProfile.discount')}</label>
            <input type="number" min="0" max="100" step="0.1" value={form.discount_percent}
              onChange={e => set({ discount_percent: e.target.value })} placeholder="0" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>{t('customerProfile.agent')}</label>
            <select value={form.agent_id} onChange={e => set({ agent_id: e.target.value })} className={inputCls}>
              <option value="">—</option>
              {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
        </div>
      </Section>

      {/* Manzil + xarita */}
      <Section title={t('customerProfile.address')}
        right={form.lat != null && (
          <a href={yandexMapsUrl(form.lat, form.lng)} target="_blank" rel="noreferrer"
            className="text-xs text-blue-600 font-medium flex items-center gap-1 hover:underline">
            <ExternalLink className="size-3" />{t('customerProfile.openInMaps')}
          </a>
        )}>
        <div className="grid grid-cols-2 gap-3">
          <select value={form.region} onChange={e => set({ region: e.target.value, district: '' })} className={inputCls}>
            <option value="">{t('customerProfile.selectRegion')}</option>
            {Object.keys(REGIONS).map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <select value={form.district} onChange={e => set({ district: e.target.value })} disabled={!form.region}
            className={`${inputCls} disabled:bg-slate-50 disabled:text-slate-300`}>
            <option value="">{t('customerProfile.selectDistrict')}</option>
            {districts.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2 px-3.5 border border-slate-200 rounded-xl bg-white focus-within:ring-2 focus-within:ring-blue-500">
          <MapPin className="size-4 text-slate-400 shrink-0" />
          <input value={form.address} onChange={e => set({ address: e.target.value })}
            placeholder={t('customerProfile.addressPlaceholder')} className="flex-1 py-2.5 text-sm outline-none bg-transparent" />
        </div>

        <MapPicker value={form.lat != null ? { lat: form.lat, lng: form.lng } : null} onChange={onMapPick} height={240} />

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-[11px] text-slate-400">
            {form.lat != null
              ? <>📍 {Number(form.lat).toFixed(5)}, {Number(form.lng).toFixed(5)} · {sourceLabel[form.location_source] || sourceLabel.map}</>
              : t('customerProfile.noLocation')}
          </span>
          <div className="flex items-center gap-2">
            {form.lat != null && (
              <button type="button" onClick={() => set({ lat: null, lng: null, location_source: null })}
                className="text-xs text-red-500 font-medium hover:underline">{t('customerProfile.clearLocation')}</button>
            )}
            {isEdit && customer.tg_connected && <>
              <button type="button" onClick={requestTgLocation} disabled={busy}
                className="text-xs font-semibold flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-sky-50 text-sky-600 hover:bg-sky-100">
                <Send className="size-3" />{t('customerProfile.requestTgLocation')}
              </button>
              <button type="button" onClick={refreshLocation} className="text-xs text-slate-500 hover:underline">{t('customerProfile.refresh')}</button>
            </>}
          </div>
        </div>
        {isEdit && !customer.tg_connected && (
          <p className="text-[11px] text-slate-400">{t('customerProfile.tgNotConnected')}</p>
        )}
      </Section>

      {/* Tashrif: ish kunlari + radius */}
      <Section title={t('customerProfile.visits')}>
        <div>
          <label className={labelCls}>{t('customerProfile.workDays')}</label>
          <div className="flex gap-1.5 flex-wrap">
            {WEEKDAYS.map(({ d, label }) => {
              const on = form.work_days.includes(d);
              return (
                <button key={d} type="button"
                  onClick={() => set({ work_days: on ? form.work_days.filter(x => x !== d) : [...form.work_days, d].sort() })}
                  className={`w-11 py-2 rounded-lg text-xs font-bold border transition-all ${on ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'}`}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="w-1/2 pr-1.5">
          <label className={labelCls}>{t('customerProfile.visitRadius')}</label>
          <input type="number" min="0" value={form.visit_radius_m} onChange={e => set({ visit_radius_m: e.target.value })}
            placeholder="100" className={inputCls} />
        </div>
      </Section>

      {/* Rasm + hujjatlar */}
      <Section title={t('customerProfile.files')}>
        <div className="flex gap-4 items-start">
          <div className="shrink-0">
            {shownPhoto ? (
              <div className="relative group">
                <img src={shownPhoto} alt="" className="w-28 h-28 object-cover rounded-xl border border-slate-200" />
                <button type="button" onClick={removePhoto}
                  className="absolute top-1 right-1 p-1 rounded-lg bg-white/90 text-red-500 opacity-0 group-hover:opacity-100 shadow"><Trash2 className="size-3.5" /></button>
              </div>
            ) : (
              <button type="button" onClick={() => photoInput.current?.click()} disabled={busy}
                className="w-28 h-28 rounded-xl border-2 border-dashed border-slate-200 text-slate-400 hover:border-blue-400 hover:text-blue-500 flex flex-col items-center justify-center gap-1 text-[11px] font-medium">
                <ImagePlus className="size-6" />{t('customerProfile.addPhoto')}
              </button>
            )}
            <input ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp" hidden
              onChange={e => { onPhotoSelected(e.target.files?.[0]); e.target.value = ''; }} />
            <p className="text-[10px] text-slate-400 mt-1 w-28">{t('customerProfile.photoHint')}</p>
          </div>

          <div className="flex-1 min-w-0 space-y-2">
            <button type="button" onClick={() => docInput.current?.click()} disabled={busy}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50">
              <Paperclip className="size-4" />{t('customerProfile.attachDoc')}
            </button>
            <input ref={docInput} type="file" multiple hidden
              accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xlsx"
              onChange={e => { onDocsSelected(e.target.files); e.target.value = ''; }} />
            <p className="text-[10px] text-slate-400">{t('customerProfile.docHint')}</p>
            {(isEdit ? docs : (pending?.docs || [])).map((d, i) => (
              <div key={d.id || i} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 text-sm">
                <FileText className="size-4 text-slate-400 shrink-0" />
                <span className="flex-1 truncate text-slate-700">{d.original_name || d.name}</span>
                <span className="text-[11px] text-slate-400 shrink-0">{fmtSize(d.size)}</span>
                {isEdit ? <>
                  <button type="button" onClick={() => downloadDoc(d)} className="p-1 text-slate-400 hover:text-blue-600"><Download className="size-4" /></button>
                  <button type="button" onClick={() => deleteDoc(d)} className="p-1 text-slate-400 hover:text-red-500"><Trash2 className="size-4" /></button>
                </> : (
                  <button type="button" onClick={() => setPending(p => ({ ...p, docs: p.docs.filter((_, j) => j !== i) }))}
                    className="p-1 text-slate-400 hover:text-red-500"><Trash2 className="size-4" /></button>
                )}
              </div>
            ))}
          </div>
        </div>
        {!isEdit && (pending?.photo || pending?.docs?.length > 0) && (
          <p className="text-[11px] text-amber-600">{t('customerProfile.filesAfterSave')}</p>
        )}
      </Section>
    </div>
  );
}
