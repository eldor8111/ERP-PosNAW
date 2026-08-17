/**
 * SizeMatrixModal.jsx
 * Kiyim-kechak uchun razmer × rang matritsasi UI.
 *
 * Foydalanish:
 *   <SizeMatrixModal
 *     product={product}          // { id, name, sale_price, wholesale_price, cost_price }
 *     existingVariants={[...]}   // mavjud variantlar (tahrirlash uchun)
 *     onSave={(variants) => {}}  // [{name, sku, size, color, qty, sale_price}]
 *     onClose={() => {}}
 *   />
 */

import { useState, useMemo, useCallback } from 'react';
import toast from 'react-hot-toast';

// ── Standart razmerlar to'plami ───────────────────────────────
const DEFAULT_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'];

// ── Rang palitrasы ─────────────────────────────────────────────
const PALETTE = [
  { name: "Oq",       hex: "#FFFFFF" },
  { name: "Qora",     hex: "#1a1a1a" },
  { name: "Ko'k",     hex: "#1d4ed8" },
  { name: "Qizil",    hex: "#dc2626" },
  { name: "Yashil",   hex: "#16a34a" },
  { name: "Sariq",    hex: "#eab308" },
  { name: "To'q sariq", hex: "#d97706" },
  { name: "Binafsha", hex: "#7c3aed" },
  { name: "Pushti",   hex: "#ec4899" },
  { name: "Kulrang",  hex: "#6b7280" },
  { name: "Jigarrang",hex: "#92400e" },
  { name: "Moviy",    hex: "#0ea5e9" },
];

// ── Yordamchi ─────────────────────────────────────────────────
const cellKey = (color, size) => `${color}__${size}`;

