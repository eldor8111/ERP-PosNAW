import { useState, useEffect, useCallback } from 'react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';
import { loadXLSX, loadSaveAs } from '../../../utils/excelLazy';
import { toast } from '../../../utils/toast';

// D4.4: dorixona jurnallari — nazoratdagi dorilar harakati (oy boshi/oxiri qoldiq, retsept raqami bilan)
// va retseptli sotuvlar jurnali. Faqat o'qiydi: GET /pharmacy/journals/controlled (json | pdf),
// GET /pharmacy/journals/prescriptions. Jurnal manba yozuvlardan hisoblanadi — tahrirlanmaydi.
// Faqat dorixona moduli yoqilgan korxonada ko'rinadi. D4.6 sahifaga ulaydi.
// Props: branchId (ixtiyoriy) — faqat shu filial.
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });
const z2 = (n) => String(n).padStart(2, '0');
const isoDate = (d) => `${d.getFullYear()}-${z2(d.getMonth() + 1)}-${z2(d.getDate())}`;
const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${z2(d.getMonth() + 1)}`; };
const MODES = ['all', 'with', 'without'];
const KINDS = ['receipt', 'sale', 'return_customer', 'return_supplier', 'write_off', 'transfer_in', 'transfer_out', 'adjustment', 'reversal', 'other'];

export default function JournalsPanel({ branchId = '' }) {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();
  const enabled = !!features?.pharmacy;

  const [tab, setTab] = useState('controlled');
  const [month, setMonth] = useState(thisMonth);
  const [ctl, setCtl] = useState(null);
  const [dateTo, setDateTo] = useState(() => isoDate(new Date()));
  const [dateFrom, setDateFrom] = useState(() => { const d = new Date(); d.setDate(d.getDate() - 29); return isoDate(d); });
  const [doctor, setDoctor] = useState('');
  const [clinic, setClinic] = useState('');
  const [mode, setMode] = useState('all');
  const [rx, setRx] = useState(null);
  const [loading, setLoading] = useState(false);

  const kindLabel = {
    receipt: tf('pharmJournals.kind.receipt', 'Kirim'),
    sale: tf('pharmJournals.kind.sale', 'Sotuv'),
    return_customer: tf('pharmJournals.kind.returnCustomer', 'Mijozdan qaytarish'),
    return_supplier: tf('pharmJournals.kind.returnSupplier', 'Yetkazuvchiga qaytarish'),
    write_off: tf('pharmJournals.kind.writeOff', 'Hisobdan chiqarish'),
    transfer_in: tf('pharmJournals.kind.transferIn', 'Transfer (kirim)'),
    transfer_out: tf('pharmJournals.kind.transferOut', 'Transfer (chiqim)'),
    adjustment: tf('pharmJournals.kind.adjustment', 'Tuzatish'),
    reversal: tf('pharmJournals.kind.reversal', 'Teskari hujjat'),
    other: tf('pharmJournals.kind.other', 'Boshqa'),
  };
  const modeLabel = {
    all: tf('pharmJournals.mode.all', 'Hammasi'),
    with: tf('pharmJournals.mode.with', 'Retseptli'),
    without: tf('pharmJournals.mode.without', 'Retseptsiz (sabab bilan)'),
  };

  const loadControlled = useCallback(async () => {
    setLoading(true);
    try {
      const p = { month };
      if (branchId) p.branch_id = branchId;
      const r = await api.get('/pharmacy/journals/controlled', { params: p, _suppressToast: true });
      setCtl(r.data);
    } catch (e) {
      setCtl(null);
      toast.error(e.response?.data?.detail || tf('pharmJournals.loadFailed', "Jurnalni yuklab bo'lmadi"));
    } finally { setLoading(false); }
  }, [month, branchId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadRx = useCallback(async () => {
    setLoading(true);
    try {
      const p = { from: dateFrom, to: dateTo, mode };
      if (doctor.trim()) p.doctor = doctor.trim();
      if (clinic.trim()) p.clinic = clinic.trim();
      if (branchId) p.branch_id = branchId;
      const r = await api.get('/pharmacy/journals/prescriptions', { params: p, _suppressToast: true });
      setRx(r.data);
    } catch (e) {
      setRx(null);
      toast.error(e.response?.data?.detail || tf('pharmJournals.loadFailed', "Jurnalni yuklab bo'lmadi"));
    } finally { setLoading(false); }
  }, [dateFrom, dateTo, mode, doctor, clinic, branchId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (enabled && tab === 'controlled') loadControlled(); }, [enabled, tab, loadControlled]);
  useEffect(() => { if (enabled && tab === 'prescriptions') loadRx(); }, [enabled, tab, loadRx]);

  if (!enabled) return null;

  const exportControlled = async () => {
    if (!ctl?.rows?.length) return;
    try {
      const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
      const ws = XLSX.utils.json_to_sheet(ctl.rows.map(r => ({
        [tf('pharmJournals.date', 'Sana')]: r.date,
        [tf('pharmJournals.drug', 'Dori')]: r.product_name,
        [tf('pharmJournals.class', 'Nazorat sinfi')]: r.control_class,
        [tf('pharmJournals.movement', 'Harakat')]: kindLabel[r.kind] || r.kind_label,
        [tf('pharmJournals.document', 'Hujjat')]: r.document_number || (r.document_type ? `${r.document_type}#${r.document_id}` : ''),
        [tf('pharmJournals.rxNumber', 'Retsept raqami')]: r.rx_number || '',
        [tf('pharmJournals.warehouse', 'Ombor')]: r.warehouse_name || '',
        [tf('pharmJournals.in', 'Kirim')]: r.in_qty,
        [tf('pharmJournals.out', 'Chiqim')]: r.out_qty,
        [tf('pharmJournals.balance', 'Qoldiq')]: r.balance_after,
      })));
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, tf('pharmJournals.controlledTitle', 'Nazoratdagi dorilar').slice(0, 31));
      saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `nazoratdagi_jurnal_${ctl.month}.xlsx`);
    } catch { toast.error(tf('pharmJournals.downloadFailed', "Faylni yuklab bo'lmadi")); }
  };

  const downloadPdf = async () => {
    try {
      const p = { month, format: 'pdf' };
      if (branchId) p.branch_id = branchId;
      const [r, saveAs] = await Promise.all([
        api.get('/pharmacy/journals/controlled', { params: p, responseType: 'blob', _suppressToast: true }),
        loadSaveAs(),
      ]);
      saveAs(new Blob([r.data], { type: 'application/pdf' }), `nazoratdagi_jurnal_${month}.pdf`);
    } catch { toast.error(tf('pharmJournals.downloadFailed', "Faylni yuklab bo'lmadi")); }
  };

  const exportRx = async () => {
    if (!rx?.rows?.length) return;
    try {
      const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
      const ws = XLSX.utils.json_to_sheet(rx.rows.map(r => ({
        [tf('pharmJournals.saleDate', 'Sotuv sanasi')]: r.sale_date,
        [tf('pharmJournals.sale', 'Sotuv')]: r.sale_number,
        [tf('pharmJournals.drug', 'Dori')]: r.product_name || '',
        [tf('pharmJournals.qty', 'Miqdor')]: r.quantity ?? '',
        [tf('pharmJournals.rxNumber', 'Retsept raqami')]: r.number || '',
        [tf('pharmJournals.rxDate', 'Retsept sanasi')]: r.issued_at || '',
        [tf('pharmJournals.doctor', 'Shifokor')]: r.doctor || '',
        [tf('pharmJournals.clinic', 'Shifoxona')]: r.clinic || '',
        [tf('pharmJournals.patient', 'Bemor')]: r.patient || '',
        [tf('pharmJournals.blank', 'Blank turi')]: r.blank_type || '',
        [tf('pharmJournals.reason', 'Retseptsiz sotish sababi')]: r.reason_without_rx || '',
      })));
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, tf('pharmJournals.rxTitle', 'Retsept jurnali').slice(0, 31));
      saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `retsept_jurnali_${dateFrom}_${dateTo}.xlsx`);
    } catch { toast.error(tf('pharmJournals.downloadFailed', "Faylni yuklab bo'lmadi")); }
  };

  const inputCls = 'border border-slate-200 rounded-lg px-2 py-1.5';
  const btnCls = 'px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold disabled:opacity-50';
  const tabCls = (k) => `px-3 py-1.5 rounded-lg text-xs font-semibold ${tab === k ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('pharmJournals.title', 'Dorixona jurnallari')}</h3>
      <p className="text-xs text-slate-500 mt-1">
        {tf('pharmJournals.desc', "Jurnal tizim yozuvlaridan avtomatik hosil qilinadi va tahrirlanmaydi. Xatoni tuzatish faqat teskari hujjat (qaytarish, tuzatish) orqali bajariladi.")}
      </p>

      <div className="flex gap-2 mt-4">
        <button type="button" className={tabCls('controlled')} onClick={() => setTab('controlled')}>
          {tf('pharmJournals.controlledTitle', 'Nazoratdagi dorilar')}
        </button>
        <button type="button" className={tabCls('prescriptions')} onClick={() => setTab('prescriptions')}>
          {tf('pharmJournals.rxTitle', 'Retsept jurnali')}
        </button>
      </div>

      {tab === 'controlled' && (
        <div className="mt-4">
          <div className="flex flex-wrap items-end gap-3 text-xs">
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">{tf('pharmJournals.month', 'Oy')}</span>
              <input type="month" value={month} onChange={e => e.target.value && setMonth(e.target.value)} className={inputCls} />
            </label>
            <button type="button" onClick={loadControlled} disabled={loading} className={btnCls}>
              {loading ? tf('pharmJournals.loading', 'Yuklanmoqda...') : tf('pharmJournals.refresh', 'Yangilash')}
            </button>
            <button type="button" onClick={exportControlled} disabled={!ctl?.rows?.length} className={btnCls}>
              {tf('pharmJournals.excel', 'Excel')}
            </button>
            <button type="button" onClick={downloadPdf} disabled={!ctl} className="px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 font-semibold disabled:opacity-50">
              {tf('pharmJournals.pdf', 'PDF')}
            </button>
          </div>

          {ctl && ctl.products.length === 0 && !loading && (
            <div className="mt-6 text-center text-sm text-slate-400">{tf('pharmJournals.emptyControlled', "Tanlangan oyda nazoratdagi dori harakati yo'q")}</div>
          )}

          {ctl && ctl.products.length > 0 && (
            <div className="mt-4 overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 bg-slate-50 border-b border-slate-100">
                    <th className="py-2 px-3">{tf('pharmJournals.drug', 'Dori')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.class', 'Nazorat sinfi')}</th>
                    <th className="py-2 px-2 text-right">{tf('pharmJournals.opening', 'Oy boshi qoldiq')}</th>
                    <th className="py-2 px-2 text-right">{tf('pharmJournals.in', 'Kirim')}</th>
                    <th className="py-2 px-2 text-right">{tf('pharmJournals.out', 'Chiqim')}</th>
                    <th className="py-2 px-3 text-right">{tf('pharmJournals.closing', 'Oy oxiri qoldiq')}</th>
                  </tr>
                </thead>
                <tbody>
                  {ctl.products.map(p => (
                    <tr key={p.product_id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2 px-3 text-slate-700">{p.name}</td>
                      <td className="py-2 px-2">{p.control_class}</td>
                      <td className="py-2 px-2 text-right">{fmt(p.opening)}</td>
                      <td className="py-2 px-2 text-right text-emerald-600">{fmt(p.receipts)}</td>
                      <td className="py-2 px-2 text-right text-red-600">{fmt(p.issues)}</td>
                      <td className="py-2 px-3 text-right font-semibold">{fmt(p.closing)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {ctl && ctl.rows.length > 0 && (
            <div className="mt-4 overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 bg-slate-50 border-b border-slate-100">
                    <th className="py-2 px-3">{tf('pharmJournals.date', 'Sana')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.drug', 'Dori')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.movement', 'Harakat')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.document', 'Hujjat')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.rxNumber', 'Retsept raqami')}</th>
                    <th className="py-2 px-2 text-right">{tf('pharmJournals.in', 'Kirim')}</th>
                    <th className="py-2 px-2 text-right">{tf('pharmJournals.out', 'Chiqim')}</th>
                    <th className="py-2 px-3 text-right">{tf('pharmJournals.balance', 'Qoldiq')}</th>
                  </tr>
                </thead>
                <tbody>
                  {ctl.rows.map(r => (
                    <tr key={r.id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2 px-3 whitespace-nowrap">{(r.date || '').slice(0, 16).replace('T', ' ')}</td>
                      <td className="py-2 px-2 text-slate-700">{r.product_name}</td>
                      <td className="py-2 px-2">{KINDS.includes(r.kind) ? kindLabel[r.kind] : r.kind_label}</td>
                      <td className="py-2 px-2">{r.document_number || (r.document_type ? `${r.document_type}#${r.document_id}` : '—')}</td>
                      <td className="py-2 px-2">
                        {r.rx_number || (r.rx_missing
                          ? <span className="text-red-600 font-semibold">{tf('pharmJournals.noRx', 'Retseptsiz')}</span>
                          : '—')}
                      </td>
                      <td className="py-2 px-2 text-right">{r.in_qty ? fmt(r.in_qty) : ''}</td>
                      <td className="py-2 px-2 text-right">{r.out_qty ? fmt(r.out_qty) : ''}</td>
                      <td className="py-2 px-3 text-right font-semibold">{fmt(r.balance_after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {ctl?.truncated && (
            <p className="text-[11px] text-amber-600 mt-2">{tf('pharmJournals.truncated', "Qatorlar soni cheklangan — davrni qisqartiring yoki filial tanlang.")}</p>
          )}
        </div>
      )}

      {tab === 'prescriptions' && (
        <div className="mt-4">
          <div className="flex flex-wrap items-end gap-3 text-xs">
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">{tf('pharmJournals.from', 'Dan')}</span>
              <input type="date" value={dateFrom} max={dateTo} onChange={e => setDateFrom(e.target.value)} className={inputCls} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">{tf('pharmJournals.to', 'Gacha')}</span>
              <input type="date" value={dateTo} min={dateFrom} onChange={e => setDateTo(e.target.value)} className={inputCls} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">{tf('pharmJournals.doctor', 'Shifokor')}</span>
              <input value={doctor} onChange={e => setDoctor(e.target.value)} className={inputCls} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">{tf('pharmJournals.clinic', 'Shifoxona')}</span>
              <input value={clinic} onChange={e => setClinic(e.target.value)} className={inputCls} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">{tf('pharmJournals.filter', 'Filtr')}</span>
              <select value={mode} onChange={e => setMode(e.target.value)} className={`${inputCls} min-w-[180px]`}>
                {MODES.map(m => <option key={m} value={m}>{modeLabel[m]}</option>)}
              </select>
            </label>
            <button type="button" onClick={loadRx} disabled={loading} className={btnCls}>
              {loading ? tf('pharmJournals.loading', 'Yuklanmoqda...') : tf('pharmJournals.refresh', 'Yangilash')}
            </button>
            <button type="button" onClick={exportRx} disabled={!rx?.rows?.length} className={btnCls}>
              {tf('pharmJournals.excel', 'Excel')}
            </button>
          </div>

          {rx && (
            <p className="text-xs text-slate-500 mt-3">
              {tf('pharmJournals.summary', 'Jami')}: {fmt(rx.summary.total)} · {tf('pharmJournals.withRx', 'Retseptli')}: {fmt(rx.summary.with_rx)} · {tf('pharmJournals.withoutRx', 'Retseptsiz')}: {fmt(rx.summary.without_rx)}
            </p>
          )}

          {rx && rx.rows.length === 0 && !loading && (
            <div className="mt-6 text-center text-sm text-slate-400">{tf('pharmJournals.emptyRx', "Tanlangan davrda yozuv yo'q")}</div>
          )}

          {rx && rx.rows.length > 0 && (
            <div className="mt-3 overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 bg-slate-50 border-b border-slate-100">
                    <th className="py-2 px-3">{tf('pharmJournals.saleDate', 'Sotuv sanasi')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.sale', 'Sotuv')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.drug', 'Dori')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.rxNumber', 'Retsept raqami')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.doctor', 'Shifokor')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.clinic', 'Shifoxona')}</th>
                    <th className="py-2 px-2">{tf('pharmJournals.patient', 'Bemor')}</th>
                    <th className="py-2 px-3">{tf('pharmJournals.reason', 'Retseptsiz sotish sababi')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rx.rows.map(r => (
                    <tr key={r.id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2 px-3 whitespace-nowrap">{(r.sale_date || '').slice(0, 16).replace('T', ' ')}</td>
                      <td className="py-2 px-2">{r.sale_number}</td>
                      <td className="py-2 px-2 text-slate-700">{r.product_name || '—'}</td>
                      <td className="py-2 px-2">{r.number || '—'}</td>
                      <td className="py-2 px-2">{r.doctor || '—'}</td>
                      <td className="py-2 px-2">{r.clinic || '—'}</td>
                      <td className="py-2 px-2">{r.patient || '—'}</td>
                      <td className={`py-2 px-3 ${r.has_rx ? '' : 'text-red-600'}`}>{r.reason_without_rx || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {rx?.truncated && (
            <p className="text-[11px] text-amber-600 mt-2">{tf('pharmJournals.truncated', "Qatorlar soni cheklangan — davrni qisqartiring yoki filial tanlang.")}</p>
          )}
        </div>
      )}
    </div>
  );
}
