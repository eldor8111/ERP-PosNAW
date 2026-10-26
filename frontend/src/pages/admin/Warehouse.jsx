import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { useBranch } from '../../context/BranchContext';
import toast from 'react-hot-toast';
import { loadXLSX, loadSaveAs } from '../../utils/excelLazy';
import { exportFileName, sheetHeaderRows } from '../../utils/exportMeta';
import BranchSelect from '../../components/BranchSelect';
import { fmtQty } from '../../utils/qty';
import { WAREHOUSE_TYPE_BY_VALUE } from '../../constants/warehouseTypes';
import { useBranches } from '../../hooks/useBranches';

// /reports/inventory: bir so'rovdagi qatorlar chegarasi (backend standarti ham shu)
const INV_LIMIT = 5000;

const fmtDate = (s) => s ? new Date(s).toLocaleString('ru-RU', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' }).replace(',','') : '—';
const today = () => (new Date(Date.now() - new Date().getTimezoneOffset() * 60000)).toISOString().slice(0, 10);
const fmtS = (v) => Number(v || 0).toLocaleString('uz-UZ') + " so'm";

// XSS himoyasi: chop etish oynasiga qo'yiladigan barcha matn escape qilinadi
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

function printTable(title, headers, rows, totalsRow = null, printLabel = 'Chop etish', metaLines = []) {
  const headerHtml = headers.map(h => `<th style="border:1px solid #ddd;padding:8px;background:#f3f4f6;font-size:12px">${esc(h)}</th>`).join('');
  const rowsHtml = rows.map((row, i) =>
    `<tr style="background:${i % 2 ? '#f9fafb' : '#fff'}">${row.map(cell =>
      `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${esc(cell ?? '—')}</td>`
    ).join('')}</tr>`
  ).join('');
  const totalsHtml = totalsRow
    ? `<tr style="background:#e0f2fe;font-weight:bold">${totalsRow.map(cell =>
        `<td style="border:1px solid #ddd;padding:7px 8px;font-size:12px">${esc(cell ?? '')}</td>`
      ).join('')}</tr>`
    : '';

  const win = window.open('', '_blank');
  win.document.write(`<!DOCTYPE html><html><head><title>${esc(title)}</title>
    <style>body{font-family:Arial,sans-serif;margin:20px}h2{color:#1e293b}table{border-collapse:collapse;width:100%}@media print{button{display:none}}</style>
    </head><body>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2>${esc(title)}</h2>
      <div style="font-size:12px;color:#64748b">${new Date().toLocaleString('uz-UZ')}</div>
    </div>
    ${metaLines.length ? `<div style="font-size:12px;color:#475569;margin:-8px 0 12px">${metaLines.map(esc).join(' &middot; ')}</div>` : ''}
    <table><thead><tr>${headerHtml}</tr></thead>
    <tbody>${rowsHtml}${totalsHtml}</tbody></table>
    <div style="margin-top:16px;text-align:center">
      <button onclick="window.print()" style="padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">${esc(printLabel)}</button>
    </div></body></html>`);
  win.document.close();
}

function ExportBtns({ onExcel, onPdf }) {
  return (
    <div className="flex gap-2">
      {onExcel && (
        <button onClick={onExcel}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Excel
        </button>
      )}
      {onPdf && (
        <button onClick={onPdf}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm font-semibold rounded-xl transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          PDF
        </button>
      )}
    </div>
  );
}

const Spinner = () => (
  <div className="flex justify-center py-16">
    <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

// Yuklash xatosi holati (T3.5): "ma'lumot yo'q" o'rniga xato matni va "Qayta urinish" tugmasi
const LoadError = ({ t, onRetry }) => (
  <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
    <p className="text-sm text-red-500">{t('common.loadError')}</p>
    <button type="button" onClick={onRetry}
      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl transition-colors">
      {t('common.retry')}
    </button>
  </div>
);

function TabBtn({ label, icon, active, onClick }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap ${
        active ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'
      }`}>
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={icon} />
      </svg>
      {label}
    </button>
  );
}

export default function Warehouse() {
  const { t } = useLang();
  const { currentBranchId, assignedBranchId, canSelectAll } = useBranch();
  const [tab, setTab] = useState('inventory');
  // T2.5: eksport sarlavhasi yorliqlari (i18n kaliti hali lug'atda bo'lmasa — o'zbekcha zaxira)
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  const branchLabel = tf('reports.exportBranch', 'Filial');
  const periodLabel = tf('reports.exportPeriod', 'Davr');
  
  const [warehouses, setWarehouses] = useState([]);
  const { branches } = useBranches();   // T3.8: yagona filial hooki (keshlangan)
  const [loading, setLoading]       = useState(true);
  const [loadError, setLoadError]   = useState(false);
  
  // Create/Edit state for warehouses
  const [modal, setModal]           = useState(null);
  const [name, setName]             = useState('');
  const [branchId, setBranchId]     = useState('');
  const [isDefault, setIsDefault]   = useState(false);
  const [saving, setSaving]         = useState(false);
  const [err, setErr]               = useState('');
  const [delConfirm, setDelConfirm] = useState(null);
  const [whUsage, setWhUsage] = useState(null);   // T3.9: omborlar ishlatilgan / limit

  // Inventory state
  const [inventoryData, setInventoryData] = useState([]);
  // T2.3: qoldiq hisoboti filial/ombor kesimida + jami qiymat kartasi
  const [invBranch, setInvBranch]       = useState('');
  const [invWarehouse, setInvWarehouse] = useState('');
  const [invWarehouses, setInvWarehouses] = useState([]);
  const [invSummary, setInvSummary]     = useState(null);
  const [invTotal, setInvTotal]         = useState(0);

  const load = async () => {
    setLoading(true);
    setLoadError(false);
    try {
      if (tab === 'warehouses') {
        // T1.3: boshqaruv sahifasi — barcha filiallar omborlari (ruxsat bo'lmasa joriy kontekst)
        const { data } = await api.get('/warehouses', { params: { scope: 'all' }, _silent: true, _suppressToast: true }).catch(() => api.get('/warehouses', { _silent: true, _suppressToast: true }));
        setWarehouses(data); 
      } else if (tab === 'inventory') {
        const sp = {};
        if (invBranch) sp.branch_id = invBranch;
        if (invWarehouse) sp.warehouse_id = invWarehouse;
        // _noCache: X-Total-Count sarlavhasi keshdan kelganda yo'qolmasin
        const [r, s] = await Promise.all([
          api.get('/reports/inventory', { params: { ...sp, limit: INV_LIMIT }, _noCache: true, _silent: true, _suppressToast: true }),
          api.get('/reports/inventory/summary', { params: sp, _noCache: true }).catch(() => null),
        ]);
        setInventoryData(r.data);
        setInvTotal(Number(r.headers?.['x-total-count'] ?? r.data.length));
        setInvSummary(s?.data ?? null);
      }
    }
    catch (e) {
      // Jim yutmaymiz: toast + xato holati (interceptor 422/5xx uchun o'zi toast chiqaradi)
      setLoadError(true);
      const st = e?.response?.status;
      if (!(st === 422 || st >= 500)) toast.error(e?.response?.data?.detail || t('common.loadError'));
    }
    finally { setLoading(false); }
  };

  useEffect(() => {
    load();
  }, [tab, invBranch, invWarehouse]); // eslint-disable-line react-hooks/exhaustive-deps

  // Ombor selektori tanlangan filial omborlari bilan to'ldiriladi
  useEffect(() => {
    if (tab !== 'inventory') return;
    const params = invBranch ? { branch_id: invBranch } : {};
    api.get('/warehouses', { params: { scope: 'all', ...params }, _silent: true })
      .catch(() => api.get('/warehouses', { params, _silent: true }))
      .then(r => setInvWarehouses(r.data || []))
      .catch(() => setInvWarehouses([]));
  }, [tab, invBranch]);

  // T3.9: tarif ombor limiti nishoni (korxonasiz super_admin uchun 404 — nishon ko'rinmaydi)
  const loadWhUsage = () => {
    api.get('/billing/my-company/usage', { _silent: true, _suppressToast: true })
      .then(r => setWhUsage(r.data)).catch(() => setWhUsage(null));
  };
  useEffect(() => { if (tab === 'warehouses') loadWhUsage(); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const onInvBranch = (v) => { setInvBranch(v); setInvWarehouse(''); };
  // Eksport sarlavhasi uchun tanlangan filial/ombor nomi
  const scopeLabel = [
    invBranch ? (branches.find(b => String(b.id) === String(invBranch))?.name || '') : t('common.allBranches'),
    invWarehouse ? (invWarehouses.find(w => String(w.id) === String(invWarehouse))?.name || '') : '',
  ].filter(Boolean).join(' / ');

  // T1.4: yangi ombor formasida filial standart qiymati — joriy / biriktirilgan filial (yoki yagona filial)
  const openCreate = () => {
    setName('');
    // T3.3: defaultBranchId = joriy / biriktirilgan filial, bo'lmasa yagona filial
    setBranchId(currentBranchId ?? assignedBranchId ?? (branches.length === 1 ? branches[0].id : ''));
    setIsDefault(false); setErr(''); setModal({ mode:'create' });
  };
  const openEdit   = (wh) => { setName(wh.name); setBranchId(wh.branch_id ?? ''); setIsDefault(!!wh.is_default); setErr(''); setModal({ mode:'edit', wh }); };
  const closeModal = () => { setModal(null); setErr(''); };

  const remove = async () => {
    try {
      await api.delete(`/warehouses/${delConfirm.id}`);
      setDelConfirm(null);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('auth.errGeneral'));
    }
  };

  const save = async () => {
    if (!name.trim()) { setErr(t('warehouse.nameRequired')); return; }
    // T3.3: filiallar bor bo'lsa filial majburiy ("Filialsiz" faqat filial cheklovi yo'q admin/director uchun)
    if (branches.length > 0 && !canSelectAll && !branchId) { setErr(tf('warehouse.branchRequiredError', 'Filialni tanlang')); return; }
    setSaving(true); setErr('');
    try {
      const payload = { name: name.trim(), branch_id: branchId ? Number(branchId) : null };
      // Asosiy savdo ombori: faqat filialli ombor uchun; hozirgi asosiy ombordan belgini olib bo'lmaydi
      if (payload.branch_id && (isDefault || !(modal.mode === 'edit' && modal.wh.is_default))) payload.is_default = isDefault;
      if (modal.mode === 'create') {
        const created = await api.post('/warehouses', payload);
        // T3.3: filialga biriktirilgan foydalanuvchi o'z filialiga tegishli bo'lmagan omborni ko'rmaydi — ogohlantiramiz
        if (assignedBranchId && (created?.data?.branch_id ?? null) !== assignedBranchId) {
          toast(tf('warehouse.notVisibleWarning', "Ombor yaratildi, lekin u sizning filialingiz ro'yxatida ko'rinmaydi"), { duration: 7000 });
        }
      } else {
        const res = await api.patch(`/warehouses/${modal.wh.id}`, payload);
        // T1.4: javobdagi filial yuborilgan qiymatga mos kelmasa, jimgina muvaffaqiyat ko'rsatilmaydi
        if ((res?.data?.branch_id ?? null) !== payload.branch_id) {
          setErr(t('branch.warehouseBranchNotSaved'));
          return;
        }
      }
      closeModal();
      load();
      loadWhUsage();
    } catch (e) {
      setErr(e.response?.data?.detail || t('auth.errGeneral'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-slate-700">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
          </svg>
          <span className="text-base font-semibold">{t('warehouse.title')}</span>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-3">
        <div className="flex flex-wrap gap-1">
          <TabBtn
            label={t('warehouse.inventoryTab')}
            icon="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
            active={tab === 'inventory'}
            onClick={() => setTab('inventory')}
          />
          <TabBtn
            label={t('warehouse.warehousesList')}
            icon="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            active={tab === 'warehouses'}
            onClick={() => setTab('warehouses')}
          />
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        {tab === 'inventory' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="text-sm font-semibold text-slate-700">{t('warehouse.inventoryReport')}</span>
              <ExportBtns
                onExcel={async () => {
                  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
                  // T2.3: filial/ombor filtri varaq boshida ko'rsatiladi
                  const metaRows = sheetHeaderRows({
                    title: t('warehouse.inventoryReport'), branchName: scopeLabel,
                    dateFrom: today(), dateTo: today(), branchLabel, periodLabel,
                  });
                  const ws = XLSX.utils.aoa_to_sheet(metaRows);
                  XLSX.utils.sheet_add_json(ws, inventoryData.map(i => ({
                    [t('warehouse.product')]: i.variant_name ? `${i.product_name} (${i.variant_name})` : i.product_name, 'SKU': i.sku,
                    [tf('warehouse.warehouseCol', 'Ombor')]: i.warehouse_name || '', [tf('warehouse.branchCol', 'Filial')]: i.branch_name || '',
                    [t('warehouse.stockLevel')]: i.quantity,
                    [t('warehouse.minStock')]: i.min_stock, [t('warehouse.valueLabel')]: i.value, [t('warehouse.statusLabel')]: i.is_low ? t('warehouse.low') : t('warehouse.sufficient'),
                  })), { origin: metaRows.length + 1 });
                  const wb = XLSX.utils.book_new();
                  XLSX.utils.book_append_sheet(wb, ws, 'Ombor');
                  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), exportFileName('ombor', { dateFrom: today(), dateTo: today(), ext: 'xlsx' }));
                }}
                onPdf={() => printTable(t('warehouse.inventoryReport'),
                  [t('warehouse.product'), 'SKU', tf('warehouse.warehouseCol', 'Ombor'), tf('warehouse.branchCol', 'Filial'), t('warehouse.stockLevel'), t('warehouse.minStock'), t('warehouse.valueLabel'), t('warehouse.statusLabel')],
                  inventoryData.map(i => [i.variant_name ? `${i.product_name} (${i.variant_name})` : i.product_name, i.sku, i.warehouse_name, i.branch_name, i.quantity, i.min_stock, fmtS(i.value), i.is_low ? `⚠ ${t('warehouse.low')}` : t('warehouse.sufficient')]),
                  null,
                  t('common.print'),
                  [`${branchLabel}: ${scopeLabel}`, `${periodLabel}: ${today()}`]
                )}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3 px-6 py-3 border-b border-slate-100">
              <BranchSelect value={invBranch} onChange={onInvBranch} branches={branches} />
              <select
                value={invWarehouse}
                onChange={e => setInvWarehouse(e.target.value)}
                className="px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              >
                <option value="">{t('common.allWarehouses')}</option>
                {invWarehouses.map(w => <option key={w.id} value={String(w.id)}>{w.name}</option>)}
              </select>
              {invSummary && (
                <div className="flex flex-wrap items-center gap-2 ml-auto text-xs">
                  <span className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 font-semibold">
                    {tf('warehouse.summaryValue', 'Jami qiymat')}: {fmtS(invSummary.total_value)}
                  </span>
                  <span className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 font-medium">
                    {tf('warehouse.summaryQty', 'Jami miqdor')}: {Number(invSummary.total_qty || 0).toLocaleString('uz-UZ')}
                  </span>
                  <span className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 font-medium">
                    {tf('warehouse.summarySku', 'Mahsulot turlari')}: {invSummary.sku_count}
                  </span>
                </div>
              )}
            </div>
            {invTotal > inventoryData.length && (
              <div className="px-6 py-2 text-xs text-amber-700 bg-amber-50 border-b border-amber-100">
                {tf('warehouse.limitNote', "Ko'rsatilgan {shown} ta qator, jami {total} ta. Filial yoki ombor bo'yicha toraytiring.").replace('{shown}', inventoryData.length).replace('{total}', invTotal)}
              </div>
            )}
            {loading ? <Spinner /> : loadError ? <LoadError t={t} onRetry={load} /> : (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {[t('warehouse.product'), 'SKU', tf('warehouse.warehouseCol', 'Ombor'), tf('warehouse.branchCol', 'Filial'), t('warehouse.stockLevel'), t('warehouse.minStock'), t('warehouse.valueLabel'), t('warehouse.statusLabel')].map(h => (
                        <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {inventoryData.map(i => (
                      <tr key={`${i.product_id}-${i.variant_id ?? 0}-${i.warehouse_id ?? 0}`} className={`hover:bg-slate-50 transition-colors ${i.is_low ? 'bg-blue-50/30' : ''}`}>
                        <td className="px-5 py-3.5 text-sm font-medium text-slate-800">
                          {i.product_name}
                          {i.variant_name && <span className="text-slate-500 font-normal ml-1">({i.variant_name})</span>}
                        </td>
                        <td className="px-5 py-3.5 text-sm font-mono text-blue-600">{i.sku}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-700">{i.warehouse_name || '—'}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-500">{i.branch_name || '—'}</td>
                        <td className="px-5 py-3.5">
                          <span className={`text-sm font-bold ${i.is_low ? 'text-red-500' : 'text-slate-800'}`}>{fmtQty(i.quantity)}</span>
                        </td>
                        <td className="px-5 py-3.5 text-sm text-slate-400">{fmtQty(i.min_stock)}</td>
                        <td className="px-5 py-3.5 text-sm text-slate-700">{fmtS(i.value)}</td>
                        <td className="px-5 py-3.5">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                            i.is_low ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-700'
                          }`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            {i.is_low ? t('warehouse.low') : t('warehouse.sufficient')}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {inventoryData.length === 0 && <tr><td colSpan={8} className="px-6 py-12 text-center text-sm text-slate-400">{t('warehouse.noData')}</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {tab === 'warehouses' && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-slate-100">
              <span className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-slate-700">{t('warehouse.warehousesList')}</span>
                {whUsage?.usage?.warehouses && (() => {
                  const u = whUsage.usage.warehouses;
                  const cls = u.over ? 'bg-red-50 text-red-700 border-red-200'
                    : (u.full ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-slate-50 text-slate-600 border-slate-200');
                  return (
                    <span
                      title={u.over ? tf('warehouse.limitOver', 'Tarif ombor limitidan oshgan') : undefined}
                      className={`text-xs font-bold px-2.5 py-1 rounded-full border ${cls}`}
                    >
                      {tf('warehouse.limitBadge', 'Omborlar: {used}/{limit}').replace('{used}', u.used).replace('{limit}', u.limit == null ? '∞' : u.limit)}
                    </span>
                  );
                })()}
              </span>
              <button
                onClick={openCreate}
                disabled={whUsage?.warehouse_limit_mode === 'enforce' && !!whUsage?.usage?.warehouses?.full}
                title={whUsage?.warehouse_limit_mode === 'enforce' && whUsage?.usage?.warehouses?.full ? tf('warehouse.limitReached', 'Tarif bo\'yicha ombor limitiga yetdingiz') : undefined}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                {t('warehouse.addWarehouse')}
              </button>
            </div>
            {loading ? <Spinner /> : loadError ? <LoadError t={t} onRetry={load} /> : (
              <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase w-12">#</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('warehouse.nameLabel')}</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('purchase.filterBranch')}</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('branch.warehouseType')}</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('warehouse.dateLabel')}</th>
                    <th className="px-4 py-3 w-24" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {warehouses.map((wh, i) => (
                    <tr key={wh.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 text-sm text-slate-500">{i + 1}</td>
                      <td className="px-4 py-3 text-sm text-slate-800 font-medium">
                        {wh.name}
                        {wh.is_default && (
                          <span className="ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded-full border bg-violet-50 text-violet-700 border-violet-200">
                            {t('branch.defaultWarehouse')}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500">
                        {wh.branch_id ? (branches.find(b => b.id === wh.branch_id)?.name || '—') : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500">
                        {WAREHOUSE_TYPE_BY_VALUE[wh.type] ? t(WAREHOUSE_TYPE_BY_VALUE[wh.type].labelKey) : (wh.type || '—')}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500">{fmtDate(wh.created_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => openEdit(wh)}
                            className="p-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                            title={t('warehouse.editLabel')}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M15.232 5.232l3.536 3.536M9 13l6.5-6.5a2 2 0 012.828 0l.172.172a2 2 0 010 2.828L12 16H9v-3z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => setDelConfirm(wh)}
                            className="p-1.5 bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                            title={t('warehouse.deleteLabel')}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {warehouses.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">
                        {t('warehouse.notFound')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              </div>
            )}
          </>
        )}
      </div>

      {/* Delete confirm */}
      {delConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-5">
              <h3 className="text-base font-semibold text-slate-800 mb-2">{t('warehouse.confirmDelete')}</h3>
              <p className="text-sm text-slate-500">
                <span className="font-medium text-slate-700">"{delConfirm.name}"</span> {t('warehouse.confirmDeleteQuestion')}
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={() => setDelConfirm(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                {t('product.cancelAction')}
              </button>
              <button
                onClick={remove}
                className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                {t('warehouse.deleteLabel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h3 className="text-base font-semibold text-slate-800">
                {modal.mode === 'create' ? t('warehouse.addWarehouse') : t('warehouse.editLabel')}
              </h3>
              <button onClick={closeModal} className="text-slate-400 hover:text-slate-600 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="px-6 py-5">
              <input
                autoFocus
                placeholder={t('warehouse.nameLabel')}
                value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && save()}
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {branches.length > 0 && (
                <div className="mt-3">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">{canSelectAll ? t('warehouse.branchOptional') : `${t('ombor.branch')} *`}</label>
                  <select
                    value={branchId}
                    required
                    onChange={e => setBranchId(e.target.value)}
                    className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {/* "Filialsiz" faqat filial cheklovi yo'q (bypass) rollar uchun */}
                    {canSelectAll ? <option value="">— {t('warehouse.noBranch')} —</option>
                      : !branchId && <option value="" disabled>{tf('warehouse.branchRequiredError', 'Filialni tanlang')}</option>}
                    {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                  {branchId && (
                    <label className="mt-2 flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                      <input type="checkbox" checked={isDefault}
                        disabled={modal.mode === 'edit' && !!modal.wh.is_default}
                        onChange={e => setIsDefault(e.target.checked)} />
                      {t('branch.setDefaultWarehouse')}
                    </label>
                  )}
                </div>
              )}
              {err && <p className="mt-2 text-sm text-red-500">{err}</p>}
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                {t('product.cancelAction')}
              </button>
              <button
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
