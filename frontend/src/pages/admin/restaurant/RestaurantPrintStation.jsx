import { useState, useEffect, useCallback, useRef } from 'react';
import toast from 'react-hot-toast';
import { Printer, RotateCcw } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R4.1: chop etish stansiyasi. Oshxona printeri ulangan kompyuterda ochiladi: tanlangan sexlar tiketlarini
// navbatdan oladi (atomar egallash — ikkinchi qurilma qayta chiqarmaydi) va yashirin iframe orqali chop etadi.
// Chrome `--kiosk-printing` bilan ishga tushirilsa, dialogsiz sukutdagi printerga chiqadi.
// Sozlamalar (sexlar, qog'oz eni, avtomatik rejim) shu qurilmaning localStorage'ida.

const POLL_MS = 3000;
const LS_KEY = 'print_station_cfg';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const qtyFmt = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });

function loadCfg() {
  try { return { stations: [], width: 80, auto: false, ...(JSON.parse(localStorage.getItem(LS_KEY) || '{}')) }; }
  catch { return { stations: [], width: 80, auto: false }; }
}

function ticketHtml(tk, t) {
  const time = tk.created_at ? new Date(tk.created_at).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : '';
  const where = tk.table_name ? `${t('restPrint.table')} ${esc(tk.table_name)}` : esc(t(`restOrd.type.${tk.order_type || 'dine_in'}`));
  const lines = (tk.lines || []).map(l => `
    <div class="ln"><b>${esc(qtyFmt(l.quantity))} x ${esc(l.name)}</b>${l.course > 1 ? ` <span class="c">${esc(l.course)}-${esc(t('restPrint.course'))}</span>` : ''}</div>
    ${l.modifiers?.length ? `<div class="md">${l.modifiers.map(esc).join(', ')}</div>` : ''}
    ${l.comment ? `<div class="cm">${esc(l.comment)}</div>` : ''}`).join('');
  return `<section class="tk">
    <div class="st">${esc(tk.station_name || t('restPrint.noStation'))}</div>
    ${tk.kind === 'cancel' ? `<div class="cancel">${esc(t('restPrint.cancelled'))}</div>` : ''}
    <div class="hd"><b>#${esc(tk.daily_no)}</b> ${where}</div>
    <div class="sub">${esc(tk.waiter_name || '')} ${time}</div>
    <hr/>${lines}<hr/>
  </section>`;
}

