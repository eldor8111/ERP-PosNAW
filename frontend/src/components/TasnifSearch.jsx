import { useState, useEffect } from 'react';
import api from '../api/axios';

// ── P.5: tasnif.soliq.uz dan dori topish (faqat dorixona rejimidagi oynalarda) ──────────────────────
// Javob: { name, short_name, mxik_code, barcode, atc_code, manufacturer, dosage_form, strength, substance_name, substances[] }
// short_name — kassa uchun qisqa nom (brend + doza + soni), name — tasnifning to'liq rasmiy nomi

// Shtrix-kod bo'yicha: { status: 'found', drug } | { status: 'notfound' } | { status: 'error', message }
export const lookupDrugByBarcode = async (code) => {
  try {
    const { data } = await api.get(`/pharmacy/tasnif/barcode/${encodeURIComponent(code)}`, { _suppressToast: true });
    return { status: 'found', drug: data };
  } catch (e) {
    if (e.response?.status === 404) return { status: 'notfound' };
    return { status: 'error', message: e.response?.data?.detail || e.message || '' };
  }
};

// Nom bo'yicha qidiruv paneli: natijani tanlasa onPick(drug)
export default function TasnifSearch({ initialQuery = '', onPick, onClose, tf }) {
  const [q, setQ] = useState(initialQuery);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [searched, setSearched] = useState(false);

  const run = async (text) => {
    const term = String(text || '').trim();
    if (term.length < 2 || busy) return;
    setBusy(true); setErr('');
    try {
      const { data } = await api.get('/pharmacy/tasnif/search', { params: { q: term, limit: 15 }, _suppressToast: true });
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      setItems([]);
      setErr(e.response?.data?.detail || tf('tasnif.error', "Tasnif bilan bog'lanib bo'lmadi"));
    } finally {
      setBusy(false); setSearched(true);
    }
  };

  useEffect(() => { if (String(initialQuery).trim().length >= 2) run(initialQuery); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="border border-emerald-200 bg-emerald-50/60 rounded-xl p-3 space-y-2">
      <div className="flex gap-2">
        <input value={q} autoFocus
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); run(q); } }}
          placeholder={tf('tasnif.placeholder', 'Dori nomini yozing, masalan: Enalozid yoki Эналозид')}
          className="flex-1 min-w-0 h-10 px-3 border border-emerald-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500" />
        <button type="button" onClick={() => run(q)} disabled={busy}
          className="px-4 h-10 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-bold whitespace-nowrap">
          {busy ? tf('tasnif.searching', 'Qidirilmoqda...') : tf('tasnif.search', 'Qidirish')}
        </button>
        {onClose && (
          <button type="button" onClick={onClose} className="px-2 h-10 text-slate-400 hover:text-slate-700 text-xl" aria-label="close">×</button>
        )}
      </div>
      {err && <p className="text-xs font-semibold text-red-600">{err}</p>}
      {items.length > 0 && (
        <div className="max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-lg divide-y divide-slate-100">
          {items.map((d, i) => (
            <button type="button" key={`${d.mxik_code}-${d.barcode || i}`} onClick={() => onPick(d)}
              className="w-full text-left px-3 py-2 hover:bg-emerald-50">
              <div className="text-sm font-semibold text-slate-800">{d.short_name || d.name}</div>
              {d.short_name && d.short_name !== d.name && <div className="text-[11px] text-slate-400 leading-snug">{d.name}</div>}
              <div className="text-xs text-slate-500">
                MXIK {d.mxik_code}{d.barcode ? ` · ${d.barcode}` : ''}{d.atc_code ? ` · ATX ${d.atc_code}` : ''}
              </div>
            </button>
          ))}
        </div>
      )}
      {searched && !busy && !err && items.length === 0 && (
        <p className="text-xs text-slate-500">{tf('tasnif.empty', "Topilmadi — boshqacha yozib ko'ring (lotin yoki kirill)")}</p>
      )}
      <p className="text-[11px] text-slate-500">{tf('tasnif.hint', "Tanlang — nomi, MXIK, ATX, ishlab chiqaruvchi o'zi to'ladi")}</p>
    </div>
  );
}
