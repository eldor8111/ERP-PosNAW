import { useState } from 'react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';
import { loadXLSX, loadSaveAs } from '../../../utils/excelLazy';
import { toast } from '../../../utils/toast';

// D4.2: dorixona seriyasi bo'yicha kuzatish va qaytarib olish (recall).
// GET /pharmacy/recall?lot= (kirim, qoldiq, kimga sotilgan, qaytarishlar),
// POST /pharmacy/recall/block (barcha filiallardagi shu seriya 'recalled'; admin Telegram xabari),
// mijozlar ro'yxati Excel (.xlsx) ga eksport qilinadi (GET /pharmacy/recall/customers — CSV variant).
// Sahifaga D4.6 ulaydi; komponent mustaqil (props yo'q).
const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ');
const fmtDate = (s) => (s ? String(s).slice(0, 16).replace('T', ' ') : '-');

export default function RecallPanel() {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const features = useCompanyFeatures();

  const [lot, setLot] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dlg, setDlg] = useState(null); // { reason }
  const [saving, setSaving] = useState(false);

  const search = async () => {
    const q = lot.trim();
    if (!q) { toast.error(tf('pharmacyRecall.lotRequired', 'Seriya raqamini kiriting')); return; }
    setLoading(true);
    try {
      const r = await api.get('/pharmacy/recall', { params: { lot: q }, _suppressToast: true });
      setData(r.data);
    } catch (e) {
      setData(null);
      const d = e?.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : tf('pharmacyRecall.loadFailed', "Seriyani yuklab bo'lmadi"));
    } finally { setLoading(false); }
  };

  const block = async () => {
    if (!dlg?.reason.trim()) { toast.error(tf('pharmacyRecall.reasonRequired', 'Sababni kiriting')); return; }
    setSaving(true);
    try {
      const r = await api.post('/pharmacy/recall/block', { lot: data.lot, reason: dlg.reason.trim() });
      toast.success(`${tf('pharmacyRecall.blocked', 'Bloklandi')}: ${r.data.blocked_batches}`);
      setDlg(null);
      search();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : tf('pharmacyRecall.blockFailed', "Seriyani bloklab bo'lmadi"));
    } finally { setSaving(false); }
  };

  const exportCustomers = async () => {
    const sales = data?.sales || [];
    if (!sales.length) { toast.error(tf('pharmacyRecall.noCustomers', "Mijozlar yo'q")); return; }
    const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
    const ws = XLSX.utils.json_to_sheet(sales.map(s => ({
      [tf('pharmacyRecall.customer', 'Mijoz')]: s.customer_name || '',
      [tf('pharmacyRecall.phone', 'Telefon')]: s.customer_phone || '',
      [tf('pharmacyRecall.date', 'Sana')]: fmtDate(s.sold_at),
      [tf('pharmacyRecall.sale', 'Sotuv')]: s.sale_number,
      [tf('pharmacyRecall.branch', 'Filial')]: s.branch_name || '',
      [tf('pharmacyRecall.product', 'Mahsulot')]: s.product_name,
      [tf('pharmacyRecall.lot', 'Seriya')]: data.lot,
      [tf('pharmacyRecall.quantity', 'Miqdor')]: s.quantity,
      [tf('pharmacyRecall.returned', 'Qaytarilgan')]: s.returned_quantity,
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, tf('pharmacyRecall.customers', 'Mijozlar').slice(0, 31));
    saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), `seriya_mijozlari_${new Date().toISOString().slice(0, 10)}.xlsx`);
  };

  if (features && !features.pharmacy) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm text-sm text-slate-500">
        {tf('pharmacyRecall.disabled', 'Dorixona moduli yoqilmagan (Sozlamalar → Umumiy).')}
      </div>
    );
  }

  const sm = data?.summary;
  const hasActive = (data?.batches || []).some(b => b.status !== 'recalled');

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <h3 className="text-sm font-bold text-slate-700">{tf('pharmacyRecall.title', 'Seriya kuzatuvi va qaytarib olish')}</h3>
      <p className="text-xs text-slate-400 mt-0.5 mb-3">
        {tf('pharmacyRecall.desc', "Seriya raqami bo'yicha: qaysi ta'minotchidan kelgan, qayerda qolgan va kimga sotilgan. Bloklangan seriya sotilmaydi.")}
      </p>

      <div className="flex flex-wrap items-end gap-2 mb-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">{tf('pharmacyRecall.lot', 'Seriya')}</span>
          <input
            value={lot} onChange={e => setLot(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') search(); }}
            className="border border-slate-200 rounded-xl px-2 py-1.5 w-48"
          />
        </label>
        <button onClick={search} disabled={loading} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl disabled:opacity-50">
          {tf('pharmacyRecall.search', 'Qidirish')}
        </button>
        {data?.found && (
          <>
            <button onClick={exportCustomers} disabled={!data.sales.length} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold rounded-xl disabled:opacity-50">
              {tf('pharmacyRecall.exportCustomers', 'Mijozlar (Excel)')}
            </button>
            <button onClick={() => setDlg({ reason: '' })} disabled={!hasActive} className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl disabled:opacity-50">
              {tf('pharmacyRecall.blockBtn', 'Seriyani bloklash')}
            </button>
          </>
        )}
      </div>

      {loading && <div className="text-xs text-slate-400">{t('common.loading')}</div>}
      {data && !data.found && !loading && (
        <div className="text-xs text-slate-400">{tf('pharmacyRecall.notFound', 'Seriya topilmadi')}</div>
      )}

      {data?.found && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 text-xs">
            {[
              ['received', 'Kirim', sm.received],
              ['remaining', 'Qoldiq', sm.remaining],
              ['sold', 'Sotilgan', sm.sold],
              ['customers', 'Mijozlar', sm.customers_count],
              ['returnedCustomers', 'Mijozlar qaytargan', sm.returned_by_customers],
              ['returnedSupplier', "Ta'minotchiga qaytarilgan", sm.returned_to_supplier],
              ['salesCount', 'Sotuvlar soni', sm.sales_count],
              ['walkIn', 'Mijozsiz sotuvlar', sm.walk_in_sales],
            ].map(([k, label, v]) => (
              <div key={k} className="bg-slate-50 rounded-xl px-3 py-2">
                <div className="text-slate-500">{tf(`pharmacyRecall.sum.${k}`, label)}</div>
                <div className="text-sm font-bold text-slate-700">{fmt(v)}</div>
              </div>
            ))}
          </div>

          <h4 className="text-xs font-bold text-slate-600 mb-1">{tf('pharmacyRecall.batches', "Kirim va qoldiq (partiyalar)")}</h4>
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-2">{tf('pharmacyRecall.product', 'Mahsulot')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.supplier', "Ta'minotchi")}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.purchase', 'Xarid')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.received', 'Kelgan')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.warehouse', 'Ombor')}</th>
                  <th className="py-2 pr-2 text-right">{tf('pharmacyRecall.initial', 'Kirim')}</th>
                  <th className="py-2 pr-2 text-right">{tf('pharmacyRecall.remaining', 'Qoldiq')}</th>
                  <th className="py-2">{tf('pharmacyRecall.status', 'Holat')}</th>
                </tr>
              </thead>
              <tbody>
                {data.batches.map(b => (
                  <tr key={b.batch_id} className="border-b border-slate-100">
                    <td className="py-2 pr-2 font-semibold text-slate-700">{b.product_name}{b.variant_name ? ` (${b.variant_name})` : ''}</td>
                    <td className="py-2 pr-2">{b.supplier_name || '-'}{b.supplier_phone ? ` · ${b.supplier_phone}` : ''}</td>
                    <td className="py-2 pr-2">{b.po_number || '-'}{b.supplier_invoice_number ? ` · ${b.supplier_invoice_number}` : ''}</td>
                    <td className="py-2 pr-2">{fmtDate(b.received_at)}</td>
                    <td className="py-2 pr-2">{b.warehouse_name || '-'}{b.branch_name ? ` (${b.branch_name})` : ''}</td>
                    <td className="py-2 pr-2 text-right">{fmt(b.initial_quantity)}</td>
                    <td className="py-2 pr-2 text-right">{fmt(b.quantity)}</td>
                    <td className="py-2">
                      <span className={`px-2 py-0.5 rounded-lg font-semibold ${b.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                        {b.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h4 className="text-xs font-bold text-slate-600 mb-1">{tf('pharmacyRecall.sold', 'Kimga sotilgan')}</h4>
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-2">{tf('pharmacyRecall.date', 'Sana')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.sale', 'Sotuv')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.customer', 'Mijoz')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.phone', 'Telefon')}</th>
                  <th className="py-2 pr-2">{tf('pharmacyRecall.branch', 'Filial')}</th>
                  <th className="py-2 pr-2 text-right">{tf('pharmacyRecall.quantity', 'Miqdor')}</th>
                  <th className="py-2 text-right">{tf('pharmacyRecall.returned', 'Qaytarilgan')}</th>
                </tr>
              </thead>
              <tbody>
                {data.sales.map((s, i) => (
                  <tr key={`${s.sale_id}-${s.batch_id}-${i}`} className="border-b border-slate-100">
                    <td className="py-2 pr-2">{fmtDate(s.sold_at)}</td>
                    <td className="py-2 pr-2">{s.sale_number}</td>
                    <td className="py-2 pr-2">{s.customer_name || <span className="text-slate-400">{tf('pharmacyRecall.walkIn', 'Mijozsiz')}</span>}</td>
                    <td className="py-2 pr-2">{s.customer_phone || '-'}</td>
                    <td className="py-2 pr-2">{s.branch_name || '-'}</td>
                    <td className="py-2 pr-2 text-right">{fmt(s.quantity)}</td>
                    <td className="py-2 text-right">{fmt(s.returned_quantity)}</td>
                  </tr>
                ))}
                {!data.sales.length && (
                  <tr><td colSpan={7} className="py-4 text-center text-slate-400">{tf('pharmacyRecall.noSales', "Sotuv yo'q")}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {data.supplier_returns.length > 0 && (
            <>
              <h4 className="text-xs font-bold text-slate-600 mb-1">{tf('pharmacyRecall.supplierReturns', "Ta'minotchiga qaytarishlar")}</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <tbody>
                    {data.supplier_returns.map((r, i) => (
                      <tr key={`${r.log_id}-${r.batch_id}-${i}`} className="border-b border-slate-100">
                        <td className="py-2 pr-2">{fmtDate(r.returned_at)}</td>
                        <td className="py-2 pr-2">{r.supplier_name || '-'}</td>
                        <td className="py-2 pr-2 text-right">{fmt(r.quantity)}</td>
                        <td className="py-2 text-slate-400">{r.reverted ? tf('pharmacyRecall.reverted', 'bekor qilingan') : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {dlg && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => !saving && setDlg(null)}>
          <div className="bg-white rounded-2xl p-5 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
            <h4 className="text-sm font-bold text-slate-700 mb-1">{tf('pharmacyRecall.blockTitle', 'Seriyani bloklash')}</h4>
            <p className="text-xs text-slate-500 mb-3">
              {tf('pharmacyRecall.lot', 'Seriya')}: {data.lot} · {tf('pharmacyRecall.blockHint', "barcha filiallardagi shu seriya sotuvdan olinadi, adminlarga Telegram xabari yuboriladi")}
            </p>
            <label className="flex flex-col gap-1 text-xs mb-4">
              <span className="text-slate-500">{tf('pharmacyRecall.reason', 'Sabab')} *</span>
              <textarea
                value={dlg.reason} onChange={e => setDlg({ reason: e.target.value })}
                rows={3} maxLength={500}
                className="border border-slate-200 rounded-xl px-2 py-1.5"
              />
            </label>
            <div className="flex justify-end gap-2 text-xs">
              <button onClick={() => setDlg(null)} disabled={saving} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold rounded-xl disabled:opacity-50">
                {tf('pharmacyRecall.cancel', 'Bekor qilish')}
              </button>
              <button onClick={block} disabled={saving} className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl disabled:opacity-50">
                {tf('pharmacyRecall.confirm', 'Bloklash')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