function printTickets(frame, tickets, width, t) {
  if (!frame || !tickets.length) return;
  const doc = frame.contentWindow.document;
  doc.open();
  doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>
    @page { size: ${width}mm auto; margin: 0; }
    body { margin: 0; font-family: Arial, sans-serif; width: ${width - 4}mm; padding: 2mm; color: #000; }
    .tk { page-break-after: always; }
    .st { font-size: 13px; text-transform: uppercase; }
    .cancel { font-size: 22px; font-weight: 700; border: 2px solid #000; text-align: center; margin: 2px 0; }
    .hd { font-size: 20px; } .sub { font-size: 12px; }
    .ln { font-size: ${width >= 80 ? 18 : 15}px; margin-top: 3px; } .c { font-size: 12px; }
    .md { font-size: 15px; font-weight: 700; padding-left: 8px; }
    .cm { font-size: 14px; font-style: italic; padding-left: 8px; }
    hr { border: 0; border-top: 1px dashed #000; }
  </style></head><body>${tickets.map(tk => ticketHtml(tk, t)).join('')}</body></html>`);
  doc.close();
  frame.contentWindow.focus();
  frame.contentWindow.print();
}

export default function RestaurantPrintStation() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [branchId, setBranchId] = useState(null);
  const [stations, setStations] = useState([]);
  const [cfg, setCfg] = useState(loadCfg);
  const [log, setLog] = useState([]);
  const [lastError, setLastError] = useState('');
  const frame = useRef(null);
  const busy = useRef(false);

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);
  useEffect(() => { api.get('/restaurant/stations').then(r => setStations(r.data.filter(s => s.is_active))).catch(() => {}); }, []);

  const save = next => {
    setCfg(next);
    try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch { /* ixtiyoriy */ }
  };
  const toggleStation = key => save({ ...cfg, stations: cfg.stations.includes(key) ? cfg.stations.filter(x => x !== key) : [...cfg.stations, key] });

  const loadRecent = useCallback(() => {
    if (!branchId) return;
    api.get('/restaurant/print/recent', { params: { branch_id: branchId, limit: 30 }, _silent: true })
      .then(r => setLog(r.data)).catch(() => {});
  }, [branchId]);
  useEffect(() => { loadRecent(); }, [loadRecent]);

  const cycle = useCallback(async () => {
    if (!branchId || !cfg.auto || !cfg.stations.length || busy.current) return;
    busy.current = true;
    try {
      const ids = cfg.stations.filter(s => s !== 'none');
      const queries = [];
      if (ids.length) queries.push(api.get('/restaurant/print/queue', { params: { branch_id: branchId, station: ids.join(',') }, _silent: true }));
      if (cfg.stations.includes('none')) queries.push(api.get('/restaurant/print/queue', { params: { branch_id: branchId, station: 'none' }, _silent: true }));
      const found = (await Promise.all(queries)).flatMap(r => r.data);
      if (found.length) {
        const claimed = (await api.post('/restaurant/print/claim', { ticket_ids: found.map(x => x.id) }, { _silent: true })).data;
        if (claimed.length) {
          printTickets(frame.current, claimed, cfg.width, t);
          setLog(prev => [...claimed, ...prev].slice(0, 30));
        }
      }
      setLastError('');
    } catch (err) {
      setLastError(err.response?.data?.detail || err.message || 'error');
    } finally {
      busy.current = false;
    }
  }, [branchId, cfg, t]);

  useEffect(() => {
    const p = setInterval(cycle, POLL_MS);
    return () => clearInterval(p);
  }, [cycle]);

  const reprint = async tk => {
    try {
      await api.post(`/restaurant/print/${tk.id}/reprint`);
      toast.success(t('restPrint.queued'));
      if (!cfg.auto) printTickets(frame.current, [tk], cfg.width, t);
    } catch (err) { toast.error(err.response?.data?.detail || t('restPrint.failed')); }
  };

  const testPrint = () => printTickets(frame.current, [{
    id: 0, kind: 'order', station_name: t('restPrint.test'), daily_no: 0, table_name: '1', waiter_name: 'E-Code',
    created_at: new Date().toISOString(), lines: [{ name: t('restPrint.testLine'), quantity: 1, course: 1 }],
  }], cfg.width, t);

  const options = [...stations.map(s => ({ key: String(s.id), name: s.name })), { key: 'none', name: t('restPrint.noStation') }];

  return (
    <div className="space-y-4 max-w-4xl">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{t('restPrint.title')}</h1>
        <p className="text-sm text-slate-500">{t('restPrint.desc')}</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="text-sm font-bold text-slate-800">{t('restPrint.stations')}</div>
        <div className="flex flex-wrap gap-2">
          {options.map(o => (
            <label key={o.key} className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer ${cfg.stations.includes(o.key) ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-slate-200 text-slate-600'}`}>
              <input type="checkbox" checked={cfg.stations.includes(o.key)} onChange={() => toggleStation(o.key)} />{o.name}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-600 flex items-center gap-2">{t('restPrint.paper')}
            <select className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm" value={cfg.width} onChange={e => save({ ...cfg, width: Number(e.target.value) })}>
              <option value={80}>80 mm</option><option value={58}>58 mm</option>
            </select>
          </label>
          {branches.length > 1 && (
            <select className="px-2 py-1.5 border border-slate-200 rounded-lg text-sm" value={branchId ?? ''} onChange={e => setBranchId(Number(e.target.value))}>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          )}
          <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-700" onClick={testPrint}>
            <Printer className="w-4 h-4" />{t('restPrint.testPrint')}
          </button>
          <button onClick={() => save({ ...cfg, auto: !cfg.auto })} disabled={!cfg.stations.length}
                  className={`ml-auto px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-40 ${cfg.auto ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-white'}`}>
            {cfg.auto ? t('restPrint.running') : t('restPrint.start')}
          </button>
        </div>
        {cfg.auto && <p className="text-xs text-emerald-700">{t('restPrint.runningHint')}</p>}
        {lastError && <p className="text-xs text-rose-700">{t('restPrint.error')}: {lastError}</p>}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 text-sm text-slate-600 space-y-1">
        <div className="font-bold text-slate-800">{t('restPrint.silentTitle')}</div>
        <p>{t('restPrint.silentHint')}</p>
        <code className="block text-xs bg-slate-50 border border-slate-200 rounded p-2 break-all">
          chrome.exe --kiosk-printing --app={window.location.origin}/admin/restaurant/print
        </code>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-2.5 border-b border-slate-100 text-sm font-bold text-slate-800">{t('restPrint.recent')}</div>
        <div className="divide-y divide-slate-100">
          {log.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">{t('restPrint.none')}</div>}
          {log.map(tk => (
            <div key={`${tk.id}-${tk.print_attempts}`} className="px-4 py-2 flex items-center gap-3 text-sm">
              <span className="font-semibold">#{tk.daily_no}</span>
              <span className="text-slate-500">{tk.station_name || t('restPrint.noStation')}</span>
              {tk.kind === 'cancel' && <span className="text-rose-700 text-xs font-semibold">{t('restPrint.cancelled')}</span>}
              <span className="flex-1 truncate text-slate-600">{(tk.lines || []).map(l => `${qtyFmt(l.quantity)} x ${l.name}`).join(', ')}</span>
              <button className="p-1.5 text-slate-400 hover:text-blue-600" title={t('restPrint.reprint')} onClick={() => reprint(tk)}>
                <RotateCcw className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
      <iframe ref={frame} title="print" className="fixed -left-[9999px] w-0 h-0 border-0" />
    </div>
  );
}
