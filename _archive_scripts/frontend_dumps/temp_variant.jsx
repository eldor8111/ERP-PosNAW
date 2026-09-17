function VariantManager({ form, setForm }) {
  const [sizes, setSizes] = useState('');
  const [colors, setColors] = useState('');

  const generate = (e) => {
    e.preventDefault();
    const szList = sizes.split(',').map(s => s.trim()).filter(Boolean);
    const coList = colors.split(',').map(s => s.trim()).filter(Boolean);
    
    let combinations = [];
    if (szList.length > 0 && coList.length > 0) {
      szList.forEach(s => coList.forEach(c => combinations.push({ size: s, color: c })));
    } else if (szList.length > 0) {
      szList.forEach(s => combinations.push({ size: s, color: '' }));
    } else if (coList.length > 0) {
      coList.forEach(c => combinations.push({ size: '', color: c }));
    }

    const newVariants = combinations.map(combo => ({
      size: combo.size,
      color: combo.color,
      sku: '',
      barcode: '',
      cost_price: form.cost_price || '',
      sale_price: form.sale_price || '',
      wholesale_price: form.wholesale_price || ''
    }));
    
    setForm(prev => ({ ...prev, variants: [...(prev.variants || []), ...newVariants] }));
    setSizes('');
    setColors('');
  };

  const removeVariant = (e, idx) => {
    e.preventDefault();
    const nv = [...(form.variants || [])];
    nv.splice(idx, 1);
    setForm(prev => ({ ...prev, variants: nv }));
  };

  const updateVariant = (idx, field, val) => {
    const nv = [...(form.variants || [])];
    nv[idx][field] = val;
    setForm(prev => ({ ...prev, variants: nv }));
  };

  return (
    <div className="bg-indigo-50/50 p-4 rounded-2xl border border-indigo-100 space-y-4 mt-6">
      <div className="flex justify-between items-center">
        <h4 className="text-[13px] font-bold text-indigo-700">Mahsulot Variantlari (Razmer va Ranglar)</h4>
      </div>
      
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="block text-xs font-semibold text-slate-600 mb-1">Razmerlar (vergul bilan)</label>
          <input className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:border-indigo-500" placeholder="S, M, L, 42, 44..." value={sizes} onChange={e=>setSizes(e.target.value)} />
        </div>
        <div className="flex-1">
          <label className="block text-xs font-semibold text-slate-600 mb-1">Ranglar (vergul bilan)</label>
          <input className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:border-indigo-500" placeholder="Oq, Qora, Qizil..." value={colors} onChange={e=>setColors(e.target.value)} />
        </div>
        <button onClick={generate} disabled={!sizes && !colors} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold disabled:opacity-50">
          Yaratish
        </button>
      </div>

      {(form.variants || []).length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-indigo-100 text-[11px] uppercase tracking-wider text-indigo-500">
                <th className="pb-2 pr-2">Razmer</th>
                <th className="pb-2 pr-2">Rang</th>
                <th className="pb-2 pr-2">Shtrix-kod</th>
                <th className="pb-2 pr-2">Tan narx</th>
                <th className="pb-2 pr-2">Sotuv narx</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {form.variants.map((v, i) => (
                <tr key={i} className="border-b border-indigo-50 last:border-0">
                  <td className="py-2 pr-2 font-medium">{v.size || '-'}</td>
                  <td className="py-2 pr-2 font-medium">{v.color || '-'}</td>
                  <td className="py-2 pr-2"><input className="w-28 px-2 py-1 border rounded" placeholder="Avtomatik" value={v.barcode} onChange={e=>updateVariant(i, 'barcode', e.target.value)} /></td>
                  <td className="py-2 pr-2"><input className="w-20 px-2 py-1 border rounded" type="number" value={v.cost_price} onChange={e=>updateVariant(i, 'cost_price', e.target.value)} /></td>
                  <td className="py-2 pr-2"><input className="w-20 px-2 py-1 border rounded" type="number" value={v.sale_price} onChange={e=>updateVariant(i, 'sale_price', e.target.value)} /></td>
                  <td className="py-2 text-right">
                    <button onClick={(e)=>removeVariant(e, i)} className="text-red-500 hover:bg-red-50 p-1 rounded"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