export default function SizeMatrixModal({ product, existingVariants = [], onSave, onClose }) {
  // Tanlangan razmerlar
  const [sizes, setSizes] = useState(() => {
    if (existingVariants.length > 0) {
      const found = [...new Set(existingVariants.map(v => v.size).filter(Boolean))];
      return found.length > 0 ? found : ['S', 'M', 'L', 'XL'];
    }
    return ['S', 'M', 'L', 'XL'];
  });

  // Ranglar qatori: [{name, hex}]
  const [colors, setColors] = useState(() => {
    if (existingVariants.length > 0) {
      const found = [...new Map(
        existingVariants.filter(v => v.color).map(v => [v.color, { name: v.color, hex: '#6b7280' }])
      ).values()];
      return found.length > 0 ? found : [PALETTE[0]];
    }
    return [PALETTE[1]]; // Qora default
  });

  // Hujayra qiymatlari: { "Qora__XL": { qty: "5", price: "" } }
  const [cells, setCells] = useState(() => {
    const init = {};
    existingVariants.forEach(v => {
      if (v.color && v.size) {
        init[cellKey(v.color, v.size)] = {
          qty: String(v.quantity || ''),
          price: String(v.sale_price || ''),
        };
      }
    });
    return init;
  });

  // Yangi rang qo'shish
  const [newColor, setNewColor] = useState('');
  const [newColorHex, setNewColorHex] = useState('#6b7280');
  const [newSize, setNewSize] = useState('');

  // Umumiy narx (barcha variantlarga bir xil)
  const [globalPrice, setGlobalPrice] = useState(String(product?.sale_price || ''));
  const [globalWholesale, setGlobalWholesale] = useState(String(product?.wholesale_price || ''));

  // Hujayra qiymatini o'zgartirish
  const updateCell = useCallback((color, size, field, value) => {
    const k = cellKey(color, size);
    setCells(prev => ({ ...prev, [k]: { ...(prev[k] || {}), [field]: value } }));
  }, []);

  // Butun ustun yoki qatorni to'ldirish
  const fillRow = (color, qty) => {
    setCells(prev => {
      const next = { ...prev };
      sizes.forEach(s => {
        const k = cellKey(color, s);
        next[k] = { ...(next[k] || {}), qty };
      });
      return next;
    });
  };

  const fillCol = (size, qty) => {
    setCells(prev => {
      const next = { ...prev };
      colors.forEach(c => {
        const k = cellKey(c.name, size);
        next[k] = { ...(next[k] || {}), qty };
      });
      return next;
    });
  };

  // Rang qo'shish
  const addColor = (c) => {
    if (!c.name.trim()) return;
    if (colors.find(x => x.name.toLowerCase() === c.name.toLowerCase())) {
      toast.error('Bu rang allaqachon mavjud'); return;
    }
    setColors(prev => [...prev, { name: c.name.trim(), hex: c.hex }]);
  };

  // Razmer qo'shish
  const addSize = (s) => {
    s = s.trim().toUpperCase();
    if (!s) return;
    if (sizes.includes(s)) { toast.error('Bu razmer allaqachon bor'); return; }
    setSizes(prev => [...prev, s]);
  };

  // Rangni o'chirish
  const removeColor = (name) => {
    setColors(prev => prev.filter(c => c.name !== name));
    setCells(prev => {
      const next = { ...prev };
      sizes.forEach(s => delete next[cellKey(name, s)]);
      return next;
    });
  };

  // Razmerni o'chirish
  const removeSize = (sz) => {
    setSizes(prev => prev.filter(s => s !== sz));
    setCells(prev => {
      const next = { ...prev };
      colors.forEach(c => delete next[cellKey(c.name, sz)]);
      return next;
    });
  };

  // Statistika
  const stats = useMemo(() => {
    let filled = 0, totalQty = 0;
    Object.values(cells).forEach(c => {
      const q = Number(c.qty);
      if (q > 0) { filled++; totalQty += q; }
    });
    return { filled, totalQty, total: sizes.length * colors.length };
  }, [cells, sizes, colors]);

  // Saqlash
  const handleSave = () => {
    const result = [];
    colors.forEach(color => {
      sizes.forEach(size => {
        const k = cellKey(color.name, size);
        const cell = cells[k] || {};
        const qty = Number(cell.qty);
        if (qty > 0 || cell.qty === '0') {
          result.push({
            name: `${size} ${color.name}`,
            size,
            color: color.name,
            colorHex: color.hex,
            quantity: qty,
            sale_price: Number(cell.price) || Number(globalPrice) || null,
            wholesale_price: Number(globalWholesale) || null,
          });
        }
      });
    });

    if (result.length === 0) {
      toast.error("Hech bo'lmaganda bitta katak to'ldirilsin"); return;
    }
    onSave(result);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 backdrop-blur-sm overflow-y-auto py-6 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl animate-in fade-in slide-in-from-bottom-4 duration-300">

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-xl font-black text-slate-800 flex items-center gap-2">
              <span className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center">
                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                </svg>
              </span>
              Razmer Matritsasi
            </h2>
            <p className="text-sm text-slate-500 mt-0.5 ml-10">{product?.name} · Variantlarni jadval ko'rinishida to'ldiring</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs bg-blue-50 text-blue-700 border border-blue-100 px-3 py-1.5 rounded-xl font-semibold">
              {stats.filled} katak · {stats.totalQty} dona
            </span>
            <button onClick={onClose} className="w-9 h-9 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-colors">
              <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">

          {/* ── Umumiy narx ── */}
          <div className="flex gap-3 mb-5 p-4 bg-slate-50 rounded-2xl border border-slate-100">
            <div className="flex-1">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5 block">Chakana narx (umumiy)</label>
              <input
                type="number"
                value={globalPrice}
                onChange={e => setGlobalPrice(e.target.value)}
                className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder="0"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5 block">Ulgurji narx (umumiy)</label>
              <input
                type="number"
                value={globalWholesale}
                onChange={e => setGlobalWholesale(e.target.value)}
                className="w-full px-3 py-2.5 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder="0"
              />
            </div>
            <div className="text-xs text-slate-400 self-end pb-3 ml-1">
              Har bir katakka alohida narx ham kiritish mumkin
            </div>
          </div>

          {/* ── Razmerlar boshqaruvi ── */}
          <div className="mb-4">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">Razmerlar (ustunlar)</label>
            <div className="flex flex-wrap gap-2">
              {sizes.map(s => (
                <span key={s} className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-50 text-blue-700 border border-blue-200 rounded-xl text-sm font-bold">
                  {s}
                  <button onClick={() => removeSize(s)} className="text-blue-400 hover:text-red-500 ml-1 transition-colors">×</button>
                </span>
              ))}
              {/* Tez qo'shish */}
              {DEFAULT_SIZES.filter(s => !sizes.includes(s)).map(s => (
                <button key={s} onClick={() => addSize(s)}
                  className="px-3 py-1.5 bg-slate-100 text-slate-500 rounded-xl text-sm font-medium hover:bg-blue-50 hover:text-blue-600 transition-colors border border-dashed border-slate-200">
                  + {s}
                </button>
              ))}
              {/* Custom razmer */}
              <form onSubmit={e => { e.preventDefault(); addSize(newSize); setNewSize(''); }} className="flex">
                <input
                  value={newSize}
                  onChange={e => setNewSize(e.target.value)}
                  placeholder="+ Boshqa..."
                  className="w-24 px-2 py-1.5 text-sm border border-dashed border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-400 outline-none"
                />
              </form>
            </div>
          </div>

          {/* ── Ranglar boshqaruvi ── */}
          <div className="mb-5">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">Ranglar (qatorlar)</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {colors.map(c => (
                <span key={c.name} className="inline-flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-sm font-medium shadow-sm">
                  <span className="w-4 h-4 rounded-full border border-slate-200 shrink-0" style={{ background: c.hex }} />
                  {c.name}
                  <button onClick={() => removeColor(c.name)} className="text-slate-300 hover:text-red-500 transition-colors">×</button>
                </span>
              ))}
            </div>
            {/* Palitra */}
            <div className="flex flex-wrap gap-1.5 mb-2">
              {PALETTE.filter(p => !colors.find(c => c.name === p.name)).map(p => (
                <button key={p.name} onClick={() => addColor(p)}
                  title={p.name}
                  className="w-7 h-7 rounded-lg border-2 border-transparent hover:border-blue-400 transition-all hover:scale-110 active:scale-95"
                  style={{ background: p.hex, boxShadow: p.hex === '#FFFFFF' ? 'inset 0 0 0 1px #e2e8f0' : undefined }}
                />
              ))}
            </div>
            {/* Custom rang */}
            <form onSubmit={e => { e.preventDefault(); addColor({ name: newColor, hex: newColorHex }); setNewColor(''); }}
              className="flex gap-2 items-center">
              <input type="color" value={newColorHex} onChange={e => setNewColorHex(e.target.value)}
                className="w-9 h-9 rounded-xl cursor-pointer border border-slate-200" />
              <input value={newColor} onChange={e => setNewColor(e.target.value)} placeholder="Rang nomi..."
                className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-400 outline-none" />
              <button type="submit" className="px-4 py-2 bg-blue-600 text-white text-sm rounded-xl font-semibold hover:bg-blue-700 transition-colors">
                Qo'shish
              </button>
            </form>
          </div>

          {/* ── MATRITSA ── */}
          {colors.length > 0 && sizes.length > 0 ? (
            <div className="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gradient-to-r from-blue-600 to-blue-700 text-white">
                    <th className="px-4 py-3 text-left font-bold text-sm rounded-tl-xl min-w-[130px]">
                      Rang ↓ / Razmer →
                    </th>
                    {sizes.map(sz => (
                      <th key={sz} className="px-3 py-3 text-center font-bold min-w-[90px]">
                        <div className="flex flex-col items-center gap-1">
                          <span>{sz}</span>
                          <input
                            type="number"
                            min="0"
                            placeholder="H."
                            title={`Barcha ${sz} razmerlarni to'ldirish`}
                            className="w-14 px-1.5 py-0.5 text-xs text-center text-blue-800 bg-white/90 rounded-lg border border-white/30 focus:ring-1 focus:ring-white outline-none"
                            onBlur={e => { if (e.target.value) fillCol(sz, e.target.value); }}
                            onChange={e => {}}
                          />
                        </div>
                      </th>
                    ))}
                    <th className="px-3 py-3 text-center font-semibold text-blue-100 text-xs min-w-[70px] rounded-tr-xl">Jami</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {colors.map((color, ci) => {
                    const rowTotal = sizes.reduce((sum, s) => sum + (Number(cells[cellKey(color.name, s)]?.qty) || 0), 0);
                    return (
                      <tr key={color.name} className={ci % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
                        {/* Rang nomi */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2.5">
                            <span className="w-5 h-5 rounded-lg border border-slate-200 shrink-0 shadow-sm"
                              style={{ background: color.hex }} />
                            <span className="font-semibold text-slate-700 text-sm">{color.name}</span>
                            {/* Qatorni to'ldirish */}
                            <input
                              type="number" min="0" placeholder="H."
                              title={`Barcha ${color.name} rangli variantlarni to'ldirish`}
                              className="w-12 px-1.5 py-0.5 text-xs text-center border border-slate-200 rounded-lg bg-slate-50 focus:ring-1 focus:ring-blue-400 outline-none ml-1"
                              onBlur={e => { if (e.target.value) fillRow(color.name, e.target.value); }}
                              onChange={() => {}}
                            />
                          </div>
                        </td>
                        {/* Kataklar */}
                        {sizes.map(sz => {
                          const k = cellKey(color.name, sz);
                          const val = cells[k]?.qty ?? '';
                          const hasVal = Number(val) > 0;
                          return (
                            <td key={sz} className="px-2 py-2 text-center">
                              <input
                                type="number"
                                min="0"
                                value={val}
                                onChange={e => updateCell(color.name, sz, 'qty', e.target.value)}
                                className={`w-16 px-2 py-2 text-center text-sm rounded-xl border-2 outline-none transition-all font-semibold
                                  ${hasVal
                                    ? 'border-blue-400 bg-blue-50 text-blue-700 shadow-sm shadow-blue-100'
                                    : 'border-slate-200 bg-white text-slate-400 hover:border-blue-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-100'
                                  }`}
                                placeholder="—"
                              />
                            </td>
                          );
                        })}
                        {/* Qator jami */}
                        <td className="px-3 py-3 text-center">
                          <span className={`text-sm font-black ${rowTotal > 0 ? 'text-blue-700' : 'text-slate-300'}`}>
                            {rowTotal || '—'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {/* Ustun jami */}
                  <tr className="bg-blue-50 font-bold border-t-2 border-blue-100">
                    <td className="px-4 py-3 text-slate-500 text-sm font-semibold">Jami (ustun)</td>
                    {sizes.map(sz => {
                      const colTotal = colors.reduce((sum, c) => sum + (Number(cells[cellKey(c.name, sz)]?.qty) || 0), 0);
                      return (
                        <td key={sz} className="px-2 py-3 text-center">
                          <span className={`text-sm font-black ${colTotal > 0 ? 'text-blue-700' : 'text-slate-300'}`}>
                            {colTotal || '—'}
                          </span>
                        </td>
                      );
                    })}
                    <td className="px-3 py-3 text-center">
                      <span className="text-base font-black text-blue-700">{stats.totalQty}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-16 text-center text-slate-400">
              <svg className="w-12 h-12 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              <p className="text-sm">Rang va razmerlarni tanlang</p>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl">
          <div className="text-sm text-slate-500">
            <span className="font-semibold text-slate-700">{stats.filled}</span> katak to'ldirilgan ·
            Jami <span className="font-semibold text-blue-700">{stats.totalQty}</span> dona variant
          </div>
          <div className="flex gap-3">
            <button onClick={onClose}
              className="px-5 py-2.5 bg-white border border-slate-200 text-slate-600 rounded-xl font-semibold text-sm hover:bg-slate-50 transition-colors">
              Bekor qilish
            </button>
            <button onClick={handleSave}
              disabled={stats.filled === 0}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all shadow-lg shadow-blue-200 active:scale-95">
              ✓ {stats.filled} ta variantni saqlash
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
